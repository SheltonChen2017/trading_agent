"""Defensive hedge-sleeve sizing (HEDGE-1, owner request 2026-08-14).

Answers one deterministic question: **how many dollars short of a stated
defensive target is this portfolio right now?** Everything after that answer
is existing machinery -- `assistant.allocation_proposals.build_allocation_plan`
sizes the shares, the same `TradeProposal` -> typed `APPROVE` ->
`risk/execution_gate.py` pipeline authorizes them, and nothing here submits
anything.

Scope, stated plainly because the word "hedge" invites bigger claims than
this milestone supports:

* the instruments are long-only ETFs the broker already supports. No
  options, no futures, no shorting -- see `docs/MANDATE.md` 4, amended for
  this milestone;
* **this project has NOT confirmed that this basket reduces drawdown.** The
  defensive-carry probe behind `config.DEFENSIVE_CARRY_TICKERS` is a
  single-window exploratory result, and a hedge that is bought is a hedge
  that is paid for. Every report carries that disclosure rather than leaving
  a reader to assume protection was measured; and
* sizing is EQUAL WEIGHT across the instruments the owner selected, not
  inverse-volatility weighting. That is a deliberate departure from
  `allocation_proposals`: inverse-volatility weighting maximizes weight where
  trailing volatility is lowest, which in a defensive basket means it would
  starve the instrument that actually moves against equities and pile into
  the one that barely moves at all. Equal weight is explainable and does not
  quietly invert the owner's intent.

Failure direction, which is the part that matters. An unknown hedge holding
makes the CURRENT hedge weight look smaller than it is, and a shortfall
computed from an understated current weight proposes buying too much. So an
unusable value on any selected instrument refuses the whole computation
instead of skipping that row. Under-hedging is a smaller error than an
unbounded purchase made on numbers the app could not read.

Nothing here creates, approves, sizes, submits, cancels, or replaces an
order. `generate_hedge_buy_proposals()` returns `proposed` proposals that
still require the typed approval phrase and still pass through the execution
gate independently at approval time.
"""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import config
from assistant.allocation_proposals import build_allocation_plan
from assistant.money import decimal_or_none, decimal_text
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.proposals import TradeProposal
from assistant.schemas import DecisionPacket, PortfolioSnapshot
from risk.execution_gate import TradeIntent, is_valid_order_quantity

EVIDENCE_STATUS = "user_directed_hedge"

#: The standing honesty disclosure. It is attached to every report and every
#: proposal, in both directions: the app has not measured protection, and the
#: hedge costs money whether or not a decline arrives.
UNMEASURED_PROTECTION_DISCLOSURE = (
    "This project has NOT confirmed that this basket reduces drawdown. The "
    "defensive-carry result behind these names is a single-window "
    "exploratory number, not validated evidence, and a hedge that is held "
    "costs money whether or not a decline arrives."
)

DAILY_RESET_DISCLOSURE = (
    "{ticker} targets its stated return over a SINGLE day. Held longer, its "
    "return compounds path-dependently and can lose money even when the "
    "index moves in the direction you were positioned for."
)


@dataclasses.dataclass(frozen=True)
class HedgeSleeveRow:
    """What one selected hedge instrument currently contributes."""

    ticker: str
    held: bool
    shares_exact: str
    market_value_exact: str
    pct_of_equity: float
    value_available: bool
    daily_reset: bool


@dataclasses.dataclass(frozen=True)
class HedgeSleeveReport:
    """Current defensive weight against a stated target, and the gap."""

    as_of: str
    tickers: tuple[str, ...]
    target_pct: float
    total_equity_exact: str
    hedge_value_exact: str
    current_pct: float
    shortfall_dollars_exact: str
    surplus_dollars_exact: str
    rows: tuple[HedgeSleeveRow, ...]
    disclosures: tuple[str, ...]
    refusals: tuple[str, ...]

    @property
    def usable(self) -> bool:
        """True when the gap was computed from values the app could read."""
        return not self.refusals

    @property
    def has_shortfall(self) -> bool:
        shortfall = decimal_or_none(self.shortfall_dollars_exact)
        return self.usable and shortfall is not None and shortfall > 0


