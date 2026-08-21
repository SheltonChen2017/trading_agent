"""Frozen experiment (2026-08-09): the three-sleeve engine's ORIGINAL
growth-rotation rule (+5% any-term full exit / -10% add) vs buy-and-hold.

NOT a research finding -- descriptive evidence for the owner's question
"would this strategy work?", produced BEFORE M2 encoded any threshold.
Its result (rule 3.29% modeled after-tax proxy CAGR vs 48.14% buy-and-hold;
95-99% of
days in cash) drove the section-1.1 revision recorded in
docs/Plan/THREE_SLEEVE_ENGINE_PLAN.md and the rejected-status entry
in assistant/research_findings.json. Run from the repository root; do not
re-scope this window -- a new question is a new dated script.

THE RULE (docs/Plan/THREE_SLEEVE_ENGINE_PLAN.md, owner-adopted):
  - per-LOT basis, never average cost;
  - a lot's close >= 1.05 x its basis  -> sell that lot (gain review);
  - a lot's close <= 0.90 x its basis  -> buy an additional unit (decline
    review), at most ONE add triggered per lot, adds can cascade because
    each new lot carries its own thresholds;
  - after going flat, re-enter one unit when close <= 0.90 x the last
    disposal fill price (resolved decision #3).

REALISM CHOICES (project standards, stated not hidden):
  - signals on daily CLOSE, fills at NEXT day's OPEN (entry_timing =
    next_open -- the timing fix that flipped a prior project finding);
  - prices are yfinance auto_adjust=True, so dividends are folded into
    price for BOTH strategies (approximate total return). Consequently the
    tax result is only a MODELED PROXY: dividend adjustments enter price
    gains, while real dividend tax timing/classification is not modeled;
  - per-ticker bankroll of MAX_UNITS x UNIT dollars; undeployed cash earns
    CASH_YIELD (flat approximation, sensitivity at 0%);
  - annual tax netting with loss carryforward: short-term net gains 37%,
    long-term (approximated here as held > 365 days) 15%; terminal liquidation at the final
    close taxed the same way. Buy-and-hold pays its single long-term tax
    at that same terminal liquidation. The >365 shortcut can disagree with
    the app's calendar- and leap-day-correct tax-lot authority at boundaries;
  - no commissions (Alpaca); no bid/ask spread model (noted caveat).

WHAT THIS IS NOT: not purged/walk-forward research, not a multiplicity-
corrected significance claim, and threshold variants below are an
UNCOUNTED grid -- picking the best cell after seeing results is a look.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


import pandas as pd

from data.market_data import fetch_historical

TICKERS = ["NVDA", "AMD", "AVGO", "TSM", "MSFT", "SOXX"]
REFERENCE = ["SPY"]
LOOKBACK_DAYS = 1764  # ~7 trading years, the project's standard window

UNIT = 10_000.0
MAX_UNITS = 5           # finite adds: the martingale cannot deepen forever
ST_TAX = 0.37
LT_TAX = 0.15
CASH_YIELD = 0.03       # flat approximation; 0% sensitivity reported too
TRADING_DAYS = 252

OUT = Path.cwd() / (Path(__file__).stem + ".results.json")


@dataclass
class Lot:
    shares: float
    basis: float          # fill price per share
    acquired_i: int       # bar index of the fill
    add_triggered: bool = False


@dataclass
class TaxYearBook:
    st: float = 0.0
    lt: float = 0.0


def _tax_due(st_net: float, lt_net: float, carry: float) -> tuple[float, float]:
    """Annual netting: apply carried loss, offset across categories, tax
    positives. Returns (tax, new_carryforward<=0)."""
    st = st_net
    lt = lt_net + carry           # carried losses land on LT first (simplification)
    if st < 0 and lt > 0:
        move = min(-st, lt); st += move; lt -= move
    if lt < 0 and st > 0:
        move = min(-lt, st); lt += move; st -= move
    tax = ST_TAX * max(0.0, st) + LT_TAX * max(0.0, lt)
    carry_out = min(0.0, st) + min(0.0, lt)
    return tax, carry_out


def simulate_rule(df: pd.DataFrame, gain_pct: float, decline_pct: float,
                  cash_yield: float) -> dict:
    """One ticker, one parameter pair. Returns summary stats."""
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    years = df.index.year.to_numpy()
    n = len(df)

    bankroll = MAX_UNITS * UNIT
    cash = bankroll
    lots: list[Lot] = []
    # Symmetric start with buy-and-hold: one unit at the FIRST open, no
    # signal needed -- both strategies begin at the same bar and price.
    lots.append(Lot(shares=UNIT / opens[0], basis=float(opens[0]), acquired_i=0))
    cash -= UNIT
    last_disposal: float | None = None
    carry = 0.0
    books: dict[int, TaxYearBook] = {}
    daily_yield = (1.0 + cash_yield) ** (1.0 / TRADING_DAYS) - 1.0

    trades = buys = sells = 0
    invested_days = 0
    cap_bound_days = 0
    tax_paid = 0.0
    st_realized = lt_realized = 0.0
    equity_curve = []

    # Orders decided on close[t], filled at open[t+1].
    pending_sells: list[Lot] = []
    pending_buys = 0
    pending_reentry = False

    def deployed_units() -> int:
        return round(sum(l.shares * l.basis for l in lots) / UNIT)

    for t in range(n):
        price_open, price_close, year = opens[t], closes[t], years[t]

        # --- fills from yesterday's signals, at today's open --------------
        for lot in pending_sells:
            proceeds = lot.shares * price_open
            gain = proceeds - lot.shares * lot.basis
            held_days_cal = (df.index[t] - df.index[lot.acquired_i]).days
            book = books.setdefault(year, TaxYearBook())
            if held_days_cal > 365:
                book.lt += gain;
            else:
                book.st += gain
            if held_days_cal > 365:
                lt_realized += gain
            else:
                st_realized += gain
            cash += proceeds
            lots.remove(lot)
            last_disposal = price_open
            sells += 1; trades += 1
        pending_sells = []
        for _ in range(pending_buys):
            if cash >= UNIT and (sum(l.shares * l.basis for l in lots) + UNIT) <= MAX_UNITS * UNIT + 1e-6:
                lots.append(Lot(shares=UNIT / price_open, basis=price_open, acquired_i=t))
                cash -= UNIT
                buys += 1; trades += 1
        pending_buys = 0
        if pending_reentry and not lots and cash >= UNIT:
            lots.append(Lot(shares=UNIT / price_open, basis=price_open, acquired_i=t))
            cash -= UNIT
            buys += 1; trades += 1
        pending_reentry = False

        # --- cash yield ---------------------------------------------------
        cash *= (1.0 + daily_yield)

        # --- signals on today's close ------------------------------------
        for lot in lots:
            if price_close >= lot.basis * (1.0 + gain_pct / 100.0):
                pending_sells.append(lot)
            elif (not lot.add_triggered
                  and price_close <= lot.basis * (1.0 + decline_pct / 100.0)):
                lot.add_triggered = True
                pending_buys += 1
        if not lots and last_disposal is not None and price_close <= 0.90 * last_disposal:
            pending_reentry = True

        # cap accounting
        if lots:
            invested_days += 1
        if deployed_units() >= MAX_UNITS:
            cap_bound_days += 1

        # --- year-end tax (approximated on last bar of each year) --------
        if t + 1 < n and years[t + 1] != year:
            book = books.pop(year, TaxYearBook())
            tax, carry = _tax_due(book.st, book.lt, carry)
            cash -= tax
            tax_paid += tax

        equity_curve.append(cash + sum(l.shares * price_close for l in lots))

    # --- terminal liquidation at the final close -------------------------
    final_close = closes[-1]
    final_year = years[-1]
    book = books.pop(final_year, TaxYearBook())
    for lot in lots:
        gain = lot.shares * (final_close - lot.basis)
        held = (df.index[-1] - df.index[lot.acquired_i]).days
        if held > 365:
            book.lt += gain; lt_realized += gain
        else:
            book.st += gain; st_realized += gain
        cash += lot.shares * final_close
        sells += 1; trades += 1
    tax, carry = _tax_due(book.st, book.lt, carry)
    cash -= tax
    tax_paid += tax
    lots = []

    curve = pd.Series(equity_curve, index=df.index)
    running_max = curve.cummax()
    max_dd = float(((curve - running_max) / running_max).min() * 100.0)
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = ((cash / bankroll) ** (1.0 / n_years) - 1.0) * 100.0

    return {
        "end_wealth_after_tax": round(cash, 2),
        "cagr_after_tax_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trades": trades,
        "sells": sells,
        "pct_days_any_lot_open": round(100.0 * invested_days / n, 1),
        "pct_days_at_unit_cap": round(100.0 * cap_bound_days / n, 1),
        "tax_paid": round(tax_paid, 2),
        "st_realized": round(st_realized, 2),
        "lt_realized": round(lt_realized, 2),
    }


def simulate_buy_hold(df: pd.DataFrame) -> dict:
    """Same bankroll, all-in at the first open, liquidated at final close,
    single long-term tax at the end."""
    bankroll = MAX_UNITS * UNIT
    entry = float(df["open"].iloc[0])
    shares = bankroll / entry
    curve = shares * df["close"]
    final = float(curve.iloc[-1])
    gain = final - bankroll
    tax = LT_TAX * max(0.0, gain)
    end = final - tax
    running_max = curve.cummax()
    max_dd = float(((curve - running_max) / running_max).min() * 100.0)
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = ((end / bankroll) ** (1.0 / n_years) - 1.0) * 100.0
    return {
        "end_wealth_after_tax": round(end, 2),
        "cagr_after_tax_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "tax_paid": round(tax, 2),
    }


def main() -> None:
    data = fetch_historical(TICKERS + REFERENCE, lookback_days=LOOKBACK_DAYS)
    report: dict = {"depth": {}, "primary": {}, "variants": {}, "start_year_sensitivity": {},
                    "cash_yield_zero": {}, "buy_hold": {}, "aggregate": {}}
    for t in TICKERS + REFERENCE:
        df = data.get(t)
        report["depth"][t] = 0 if df is None else len(df)
        if df is None or len(df) < 500:
            print(f"FATAL: {t} has insufficient real history", file=sys.stderr)
            raise SystemExit(2)

    # primary: +5 / -10, cash 3%
    agg_rule = agg_bh = 0.0
    for t in TICKERS:
        df = data[t]
        rule = simulate_rule(df, 5.0, -10.0, CASH_YIELD)
        bh = simulate_buy_hold(df)
        report["primary"][t] = rule
        report["buy_hold"][t] = bh
        agg_rule += rule["end_wealth_after_tax"]
        agg_bh += bh["end_wealth_after_tax"]
    report["buy_hold"]["SPY_reference"] = simulate_buy_hold(data["SPY"])
    bank_total = MAX_UNITS * UNIT * len(TICKERS)
    n_years = (data["NVDA"].index[-1] - data["NVDA"].index[0]).days / 365.25
    report["aggregate"] = {
        "bankroll": bank_total,
        "years": round(n_years, 2),
        "rule_end_wealth": round(agg_rule, 2),
        "buy_hold_end_wealth": round(agg_bh, 2),
        "rule_cagr_pct": round(((agg_rule / bank_total) ** (1 / n_years) - 1) * 100, 2),
        "buy_hold_cagr_pct": round(((agg_bh / bank_total) ** (1 / n_years) - 1) * 100, 2),
    }

    # threshold variants (UNCOUNTED grid -- descriptive only)
    for gain in (5.0, 10.0, 20.0):
        for decline in (-10.0, -15.0):
            key = f"gain+{gain:g}/decline{decline:g}"
            total = 0.0
            for t in TICKERS:
                total += simulate_rule(data[t], gain, decline, CASH_YIELD)[
                    "end_wealth_after_tax"]
            report["variants"][key] = {
                "end_wealth": round(total, 2),
                "cagr_pct": round(((total / bank_total) ** (1 / n_years) - 1) * 100, 2),
            }

    # cash-yield sensitivity at the primary thresholds
    total = 0.0
    for t in TICKERS:
        total += simulate_rule(data[t], 5.0, -10.0, 0.0)["end_wealth_after_tax"]
    report["cash_yield_zero"] = {
        "end_wealth": round(total, 2),
        "cagr_pct": round(((total / bank_total) ** (1 / n_years) - 1) * 100, 2),
    }

    # start-year sensitivity (primary thresholds): later entry points
    for start_year in (2020, 2021, 2022, 2023, 2024):
        rule_total = bh_total = 0.0
        for t in TICKERS:
            df = data[t]
            sub = df[df.index.year >= start_year]
            if len(sub) < 200:
                continue
            rule_total += simulate_rule(sub, 5.0, -10.0, CASH_YIELD)["end_wealth_after_tax"]
            bh_total += simulate_buy_hold(sub)["end_wealth_after_tax"]
        yrs = (data["NVDA"].index[-1] - data["NVDA"][data["NVDA"].index.year >= start_year].index[0]).days / 365.25
        report["start_year_sensitivity"][str(start_year)] = {
            "rule_end_wealth": round(rule_total, 2),
            "buy_hold_end_wealth": round(bh_total, 2),
            "rule_cagr_pct": round(((rule_total / bank_total) ** (1 / yrs) - 1) * 100, 2),
            "buy_hold_cagr_pct": round(((bh_total / bank_total) ** (1 / yrs) - 1) * 100, 2),
        }

    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
