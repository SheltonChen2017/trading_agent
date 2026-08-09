"""Three-sleeve engine status report (M1 of THREE_SLEEVE_ENGINE_PLAN).

Deliberately a REPORT, not a proposal source. Nothing here creates, sizes,
approves, or ranks a trade, and no field is action-shaped: the numbers say
what the portfolio *is* relative to the owner's stated preference, never
what to do about it. The owner reads it and decides.

The engine it measures (docs/reference/THREE_SLEEVE_ENGINE_PLAN.md,
owner-adopted 2026-08-09) is a PREFERENCE, not validated research, and this
module must never describe it otherwise. Three sleeves:

* dividend income (``config.DIVIDEND_INCOME_TICKERS``), with a floor of
  ``DIVIDEND_SLEEVE_FLOOR_PCT`` of total equity;
* semis/tech growth rotation (``GROWTH_ROTATION_TICKERS``), watched per
  LOT against gain/decline review thresholds; and
* leveraged reinvestment destinations (``DIVIDEND_REINVEST_TICKERS``)
  for confirmed dividend income.

Thresholds are per-lot on ``cost_per_share`` -- never average cost, which
is exactly the lens ``assistant/tax_lots.py`` documents as hiding real
money. Per-lot rows come from that module's already-reviewed
``unrealized_by_lot``, which also carries the tax-reduction mechanism the
owner mandated (2026-08-09): term-if-sold-now, days to long term, and the
first long-term date, so a crossing can be weighed against the tax
consequence of acting on it now. Classification and dates only -- this
module never invents a tax bracket.

Coverage honesty: lots exist only for fills this application recorded.
A growth position whose snapshot shares disagree with its ledger lots is
reported with BOTH numbers and a reason, and threshold flags are computed
only over covered lots. Silent row-dropping is the failure mode this
shape exists to prevent.

Dividend income is summed from the append-only journal's
``INCOME:DIVIDENDS`` postings -- the accounting authority. There is
deliberately NO "reinvestable budget" field in M1: a budget number without
the M3 earmark records would carry undefined double-spend semantics and
invite acting on it.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Iterable, Mapping

import config
from assistant.money import decimal_text, to_decimal
from assistant.portfolio_ledger import ACCOUNT_DIVIDEND_INCOME
from assistant.schemas import PortfolioSnapshot
from assistant.tax_lots import LotLedger, TaxLotError, unrealized_by_lot

# Ledger lot quantities are floats replayed from fills; snapshot shares are
# broker decimals. Equality within a millionth of a share is agreement;
# anything larger is a real coverage gap, not float noise.
_SHARE_MATCH_TOLERANCE = 1e-6

_TWO_PLACES = Decimal("0.01")


class SleeveReportError(ValueError):
    """The inputs cannot support an honest sleeve report."""


def _pct_of_equity(amount: Decimal, total_equity: Decimal) -> str:
    return decimal_text((amount / total_equity * Decimal("100")).quantize(_TWO_PLACES))


def _money(amount: Decimal) -> str:
    return decimal_text(amount.quantize(_TWO_PLACES))


def _holding_rows(
    snapshot: PortfolioSnapshot,
    tickers: Iterable[str],
    total_equity: Decimal,
) -> tuple[list[dict[str, Any]], Decimal]:
    rows: list[dict[str, Any]] = []
    total = Decimal("0")
    wanted = {t.upper() for t in tickers}
    for position in snapshot.positions:
        if position.ticker.upper() not in wanted:
            continue
        value = position.exact_field("market_value")
        total += value
        rows.append(
            {
                "ticker": position.ticker.upper(),
                "market_value": _money(value),
                "pct_of_equity": _pct_of_equity(value, total_equity),
            }
        )
    rows.sort(key=lambda row: row["ticker"])
    return rows, total


def _dividend_income(journal_postings: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum confirmed dividend income from the journal's income account.

    Income posts NEGATIVE to ``INCOME:DIVIDENDS`` (double-entry: cash
    debits, income credits), so received income is the negated sum. A
    posting without ticker metadata still counts -- it lands in an explicit
    unattributed bucket instead of being dropped or guessed.
    """
    by_ticker: dict[str, Decimal] = {}
    unattributed = Decimal("0")
    total = Decimal("0")
    count = 0
    for posting in journal_postings:
        if posting.get("account") != ACCOUNT_DIVIDEND_INCOME:
            continue
        count += 1
        amount = -to_decimal(posting["amount"], name="dividend posting amount")
        if amount < 0:
            # A positive INCOME:DIVIDENDS posting would be a reversal or a
            # corrupt row; either way pretending it is income would be
            # wrong in the dangerous direction. Refuse loudly.
            raise SleeveReportError(
                "journal contains a negative dividend income amount "
                f"({decimal_text(amount)}); refusing to report income from it"
            )
        total += amount
        metadata = posting.get("metadata") or {}
        ticker = str(metadata.get("ticker") or "").upper()
        if ticker:
            by_ticker[ticker] = by_ticker.get(ticker, Decimal("0")) + amount
        else:
            unattributed += amount
    return {
        "confirmed_total": _money(total),
        "by_ticker": {t: _money(v) for t, v in sorted(by_ticker.items())},
        "unattributed_total": _money(unattributed),
        "posting_count": count,
        "note": (
            "income received to date from the account journal; reinvestment "
            "earmarking is not tracked until M3 of the engine plan"
        ),
    }


