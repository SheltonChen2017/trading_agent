"""
Tax-lot ledger: per-lot cost basis, realized P&L, and holding-period
classification.

WHY THIS EXISTS
---------------
The portfolio snapshot reports ONE average cost per ticker
(`context_builder.build_portfolio_snapshot` computes `cost / shares`), which is
the standard broker display convention and matches what Alpaca reports as
`avg_entry_price`. It is also lossy in a way that hides real money. Buying
2 shares at 100 and 2 more at 90, then seeing the price at 95, shows as
"4 shares, average 95, unrealized 0.00%" -- looks like nothing happened, while
in fact you hold a harvestable 10 dollar loss and a 10 dollar short-term gain
at the same time, and which one you realize depends entirely on which lot you
sell. Average cost cannot represent that difference at all.

This module keeps the lots separate so it can.

NOT TAX ADVICE. This is deterministic bookkeeping over your own fills. It
computes holding periods from dates and flags possible wash sales; it does not
adjust cost basis for them, does not decide what counts as "substantially
identical", and does not know about your other accounts, options positions,
dividend reinvestment, unconfirmed corporate actions, or which basis method you have
actually elected with your broker. Your broker's 1099-B is authoritative for
filing. Use this to understand the shape of a decision before making it, and
to see numbers the average-cost view structurally cannot show.

DESIGN
------
Pure functions over a list of `Fill`s. No storage, no broker, no network -- so
the same code serves the app's own journaled fills (`AssistantStore.list_fills()`
reads them out of `broker_order_events`) and, later, an importer for fills that
predate the app or were placed elsewhere. Positions acquired outside the app
have no fills recorded and therefore no lots; `build_ledger` reports what it
covered rather than silently presenting a partial ledger as complete.

Every quantity and price is validated as finite and positive before use. A
non-finite value must never enter this arithmetic: it would propagate through
every sum and defeat the ordered comparisons that pick lots (this project has
hit that bug class repeatedly -- see risk/execution_gate.py's notes).
"""
from __future__ import annotations

import dataclasses
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from assistant.money import to_decimal

# The single timezone every date-valued tax judgement is made in. A holding
# period is a rule about TRADE DATES, and for US equities the trade date is the
# exchange-local one -- so the boundary has to be evaluated in the same zone the
# report prints its dates in and assigns its tax year in. `tax_reporting`
# imports this rather than defining its own, so the printed date and the
# long/short classification cannot drift apart (FCS-016: they had, and the
# exported row could read "acquired 2025-03-10, sold 2026-03-10, LONG-TERM").
MARKET_TIMEZONE = ZoneInfo("America/New_York")

# Selection methods. "specific" requires the caller to name lot ids.
FIFO = "fifo"          # oldest first -- the US default when you elect nothing
LIFO = "lifo"          # newest first
HIFO = "hifo"          # highest cost first: minimizes realized gain
SPECIFIC = "specific"  # caller names the lots
SELECTION_METHODS = (FIFO, LIFO, HIFO, SPECIFIC)

# A loss where the same ticker was bought within this window either side of the
# sale is FLAGGED as a possible wash sale. Never adjusted -- see module docstring.
WASH_SALE_WINDOW_DAYS = 30


class TaxLotError(ValueError):
    """Malformed fill data, or a sale that cannot be satisfied from open lots."""


def _decimal_sum(values) -> float:
    """Sum an iterable of money floats through Decimal, return a float.

    Independent review, 2026-07-31 (P2 #4): summing many lots'/components'
    dollar figures as plain binary floats can drift by float epsilon from
    the ledger's exact Decimal figures. Only used at aggregation points --
    single-operation per-lot arithmetic (one multiply/subtract) already has
    negligible error and doesn't need this."""
    return float(sum((to_decimal(v) for v in values), Decimal("0")))


