# Session handoff — REBAL-1 Stage 3 implemented

Prepared: 2026-08-15 by Claude, after implementing Stage 3 of the REBAL-1
plan under the owner's explicit authorization.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REBAL1_MILESTONE_PLAN.md`
4. `docs/REVIEW_2026-08-15_REBAL1_STAGE3.md`
5. `docs/REVIEW_2026-08-15_REBAL1_STAGE2_COUNTERREVIEW.md`
6. `docs/REVIEW_2026-08-15_REBAL1_STAGE2_INDEPENDENT.md`
7. `docs/MANDATE.md` (§2, §4, §6)
8. `docs/OPERATIONAL_FACTS.md`
9. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes deployment, evidence repair, an epoch roll, M4,
funded-account access, live trading, operator-database mutation, or a
scheduled-task change.

## 1. Repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- `main` and `origin/main`: `45faf1c`, PR #229's merge of the Stage 2
  counter-review.
- **Current branch: `user/claude/rebal1-stage3-tax-aware-trims-20260815`**,
  branched from `45faf1c`. One branch for the whole round, per the owner's
  2026-08-15 workflow rule.
- The operational checkout remains separate at frozen commit `752d3b7` in
  active `paper-epoch-005`. No development commit has been copied there.

Relevant recent history:

- `4de784e` / `1cb8abf`: the epoch-005 observation-clock roll chain and
  Codex's correction of it.
- `c048a94`: the owner's decision to keep epoch-005 unchanged for 60 days.
- `6fcdd35` / `5519a69` / `832ea6a`: REBAL-1 Stage 1, Codex's review
  correction, and Claude's counter-review.
- `c0d56d5` / `bdeb61d` / `bedb598`: Stage 2, Codex's review correction, and
  Claude's counter-review.
- The completed BUY-1 review branch remains
  `codex/review-buy1-suggestion-picker-20260813`, correction `44a7f85`. It is
  historical recovery context, not reopened work.

## 2. Authorization for this stage, and its limits

The milestone plan required Stage 3 to have "separate explicit authorization
naming it" before any code was written, because it is the first path where a
rebalancing sell originates from the app's own arithmetic rather than from a
computed policy breach or the owner naming a holding. The owner gave that on
2026-08-15.

**That authorization covers building the workflow only.** It does not
authorize deployment, an epoch roll, any change to the operational checkout,
or any live or paper order. Nothing in this branch submits anything.

## 3. What Stage 3 does

`assistant/rebalance_trim.py` plus a section on the existing Portfolio
Rebalancing page.

The owner chooses **sleeve, ticker, amount, and lot strategy**. All four
start unset — the selectboxes read "-- choose --" and shares start at zero —
and the check control stays disabled until every one is chosen. The app
chooses none of them.

The plan then shows the amount above the band, the amount that restores the
target, each open lot with acquisition date and holding period, which lots
the chosen strategy would consume, the realized gain split short- and
long-term, any working sell already reducing the sleeve, and the remainder.

**Five refusals, each a deliberate direction:**

1. a sleeve inside or below its band cannot be trimmed;
2. cash and the residual are never trimmable — absence from the profile is
   never a reason to sell, which is Stage 1's rule applied where it bites;
3. a sale beyond the target-restoration amount is refused, because trimming
   past target flips the sleeve underweight and hands the next steering pass
   a shortfall to buy back, paying spread and tax both ways;
4. an incomplete tax ledger refuses the whole trim rather than proposing a
   sale whose tax effect is unknown — this stage exists to show that
   consequence, and `docs/MANDATE.md` rates tax sensitivity High; and
