# Hedge policy QC family — preregistration

Date: 2026-08-19
Status: **DRAFT pending owner freeze.** Proposed values listed for
accept-as-is. Not frozen until the action plan schedules HPQ-1. Not an
alpha family. Does not reopen A-002.

Governing plan: `docs/Plan/HEDGE_POLICY_QC_PLAN.md`

This family is **QuantConnect research**. It is **not** the HEDGE-1
Streamlit sleeve (`assistant` UI, PR #223). Do not treat HEDGE-1
as evidence for these mixes, and do not change that UI from this
program.

## 1. What this is

A historical comparison of **three frozen static overlays** against
**100% SPY**, after costs, on the **same confirmatory window as APQ**.

APQ answers: “does a **long-only defensive mix** cushion a crash?”
This family answers: “does a **small inverse or market-neutral sleeve**
cushion a crash **without** throwing away most of the equity upside?”

The overlay is **always on**. There is no VIX trigger, no crash
predictor, and no LLM. A timing hedge is a different R-number.

## 2. Window (confirmatory, only) [TO FREEZE]

Identical to APQ and MPQ:

| Field | Proposed value |
|---|---|
| Start | 2022-01-01 |
| End | last complete US session on or before 2026-08-18 |
| Cadence | calendar-month rebalance at month-end close |
| Normalization | adjusted closes |

The 2022 crash is in-sample for a hedge. That is the point of a crash
cushion test. It is also why this is **not** a forecast that the next
crash will look like 2022.

## 3. Instruments [TO FREEZE]

| Ticker | Role | Honest limitation |
|---|---|---|
| SPY | long equity | — |
| SH | ProShares Short S&P 500 | **daily-reset inverse**; path-dependent decay in chop |
| BTAL | AGFiQ US Market Neutral Anti-Beta | already in the HEDGE-1 **app** ticker set; still not evidence. Counter-review note: thin AUM/volume for its class — the 0/5/10/25 bps grid may understate realized spread cost for H3; read H3's net rows as optimistic |

If any name is missing or non-finite on a rebalance date, refuse that
date for **every** policy (union alignment).

Forbidden here: SDS/SPXU (levered inverse), VIXY/UVXY, options, futures,
3x products.

## 4. Policies (weights sum to 100%) [TO FREEZE]

| ID | Name | SPY | SH | BTAL |
|---|---|---|---|---|
| H0 | Benchmark | 100 | 0 | 0 |
| H1 | Light inverse | 90 | 10 | 0 |
| H2 | Inverse cap | 80 | 20 | 0 |
| H3 | Neutral sleeve | 90 | 0 | 10 |

H2 SH weight is a **cap and a target**: 20%, never raised after results.

H1 and H2 are the same instrument at two sizes so a 10% vs 20% inverse
cost can be read without a second look. H3 exists so the family is not
only “short SPY with SH.”

## 5. Costs, turnover, output

Same as APQ: `_drift_turnover`, empty turnover charged 1.0 at analysis,
0/5/10/25 bps per side, one row per policy per month, refuse below 24
months or if date sets diverge.

## 6. Inference [TO FREEZE]

Not an alpha cell family. Do not add these series to the 452 lifetime
floor.

**Primary, required:** descriptive table vs H0 — n, CAGR, Sharpe, maxDD,
time underwater, mean turnover (with unavailable-turnover note), net 10
bps.

**Hedge composite gate (all three vs H0, net 10 bps).**
Counter-review label (2026-08-19, pre-freeze): this composite gate is a
DESCRIPTIVE CLASSIFICATION of one price path — no p-value, no
statistical claim; only the optional mean-cost descriptor below
carries significance machinery. Related evidence: APQ's P1/P2
defensive mixes closed NULL on mean with a real drawdown trade
(A-003), and the defensive-carry overlay stream observes a
carry-sleeve hedge prospectively — this family is the inverse/anti-beta
counterpart, not a duplicate.

1. maxDD **strictly better** (less severe) than H0 by at least **10%
   relative** — example: H0 maxDD −20% requires the mix maxDD ≥ −18%
   (algebra: `mix_maxdd > h0_maxdd * 0.9` when both are negative
   drawdowns expressed as signed returns);
2. upside capture **≥ 75%** of H0: mix CAGR ≥ 0.75 × H0 CAGR when H0 CAGR
   is positive; if H0 CAGR is non-positive, this clause is **not
   applicable** and the mix must still satisfy (1) and (3);
3. mix CAGR **not worse** than H0 by more than **4 percentage points
   annualized** (absolute, net 10 bps) — a hedge that “works” only by
   destroying the decade is a fail.

If H0 CAGR is non-positive, record clause (2) as `not_applicable` and
still apply (1) and (3).

**Optional test family (report vs omit frozen at HPQ-2 review, before
any run):** excess monthly mean of H1/H2/H3 vs H0 is **not** the
success metric (a successful hedge can lose on mean). If reported, use
it only as a **cost** descriptor, Bonferroni 0.05/3, and do not treat a
mean-win as a hedge success.

No IC. No long-short of the 50-name universe. No extra tickers.

## 7. Looks

- **Run-level:** one cloud backtest, four policies. Counted.
- **Cells:** 3 if any optional mean test is reported.
- Refusals and extra launches still count.

## 8. What is forbidden after seeing output

- Raising SH above 20%
- Adding SDS, VIX products, or options
- Switching H3 to “the other HEDGE-1 tickers that would have won”
- Changing the window
- A second analyser pass
- Shipping weights into the HEDGE-1 UI or paper REBAL
- Claiming the HEDGE-1 **application** was validated by this QC family