@dataclasses.dataclass(frozen=True)
class Fill:
    """One executed trade. `at` must be timezone-aware."""

    ticker: str
    side: str  # "buy" | "sell"
    qty: float
    price: float
    at: datetime
    fill_id: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise TaxLotError(f"side must be 'buy' or 'sell', got {self.side!r}")
        for field, value in (("qty", self.qty), ("price", self.price)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TaxLotError(f"{field} must be a number, got {value!r}")
            if not math.isfinite(value) or value <= 0:
                raise TaxLotError(
                    f"{field} must be positive and finite, got {value!r} -- refusing to "
                    "build a lot ledger from corrupt fill data"
                )
        if self.at.tzinfo is None:
            raise TaxLotError(f"Fill.at must be timezone-aware, got naive {self.at!r}")


@dataclasses.dataclass(frozen=True)
class Split:
    """A confirmed split expressed as the new-shares / old-shares ratio.

    A 4-for-1 split has ``ratio=4``; a 1-for-10 reverse split has
    ``ratio=0.1``. Fractional-share cash-in-lieu is a separate broker cash
    event and is deliberately not guessed here.
    """

    ticker: str
    ratio: float
    at: datetime
    action_id: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ratio, (int, float))
            or isinstance(self.ratio, bool)
            or not math.isfinite(self.ratio)
            or self.ratio <= 0
        ):
            raise TaxLotError(
                f"split ratio must be positive and finite, got {self.ratio!r}"
            )
        if self.at.tzinfo is None:
            raise TaxLotError(
                f"Split.at must be timezone-aware, got naive {self.at!r}"
            )


LotEvent = Fill | Split


@dataclasses.dataclass(frozen=True)
class OpenLot:
    lot_id: str
    ticker: str
    qty: float
    cost_per_share: float
    acquired_at: datetime

    @property
    def cost_basis(self) -> float:
        return self.qty * self.cost_per_share

    def market_value(self, price: float) -> float:
        return self.qty * price

    def unrealized_pnl(self, price: float) -> float:
        return self.market_value(price) - self.cost_basis

    def unrealized_pnl_pct(self, price: float) -> float:
        return (self.unrealized_pnl(price) / self.cost_basis * 100) if self.cost_basis else 0.0

    def is_long_term_if_sold(self, when: datetime) -> bool:
        return is_long_term(self.acquired_at, when)


@dataclasses.dataclass(frozen=True)
class RealizedComponent:
    """One lot (or part of one) consumed by one sale."""

    ticker: str
    lot_id: str
    qty: float
    cost_per_share: float
    proceeds_per_share: float
    acquired_at: datetime
    sold_at: datetime
    long_term: bool
    wash_sale_suspected: bool = False

    @property
    def cost_basis(self) -> float:
        return self.qty * self.cost_per_share

    @property
    def proceeds(self) -> float:
        return self.qty * self.proceeds_per_share

    @property
    def realized_pnl(self) -> float:
        return self.proceeds - self.cost_basis


@dataclasses.dataclass(frozen=True)
class LotLedger:
    open_lots: tuple[OpenLot, ...]
    realized: tuple[RealizedComponent, ...]
    method: str

    def open_for(self, ticker: str) -> tuple[OpenLot, ...]:
        upper = ticker.upper()
        return tuple(lot for lot in self.open_lots if lot.ticker == upper)

    def shares_held(self, ticker: str) -> float:
        return sum(lot.qty for lot in self.open_for(ticker))

    def average_cost(self, ticker: str) -> float:
        """The single number the portfolio snapshot shows, for comparison."""
        lots = self.open_for(ticker)
        shares = sum(lot.qty for lot in lots)
        if not shares:
            return 0.0
        return _decimal_sum(lot.cost_basis for lot in lots) / shares

    def realized_pnl(self, ticker: str | None = None, *, long_term: bool | None = None) -> float:
        rows = self.realized
        if ticker is not None:
            rows = tuple(r for r in rows if r.ticker == ticker.upper())
        if long_term is not None:
            rows = tuple(r for r in rows if r.long_term is long_term)
        return _decimal_sum(r.realized_pnl for r in rows)


def _market_date(value: datetime) -> date:
    """The exchange-local calendar date a timestamp belongs to."""
    return value.astimezone(MARKET_TIMEZONE).date()