def _growth_positions(
    snapshot: PortfolioSnapshot,
    ledger: LotLedger,
    total_equity: Decimal,
    *,
    growth_tickers: Iterable[str],
    gain_threshold_pct: float,
    decline_threshold_pct: float,
) -> tuple[list[dict[str, Any]], int, int]:
    positions: list[dict[str, Any]] = []
    gain_crossings = 0
    decline_crossings = 0
    wanted = {t.upper() for t in growth_tickers}
    for position in snapshot.positions:
        ticker = position.ticker.upper()
        if ticker not in wanted:
            continue
        value = position.exact_field("market_value")
        row: dict[str, Any] = {
            "ticker": ticker,
            "market_value": _money(value),
            "pct_of_equity": _pct_of_equity(value, total_equity),
            "snapshot_shares": position.shares,
        }
        try:
            lots = unrealized_by_lot(ledger, ticker, position.current_price)
        except TaxLotError as exc:
            # A bad price must degrade THIS position's lot view loudly, not
            # crash the report or silently show the position lot-less.
            row.update(
                {
                    "ledger_lot_shares": None,
                    "lot_coverage": "unavailable",
                    "coverage_reason": f"per-lot view unavailable: {exc}",
                    "lots": [],
                }
            )
            positions.append(row)
            continue

        lot_shares = sum(lot["qty"] for lot in lots)
        share_gap = position.shares - lot_shares
        if not lots:
            coverage = "none"
            reason = (
                "no recorded fills produce lots for this position (acquired "
                "outside this app or before ledger bootstrap); threshold "
                "review is not possible without a per-lot basis"
            )
        elif abs(share_gap) > _SHARE_MATCH_TOLERANCE:
            coverage = "partial"
            reason = (
                f"snapshot holds {position.shares} shares but recorded lots "
                f"cover {lot_shares}; threshold flags below describe only "
                "the covered lots"
            )
        else:
            coverage = "full"
            reason = None

        annotated_lots = []
        for lot in lots:
            pct = lot["unrealized_pnl_pct"]
            annotated = dict(lot)
            annotated["crossed_gain_review_threshold"] = pct >= gain_threshold_pct
            annotated["crossed_decline_review_threshold"] = pct <= decline_threshold_pct
            gain_crossings += annotated["crossed_gain_review_threshold"]
            decline_crossings += annotated["crossed_decline_review_threshold"]
            annotated_lots.append(annotated)

        row.update(
            {
                "ledger_lot_shares": lot_shares,
                "lot_coverage": coverage,
                "coverage_reason": reason,
                "lots": annotated_lots,
            }
        )
        positions.append(row)
    positions.sort(key=lambda row: row["ticker"])
    return positions, gain_crossings, decline_crossings


