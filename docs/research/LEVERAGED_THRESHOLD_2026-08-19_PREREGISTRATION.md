# Preregistration: leveraged-ETF take-profit family (LEV, 2026-08-19)

Status: **DRAFT — becomes FROZEN upon owner adoption.** Every value in
section 3–6 is fixed at adoption, before any result is observed.
Author: Claude, from the owner's strategy description of 2026-08-19
(Path B of that discussion: the leveraged-ETF engine, testable today;
the analyst-ratings layer is the separate SBR capture stream).

## 1. Idea and owner goal

Hold a leveraged NASDAQ ETF; take profit when it has risen a fixed
threshold from entry; re-enter by rule. Owner goal: beat NASDAQ and
SPY. This family tests whether the take-profit/re-entry rule adds
anything beyond simply holding the leveraged instrument — the only
comparison at which "edge" is even possible, since a 3x instrument
beating SPY in a rising tape is leverage, not skill.

## 2. Relation to closed programs and prior evidence

- NOT a reopening of the closed cross-sectional alpha program (A-002):
  no stock selection, fixed instruments only, its own family and gate.
- Prior related evidence in this repository, disclosed up front:
  SOXX/SOXL rotation survived look-ahead and walk-forward scrutiny but
  LOST its CAGR edge under 37% tax modeling (only the drawdown benefit
  survived); Kelly/ratchet variants failed walk-forward; vol-target
  rotation failed on five pairs. The prior for a return edge from
  timing rules on leveraged ETFs is poor; the realistic prize is a
  risk-shape improvement — which is why after-tax and drawdown columns
  are preregistered as descriptives below.

## 3. Frozen specification

| Item | Value |
|---|---|
| Instrument | TQQQ (3x NASDAQ-100), the leverage of the index the owner named |
| Reference series | QQQ, SPY (same dates, buy-and-hold) |
| Benchmark policy | L0 = TQQQ buy-and-hold |
| Window | 2011-01-03 → run date (TQQQ inception Feb 2010; first full calendar year after; includes the 2022 −80% drawdown deliberately) |
| Evaluation | Monthly rows from daily closes; monthly return = close-to-close over completed month ends (APQ conventions) |
| Cash while out | Uninvested, 0% (disclosed simplification; no BIL sleeve) |
| Data | QC daily equity closes only; no fundamental or ratings data |

Rule state machine (all four variants start invested at the first
window close; all evaluation at daily closes, execution at the next
session's close after a trigger):

| Variant | Take-profit T | Re-entry rule |
|---|---|---|
| L1 | +20% from entry close | next month-end close after the sale |
| L2 | +40% from entry close | next month-end close after the sale |
| L3 | +20% from entry close | first close ≥10% BELOW the sale-fill close; if never, stay in cash (that outcome is recorded, not patched) |
| L4 | +40% from entry close | same −10% pullback rule |

Each sale logs its realized gain and holding period (calendar days) so
the after-tax descriptive column is computable without re-observation.

## 4. Test cells and gate (the only tested statistics)

Eight cells, Bonferroni gate **0.05/8 = 6.25e-3**, two-sided
stationary bootstrap on monthly excess means, 20,000 draws (smallest
attainable p 5.0e-5; ABR-001 reachability guard applies):

- Cells 1–4: L1..L4 monthly excess mean vs **L0 (TQQQ buy-and-hold)**.
  This is the edge test: does the rule add anything to the instrument?
- Cells 5–8: L1..L4 monthly excess mean vs **QQQ buy-and-hold**. This
  is the owner's stated goal ("beat NASDAQ"). Interpretation limit,
  frozen now: a pass here with a fail against L0 is LEVERAGE, not
  skill, and will be labeled exactly that.

Sharpe differences, max-drawdown differences, time under water, vs-SPY
comparisons, and the after-tax column are **descriptive only** — no
p-values, no claims, same as the ratified APQ schema.

## 5. Descriptive after-tax column (frozen formula, no gate)

Prior lesson (SOXL): untaxed leveraged-rotation comparisons mislead.
Per variant, a descriptive after-tax terminal wealth is computed from
the logged sales: each realized gain is charged 37% if the holding
period was under 366 calendar days, else 20%; losses offset gains
within the run; L0/QQQ/SPY buy-and-hold are charged nothing (unsold).
Descriptive only; conservative against the strategy by construction.

## 6. Process, look budget, and refusals

- Milestones, one branch + independent review each: LEV-1 LEAN
  algorithm + local tests (no QC); LEV-2 analyser + driver family hook
  + tests (no QC); LEV-3 ONE cloud run, ledgered R-nnn UNANALYSED,
  structural round-trip only; LEV-4 ONE analyser pass, A-nnn, upgrade
  to VALID in the same commit, family CLOSES either way.
- Look budget: one cloud run and one analyser pass, total. A
  structurally incomplete log is ledgered REFUSED/INCOMPLETE and any
  rerun is a new counted look on a new R-number.
- Scope: this family only; nothing here adds to the closed alpha
  program's lifetime floor.
- Parser refusals follow the APQ contract: fail closed on unknown
  variant, duplicate rows, non-finite values, misaligned dates,
  truncation, and a floor of 120 months.
- Paper/live use of any rule is a separate owner decision on the
  Alpaca/REBAL stack, never a QC follow-up.

## 7. Adoption

Owner adoption line (date + wording) to be recorded here; all values
above freeze at that moment. Until then this document is a proposal
and no LEV code milestone may start.
