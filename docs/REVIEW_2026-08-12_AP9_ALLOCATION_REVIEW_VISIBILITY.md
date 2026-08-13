# Independent review — AP-9 allocation-review visibility

Date: 2026-08-12

Final disposition: **accepted after correction; not deployed**

## 1. Exact review snapshot

- Submitted base: `cea6640` (then-local `main`, PR #193 merge).
- Submitted branch: `user/claude/allocation-review-visibility-20260812`.
- Submitted implementation: `3f1faf3`.
- Reviewed range: `cea6640..3f1faf3` (one commit).
- Review branch: `codex/review-ap9-allocation-visibility-20260812`.
- Review correction: `6295b2f`.
- Current remote main observed during review: `origin/main` at `27fa872`
  (PR #194, AP-8). The AP-9 submission predates that merge; integration with
  current main remains required before AP-9 can merge.
- Availability at review close: Claude's branch is pushed; the Codex review
  branch and correction are local-only. No push, PR, merge, deployment, task
  change, epoch mutation, or operator-database write was authorized or made.

## 2. Commit-by-commit disposition

| Commit | Intent | Disposition | Notes |
|---|---|---|---|
| `3f1faf3` | Remove unsupported allocation-review prose caps and make every absent review explain itself in the Buying UI | **Accepted after correction** | The root-cause diagnosis, removal of the 500/300-character caps, retained content validation, compatibility wrapper, sanitized failure text, audit behavior, and initial AppTests were sound. Review corrected one material stale-state defect and four minor contract/honesty issues listed below. |

## 3. Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| AP9R-001 | P2 | Resolved | `3f1faf3` | `scripts/personal_assistant_ui.py`, Buying allocation-review state | A review remained visible after the max-weight slider or another split input changed. Its validated numbers could therefore describe the old split while the page presented them as checked against the new split. | A real AppTest seeded a valid 66.7/33.3 review, changed the slider to 50/50, and proved the old summary still rendered with no warning on the submitted tree. | This violated the feature's core truthfulness contract and AP-9 definition of done: displayed numeric commentary must be checked against the split currently shown, not a prior rerun's input. | Added a canonical allocation-review input identity over ordered cart tickers, weights, volatilities, and basket memberships. Every outcome carries that hash; the UI compares it on every rerun, hides stale output, and asks for a fresh review. Missing legacy hashes fail safely as stale. | Reviewer test failed red, then passed green in `tests/test_ui_allocation_review.py::test_review_is_not_displayed_against_a_changed_split`; full suite passed. |
| AP9R-002 | P3 | Resolved | `3f1faf3` | `assistant/ai_advisor.py::AllocationReviewOutcome` | The public outcome type claimed that contradictory states were unrepresentable, but allowed both fields to be absent or both present. | Two parameterized constructor cases both failed to raise on the submitted tree. | The type is AP-9's replacement for ambiguous absence; leaving its defining invariant as a caller convention would permit the same ambiguity to return. | Added `__post_init__` XOR enforcement and a required non-empty input identity. | Both red cases now pass; all production constructors and tests use valid states. |
| AP9R-003 | P3 | Resolved | `3f1faf3` | `assistant/ai_advisor.py::review_allocation_outcome` | JSON arrays/scalars parsed successfully, then raised `AttributeError` in the validator and were reported as “The call to Claude did not complete.” | A mocked `[]` response produced `REVIEW_REJECTED_CALL_FAILED(AttributeError)` on the submitted tree. | The API call did complete; blaming transport hid a response-shape failure and made the new user-visible reason dishonest. | Reject non-object JSON immediately as `REVIEW_REJECTED_UNPARSEABLE` and audit the exact structural failure without exposing it in the UI. | Red/green mocked-response regression passed. |
| AP9R-004 | P3 | Resolved | `3f1faf3` | `assistant/ai_advisor.py::review_allocation_outcome` | An empty cart with a configured key returned “No Anthropic credential is configured.” | Direct configured-key regression reproduced the false reason. | AP-9 promises that every absence reports what happened; the stated cause must match the input state. | Added `REVIEW_REJECTED_NO_INPUT` and separated the empty-input and unconfigured branches. | Red/green direct regression passed. |
| AP9R-005 | P3 | Resolved | `3f1faf3` | `assistant/ai_advisor.py` validator documentation; touched Buying dataframes | The validator docstring still claimed string-length caps existed, and both AP-9-touched dataframes used Streamlit's removed `use_container_width` argument, producing deprecation warnings under the pinned Streamlit 1.60. | Source inspection plus warnings emitted by the reviewer AppTest. | Stale documentation misstates the accepted safety model; leaving a removed UI argument in newly touched code creates avoidable framework drift. | Documented full-text content checking with the upstream token bound and replaced the two touched calls with `width="stretch"`. | Compile, focused tests, and full suite passed; those AP-9 dataframe deprecation warnings no longer appear. |

No P0 or P1 issue was found. No finding remains open in the reviewed AP-9
scope.

## 4. What was correct in the submitted work

Claude's diagnosis was strong and unusually evidence-driven. The two valid
operator reviews were rejected only by undocumented prose-length limits; the
actual allocation safety checks inspect the complete output, and the
Anthropic request already has an 800-token generation bound. Removing the
500-character summary and 300-character claim caps therefore restores valid
commentary without weakening the rules against invented numbers, dollar
amounts, out-of-cart tickers, number misattribution, or action language.

The compatibility choice was also good: `review_allocation_plan()` retains its
old `AllocationReview | None` facade, while the UI opts into the richer
`review_allocation_outcome()` contract. Failure messages expose exception type
but not exception text, audit writes remain best effort, and no AI output gains
proposal, approval, policy, broker, scheduler, or order authority.

## 5. Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted focused baseline: **159 passed** in 10.92s
  (`test_ai_advisor`, submitted three UI tests, and ML import boundary).
- Reviewer red proof on uncorrected `3f1faf3`: **5 failed, 151 passed** in
  10.36s. The five failures covered two invalid outcome states, wrong-root
  JSON, empty-input reason, and stale UI commentary.
- Corrected focused/import-boundary suite: **164 passed** in 12.30s.
- Corrected full repository suite: **3,445 passed, 0 failed, 0 skipped, 25
  known dependency warnings** in 633.40s.
- `compileall -q assistant scripts tests`: clean.
- `git diff --check`: clean apart from informational Windows LF-to-CRLF
  working-copy notices.

The live Anthropic service and visual layout of a genuinely long response were
not exercised; tests mock the provider. The page behavior itself is covered
through Streamlit `AppTest`, including the actual slider rerun.

## 6. Genuine quality assessment

**7.5/10 for the submitted AP-9 implementation.** Claude found the real root
cause, used operator evidence correctly and read-only, preserved the public
facade, retained the meaningful content checks, and made failures visible with
good behavioral tests. That is solid work. The material deduction is for not
binding a persisted AI result to the split it described: Streamlit reruns make
that lifecycle case central, and the page's “every number checked” statement
became false after one slider movement. The remaining deductions are for
small but concrete honesty and contract gaps. With `6295b2f`, the reviewed
scope meets AP-9's definition of done.

## 7. Safety and deployment conclusion

AP-9 is advisory UI behavior only. It does not create or alter weights, write
policy, create or approve proposals, submit orders, contact the broker for
execution, modify scheduled tasks, or change live-trading authority. It is not
deployed into `paper-epoch-004`, whose frozen runtime remains `b837374`.
Merging development code does not authorize an epoch roll; any deployment or
new epoch still requires a separate explicit owner instruction.
