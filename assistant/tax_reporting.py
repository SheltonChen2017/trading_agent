"""GR-7a: annual realized-gain reporting from the confirmed tax-lot ledger.

This module is a REPORTING layer. Every number it prints is produced by
`assistant/tax_lots.py`'s already-tested lot machinery (lot selection,
holding-period classification, wash-sale flagging) replayed over the
append-only journal's fills plus journal-CONFIRMED corporate actions --
the same construction `assistant/corporate_actions.py` uses for proposal
previews. Nothing here re-derives a basis, a holding period, or a wash
sale; if this file and `tax_lots.py` ever disagree, `tax_lots.py` is
right and this file is the bug.

Three honesty rules the export exists to satisfy:

  * **Coverage is part of the artifact, not a console aside.** A report
    built from incomplete fill history is the dangerous case (an
    accountant reads the file, not the terminal), so coverage status and
    its per-ticker evidence are embedded in both the JSON and the CSV,
    and an incomplete report says so on its first line.
  * **Wash-sale entries are flags, never adjustments.** The real rule
    turns on "substantially identical" securities across every account
    the taxpayer controls, which this project cannot see. Basis is never
    modified; the report says "check this one".
  * **The tax year is a market-timezone calendar year.** A sale at
    2026-01-01T02:00Z happened 2025-12-31 21:00 in New York and belongs
    to tax year 2025. Bucketing on the raw UTC date would silently move
    late-December sales into the wrong year.

This is not tax advice, and it is not a substitute for broker 1099-B
forms; it is a reconciliation aid built from this app's own records.
"""
from __future__ import annotations

import csv
import dataclasses
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from assistant.corporate_actions import fills_with_confirmed_splits
from assistant.money import decimal_text, to_decimal
from assistant.storage import AssistantStore
from assistant.tax_lots import LotLedger, RealizedComponent, TaxLotError, build_ledger

# US tax years are calendar years in the taxpayer's local time; this
# project's trading clock is the US market's, so sales are bucketed in
# Eastern time rather than UTC (see the module docstring).
TAX_YEAR_TIMEZONE = ZoneInfo("America/New_York")

SHORT_TERM = "short"
LONG_TERM = "long"

DISCLAIMERS: tuple[str, ...] = (
    "Built from this application's own recorded fills and journal-confirmed "
    "corporate actions only. It is a reconciliation aid, NOT tax advice and "
    "NOT a substitute for your broker's 1099-B.",
    "Wash-sale entries are ADVISORY FLAGS. Cost basis is never adjusted "
    "here: the rule depends on substantially identical securities across "
    "every account you control (including a spouse's and any IRA), which "
    "this application cannot see.",
    "Realized amounts exclude commissions and fees unless those were "
    "recorded as journal postings.",
    f"Sales are assigned to a tax year in {TAX_YEAR_TIMEZONE.key} local time.",
)

_CSV_COLUMNS = (
    "ticker",
    "lot_id",
    "quantity",
    "acquired_at",
    "sold_at",
    "holding_period",
    "cost_basis",
    "proceeds",
    "realized_pnl",
    "wash_sale_suspected",
)


class TaxReportError(ValueError):
    """The requested report cannot be built from the recorded evidence."""


@dataclasses.dataclass(frozen=True)
class TaxReportRow:
    """One realized lot component, exactly as `tax_lots` computed it."""

    ticker: str
    lot_id: str
    quantity: Decimal
    acquired_at: str
    sold_at: str
    holding_period: str
    cost_basis: Decimal
    proceeds: Decimal
    realized_pnl: Decimal
    wash_sale_suspected: bool

    def to_dict(self) -> dict[str, Any]:
        # decimal_text: the project's canonical non-exponent money text, so
        # an exported figure reads the same way it is persisted everywhere
        # else (and never as a float or in scientific notation).
        return {
            "ticker": self.ticker,
            "lot_id": self.lot_id,
            "quantity": decimal_text(self.quantity),
            "acquired_at": self.acquired_at,
            "sold_at": self.sold_at,
            "holding_period": self.holding_period,
            "cost_basis": decimal_text(self.cost_basis),
            "proceeds": decimal_text(self.proceeds),
            "realized_pnl": decimal_text(self.realized_pnl),
            "wash_sale_suspected": self.wash_sale_suspected,
        }


@dataclasses.dataclass(frozen=True)
class TaxTotals:
    proceeds: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    sale_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "proceeds": decimal_text(self.proceeds),
            "cost_basis": decimal_text(self.cost_basis),
            "realized_pnl": decimal_text(self.realized_pnl),
            "sale_count": self.sale_count,
        }


