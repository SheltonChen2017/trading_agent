"""Frozen experiment (2026-08-09): candidate revisions of the three-sleeve
growth-rotation rule, measured. Run from the repository root; results land
in ./backtest_three_sleeve_revisions_2026_08_09.results.json and the
adopted-revision summary is recorded in assistant/research_findings.json
and docs/reference/THREE_SLEEVE_ENGINE_PLAN.md section 1.1. Do not re-scope
this window; a new question is a new dated script.

Follow-up to backtest_three_sleeve_rule_2026_08_09.py after its finding: the +5%
full-exit leg alone costs ~32 CAGR points; the -10% dip-add leg is
harmless. Candidates below keep the owner's spirit (take profits, buy
dips, tax-aware) while repairing the structural stranding.

Same realism: next-open fills, 37%/15% annual tax netting with carryforward,
terminal liquidation taxed, 3% cash yield, dividend-adjusted prices, 5-unit
cap per ticker. Same names, same 7 years. Descriptive design guidance --
every number here is an uncounted look at hindsight-picked winners; the
chosen rule must be frozen and tested prospectively in the paper epoch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


import pandas as pd

from data.market_data import fetch_historical

TICKERS = ["NVDA", "AMD", "AVGO", "TSM", "MSFT", "SOXX"]
LOOKBACK_DAYS = 1764
UNIT = 10_000.0
MAX_UNITS = 5
ST_TAX = 0.37
LT_TAX = 0.15
CASH_YIELD = 0.03
TRADING_DAYS = 252

OUT = Path.cwd() / (Path(__file__).stem + ".results.json")


@dataclass
class Lot:
    shares: float
    basis: float
    acquired_i: int
    add_triggered: bool = False
    trimmed: bool = False


def _tax_due(st_net, lt_net, carry):
    st, lt = st_net, lt_net + carry
    if st < 0 and lt > 0:
        move = min(-st, lt); st += move; lt -= move
    if lt < 0 and st > 0:
        move = min(-lt, st); lt += move; st -= move
    return ST_TAX * max(0.0, st) + LT_TAX * max(0.0, lt), min(0.0, st) + min(0.0, lt)


def simulate(df: pd.DataFrame, *, exit_pct: float | None, exit_fraction: float,
             lt_gate: bool, decline_pct: float = -10.0,
             cash_yield: float = CASH_YIELD) -> dict:
    """Generalized per-lot rule.

    exit_pct=None      -> never a scheduled exit (accumulator).
    exit_fraction=0.5  -> trim half at the threshold (once per lot), keep rest.
    lt_gate=True       -> the exit/trim fires only once the lot is long-term,
                          so no scheduled sale can ever realize a short-term
                          gain (the tax mechanism made binding).
    Dip-adds and flat re-entry are unchanged from the adopted engine:
    one add per lot at decline_pct, cascade allowed, 5-unit cap; when flat,
    re-enter one unit at -10% from the last disposal fill.
    """
    opens = df["open"].to_numpy(); closes = df["close"].to_numpy()
    years = df.index.year.to_numpy(); n = len(df)
    bankroll = MAX_UNITS * UNIT
    cash = bankroll - UNIT
    lots = [Lot(UNIT / opens[0], float(opens[0]), 0)]
    last_disposal = None
    carry = 0.0
    books: dict[int, list[float]] = {}
    daily_yield = (1.0 + cash_yield) ** (1.0 / TRADING_DAYS) - 1.0
    trades = 0; invested_days = 0; tax_paid = 0.0
    st_realized = lt_realized = 0.0
    pending: list[tuple[str, Lot | None]] = []
    curve = []

    def realize(gain: float, held_days: int, year: int):
        nonlocal st_realized, lt_realized
        book = books.setdefault(year, [0.0, 0.0])
        if held_days > 365:
            book[1] += gain; lt_realized += gain
        else:
            book[0] += gain; st_realized += gain

    for t in range(n):
        po, pc, year = opens[t], closes[t], years[t]
        # --- fills at today's open from yesterday's close signals ---------
        for action, lot in pending:
            if action == "sell" and lot in lots:
                qty = lot.shares * exit_fraction
                realize(qty * (po - lot.basis), (df.index[t] - df.index[lot.acquired_i]).days, year)
                cash += qty * po
                if exit_fraction >= 1.0:
                    lots.remove(lot)
                else:
                    lot.shares -= qty
                    lot.trimmed = True
                last_disposal = po
                trades += 1
            elif action == "add":
                if cash >= UNIT and sum(l.shares * l.basis for l in lots) + UNIT <= MAX_UNITS * UNIT + 1e-6:
                    lots.append(Lot(UNIT / po, po, t)); cash -= UNIT; trades += 1
            elif action == "reenter" and not lots and cash >= UNIT:
                lots.append(Lot(UNIT / po, po, t)); cash -= UNIT; trades += 1
        pending = []
        cash *= (1.0 + daily_yield)

        # --- signals on today's close -------------------------------------
        for lot in lots:
            exit_ok = (
                exit_pct is not None
                and not lot.trimmed
                and pc >= lot.basis * (1.0 + exit_pct / 100.0)
                and (not lt_gate or (df.index[t] - df.index[lot.acquired_i]).days > 365)
            )
            if exit_ok:
                pending.append(("sell", lot))
            elif not lot.add_triggered and pc <= lot.basis * (1.0 + decline_pct / 100.0):
                lot.add_triggered = True
                pending.append(("add", None))
        if not lots and last_disposal is not None and pc <= 0.90 * last_disposal:
            pending.append(("reenter", None))

        if lots:
            invested_days += 1
        if t + 1 < n and years[t + 1] != year:
            st, lt = books.pop(year, [0.0, 0.0])
            tax, carry = _tax_due(st, lt, carry)
            cash -= tax; tax_paid += tax
        curve.append(cash + sum(l.shares * pc for l in lots))

    # terminal liquidation at final close
    fc, fy = closes[-1], years[-1]
    for lot in lots:
        realize(lot.shares * (fc - lot.basis), (df.index[-1] - df.index[lot.acquired_i]).days, fy)
        cash += lot.shares * fc; trades += 1
    st, lt = books.pop(fy, [0.0, 0.0])
    tax, carry = _tax_due(st, lt, carry)
    cash -= tax; tax_paid += tax

    series = pd.Series(curve, index=df.index)
    dd = float(((series - series.cummax()) / series.cummax()).min() * 100.0)
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    return {
        "end": round(cash, 2),
        "cagr": round(((cash / bankroll) ** (1 / yrs) - 1) * 100, 2),
        "max_dd": round(dd, 2),
        "trades": trades,
        "pct_days_invested": round(100 * invested_days / n, 1),
        "tax": round(tax_paid, 2),
        "st": round(st_realized, 2),
        "lt": round(lt_realized, 2),
    }


VARIANTS = {
    "adopted (+5 full exit, any term)": dict(exit_pct=5.0, exit_fraction=1.0, lt_gate=False),
    "accumulator (no scheduled exit)": dict(exit_pct=None, exit_fraction=1.0, lt_gate=False),
    "LT-gated full exit +20": dict(exit_pct=20.0, exit_fraction=1.0, lt_gate=True),
    "LT-gated full exit +50": dict(exit_pct=50.0, exit_fraction=1.0, lt_gate=True),
    "trim-half at +50, any term": dict(exit_pct=50.0, exit_fraction=0.5, lt_gate=False),
    "LT-gated trim-half +50": dict(exit_pct=50.0, exit_fraction=0.5, lt_gate=True),
    "LT-gated trim-half +100": dict(exit_pct=100.0, exit_fraction=0.5, lt_gate=True),
    "full exit +50, any term": dict(exit_pct=50.0, exit_fraction=1.0, lt_gate=False),
}


def main():
    data = fetch_historical(TICKERS, lookback_days=LOOKBACK_DAYS)
    bank = MAX_UNITS * UNIT * len(TICKERS)
    yrs = (data["NVDA"].index[-1] - data["NVDA"].index[0]).days / 365.25
    report = {}
    for name, kwargs in VARIANTS.items():
        total = 0.0; worst_dd = 0.0; trades = 0; tax = 0.0; st = lt = 0.0
        inv = []
        for t in TICKERS:
            r = simulate(data[t], **kwargs)
            total += r["end"]; worst_dd = min(worst_dd, r["max_dd"])
            trades += r["trades"]; tax += r["tax"]; st += r["st"]; lt += r["lt"]
            inv.append(r["pct_days_invested"])
        report[name] = {
            "end_wealth": round(total, 2),
            "cagr_pct": round(((total / bank) ** (1 / yrs) - 1) * 100, 2),
            "worst_ticker_max_dd_pct": worst_dd,
            "total_trades": trades,
            "avg_pct_days_invested": round(sum(inv) / len(inv), 1),
            "tax_paid": round(tax, 2),
            "st_realized": round(st, 2),
            "lt_realized": round(lt, 2),
        }
    # buy-and-hold reference (same terminal-tax treatment)
    bh_total = 0.0; bh_dd = 0.0
    for t in TICKERS:
        entry = float(data[t]["open"].iloc[0])
        shares = MAX_UNITS * UNIT / entry
        curveS = shares * data[t]["close"]
        final = float(curveS.iloc[-1])
        end = final - LT_TAX * max(0.0, final - MAX_UNITS * UNIT)
        bh_total += end
        bh_dd = min(bh_dd, float(((curveS - curveS.cummax()) / curveS.cummax()).min() * 100))
    report["buy_and_hold"] = {
        "end_wealth": round(bh_total, 2),
        "cagr_pct": round(((bh_total / bank) ** (1 / yrs) - 1) * 100, 2),
        "worst_ticker_max_dd_pct": round(bh_dd, 2),
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
