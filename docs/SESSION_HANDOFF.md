# Session handoff — REBAL-3V and REBAL-3W await independent review

Prepared: 2026-08-15 by Claude, after the owner exercised the Portfolio
Rebalancing page in the development app across two rounds and then merged
both of them into `main` directly.

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
- `main` and `origin/main`: `006a9d5` when this was written, after PRs
  #231, #232 and #233. `main` may have advanced since; check it rather
  than trusting this line.
- **Both product rounds were merged WITHOUT independent review.**
  REBAL-3V (feasibility legibility) and REBAL-3W (refusal accuracy) are in
  `main` and neither has been reviewed. That is what this handoff exists to
  hand over.
- **No feature branch is open.** Every branch created for REBAL-1 and its
  follow-ups has been deleted, locally and on the remote, each after
  confirming with `git merge-base --is-ancestor` that its commits are
  reachable from `main`. Nothing is stranded on a deleted ref.
- The operational checkout remains separate and frozen at `752d3b7` in

Earlier history that remains load-bearing for anyone resuming:

- `4de784e` / `1cb8abf`: the epoch-005 observation-clock roll chain and
  Codex's correction of it. `paper-epoch-005` has been the only active
  evidence epoch since 2026-08-13; epochs 001 through 004 are closed and
  cannot pool evidence into it.
- `c048a94`: the owner's decision to hold epoch-005 unchanged for 60 days.
- BUY-1 is merged and independently corrected: review branch
  `codex/review-buy1-suggestion-picker-20260813`, correction `44a7f85`,
  on top of `e0df810`. It is closed history, not reopened work.
  active `paper-epoch-005`. No development commit has been copied there.

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

## 7e. The trim refusal stated a reason that was not true (this round)

The owner opened the Stage 3 trim section on a real book and got "No sleeve
is above its upper band, so there is nothing to trim." The same page, three
subheadings higher, reported **Bands breached: 6**. Both cannot be true.

`overweight_sleeves()` filters on two independent conditions in one pass --
above the upper band AND trimmable -- and returns one list, so an empty
result cannot say which condition failed. The UI reported only one of them.
Reproduced deterministically with one unsleeved position plus cash: `cash`
and `other_unassigned` both sit at 50% against a 7.50-12.50 band while
`overweight_sleeves()` returns `[]`.

**The refusal was correct; only its stated reason was false.** Cash is not a
holding, and the residual is the set of positions the profile does not
describe, so trimming there is exactly the reading Stage 1 forbids. Which
sleeves may be trimmed has not changed.

That distinction is the point. A refusal that misreports why it fired is
indistinguishable from a broken feature, and this workflow already lost two
rounds to that shape: ST3R-001 and ST3CCR-001 both refused every trim while
reading like careful safeguards. This is the same family seen from the
reader's side rather than the code's.

`untrimmable_overweight_sleeves()` now answers the second question on its
own, and the page either names the over-band-but-untrimmable sleeves with
the reason each is excluded, or keeps the original sentence when nothing is
over the band at all.

**Two mistakes of mine that this round exposed.**

1. `test_the_trim_section_appears_only_when_a_sleeve_is_overweight` PINNED
   the false message. It forced a book where cash is the only overweight
   sleeve -- exactly the reported situation -- and asserted the false
   sentence appears. Its docstring congratulates itself for forcing the book
   rather than assuming it. The setup was right and the expectation was
   wrong, so the defect was tested IN.
2. The first fix could have MOVED the lie rather than removed it. A mutation
   reporting the untrimmable reason for every empty case survived, and would
   have told an owner whose book is exactly on target that cash and the
   residual are above their bands. An on-target book is now pinned too.

Validation for this round, repository `.venv`, Python 3.13.14, Streamlit
1.60.0, Windows:

- `tests/test_rebalance_trim.py` and `tests/test_ui_portfolio_rebalance.py`:
  **76 passed** (74 before).
- Mutation verification: **4 mutations, 4 detected.**
- Full pinned-venv tree: **4,048 passed / 0 failed / 25 known dependency warnings in 733.50 seconds**.
- `compileall` and `git diff --check` clean. `assistant/rebalance_trim.py`
  had eighteen bare-LF lines from scripted editing and was normalized to
  CRLF before the recorded runs.

See `docs/REVIEW_2026-08-15_REBAL1_TRIM_REFUSAL_ACCURACY.md`.

**Operational note for whoever exercises Stage 3 next.** On a book whose
profiled sleeves are all inside or below their bands, Stage 3 correctly has
nothing to offer; only the two untrimmable sleeves are over. Exercising the
trim path needs a profiled sleeve genuinely overweight.

## 7f. Records corrected after the merge (this round)

PR #231 and PR #232 merged both rounds into `main`, and the document
guards went red on `main` within minutes:

```
FAILED test_no_action_plan_row_calls_its_own_merged_commits_unmerged
assert not ['row claims unmerged but a0a657b is in origin/main']
```

This is the trap `tests/test_active_document_consistency.py` documents in
its own docstring: **any statement about push or merge state, written in
the commit that is being merged, is false by construction the moment it
lands.** It cannot be prevented by being more careful when writing the row;
it can only be caught afterwards, which is what happened. This is the
second time in one day, and both times the guard found it rather than a
human.

