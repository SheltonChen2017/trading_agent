"""Tests for assistant/proposals.py -- generate_risk_reduction_proposals()
and its total-exposure remediation (GPT review, 2026-07-31)."""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.tax_lots import Fill, build_ledger


def _packet(positions: list[dict], cash: float) -> DecisionPacket:
    snapshot = build_portfolio_snapshot(positions, cash=cash)
    return DecisionPacket(
        generated_at="2026-07-31T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-31",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _permissive_policy(
    max_total_exposure_pct: float = 1.0,
    max_basket_pct: float = 1.0,
    max_position_pct: float | None = None,
    max_leveraged_etf_pct: float = 1.0,
    max_order_value: float = 100_000.0,
) -> TradingPolicy:
    if max_position_pct is None:
        max_position_pct = max_total_exposure_pct
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=max_position_pct, max_total_exposure_pct=max_total_exposure_pct,
        max_basket_pct=max_basket_pct, max_leveraged_etf_pct=max_leveraged_etf_pct,
        min_cash_reserve_pct=0.0, max_order_value=max_order_value,
    )


# --- Total-exposure remediation (P1, GPT review, 2026-07-31):
# generate_risk_reduction_proposals() never checked policy.
# max_total_exposure_pct at all -- a diversified portfolio well over the
# cap, with every individual position/basket/leveraged check passing,
# got ZERO remediation proposals.

def test_total_exposure_breach_with_no_individual_violations_produces_a_proposal():
    # 3 positions at $30k each (30% of equity individually, well under
    # a 100% per-position cap) -> $90k invested = 90% of a $100k account,
    # against a 50% total-exposure cap. No position/basket/leveraged
    # check fires (all set to 100%/permissive) -- only the total-exposure
    # check should.
    positions = [
        {"ticker": "AAA", "shares": 300, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": "BBB", "shares": 300, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": "CCC", "shares": 300, "entry_price": 100.0, "current_price": 100.0},
    ]
    packet = _packet(positions, cash=10_000.0)
    assert packet.portfolio.total_equity == 100_000.0
    policy = _permissive_policy(max_total_exposure_pct=0.50)

    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals, "expected at least one total-exposure remediation proposal"
    assert all(p.intent.side == "sell" for p in proposals)
    assert any("total invested exposure" in r.lower() for p in proposals for r in p.reasons)


def test_total_exposure_breach_does_not_fire_when_within_cap():
    positions = [
        {"ticker": "AAA", "shares": 100, "entry_price": 100.0, "current_price": 100.0},
    ]
    packet = _packet(positions, cash=90_000.0)  # 10% invested
    policy = _permissive_policy(max_total_exposure_pct=0.50)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals == []


def test_total_exposure_remediation_accounts_for_already_planned_reductions():
    # A tight per-position cap already forces most of AAA's excess to be
    # sold; the total-exposure remediation must not ALSO independently
    # demand the full total-exposure gap from AAA on top of that (which
    # would over-sell it) -- it should only ask for whatever's left after
    # crediting the position-cap reduction already planned.
    positions = [
        {"ticker": "AAA", "shares": 500, "entry_price": 100.0, "current_price": 100.0},  # $50k, 50% of equity
        {"ticker": "BBB", "shares": 300, "entry_price": 100.0, "current_price": 100.0},  # $30k, 30% of equity
    ]
    packet = _packet(positions, cash=20_000.0)  # total equity = $100k, invested = $80k (80%)
    policy = _permissive_policy(
        max_position_pct=0.20,  # AAA (50%) way over -> forces a big AAA sell
        max_total_exposure_pct=0.50,  # 80% invested is also over this
        max_order_value=100_000.0,
    )
    proposals = generate_risk_reduction_proposals(packet, policy)
    by_ticker = {p.intent.ticker: p for p in proposals}
    assert "AAA" in by_ticker
    # AAA's reduction must satisfy BOTH the position cap (down to $20k,
    # i.e. sell $30k = 300 shares) AND, combined with any BBB sell,
    # close the total-exposure gap ($80k - $50k = $30k excess) -- selling
    # 300 AAA shares ($30k) alone already closes the total-exposure gap
    # exactly, so BBB should need no additional sell.
    assert by_ticker["AAA"].intent.shares >= 300
    total_sold_value = sum(p.intent.shares * p.reference_price for p in proposals)
    assert total_sold_value >= 30_000.0 - 1.0  # closes (at least) the real exposure gap