5. a working sell already counts against the excess, measured on the
   projected value, so a second trim is not prepared for a gap the first is
   closing (HEDGER-004's lesson).

**Execution-time binding** now covers the trim status through a named
`_PROFILE_BOUND_EVIDENCE_STATUSES` set in `assistant/execution_service.py`. A
stale trim is worse than a stale buy: a buy spends money toward a target the
owner has since moved, while a trim SELLS toward one and realizes gains that
no later profile edit can un-realize.

**Lot selection is advisory.** The app records which lots the owner chose; it
does not instruct the broker to use them, and the proposal says so.

## 4. A consequence worth knowing before reviewing

The restoration cap makes it arithmetically impossible to sell most of a
sleeve's *only* holding: restoring a 40% target from a heavily overweight
sleeve always leaves far more than a sub-one-share remainder. Closing a
position through a trim is therefore only reachable when that position is a
minor part of its sleeve. That is correct behaviour rather than a limitation,
and it is pinned by a test so a later change does not "fix" it. Two of my
test fixtures failed on first write for exactly this reason.

## 5. Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Full settled tree: **4,017 passed / 0 failed / 25 known dependency
  warnings** in 595.63 seconds, with no concurrent edit.
- Focused: 36 trim tests, 20 UI tests.
- Mutation verification: **6 mutations, 6 detected** by exactly the intended
  test.
- `python -m compileall` and `git diff --check`: clean.

Always run the full suite through `.venv\Scripts\python.exe`; a bare
`python -m pytest` uses the user Python, which still has Streamlit 1.52.2 and
produces spurious UI failures.

## 6. Operational truth and owner decisions

- `paper-epoch-005` is active on the epoch host at frozen deployed commit
  `752d3b7`. Epochs 001 through 004 are closed and cannot pool evidence into
  it.
- Owner decision, 2026-08-14: epoch-005 runs unchanged for 60 days. Do not
  deploy, roll, or otherwise disturb it. TRADE-1, BUY-1, SET-1, STALL-1,
  HEDGE-1, and all three REBAL-1 stages remain development-only.
- Owner decision, 2026-08-15: the development `assistant/my_policy.json`
  carries `max_total_exposure_pct` 0.90 and `max_position_pct` 0.07 so the
  approved sleeve profile is reachable. It is untracked, so no commit
  contains it. **The operational checkout deliberately keeps 0.50/0.05** —
  `_active_runtime_lineage` computes the policy fingerprint from the live
  file and capture refuses on a lineage mismatch, so editing it during the
  hold would stall epoch-005 exactly as epoch-002 stalled. A later agent must
  not "finish the job" by copying it across.
- Sixty calendar days is roughly 43 weekday observations, not 60 sessions.
  Whether the owner's target means days or observations is still open.
- The owner may exercise this work with `scripts/launch_dev_app.ps1`; its
  scratch database and default environment kill switch prevent submission.
  `-AllowPaperOrders` reaches the shared Alpaca paper account and must not be
  used while the 60-day hold stands.
- CR-W3 remains a watch item: the first real AEP dividend subtype may fail
  closed around 2026-09-10 and require the reviewed acknowledgement path. Do
  not widen reconciliation tolerance or post a manual compensating entry.

No account identifier, balance, credential value, private artifact content, or
secret is recorded here.

## 7. What is next

1. Independent review of Stage 3. Suggested focus: whether the
   target-restoration cap is the right bound (versus the band edge), whether
   the incomplete-ledger refusal is too strict for a legitimately
   pre-app holding, and whether the realized-gain estimate should be
   recomputed at approval time rather than fixed at proposal time.
2. REBAL-1 has no further defined stages. Anything beyond Stage 3 needs a new
   plan.
3. Answer whether the 60-day decision means calendar days or 60 captured
   market sessions.
4. The SET-1 design question remains open: whether strict whole-share mode
   should permit a fractional sell only when it closes an entire position.
5. `TRADE1CR-002` remains open and unscheduled: date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` make the full suite unpassable
   between roughly 00:00 and 09:30 ET.

`docs/FEATURE_MILESTONE_RECORD.md` deliberately has no Stage 3 entry yet;
that file records work that has completed its definition of done AND its
required review.

Do not begin M4, mutate the operator database, alter scheduled tasks, access a
funded account, enable live trading, deploy, or roll an epoch without a new
explicit owner instruction.

## 8. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, docs/REBAL1_MILESTONE_PLAN.md,
and docs/SESSION_HANDOFF.md. main and origin/main are 45faf1c (PR #229).
Branch user/claude/rebal1-stage3-tax-aware-trims-20260815 implements REBAL-1
Stage 3, tax-aware trims, under the owner's explicit 2026-08-15 authorization
naming that stage. It is the first path where a rebalancing SELL originates
from the app's own arithmetic. The owner chooses sleeve, ticker, amount and
lot strategy, all starting unset; the plan shows the amount above band, the
target-restoration amount, per-lot holding periods, and the realized gain
split short/long. Five refusals: non-overweight sleeve, cash or residual,
a sale past target restoration, an incomplete tax ledger, and double-trimming
against a working sell. Execution-time profile binding now covers the trim
status. Full pinned-venv tree: 4,017 passed / 0 failed. Stage 3 has had NO
independent review. Do not deploy, roll the epoch, mutate the operator
database, begin M4, access a funded account, or enable live trading without
explicit owner authorization.
```