def _single_issuer_overlap(
    snapshot: PortfolioSnapshot,
    *,
    income_underlying: Mapping[str, str],
    leveraged_underlying: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Name every route to an issuer that a single-stock income ETF rides.

    JEPI-style diversified funds never appear here; NVDY-style funds do,
    whenever the same issuer is also held directly or through a leveraged
    ETF. Disclosure only -- concentration is the owner's to accept, but it
    must be visible to be accepted.
    """
    held = {p.ticker.upper() for p in snapshot.positions}
    overlaps: list[dict[str, Any]] = []
    for income_etf, issuer in sorted(income_underlying.items()):
        if income_etf.upper() not in held:
            continue
        routes = [f"{income_etf.upper()} (income ETF on {issuer})"]
        if issuer.upper() in held:
            routes.append(f"{issuer} held directly")
        for etf, underlying in sorted(leveraged_underlying.items()):
            if underlying.upper() == issuer.upper() and etf.upper() in held:
                routes.append(f"{etf} (leveraged ETF on {issuer})")
        if len(routes) > 1:
            overlaps.append({"issuer": issuer.upper(), "routes": routes})
    return overlaps


def evaluate_sleeves(
    snapshot: PortfolioSnapshot,
    ledger: LotLedger,
    journal_postings: Iterable[Mapping[str, Any]],
    *,
    dividend_tickers: Iterable[str] = tuple(config.DIVIDEND_INCOME_TICKERS),
    growth_tickers: Iterable[str] = tuple(config.GROWTH_ROTATION_TICKERS),
    reinvest_tickers: Iterable[str] = tuple(config.DIVIDEND_REINVEST_TICKERS),
    floor_pct: float = config.DIVIDEND_SLEEVE_FLOOR_PCT,
    gain_threshold_pct: float = config.GROWTH_GAIN_REVIEW_THRESHOLD_PCT,
    decline_threshold_pct: float = config.GROWTH_DECLINE_REVIEW_THRESHOLD_PCT,
    income_underlying: Mapping[str, str] | None = None,
    leveraged_underlying: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Measure the portfolio against the owner's three-sleeve preference.

    Pure over its inputs: pass a snapshot, a replayed lot ledger, and the
    journal postings. Store access belongs to the caller (see the CLI),
    so this function can be tested exhaustively without a database and can
    never write anywhere.

    Raises ``SleeveReportError`` when the inputs cannot support an honest
    report (non-finite or non-positive equity, corrupt income postings).
    Failing loudly is correct: a sleeve report derived from broken inputs
    would be read as fact.
    """
    for name, value in (
        ("floor_pct", floor_pct),
        ("gain_threshold_pct", gain_threshold_pct),
        ("decline_threshold_pct", decline_threshold_pct),
    ):
        if not math.isfinite(value):
            raise SleeveReportError(f"{name} must be finite, got {value!r}")
    if gain_threshold_pct <= 0:
        raise SleeveReportError(
            f"gain_threshold_pct must be positive, got {gain_threshold_pct!r}"
        )
    if decline_threshold_pct >= 0:
        raise SleeveReportError(
            f"decline_threshold_pct must be negative, got {decline_threshold_pct!r}"
        )
    if floor_pct < 0:
        raise SleeveReportError(f"floor_pct must be >= 0, got {floor_pct!r}")

    try:
        total_equity = snapshot.total_equity_exact_decimal
    except ValueError as exc:
        raise SleeveReportError(f"snapshot equity is not usable: {exc}") from exc
    if not total_equity.is_finite() or total_equity <= 0:
        raise SleeveReportError(
            "total equity must be positive and finite to express sleeves as "
            f"a share of it, got {decimal_text(total_equity)}"
        )

    held = {p.ticker.upper() for p in snapshot.positions}

    dividend_rows, dividend_total = _holding_rows(
        snapshot, dividend_tickers, total_equity
    )
    dividend_pct = dividend_total / total_equity * Decimal("100")
    floor = to_decimal(floor_pct, name="floor_pct")
    reinvest_rows, reinvest_total = _holding_rows(
        snapshot, reinvest_tickers, total_equity
    )
    growth_rows, gain_crossings, decline_crossings = _growth_positions(
        snapshot,
        ledger,
        total_equity,
        growth_tickers=growth_tickers,
        gain_threshold_pct=gain_threshold_pct,
        decline_threshold_pct=decline_threshold_pct,
    )

    return {
        "as_of": snapshot.as_of,
        "portfolio_source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "total_equity": _money(total_equity),
        "engine": {
            "plan": "docs/reference/THREE_SLEEVE_ENGINE_PLAN.md",
            "authority": (
                "owner-stated preference (2026-08-09); not validated research"
            ),
            "floor_pct": decimal_text(floor),
            "gain_review_threshold_pct": decimal_text(
                to_decimal(gain_threshold_pct, name="gain_threshold_pct")
            ),
            "decline_review_threshold_pct": decimal_text(
                to_decimal(decline_threshold_pct, name="decline_threshold_pct")
            ),
            "threshold_basis": "per_lot_cost_per_share",
        },
        "dividend_sleeve": {
            "holdings": dividend_rows,
            "total_market_value": _money(dividend_total),
            "pct_of_equity": decimal_text(dividend_pct.quantize(_TWO_PLACES)),
            # Exact boundary: exactly at the floor is AT the floor, not
            # below it. Compared on unrounded values so a display-rounded
            # 10.00 cannot flip the verdict.
            "floor_status": (
                "below_floor" if dividend_pct < floor else "at_or_above_floor"
            ),
            "candidates_not_held": sorted(
                t.upper() for t in dividend_tickers if t.upper() not in held
            ),
        },
        "growth_sleeve": {
            "positions": growth_rows,
            "candidates_not_held": sorted(
                t.upper() for t in growth_tickers if t.upper() not in held
            ),
            "lots_at_gain_review": gain_crossings,
            "lots_at_decline_review": decline_crossings,
        },
        "reinvest_sleeve": {
            "holdings": reinvest_rows,
            "total_market_value": _money(reinvest_total),
            "pct_of_equity": decimal_text(
                (reinvest_total / total_equity * Decimal("100")).quantize(_TWO_PLACES)
            ),
            "candidates_not_held": sorted(
                t.upper() for t in reinvest_tickers if t.upper() not in held
            ),
        },
        "dividend_income": _dividend_income(journal_postings),
        "single_issuer_overlap": _single_issuer_overlap(
            snapshot,
            income_underlying=(
                config.SINGLE_STOCK_INCOME_ETF_UNDERLYING
                if income_underlying is None
                else income_underlying
            ),
            leveraged_underlying=(
                config.LEVERAGED_ETF_UNDERLYING
                if leveraged_underlying is None
                else leveraged_underlying
            ),
        ),
    }
