# Max-profit (levered growth) policy — QuantConnect research family

Status: **PROPOSED / OWNER DECISION PENDING**
Date: 2026-08-19
Owner: xiao
Audience: implementer and independent reviewer

This is the **growth counterpart** to
`docs/reference/ALLOCATION_POLICY_QC_PLAN.md` (APQ). It uses the same
evidence shape: frozen ETF weights, monthly rebalance, same 2022–2026
window, one cloud run, one analyser pass. It answers a **different**
question: **after costs, does a static 3x Nasdaq / 3x semiconductor
sleeve beat unlevered 100% SPY on growth?**

It is **not** stock-picking. It does not reopen A-002. It does not
authorize paper or live trading. Leverage is **listed 3x ETFs at frozen
weights**, not margin, options, or a fourth product after seeing
results.

Owner revision 2026-08-19, before any run: QQQ/SMH replaced by TQQQ/SOXL
at the same percentages.

Sequencing (updated at counter-review 2026-08-19: APQ-4/5 completed
and the allocation family CLOSED as A-003 the day this plan was
drafted): do **not** start MPQ-1 until the owner freezes the
preregistration and schedules it. Sequencing authority remains
`docs/reference/ACTION_PLAN_2026-08-02.md`.

## 1. Question

On the frozen confirmatory window, after the same turnover and
cost-sensitivity machinery as APQ:

- Does 100% TQQQ beat 100% SPY on net CAGR and terminal wealth, and at
  what drawdown cost?
- Does a 70/30 TQQQ/SPY mix keep most of that growth with less 3x
  concentration?
- Does a 20% SOXL satellite on top of a TQQQ/SPY core add enough extra
  growth to justify the extra crash risk?

Worse max drawdown than SPY is an **expected cost of 3x**, not an
automatic fail. Sharpe vs G0 is reported, not gated: daily-reset
leverage usually loses on Sharpe even when it wins on CAGR.

## 2. Why a separate family (not APQ, not Stage 0)

| Program | Question |
|---|---|
| Closed Stage 0/1 (A-002) | Cross-sectional IC / long-short on the 50-name universe |
| APQ | Long-only **defensive** mix vs 100% SPY |
| **This family (MPQ)** | Long-only **3x growth** mix vs 100% SPY |
| HPQ | Static **inverse overlay** vs 100% SPY |

Mixing TQQQ into APQ after seeing APQ results would be a look. A new
named family with frozen 3x weights is the honest path.

## 3. Frozen mix (see preregistration)

- **G0:** 100% SPY (unlevered benchmark)
- **G1:** 100% TQQQ
- **G2:** 70% TQQQ / 30% SPY
- **G3:** 50% TQQQ / 30% SPY / 20% SOXL (SOXL cap 20%)

Full window, daily-reset disclosure, costs, refusal, and inference:
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

**Definition of done:** tests for G0–G3 weights, refusal, 20% SOXL cap
enforced in config (cannot silently become 25%), no silent fallback
from TQQQ/SOXL to QQQ/SMH, no `ml` import, no Alpaca.

### MPQ-2 — Analyser family

Same JSON report contract as APQ. Levered-growth composite gate implemented
as specified in the preregistration (CAGR vs G0; no Sharpe floor).
Optional excess-mean test: **report vs omit frozen at this milestone’s
review, before any cloud run.**

### MPQ-3 — Driver hook

Add a universe-free family beside the existing ones (correction at
counter-review 2026-08-19: the existing universe-free driver family is
`allocation` — APQ-3 — with LEV's family arriving at LEV-2;
`defensive_carry` is the overlay shadow stream, not a driver family).
Name it `levered_growth` or equivalent. Same `require_clean` hash
lock. Do not retarget APQ bytes.

### MPQ-4 — One cloud backtest

Owner GO. One project, one compile, one backtest, four policies.

### MPQ-5 — One analyser pass

Same hash-locked logs. Verdict recorded. Family ends on fail or on
owner-accepted descriptive close. No second pass.

## 5. Explicitly out of scope (all milestones)

- Options, futures, broker margin, 4x products, UPRO/SSO stacked on TQQQ
- Single stocks, universe screens, ranking
- Raising SOXL after results
- Changing REBAL paper targets from this family
- Folding into SHW overlay or paper epoch
- Starting code before the owner freezes and schedules this family