def _one_year_on(acquired_at: datetime) -> date:
    """The last market-local DATE that is still short term.

    A sale on this date is exactly one year and therefore short; the position
    becomes long term on the following day. For a 29 February acquisition,
    the next year's 28 February is the last short-term date and 1 March is the
    first long-term date: the holding-period count starts on 1 March in the
    acquisition year and includes the disposition date (CXL-001).
    """
    # Derived from the day counting actually STARTS on, not from the
    # acquisition date. Pub 550: "begin counting on the date after the day you
    # acquired the property", and its worked example (buy 5 Feb, long term on
    # 6 Feb the next year) fixes the shape: the first long-term date is the
    # first anniversary of `acquired + 1 day`, and the last short-term date is
    # the day before that.
    #
    # CXL-001 corrected a 29-February ACQUISITION, which this reproduces. But
    # anchoring on the acquisition date left the mirror case wrong in the
    # opposite direction (CCX-001): buying 28 Feb 2023 put a 29 February
    # INSIDE the holding window, and `replace(year=+1)` made 29 Feb 2024 the
    # first long-term date when counting from 1 Mar 2023 reaches one year only
    # on 1 Mar 2024. That direction understates tax, on the same
    # accountant-facing export. Anchoring on the count's first day handles
    # both leap positions with one rule instead of two special cases.
    first_counted_day = _market_date(acquired_at) + timedelta(days=1)
    try:
        first_long_term = first_counted_day.replace(year=first_counted_day.year + 1)
    except ValueError:
        # Counting began on 29 February; the next year has no such date, so
        # the anniversary falls on 1 March.
        first_long_term = date(first_counted_day.year + 1, 3, 1)
    return first_long_term - timedelta(days=1)


def is_long_term(acquired_at: datetime, sold_at: datetime) -> bool:
    """
    True when the holding period exceeds one year.

    The US rule counts from the day AFTER acquisition, so a position bought
    2025-03-10 and sold exactly 2026-03-10 is still SHORT term; it becomes long
    term on 2026-03-11. Compared as the same calendar date one year later
    rather than as "> 365 days", so leap years do not shift the boundary.

    DATES, not timestamps, and market-local dates specifically (FCS-016). This
    compared full timestamps until 2026-08-07, which made an anniversary sale
    later in the day than the purchase long term -- contradicting the rule
    stated in the paragraph above. Comparing raw UTC dates is not enough
    either: `tax_reporting` prints `sold_at` and assigns the tax year in
    ``MARKET_TIMEZONE``, so a 00:30Z sale (the previous evening in New York)
    would still be classified against the wrong day and the exported row would
    contradict itself.
    """
    if sold_at <= acquired_at:
        return False
    return _market_date(sold_at) > _one_year_on(acquired_at)


def _sort_key_for(method: str):
    if method == FIFO:
        return lambda lot: (lot.acquired_at, lot.lot_id)
    if method == LIFO:
        return lambda lot: (_negated_time(lot.acquired_at), lot.lot_id)
    if method == HIFO:
        return lambda lot: (-lot.cost_per_share, lot.acquired_at, lot.lot_id)
    raise TaxLotError(f"no ordering defined for method {method!r}")


def _negated_time(value: datetime) -> float:
    return -value.timestamp()


