# Session handoff — REBAL-1 target feasibility made visible

Prepared: 2026-08-15 by Claude, after the owner exercised the Portfolio
Rebalancing page in the development app and found that the column stating
whether the sleeve targets are reachable was itself unreachable.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REBAL1_MILESTONE_PLAN.md`
4. `docs/REVIEW_2026-08-15_REBAL1_STAGE3.md`
5. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
6. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
7. `docs/MANDATE.md` (§2, §4, §6)
8. `docs/OPERATIONAL_FACTS.md`
9. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes a push, merge, pull request, deployment, evidence
repair, epoch roll, M4, funded-account access, live trading, paper order,
operator-database mutation, or scheduled-task change.

## 1. Exact repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- `main` and `origin/main`:
  `84e73af` — PR #230, which merged the whole REBAL-1 Stage 3 chain: the
  stage, Codex's correction, Claude's counter-review, and the end-to-end
  coverage against real journaled fills.
- **Every earlier feature branch has been deleted, locally and on the
  remote.** Before this round `main` was the only branch in either place.
  Nothing was lost: each deleted branch was verified merged into `84e73af`
  by content, not only by `git cherry` patch-id.
- **Current branch: `user/claude/rebal-feasibility-visible-20260815`**,
  branched from `84e73af`. One branch for the whole round, per the owner's
  2026-08-15 workflow rule.
- The operational checkout remains separate and frozen at `752d3b7` in
  active `paper-epoch-005`. No development commit has been copied there.

Earlier history that remains load-bearing for anyone resuming:

- `4de784e` / `1cb8abf`: the epoch-005 observation-clock roll chain and
  Codex's correction of it. `paper-epoch-005` has been the only active
  evidence epoch since 2026-08-13; epochs 001 through 004 are closed and
  cannot pool evidence into it.
- `c048a94`: the owner's decision to hold epoch-005 unchanged for 60 days.
- BUY-1 is merged and independently corrected: review branch
  `codex/review-buy1-suggestion-picker-20260813`, correction `44a7f85`,
  on top of `e0df810`. It is closed history, not reopened work.

Sections 2 through 7c below describe the Stage 3 chain that is now merged
into `main`. They are retained as the record of how that work was reviewed;
section 7d is this round.

## 2. Review outcome and commit dispositions

**Accepted after correction.** REBAL-1 Stage 3 met its development
definition of done and is now merged into `main` by PR #230. It is still
UNDEPLOYED: the operational runtime remains frozen at `752d3b7`.

| Commit | Disposition |
|---|---|
| `0490d9d` | Accepted after correction `ed6879d`. The design and refusal directions were sound, but the real coverage provider was incompatible with the new consumer and eight material contracts required correction. |
| `bedeea2` | Accepted after documentation correction. Its intended design narrative was useful, but it inaccurately claimed the submitted UI left all four owner choices unset and could not stand as a completed review record. |

Issue summary: no P0, no P1, eight closed P2 findings, one closed P3 finding,
and no open review issue. The complete evidence/reason/correction/verification
ledger is in `docs/REVIEW_2026-08-15_REBAL1_STAGE3.md`.

The implementation-quality rating is **6.5/10 as submitted**. Claude made the
right architectural choices—separate module, strict restoration bound,
complete-ledger refusal, profile binding, typed approval reuse, and strong
negative tests—but missed the production coverage schema, which made the
feature's only real UI action path unusable despite 56 focused tests passing.
The corrected reviewed result is materially stronger than the submitted tree.

## 3. What Stage 3 now does

The Portfolio Rebalancing page offers one tax-aware trim workflow only when a
non-cash, non-residual sleeve is above its upper band. The owner must
explicitly choose all four inputs: sleeve, held ticker, amount, and FIFO/LIFO/
HIFO strategy. Whole-share mode uses the strict whole-share control;
fractional mode accepts exact decimal text with at most nine places. The app
does not select a sell or provide a submit-all action.

The plan shows both dollars above the upper band and dollars back to target,
caps the sale at target restoration, includes priced working sells in band
arithmetic, separately shows positive gross working sells, and reports each
lot the strategy would consume, acquisition/holding period, estimated realized
gain split short/long, position remainder, and whole-close status. Cash and
the residual are never trimmable. A non-overweight sleeve, unusable report,
invalid/over-held quantity, wrong-sleeve ticker, target overshoot, or
incomplete tax-lot coverage refuses without a proposal.

Lot selection is advisory: Alpaca and its tax records remain authoritative.
The estimate uses the displayed reference price and can differ from a market
fill. The proposal durably stores its lot consequence and includes it in
identity. At execution validation, the app rechecks the active allocation
profile and reconstructs complete current tax coverage; a missing or changed
open-lot fingerprint refuses before broker import and requires regeneration.

Each proposal remains one ordinary `proposed` paper sell. It still requires
the exact typed approval, fresh policy and quote validation, paper-broker
configuration, kill switches, the atomic storage claim, idempotency key,
reservation/recovery rules, and ordinary reconciliation. No automatic order
or broker call was added to page load or plan generation.

## 4. Corrections in `ed6879d`

1. Matched Stage 3 to the real coverage contract: global `complete` plus
   per-ticker `matched`; replaced the invented test fixture with an integration
   regression through `tax_ledger_with_coverage()`.
2. Added `-- choose --` for the sleeve and kept the check button disabled
   until every owner choice is explicit.
3. Replaced fractional binary-float input with canonical exact decimal text.
4. Distinguished signed net pending exposure used for projections from
   positive gross working sells shown to the owner, and rendered the metric.
5. Persisted per-lot consequence and included it in proposal identity so a
   regenerated changed ledger cannot collide with an old stored proposal.
6. Threaded one proposal clock through holding-period labels and short/long
   totals.
7. Rejected duplicate named-lot IDs instead of double-counting one lot.
8. Added an open-lot fingerprint and complete-ledger execution revalidation
   before broker import; extended the frozen dependency contract with current
   portfolio/store arguments while preserving its call-time facade seam.
9. Removed Claude's duplicate steering-fingerprint import.

## 5. Validation on the final product tree

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Submitted-head baseline: **56 passed** focused.
- Initial material regression run: **6 expected failures**.
- Duplicate named-lot regression: red, then green.
- Changed/missing tax-lot execution bindings: both red, then green before
  broker configuration.
- Final focused set: **243 passed in 30.77 seconds**
  (`test_rebalance_trim`, rebalancing UI, shared tax lots, execution
  characterization, and Stage 2 steering).
- Final settled tree: **4,026 passed / 0 failed / 25 known dependency warnings
  in 606.37 seconds**.
- `python -m compileall`: clean.
- `git diff --check`: clean.

The warnings are the existing `websockets.legacy` and NumPy/joblib dependency
deprecations. No warning was introduced as a Stage 3 failure.

## 6. Safety and scope disposition

- Paper mode, typed approval, persistent/environment kill switches, atomic
  claims, reservations for ambiguous outcomes, confirmed-only release,
  telemetry failure ordering, exact idempotency, broker identity matching,
  replacement-chain handling, mismatch refusal, and reconciliation were not
  weakened.
- The execution change is feature-keyed to
  `user_directed_rebalance_trim`, runs after universal policy checks and before
  broker import, and returns the existing data-integrity failure class.
- Proposal/execution roots still do not gain an LLM, ML, research, backtest,
  strategy-authoring, or proposal-generation authority path. The new deferred
  execution imports are deterministic tax-ledger reconstruction only.
- No broker account, order, operator database, licensed artifact, credential,
  scheduler, operational checkout, or epoch state was accessed or mutated.
- No deployment claim or market-edge claim is made. The chosen portfolio shape
  is owner preference; the confirmed SOXX/SOXL wide-band result does not prove
  this general allocation will outperform.

## 7. Operational truth that remains unchanged

- `paper-epoch-005` remains active on the epoch host at frozen deployed commit
  `752d3b7`. Epochs 001–004 are closed.
- Owner decision 2026-08-14: keep epoch-005 unchanged for 60 days. Do not
  deploy, roll, or copy development policy/code into it.
- The ignored development `assistant/my_policy.json` may carry the owner-
  chosen 0.90 total-exposure and 0.07 position caps. The operational checkout
  deliberately keeps its frozen policy; changing it would alter lineage.
- The owner may inspect the development UI through
  `scripts/launch_dev_app.ps1`, which uses a scratch database and enables the
  environment kill switch by default. `-AllowPaperOrders` reaches the shared
  Alpaca paper account and remains prohibited during the frozen hold unless
  the owner separately changes that decision.
- CR-W3 remains a watch item for the first real AEP dividend subtype around
  2026-09-10. Do not widen reconciliation tolerance or post manual evidence.

No account identifier, balance, credential value, or private artifact content
is recorded here.

## 7b. Counter-review of the Stage 3 correction (Claude, 2026-08-15)

Branch `user/claude/rebal1-stage3-counterreview-20260815`, based on Codex's
review tip `0c91aa4`. Ledger in
`docs/REVIEW_2026-08-15_REBAL1_STAGE3_COUNTERREVIEW.md`.

All nine of Codex's findings were re-derived on a worktree at the submitted
tree `bedeea2` and all nine are real.

**ST3R-001 deserves stating plainly rather than as a ledger row: the
submitted Stage 3 refused every trim, always.** It read
`coverage["tickers"][name]["complete"]`, a key the real provider never emits
— the actual per-ticker keys are `broker_shares`, `ledger_shares`, and
`matched`. The tests passed because the fixture was a shape I invented
instead of one obtained from the real producer. That is the same root cause
as Stage 2's REBAL2CR-001 one round earlier, and worse here, because a
refusal that always fires is indistinguishable from a careful safeguard —
my own review document listed it as a safety feature.

**One P2 closed (ST3CCR-001), and it is the same failure shape again.**
Codex's corrected gate still required the GLOBAL `complete` flag alongside
the trimmed ticker's `matched`. `complete` is the AND across every ticker,
and `AssistantStore.list_fills` documents that positions bought before the
app existed "produce no events and therefore no lots" — so one pre-app
holding anywhere refuses every trim permanently. The owner's real book holds
roughly fifteen positions, most acquired outside the app, so Stage 3 would
still have proposed nothing. Both the creation and approval gates are now
scoped to the trimmed ticker's `matched` flag, which is necessary and
sufficient because the sale realizes gains from that ticker's lots alone;
the uncovered remainder of the book is disclosed rather than blocking.

**The execution-path change (ST3R-008) was audited on its own terms and
accepted.** The two new parameters come from the kernel's own arguments, so
its zero-module-global boundary holds; the trim branch is nested inside the
existing evidence-status gate so other families are untouched;
`open_lot_fingerprint` is deterministic and cannot raise on an unknown
ticker; and `tax_ledger_with_coverage` catches its own error classes rather
than raising into validation.

Validation on this tree: **4,031 passed / 0 failed** in the pinned `.venv`;
48 trim tests. Four mutations against the fix, all detected — restoring the
global gate on either side, dropping the per-ticker requirement, and
removing the disclosure.

**The gap I would close next**, recorded because it caused both rounds of
failure: the feature has still never been exercised end to end against a
real store with real fills. Both defects were interface-shape mistakes that
only a test driving the real producer would have caught, and the tests here
still monkeypatch `tax_ledger_with_coverage` at the execution seam rather
than seeding `broker_order_events`.

## 7c. End-to-end coverage against real fills (this round)

Branch `user/claude/rebal1-e2e-real-fills-20260815`, based on `c48861e`,
combined the whole chain -- Stage 3 (`bedeea2`), Codex's review
(`0c91aa4`), the counter-review (`c48861e`), and this work -- and PR #230
merged all of it into `main` at `84e73af`. The branch has since been
deleted; its content is contained in that merge.
Disposition in `docs/REVIEW_2026-08-15_REBAL1_STAGE3_END_TO_END.md`.

`tests/test_rebalance_trim_end_to_end.py` invents no shapes. Fills are
journaled through `journal_broker_order_update`, the ledger and coverage come
from the real providers, the proposal is persisted through
`AssistantStore.save_proposal` and reloaded, and approval runs the real
validation path.

**Writing it immediately found a fourth instance of the same defect, in my
own previous fix.** `tax_ledger_with_coverage` returns
`(ledger if complete else None, ...)` — it withholds the ledger ENTIRELY when
any holding is unreconciled. My ST3CCR-001 fix scoped only the caller's
`matched` check and was verified against a hand-built dict pairing a real
ledger with `complete: False`, a combination the real provider never emits.
Against the real provider there was no ledger at all, so Stage 3 was still
unusable on any book with a pre-app holding — which is the owner's book.

Fixed with a new sibling `ticker_tax_ledger_with_coverage(store, portfolio,
ticker)` rather than by loosening the shared function. The portfolio-wide
provider answers "can this whole book be taxed accurately?" and is correct to
withhold on partial history; the scoped one answers "can THIS ticker's lots
be accounted for?", which is what a trim of one ticker actually depends on.
The scoped coverage keeps the same shape, with `complete` scoped to the
ticker and `portfolio_complete` carrying the book-wide answer for disclosure.
An uncovered ticker still receives no ledger. All three call sites use it:
`plan_trim`, the execution-time revalidation, and the Stage 3 UI.

Validation: **4,041 passed / 0 failed**; 10 new end-to-end tests; 3 mutations
against the new provider, all detected.

**The gap that remains, recorded so it is not rediscovered:** no test clicks
the Streamlit trim button through to a saved proposal. The UI tests assert
control state and page text only. That is the same family of gap as the four
defects above and is the next one to close.

## 7d. Target feasibility made visible (this round)

The owner reported two things while exercising the development app.

**"Bands breached: 6" was correct and my prediction of 5 was wrong.** My
number came from a calculation made before REBAL1CR-002, which is the exact
change that stopped a display status from masking a real band breach. The
residual sleeve sits far above its band and now correctly reports
`band_state = overweight` while its `status` stays `unassigned_holdings`.
The app was right; I was reading a stale number.

**"There is no horizontal roll" was a real defect.** "Target reachable" was
the ninth and last column of a nine-column table, and Streamlit gave that
table no horizontal scrollbar at the owner's window width, so the one
column stating whether the targets can be reached at all was unreadable.

The conflict text was never actually lost — `evaluate_portfolio_rebalance`
also routes each conflict into `report.disclosures`, which render as
warnings above the table. **The dangerous direction was the opposite one:**
when every target IS reachable the page said nothing, so a reader had to
infer feasibility from the absence of a warning they had never seen fire.

The fix is presentation only. No computation, refusal, threshold, count, or
contract moved.

- Feasibility is stated in full BELOW the drift table, where width cannot
  hide it: a bordered block naming each affected sleeve and its exact
  conflict reason when any target is unreachable, and an explicit positive
  confirmation naming the active policy file when all of them are.
- The per-row column survives, shortened to "Reachable" and reduced to
  yes/no, so the fact stays next to the row it describes.
- Column ORDER is deliberately unchanged, because the owner is mid-way
  through testing this page.

**The finding of this round is a mutation that initially survived.** I
removed the sleeve label from each conflict line, leaving only the reason,
and every test still passed. Naming the sleeve is load-bearing: the
total-exposure conflict applies to every funded sleeve at once, so an
unlabelled list is one sentence repeated with no way to tell which sleeve
each belongs to. The test now pins `**Growth**`, which also distinguishes
this block from the raw-key disclosure warning (`growth: ...`) the report
already emits. A test asserting that a message appeared is not a test that
the message is useful.

Validation for this round, on the settled tree in the repository `.venv`
(Python 3.13.14, Streamlit 1.60.0, Windows):

- `tests/test_ui_portfolio_rebalance.py`: **24 passed** (21 before).
- The conflict branch is driven through the REAL conflict rule: the test
  replaces the loaded policy with one capping total exposure at 50% — the
  operational policy's actual value — against the profile's 90% invested
  target, and asserts on the rendered text.
- Mutation verification: **3 mutations, 3 detected** (after strengthening
  the test that let one through).
- Full pinned-venv tree: **4,044 passed / 0 failed / 25 known dependency warnings in 739.33 seconds**.
- `python -m compileall` and `git diff --check`: clean. One test file had
  six bare-LF lines from scripted editing and was normalized to CRLF; the
  full suite was restarted afterwards so the recorded result validates the
  final tree.

See `docs/REVIEW_2026-08-15_REBAL1_FEASIBILITY_VISIBILITY.md`.

## 8. What is next

1. Independent review of this round. It is presentation-only, so the useful
   focus is whether the positive confirmation could ever be shown while a
   conflict exists, and whether the shortened column still reads correctly
   for a sleeve that is both infeasible and badly drifted.
2. The owner is mid-way through exercising the development app and has
   completed step 1 (the Stage 1 drift table). Steps 2 (Stage 2 steering
   with a non-zero budget) and 3 (Stage 3 against a COPY of the operator
   database) are still to do. The dev app must be restarted to pick up this
   round's change.
3. **The remaining test gap is unchanged:** no test clicks the Streamlit
   trim button through to a saved proposal. Everything below that seam is
   now covered end to end against real journaled fills.
4. REBAL-1 has no Stage 4 in the adopted plan. Any new rebalancing feature
   needs a new owner-approved plan and scope.
5. Resolve whether the 60-day epoch-005 hold means calendar days (roughly
   43 weekday observations) or 60 captured market sessions.
6. The SET-1 design question remains open: whether strict whole-share mode
   should allow a fractional sell only when it closes an entire position.
7. `TRADE1CR-002` remains open and unscheduled: date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` can fail between roughly
   00:00 and 09:30 ET.

