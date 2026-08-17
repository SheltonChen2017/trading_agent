# Independent review — REBAL-3V feasibility visibility and REBAL-3W refusal accuracy

Date: 2026-08-15
Reviewer: Codex
Remote reviewed: `origin/main`
Base: `84e73afafbdff62fb7a06c1b587b6a1b258bc253`
Exact submitted head: `006a9d5a887f6fc6da8a4978e1ac2680e941c783`
Review branch: `codex/review-rebal3v3w-20260815`
Product/test correction: `3a506ae39f7186fc065d04cd60beedeb4c4e2fbb`
Status: **Accepted after correction; not pushed, merged, or deployed.**

## Scope and method

The owner identified two rounds that had reached `main` without independent
review and named the literal range `84e73af..006a9d5`. Review began only after
fetching the remote and resolving `origin/main` to the exact submitted head.
All eight commits in the literal range were read separately. For each merge,
the result was compared with both parents and the combined diff was inspected;
all three merge trees equal their second-parent trees, so none contains a
hidden conflict-resolution change.

The review used the repository's pinned Python environment and the installed
Streamlit 1.60 guidance. The relevant native `st.container`, `st.dataframe`,
`width`, copy, and data-payload choices are appropriate. The policy filename
shown below the table is only the basename already displayed in the sidebar;
no policy contents or absolute path are sent by this change.

## Commit-by-commit dispositions

| Commit | Disposition | Evidence and issue mapping |
|---|---|---|
| `7e9d005` | **Accepted after correction `3a506ae`.** | The width-independent positive/negative feasibility block is correct and changes presentation only. R3VW-001 closed two weak tests added here: one test had no executable body, and another accepted either mutually exclusive branch while claiming to prove the positive branch. No calculation, band, conflict, proposal, or execution contract changed. |
| `a0a657b` | **Accepted after correction.** | The feasibility report and topology repair are materially accurate for their then-current branch, but their validation narrative inherited R3VW-001's overstated test sensitivity. The final independent report and round document addendum replace that evidence. |
| `8ee5f39` | **Accepted after correction.** | PR #231's merge tree is byte-for-byte its second-parent tree and adds no conflict resolution. It inherits R3VW-001 and the corresponding correction; no separate merge defect was found. The merge subject names the later trim branch even though this merge contains the feasibility round, but commit ancestry and the explicit dispositions remove the ambiguity. |
| `bead8ac` | **Accepted after correction `3a506ae`.** | The refusal now correctly distinguishes nothing overweight from only untrimmable sleeves overweight, and eligibility itself is unchanged. R3VW-002 closes the still-ambiguous helper API by returning both overweight partitions together; R3VW-003 corrects a sentence that falsely called every profile-described sleeve inside/below while cash, which the profile describes, was explicitly overweight. |
| `43b29df` | **Accepted after correction.** | The round report accurately records the original owner-visible contradiction and the corrected refusal direction. Its references to the two-helper design and original focused count are superseded by the independent-review addendum and R3VW-002's single classification result. No new product issue was introduced by this records commit. |
| `18a3ee5` | **Accepted after correction.** | PR #232's merge tree is byte-for-byte its second-parent tree and contains no conflict-resolution change. It inherits R3VW-002 and R3VW-003; no separate merge defect was found. |
| `bacc66f` | **Accepted after documentation correction.** | The post-merge status update correctly says both rounds still needed review, but R3VW-004 confirms its topology rewrite split the operational-runtime sentence and attached its second half to the BUY-1 bullet. Product behavior is untouched. |
| `006a9d5` | **Accepted after documentation correction.** | PR #233's merge tree is byte-for-byte its second-parent tree and contains no conflict-resolution change. R3VW-005 closes the resulting final-tree topology drift: the action plan and handoff still named `18a3ee5` and the records branch after `006a9d5` had become the exact main head. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| R3VW-001 | P3 | Closed | `7e9d005` | `tests/test_ui_portfolio_rebalance.py` | New feasibility coverage overstated what it proved: one collected test executed no assertion, while the positive-case test passed for either the positive or negative branch and depended on an ignored machine-local policy. A regression could remove the positive confirmation while the tests stayed green. | The submitted focused suite passed 106 tests. Removing the no-op changed no behavior, and source inspection showed the `A or B` assertion accepted both exclusive outcomes. | The round's purpose is to make both feasibility outcomes explicit; a test that cannot distinguish them does not protect the user-visible contract and makes the validation claim inaccurate. | Removed the empty test; forced a known permissive policy for the positive branch; retained an exclusive negative assertion; and parameterized all four real conflict rules, including each row's `Reachable = no` value. | The deterministic positive test passed; all total-exposure, leveraged-cap, cash-floor, and position-cap UI cases passed. |
| R3VW-002 | P3 | Closed | `bead8ac` | `assistant/rebalance_trim.py` | Adding `untrimmable_overweight_sleeves()` beside a generically named `overweight_sleeves()` left the root ambiguity in the API. A caller could still read the latter as the complete overweight set and repeat the same false refusal. | The submitted UI had to call the two helpers separately, and `overweight_sleeves()` continued to exclude cash/residual despite its unqualified name. The handoff itself identified this recurrence risk. | This exact conflation already produced an owner-visible false statement. Returning both partitions together makes omission explicit and removes the misleading generic helper. | Replaced both helpers with immutable `OverweightSleeveClassification` from one `classify_overweight_sleeves()` pass; the planner and UI consume its named `trimmable`/`untrimmable` fields. | Import regression was red before implementation. Unit coverage now pins trimmable-only, untrimmable-only, empty, and simultaneous mixed groups; all REBAL-focused tests pass. |
| R3VW-003 | P3 | Closed | `bead8ac` | `scripts/personal_assistant_ui.py` | The corrected refusal ended by saying every sleeve the profile describes was inside or below its band, even while the same message named cash—an explicitly profiled sleeve—as overweight. | A real-report AppTest with 50% cash and 50% residual rendered the contradictory sentence; the new assertion failed red on the submitted copy. | A refusal meant to restore truthful explanations must not replace one contradiction with another, especially on the exact owner-reported portfolio shape. | The sentence now says every sleeve the workflow is allowed to trim is inside or below its band, which is exactly what the classification establishes. | Red/green AppTest on the reproduced cash/residual-only book. |
| R3VW-004 | P3 | Closed | `bacc66f` | `docs/SESSION_HANDOFF.md` | A topology rewrite left “The operational checkout remains separate and frozen at `752d3b7` in” incomplete and attached “active `paper-epoch-005`...” to the BUY-1 history bullet. This corrupts the canonical resume record. | Direct reading of §1 at the submitted head reproduces the split sentence. | The handoff is the cross-computer authority; malformed operational state can be misread during a later deployment or epoch decision. | Restored one complete operational-runtime bullet and separated the BUY-1 history cleanly. | Active-document consistency tests and final manual topology read. |
| R3VW-005 | P3 | Closed | `006a9d5` | `docs/ACTION_PLAN_2026-08-02.md`, `docs/SESSION_HANDOFF.md` | The final merged tree still named `18a3ee5` as main/origin main, named the now-merged records branch as current, and said independent review was outstanding. | Fetched `origin/main` resolved to `006a9d5`; the submitted documents did not. | Stale topology and review status can make the next agent review the wrong range or repeat completed work. | Recorded the exact reviewed base/head, local review branch and correction, all eight dispositions, issue summary, and no-push state; marked both rounds accepted after correction. | SHA resolution, document-consistency tests, and final handoff review. |

