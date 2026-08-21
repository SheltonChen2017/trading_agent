# Max-profit policy QC family — preregistration

Date: 2026-08-19
Status: **DRAFT pending owner freeze.** Proposed values are listed so
they can be accepted as-is (the defensive-carry pattern). Nothing is
owner-frozen until the action plan schedules MPQ-1. Not an alpha family.
Does not reopen the closed cross-sectional program (A-002).

Governing plan: `docs/Plan/MAX_PROFIT_POLICY_QC_PLAN.md`

This file is the specification. After an owner freeze, do not edit
weights, window, or gates after seeing a result; a change needs a **new**
named preregistration.

Owner revision the same day, **before any run:** unlevered QQQ/SMH
weights were replaced with **daily-reset 3x** analogs (TQQQ/SOXL) at
the same percentage mix. That is a spec change, not a look.

## 1. What this is

A historical comparison of **three frozen levered growth ETF mixes**
against **unlevered 100% SPY**, after costs, on the **same confirmatory
window as APQ**. The question is not “can we pick stocks.” It is: **does
a static 3x Nasdaq / 3x semiconductor sleeve earn more terminal growth
than the S&P 500 sleeve after costs and after daily-reset drag?**

A higher CAGR with a **much worse** drawdown is the expected shape. That
is the opposite of APQ’s success shape (milder crash, acceptable upside
cost). It is also why this family **does not** use APQ’s Sharpe-near-SPY
gate: 3x products will almost always look worse on Sharpe even when CAGR
wins.

This is still **not** “maximum possible profit.” Options, futures,
margin, 4x products, and single-name concentration remain forbidden.
Leverage here means **listed 3x ETFs only**, at frozen weights.

## 2. Window (confirmatory, only) [TO FREEZE]

| Field | Proposed value |
|---|---|
| Start | 2022-01-01 (US equity session calendar) |
| End | last complete US session on or before 2026-08-18 |
| Cadence | calendar-month rebalance at that month's last session close |
| Normalization | adjusted closes |

**Same window as APQ on purpose.** Three families (safety / levered
growth / hedge) on identical dates can be compared. Do not extend into
2012–2021 as the headline test: that sample is a long QE/Nasdaq bull
and would flatter 3x products. A later labelled 2012–2024 run is a
separate R-number.

The 2022+ tape includes a **levered growth crash** and a rebound.
Daily-reset 3x products can lose a large fraction of capital in 2022
and still print a high CAGR if the rebound is large enough. Results are
path-dependent and regime-conditioned. They are not a forecast and they
are not evidence that the next crash will be survivable.

## 3. Instruments [TO FREEZE]

| Ticker | Role | Honest limitation |
|---|---|---|
| SPY | unlevered broad US equity (benchmark sleeve) | — |
| TQQQ | ProShares UltraPro QQQ (~3x Nasdaq-100, daily reset) | volatility drag; path-dependent; can go to near-zero in a crash |
| SOXL | Direxion Daily Semiconductor Bull 3x | same daily-reset class; extra single-industry crash risk |

All three must be US Equity, daily, adjusted. If any name is missing,
delisted for the window, or has a non-finite close on a rebalance date,
the algorithm **refuses** that date for every policy (no silent
substitute, including no fallback to QQQ/SMH). Union-wide alignment,
same rule as APQ.

No QQQ/SMH in this family (the unlevered analogs were withdrawn before
any run). No UPRO/SSO stack on top of TQQQ. No TNA, TECL, TQQQ options,
or futures. No single stocks. No universe screen.

## 4. Policies (weights sum to 100%) [TO FREEZE]

Rebalance monthly to these exact weights. No bands, no signals, no
VIX switch, no ranking, no leverage overlay on top of the ETF.

| ID | Name | SPY | TQQQ | SOXL |
|---|---|---|---|---|
| G0 | Benchmark (unlevered equity) | 100 | 0 | 0 |
| G1 | All 3x Nasdaq-100 | 0 | 100 | 0 |
| G2 | Levered growth tilt | 30 | 70 | 0 |
| G3 | G2 + 3x semis satellite | 30 | 50 | 20 |

G1 TQQQ weight is a **cap and a target**: 100% of the sleeve, never
replaced by a 4x product after seeing results.

G3 SOXL weight is a **cap and a target**: 20%, never raised after seeing
results.

Effective notional beta is **not** a fifth policy. Approximate daily
beta vs Nasdaq is about 3.0 (G1), 2.1 (G2), and 2.1 equity-beta plus
0.6 semis-beta (G3). Those figures are disclosure, not a rebalance
target.

## 5. Costs, turnover, output

Same contracts as APQ: `_drift_turnover`, empty turnover charged 1.0 at
analysis, gross/net at **0 / 5 / 10 / 25 bps** per side, one row per
policy per month, refuse the run below 24 months or if date sets
diverge.

Expense ratios and daily-reset drag are **inside** the adjusted-close
path; do not subtract a second leverage fee on top. The 0/5/10/25 bps
grid is rebalance-turnover cost only.

## 6. Inference [TO FREEZE]

Not an alpha cell family. Do not add these series to the 452 lifetime
alpha floor.

**Primary, required:** descriptive table vs G0 — n months, CAGR, Sharpe,
maxDD, time underwater, mean turnover (read beside
`unavailable_turnover_periods`), net 10 bps CAGR/Sharpe/maxDD. Also
report **terminal wealth relative to G0** (ending NAV / G0 ending NAV)
because that is the max-profit reading.

**Levered-growth composite gate (all three must hold vs G0, net 10 bps).**
Counter-review label (2026-08-19, pre-freeze): this composite gate is a
DESCRIPTIVE CLASSIFICATION of one price path — it carries no p-value
and no statistical claim, and a pass is a leverage/beta reading
conditional on this tape, never evidence of edge or skill. Only the
optional bootstrap family below carries significance. Related coverage:
the frozen LEV family's L0-vs-SREF descriptives already contain the
G1-vs-G0 question on the longer 2011+ window; this family adds the
mixes and the SOXL satellite on the shared 2022+ window.

1. CAGR **higher** than G0 (no minimum spread — any positive gap after
   costs);
2. maxDD **may be worse** than G0; that is disclosed, not a fail;
3. Sharpe is **descriptive only** (no Sharpe floor vs G0 — a 3x product
   that beats SPY on CAGR will usually lose on Sharpe).

A mix that **fails (1)** is a fail even if maxDD is milder. There is no
“leverage worked because it crashed less” reading in this family.

**Optional test family (reporting decision frozen at MPQ-2 review, before
any run):** excess monthly mean of G1, G2, G3 versus G0, two-sided,
stationary bootstrap 20,000 draws, Bonferroni **0.05/3**. A fail ends
the family. A pass is not authorization to trade, to raise the SOXL
cap, or to hold TQQQ in paper/live.

No IC. No long-short. No extra tickers.

## 7. Looks

- **Run-level:** one cloud backtest emitting all four policies. Counted.
- **Cells:** 3 (G1/G2/G3 vs G0) if the optional test is reported.
- Refusals and accidental launches still count.

## 8. What is forbidden after seeing output

- Adding UPRO, SSO, TNA, TECL, QQQ, SMH, IWM, ARKK, or a fourth ticker
- Raising SOXL above 20% or rotating to “whatever won”
- Replacing TQQQ with a higher-leverage product
- Changing the window
- Treating G1 as the only result and dropping G2/G3
- A second analyser pass on the same logs
- Alpaca / paper / live from this family
- Reopening A-002 stock selection
