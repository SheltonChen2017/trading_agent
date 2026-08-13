# Session handoff — AP-9 reviewed, counter-reviewed, and integrated

Prepared: 2026-08-12, after independent Codex review of the AP-9
allocation-review visibility fix, Claude's counter-review with two further
corrections, and integration of current `origin/main` (AP-8) into the review
branch.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0. Read this first

Read, in order:

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md` (§6 AP-8 and AP-9)
3. `docs/OPERATIONAL_FACTS.md`
4. `docs/REVIEW_2026-08-12_AP9_ALLOCATION_REVIEW_VISIBILITY.md`
5. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
6. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`

The action plan is the sequencing authority. Operational facts are the
append-and-amend machine/epoch record. Do not reconstruct either from chat
memory.

## 1. Repository and branch topology

- `origin/main`: `27fa872` (PR #194, merged AP-8 review).
- Submitted AP-9 base: `cea6640` (PR #193 merge; predates AP-8's merge).
- Submitted branch: `user/claude/allocation-review-visibility-20260812` at
  `3f1faf3` (pushed).
- Review branch: `codex/review-ap9-allocation-visibility-20260812`, in order:
  - `6295b2f` — Codex review correction (AP9R-001..005).
  - `75e8167` — Codex review/action-plan/milestone/operational-facts docs.
  - `d82037d` — Codex handoff.
  - `9d5e134` — Claude counter-review correction (AP9CR-001, AP9CR-002).
  - a merge of `origin/main` `27fa872` resolving documentation-only conflicts
    (both AP-8 and AP-9 records preserved; this replacement handoff and final
    validation follow it as the branch tip — use `git log` for exact ids).
- The integration the Codex review flagged as outstanding is therefore done:
  this branch now contains AP-8's merged records and AP-9, and the PR to main
  should be conflict-free.

## 2. Review outcome (Codex)

**Accepted after correction.** Five findings, all closed by `6295b2f`:

- **AP9R-001 — P2:** a review stayed visible after the split changed (slider
  rerun), presenting numbers validated against the old split as if checked
  against the new one. Every outcome now carries a SHA-256 identity of the
  exact cart/weights/volatilities/baskets; the UI hides stale output and asks
  for a fresh review; missing legacy hashes fail safe as stale.
- **AP9R-002 — P3:** `AllocationReviewOutcome` promised an XOR invariant it
  did not enforce; `__post_init__` now raises on contradictory states.
- **AP9R-003 — P3:** a JSON array/scalar root raised `AttributeError` in the
  validator and was blamed on transport; non-object roots now report as
  unparseable.
- **AP9R-004 — P3:** an empty cart with a configured key claimed no
  credential was configured; a distinct no-input reason now exists.
- **AP9R-005 — P3:** the validator docstring still claimed length caps
  existed, and the two touched dataframes used removed
  `use_container_width`; both corrected.

## 3. Counter-review outcome (Claude)

All five findings verified and accepted — each re-established by mutation
(reverting each correction reddens exactly the reviewer's test). AP9R-005's
stale docstring claim and missed deprecations were Claude's own errors in
code touched the same day, and are acknowledged as such in the review report.

Two further defects found and fixed in `9d5e134`, both generalizations of
review findings:

- **AP9CR-001 — P3:** AP9R-003 guarded the JSON root but not the fields.
  `observations` as null or a number raised `TypeError` into the broad
  except and was reported as a failed call; a string iterated silently into
  the misleading all-observations-failed reason. A non-list `observations`
  now reports as unparseable; an absent key still yields a valid
  summary-only review, pinned so the guard cannot over-reject.
- **AP9CR-002 — P3:** the identical stale-state defect AP9R-001 fixed
  existed one block above it: `watchlist_ai_suggestions` stored no cart
  identity, so suggestions and their measured-evidence columns rendered
  under an expander header naming the *current* cart after an edit. The
  stored state now carries its normalized cart; a mismatch hides the
  suggestions with a stated reason; legacy state fails safe as stale.

One probe artifact recorded so it is not rediscovered as a bug: a summary
consisting of "A calm split." is rejected because the standalone word "A" is
ticker-shaped — the hallucinated-ticker guard's long-standing conservative
design, not an AP-9 regression.

## 4. Validation

Repository `.venv`, Python 3.13.14, Streamlit 1.60.0, on the final integrated
tree (after the merge of `origin/main`):

- Full repository suite: FULL_SUITE_RESULT
- Focused: `tests/test_ai_advisor.py` 156 passed;
  `tests/test_ui_allocation_review.py` 6 passed.
- Every correction on this branch — the reviewer's four code corrections and
  both counter-review fixes — mutation-verified to redden exactly its own
  test, restored in a `finally` block.
- `compileall` clean; `git diff --check` clean apart from expected Windows
  LF→CRLF notices; active-document guards pass.

Untested: the live Anthropic call (all tests mock the client) and the browser
rendering of a genuinely long review, which needs a deployed build.

## 5. Operational truth — do not disturb the epoch

- `paper-epoch-004` is the only active evidence epoch; its deployed runtime
  is `b837374` in `C:\git\trading_agent_operational`, which none of this
  branch touches.
- Merging to `main` does not affect the epoch: all four
  `TradingAgent-Paper-*` scheduled tasks run from the operational checkout,
  and deployment is a separate deliberate step requiring explicit owner
  authorization and the epoch-swap runbook.
- AP-8 and AP-9 are merged-or-mergeable development code, **not deployed**.
  They should ride the next owner-authorized roll (CR-W2/AP-7 are already
  queued for the same roll before 2026-09-10).
- The point-in-time epoch observation from AP-9's diagnosis (1 observation,
  0 orders, 5/5 drills, 5 network-caused open alerts, books matched all day)
  is recorded in `docs/OPERATIONAL_FACTS.md`; re-measure read-only before
  any operational decision.

## 6. Next step

The branch is ready for the owner's merge decision
(`codex/review-ap9-allocation-visibility-20260812` → `main`); the integration
merge is already done, so the PR should apply cleanly. Merging does not
authorize deployment.

## 7. Resume prompt

```text
Fetch origin and switch to codex/review-ap9-allocation-visibility-20260812.
Read CLAUDE.md, docs/SESSION_HANDOFF.md, docs/ACTION_PLAN_2026-08-02.md (§6
AP-8 and AP-9), docs/OPERATIONAL_FACTS.md, and
docs/REVIEW_2026-08-12_AP9_ALLOCATION_REVIEW_VISIBILITY.md completely. Verify
the branch tip and a clean worktree before acting. AP-9 was accepted after
6295b2f and the counter-review corrections in 9d5e134: do not reinstate
prose-length caps, do not unbind a displayed review or the similar-ticker
suggestions from the inputs they were computed against, and keep every
rejection reporting an honest reason on screen. Do not deploy or roll
paper-epoch-004 without a new explicit owner authorization.
```
