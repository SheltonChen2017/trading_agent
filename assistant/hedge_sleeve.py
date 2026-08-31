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
  options, no futures, no shorting -- see `docs/operations/MANDATE.md` 4, amended for
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

This module creates and sizes proposals; it never approves, submits, cancels,
or replaces an order. `generate_hedge_buy_proposals()` returns `proposed`
proposals that still require the typed approval phrase and still pass through
the execution gate independently at approval time.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import config
from assistant.allocation_proposals import build_allocation_plan
from assistant.money import (
    decimal_or_none,
    decimal_text,
    deterministic_decimal_divide,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import (
    estimate_pending_buy_value_by_ticker,
    preview_trade_impact,
)
from assistant.proposals import TradeProposal
from assistant.schemas import DecisionPacket, PortfolioSnapshot
from risk.execution_gate import TradeIntent, is_valid_order_quantity

EVIDENCE_STATUS = "user_directed_hedge"
_ONE_HUNDRED = Decimal("100")
_ONE_PERCENT = Decimal("0.01")

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
    pending_buy_value_exact: str
    current_pct: float
    projected_pct: float
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

    allowed = frozenset(name.upper() for name in config.HEDGE_SLEEVE_TICKERS)
    seen: set[str] = set()
    selected: list[str] = []
    refusals: list[str] = []
    for raw in candidates:
        if not isinstance(raw, str):
            refusals.append(
                f"Hedge instrument names must be text, got {raw!r}."
            )
            continue
        name = raw.strip().upper()
        if not name:
            refusals.append("An empty hedge instrument name was supplied.")
            continue
        if name not in allowed:
            refusals.append(
                f"{name} is not in the configured hedge sleeve "
                f"({', '.join(config.HEDGE_SLEEVE_TICKERS)})."
            )
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
    if exact is not None:
        # Presence means the broker-preserved value is authoritative. A
        # malformed exact field is corrupt input, not permission to fall back
        # to the rounded display float and hide that corruption.
        return decimal_or_none(exact)
    return decimal_or_none(getattr(position, "market_value", None))


def _percentage(value: Decimal, total: Decimal, *, name: str) -> Decimal:
    ratio = deterministic_decimal_divide(value, total, name=f"{name} ratio")
    return exact_decimal_multiply(ratio, _ONE_HUNDRED, name=name)


def _percentage_float(value: Decimal, total: Decimal, *, name: str) -> float:
    result = float(_percentage(value, total, name=name))
    if not math.isfinite(result):
        raise ValueError(f"{name} cannot be represented for display")
    return result


def _conservative_equal_weight(count: int) -> Decimal:
    """Deterministic equal weight that can never sum above 100 percent."""
    weight = deterministic_decimal_divide(
        _ONE_HUNDRED,
        Decimal(count),
        name="equal hedge weight",
    )
    combined = exact_decimal_multiply(
        weight,
        Decimal(count),
        name="combined equal hedge weights",
    )
    if combined > _ONE_HUNDRED:
        # Recurring decimal division can round up at its final digit. One ULP
        # off each equal leg lowers the combined allocation by `count` ULPs,
        # more than the at-most-half-ULP quotient rounding error times count.
        unit = Decimal((0, (1,), int(weight.as_tuple().exponent)))
        weight = exact_decimal_subtract(
            weight,
            unit,
            name="conservative equal hedge weight",
        )
    return weight


def evaluate_hedge_sleeve(
    snapshot: PortfolioSnapshot,
    *,
    target_pct: object,
    tickers: object = None,
    pending_buy_value_by_ticker: dict[str, object] | None = None,
    pending_value_unknown_tickers: set[str] | None = None,
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

    if not report_only and not snapshot.open_orders_available:
        refusals.append(
            "Open-order data is unavailable, so pending hedge exposure cannot "
            "be measured and a target-sized purchase would risk duplication."
        )

    if (
        pending_buy_value_by_ticker is None
        and pending_value_unknown_tickers is None
    ):
        estimated, unknown = estimate_pending_buy_value_by_ticker(
            snapshot.open_orders
        )
        pending_buy_value_by_ticker = estimated
        pending_value_unknown_tickers = unknown
    else:
        pending_buy_value_by_ticker = pending_buy_value_by_ticker or {}
        pending_value_unknown_tickers = pending_value_unknown_tickers or set()

    disclosures_pending: list[str] = []
    selected_set = set(selected)
    unknown_pending = {
        str(name).strip().upper()
        for name in pending_value_unknown_tickers
        if str(name).strip().upper() in selected_set
    }
    if unknown_pending:
        # HEDGE1CR-002: a refusal only when something is actually being
        # sized. The open-order-availability check above is already gated on
        # `report_only` for exactly this reason and this one was not, so the
        # page's DEFAULT state -- no target typed yet -- greeted the owner
        # with a red error claiming it was "refusing to size another
        # purchase" when nothing had been asked for. In report-only mode the
        # same fact is a disclosure: it explains why the projected weight
        # below is incomplete.
        names = ", ".join(sorted(unknown_pending))
        if report_only:
            disclosures_pending.append(
                f"A working buy order for {names} has no determinable value, "
                "so the projected sleeve below understates it. Set a target "
                "to size a purchase and this becomes a refusal."
            )
        else:
            refusals.append(
                f"Pending hedge-buy value is unavailable for {names}; "
                "refusing to size another purchase against an unknown "
                "working order."
            )

    pending_hedge_value = Decimal("0")
    pending_values_readable = True
    for raw_ticker, raw_value in pending_buy_value_by_ticker.items():
        name = str(raw_ticker).strip().upper()
        if name not in selected_set:
            continue
        value = decimal_or_none(raw_value)
        if value is None or value < 0:
            refusals.append(
                f"Pending hedge-buy value for {name} is not a usable "
                f"non-negative amount ({raw_value!r})."
            )
            continue
        try:
            pending_hedge_value = exact_decimal_add(
                pending_hedge_value,
                value,
                name="pending hedge-buy value",
            )
        except ValueError as exc:
            pending_values_readable = False
            refusals.append(
                f"Pending hedge-buy values cannot be combined exactly ({exc})."
            )

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
    values_readable = pending_values_readable
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
        shares_input = (
            position.shares_exact
            if position.shares_exact is not None
            else position.shares
        )
        shares = decimal_or_none(shares_input)
        # HEDGE1CR-003: a row reporting zero shares AND zero value is a
        # position that is not held, which is the `position is None` case
        # above -- `build_portfolio_snapshot` constructs exactly such a row
        # through its documented API. Refusing it bricked the whole page,
        # including the read-only view of the current weight, and called a
        # value "unreadable" that was read perfectly well and was zero. A
        # zero value against a POSITIVE quantity is still the impossible
        # state HEDGER-002 identified, and still refuses.
        if shares is not None and shares == 0 and value == 0:
            rows.append(
                HedgeSleeveRow(
                    ticker=name, held=False, shares_exact="0",
                    market_value_exact="0", pct_of_equity=0.0,
                    value_available=True, daily_reset=daily_reset,
                )
            )
            continue
        if value is None or value <= 0 or shares is None or shares <= 0:
            values_readable = False
            unreadable = value is None or shares is None
            refusals.append(
                f"{name} is held but its exact quantity or market value is "
                + (
                    "unreadable."
                    if unreadable
                    else f"impossible ({decimal_text(shares)} share(s) worth "
                         f"{decimal_text(value)})."
                )
                + " Refusing to size a hedge from an understated current "
                "weight."
            )
            rows.append(
                HedgeSleeveRow(
                    ticker=name, held=True, shares_exact="0",
                    market_value_exact="0", pct_of_equity=0.0,
                    value_available=False, daily_reset=daily_reset,
                )
            )
            continue
        try:
            hedge_value = exact_decimal_add(
                hedge_value,
                value,
                name="hedge sleeve value",
            )
            row_pct = (
                _percentage_float(value, equity, name=f"{name} hedge weight")
                if equity is not None
                else 0.0
            )
        except (OverflowError, ValueError) as exc:
            values_readable = False
            refusals.append(
                f"{name} hedge arithmetic is unavailable ({exc}); refusing "
                "to size from a rounded or partial value."
            )
            row_pct = 0.0
        rows.append(
            HedgeSleeveRow(
                ticker=name, held=True,
                shares_exact=decimal_text(shares) if shares is not None else "0",
                market_value_exact=decimal_text(value),
                pct_of_equity=row_pct,
                value_available=True, daily_reset=daily_reset,
            )
        )

    disclosures = [UNMEASURED_PROTECTION_DISCLOSURE]
    for row in rows:
        if row.daily_reset:
            disclosures.append(DAILY_RESET_DISCLOSURE.format(ticker=row.ticker))
    disclosures.extend(disclosures_pending)

    shortfall = Decimal("0")
    surplus = Decimal("0")
    current_pct = 0.0
    projected_pct = 0.0
    # The percentage is reportable without a target; the GAP is not. Both are
    # suppressed while any selected holding is unreadable, because a partial
    # hedge value displayed as the whole one is the reading that oversizes a
    # purchase.
    if equity is not None and values_readable:
        try:
            projected_value = exact_decimal_add(
                hedge_value,
                pending_hedge_value,
                name="projected hedge sleeve value",
            )
            current_pct = _percentage_float(
                hedge_value,
                equity,
                name="current hedge weight",
            )
            projected_pct = _percentage_float(
                projected_value,
                equity,
                name="projected hedge weight",
            )
            if target is not None:
                target_value = exact_decimal_multiply(
                    exact_decimal_multiply(
                        equity,
                        target,
                        name="hedge target scaled value",
                    ),
                    _ONE_PERCENT,
                    name="hedge target value",
                )
                difference = exact_decimal_subtract(
                    exact_decimal_subtract(
                        target_value,
                        hedge_value,
                        name="hedge target less holdings",
                    ),
                    pending_hedge_value,
                    name="hedge shortfall after pending buys",
                )
                if difference > 0:
                    shortfall = difference
                else:
                    surplus = exact_decimal_subtract(
                        Decimal("0"),
                        difference,
                        name="hedge surplus",
                    )
        except (OverflowError, ValueError) as exc:
            current_pct = 0.0
            projected_pct = 0.0
            shortfall = Decimal("0")
            surplus = Decimal("0")
            refusals.append(
                f"Hedge sleeve arithmetic is unavailable ({exc}); refusing "
                "to publish or size a rounded gap."
            )

    return HedgeSleeveReport(
        as_of=snapshot.as_of,
        tickers=tuple(selected),
        target_pct=float(target) if target is not None else 0.0,
        total_equity_exact=decimal_text(equity) if equity is not None else "0",
        hedge_value_exact=decimal_text(hedge_value),
        pending_buy_value_exact=decimal_text(pending_hedge_value),
        current_pct=current_pct,
        projected_pct=projected_pct,
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
    prices: dict[str, object],
    *,
    target_pct: object,
    tickers: object = None,
    ttl_minutes: int = 15,
    pending_buy_value_by_ticker: dict[str, object] | None = None,
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
        packet.portfolio,
        target_pct=target_pct,
        tickers=tickers,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        pending_value_unknown_tickers=pending_value_unknown_tickers,
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
        pending = Decimal(report.pending_buy_value_exact)
        if pending > 0:
            position = (
                f"Current holdings are {report.current_pct:.2f}% of equity; "
                f"${pending:,.2f} of pending hedge buys bring the projected "
                f"sleeve to {report.projected_pct:.2f}% against the "
                f"{report.target_pct:.2f}% target"
            )
        else:
            position = (
                f"The hedge sleeve is already at {report.current_pct:.2f}% of "
                f"equity against a {report.target_pct:.2f}% target"
            )
        return {
            "created": False,
            "report": report,
            "reason": (
                f"{position} "
                f"(${float(surplus):,.2f} above it). Nothing to buy. This app "
                "does not sell to rebalance a hedge down."
            ),
        }

    # Guarded Decimal conversion rather than `> 0` on the raw value: a float
    # NaN passes truthiness and every ordered comparison, then poisons the
    # sizing downstream. This also rejects infinity, bool, and bad text.
    usable_prices: dict[str, Decimal] = {}
    missing_prices: list[str] = []
    for ticker in report.tickers:
        price = decimal_or_none(prices.get(ticker))
        if price is None or price <= 0:
            missing_prices.append(ticker)
        else:
            usable_prices[ticker] = price
    if missing_prices:
        return {
            "created": False,
            "report": report,
            "reason": (
                "Every selected hedge instrument needs a usable current "
                "price before the chosen basket can be sized. Missing: "
                f"{', '.join(missing_prices)}. Deselect "
                f"{'them' if len(missing_prices) > 1 else 'it'} to hedge with "
                "the rest, or try again once a fresh close is recorded."
            ),
        }

    # Equal weight, computed once and stated. The remainder from an
    # indivisible split is left unallocated rather than being pushed onto an
    # arbitrary instrument, which would silently overweight it.
    weight = _conservative_equal_weight(len(usable_prices))
    weights_pct = {ticker: weight for ticker in usable_prices}
    shortfall = Decimal(report.shortfall_dollars_exact)

    plan = build_allocation_plan(
        packet, policy, weights_pct, usable_prices, shortfall,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        pending_value_unknown_tickers=pending_value_unknown_tickers,
    )

    at = now or datetime.now(timezone.utc)
    invalid_entries = [
        entry for entry in plan
        if entry.skipped or not is_valid_order_quantity(
            entry.shares, whole_shares_only=policy.whole_shares_only
        )
    ]
    if invalid_entries:
        details = "; ".join(
            f"{entry.ticker}: {entry.skip_reason or 'invalid order quantity'}"
            for entry in invalid_entries
        )
        return {
            "created": False,
            "report": report,
            "reason": (
                "The selected hedge basket cannot be created completely at "
                f"the active minimum order quantity. {details.rstrip(chr(46))}. Raise "
                "the "
                "target, deselect that instrument, or enable fractional "
                "shares in Settings & Features."
            ),
        }

    proposals: list[TradeProposal] = []
    for entry in plan:
        intent = TradeIntent(
            ticker=entry.ticker,
            side="buy",
            shares=entry.shares,
            order_type="market",
            rationale=(
                f"Defensive hedge sleeve: {entry.weight_pct:.1f}% of the "
                f"${shortfall:,.2f} remaining shortfall to a "
                f"{report.target_pct:.2f}% "
                f"target -> {entry.shares} share(s) at "
                f"~${entry.reference_price:,.2f}."
            ),
        )
        proposal_id = _stable_id(
            packet, policy, intent,
            salt=(
                f"{report.shortfall_dollars_exact}|"
                f"{report.pending_buy_value_exact}"
            ),
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
                    f"with ${Decimal(report.pending_buy_value_exact):,.2f} of "
                    f"selected pending buys, leaving a ${shortfall:,.2f} "
                    f"shortfall to your {report.target_pct:.2f}% target.",
                    f"{entry.ticker} takes {entry.weight_pct:.1f}% of that "
                    f"shortfall under an equal-weight split across "
                    f"{len(usable_prices)} selected instrument(s).",
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
                f"{len(usable_prices)} instrument(s) cannot buy the minimum "
                "order quantity your policy allows for any of them."
            ),
        }
    return {"created": True, "report": report, "proposals": proposals}
