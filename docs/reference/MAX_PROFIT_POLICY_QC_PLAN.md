# Max-profit (growth-tilt) policy — QuantConnect research family

Status: **PROPOSED / OWNER DECISION PENDING**
Date: 2026-08-19
Owner: xiao
Audience: implementer and independent reviewer

This is the **growth counterpart** to
`docs/reference/ALLOCATION_POLICY_QC_PLAN.md` (APQ). It uses the same
evidence shape: frozen ETF weights, monthly rebalance, same 2022–2026
window, one cloud run, one analyser pass. It answers a **different**
question: **after costs, does a long-only Nasdaq/semiconductor tilt beat
100% SPY on growth?**

It is **not** stock-picking. It does not reopen A-002. It does not
authorize paper or live trading. It is **not** “max leverage / max
concentration.” Levered products are out of scope.

Do **not** start MPQ-1 while APQ-4 is in flight unless the owner
explicitly reorders. Sequencing authority remains
`docs/ACTION_PLAN_2026-08-02.md`.

## 1. Question

On the frozen confirmatory window, after the same turnover and
cost-sensitivity machinery as APQ:

- Does 100% QQQ beat 100% SPY on net CAGR?
- Does a 70/30 QQQ/SPY mix capture most of that gap with less
  concentration?
- Does a 20% SMH satellite on top of a QQQ/SPY core add enough extra
  growth to justify the extra crash risk?

Worse max drawdown than SPY is an **expected cost of the tilt**, not an
automatic fail. The growth composite gate still refuses a mix that is
only noisier without higher CAGR (Sharpe floor vs G0).

## 2. Why a separate family (not APQ, not Stage 0)

| Program | Question |
|---|---|
| Closed Stage 0/1 (A-002) | Cross-sectional IC / long-short on the 50-name universe |
| APQ | Long-only **defensive** mix vs 100% SPY |
| **This family (MPQ)** | Long-only **growth** mix vs 100% SPY |
| HPQ | Static **inverse overlay** vs 100% SPY |

Mixing growth names into APQ after seeing APQ results would be a look.
A new named family with frozen weights is the honest path.

## 3. Frozen mix (see preregistration)

- **G0:** 100% SPY
- **G1:** 100% QQQ
- **G2:** 70% QQQ / 30% SPY
- **G3:** 50% QQQ / 30% SPY / 20% SMH (SMH cap 20%)

Full window, costs, refusal, and inference:
`docs/research/MAX_PROFIT_POLICY_2026-08-19_PREREGISTRATION.md`

## 4. Milestones

Mirror APQ. One milestone per branch. Independent review before the
next. Do not start MPQ-1 until the owner schedules it.

### MPQ-0 — Plan freeze (this document + preregistration)

**Definition of done**

- Plan and preregistration committed on a distinctive branch.
- Action-plan row exists as **proposed**, not as the current next QC
  step.
- Owner freeze (or explicit reject / rewrite) is recorded before MPQ-1.

**Out of scope:** LEAN, driver, QC, paper, live.

### MPQ-1 — Dedicated LEAN algorithm + local tests

Copy the APQ algorithm pattern: one algorithm, four policies, union
alignment, `_drift_turnover`, 24-month floor. Distinct
`algorithm_id` / family id so APQ logs cannot be analysed as MPQ.

**Definition of done:** tests for G0–G3 weights, refusal, 20% SMH cap
enforced in config (cannot silently become 25%), no `ml` import, no
Alpaca.

### MPQ-2 — Analyser family

Same JSONL contract as APQ. Growth composite gate implemented as
specified in the preregistration. Optional excess-mean test: **report
vs omit frozen at this milestone’s review, before any cloud run.**

### MPQ-3 — Driver hook

Add a second universe-free family beside `defensive_carry` (name
`growth_tilt` or equivalent). Same `require_clean` hash lock. Do not
retarget APQ bytes.

### MPQ-4 — One cloud backtest

Owner GO. One project, one compile, one backtest, four policies.

### MPQ-5 — One analyser pass

Same hash-locked logs. Verdict recorded. Family ends on fail or on
owner-accepted descriptive close. No second pass.

## 5. Explicitly out of scope (all milestones)

- TQQQ, SOXL, options, futures, margin
- Single stocks, universe screens, ranking
- Raising SMH after results
- Changing REBAL paper targets from this family
- Folding into SHW overlay or paper epoch
- Starting code while APQ-4 is the scheduled QC step without owner
  reorder
