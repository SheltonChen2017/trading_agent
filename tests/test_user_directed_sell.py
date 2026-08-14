"""Owner-directed sells of an individual held position (2026-08-13 request).

The dangerous directions this pins:

* proposing a sale of shares the account does not hold (a short) -- via an
  oversized request, a fractional holding rounded up, or a corrupt row;
* a NaN/float/bool share count sailing through, which defeats every ordered
  comparison and every downstream dollar check;
* silently shrinking the owner's requested quantity instead of saying no;
* losing the tax-consequence disclosure that the policy-breach path carries;
  and
* the proposal claiming project evidence it does not have.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import (
    DecisionPacket,
    MarketRegime,
    PortfolioPosition,
    PortfolioSnapshot,
)
from assistant.tax_lots import Fill, build_ledger
from assistant.user_directed_sell import (
    EVIDENCE_STATUS,
    generate_user_directed_sell_proposal,
    sellable_whole_shares,
)

_NOW = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)


def _packet(positions=None, cash=10_000.0):
    snapshot = build_portfolio_snapshot(positions or [], cash=cash)
    return DecisionPacket(
        generated_at="2026-08-13T15:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-12",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _position(ticker="NVDA", shares=10, price=100.0, entry=90.0):
    return {
        "ticker": ticker,
        "shares": shares,
        "current_price": price,
        "entry_price": entry,
    }


def _policy(max_order_value=50_000.0, *, whole_shares_only=True):
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0,
        max_order_value=max_order_value, allow_new_positions=False,
        whole_shares_only=whole_shares_only,
    )


def _sell(shares=3, ticker="NVDA", positions=None, policy=None, **kwargs):
    return generate_user_directed_sell_proposal(
        _packet(positions if positions is not None else [_position()]),
        policy or _policy(),
        ticker=ticker,
        shares=shares,
        now=_NOW,
        **kwargs,
    )


# --- the happy path --------------------------------------------------------


def test_creates_an_approve_gated_sell_for_a_held_position():
    result = _sell(shares=3)
    assert result["created"] is True
    proposal = result["proposal"]
    assert proposal.intent.side == "sell"
    assert proposal.intent.shares == 3
    assert proposal.intent.ticker == "NVDA"
    assert proposal.status == "proposed", "never pre-approved"
    assert proposal.reference_price == 100.0


def test_the_evidence_status_claims_nothing_the_project_has_not_measured():
    proposal = _sell()["proposal"]
    assert proposal.evidence_status == EVIDENCE_STATUS
    assert "confirmed" not in proposal.evidence_status
    # And the copy must not imply a price prediction.
    text = " ".join(proposal.reasons + proposal.uncertainties)
    assert "zero signals as real edge" in text


def test_selling_every_whole_share_says_it_closes_the_position():
    result = _sell(shares=10)
    assert result["created"] is True
    assert any("closes the entire" in r for r in result["proposal"].reasons)


def test_a_lowercase_ticker_still_matches_the_held_position():
    result = _sell(ticker="nvda", shares=2)
    assert result["created"] is True
    assert result["proposal"].intent.ticker == "NVDA"


# --- never short -----------------------------------------------------------


def test_selling_more_than_held_is_refused():
    result = _sell(shares=11)
    assert result["created"] is False
    assert "would short the position" in result["reason"]
    assert "10 whole share(s)" in result["reason"]


def test_an_unheld_ticker_is_refused():
    result = _sell(ticker="AMD")
    assert result["created"] is False
    assert "not currently held" in result["reason"]


@pytest.mark.parametrize(
    "held, expected",
    [(10.5, 10), (0.4, 0), (10, 10), (0, 0), (-3, 0), (float("nan"), 0),
     (float("inf"), 0), ("x", 0), (None, 0)],
)
def test_fractional_holdings_floor_and_bad_ones_yield_nothing(held, expected):
    """Rounding UP would propose selling shares that do not exist."""
    assert sellable_whole_shares(held) == expected


def test_a_fractional_holding_caps_at_the_floored_whole_shares():
    positions = [_position(shares=10.5)]
    assert _sell(shares=10, positions=positions)["created"] is True
    over = _sell(shares=11, positions=positions)
    assert over["created"] is False
    assert "would short the position" in over["reason"]


def test_exact_fractional_holding_cannot_round_up_into_a_short_sale():
    """The broker's exact quantity outranks its lossy float display field.

    float("10.999999999999999999") is 11.0.  Reading only that display field
    would offer and propose 11 shares even though the account owns less.
    """
    result = _sell(
        shares=11,
        positions=[_position(shares="10.999999999999999999")],
    )
    assert result["created"] is False
    assert "would short the position" in result["reason"]
    assert "10 whole share(s)" in result["reason"]


def test_selling_all_whole_shares_of_a_fractional_holding_does_not_claim_close():
    result = _sell(shares=10, positions=[_position(shares="10.5")])
    assert result["created"] is True

    proposal = result["proposal"]
    text = " ".join([proposal.intent.rationale, *proposal.reasons])
    assert "closes the whole position" not in text
    assert "closes the entire" not in text
    assert "0.5" in text and "remain" in text


def _raw_packet(position: PortfolioPosition) -> DecisionPacket:
    """A snapshot built WITHOUT build_portfolio_snapshot's validation.

    That constructor already refuses non-finite rows (verified: it raises on
    a NaN/inf price), so these adversarial rows cannot arrive through it
    today. The generator's own guards are the second line of defence for any
    other snapshot source, and an untested second line is an assumed one.
    """
    snapshot = PortfolioSnapshot(
        positions=[position], cash=10_000.0, total_equity=11_000.0,
        as_of="2026-08-13",
    )
    return DecisionPacket(
        generated_at="2026-08-13T15:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(build_portfolio_snapshot([], cash=10_000.0)),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-12",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _raw_position(shares=10.0, price=100.0, ticker="BAD") -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker, shares=shares, entry_price=90.0, current_price=price,
        market_value=1000.0, unrealized_pnl_pct=1.0, is_leveraged_etf=False,
    )


def test_a_corrupt_share_count_refuses_only_that_ticker():
    result = generate_user_directed_sell_proposal(
        _raw_packet(_raw_position(shares=float("nan"))),
        _policy(), ticker="BAD", shares=1, now=_NOW,
    )
    assert result["created"] is False
    assert "not a usable whole-share quantity" in result["reason"]


# --- share-quantity validity ----------------------------------------------


@pytest.mark.parametrize(
    "shares", [0, -1, 2.0, 2.5, float("nan"), float("inf"), True, False, "3", None]
)
def test_only_a_real_positive_integer_share_count_is_accepted(shares):
    """Reuses risk.execution_gate.is_valid_share_quantity, the project's
    existing authority -- a whole-valued float and a bool are rejected too,
    because the broker layer applies exactly the same rule."""
    result = _sell(shares=shares)
    assert result["created"] is False
    assert "whole number greater than zero" in result["reason"]


def test_fractional_policy_can_sell_an_exact_fraction_without_shorting():
    result = _sell(
        shares="0.125",
        policy=_policy(whole_shares_only=False),
        positions=[_position(shares="1.25")],
    )
    assert result["created"] is True
    proposal = result["proposal"]
    assert proposal.intent.shares == "0.125"
    assert any("1.125 share(s)" in reason for reason in proposal.reasons)


def test_fractional_policy_refuses_one_nano_share_more_than_held():
    result = _sell(
        shares="1.250000001",
        policy=_policy(whole_shares_only=False),
        positions=[_position(shares="1.25")],
    )
    assert result["created"] is False
    assert "would short" in result["reason"]


# --- pricing ---------------------------------------------------------------


@pytest.mark.parametrize("price", [0.0, -5.0])
def test_a_nonpositive_price_refuses_rather_than_pricing_the_sale_wrong(price):
    result = _sell(shares=1, positions=[_position(price=price)])
    assert result["created"] is False
    assert "no usable current price" in result["reason"]


@pytest.mark.parametrize("price", [float("nan"), float("inf")])
def test_a_non_finite_price_refuses_at_the_generator_too(price):
    """Defence in depth: build_portfolio_snapshot already refuses these, so
    this exercises the generator's own guard through a raw snapshot. Without
    it, NaN would defeat the max-order-value comparison silently (every
    ordered comparison against NaN is False)."""
    result = generate_user_directed_sell_proposal(
        _raw_packet(_raw_position(price=price)),
        _policy(), ticker="BAD", shares=1, now=_NOW,
    )
    assert result["created"] is False
    assert "no usable current price" in result["reason"]


# --- max order value: state it, never silently shrink ----------------------


def test_an_oversized_order_is_refused_with_the_number_that_fits():
    result = _sell(shares=10, policy=_policy(max_order_value=550.0))
    assert result["created"] is False
    assert "maximum order value" in result["reason"]
    # 550 / 100 = 5 whole shares fit.
    assert "up to 5 share(s) fit" in result["reason"]


def test_the_requested_quantity_is_never_silently_reduced():
    """The refusal above must not become a quiet edit of the owner's own
    instruction -- a proposal for fewer shares than asked would be an
    action-shaped change nobody approved."""
    result = _sell(shares=10, policy=_policy(max_order_value=550.0))
    assert result["created"] is False
    assert "proposal" not in result


def test_a_single_share_over_the_limit_says_so_plainly():
    result = _sell(shares=1, policy=_policy(max_order_value=50.0))
    assert result["created"] is False
    assert "Even one share exceeds that limit" in result["reason"]


def test_exactly_at_the_maximum_order_value_is_allowed():
    """Boundary: the gate refuses only when trade value EXCEEDS the cap, so
    proposing at exactly the cap must not be refused here either."""
    result = _sell(shares=5, policy=_policy(max_order_value=500.0))
    assert result["created"] is True


def test_decimal_exact_maximum_order_boundary_is_allowed():
    """3 * 0.1 is exactly 0.3 in decimal, despite its binary-float value."""
    result = _sell(
        shares=3,
        positions=[_position(shares="3", price="0.1")],
        policy=_policy(max_order_value=0.3),
    )
    assert result["created"] is True


# --- tax disclosure --------------------------------------------------------


def test_the_tax_advisory_is_attached_when_lot_history_covers_the_sale():
    ledger = build_ledger(
        [
            Fill(
                ticker="NVDA", side="buy", qty=10, price=90.0,
                at=datetime(2024, 1, 5, tzinfo=timezone.utc), fill_id="f1",
            )
        ]
    )
    result = _sell(shares=3, tax_lot_ledger=ledger)
    advisory = result["proposal"].expected_impact["tax_lot_advisory"]
    assert advisory["available"] is True
    assert advisory["advisory_only"] is True
    assert any("1099-B" in u for u in result["proposal"].uncertainties)


def test_missing_lot_history_says_so_instead_of_implying_no_tax():
    result = _sell(shares=3, tax_lot_coverage={"reason": "no imported fills"})
    advisory = result["proposal"].expected_impact["tax_lot_advisory"]
    assert advisory["available"] is False
    assert advisory["advisory_only"] is True
    assert "no imported fills" in advisory["reason"]
    assert any("never blocks a risk-reducing sell" in u
               for u in result["proposal"].uncertainties)


def test_the_shared_advisory_helper_is_the_same_one_the_breach_path_uses():
    """Consolidated deliberately: a second hand-copied tax disclosure is how
    one surface quietly stops matching the other."""
    import assistant.proposals as proposals
    import assistant.user_directed_sell as user_directed_sell

    assert (
        user_directed_sell.attach_tax_lot_advisory
        is proposals.attach_tax_lot_advisory
    )


# --- identity --------------------------------------------------------------


def test_the_proposal_id_is_namespaced_and_quantity_specific():
    three = _sell(shares=3)["proposal"]
    four = _sell(shares=4)["proposal"]
    assert three.proposal_id != four.proposal_id
    assert three.idempotency_key.endswith(three.proposal_id.split("tp_")[-1]) is False
    assert three.idempotency_key.startswith(three.proposal_id)


def test_regenerating_the_same_request_is_deterministic():
    assert _sell(shares=3)["proposal"].proposal_id == _sell(shares=3)["proposal"].proposal_id