def select_lots(
    open_lots: list[OpenLot],
    qty: float,
    *,
    method: str = FIFO,
    lot_ids: list[str] | None = None,
) -> list[tuple[OpenLot, float]]:
    """
    Choose which lots satisfy a sale of `qty` shares, returning
    `[(lot, qty_taken), ...]`.

    Refuses (rather than partially filling) when the open lots cannot cover the
    sale: an over-sale means the ledger is missing fills, and silently realizing
    less than was actually sold would understate a gain -- the wrong direction.
    """
    if method not in SELECTION_METHODS:
        raise TaxLotError(f"method must be one of {SELECTION_METHODS}, got {method!r}")
    if not math.isfinite(qty) or qty <= 0:
        raise TaxLotError(f"qty must be positive and finite, got {qty!r}")

    if method == SPECIFIC:
        if not lot_ids:
            raise TaxLotError("method='specific' requires lot_ids")
        by_id = {lot.lot_id: lot for lot in open_lots}
        missing = [lid for lid in lot_ids if lid not in by_id]
        if missing:
            raise TaxLotError(f"unknown lot id(s): {missing}")
        ordered = [by_id[lid] for lid in lot_ids]
    else:
        ordered = sorted(open_lots, key=_sort_key_for(method))

    available = sum(lot.qty for lot in ordered)
    if available + 1e-9 < qty:
        raise TaxLotError(
            f"cannot sell {qty} shares: only {available} available in the selected lots. "
            "The lot ledger is incomplete (fills placed outside this app are not recorded)."
        )

    taken: list[tuple[OpenLot, float]] = []
    remaining = qty
    for lot in ordered:
        if remaining <= 1e-9:
            break
        take = min(lot.qty, remaining)
        taken.append((lot, take))
        remaining -= take
    return taken


def build_ledger(
    fills: list[LotEvent],
    *,
    method: str = FIFO,
    specific_lot_ids: dict[str, list[str]] | None = None,
) -> LotLedger:
    """
    Replay fills and confirmed splits in chronological order into open lots
    plus realized components.

    Deterministic and idempotent: the same fills always produce the same
    ledger, which is why lots are derived from the append-only
    `broker_order_events` journal rather than maintained as separate mutable
    state. There is no second source of truth to drift.

    `specific_lot_ids` maps a sell fill's `fill_id` to the lots it should
    consume, for `method='specific'`.
    """
    if method not in SELECTION_METHODS:
        raise TaxLotError(f"method must be one of {SELECTION_METHODS}, got {method!r}")

    open_lots: list[OpenLot] = []
    realized: list[RealizedComponent] = []
    counter = 0
    used_lot_ids: set[str] = set()
    buy_events: list[tuple[Fill, str]] = []

    for fill in sorted(
        fills,
        key=lambda event: (
            event.at,
            event.fill_id if isinstance(event, Fill) else event.action_id,
        ),
    ):
        ticker = fill.ticker.upper()
        if isinstance(fill, Split):
            open_lots = [
                (
                    dataclasses.replace(
                        lot,
                        qty=lot.qty * fill.ratio,
                        cost_per_share=lot.cost_per_share / fill.ratio,
                    )
                    if lot.ticker == ticker
                    else lot
                )
                for lot in open_lots
            ]
            continue
        if fill.side == "buy":
            counter += 1
            base_lot_id = (
                str(fill.fill_id).strip() if fill.fill_id else f"lot-{counter}"
            )
            lot_id = base_lot_id
            duplicate_number = 2
            while lot_id in used_lot_ids:
                lot_id = f"{base_lot_id}#{duplicate_number}"
                duplicate_number += 1
            used_lot_ids.add(lot_id)
            buy_events.append((fill, lot_id))
            open_lots.append(
                OpenLot(
                    lot_id=lot_id,
                    ticker=ticker,
                    qty=fill.qty,
                    cost_per_share=fill.price,
                    acquired_at=fill.at,
                )
            )
            continue

        candidates = [lot for lot in open_lots if lot.ticker == ticker]
        chosen = select_lots(
            candidates,
            fill.qty,
            method=method,
            lot_ids=(specific_lot_ids or {}).get(fill.fill_id) if method == SPECIFIC else None,
        )
        for lot, take in chosen:
            realized.append(
                RealizedComponent(
                    ticker=ticker,
                    lot_id=lot.lot_id,
                    qty=take,
                    cost_per_share=lot.cost_per_share,
                    proceeds_per_share=fill.price,
                    acquired_at=lot.acquired_at,
                    sold_at=fill.at,
                    long_term=is_long_term(lot.acquired_at, fill.at),
                )
            )
            remaining = lot.qty - take
            index = open_lots.index(lot)
            if remaining <= 1e-9:
                open_lots.pop(index)
            else:
                open_lots[index] = dataclasses.replace(lot, qty=remaining)

    realized = _flag_wash_sales(realized, buy_events)
    return LotLedger(tuple(open_lots), tuple(realized), method)


