"""GR-7d (report-only slice): portfolio drift measured against a target weighting.

Deliberately a REPORT, not a proposal source. Nothing here creates, sizes,
approves, ranks, or orders a trade, and no field is action-shaped: every
number says what the portfolio *is* relative to a stated target, never what
to buy or sell. Share counts are conspicuously absent -- converting a dollar
gap into shares is proposal-layer work and is out of scope for this
milestone by explicit owner decision (2026-08-06), so that the owner can
read real drift numbers before any proposal-generating code exists.

WHY A TARGET HAD TO BE CHOSEN BY THE OWNER, NOT DERIVED
-------------------------------------------------------
``docs/ACTION_PLAN_2026-08-02.md`` recorded GR-7d as blocked on an owner
decision rather than on code, and the reason survives into this module. The
approved mandate defines *risk-shape* targets (a volatility band, drawdown
limits); ``TradingPolicy`` defines *caps* (``max_position_pct``,
``max_total_exposure_pct``, ``max_basket_pct``, ``min_cash_reserve_pct``).
**A cap is not a target.** Neither document contains a target allocation, so
deriving one here would have been this project inventing an investment
policy and asserting an allocation claim it has no evidence for -- exactly
what ``CLAUDE.md`` sections 1 and 6 forbid. The target is therefore an
argument, supplied by the caller from an explicit owner-chosen list.

WHAT THE TARGET IS NOT
----------------------
``target_weights_equal()`` divides one exposure figure evenly across a
ticker list. That is an arithmetic convenience, not a claim. Equal weight is
not asserted here to be optimal, risk-efficient, or superior to any
alternative; it is the weighting that asserts the *least* -- no security
selection and no sector view -- which is the honest default for a project
whose research record is seven-plus candidate signals tested and zero
confirmed. Nothing in this module should be cited as evidence for any
allocation.

THREE ROW CLASSES, AND WHY THE THIRD MATTERS MOST
-------------------------------------------------
1. in target and held        -> ordinary drift measurement
2. in target and not held    -> fully underweight (current 0%)
3. **held but NOT in target** -> target 0%

Class 3 is the dangerous one and is never silently dropped. A holding absent
from the target list has an implied target of zero, which reads as "exit the
entire position" -- a far larger statement than routine drift. Silently
omitting such a row would understate the consequence of adopting a target,
which is the reporting analogue of the standing watch item in
``docs/OPERATIONAL_FACTS.md`` about dropping a row and losing its cash flow.
Real holdings hit this class: as of 2026-08-06 the paper account held NVDL
and BBB, and ``config.CONFIGURED_LEVERAGED_PAIRS`` deliberately trades
SOXX/SOXL -- none of which appear in ``config.UNIVERSE``. A UNIVERSE-derived
target therefore implies exiting positions that other, deliberately
configured parts of this system exist to hold. That conflict is surfaced as
``held_not_in_target`` rows and a ``held_not_in_target`` count, and is a
finding for the owner to resolve, never something this module resolves on
its own.

RELATIVE BAND, AND THE UNDEFINED CASE
-------------------------------------
Drift is relative: ``(current - target) / target``. The owner chose a wide
band (2026-08-06) because this project's own rotation research found a wide
rebalance band produced materially less realised tax for equivalent
performance. Boundaries are INCLUSIVE -- a position exactly at the band edge
is inside it and reports no drift action -- matching both the archived GR-7
plan ("respect the band and never propose inside it") and the inclusive-cap
convention already pinned by ``tests/test_allocation_batch.py``.

When the target weight is zero the relative ratio is undefined, and this
module does **not** divide. ``drift_ratio_pct`` is ``None`` for those rows
and the status is decided by whether anything is actually held. Returning a
sentinel number instead would let a zero-target row silently compare as
"inside band" -- a fail-open direction.

PRECISION
---------
All arithmetic runs in ``Decimal`` via ``assistant/money.py``; no binary
float enters a money path. Exact broker decimal text is preferred over the
display-rounded floats wherever the snapshot carries it, and
``exact_numerics`` reports which of the two the figures came from rather
than leaving the reader to assume. Emitted strings are rounded for
presentation only (money to cents, percentages to four places), which is the
rounding ``assistant/money.py`` explicitly permits presentation code to do;
the comparisons that decide a row's status are made on unrounded values
BEFORE that rounding, so a row can never be classified by a rounded number.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping

from assistant.money import decimal_text, to_decimal
from assistant.schemas import PortfolioSnapshot

# Presentation-only quantisation. The status decision for every row is made
# on unrounded Decimals before these are applied -- see _row_status().
_MONEY_PLACES = Decimal("0.01")
_PERCENT_PLACES = Decimal("0.0001")

STATUS_INSIDE_BAND = "inside_band"
STATUS_UNDERWEIGHT = "underweight"
STATUS_OVERWEIGHT = "overweight"
STATUS_HELD_NOT_IN_TARGET = "held_not_in_target"

# Every status this module can emit. Exhaustive by construction so a caller
# can switch on it without a silent default branch.
ROW_STATUSES = (
    STATUS_INSIDE_BAND,
    STATUS_UNDERWEIGHT,
    STATUS_OVERWEIGHT,
    STATUS_HELD_NOT_IN_TARGET,
)


class RebalanceReportError(ValueError):
    """The snapshot or target cannot support an honest drift report."""


def _money(value: Decimal) -> str:
    return decimal_text(value.quantize(_MONEY_PLACES))


def _percent(value: Decimal) -> str:
    return decimal_text(value.quantize(_PERCENT_PLACES))


def target_weights_equal(
    tickers: Iterable[str],
    total_exposure_pct: float | Decimal | str,
) -> dict[str, Decimal]:
    """Split ``total_exposure_pct`` evenly across ``tickers``.

    Returns ticker -> percent-of-equity as an unrounded ``Decimal``. Tickers
    are upper-cased and de-duplicated; duplicates in the input would
    otherwise silently concentrate the weighting, since a name listed twice
    would receive twice the intended share.

    RESIDUAL, stated rather than hidden: when ``total_exposure_pct`` does not
    divide evenly by the ticker count the per-ticker weight is a repeating
    decimal, so the weights cannot sum to exactly ``total_exposure_pct`` at
    finite precision -- 50% across 104 names is the live example. The residual
    is on the order of 1e-26 percentage points, i.e. sub-cent on any
    conceivable account. It is deliberately NOT redistributed: handing the
    remainder to some arbitrary subset of tickers would make the weighting
    unequal, which is a worse lie than a 1e-26 rounding residual. Callers must
    not assume exact summation.

    This is arithmetic, not an investment claim -- see the module docstring.
    """
    normalised: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = str(raw).strip().upper()
        if not ticker:
            raise RebalanceReportError("Target ticker list contains a blank ticker.")
        if ticker in seen:
            continue
        seen.add(ticker)
        normalised.append(ticker)

    if not normalised:
        raise RebalanceReportError(
            "Target ticker list is empty; a target portfolio of nothing is not a "
            "target. Supply the owner-chosen target list explicitly."
        )

    try:
        exposure = to_decimal(total_exposure_pct, name="total_exposure_pct")
    except ValueError as exc:
        raise RebalanceReportError(f"Invalid total_exposure_pct: {exc}") from exc
    if exposure <= 0:
        raise RebalanceReportError(
            f"total_exposure_pct must be positive, got {decimal_text(exposure)}."
        )
    if exposure > Decimal("100"):
        raise RebalanceReportError(
            f"total_exposure_pct {decimal_text(exposure)}% exceeds 100% of equity."
        )

    per_ticker = exposure / Decimal(len(normalised))
    return {ticker: per_ticker for ticker in normalised}


def _aggregate_positions(snapshot: PortfolioSnapshot) -> dict[str, Decimal]:
    """Market value per ticker, summing any duplicate rows for one ticker.

    A broker or a manual snapshot may legitimately carry more than one row
    for the same symbol. Taking only the first (or last) would understate
    the position and make an overweight holding look compliant, so rows are
    summed -- the same aggregation ``tests/test_proposals.py`` already pins
    for the risk-reduction generator.
    """
    values: dict[str, Decimal] = {}
    for position in snapshot.positions:
        ticker = str(position.ticker).strip().upper()
        if not ticker:
            raise RebalanceReportError(
                "Portfolio snapshot contains a position with a blank ticker; "
                "refusing to report drift against an unidentifiable holding."
            )
        try:
            market_value = position.exact_field("market_value")
        except ValueError as exc:
            raise RebalanceReportError(
                f"{ticker}: unusable market value ({exc})."
            ) from exc
        values[ticker] = values.get(ticker, Decimal("0")) + market_value
    return values


def _row_status(
    *,
    in_target: bool,
    target_value: Decimal,
    current_value: Decimal,
    drift_ratio_pct: Decimal | None,
    band_pct: Decimal,
) -> str:
    """Classify one row from UNROUNDED values.

    Fails toward reporting drift rather than concealing it: a zero-target row
    that holds anything is never "inside band", because the relative ratio
    that would place it there does not exist.
    """
    if not in_target:
        return STATUS_HELD_NOT_IN_TARGET
    if drift_ratio_pct is None:
        # In target, yet zero target value -- only reachable if the target
        # weight itself is zero, which target_weights_equal() cannot produce.
        # Treated as drift rather than silently passed.
        return STATUS_OVERWEIGHT if current_value > 0 else STATUS_INSIDE_BAND
    if abs(drift_ratio_pct) <= band_pct:
        return STATUS_INSIDE_BAND
    return STATUS_UNDERWEIGHT if drift_ratio_pct < 0 else STATUS_OVERWEIGHT


def evaluate_rebalance_drift(
    snapshot: PortfolioSnapshot,
    target_weights_pct: Mapping[str, float | Decimal | str],
    *,
    band_pct: float | Decimal | str,
) -> dict[str, Any]:
    """Measure each holding's drift from its target weight.

    ``target_weights_pct`` maps ticker -> percent of TOTAL EQUITY (not
    percent of the invested sleeve), so the figures compose directly with
    ``TradingPolicy``'s caps, which are also expressed against total equity.

    ``band_pct`` is a RELATIVE tolerance in percent: 25 means a position is
    inside the band while it sits within +/-25% of its own target weight.
    The boundary is inclusive.

    Returns a JSON-serialisable dict. Money and percent values are strings
    carrying exact decimal text (presentation-rounded), never floats.
    """
    try:
        band = to_decimal(band_pct, name="band_pct")
    except ValueError as exc:
        raise RebalanceReportError(f"Invalid band_pct: {exc}") from exc
    if band < 0:
        raise RebalanceReportError(
            f"band_pct must not be negative, got {decimal_text(band)}."
        )

    try:
        total_equity = snapshot.total_equity_exact_decimal
    except ValueError as exc:
        raise RebalanceReportError(f"Unusable total equity: {exc}") from exc
    if total_equity <= 0:
        raise RebalanceReportError(
            f"Total equity is {decimal_text(total_equity)}; drift against a "
            "non-positive equity base is meaningless. Refusing to report."
        )

    targets: dict[str, Decimal] = {}
    for raw_ticker, raw_weight in target_weights_pct.items():
        ticker = str(raw_ticker).strip().upper()
        if not ticker:
            raise RebalanceReportError("Target weights contain a blank ticker.")
        if ticker in targets:
            raise RebalanceReportError(
                f"Target weights contain {ticker} more than once after "
                "normalisation; the intended weight is ambiguous."
            )
        try:
            weight = to_decimal(raw_weight, name=f"target_weight[{ticker}]")
        except ValueError as exc:
            raise RebalanceReportError(f"{ticker}: invalid target weight ({exc}).") from exc
        if weight < 0:
            raise RebalanceReportError(
                f"{ticker}: target weight {decimal_text(weight)}% is negative."
            )
        targets[ticker] = weight

    if not targets:
        raise RebalanceReportError(
            "No target weights supplied; there is nothing to measure drift against."
        )

    held = _aggregate_positions(snapshot)

    rows: list[dict[str, Any]] = []
    # Union, so a held ticker absent from the target set still produces a row.
    for ticker in sorted(set(targets) | set(held)):
        in_target = ticker in targets
        target_pct = targets.get(ticker, Decimal("0"))
        target_value = total_equity * target_pct / Decimal("100")
        current_value = held.get(ticker, Decimal("0"))
        current_pct = current_value / total_equity * Decimal("100")

        drift_ratio_pct: Decimal | None
        if target_value > 0:
            drift_ratio_pct = (current_value - target_value) / target_value * Decimal("100")
        else:
            drift_ratio_pct = None

        status = _row_status(
            in_target=in_target,
            target_value=target_value,
            current_value=current_value,
            drift_ratio_pct=drift_ratio_pct,
            band_pct=band,
        )

        rows.append(
            {
                "ticker": ticker,
                "in_target": in_target,
                "held": current_value != 0,
                "status": status,
                "target_pct": _percent(target_pct),
                "target_value": _money(target_value),
                "current_pct": _percent(current_pct),
                "current_value": _money(current_value),
                # Descriptive gap, NOT an instruction and NOT a share count:
                # how far this holding sits from its stated target in dollars.
                "gap_value": _money(target_value - current_value),
                "drift_ratio_pct": (
                    None if drift_ratio_pct is None else _percent(drift_ratio_pct)
                ),
            }
        )

    invested = sum(held.values(), Decimal("0"))
    target_invested_pct = sum(targets.values(), Decimal("0"))
    counts = {status: 0 for status in ROW_STATUSES}
    for row in rows:
        counts[row["status"]] += 1

    return {
        "as_of": snapshot.as_of,
        "account_mode": snapshot.account_mode,
        "source": snapshot.source,
        "exact_numerics": snapshot.has_exact_numerics,
        "band_pct": _percent(band),
        "totals": {
            "total_equity": _money(total_equity),
            "invested": _money(invested),
            "invested_pct": _percent(invested / total_equity * Decimal("100")),
            "cash": _money(snapshot.cash_exact_decimal),
            "target_invested_pct": _percent(target_invested_pct),
            "target_ticker_count": len(targets),
        },
        "counts": counts,
        "rows": rows,
    }
