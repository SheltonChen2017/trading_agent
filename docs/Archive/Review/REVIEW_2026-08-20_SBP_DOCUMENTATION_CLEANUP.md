# Independent review: SBP audit and documentation cleanup

- Date: 2026-08-20
- Reviewer: Codex
- Immutable submitted snapshot: `origin/main` at
  `13355a602f025270169866c27627d45363edbbc4`
- Prior reviewed/merged base: `c289f95b03095f117bbf918df843be4a671d97d4`
- Ordered submitted range: `c289f95..13355a6` (five commits, including both
  merge commits)
- Review branch: `codex/review-sbp-doc-cleanup-20260820`

## Verdict

**ACCEPTED AFTER CORRECTION.** Claude's cleanup is useful and mostly accurate:
it replaces the obsolete sequencing plan, corrects UI/page and archive-path
documentation, sustains the seven earlier SBP review findings, and identifies
real remaining concerns about industry concentration, overlay alignment, and
small-sample power planning.

The submitted tree nevertheless mixed up *valid null evidence* with invalid
runs, overstated the mathematical reach of the 15% look-through cap, and
offered exclusion of exactly-10-name months even though those zeros are the
true primary-strategy outcome. It also left the operative overlay comparison
gated by descriptive P4 availability, bundled two unrelated amendments, split
the amendment ledger into invalid Markdown, and retained stale current-state
claims in the handoff. The corrections preserve the Strong-Buy plan as a
draft; they adopt no threshold and create no execution authority.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `a2b69eb` — Refresh stale handoff topology and push-state claims | **Accepted after correction** | The merge-state repair was correct, but current alpha-program bullets remained stale and were later contradicted by the new closed-program header. The final handoff now separates legacy invalid runs from reviewed valid-null evidence. |
| `9009239` — Merge PR #283 | **Accepted** | The merge contains the submitted topology refresh without additional conflict-resolution changes. No issue was introduced by the merge itself. |
| `2c133cb` — Audit the SBP amendments review; propose SBPA-007..010 | **Accepted after correction** | The earlier seven-finding audit and SBPX-002/004/005/006 are sound. SBPX-001 was only partly correct, and SBPX-003's proposed exclusion would change the primary estimand. The later verification addendum preserves and corrects those dispositions. |
| `a77c6a5` — Replace the Action Plan with a Strong-Buy-first plan; sync docs to the code | **Accepted after correction** | The new plan and most code/document synchronization are correct. Current evidence validity, topology, amendment boundaries, plan-table rendering, and handoff state required correction. |
| `13355a6` — Merge PR #284 | **Accepted after correction** | The merge tree contains the reviewed audit/cleanup without hidden conflict-resolution changes; the cumulative final tree required the corrections recorded below. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SBDC-001 | P2 | Closed | `a77c6a5` | `docs/Archive/Plans/Alpha_Test_Implementation_Plan.md`; Action Plan §1 | The cleanup said no historical alpha result is valid while the permanent ledger marks reviewed Stage 0/1 runs `VALID` and records their null observations. This converts valid evidence of no detected edge into invalid evidence and contradicts the same Action Plan. | Ledger R-007..R-028 and A-001/A-002 distinguish `VALID` runs from a null verdict; APQ R-029/A-003 is also valid and null. The new red guard reproduced both stale literals. | Evidence validity is an authoritative research state; “null” and “invalid” are not interchangeable. | Current plans now say Stage 0/1 are **VALID but null**, APQ is valid-null in its separate family, legacy rows retain their individual statuses, and the lifetime alpha-cell floor is 452 at A-002. | New focused guard failed on the submitted tree and passes after correction. |
| SBDC-002 | P3 | Closed | `2c133cb` | SBP plan §5; audit SBPX-001/SBPA-007 | The audit called the 15% cap structurally unable to fire. P3 indeed cannot breach, but P4 can when the ordinary-fund issuer weight exceeds 36.7% at the maximum core weight; no contract caps that weight. Calling the gate corrupt-data-only could cause an unnecessary threshold change. | Direct inequality: `0.95*0.10 + 0.05*3*w > 0.15` when `w > 0.3667`; P3's maximum is 14.5%. Current holdings are not a proof of future contractual impossibility. | The owner needs the correct choice: retain a rare-tail P4 cap or adopt a lower routine cap. | SBPA-007 now distinguishes the impossible P3 breach from the possible P4 tail breach and removes the corrupt-data label. | Arithmetic and cross-document inspection; corrected audit addendum retained. |
| SBDC-003 | P3 | Closed | `2c133cb` | SBP plan §6/§11; audit SBPX-003 | The audit proposed excluding months with exactly ten names from P2−P1 and claimed zeros deflate both mean and variance. The zero is the strategy's true result; exclusion changes the estimand, and adding zero does not universally reduce sample variance. | At ten names the cap forces P1=P2. Conditioning on `n>10` answers a different question. A simple constant-positive nonzero sample gains, rather than loses, variance when a zero is appended. | Confirmatory sample membership cannot be made optional around a legitimate zero-return state. | Exactly-10-name months remain in primary P2−P1; an `n>10` decomposition is descriptive only. | New focused guard failed before and passes after correction. |
| SBDC-004 | P3 | Closed | `2c133cb` | SBP plan §6/§11 | The audit correctly found that descriptive P4 availability could delete valid inferential P3−P2 months, but left the contract as an owner-selectable ambiguity. | P3−P2 uses no P4 return; missing P4 mapping/evidence need not invalidate P2 or P3. | A descriptive variant must not shrink a confirmatory sample it does not enter. | P3−P2 now aligns on P2/P3; P4 is described against P3 only on P3/P4 dates. | Contract inspection and focused active-document suite. |
| SBDC-005 | P3 | Closed | `2c133cb` | SBP plan amendment ledger | SBPA-007..010 were separated from the Markdown table by a blank line, and the bootstrap-power requirement was bundled into unrelated SBPA-010. This obscured owner decisions and rendered part of the ledger outside its header. | Source inspection; new continuity guard raised `StopIteration`/failed on the submitted table. | The draft contract must remain mechanically readable and give each independent decision a stable identity. | Restored one contiguous SBPA-001..011 table and separated bootstrap power as SBPA-011. | Red/green continuity guard. |
| SBDC-006 | P3 | Closed | `a77c6a5` | Action Plan topology; Session Handoff §§0,1,8,9 | The current-state documents still described pre-PR heads/branches and an obsolete alpha contract/current-run count after PR #284. The resume prompt also reopened already merged LEV/SBR review work. | Git shows exact `origin/main=13355a6`; ledger contains 30 run-level looks and valid-null observations; current Action Plan closes the alpha program. | Cross-computer resumption must start from the actual published tree and must not reopen closed work. | Action Plan records the immutable review-start head; the final handoff records this review branch, current evidence state, corrected next step, and a fresh resume prompt. | Git ancestry/status checks plus active-document tests. |

No P0 or P1 findings were identified. No product behavior, schema, CLI,
migration, research result, QuantConnect run, broker state, scheduled task,
deployment, evidence epoch, or operational database changed.

## Validation

- Red proof: the three new focused guards failed **3/3** on the submitted
  document state.
- Focused corrected suite:
  `tests/test_active_document_consistency.py` plus
  `tests/test_proposal_outcome_groups.py`: **50 passed** in 2.52 seconds.
- Full suite after the substantive corrections: **4,351 passed, 25 warnings**
  in 947.30 seconds. The exact final-tree rerun after the handoff is recorded
  in `docs/SESSION_HANDOFF.md`.
- Python **3.13.14**; required `compileall` surface plus `research/`: **PASS**;
  `git diff --check`: **PASS**.

## Standing

SBP remains **DRAFT**. The owner still must adopt every proposed section-2
value and decide the unresolved SBPA-007/008/011 choices before SBP-0 can
freeze. No capture task installation, price join, QC run, paper order,
deployment, or live authority is granted by this review.