def _flag_wash_sales(
    realized: list[RealizedComponent], buys: list[tuple[Fill, str]]
) -> tuple[RealizedComponent, ...]:
    """
    Mark realized LOSSES that have a purchase of the same ticker within
    +/- WASH_SALE_WINDOW_DAYS.

    Flag only. Basis is never adjusted: the real rule turns on "substantially
    identical" securities across ALL of your accounts (including a spouse's and
    any IRA), which this module cannot see and should not guess at. A flag says
    "check this one", not "this is disallowed".
    """
    # A purchase only counts as a REPLACEMENT if it is not itself among the
    # shares this sale disposed of. Without that exclusion the original
    # purchase flagged its own loss sale: buy at 100, sell at 90 a day later
    # and the day-old buy sits inside the +/-30 day window, so every
    # short-term loss looked like a wash sale. You cannot replace a position
    # with the very shares you just sold. (Found by this module's own
    # negative-case test, not by review.)
    consumed_lot_ids_by_sale: dict[tuple[str, datetime], set[str]] = {}
    for component in realized:
        consumed_lot_ids_by_sale.setdefault(
            (component.ticker, component.sold_at), set()
        ).add(component.lot_id)

    buys_by_ticker: dict[str, list[tuple[datetime, str]]] = {}
    for fill, lot_id in buys:
        buys_by_ticker.setdefault(fill.ticker.upper(), []).append((fill.at, lot_id))

    window = timedelta(days=WASH_SALE_WINDOW_DAYS)
    flagged = []
    for component in realized:
        suspect = False
        if component.realized_pnl < 0:
            disposed = consumed_lot_ids_by_sale.get(
                (component.ticker, component.sold_at), set()
            )
            suspect = any(
                abs(buy_at - component.sold_at) <= window and buy_id not in disposed
                for buy_at, buy_id in buys_by_ticker.get(component.ticker, ())
            )
        flagged.append(dataclasses.replace(component, wash_sale_suspected=suspect))
    return tuple(flagged)


