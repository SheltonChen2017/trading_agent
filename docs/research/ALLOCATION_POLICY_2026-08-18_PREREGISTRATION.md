# Allocation-policy QC family — preregistration

Date: 2026-08-18
Status: **Frozen in this commit, before any allocation-policy algorithm,
cloud run, or statistic.** Not an alpha family. Does not reopen the
closed cross-sectional program (A-002).

Governing plan: `docs/ALLOCATION_POLICY_QC_PLAN.md`

This file is the specification. If implementation drifts, the run is
invalid until the spec is followed or a **new** named preregistration
replaces this one. Do not edit weights, window, or gates after seeing a
result.

## 1. What this is

A historical comparison of **three frozen ETF mixes** against a **100%
equity benchmark**, after costs, on a window chosen for the August 2026
rate/oil/earnings regime — not a stock-selection hunt.

A worse CAGR than the benchmark with a milder drawdown is a **valid
success of the tilt**, not a failed alpha.

## 2. Window (confirmatory, only)

| Field | Frozen value |
|---|---|
| Start | 2022-01-01 (US equity session calendar) |
| End | last complete US session on or before 2026-08-18 |
| Cadence | calendar-month rebalance at that month's last session close |
| Normalization | adjusted closes (dividends in the price; **required for BIL**) |

Do **not** use 2012–2024 as the headline test. That sample is QE and
falling long yields; bills+equity will lose to 100% SPY for reasons that
are not the 2026 question. A later **labelled** 2012–2024 run is a
separate R-number ("does this mix lag when yields fall") and is out of
scope for the first cloud execution.

## 3. Instruments

| Ticker | Role |
|---|---|
| SPY | broad US equity (earnings bid) |
| BIL | T-bill / front of the curve (do **not** use Lean `Cash` for this sleeve; cash often earns 0) |
| XLP | consumer staples (defensive / cash-flow) |
| XLV | healthcare (defensive / cash-flow) |
| XLE | energy satellite |

All five must be US Equity, daily, adjusted. If any name is missing,
delisted for the window, or has a non-finite close on a rebalance date,
the algorithm **refuses** that date for every policy (no silent substitute).

## 4. Policies (weights sum to 100%)

Rebalance monthly to these exact weights. No bands, no signals, no VIX
switch, no ranking.

| ID | Name | SPY | BIL | XLP | XLV | XLE |
|---|---|---|---|---|---|---|
| P0 | Benchmark (all equity) | 100 | 0 | 0 | 0 | 0 |
| P1 | Bills + equity | 40 | 60 | 0 | 0 | 0 |
| P2 | Less equity duration | 40 | 20 | 20 | 20 | 0 |
| P3 | P1 + energy satellite | 35 | 55 | 0 | 0 | 10 |

P3 energy weight is a **cap and a target**: 10%, never raised after seeing
results. No SH, TLT, QQQ short, options, or vol sales in this family.

## 5. Costs, turnover, output

- One-way turnover from drifted prior weights to target, same definition
  as the reviewed universe benchmark (`_drift_turnover`). Unavailable
  turnover: empty field; analyser charges 1.0 one-way and discloses.
- Report gross and net at **0 / 5 / 10 / 25 bps** per side.
- Emit **one row per policy per month** (four rows per date): date,
  policy id, return, turnover, names priced, names targeted.
- Completeness: refuse the run if any policy has fewer than 24 months
  (the existing bootstrap floor) or if P0 dates are not identical to
  P1/P2/P3 dates.

## 6. Inference (frozen)

This is **not** an alpha cell family. Do not add these 3 or 4 series to
the 452 lifetime alpha floor.

**Primary, required:** descriptive table vs P0 on the confirmatory
window — n months, CAGR, Sharpe, maxDD, time underwater, mean turnover,
net 10 bps CAGR/Sharpe/maxDD.

**Optional single test family (if reported at all):** excess monthly
mean of P1, P2, P3 versus P0, two-sided, stationary bootstrap 20,000
draws, Bonferroni **0.05/3**. A fail is the expected outcome and **ends
the family**. A pass is not authorization to trade or to add variants.

No IC. No long-short. No universe screen. No extra tickers.

## 7. Looks

- **Run-level:** one cloud backtest of the single algorithm that emits
  all four policies. Counted (29 → 30 if the Stage 1 count still stands
  at launch).
- **Allocation-policy cells:** 3 (P1/P2/P3 vs P0) if the optional test
  is reported; 0 if only the descriptive table is published.
- Refusals, crashes, and accidental launches still count as runs.

## 8. What is forbidden after seeing output

- Adding DBC, IEF, QQQ, puts, or a second energy ticker
- Changing 60/40 to 50/50 or 10% XLE to 15%
- Extending or shortening the window
- Treating P3's satellite as the "real" result and dropping P1
- A second analyser pass on the same logs
- Alpaca / paper / live from this family
