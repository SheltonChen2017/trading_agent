"""Read-only sleeve drift against the allocation profile (REBAL-1 Stage 1).

Reports what the portfolio IS relative to the owner's stated sleeve targets.
It is a report, not a proposal source: no field is action-shaped. There are
no share counts, no buy/sell sides, no ranking of what to trade first, and
no proposal, because converting a dollar gap into an order is later-stage
work under separate review.

The dollar figure each row carries is the gap to TARGET, which answers "how
far from the stated shape is this sleeve". It is deliberately not a
correction-to-band-edge amount: that is a sizing decision, and sizing belongs
to the stage that also carries tax consequences and typed approval.

Failure direction, which differs from a per-instrument sleeve check. A weight
is a ratio, and every sleeve shares one denominator. A single unreadable
holding therefore corrupts EVERY sleeve's percentage, not just its own, and
can manufacture a phantom breach on a sleeve whose own holdings all read
fine. Dropping the bad row is the dangerous choice here, not the cautious
one, so an unusable authoritative value refuses the whole computation.

Unassigned holdings are always surfaced. Absence from the allocation profile
is a gap in the profile, never a signal about the holding, and this module
must never let "not in a sleeve" read as "should not be held".
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal

from assistant.money import decimal_or_none, decimal_text
from assistant.rebalance_profile import (
    SLEEVE_CASH,
    SLEEVE_ORDER,
    SLEEVE_OTHER,
    AllocationProfile,
    AllocationProfileError,
    compute_profile_fingerprint,
    sleeve_membership,
    validate_profile,
)
from assistant.schemas import PortfolioSnapshot

STATUS_INSIDE = "inside_band"
STATUS_UNDERWEIGHT = "underweight"
STATUS_OVERWEIGHT = "overweight"
STATUS_UNASSIGNED = "unassigned_holdings"
STATUS_PENDING_UNKNOWN = "pending_value_unknown"
STATUS_DATA_UNAVAILABLE = "data_unavailable"
STATUS_POLICY_CONFLICT = "policy_conflict"

ROW_STATUSES = (
    STATUS_INSIDE,
    STATUS_UNDERWEIGHT,
    STATUS_OVERWEIGHT,
    STATUS_UNASSIGNED,
    STATUS_PENDING_UNKNOWN,
    STATUS_DATA_UNAVAILABLE,
    STATUS_POLICY_CONFLICT,
)

BAND_MECHANISM_DISCLOSURE = (
    "Targets and band width are your stated preference, not a research "
    "result. This project's wide-band finding was measured on the SOXX/SOXL "
    "vol-targeting pair and says nothing about whether this portfolio's "
    "shape is right."
)

UNASSIGNED_DISCLOSURE = (
    "Holdings outside every sleeve are shown, never hidden. Being absent "
    "from the allocation profile says nothing about whether a holding "
    "should be kept, and is not a reason to sell it."
)


@dataclasses.dataclass(frozen=True)
class SleeveRow:
    """One sleeve measured against its band."""

    sleeve: str
    target_pct: float
    lower_edge_pct: float
    upper_edge_pct: float
    current_pct: float
    projected_pct: float
    market_value_exact: str
    pending_value_exact: str
    #: Signed exact dollars between the PROJECTED value and the target value.
    #: Positive means the sleeve is below target. This is a measurement of
    #: distance, not an instruction: no side, no quantity, no ordering.
    gap_to_target_exact: str
    status: str
    tickers: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class RebalanceReport:
    """The whole portfolio measured against one profile version."""

    as_of: str
    profile_version: str
    profile_fingerprint: str
    band_fraction: float
    total_equity_exact: str
    invested_pct: float
    cash_pct: float
    rows: tuple[SleeveRow, ...]
    breached: tuple[str, ...]
    unassigned_tickers: tuple[str, ...]
    disclosures: tuple[str, ...]
    refusals: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not self.refusals

    @property
    def breached_count(self) -> int:
        return len(self.breached)


def _position_value(position: object) -> Decimal | None:
    """Exact market value, preferring the broker-preserved exact text.

    Presence of the exact field makes it authoritative; a malformed exact
    value is corrupt input, not permission to fall back to the rounded
    display float and hide the corruption.
    """
    exact = getattr(position, "market_value_exact", None)
    if exact is not None:
        return decimal_or_none(exact)
    return decimal_or_none(getattr(position, "market_value", None))


def _aggregate_positions(
    snapshot: PortfolioSnapshot,
) -> tuple[dict[str, Decimal], list[str]]:
    """Canonical ticker -> summed exact market value, plus refusals.

    Rows are summed rather than replaced. Two rows for the same ticker are a
    real broker shape, and a per-ticker dict comprehension would silently
    keep only one of them -- understating that ticker's sleeve and every
    other sleeve's share of the denominator.
    """
    totals: dict[str, Decimal] = {}
    refusals: list[str] = []
    for position in snapshot.positions:
        ticker = str(position.ticker).strip().upper()
        if not ticker:
            refusals.append("A position row has no ticker.")
            continue
        value = _position_value(position)
        shares_input = (
            position.shares_exact
            if position.shares_exact is not None
            else position.shares
        )
        shares = decimal_or_none(shares_input)
        if shares is not None and shares == 0 and value == 0:
            # Zero quantity and zero value is a row for something not held.
            totals.setdefault(ticker, Decimal("0"))
            continue
        if value is None or value <= 0 or shares is None or shares <= 0:
            refusals.append(
                f"{ticker} is held but its exact quantity or market value is "
                + (
                    "unreadable"
                    if value is None or shares is None
                    else f"impossible ({decimal_text(shares)} share(s) worth "
                         f"{decimal_text(value)})"
                )
                + ". Refusing to measure drift, because one unusable holding "
                "distorts every sleeve's percentage through the shared "
                "equity denominator."
            )
            totals.setdefault(ticker, Decimal("0"))
            continue
        totals[ticker] = totals.get(ticker, Decimal("0")) + value
    return totals, refusals


def _pending_by_ticker(
    snapshot: PortfolioSnapshot,
) -> tuple[dict[str, Decimal], set[str], list[str]]:
    """Signed pending exposure per ticker: buys add, sells subtract.

    Returns ``(values, unknown_tickers, refusals)``. A working order whose
    value cannot be determined is reported as unknown rather than treated as
    zero, because zero is the one value it is certainly not.
    """
    values: dict[str, Decimal] = {}
    unknown: set[str] = set()
    refusals: list[str] = []
    if not snapshot.open_orders_available:
        refusals.append(
            "Open-order data is unavailable, so pending exposure cannot be "
            "measured and no projected weight can be shown."
        )
        return values, unknown, refusals

    for order in snapshot.open_orders or ():
        if not isinstance(order, dict):
            refusals.append(
                "An open-order row is unreadable, so pending exposure cannot "
                "be measured."
            )
            continue
        ticker = str(order.get("ticker") or "").strip().upper()
        if not ticker:
            refusals.append(
                "An open order has no ticker, so its pending exposure cannot "
                "be assigned to a sleeve."
            )
            continue
        side = str(order.get("side") or "").strip().lower()
        if side not in ("buy", "sell"):
            unknown.add(ticker)
            continue
        notional = order.get("notional")
        limit_price = order.get("limit_price")
        quantity = decimal_or_none(order.get("qty") or order.get("shares"))
        value = decimal_or_none(notional) if notional is not None else None
        # Presence makes broker notional authoritative. A malformed value is
        # corruption, not permission to substitute a derived estimate.
        if notional is None and quantity is not None and limit_price is not None:
            price = decimal_or_none(limit_price)
            if price is not None and price > 0 and quantity > 0:
                value = quantity * price
        if value is None or value <= 0:
            # A plain market order carries no determinable value here, and a
            # live quote call per rerun is exactly what this surface must not
            # do. Name it instead of guessing.
            unknown.add(ticker)
            continue
        signed = value if side == "buy" else -value
        values[ticker] = values.get(ticker, Decimal("0")) + signed
    return values, unknown, refusals


def _policy_conflicts(
    profile: AllocationProfile, policy: object | None
) -> dict[str, str]:
    """Sleeve -> why its target contradicts an active policy cap.

    A cap is not a target, but a target ABOVE a cap is unreachable, and one
    below a floor is unholdable. Either makes the band fiction, so the row is
    marked rather than quietly measured against an impossible number.
    """
    if policy is None:
        return {}
    conflicts: dict[str, str] = {}

    def add(sleeve: str, reason: str) -> None:
        existing = conflicts.get(sleeve)
        conflicts[sleeve] = f"{existing}; {reason}" if existing else reason

    leveraged_cap = decimal_or_none(getattr(policy, "max_leveraged_etf_pct", None))
    if leveraged_cap is not None:
        cap_pct = leveraged_cap * 100
        target = profile.target_decimal("leveraged_reinvestment")
        if target > cap_pct:
            add("leveraged_reinvestment", (
                f"target {decimal_text(target)}% exceeds the policy's "
                f"{decimal_text(cap_pct)}% leveraged-ETF cap"
            ))
    cash_floor = decimal_or_none(getattr(policy, "min_cash_reserve_pct", None))
    if cash_floor is not None:
        floor_pct = cash_floor * 100
        target = profile.target_decimal(SLEEVE_CASH)
        if target < floor_pct:
            add(SLEEVE_CASH, (
                f"target {decimal_text(target)}% is below the policy's "
                f"{decimal_text(floor_pct)}% minimum cash reserve"
            ))

    total_cap = decimal_or_none(getattr(policy, "max_total_exposure_pct", None))
    if total_cap is not None:
        cap_pct = total_cap * 100
        invested_target = sum(
            (profile.target_decimal(s) for s in SLEEVE_ORDER if s != SLEEVE_CASH),
            Decimal("0"),
        )
        if invested_target > cap_pct:
            reason = (
                f"the {decimal_text(invested_target)}% invested target exceeds "
                f"the policy's {decimal_text(cap_pct)}% total-exposure cap"
            )
            for sleeve in SLEEVE_ORDER:
                if sleeve != SLEEVE_CASH and profile.target_decimal(sleeve) > 0:
                    add(sleeve, reason)

    position_cap = decimal_or_none(getattr(policy, "max_position_pct", None))
    if position_cap is not None:
        membership = sleeve_membership()
        for sleeve in SLEEVE_ORDER:
            tickers = {t for t, assigned in membership.items() if assigned == sleeve}
            if not tickers:
                continue
            capacity = position_cap * Decimal(len(tickers)) * 100
            target = profile.target_decimal(sleeve)
            if target > capacity:
                add(
                    sleeve,
                    f"target {decimal_text(target)}% exceeds its "
                    f"{decimal_text(capacity)}% combined position-cap capacity "
                    f"across {len(tickers)} configured ticker(s)",
                )
    return conflicts


def evaluate_portfolio_rebalance(
    snapshot: PortfolioSnapshot,
    profile: AllocationProfile,
    *,
    policy: object | None = None,
) -> RebalanceReport:
    """Measure every sleeve against its band. Reports; proposes nothing."""
    refusals: list[str] = []
    try:
        validate_profile(profile)
        membership = sleeve_membership()
    except AllocationProfileError as exc:
        membership = {}
        refusals.append(str(exc))

    equity_input = (
        snapshot.total_equity_exact
        if snapshot.total_equity_exact is not None
        else snapshot.total_equity
    )
    equity = decimal_or_none(equity_input)
    if equity is None or equity <= 0:
        refusals.append(
            f"Total equity is not a usable positive amount ({equity_input!r}), "
            "so no sleeve weight can be computed."
        )
        equity = None

    values, value_refusals = _aggregate_positions(snapshot)
    refusals.extend(value_refusals)

    cash_input = (
        snapshot.cash_exact if snapshot.cash_exact is not None else snapshot.cash
    )
    cash = decimal_or_none(cash_input)
    if cash is None:
        refusals.append(
            f"Cash is not a usable amount ({cash_input!r}), so the cash "
            "sleeve cannot be measured."
        )

    pending, pending_unknown, pending_refusals = _pending_by_ticker(snapshot)
    refusals.extend(pending_refusals)

    conflicts = _policy_conflicts(profile, policy) if not refusals else {}

    sleeve_values: dict[str, Decimal] = {s: Decimal("0") for s in SLEEVE_ORDER}
    sleeve_pending: dict[str, Decimal] = {s: Decimal("0") for s in SLEEVE_ORDER}
    sleeve_tickers: dict[str, list[str]] = {s: [] for s in SLEEVE_ORDER}
    unassigned: list[str] = []
    unknown_sleeves: set[str] = set()

    for ticker, value in sorted(values.items()):
        sleeve = membership.get(ticker, SLEEVE_OTHER)
        sleeve_values[sleeve] += value
        sleeve_tickers[sleeve].append(ticker)
        if sleeve == SLEEVE_OTHER:
            unassigned.append(ticker)
    for ticker, value in sorted(pending.items()):
        sleeve = membership.get(ticker, SLEEVE_OTHER)
        sleeve_pending[sleeve] += value
        if ticker not in sleeve_tickers[sleeve]:
            sleeve_tickers[sleeve].append(ticker)
        if sleeve == SLEEVE_OTHER and ticker not in unassigned:
            unassigned.append(ticker)
        # A working buy consumes cash and a working sell produces it. Keeping
        # this opposite leg makes projected sleeve weights conserve equity.
        sleeve_pending[SLEEVE_CASH] -= value
    for ticker in sorted(pending_unknown):
        sleeve = membership.get(ticker, SLEEVE_OTHER)
        unknown_sleeves.add(sleeve)
        unknown_sleeves.add(SLEEVE_CASH)
        if ticker not in sleeve_tickers[sleeve]:
            sleeve_tickers[sleeve].append(ticker)
        if sleeve == SLEEVE_OTHER and ticker not in unassigned:
            unassigned.append(ticker)

    if cash is not None:
        sleeve_values[SLEEVE_CASH] = cash

    computable = not refusals and equity is not None
    rows: list[SleeveRow] = []
    breached: list[str] = []
    for sleeve in SLEEVE_ORDER:
        value = sleeve_values[sleeve]
        pending_value = sleeve_pending[sleeve]
        if not computable:
            rows.append(
                SleeveRow(
                    sleeve=sleeve, target_pct=0.0, lower_edge_pct=0.0,
                    upper_edge_pct=0.0, current_pct=0.0, projected_pct=0.0,
                    market_value_exact=decimal_text(value),
                    pending_value_exact=decimal_text(pending_value),
                    gap_to_target_exact="0",
                    status=STATUS_DATA_UNAVAILABLE,
                    tickers=tuple(sleeve_tickers[sleeve]),
                )
            )
            continue

        target = profile.target_decimal(sleeve)
        lower, upper = profile.band_edges(sleeve)
        current = value / equity * Decimal("100")
        projected = (value + pending_value) / equity * Decimal("100")
        gap = equity * target / Decimal("100") - (value + pending_value)

        if sleeve in unknown_sleeves:
            status = STATUS_PENDING_UNKNOWN
        elif sleeve in conflicts:
            status = STATUS_POLICY_CONFLICT
        elif sleeve == SLEEVE_OTHER and sleeve_tickers[sleeve]:
            # The residual always reads as unassigned when it holds anything,
            # so a reader is never invited to treat it as a tidy sleeve that
            # merely drifted.
            status = STATUS_UNASSIGNED
        elif projected < lower:
            status = STATUS_UNDERWEIGHT
        elif projected > upper:
            status = STATUS_OVERWEIGHT
        else:
            status = STATUS_INSIDE
        if status in (STATUS_UNDERWEIGHT, STATUS_OVERWEIGHT):
            breached.append(sleeve)

        rows.append(
            SleeveRow(
                sleeve=sleeve, target_pct=float(target),
                lower_edge_pct=float(lower), upper_edge_pct=float(upper),
                current_pct=float(current), projected_pct=float(projected),
                market_value_exact=decimal_text(value),
                pending_value_exact=decimal_text(pending_value),
                gap_to_target_exact=decimal_text(gap),
                status=status,
                tickers=tuple(sleeve_tickers[sleeve]),
            )
        )

    invested_pct = 0.0
    cash_pct = 0.0
    if computable:
        invested = sum(
            (sleeve_values[s] for s in SLEEVE_ORDER if s != SLEEVE_CASH),
            Decimal("0"),
        )
        invested_pct = float(invested / equity * 100)
        cash_pct = float(sleeve_values[SLEEVE_CASH] / equity * 100)

    disclosures = [BAND_MECHANISM_DISCLOSURE, UNASSIGNED_DISCLOSURE]
    for sleeve, reason in sorted(conflicts.items()):
        disclosures.append(f"{sleeve}: {reason}.")

    valid_profile = isinstance(profile, AllocationProfile)
    return RebalanceReport(
        as_of=snapshot.as_of,
        profile_version=profile.version if valid_profile else "",
        profile_fingerprint=(
            compute_profile_fingerprint(profile) if valid_profile else ""
        ),
        band_fraction=float(profile.band_decimal()) if valid_profile else 0.0,
        total_equity_exact=decimal_text(equity) if equity is not None else "0",
        invested_pct=invested_pct,
        cash_pct=cash_pct,
        rows=tuple(rows),
        breached=tuple(breached),
        unassigned_tickers=tuple(unassigned),
        disclosures=tuple(disclosures),
        refusals=tuple(refusals),
    )