# --- Basket-cap rounding fix (P1, GPT review, 2026-07-31): the basket
# check used to compare packet.risk.basket_exposure_pct (a value ALREADY
# rounded to 1 decimal for display) against the cap, so a true exposure
# just above the boundary (e.g. 40.04%) could round down to exactly the
# limit (40.0%) and silently evade proposal generation.

def test_basket_breach_just_above_the_rounding_boundary_still_fires():
    # NVDA + AMD (both in config.BASKETS["semiconductors"]) at exactly
    # 40.04% of a $100k account -- rounds to "40.0%" for DISPLAY, which
    # the old buggy comparison (`pct <= cap*100` using the rounded value)
    # would have treated as within a 40% cap.
    positions = [
        {"ticker": "NVDA", "shares": 1, "entry_price": 25_040.0, "current_price": 25_040.0},
        {"ticker": "AMD", "shares": 1, "entry_price": 15_000.0, "current_price": 15_000.0},
    ]
    packet = _packet(positions, cash=59_960.0)
    assert packet.portfolio.total_equity == 100_000.0
    basket_pct_rounded = packet.risk.basket_exposure_pct["semiconductors"]
    assert basket_pct_rounded == 40.0  # confirms the display value rounds down to exactly the cap

    policy = _permissive_policy(max_basket_pct=0.40)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals, "expected the basket breach to fire despite rounding down to exactly the cap for display"
    assert any("semiconductors" in r.lower() for p in proposals for r in p.reasons)


def test_basket_breach_genuinely_within_cap_does_not_fire():
    positions = [
        {"ticker": "NVDA", "shares": 1, "entry_price": 10_000.0, "current_price": 10_000.0},
    ]
    packet = _packet(positions, cash=90_000.0)  # 10% -- well under a 40% basket cap
    policy = _permissive_policy(max_basket_pct=0.40)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals == []


# --- Regression: pre-existing position/leveraged-ETF checks still work.

def test_position_cap_breach_still_produces_a_proposal():
    positions = [{"ticker": "AAA", "shares": 100, "entry_price": 100.0, "current_price": 100.0}]
    packet = _packet(positions, cash=0.0)  # 100% in one position
    policy = _permissive_policy(max_position_pct=0.05)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any("position exceeds" in r.lower() for p in proposals for r in p.reasons)


def test_max_order_value_cap_uses_exact_price_not_rounded_display_float():
    # This exact price is just above one third of the $100 cap, while its
    # binary-float display companion makes 100 / display_price equal 3.0.
    # Authoritative sizing must therefore floor the exact quotient to two.
    price = "33.333333333333333334"
    packet = _packet(
        [
            {
                "ticker": "AAA",
                "shares": "10",
                "entry_price": price,
                "current_price": price,
            }
        ],
        cash=0,
    )
    policy = _permissive_policy(max_position_pct=0.50, max_order_value=100.0)

    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    exact_price = packet.portfolio.positions[0].exact_field("current_price")

    assert proposal.intent.shares == 2
    assert exact_price * proposal.intent.shares <= Decimal("100")


def test_max_order_cap_retains_digits_past_default_decimal_precision():
    price = "33.33333333333333333333333334"
    packet = _packet(
        [
            {
                "ticker": "AAA",
                "shares": "10",
                "entry_price": price,
                "current_price": price,
            }
        ],
        cash=0,
    )
    policy = _permissive_policy(max_position_pct=0.50, max_order_value=100.0)

    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    exact_price = packet.portfolio.positions[0].exact_field("current_price")

    assert proposal.intent.shares == 2
    assert exact_price * proposal.intent.shares <= Decimal("100")


def test_max_order_cap_ignores_lowered_ambient_decimal_precision():
    with localcontext() as context:
        context.prec = 2
        packet = _packet(
            [
                {
                    "ticker": "AAA",
                    "shares": "10",
                    "entry_price": "33.34",
                    "current_price": "33.34",
                }
            ],
            cash=0,
        )
        policy = _permissive_policy(
            max_position_pct=0.50,
            max_order_value=100.0,
        )
        proposal = generate_risk_reduction_proposals(packet, policy)[0]

    assert proposal.intent.shares == 2
    exact_price = packet.portfolio.positions[0].exact_field("current_price")
    assert exact_price * proposal.intent.shares <= Decimal("100")


