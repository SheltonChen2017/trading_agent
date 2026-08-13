# Session handoff — SELL-1 reviewed, counter-reviewed, and pushed

Prepared: 2026-08-13, after Codex's independent SELL-1 review and Claude's
counter-review of it.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md` (SELL-1, AP-11, GR-7d)
3. `docs/REVIEW_2026-08-13_SELL1_AND_BRANCH_CLEANUP.md`
4. `docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md`
5. `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md`
6. `docs/OPERATIONAL_FACTS.md`

Nothing here authorizes deployment, an evidence-epoch roll, M4, live trading,
operator-database mutation, or any funded action.

## 1. Repository topology

- Review base/head: `c3d10ff`, which is both local `main` and `origin/main`
  as observed when this review began. It merges PR #203 (SELL-1) and PR #204
  (branch-cleanup documentation).
- Implementation: `918eecd`; integration merge with reviewed M3: `dc1233a`;
  mainline SELL-1 merge: `08fde9f`.
- Review branch: `codex/review-claude-sell1-cleanup-20260813`.
- Review correction: `3ba3d41`.
- Claude's counter-review commit follows `e3931e0` on the same review
  branch, carrying the counter-review section, the SELCR-001 consolidation,
  its regression, and this handoff revision.
- **The branch is pushed after the counter-review**, deliberately superseding
  the pre-push local-only statement rather than leaving it to go stale.
  Merging its PR is the owner's action.
- Current fetched refs also show the documentation-cleanup topic ref, but the
  former SELL-1, M3 implementation, and M3 review topic refs are absent. Their
  required work is already merged to `main`; do not recreate or merge them.

## 2. Review outcome

Final disposition: **accepted after correction**. Submitted implementation
quality: **7/10**. Commit dispositions:

- `918eecd`: accepted after correction (SELREV-001 through SELREV-004).
- `dc1233a`: accepted after correction in the cumulative tree; no
  integration-specific loss found.
- `08fde9f`: accepted after correction in the cumulative tree; current-state
  documentation corrected.
- `cbb38cb`: accepted after correction (BRREV-001 and incomplete topology
  synchronization).
- `c3d10ff`: accepted after correction in the cumulative tree; merge-only.

Issue summary: **0 P0, 1 P1, 3 P2, 2 P3; all resolved**. The full ledger and
red/green evidence are in the review report.

The P1 mattered: exact broker shares of `10.999999999999999999` became the
display float `11.0`, and both proposal creation and the shared execution gate
authorized an 11-share sale. `3ba3d41` makes exact broker quantity govern both
boundaries. The same correction also uses Decimal for `max_order_value`,
reports fractional remainders truthfully, and hides an old proposal card when
the selected quantity changes.

## 2b. Counter-review outcome (Claude, 2026-08-13)

All six review findings **confirmed genuine**, each reproduced independently:
`float("10.999999999999999999")` really is `11.0` (SELREV-001, a P1 in
Claude's submitted code and a plain violation of CLAUDE.md §5's ban on binary
floating point in money paths), and `3 * 0.10` really does exceed a `0.30`
cap in float arithmetic (SELREV-002 — the submitted boundary test passed only
because it used binary-friendly numbers). No test was weakened.

One further finding, **SELCR-001 (P2), resolved on the review branch**: the
gate hardening was only half the fix. `risk/execution_gate.py` now refuses a
sell of 11 against an exact holding of 10.999999999999999999, but both older
generators still floored the display float and kept proposing 11 — so a
legitimate RISK-REDUCING sell could never be approved and the position stayed
over its cap with no in-app remedy, the exception CLAUDE.md §5 names by name.
Reproduced end to end, then fixed by consolidating the exact floor into
`assistant.proposals.sellable_whole_shares` for all three generators.

## 3. Validation

Environment: repository virtual environment, Python 3.13.14 / Streamlit
1.60.0.

- Submitted-tree red proof: **6 failed, 49 passed**, all for the intended
  findings.
- Corrected broader focused suite: **391 passed** in 36.40 s.
- Documentation-complete full suite: **3,618 passed, 0 failed, 0 skipped,
  25 known dependency warnings** in 669.76 s.
- After recording the measured result: active-document suite **21 passed**;
  ML import-boundary tests, compileall including `research`, `git diff
  --check`, staged checks, narrow secret-shape scan, and final status passed.

## 4. Operational truth

- `paper-epoch-004` remains the only active evidence epoch, frozen at
  `b837374` in `C:\git\trading_agent_operational` according to the current
  verified records. This review did not inspect or mutate that clone or its
  database.
- SELL-1, M3, AP-8, AP-9, QC-2, AP-10, and AP-11 remain development changes
  not deployed into that frozen epoch.
- CR-W3 remains unchanged: the first real AEP dividend subtype may over-refuse
  safely around 2026-09-10; JNLC still requires operator judgement. Never
  widen reconciliation tolerance or use a manual compensating entry.
- The deleted GR-7d equal-weight branch is not reachable from current refs.
  This checkout currently retains dangling tip `85a77291...`, but it is
  local-only, may be pruned, and does not restore the superseded decision.

## 5. Completed scope and exclusions

SELL-1 now prepares one explicit owner-directed whole-share sell proposal for
a held ticker through the existing typed-approval and paper-only execution
pipeline. It remains distinct from policy-breach recommendations and retains
tax-advisory disclosure.

No schema or migration changed. No limit, fractional, conditional, scheduled,
or multi-ticker sell was added. Nothing auto-submits. No ML/LLM authority,
policy cap, broker outcome, scheduler, deployment, live-account support, or
evidence status changed.

## 6. Next step

The review loop is complete: implemented, independently reviewed,
counter-reviewed, and pushed. The remaining action is the owner's merge of the
review branch's PR. Do not deploy or roll `paper-epoch-004` as part of that
Git action. M4 remains deferred unless
the owner explicitly schedules it. Open owner decisions remain epoch-roll
timing, the physical-media-only off-machine backup, and whether to preserve or
allow pruning of the dangling superseded GR-7d objects.

## 7. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, and
docs/REVIEW_2026-08-13_SELL1_AND_BRANCH_CLEANUP.md including its
counter-review section. Confirm whether
codex/review-claude-sell1-cleanup-20260813 has merged; it was pushed and
awaiting the owner's merge at handoff. Do not deploy, touch the
operator database, roll paper-epoch-004, restore deleted branches, or begin M4
without a new owner instruction.
```
