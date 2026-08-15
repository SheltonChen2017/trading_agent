"""Wide-band portfolio drift measurement (REBAL-1 core).

This module answers one deterministic question: **which holdings have drifted
outside their band, and what is the smallest trade that puts each back inside
it?** It computes; it proposes nothing.

Why a band, and why "back to the edge":

`assistant/research_findings.json` carries exactly one entry with status
`confirmed` -- "Wide rebalance band vs. tight/continuous vol-targeting:
~89% less tax/turnover for essentially the same performance". `docs/MANDATE.md`
codifies the consequence as policy: rebalancing is event-driven, not
calendar-driven. The saving comes specifically from **not** trading back to
target. Correcting to the centre of the band re-realizes gains on every small
oscillation, which is the behaviour the finding beat. So a breach is corrected
to the nearest band EDGE, and a holding inside its band produces no trade at
all.

What that finding does NOT license, stated here because the number is
quotable and the temptation is real: 89% was measured in a specific
vol-targeting comparison. It is evidence that the MECHANISM is cheaper, not a
prediction about this portfolio, and nothing in this module may claim
otherwise.

Scope of this module, deliberately narrow while the milestone plan is being
written independently:

* it measures drift and band breaches in both directions, because that
  computation is the same whichever way the plan later resolves; and
* it produces no `TradeProposal`, touches no policy field, and has no UI.
  Rebalancing SELLS -- unlike every other sell path in this app, which is
  either a computed policy breach or the owner's explicit instruction, this
  one would sell winners on the app's initiative. That is a materially larger
  safety surface than HEDGE-1's buy-only sleeve and belongs to a reviewed
  plan, not to a convenient default chosen here.

Failure direction. A rebalance trade is sized from a weight, and a weight is
a ratio of two numbers that can each be missing. An unreadable holding makes
every OTHER weight look larger than it is, because the denominator is wrong
in one direction and the numerator in another -- so a single unreadable
position can manufacture a phantom breach anywhere in the portfolio. This
module therefore refuses the whole computation rather than dropping a row,
the same rule and for the same reason as `assistant/hedge_sleeve.py`.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal

from assistant.money import decimal_or_none, decimal_text
from assistant.schemas import PortfolioSnapshot

#: The band is expressed as a RELATIVE fraction of the target weight, not as
#: absolute percentage points. A 5-point band means something very different
#: on a 40% target than on a 2% one; a relative band keeps "wide" meaning the
#: same thing across a portfolio whose targets differ by an order of
#: magnitude. No default is offered on purpose -- band width is the single
#: number that decides how often this trades, and a hidden default would be a
#: financial default chosen by this module rather than by the owner.
MINIMUM_BAND_FRACTION = Decimal("0.01")
MAXIMUM_BAND_FRACTION = Decimal("1")

INSIDE = "inside"
ABOVE = "above"
BELOW = "below"


@dataclasses.dataclass(frozen=True)
class DriftRow:
    """One target holding: where it is, where its band ends, what it needs."""

    ticker: str
    target_pct: float
    current_pct: float
    market_value_exact: str
    lower_edge_pct: float
    upper_edge_pct: float
    state: str
    #: Signed exact dollars to reach the nearest EDGE. Positive means buy,
    #: negative means sell, "0" means the holding is inside its band.
    correction_dollars_exact: str
    held: bool


@dataclasses.dataclass(frozen=True)
class DriftReport:
    """Every target holding measured against its band."""

    as_of: str
    total_equity_exact: str
    band_fraction: float
    rows: tuple[DriftRow, ...]
    breached: tuple[str, ...]
    refusals: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not self.refusals

    @property
    def has_breach(self) -> bool:
        return self.usable and bool(self.breached)


def _normalized_targets(targets: object) -> tuple[dict[str, Decimal], list[str]]:
    """Exact target weights keyed by canonical ticker, plus refusals."""
    refusals: list[str] = []
    if not isinstance(targets, dict):
        return {}, ["Target weights must be supplied as a mapping."]
    if not targets:
        return {}, ["No target weights were supplied."]

    normalized: dict[str, Decimal] = {}
    for raw_ticker, raw_weight in targets.items():
        if not isinstance(raw_ticker, str):
            refusals.append(f"Target ticker names must be text, got {raw_ticker!r}.")
            continue
        name = raw_ticker.strip().upper()
        if not name:
            refusals.append("An empty target ticker name was supplied.")
            continue
        if name in normalized:
            # Silently keeping one of two weights for the same name would make
            # the portfolio's stated targets depend on dict ordering.
            refusals.append(f"{name} was given more than one target weight.")
            continue
        weight = decimal_or_none(raw_weight)
        if weight is None or weight < 0 or weight > 100:
            refusals.append(
                f"{name}'s target weight must be between 0 and 100, "
                f"got {raw_weight!r}."
            )
            continue
        normalized[name] = weight

    total = sum(normalized.values(), Decimal("0"))
    if normalized and total > 100:
        # Over 100% is unreachable without leverage this app does not use, so
        # every band derived from it would be fiction. Under 100% is a
        # deliberate cash allocation and is allowed.
        refusals.append(
            f"Target weights total {decimal_text(total)}%, which exceeds 100%."
        )
    return normalized, refusals


def _band_fraction(band: object) -> tuple[Decimal | None, list[str]]:
    value = decimal_or_none(band)
    if value is None or value < MINIMUM_BAND_FRACTION or value > MAXIMUM_BAND_FRACTION:
        return None, [
            "The band must be a relative fraction of the target weight "
            f"between {decimal_text(MINIMUM_BAND_FRACTION)} and "
            f"{decimal_text(MAXIMUM_BAND_FRACTION)}, got {band!r}."
        ]
    return value, []


def _position_value(position: object) -> Decimal | None:
    """Exact market value, preferring the broker-preserved exact text.

    Presence of the exact field means it is authoritative; a malformed exact
    value is corrupt input, not permission to fall back to the rounded
    display float and hide the corruption (the rule HEDGER-002 established).
    """
    exact = getattr(position, "market_value_exact", None)
    if exact is not None:
        return decimal_or_none(exact)
    return decimal_or_none(getattr(position, "market_value", None))


def evaluate_drift(
    snapshot: PortfolioSnapshot,
    *,
    targets: object,
    band_fraction: object,
) -> DriftReport:
    """Measure every target holding against its band.

    Pure: reads the snapshot and returns a frozen report. Refuses rather than
    substituting a default whenever equity, a target, a band, or any target
    holding's value is missing or unreadable -- see the module docstring for
    why one unreadable row invalidates every other row's weight.
    """
    normalized, refusals = _normalized_targets(targets)
    refusals = list(refusals)

    band, band_refusals = _band_fraction(band_fraction)
    refusals.extend(band_refusals)

    equity_input = (
        snapshot.total_equity_exact
        if snapshot.total_equity_exact is not None
        else snapshot.total_equity
    )
    equity = decimal_or_none(equity_input)
    if equity is None or equity <= 0:
        refusals.append(
            f"Total equity is not a usable positive amount ({equity_input!r}), "
            "so no weight can be computed."
        )
        equity = None

    by_ticker = {p.ticker.upper(): p for p in snapshot.positions}
    values: dict[str, Decimal] = {}
    values_readable = True
    for name in normalized:
        position = by_ticker.get(name)
        if position is None:
            values[name] = Decimal("0")
            continue
        value = _position_value(position)
        shares_input = (
            position.shares_exact
            if position.shares_exact is not None
            else position.shares
        )
        shares = decimal_or_none(shares_input)
        if shares is not None and shares == 0 and value == 0:
            # A zero-quantity, zero-value row is a position that is not held,
            # which is the missing-position case above (HEDGE1CR-003).
            values[name] = Decimal("0")
            continue
        if value is None or value <= 0 or shares is None or shares <= 0:
            values_readable = False
            refusals.append(
                f"{name} is held but its exact quantity or market value is "
                + (
                    "unreadable"
                    if value is None or shares is None
                    else f"impossible ({decimal_text(shares)} share(s) worth "
                         f"{decimal_text(value)})"
                )
                + ". Refusing to measure drift, because one unreadable "
                "holding distorts every other holding's weight."
            )
            values[name] = Decimal("0")
            continue
        values[name] = value

    rows: list[DriftRow] = []
    breached: list[str] = []
    computable = equity is not None and band is not None and values_readable
    for name, target in sorted(normalized.items()):
        value = values.get(name, Decimal("0"))
        if not computable:
            rows.append(
                DriftRow(
                    ticker=name, target_pct=float(target), current_pct=0.0,
                    market_value_exact=decimal_text(value),
                    lower_edge_pct=0.0, upper_edge_pct=0.0, state=INSIDE,
                    correction_dollars_exact="0",
                    held=name in by_ticker,
                )
            )
            continue

        current = value / equity * Decimal("100")
        half_width = target * band
        lower = target - half_width
        upper = target + half_width
        if current < lower:
            state = BELOW
            edge_value = equity * lower / Decimal("100")
            correction = edge_value - value
        elif current > upper:
            state = ABOVE
            edge_value = equity * upper / Decimal("100")
            correction = edge_value - value
        else:
            state = INSIDE
            correction = Decimal("0")
        if state != INSIDE:
            breached.append(name)
        rows.append(
            DriftRow(
                ticker=name, target_pct=float(target),
                current_pct=float(current),
                market_value_exact=decimal_text(value),
                lower_edge_pct=float(lower), upper_edge_pct=float(upper),
                state=state,
                correction_dollars_exact=decimal_text(correction),
                held=name in by_ticker,
            )
        )

    notes = [
        "A breach is corrected to the nearest band EDGE, never to the target. "
        "Correcting to target is what the wide-band finding measured against, "
        "and is where its turnover saving comes from.",
        "The ~89% turnover reduction behind this design was measured in a "
        "specific vol-targeting comparison. It is evidence that the mechanism "
        "is cheaper, not a prediction about this portfolio.",
    ]
    untargeted = sorted(
        name for name in by_ticker if name not in normalized
    )
    if untargeted:
        # Named rather than silently ignored: these holdings dilute every
        # target's weight through the shared denominator, so a reader who
        # assumes the targets describe the whole portfolio is misreading it.
        notes.append(
            "Held without a target weight, and therefore counted only in the "
            "equity denominator: " + ", ".join(untargeted) + "."
        )

    return DriftReport(
        as_of=snapshot.as_of,
        total_equity_exact=decimal_text(equity) if equity is not None else "0",
        band_fraction=float(band) if band is not None else 0.0,
        rows=tuple(rows),
        breached=tuple(breached),
        refusals=tuple(refusals),
        notes=tuple(notes),
    )