def _selected_tickers(tickers: object) -> tuple[list[str], list[str]]:
    """Normalized, de-duplicated, order-preserving selection plus refusals."""
    if tickers is None:
        candidates = list(config.HEDGE_SLEEVE_TICKERS)
    elif isinstance(tickers, (str, bytes)):
        # A bare string would iterate character by character and silently
        # produce single-letter "tickers"; refuse rather than guess.
        return [], ["Hedge instruments must be a list of tickers, not text."]
    else:
        try:
            candidates = list(tickers)
        except TypeError:
            return [], ["Hedge instruments must be a list of tickers."]

    seen: set[str] = set()
    selected: list[str] = []
    refusals: list[str] = []
    for raw in candidates:
        name = str(raw).strip().upper()
        if not name:
            refusals.append("An empty hedge instrument name was supplied.")
            continue
        if name in seen:
            continue
        seen.add(name)
        selected.append(name)
    if not selected and not refusals:
        refusals.append("No hedge instrument was selected.")
    return selected, refusals


def _position_value(position: object) -> Decimal | None:
    """Exact market value of a position, preferring the exact text field."""
    exact = getattr(position, "market_value_exact", None)
    value = decimal_or_none(exact) if exact is not None else None
    if value is None:
        value = decimal_or_none(getattr(position, "market_value", None))
    return value


def evaluate_hedge_sleeve(
    snapshot: PortfolioSnapshot,
    *,
    target_pct: object,
    tickers: object = None,
) -> HedgeSleeveReport:
    """Current defensive weight, the stated target, and the exact gap.

    Pure: reads the snapshot and returns a frozen report. Refuses rather than
    substituting a default whenever equity, a target, or any selected
    instrument's value is missing or unreadable -- see the module docstring
    for why an unreadable holding must refuse instead of being skipped.
    """
    selected, refusals = _selected_tickers(tickers)
    refusals = list(refusals)

    # ``target_pct=None`` is REPORT-ONLY, not an error: the page's own default
    # state has no target yet, and greeting the owner with a red refusal for
    # not having typed one trains them to ignore this page's errors. A target
    # that was actually supplied and is unusable still refuses.
    report_only = target_pct is None
    target = None if report_only else decimal_or_none(target_pct)
    if not report_only and (target is None or target <= 0 or target > 100):
        refusals.append(
            f"The hedge target must be a percentage above 0 and at most 100, "
            f"got {target_pct!r}."
        )
        target = None

    equity_input = (
        snapshot.total_equity_exact
        if snapshot.total_equity_exact is not None
        else snapshot.total_equity
    )
    equity = decimal_or_none(equity_input)
    if equity is None or equity <= 0:
        refusals.append(
            f"Total equity is not a usable positive amount ({equity_input!r}), "
            "so a hedge weight cannot be computed."
        )
        equity = None

    by_ticker = {p.ticker.upper(): p for p in snapshot.positions}
    rows: list[HedgeSleeveRow] = []
    hedge_value = Decimal("0")
    values_readable = True
    for name in selected:
        position = by_ticker.get(name)
        daily_reset = name in config.DAILY_RESET_HEDGE_ETFS
        if position is None:
            rows.append(
                HedgeSleeveRow(
                    ticker=name, held=False, shares_exact="0",
                    market_value_exact="0", pct_of_equity=0.0,
                    value_available=True, daily_reset=daily_reset,
                )
            )
            continue
        value = _position_value(position)
        if value is None or value < 0:
            values_readable = False
            refusals.append(
                f"{name} is held but its market value is unreadable "
                f"({getattr(position, 'market_value', None)!r}). Refusing to "
                "size a hedge from an understated current weight."
            )
            rows.append(
                HedgeSleeveRow(
                    ticker=name, held=True, shares_exact="0",
                    market_value_exact="0", pct_of_equity=0.0,
                    value_available=False, daily_reset=daily_reset,
                )
            )
            continue
        hedge_value += value
        shares_input = (
            position.shares_exact
            if position.shares_exact is not None
            else position.shares
        )
        shares = decimal_or_none(shares_input)
        rows.append(
            HedgeSleeveRow(
                ticker=name, held=True,
                shares_exact=decimal_text(shares) if shares is not None else "0",
                market_value_exact=decimal_text(value),
                pct_of_equity=(
                    float(value / equity * 100) if equity is not None else 0.0
                ),
                value_available=True, daily_reset=daily_reset,
            )
        )

    disclosures = [UNMEASURED_PROTECTION_DISCLOSURE]
    for row in rows:
        if row.daily_reset:
            disclosures.append(DAILY_RESET_DISCLOSURE.format(ticker=row.ticker))

    shortfall = Decimal("0")
    surplus = Decimal("0")
    current_pct = 0.0
    # The percentage is reportable without a target; the GAP is not. Both are
    # suppressed while any selected holding is unreadable, because a partial
    # hedge value displayed as the whole one is the reading that oversizes a
    # purchase.
    if equity is not None and values_readable:
        current_pct = float(hedge_value / equity * 100)
        if target is not None:
            difference = equity * target / Decimal("100") - hedge_value
            if difference > 0:
                shortfall = difference
            else:
                surplus = -difference

    return HedgeSleeveReport(
        as_of=snapshot.as_of,
        tickers=tuple(selected),
        target_pct=float(target) if target is not None else 0.0,
        total_equity_exact=decimal_text(equity) if equity is not None else "0",
        hedge_value_exact=decimal_text(hedge_value),
        current_pct=current_pct,
        shortfall_dollars_exact=decimal_text(shortfall),
        surplus_dollars_exact=decimal_text(surplus),
        rows=tuple(rows),
        disclosures=tuple(disclosures),
        refusals=tuple(refusals),
    )