def compare_sale_bases(
    ledger: LotLedger, ticker: str, qty: float, price: float, *, when: datetime | None = None
) -> dict:
    """
    What selling `qty` shares at `price` would realize under each method --
    the comparison the average-cost view cannot show.

    This is the whole point of the module in one call: same trade, same price,
    materially different realized results and tax character depending only on
    which lots you choose.
    """
    when = when or datetime.now(timezone.utc)
    for field, value in (("qty", qty), ("price", price)):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise TaxLotError(
                f"{field} must be positive and finite, got {value!r}"
            )
    if when.tzinfo is None:
        raise TaxLotError("when must be timezone-aware")
    lots = list(ledger.open_for(ticker))
    average_cost = ledger.average_cost(ticker)
    shares_held = ledger.shares_held(ticker)

    result: dict = {
        "ticker": ticker.upper(),
        "qty": qty,
        "price": price,
        "as_of": when.isoformat(),
        "shares_held": shares_held,
        "methods": {},
    }

    # An uncovered ticker must NOT get an average-cost view. average_cost()
    # returns 0.0 when no lots are known, so the naive view reported a cost
    # basis of zero and therefore the entire proceeds as gain -- a $2,000
    # "realized gain" on a position whose basis is simply unknown (found
    # 2026-07-30 reviewing this feature). For a TAX figure that is the worst
    # direction to be wrong in: it overstates the bill and can talk a user out
    # of a risk-reducing sell. Report the gap instead of a fabricated number.
    if shares_held < qty:
        result["average_cost_view"] = {
            "available": False,
            "reason": (
                (
                    "no lots are recorded for this ticker, so its cost basis "
                    "is unknown -- not zero"
                )
                if shares_held <= 0
                else (
                    f"recorded lots cover only {shares_held} of the {qty} "
                    "shares in this sale; applying that partial average basis "
                    "to every share would fabricate the uncovered basis"
                )
            ),
            **(
                {"covers_only_shares": shares_held}
                if shares_held > 0
                else {}
            ),
        }
    else:
        result["average_cost_view"] = {
            "available": True,
            "cost_per_share": round(average_cost, 4),
            "realized_pnl": round((price - average_cost) * qty, 2),
            "note": "what the average-cost display implies; not a lot-level tax result",
        }
    for method in (FIFO, LIFO, HIFO):
        try:
            chosen = select_lots(lots, qty, method=method)
        except TaxLotError as exc:
            result["methods"][method] = {"error": str(exc)}
            continue
        components = [
            RealizedComponent(
                ticker=ticker.upper(), lot_id=lot.lot_id, qty=take,
                cost_per_share=lot.cost_per_share, proceeds_per_share=price,
                acquired_at=lot.acquired_at, sold_at=when,
                long_term=is_long_term(lot.acquired_at, when),
            )
            for lot, take in chosen
        ]
        result["methods"][method] = {
            "realized_pnl": round(_decimal_sum(c.realized_pnl for c in components), 2),
            "short_term_pnl": round(
                _decimal_sum(c.realized_pnl for c in components if not c.long_term), 2
            ),
            "long_term_pnl": round(
                _decimal_sum(c.realized_pnl for c in components if c.long_term), 2
            ),
            "lots": [
                {"lot_id": c.lot_id, "qty": c.qty, "cost_per_share": c.cost_per_share,
                 "realized_pnl": round(c.realized_pnl, 2),
                 "term": "long" if c.long_term else "short"}
                for c in components
            ],
        }
    # "Available" means at least one method actually produced figures. Callers
    # branch on this to decide between showing a table and explaining why there
    # is none; when every method errored, both the CLI and the UI rendered an
    # EMPTY result rather than the "advisory unavailable" message, so a missing
    # lot history looked identical to "no tax implications" (found 2026-07-30).
    usable = [m for m, detail in result["methods"].items() if "error" not in detail]
    result["available"] = bool(usable)
    if not usable:
        first_error = next(
            (detail.get("error") for detail in result["methods"].values() if "error" in detail),
            "no lot-level result could be computed",
        )
        result["reason"] = first_error
    return result


def unrealized_by_lot(ledger: LotLedger, ticker: str, price: float) -> list[dict]:
    """Per-lot unrealized P&L -- what average cost averages away."""
    if not math.isfinite(price) or price <= 0:
        raise TaxLotError(f"price must be positive and finite, got {price!r}")
    now = datetime.now(timezone.utc)
    return [
        {
            "lot_id": lot.lot_id,
            "qty": lot.qty,
            "cost_per_share": lot.cost_per_share,
            "acquired_at": lot.acquired_at.isoformat(),
            "unrealized_pnl": round(lot.unrealized_pnl(price), 2),
            "unrealized_pnl_pct": round(lot.unrealized_pnl_pct(price), 2),
            "term_if_sold_now": "long" if lot.is_long_term_if_sold(now) else "short",
            "days_to_long_term": max(
                0, (_long_term_date(lot.acquired_at) - now).days
            ) if not lot.is_long_term_if_sold(now) else 0,
            "first_long_term_date": _long_term_date(lot.acquired_at).date().isoformat(),
        }
        for lot in ledger.open_for(ticker)
    ]


def _long_term_date(acquired_at: datetime) -> datetime:
    """First instant the lot is long term: market-local midnight the day after
    the last short-term date.

    Derived from ``_one_year_on`` so the countdown and ``is_long_term`` cannot
    disagree. They did until 2026-08-07: this used ``replace(year=+1) + 1 day``
    against a timestamp while the classifier compared ``replace(year=+1)``, so
    the countdown could report "1 day to go" for a lot already called long.
    """
    first_long_day = _one_year_on(acquired_at) + timedelta(days=1)
    return datetime.combine(
        first_long_day, datetime.min.time(), tzinfo=MARKET_TIMEZONE
    )
