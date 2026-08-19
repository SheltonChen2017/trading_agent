# Max-profit policy QC family — preregistration

Date: 2026-08-19
Status: **DRAFT pending owner freeze.** Proposed values are listed so
they can be accepted as-is (the defensive-carry pattern). Nothing is
owner-frozen until the action plan schedules MPQ-1. Not an alpha family.
Does not reopen the closed cross-sectional program (A-002).

Governing plan: `docs/reference/MAX_PROFIT_POLICY_QC_PLAN.md`

This file is the specification. After an owner freeze, do not edit
weights, window, or gates after seeing a result; a change needs a **new**
named preregistration.

## 1. What this is

A historical comparison of **three frozen growth-tilted ETF mixes**
against **100% SPY**, after costs, on the **same confirmatory window as
APQ**. The question is not “can we pick stocks.” It is: **does taking
more Nasdaq / semiconductor beta, still long-only and unlevered, earn
more than the S&P 500 sleeve after costs?**

A higher CAGR with a **worse** drawdown can still be a valid success of
the tilt. That is the opposite of APQ’s success shape (milder crash,
acceptable upside cost).

This is **not** “maximum possible profit.” Levered ETFs, options,
margin, and single-name concentration are forbidden here. The name means
**growth-oriented allocation**, the counterpart to APQ’s safety mix.

## 2. Window (confirmatory, only) [TO FREEZE]

| Field | Proposed value |
|---|---|
| Start | 2022-01-01 (US equity session calendar) |
| End | last complete US session on or before 2026-08-18 |
| Cadence | calendar-month rebalance at that month's last session close |
| Normalization | adjusted closes |

**Same window as APQ on purpose.** Three families (safety / growth /
hedge) on identical dates can be compared. Do not extend into 2012–2021
as the headline test: that sample is a long QE/Nasdaq bull and would
answer a different question. A later labelled 2012–2024 run is a
separate R-number.

The 2022+ tape includes a growth crash and a growth rebound. Results are
regime-conditioned. They are not a forecast.

## 3. Instruments [TO FREEZE]

| Ticker | Role |
|---|---|
| SPY | broad US equity (benchmark sleeve) |
| QQQ | Nasdaq-100 growth tilt |
| SMH | semiconductor satellite (capped) |

All three must be US Equity, daily, adjusted. If any name is missing,
delisted for the window, or has a non-finite close on a rebalance date,
the algorithm **refuses** that date for every policy (no silent
substitute). Union-wide alignment, same rule as APQ.

No TQQQ/SOXL or other levered products. No single stocks. No universe
screen.

## 4. Policies (weights sum to 100%) [TO FREEZE]

Rebalance monthly to these exact weights. No bands, no signals, no
VIX switch, no ranking.

| ID | Name | SPY | QQQ | SMH |
|---|---|---|---|---|
| G0 | Benchmark (all equity) | 100 | 0 | 0 |
| G1 | All Nasdaq-100 | 0 | 100 | 0 |
| G2 | Growth tilt | 30 | 70 | 0 |
| G3 | G2 + semis satellite | 30 | 50 | 20 |

G3 SMH weight is a **cap and a target**: 20%, never raised after seeing
results.

## 5. Costs, turnover, output

Same contracts as APQ: `_drift_turnover`, empty turnover charged 1.0 at
analysis, gross/net at **0 / 5 / 10 / 25 bps** per side, one row per
policy per month, refuse the run below 24 months or if date sets
diverge.

## 6. Inference [TO FREEZE]

Not an alpha cell family. Do not add these series to the 452 lifetime
alpha floor.

**Primary, required:** descriptive table vs G0 — n months, CAGR, Sharpe,
maxDD, time underwater, mean turnover (read beside
`unavailable_turnover_periods`), net 10 bps CAGR/Sharpe/maxDD.

**Growth composite gate (all three must hold vs G0, net 10 bps):**

1. CAGR **higher** than G0 (no minimum spread — any positive gap after
   costs);
2. Sharpe **not worse** than G0 by more than **0.10** absolute (so a
   pure volatility binge without compensation refuses);
3. maxDD **may be worse** than G0; that is disclosed, not a fail.

**Optional test family (reporting decision frozen at MPQ-2 review, before
any run):** excess monthly mean of G1, G2, G3 versus G0, two-sided,
stationary bootstrap 20,000 draws, Bonferroni **0.05/3**. A fail ends
the family. A pass is not authorization to trade or to raise the SMH
cap.

No IC. No long-short. No extra tickers.

## 7. Looks

- **Run-level:** one cloud backtest emitting all four policies. Counted.
- **Cells:** 3 (G1/G2/G3 vs G0) if the optional test is reported.
- Refusals and accidental launches still count.

## 8. What is forbidden after seeing output

- Adding TQQQ, SOXL, IWM, ARKK, or a fourth ticker
- Raising SMH above 20% or rotating to “whatever won”
- Changing the window
- Treating G1 as the only result and dropping G2/G3
- A second analyser pass on the same logs
- Alpaca / paper / live from this family
- Reopening A-002 stock selection