@dataclasses.dataclass(frozen=True)
class AnnualTaxReport:
    tax_year: int
    generated_at: str
    lot_method: str
    rows: tuple[TaxReportRow, ...]
    short_term: TaxTotals
    long_term: TaxTotals
    total: TaxTotals
    wash_sale_flagged_count: int
    coverage: dict[str, Any]
    disclaimers: tuple[str, ...] = DISCLAIMERS

    @property
    def complete(self) -> bool:
        """True only when share coverage was VERIFIED complete.

        Unverified coverage (no portfolio snapshot supplied) is not
        completeness -- it is an unanswered question, and this property
        answers it conservatively.
        """
        return self.coverage.get("complete") is True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tax_year": self.tax_year,
            "generated_at": self.generated_at,
            "lot_method": self.lot_method,
            "complete": self.complete,
            "coverage": self.coverage,
            "short_term": self.short_term.to_dict(),
            "long_term": self.long_term.to_dict(),
            "total": self.total.to_dict(),
            "wash_sale_flagged_count": self.wash_sale_flagged_count,
            "rows": [row.to_dict() for row in self.rows],
            "disclaimers": list(self.disclaimers),
        }


def _validate_year(year: Any) -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        raise TaxReportError(f"tax year must be an integer, got {year!r}")
    if not 1900 <= year <= 2200:
        raise TaxReportError(f"tax year {year} is outside the supported range")
    return year