Standing operational constraints, unchanged by this round:

- `paper-epoch-005` runs UNCHANGED for 60 days (owner decision 2026-08-14).
  Do not deploy, roll, or disturb it. `-AllowPaperOrders` must not be used
  while that hold stands.
- **The operational checkout's `my_policy.json` stays at 0.50/0.05.** The
  development copy carries 0.90/0.07 so the approved profile is reachable,
  and it is untracked so no commit contains it. Copying it across would
  change the policy fingerprint and stall epoch-005 exactly as epoch-002
  stalled. A later agent must not "finish the job" by syncing them.
- Never open the operator database with the development checkout's
  `AssistantStore`; that would run migrations against a frozen-epoch
  database. Read it through a `sqlite3` read-only URI, or work on a copy.
- CR-W3 remains a watch item: the first real AEP dividend subtype may fail
  closed around 2026-09-10. Do not widen reconciliation tolerance or post a
  manual compensating entry.

No account identifier, balance, credential value, private artifact content,
or secret is recorded here.

Do not begin M4, deploy, mutate the operator database, alter scheduled
tasks, access a funded account, enable live trading, submit a paper order,
or roll an epoch without a new explicit owner instruction.

## 9. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, docs/REBAL1_MILESTONE_PLAN.md
and docs/SESSION_HANDOFF.md. main and origin/main are 84e73af (PR #230),
which merged the entire REBAL-1 Stage 3 chain; all earlier feature branches
were deleted after verifying their content is contained in that commit.
Branch user/claude/rebal-feasibility-visible-20260815 is a presentation-only
round: the owner exercising the dev app could not reach the "Target
reachable" column, which was ninth of nine in a table with no horizontal
scrollbar, so target feasibility is now stated in full BELOW the table --
sleeve and exact conflict reason when unreachable, and an explicit positive
confirmation when every target is reachable, which the page previously left
to be inferred from an absent warning. No computation, refusal, threshold,
count, or contract changed. The owner also reported "Bands breached: 6",
which is CORRECT; a predicted 5 was stale, from before REBAL1CR-002 stopped
a display status masking a real breach. 24 UI tests; 3 mutations, 3
detected, one only after strengthening a test that asserted a message
appeared rather than that it named its sleeve. Full pinned-venv tree:
4,044 passed / 0 failed / 25 known dependency warnings in 739.33 seconds. Remaining gap: no test drives the Streamlit trim button
through to a saved proposal. paper-epoch-005 runs unchanged for 60 days;
the operational my_policy.json stays 0.50/0.05. Do not push to main, deploy,
roll the epoch, mutate the operator database, submit orders, access funded
accounts, begin M4, or enable live trading without explicit owner
authorization.
```