def _stable_id(
    packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, salt: str
) -> str:
    # Built from packet.generated_at (a full timestamp) rather than
    # portfolio.as_of (a date) for the same reason as every other generator
    # here: save_proposal()'s ON CONFLICT DO NOTHING would otherwise make a
    # same-day regeneration a silent no-op against a stale or expired row.
    raw = (
        f"{EVIDENCE_STATUS}|{packet.generated_at}|{policy.version}|"
        f"{intent.ticker.upper()}|{intent.side}|{intent.shares}|{salt}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_hedge_buy_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    prices: dict[str, float],
    *,
    target_pct: object,
    tickers: object = None,
    ttl_minutes: int = 15,
    pending_buy_value_by_ticker: dict[str, float] | None = None,
    pending_value_unknown_tickers: set[str] | None = None,
    now: datetime | None = None,
) -> dict:
    """APPROVE-gated buy proposals that close the hedge shortfall.

    Returns ``{"created": True, "report": ..., "proposals": [...]}`` or
    ``{"created": False, "report": ..., "reason": str}``. Never raises for
    ordinary bad input and never partially creates anything.

    Share sizing is delegated to ``build_allocation_plan`` -- the same
    function the preview uses -- so what is shown and what is proposed cannot
    drift apart. Only the SHORTFALL and the equal-weight split are computed
    here.
    """
    report = evaluate_hedge_sleeve(
        packet.portfolio, target_pct=target_pct, tickers=tickers
    )
    if not report.usable:
        return {
            "created": False,
            "report": report,
            "reason": " ".join(report.refusals),
        }
    if target_pct is None:
        # Report-only is a legitimate report but never an order: refuse
        # explicitly rather than falling through to the at-target wording,
        # which would claim a comparison that was never made.
        return {
            "created": False,
            "report": report,
            "reason": (
                "No hedge target was supplied, so there is nothing to size "
                "against. Set a target above 0%."
            ),
        }
    if not report.has_shortfall:
        surplus = report.surplus_dollars_exact
        return {
            "created": False,
            "report": report,
            "reason": (
                f"The hedge sleeve is already at {report.current_pct:.2f}% of "
                f"equity against a {report.target_pct:.2f}% target "
                f"(${float(surplus):,.2f} above it). Nothing to buy. This app "
                "does not sell to rebalance a hedge down."
            ),
        }

    # Guarded Decimal conversion rather than `> 0` on the raw value: a float
    # NaN passes truthiness and every ordered comparison, then poisons the
    # sizing downstream. This also rejects infinity, bool, and bad text.
    priced = [
        ticker for ticker in report.tickers
        if (price := decimal_or_none(prices.get(ticker))) is not None
        and price > 0
    ]
    if not priced:
        return {
            "created": False,
            "report": report,
            "reason": (
                "None of the selected hedge instruments has a usable current "
                "price, so no purchase can be sized."
            ),
        }

    # Equal weight, computed once and stated. The remainder from an
    # indivisible split is left unallocated rather than being pushed onto an
    # arbitrary instrument, which would silently overweight it.
    weight = 100.0 / len(priced)
    weights_pct = {ticker: weight for ticker in priced}
    shortfall = float(Decimal(report.shortfall_dollars_exact))

    plan = build_allocation_plan(
        packet, policy, weights_pct, prices, shortfall,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        pending_value_unknown_tickers=pending_value_unknown_tickers,
    )

    at = now or datetime.now(timezone.utc)
    proposals: list[TradeProposal] = []
    for entry in plan:
        if entry.skipped or not is_valid_order_quantity(
            entry.shares, whole_shares_only=policy.whole_shares_only
        ):
            continue
        intent = TradeIntent(
            ticker=entry.ticker,
            side="buy",
            shares=entry.shares,
            order_type="market",
            rationale=(
                f"Defensive hedge sleeve: {entry.weight_pct:.1f}% of the "
                f"${shortfall:,.2f} shortfall to a {report.target_pct:.2f}% "
                f"target -> {entry.shares} share(s) at "
                f"~${entry.reference_price:,.2f}."
            ),
        )
        proposal_id = _stable_id(
            packet, policy, intent, salt=report.shortfall_dollars_exact
        )
        uncertainties = [
            UNMEASURED_PROTECTION_DISCLOSURE,
            "Equal weighting sizes the split; it makes no claim that these "
            "instruments hedge equally well, or at all.",
            "Share quantity is rounded down to the granularity your policy "
            "allows, so the hedge will land slightly under target rather "
            "than over it.",
            "Requires allow_new_positions=true in your policy -- off by "
            "default, so this is blocked at approval time unless you have "
            "explicitly enabled it.",
            "Market orders can fill away from the displayed reference price.",
            "Policy limits are re-checked independently at approval time; "
            "this proposal is not a promise that the order will pass.",
        ]
        if entry.ticker in config.DAILY_RESET_HEDGE_ETFS:
            uncertainties.insert(
                1, DAILY_RESET_DISCLOSURE.format(ticker=entry.ticker)
            )
        proposals.append(
            TradeProposal(
                proposal_id=proposal_id,
                created_at=at.isoformat(),
                expires_at=(at + timedelta(minutes=ttl_minutes)).isoformat(),
                status="proposed",
                idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
                policy_version=policy.version,
                policy_fingerprint=compute_policy_fingerprint(policy),
                intent=intent,
                reference_price=entry.reference_price,
                price_timestamp=at.isoformat(),
                reasons=[
                    f"Your hedge sleeve is {report.current_pct:.2f}% of equity "
                    f"against your {report.target_pct:.2f}% target, a "
                    f"${shortfall:,.2f} shortfall.",
                    f"{entry.ticker} takes {entry.weight_pct:.1f}% of that "
                    f"shortfall under an equal-weight split across "
                    f"{len(priced)} selected instrument(s).",
                    "This is your own instruction, not a project "
                    "recommendation: no confirmed evidence says this "
                    "position protects the portfolio.",
                ],
                evidence_status=EVIDENCE_STATUS,
                expected_impact=preview_trade_impact(
                    packet.portfolio, entry.ticker, "buy",
                    entry.shares, entry.reference_price,
                ),
                alternatives=[
                    "Take no action -- nothing is bought until you type the "
                    "approval phrase for each proposal.",
                    "Lower the hedge target, or select fewer instruments, and "
                    "check again before approving.",
                    "Hold more cash instead. Cash is the one defensive "
                    "position with no tracking error and no expense ratio.",
                ],
                uncertainties=uncertainties,
            )
        )

    if not proposals:
        return {
            "created": False,
            "report": report,
            "reason": (
                f"The ${shortfall:,.2f} shortfall split across "
                f"{len(priced)} instrument(s) cannot buy the minimum order "
                "quantity your policy allows for any of them."
            ),
        }
    return {"created": True, "report": report, "proposals": proposals}