The REBAL-3V and REBAL-3W rows now record their merges, and the topology
paragraphs record `18a3ee5`. Records only -- no product code is touched by
this round.

**Recorded plainly because it is easy to lose:** neither round has had
independent review. They went from implementation straight into `main`.

## 7g. Review scope handed to the independent reviewer

Both rounds are already in `main`, so this is a post-merge review. The
exact ordered range, base `84e73af` (PR #230):

| Commit | Round | Content |
|---|---|---|
| `7e9d005` | REBAL-3V | product: feasibility stated below the drift table |
| `a0a657b` | REBAL-3V | records, plus stale merge-claim corrections |
| `bead8ac` | REBAL-3W | product: trim refusal states the true reason |
| `43b29df` | REBAL-3W | records |
| `bacc66f` | post-merge | records only, after PRs #231/#232 |

Per `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` every commit needs an
explicit disposition; reviewing only the tip or a combined diff is not
sufficient.

### Where I would look first, stated against my own interest

1. **`untrimmable_overweight_sleeves` may be the wrong shape.** It sits
   beside `overweight_sleeves`, which still filters on two independent
   conditions at once. I removed the consequence at the one call site that
   had it; I did not remove the ability for the next caller to repeat it. A
   single function returning both lists may be the correct consolidation
   under `CLAUDE.md` section 8.
2. **Two of my tests were wrong this session, in the same direction.** One
   asserted a message appeared without asserting it named its sleeve. The
   other, `test_the_trim_section_appears_only_when_a_sleeve_is_overweight`,
   deliberately forced the exact book that reproduces REBAL-3W and then
   asserted the FALSE sentence appears -- it tested the defect in, and its
   docstring congratulates itself for forcing the book. Assume more tests
   in `tests/test_ui_portfolio_rebalance.py` assert presence of a string
   rather than correctness of a claim.
3. **The UI branch for infeasible targets is exercised by exactly one
   test**, which drives the real conflict rule by capping total exposure at
   50%. Any other conflict shape (leveraged cap, cash floor, position-cap
   capacity) is unexercised through the UI.
4. **`Path(policy_path).name` is rendered to the owner.** It is a file name
   rather than a path, but it is worth confirming no deployment layout
   makes that name disclose something it should not.
5. **Neither round has a `docs/FEATURE_MILESTONE_RECORD.md` entry**, which
   is correct: that file records work that has completed its definition of
   done AND its required review. Adding entries is part of closing this
   review, not part of the rounds themselves.

### What these rounds did NOT change

Verify this rather than taking it from me: no threshold, refusal, band
edge, sizing rule, proposal contract, execution gate, or eligibility rule
moved. REBAL-3V is presentation-only. REBAL-3W changed the stated reason
for a refusal that was already firing correctly, plus one new pure
function. `git diff 84e73af..006a9d5 -- assistant/ risk/ execution/` should
show only `assistant/rebalance_trim.py`, and only the added helper.

## 8. What is next

1. **Independent review of REBAL-3V and REBAL-3W, both already in `main`.**
   Suggested focus: whether `untrimmable_overweight_sleeves` should live
   beside `overweight_sleeves` at all, or whether the two-condition filter
   should be replaced by one function returning both lists so a future
   caller cannot repeat the conflation that caused REBAL-3W.
2. The owner has completed steps 1 and 2 of the dev-app walkthrough; Stage 2
   steering is confirmed working. Step 3 is in progress against a COPY of
   the development database at
   `data/dev_scratch_withfills.db` with the kill switch engaged. That copy
   carries 108 proposals and 72 broker order events across 17 tickers, all
   buys, so real journaled lots exist for JEPI, JEPQ, NVDY, AVGO, MSFT and
   NVDL. The dev app must be restarted to pick up these rounds.
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
Read CLAUDE.md, docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/ACTION_PLAN_2026-08-02.md and docs/SESSION_HANDOFF.md. main is at or
ahead of 006a9d5; check it rather than assuming. Two owner-reported rounds
from exercising the development app are ALREADY MERGED INTO main WITHOUT
independent review, and reviewing them is the task: REBAL-3V (7e9d005,
a0a657b) made sleeve target feasibility legible -- the "Target reachable"
column was ninth of nine with no horizontal scrollbar, and the reachable
case was never stated at all -- and REBAL-3W (bead8ac, 43b29df) corrected a
refusal that stated a reason which was not true: the page said "No sleeve
is above its upper band" while its own headline reported six breaches,
because overweight_sleeves() filters on two independent conditions at once.
bacc66f is records only. Base the range at 84e73af and give every commit an
explicit disposition. Neither round changed any threshold, refusal, band
edge, sizing rule, proposal contract, or execution gate -- verify that
rather than accepting it. Two of my own tests were wrong this session in
the same direction, and one PINNED the false message on exactly the book
that reproduced the bug, so treat tests/test_ui_portfolio_rebalance.py as
suspect for asserting presence of a string rather than correctness of a
claim. Full pinned-venv tree at the time of writing: 4,048 passed / 0
failed. Remaining known gap: no test drives the Streamlit trim button
through to a saved proposal. paper-epoch-005 runs unchanged for 60 days and
the operational my_policy.json stays 0.50/0.05. Do not deploy, roll the
epoch, mutate the operator database, submit orders, access funded accounts,
begin M4, or enable live trading without explicit owner authorization.
```