Issue summary: **0 P0, 0 P1, 0 P2, 5 closed P3, 0 open.**

## Functional and safety disposition

REBAL-3V correctly makes target feasibility readable outside the wide table.
When no conflict exists it positively says every target is reachable; when a
known structural policy conflict exists it names the affected sleeve and exact
reason while retaining the per-row yes/no value. Independent coverage now
drives all four implemented conflict rules rather than only total exposure.

REBAL-3W correctly leaves trim eligibility unchanged while making an empty
trim choice truthful. Cash and residual remain untrimmable; no proposal size,
tax-lot rule, typed approval, policy gate, execution dependency, broker call,
or order-submission path changed. The correction only makes the complete
overweight classification harder to misuse and fixes explanatory copy.

No schema, migration, durable proposal identity, policy fingerprint, evidence
epoch, scheduler, operator database, broker account, order, or deployment was
mutated. The allocation targets remain owner preference, not research evidence
or a profit claim. The operational runtime remains frozen at `752d3b7` in
active `paper-epoch-005` under the owner's 60-day hold.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Submitted-head baseline: **106 passed** across trim, rebalancing UI, and
  active-document consistency tests.
- R3VW-003 reproduction: **1 failed / 1 passed**, then **2 passed** after the
  copy correction.
- R3VW-002 API regression: failed import during collection before the new
  classifier existed, then passed after implementation.
- Corrected REBAL-1 focused set: **192 passed** across report, steering, trim,
  real-fill end-to-end, and Streamlit UI tests.
- Corrected trim/UI set: **79 passed**; the submitted no-op is gone while the
  four policy-conflict cases and mixed classification are now independently
  collected.
- Final full suite: **4,051 passed / 0 failed / 25 known dependency warnings
  in 719.51 seconds**. The warnings are the existing `websockets.legacy` and
  NumPy/joblib deprecations.
- Final compilation, active-document, and diff checks: clean; the exact
  commands and records commit are also captured in `docs/SESSION_HANDOFF.md`.

## Remaining scope

No open issue remains in these two rounds. The pre-existing gap that no test
clicks the Streamlit trim button through proposal persistence remains outside
this owner-reported presentation/refusal review; the lower real-fill path is
covered end to end. REBAL-1 still has no Stage 4. No push, merge, deployment,
paper order, operator-database mutation, epoch roll, or live authority is
authorized by this review.