def _parse_at(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise TaxReportError(f"{field} must be timezone-aware, got {value!r}")
    return parsed


def tax_year_of(sold_at: datetime) -> int:
    """The tax year a sale falls in, in market-local time."""
    return _parse_at(sold_at, "sold_at").astimezone(TAX_YEAR_TIMEZONE).year


def _row_from_component(component: RealizedComponent) -> TaxReportRow:
    quantity = to_decimal(component.qty, name="component.qty")
    cost_basis = to_decimal(component.cost_basis, name="component.cost_basis")
    proceeds = to_decimal(component.proceeds, name="component.proceeds")
    return TaxReportRow(
        ticker=component.ticker,
        lot_id=component.lot_id,
        quantity=quantity,
        acquired_at=_parse_at(component.acquired_at, "acquired_at").isoformat(),
        sold_at=_parse_at(component.sold_at, "sold_at").isoformat(),
        holding_period=LONG_TERM if component.long_term else SHORT_TERM,
        cost_basis=cost_basis,
        proceeds=proceeds,
        # Recomputed from the exact decimal basis/proceeds rather than
        # converting the float `realized_pnl`, so the exported rows sum
        # to the exported totals with no rounding drift.
        realized_pnl=proceeds - cost_basis,
        wash_sale_suspected=bool(component.wash_sale_suspected),
    )


def _totals(rows: tuple[TaxReportRow, ...]) -> TaxTotals:
    proceeds = sum((row.proceeds for row in rows), Decimal("0"))
    cost_basis = sum((row.cost_basis for row in rows), Decimal("0"))
    return TaxTotals(
        proceeds=proceeds,
        cost_basis=cost_basis,
        realized_pnl=proceeds - cost_basis,
        sale_count=len(rows),
    )


def _coverage_report(ledger: LotLedger, portfolio: Any | None) -> dict[str, Any]:
    """Share-coverage verdict using the same comparison proposals use.

    Deliberately NOT reusing `tax_ledger_with_coverage()` itself: that
    helper returns `None` for the ledger when coverage is incomplete
    (correct for proposal generation, which must refuse), whereas a report
    must still be produced and labelled. The comparison rule below is the
    same one, and `tests/test_tax_reporting.py` pins that the two verdicts
    agree.
    """
    if portfolio is None:
        return {
            "complete": None,
            "verified": False,
            "reason": (
                "no portfolio snapshot supplied; share coverage was not "
                "verified against the broker"
            ),
            "tickers": {},
        }
    details: dict[str, dict[str, Any]] = {}
    complete = True
    portfolio_tickers = {p.ticker.upper() for p in portfolio.positions}
    lot_tickers = {lot.ticker for lot in ledger.open_lots}
    for ticker in sorted(portfolio_tickers | lot_tickers):
        broker_shares = sum(
            (
                to_decimal(p.shares, name=f"{ticker}.shares")
                for p in portfolio.positions
                if p.ticker.upper() == ticker
            ),
            Decimal("0"),
        )
        ledger_shares = to_decimal(
            ledger.shares_held(ticker), name=f"{ticker}.ledger_shares"
        )
        matched = abs(broker_shares - ledger_shares) <= Decimal("0.00000001")
        details[ticker] = {
            "broker_shares": str(broker_shares),
            "ledger_shares": str(ledger_shares),
            "matched": matched,
        }
        complete = complete and matched
    return {
        "complete": complete,
        "verified": True,
        "reason": (
            None
            if complete
            else (
                "tax-lot shares do not match the portfolio snapshot; realized "
                "history is missing fills and this report is INCOMPLETE"
            )
        ),
        "tickers": details,
    }


def build_annual_tax_report(
    store: AssistantStore,
    tax_year: int,
    *,
    portfolio: Any | None = None,
    now: datetime | None = None,
) -> AnnualTaxReport:
    """Realized gains for one tax year, from confirmed records only.

    `portfolio` is an optional `PortfolioSnapshot`. Supplying it lets the
    report VERIFY that the lot ledger accounts for every share the broker
    reports; omitting it leaves coverage explicitly unverified rather than
    assumed good.

    Raises `TaxReportError` when the ledger itself cannot be built (bad
    fill history, unbalanced splits) -- an unusable ledger must not
    produce a confident-looking empty report.
    """
    year = _validate_year(tax_year)
    generated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        ledger = build_ledger(fills_with_confirmed_splits(store))
    except (TaxLotError, ValueError, KeyError) as exc:
        raise TaxReportError(
            f"tax-lot ledger could not be built from recorded fills: {exc}"
        ) from exc

    rows = tuple(
        _row_from_component(component)
        for component in sorted(
            ledger.realized,
            key=lambda c: (c.sold_at, c.ticker, c.lot_id),
        )
        if tax_year_of(component.sold_at) == year
    )
    short_rows = tuple(row for row in rows if row.holding_period == SHORT_TERM)
    long_rows = tuple(row for row in rows if row.holding_period == LONG_TERM)
    return AnnualTaxReport(
        tax_year=year,
        generated_at=generated_at.isoformat(),
        lot_method=ledger.method,
        rows=rows,
        short_term=_totals(short_rows),
        long_term=_totals(long_rows),
        total=_totals(rows),
        wash_sale_flagged_count=sum(1 for row in rows if row.wash_sale_suspected),
        coverage=_coverage_report(ledger, portfolio),
    )


def render_tax_report_csv(report: AnnualTaxReport) -> str:
    """Accountant-readable CSV: banner, disclaimers, rows, then totals.

    The completeness banner is the FIRST line so the limitation cannot be
    missed by someone who opens the file and reads the table.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    if report.complete:
        status = "COMPLETE: recorded lots match the broker's share counts"
    elif report.coverage.get("verified"):
        status = (
            "INCOMPLETE: recorded lots do NOT match the broker's share counts "
            "-- realized history is missing fills"
        )
    else:
        status = (
            "COVERAGE UNVERIFIED: no portfolio snapshot was supplied, so this "
            "report was not checked against the broker's share counts"
        )
    writer.writerow([f"Realized gains and losses -- tax year {report.tax_year}"])
    writer.writerow([status])
    writer.writerow([f"Generated at {report.generated_at} (lot method: {report.lot_method})"])
    for disclaimer in report.disclaimers:
        writer.writerow([disclaimer])
    writer.writerow([])
    writer.writerow(_CSV_COLUMNS)
    for row in report.rows:
        writer.writerow(
            [
                row.ticker,
                row.lot_id,
                decimal_text(row.quantity),
                row.acquired_at,
                row.sold_at,
                row.holding_period,
                decimal_text(row.cost_basis),
                decimal_text(row.proceeds),
                decimal_text(row.realized_pnl),
                "yes" if row.wash_sale_suspected else "no",
            ]
        )
    writer.writerow([])
    for label, totals in (
        ("SHORT-TERM TOTAL", report.short_term),
        ("LONG-TERM TOTAL", report.long_term),
        ("TOTAL", report.total),
    ):
        writer.writerow(
            [
                label,
                "",
                "",
                "",
                "",
                "",
                decimal_text(totals.cost_basis),
                decimal_text(totals.proceeds),
                decimal_text(totals.realized_pnl),
                f"{totals.sale_count} sale row(s)",
            ]
        )
    writer.writerow([])
    writer.writerow(
        [f"Wash-sale FLAGGED rows (advisory, basis unadjusted): {report.wash_sale_flagged_count}"]
    )
    if report.coverage.get("tickers"):
        writer.writerow([])
        writer.writerow(["Share coverage check", "broker_shares", "ledger_shares", "matched"])
        for ticker, detail in sorted(report.coverage["tickers"].items()):
            writer.writerow(
                [
                    ticker,
                    detail["broker_shares"],
                    detail["ledger_shares"],
                    "yes" if detail["matched"] else "NO",
                ]
            )
    return buffer.getvalue()


def render_tax_report_json(report: AnnualTaxReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)
