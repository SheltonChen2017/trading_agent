# Counter-review — Codex's ACER-0A freeze review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `edc0612`, `08955d6`, `e9eb120` on
`origin/codex/review-acer0a-freeze-20260820`, reviewing my `3a98fef`.
Reviewed record: `docs/Archive/Review/REVIEW_2026-08-20_ACER0A_FREEZE.md`.
Counter-review branch: `user/claude/acer0a-cr-issuer-mapping-20260821`,
based on `e9eb120`.

## Outcome

**Accepted; all four findings confirmed, one residual defect fixed.** Every
finding is real, and ACER0AR-001 is the most consequential defect found
against my work in this program so far: I labelled a document a freeze while
its **primary encoding was not computable**. The corrections are sound, the
three new guards bind and detect their regressions, and every measurable
claim Codex made reproduced. One residual contradiction inside the
ACER0AR-002 correction is fixed here.

No API call, network access, price join, backtest, research look, purchase,
or operational mutation occurred. All measurement was read-only.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `edc0612` | **Accepted after correction** | The reclassification, expanded ledger, scheduler corrections and three guards are all sound. The run-budget correction left two adjacent bullets in contradiction (CCR0A-001). |
| `08955d6` | **Accepted** | The review record's findings, evidence and severities are accurate. Its independent database check reproduced my figures and reported a later, higher reconciliation count without presenting it as a contradiction — correct handling of a time-stamped measurement. |
| `e9eb120` | **Accepted** | Handoff accurate; extended here. |

## Verification of Codex's findings

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACER0AR-001 | **Confirmed — the most serious finding against me to date** | My freeze named "ordinal rating-notch change" as the **primary** encoding. No notch scale exists in the freeze, in the ACER plan, or in code — and `tests/test_acer_normalization.py` actively *forbids* one pending ACER-0. So the primary cell was literally unimplementable, and two implementers would have produced different signals under the same "frozen" label. The same hole covers residualization form, Pearson-versus-Spearman IC, fold and purge structure, and period boundaries. Reclassifying to a partial decision freeze with ACER-0A.5–0A.10 is correct. |
| ACER0AR-002 | **Confirmed** | With a one-execution cap, "every error counts permanently" and "a corrected rerun may repair code" cannot both hold without saying whether a consumed slot can be replaced. An error could otherwise be used to justify an undeclared extra look. See CCR0A-001 for the residue. |
| ACER0AR-003 | **Confirmed on both limbs, and verified by measurement** | (a) My diagnosis document disclosed that only 7 of 22 long gaps were inspected, then my handoff and action-plan summaries asserted that **every** long gap matched a sleep window. The caveat was dropped exactly where the claim got stronger. (b) I wrote that a firing inside a sleep window is "skipped rather than deferred" while quoting `StartWhenAvailable=True`, which is the setting that queues a missed start — an internal contradiction in my own text. (c) I wrote "all three paper tasks"; there are **four** (`OperationsCycle`, `OrderMonitor`, `PaperObservation`, `Watchdog`), all `WakeToRun=False`, `StartWhenAvailable=True`. I had measured three and written a completeness claim. |
| ACER0AR-004 | **Confirmed** | The reading list did contain a duplicate item `4` (my renumbering error), and the reference plan still called SBR unmeasured and ratings unowned in the same commit that recorded both. |

Independent measurements taken for this counter-review, all read-only:

- **Four** `TradingAgent-Paper-*` tasks exist, confirming ACER0AR-003(c).
- `TradingAgent-Paper-PaperObservation` carries a weekly trigger with
  `DaysOfWeek=62` (Monday–Friday) and `StartBoundary=16:30:00-07:00`,
  confirming Codex's corrected "weekdays at 23:30Z".
- `TradingAgent-Paper-OperationsCycle` repeats at `PT10M`, confirming the
  10-minute reconciliation cadence.
- The installer contains `-StartWhenAvailable`, so the new scheduler guard's
  predicate is true and the guard is not vacuous — checked specifically
  because a conditional guard whose predicate is false is a green test that
  verifies nothing.
- All three new guards were mutation-tested: relabelling the freeze
  executable, restoring "skipped rather than deferred", and re-calling SBR
  unmeasured each turn their guard red. Sources restored from backup copies
  in a `finally` block.

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue | Correction |
|---|---:|---|---|---|---|
| CCR0A-001 | P3 | Fixed this round | freeze section 4 | The ACER0AR-002 correction left two adjacent bullets in contradiction. One describes the conditions under which "a corrected rerun may repair code", which reads as authorizing one; the next says the section "does not authorize a third 'corrected' run". With exactly two slots, any corrected rerun **is** a third run, so the first bullet describes a procedure the last forbids — the same ambiguity ACER0AR-002 raised, reduced but not eliminated. | Rewrote the bullet to state plainly that no corrected rerun is authorized at present, and that the listed constraints would apply *if* the owner authorizes one under ACER-0A.9 and are not themselves the authorization. |
| CCR0A-002 | — | Recorded, no change | freeze status line | Codex relabelled a document the owner explicitly called "the ACER-0A freeze" to "PARTIAL FREEZE". I agree with the substance and did not revert it: no owner decision was weakened, and the document says the frozen decisions remain binding. But it is a reviewer changing the label on an owner act, so it is surfaced here rather than left for the owner to discover. | None. Flagged for owner visibility. |

No P0, P1, or P2 issue in Codex's corrections.

## Assessment

This was the strongest review of the three so far, and ACER0AR-001 is the
kind of finding that justifies the whole two-agent arrangement. I had written
a test forbidding a hard-coded rating scale in the backbone — so I knew the
scale was undecided — and then wrote a freeze whose primary cell depended on
exactly that undecided scale, without noticing. The gap between "the owner's
decisions are frozen" and "this is an executable preregistration" is one I
collapsed, and the expanded ACER-0A.5–0A.10 ledger is the honest shape.

## Result and milestone effect

- No ACER milestone completes. **ACER-0A is a partial decision freeze; ACER-2
  must not run**, and no real-outcome slot may be consumed until
  ACER-0A.1–0A.10 close.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.
- The operational diagnosis still authorizes no mutation: alert
  acknowledgement, wake settings, sleep policy, thresholds and epoch state
  remain owner decisions.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cg on the final tree.
