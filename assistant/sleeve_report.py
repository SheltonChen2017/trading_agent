"""Three-sleeve engine status report (M1 of THREE_SLEEVE_ENGINE_PLAN).

Deliberately a REPORT, not a proposal source. Nothing here creates, sizes,
approves, or ranks a trade, and no field is action-shaped: the numbers say
what the portfolio *is* relative to the owner's stated preference, never
what to do about it. The owner reads it and decides.

The engine it measures (docs/Plan/THREE_SLEEVE_ENGINE_PLAN.md,
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
first long-term date. Classification and dates only -- this module never
invents a tax bracket.

REVISION 2 (owner-adopted 2026-08-09, after a measured backtest rejected
the +5% any-term full exit): gain review is now LONG-TERM-GATED and a
TRIM, not an exit. A lot at or above the price threshold but still
short-term is a distinct state -- ``gain_threshold_met_awaiting_long_term``
-- whose content is the countdown, and it is deliberately NOT counted as
crossed: collapsing the two states would reintroduce short-term sales
through an eager reader. The trim fraction is engine metadata here; the
report still proposes nothing.

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

from decimal import Decimal
from datetime import datetime
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
        if not isinstance(metadata, Mapping):
            raise SleeveReportError(
                "dividend posting metadata must be an object, got "
                f"{type(metadata).__name__}"
            )
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
    gain_threshold_pct: Decimal,
    decline_threshold_pct: Decimal,
    gain_requires_long_term: bool,
    now: datetime | None,
) -> tuple[list[dict[str, Any]], int, int, int]:
    positions: list[dict[str, Any]] = []
    gain_crossings = 0
    decline_crossings = 0
    awaiting_long_term = 0
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
            exact_price = position.exact_field("current_price")
            lots = unrealized_by_lot(
                ledger, ticker, float(exact_price), now=now
            )
        except (TaxLotError, ValueError, TypeError) as exc:
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
            annotated = dict(lot)
            basis = to_decimal(
                lot["cost_per_share"], name=f"{ticker} lot cost_per_share"
            )
            # `unrealized_by_lot` rounds its display percentage to two
            # places. Comparing that rounded number would move both exact
            # boundaries in the dangerous direction: +49.999% would become
            # +50.00% and -9.999% would become -10.00%. Recompute from the
            # preserved snapshot price and the lot's own basis, publish the
            # unrounded value, and use that same value for both verdicts.
            exact_pct = (exact_price - basis) / basis * Decimal("100")
            annotated["unrealized_pnl_pct"] = float(exact_pct)
            # Keep the legacy float display field from unrealized_by_lot,
            # but also publish the plan-mandated decimal money path. M2
            # notifications consume this exact-text field rather than
            # round-tripping the display float back into accounting data.
            quantity = to_decimal(lot["qty"], name=f"{ticker} lot quantity")
            annotated["unrealized_pnl_money"] = _money(
                (exact_price - basis) * quantity
            )
            price_met = exact_pct >= gain_threshold_pct
            # Revision 2: the long-term gate is part of the RULE, not a
            # footnote. A lot above the price threshold but still short-term
            # has NOT crossed gain review -- it is "awaiting long-term", a
            # distinct state whose whole content is the countdown the tax
            # mechanism already computes (days_to_long_term). Collapsing the
            # two states into one flag would reintroduce short-term sales
            # through the back door of an eager reader.
            is_long_term = lot["term_if_sold_now"] == "long"
            crossed_gain = price_met and (is_long_term or not gain_requires_long_term)
            annotated["crossed_gain_review_threshold"] = crossed_gain
            annotated["gain_threshold_met_awaiting_long_term"] = (
                price_met and gain_requires_long_term and not is_long_term
            )
            annotated["crossed_decline_review_threshold"] = (
                exact_pct <= decline_threshold_pct
            )
            gain_crossings += crossed_gain
            awaiting_long_term += annotated["gain_threshold_met_awaiting_long_term"]
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
    return positions, gain_crossings, decline_crossings, awaiting_long_term


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
    gain_requires_long_term: bool = config.GROWTH_GAIN_REVIEW_REQUIRES_LONG_TERM,
    gain_trim_fraction: float = config.GROWTH_GAIN_REVIEW_TRIM_FRACTION,
    decline_threshold_pct: float = config.GROWTH_DECLINE_REVIEW_THRESHOLD_PCT,
    income_underlying: Mapping[str, str] | None = None,
    leveraged_underlying: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Measure the portfolio against the owner's three-sleeve preference.

    Pure over its inputs: pass a snapshot, a replayed lot ledger, and the
    journal postings. Store access belongs to the caller (see the CLI),
    so this function can be tested exhaustively without a database and can
    never write anywhere.

    ``now`` is the evaluation instant for every lot-age classification
    (``term_if_sold_now``, ``days_to_long_term``, the long-term gate).  It
    defaults to the live UTC clock for production callers.  It is an explicit
    input rather than an ambient read so the report is a pure function of its
    arguments: a fixed-clock fixture must not drift into a different tax term
    as wall time advances (TPR-OOL-009 / SI-OOL-002 / IB0H-OOL01).

    Raises ``SleeveReportError`` when the inputs cannot support an honest
    report (non-finite or non-positive equity, corrupt income postings).
    Failing loudly is correct: a sleeve report derived from broken inputs
    would be read as fact.
    """
    try:
        floor = to_decimal(floor_pct, name="floor_pct")
        gain_threshold = to_decimal(
            gain_threshold_pct, name="gain_threshold_pct"
        )
        decline_threshold = to_decimal(
            decline_threshold_pct, name="decline_threshold_pct"
        )
    except ValueError as exc:
        raise SleeveReportError(str(exc)) from exc
    if gain_threshold <= 0:
        raise SleeveReportError(
            f"gain_threshold_pct must be positive, got {gain_threshold_pct!r}"
        )
    if decline_threshold >= 0:
        raise SleeveReportError(
            f"decline_threshold_pct must be negative, got {decline_threshold_pct!r}"
        )
    if floor < 0:
        raise SleeveReportError(f"floor_pct must be >= 0, got {floor_pct!r}")
    if not isinstance(gain_requires_long_term, bool):
        raise SleeveReportError(
            "gain_requires_long_term must be a bool, got "
            f"{gain_requires_long_term!r}"
        )
    # Trim fraction is presentation metadata in M1 (the report proposes
    # nothing), but a nonsense value would still be repeated into every
    # notification and CLI line downstream, so it is validated as strictly
    # as a behavioral input: a fraction of a lot must be in (0, 1].
    try:
        trim_fraction = to_decimal(
            gain_trim_fraction, name="gain_trim_fraction"
        )
    except ValueError as exc:
        raise SleeveReportError(str(exc)) from exc
    if (
        not isinstance(gain_trim_fraction, float)
        or not Decimal("0") < trim_fraction <= Decimal("1")
    ):
        raise SleeveReportError(
            f"gain_trim_fraction must be a float in (0, 1], got "
            f"{gain_trim_fraction!r}"
        )

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

    try:
        dividend_rows, dividend_total = _holding_rows(
            snapshot, dividend_tickers, total_equity
        )
        dividend_pct = dividend_total / total_equity * Decimal("100")
        reinvest_rows, reinvest_total = _holding_rows(
            snapshot, reinvest_tickers, total_equity
        )
        growth_rows, gain_crossings, decline_crossings, awaiting_lt = (
            _growth_positions(
                snapshot,
                ledger,
                total_equity,
                growth_tickers=growth_tickers,
                gain_threshold_pct=gain_threshold,
                decline_threshold_pct=decline_threshold,
                gain_requires_long_term=gain_requires_long_term,
                now=now,
            )
        )
    except ValueError as exc:
        raise SleeveReportError(f"snapshot position value is not usable: {exc}") from exc
    try:
        dividend_income = _dividend_income(journal_postings)
    except SleeveReportError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise SleeveReportError(
            f"journal dividend income is not usable: {exc}"
        ) from exc

    return {
        "as_of": snapshot.as_of,
        "portfolio_source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "total_equity": _money(total_equity),
        "engine": {
            "plan": "docs/Plan/THREE_SLEEVE_ENGINE_PLAN.md",
            "authority": (
                "owner-stated preference (2026-08-09, revision 2); "
                "not validated research"
            ),
            "floor_pct": decimal_text(floor),
            "gain_review_threshold_pct": decimal_text(gain_threshold),
            "gain_review_requires_long_term": gain_requires_long_term,
            "gain_review_trim_fraction": gain_trim_fraction,
            "decline_review_threshold_pct": decimal_text(decline_threshold),
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
            "lots_awaiting_long_term": awaiting_lt,
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
        "dividend_income": dividend_income,
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