def test_sell_proposal_includes_advisory_lot_method_comparison():
    positions = [
        {
            "ticker": "AAA",
            "shares": 100,
            "entry_price": 100.0,
            "current_price": 100.0,
        }
    ]
    packet = _packet(positions, cash=0)
    policy = _permissive_policy(max_position_pct=0.50)
    now = datetime.now(timezone.utc)
    ledger = build_ledger(
        [
            Fill(
                "AAA",
                "buy",
                50,
                80,
                now - timedelta(days=500),
                fill_id="old-low",
            ),
            Fill(
                "AAA",
                "buy",
                50,
                120,
                now - timedelta(days=10),
                fill_id="new-high",
            ),
        ]
    )

    proposal = generate_risk_reduction_proposals(
        packet, policy, tax_lot_ledger=ledger
    )[0]
    advisory = proposal.expected_impact["tax_lot_advisory"]

    assert advisory["available"]
    assert advisory["advisory_only"]
    assert advisory["methods"]["fifo"]["long_term_pnl"] > 0
    assert advisory["methods"]["hifo"]["short_term_pnl"] < 0


def test_missing_tax_coverage_never_blocks_or_changes_risk_reduction():
    packet = _packet(
        [
            {
                "ticker": "AAA",
                "shares": 100,
                "entry_price": 100.0,
                "current_price": 100.0,
            }
        ],
        cash=0,
    )
    policy = _permissive_policy(max_position_pct=0.50)
    baseline = generate_risk_reduction_proposals(packet, policy)[0]
    with_missing_tax = generate_risk_reduction_proposals(
        packet,
        policy,
        tax_lot_ledger=None,
        tax_lot_coverage={
            "complete": False,
            "reason": "pre-app fills missing",
        },
    )[0]

    assert with_missing_tax.intent == baseline.intent
    advisory = with_missing_tax.expected_impact["tax_lot_advisory"]
    assert not advisory["available"]
    assert advisory["advisory_only"]
    assert "pre-app fills missing" in advisory["reason"]


def test_leveraged_etf_cap_breach_still_produces_a_proposal():
    positions = [{"ticker": "TQQQ", "shares": 100, "entry_price": 100.0, "current_price": 100.0}]
    packet = _packet(positions, cash=0.0)  # 100% leveraged
    policy = _permissive_policy(max_leveraged_etf_pct=0.20)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any("leveraged-etf exposure" in r.lower() for p in proposals for r in p.reasons)


def test_duplicate_ticker_rows_aggregate_exposure_still_produces_a_position_cap_proposal():
    # Independent review reproduction: two AAPL lots that each individually
    # sit under a 5% max_position_pct cap but jointly exceed it used to
    # produce no remediation at all, since generate_risk_reduction_
    # proposals() iterates snapshot.positions and position_by_ticker
    # silently collapsed duplicate keys. build_portfolio_snapshot() now
    # aggregates duplicate rows at ingestion, so this sees one $600 row.
    positions = [
        {"ticker": "AAPL", "shares": 1, "entry_price": 300.0, "current_price": 300.0},
        {"ticker": "AAPL", "shares": 1, "entry_price": 300.0, "current_price": 300.0},
    ]
    packet = _packet(positions, cash=9_400.0)  # AAPL = 600/10000 = 6%
    assert len(packet.portfolio.positions) == 1
    policy = _permissive_policy(max_position_pct=0.05)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any(p.intent.ticker == "AAPL" for p in proposals)
    assert any("position exceeds" in r.lower() for p in proposals for r in p.reasons)


def test_lowercase_ticker_basket_breach_still_produces_a_proposal():
    # Independent review reproduction: a manually-supplied lowercase
    # "aapl" used to be invisible to this generator's case-sensitive
    # basket membership check.
    positions = [{"ticker": "aapl", "shares": 50, "entry_price": 100.0, "current_price": 100.0}]
    packet = _packet(positions, cash=5_000.0)  # AAPL = 5000/10000 = 50%
    policy = _permissive_policy(max_basket_pct=0.40)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any(p.intent.ticker == "AAPL" for p in proposals)
    assert any("tech" in r.lower() for p in proposals for r in p.reasons)


if __name__ == "__main__":
    test_total_exposure_breach_with_no_individual_violations_produces_a_proposal()
    test_total_exposure_breach_does_not_fire_when_within_cap()
    test_total_exposure_remediation_accounts_for_already_planned_reductions()
    test_basket_breach_just_above_the_rounding_boundary_still_fires()
    test_basket_breach_genuinely_within_cap_does_not_fire()
    test_position_cap_breach_still_produces_a_proposal()
    test_leveraged_etf_cap_breach_still_produces_a_proposal()
    test_duplicate_ticker_rows_aggregate_exposure_still_produces_a_position_cap_proposal()
    test_lowercase_ticker_basket_breach_still_produces_a_proposal()
    print("All proposals tests passed.")


def test_a_sell_whose_lots_are_unknown_says_so_instead_of_going_silent():
    """The user-visible half of the uncovered-ticker fix (2026-07-30).

    proposals.py stamped available=True unconditionally, so for a ticker the
    lot ledger has never seen (there is still no importer for fills predating
    this app) the CLI looped every method, found them all errored, and printed
    NOTHING -- skipping the "advisory unavailable" branch entirely. Silence
    reads as "no tax implications", which is the opposite of the truth.
    """
    from datetime import datetime, timezone

    from assistant.tax_lots import Fill, build_ledger

    positions = [
        {"ticker": "AAA", "shares": 900, "entry_price": 100.0, "current_price": 100.0},
    ]
    packet = _packet(positions, cash=10_000.0)
    policy = _permissive_policy(max_total_exposure_pct=0.50)
    ledger = build_ledger([
        Fill(ticker="AAPL", qty=10, price=50.0,
             at=datetime(2025, 1, 1, tzinfo=timezone.utc), fill_id="f1", side="buy"),
    ])

    proposals = generate_risk_reduction_proposals(packet, policy, tax_lot_ledger=ledger)

    assert proposals, "missing lot coverage must never suppress a risk-reducing sell"
    advisory = proposals[0].expected_impact["tax_lot_advisory"]
    assert advisory["available"] is False
    assert advisory["advisory_only"] is True
    assert advisory["reason"]
    assert any("unavailable" in u for u in proposals[0].uncertainties)


def test_a_fractional_holding_yields_a_risk_reducing_sell_the_gate_accepts():
    """Counter-review SELCR-001 -- the gate hardening's other half.

    SELREV-001 correctly made risk/execution_gate.py compare EXACT broker
    share quantities, so a sell of 11 against a held 10.999999999999999999 is
    now refused. But this generator still floored the DISPLAY float, where
    that holding reads as 11.0, so it kept proposing 11 -- turning a correct
    refusal into a risk-reducing sell that can never be approved, leaving the
    position stuck over its cap with no in-app remedy. CLAUDE.md section 5 is
    explicit that a conservative safeguard must not obstruct a legitimate
    risk-reducing sell.

    Reproduced end to end rather than asserted on the arithmetic: generate
    the real proposal, then put it through the real gate.
    """
    from decimal import Decimal

    from assistant.schemas import PortfolioPosition, PortfolioSnapshot
    from risk.execution_gate import validate_trade_intent

    exact = "10.999999999999999999"
    assert int(float(exact)) == 11, "fixture must exercise the rounding-up case"

    def _pos(ticker, shares, price, shares_exact=None):
        return PortfolioPosition(
            ticker=ticker, shares=shares, entry_price=price, current_price=price,
            market_value=shares * price, unrealized_pnl_pct=0.0,
            is_leveraged_etf=False, shares_exact=shares_exact,
            current_price_exact=f"{price:.2f}",
        )

    # Two positions so total-exposure remediation demands the WHOLE fractional
    # position; with only one, the per-position cap sizes below the holding and
    # the float floor never becomes the binding constraint.
    snapshot = PortfolioSnapshot(
        positions=[
            _pos("NVDA", 10.999999999999999999, 100.0, shares_exact=exact),
            _pos("AAPL", 50.0, 100.0, shares_exact="50"),
        ],
        cash=100.0, total_equity=6200.0, as_of="2026-08-13",
    )
    packet = DecisionPacket(
        generated_at="2026-08-13T15:00:00+00:00", portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-12",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=0.05, max_total_exposure_pct=0.05, max_basket_pct=0.4,
        max_leveraged_etf_pct=0.2, min_cash_reserve_pct=0.0,
        max_order_value=50_000.0,
    )

    proposals = {p.intent.ticker: p for p in generate_risk_reduction_proposals(packet, policy)}
    assert "NVDA" in proposals, "the over-cap fractional position must still be remediated"
    nvda = proposals["NVDA"]
    assert nvda.intent.shares == 10, (
        f"proposed {nvda.intent.shares} shares against an exact holding of "
        f"{exact}; the held side must be floored exactly, not via the float"
    )

    now = datetime(2026, 8, 13, 14, 0, tzinfo=timezone.utc)
    result = validate_trade_intent(
        nvda.intent, snapshot, reference_price=100.0, price_timestamp=now,
        now=now, max_order_value=50_000.0,
    )
    codes = [str(getattr(v, "code", v)) for v in result.violations]
    assert not any("exceeds" in code.lower() or "SELL_EXCEEDS_HELD" in code for code in codes), (
        f"the gate must not refuse this risk-reducing sell as an oversell: {codes}"
    )
    assert Decimal(nvda.intent.shares) <= Decimal(exact)
