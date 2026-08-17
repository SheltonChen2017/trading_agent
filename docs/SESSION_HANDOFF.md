# Session handoff — full research/QuantConnect audit and documentation reset

Prepared: 2026-08-17 by Codex after a clean-slate review of every research and
QuantConnect module changed during the 2026-08-16/17 alpha work, correction
of the local measurement path, and a validity/organization audit of the
documentation. This section and section 7l supersede earlier alpha current-
state language while retaining the earlier sections as historical review.
Updated later on 2026-08-17 by Claude's FINAL counter-review of the complete
correction chain (section 7o), then by Codex's verification after that review
merged as PR #243 (section 7p), then by Claude's counter-review of Codex's
Stage 0 correction (section 7q). Section 7q and the updated
topology/next-steps text are the current state.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/Alpha_Test_Implementation_Plan.md`
4. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_FABLE_COUNTERREVIEW.md`
5. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`
6. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW_INDEPENDENT.md`
7. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW.md`
8. `docs/alpha-result.md`
9. `docs/Review/REVIEW_2026-08-16_ALPHA_QC_ROUND1.md`
10. `docs/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md`
11. `docs/research/ALPHA_BATTERY_METHOD_V2.md`
12. `docs/research/ALPHA_BATTERY_2026-08-16_QC_PREREGISTRATION.md`
13. `docs/research/Alpha explanation.md`
14. `docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md` (prior local round)
15. `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
16. `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
17. `docs/operations/MANDATE.md` (§2, §4, §6)
18. `docs/operations/OPERATIONAL_FACTS.md`
19. `docs/operations/OPERATIONS_RUNBOOK.md`

Nothing here authorizes a push, merge, pull request, deployment, evidence
repair, epoch roll, M4, funded-account access, live trading, paper order,
operator-database mutation, or scheduled-task change.

## 1. Exact repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Published `origin/main` at audit time:
  `4151b3f0c4ee2cf365d578e70ab10bd5eb93d324`. PR #243 merged Fable's exact
  counter-review head `6bd962f`. PR #242 at `f937bfb` had merged the
  counter-review integration branch, whose merge tree is byte-identical to
  branch head `5730f7b` (still reachable as `refs/pull/242/head`). PR #241 at
  `d8a32604d32e0d85fb9920b0839445eab13ad5f8` had merged the full alpha/QC
  audit before it. The long-lived alpha branch was originally created from
  `a795ea3`.
- The 2026-08-17 Fable counter-review (section 7o) ran on
  `user/claude/alpha-qc-full-counterreview-20260817`, created from the exact
  object `5730f7b`, ended at `6bd962f`, and was merged by PR #243; its record is
  `docs/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md`.
- Codex correction branch:
  `codex/review-alpha-qc-fable-counterreview-20260817`, based on exact Fable
  head `6bd962f`. Product/test correction `ac96d47` closes the four Stage 0
  findings in section 7p; records commit `dd664f9` updates the review report,
  Action Plan, alpha plan/result ledger, frozen methodology, and the superseded
  Fable report; `9e45803` is its handoff. Claude pushed the branch unchanged
  at exact head `9e45803` to freeze the review snapshot, then accepted it in
  the section 7q counter-review on
  `user/claude/alpha-qc-fable-cr-verify-20260817`, which adds the FCR-001/002
  closures.
- Claude's last submitted remote audited in this cycle was
  `origin/user/claude/alpha-qc-round-20260816` at
  `a37e73b`; the full 2026-08-16/17 chain from `db0045a` through `a37e73b`
  receives an explicit per-commit disposition in the round-2 report. On
  2026-08-17 Claude fast-forwarded that branch onto counter-reviewed Codex
  head `b4e9ee0` and added the counter-review commit (section 7m); the
  exact pushed head is `ad3b3a8`.
- Prior integration/review branch:
  `codex/review-alpha-qc-counterreview-20260817`, based on `origin/main` at
  `d8a3260`. Commit `031b5a7` retains Claude's three mutation-verified tests
  and counter-review record from `ad3b3a8`; documentation/review correction
  `46ebe04` corrects the stale branch, worktree, and main-head claims found
  during Codex's independent review.
- The prior `codex/review-alpha-qc-round2-20260817` branch was merged by PR
  #241 and then deleted locally and remotely with the other merged topic
  branches. Its commits remain reachable from `main`. Claude's counter-review
  gate was satisfied at that point; no new QC run occurred, and section 7p
  closes it again for the result-changing Stage 0 correction.
- Five real-market cloud executions remain preserved in the permanent ledger.
  None is usable
  alpha evidence: one refused, two remain deliberately unanalysed, one ran
  unreviewed code, and the benchmark is unanalysed; four entries also lack
  project/compile provenance. They count as five run-level looks and expose
  80 repeated alpha cells. The conservative lifetime cell floor is 428.
- `docs/Alpha_Test_Implementation_Plan.md` is now the current staged research
  contract. It freezes corrected-battery completion, two prior-signal
  replications, point-in-time PEAD, hierarchical sector momentum, and optional
  overnight persistence, with Alpaca Paper reserved for later forward testing.
- PR #234 first merged the prior Codex REBAL-3V/3W review through
  `f63fe2cb30aa904dec131962a133e1058185427c`; correction `3a506ae` and records
  `dae34d0` are therefore pushed, fetchable, and in `main`.
- Prior local-alpha history: Claude's pushed branch
  `origin/user/claude/alpha-battery-20260815` is exact
  head `046afc3ee39c0fff9c916e88657c43a1b5f4e5f1`; PR #236 merged it at
  `3d58f6b`.
- That prior reviewed literal range was `f63fe2c..3d58f6b`. It contains, in order,
  `db0045a`, `4de88d0`, `046afc3`, and merge `3d58f6b`; all four have an
  explicit disposition in `docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md`.
- That prior review branch was `codex/review-alpha-battery-20260816`.
  Product/test correction `124192ff3e29c3fc62f0c9e8bf95b9aadf216915`
  was merged by PR #237 before current `main`.
- The submitted alpha result and audit artifacts are **invalidated pending a
  clean rerun**. At the owner's direction, invalid generated Markdown, JSON,
  and raw logs were removed from active docs only after their exact identities,
  hashes, and dispositions were preserved in `docs/alpha-result.md` and Git
  history. Nothing was promoted to the research registry or Feature Milestone
  Record.
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
sections 7d through 7f describe the two owner-reported rounds and their merge;
section 7g records their completed independent review; section 7h records the
prior local alpha review; section 7i records the current QuantConnect review
of the original battery; section 7j records the staged alpha review, section
7k records Stage 1, and section 7l records the full-tree re-audit. Section 7l
supersedes every earlier alpha current-state statement.

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
ledger is in `docs/Review/REVIEW_2026-08-15_REBAL1_STAGE3.md`.

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
`docs/Review/REVIEW_2026-08-15_REBAL1_STAGE3_COUNTERREVIEW.md`.

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
Disposition in `docs/Review/REVIEW_2026-08-15_REBAL1_STAGE3_END_TO_END.md`.

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

See `docs/Review/REVIEW_2026-08-15_REBAL1_FEASIBILITY_VISIBILITY.md`.

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

See `docs/Review/REVIEW_2026-08-15_REBAL1_TRIM_REFUSAL_ACCURACY.md`.

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

**State at submitted head `006a9d5`:** neither round had independent review;
they went from implementation straight into `main`. Section 7g records the
review that followed.

## 7g. Independent review of both owner-reported rounds (Codex, 2026-08-16)

The owner directed review of the exact main range `84e73af..006a9d5`, with
an explicit disposition for every commit rather than a tip-only or combined
diff review. Codex fetched `origin/main`, locked exact head `006a9d5`, and
created `codex/review-rebal3v3w-20260815` from that remote object. The literal
range contains eight commits, including three merges.

| Commit | Disposition |
|---|---|
| `7e9d005` | Accepted after correction `3a506ae`: the presentation is correct; one no-op test and one branch-agnostic assertion were replaced with deterministic positive and four-rule negative coverage. |
| `a0a657b` | Accepted after documentation correction: its behavior narrative is sound, but its test-sensitivity claim inherited the weak coverage above. |
| `8ee5f39` | Accepted after correction: the PR #231 merge tree equals its second parent and contains no conflict-resolution change; it inherits the feasibility test finding. |
| `bead8ac` | Accepted after correction `3a506ae`: eligibility/refusal direction is correct; the ambiguous two-helper API and one false concluding sentence were corrected. |
| `43b29df` | Accepted after documentation correction: its historical defect narrative is accurate; the final records now describe the reviewed classifier and evidence. |
| `18a3ee5` | Accepted after correction: the PR #232 merge tree equals its second parent and contains no conflict-resolution change; it inherits the two product P3s. |
| `bacc66f` | Accepted after documentation correction: records only; its topology rewrite split the operational-runtime sentence and attached half to BUY-1. |
| `006a9d5` | Accepted after documentation correction: the PR #233 merge tree equals its second parent and contains no conflict-resolution change; the final tree's `18a3ee5` topology and pending-review claims were stale. |

Outcome: **accepted after correction; 0 P0, 0 P1, 0 P2, 5 closed P3,
0 open.** The complete evidence/reason/correction/verification ledger is in
`docs/Review/REVIEW_2026-08-15_REBAL3V_REBAL3W_INDEPENDENT.md`.

Product/test correction `3a506ae` does four things. It replaces the generic
two-helper overweight API with one immutable classification returning both
trimmable and untrimmable groups; fixes the refusal's final sentence so it no
longer calls overweight cash inside its band; removes a collected test with
no body; and makes feasibility tests deterministic across computers while
covering all four implemented policy-conflict rules through the real report
and Streamlit UI. No threshold, refusal direction, sizing, tax-lot, proposal,
approval, execution, broker, schema, policy, epoch, or deployment contract
changed.

Validation in the repository `.venv` (Python 3.13.14, Streamlit 1.60.0,
Windows): submitted baseline **106 passed**; confirmed copy regression red
then green; classifier import regression red then green; corrected REBAL-1
focused set **192 passed**; corrected trim/UI set **79 passed**; final full
suite **4,051 passed / 0 failed / 25 known dependency warnings in 719.51
seconds**. Final active-document guards: **30 passed**. Compilation and
`git diff --check` are clean.

**Post-merge availability correction (2026-08-16):** correction `3a506ae` and
records `dae34d0` were pushed and merged by PR #234 at `f63fe2c`. The earlier
local-only/shared-checkout warning is closed history. Claude's alpha branch was
subsequently pushed and merged by PR #236 and is the subject of §7h.

## 7h. Independent review of the alpha battery (Codex, 2026-08-16)

The review started only after fetching exact pushed `origin/main` head
`3d58f6b`. Every commit in `f63fe2c..3d58f6b` was reviewed separately:

| Commit | Disposition |
|---|---|
| `db0045a` | Accepted after documentation correction. The preregistration genuinely preceded results and retains its conservative denominator, but the implemented bootstrap later could not resolve its gate. |
| `4de88d0` | Accepted only as an invalidated exploratory record after correction `124192f`. The p-value floor made rejection impossible and set-only turnover understated long/short costs. |
| `046afc3` | Accepted only as an invalidated exploratory record after correction `124192f`. The claimed point-in-time universe, measured survivorship, residual/industry results, and automatic robustness labels were not valid. |
| `3d58f6b` | Accepted after product/documentation correction. The merge adds no hidden product resolution, but it left this canonical handoff semantically stale. |

Outcome: **0 P0, 0 P1, 5 closed P2, 2 closed P3, 0 open code
issue.** Full evidence, reasons, corrections, and verification are in
`docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md`.

Correction `124192f` makes a future run honest: 10,000-draw stationary
bootstrap resolution can cross the declared threshold; signed-weight turnover
counts long/short flips; actual SEC filing dates control fact availability;
unadjusted closes drive price, ADV, and market-cap screens while adjusted
closes remain return inputs; membership schema 2 prevents reuse of the bad
cache; candidate-filer coverage is not called survivorship loss; unavailable
point-in-time industry inputs refuse instead of using each ticker's final size;
and near-zero broad results cannot be labelled robust.

The historical Markdown/JSON results are not silently recalculated. They carry
explicit invalidation banners and remain audit history. A new result requires a
clean schema-2 universe rebuild and a preregistered rerun. Even then the current
ticker map, yfinance history, absent delisted returns, absent historical venue/
security type, and absent point-in-time industry classification keep the work
exploratory and non-point-in-time. No result was added to
`assistant/research_findings.json` or `docs/FEATURE_MILESTONE_RECORD.md`.

Validation in the repository `.venv` (Python 3.13.14, Windows): five focused
regressions failed red on the submitted implementation; corrected research/
backtest/cross-sectional set **112 passed**; reviewer file **10 passed**;
active-document guards **30 passed**; final full suite **4,061 passed / 0
failed / 25 known dependency warnings in 717.98 seconds**. Full compilation,
all three edited JSON artifact parses, and `git diff --check` are clean.

## 7i. Independent review of the QuantConnect battery (Codex, 2026-08-16)

The review began only after exact remote
`origin/user/claude/quantconnect-smoke-20260816` advanced from monitored
baseline `b9efc41` to pushed head `667cbf4`. Codex created the single review
branch from that exact object and reviewed the complete nine-commit branch
range `dbadb12..667cbf4`, not local/uncommitted work. Dispositions:

| Commit | Disposition |
|---|---|
| `361038e` | Accepted after correction `e8eb558`: client/runner validation and direct helper tests added. |
| `d3211c9` | Accepted after documentation correction: useful inert probes, but historical cloud IDs/log hashes were not committed. |
| `b9efc41` | Accepted after correction `e8eb558`: real and ordered date validation added. |
| `3a3132e` | Accepted after correction `e8eb558`: monthly method violations repaired; submitted result invalid. |
| `e3e8a23` | Accepted after correction `e8eb558`: short/benchmark/analyser measurement paths repaired. |
| `f0cd4fc` | Rejected as evidence; Markdown/JSON invalidated. |
| `6707a97` | Accepted after correction `e8eb558`: full-period packed output replaces state-breaking split/drop behavior. |
| `a83703e` | Rejected as evidence; no pass, null, MAX, profit, or benchmark conclusion survives review. |
| `667cbf4` | Accepted after correction `e8eb558`: benchmark analyser now records costs, series, hashes, and run identity. |

Outcome: **0 P0, 0 P1, 10 closed P2, 1 closed P3, 0 open code
findings.** The material defects were raw split-affected return bars;
same-close rather than next-session entry; a non-session short holding clock;
missing terminal delisting arithmetic and settlement-time basket selection;
non-joint/wrong-window residual momentum; wrong/reused/averaged turnover;
an understated 135 family that omitted IC and dropped a construction;
fail-open split-log parsing; mismatched/no-cost benchmarks; and absent cloud
run provenance. Full evidence and exact corrections are in
`docs/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md`.

Product/test correction `e8eb558` was created locally for the one authorized
final push at the end of this review; a resuming agent must verify the recorded
remote head. It uses adjusted bars for returns while raw
coarse/fine fields still drive screens; stages next-session entries; counts
distinct sessions; retains measured names and terminal delisting outcomes;
freezes baskets at entry; uses joint residual OLS with leave-one-out peers;
computes construction-specific drift-aware turnover; counts 180 tested
hypotheses; packs the full short run into one lossless schema under the log
cap; and requires exact QuantConnect backtest IDs plus input-log hashes.

The historical result Markdown/JSON is explicitly invalidated and unchanged
numerically. The smoke report is provenance-limited because Git lacks its
exact cloud identities. No result was promoted to the registry or Feature
Milestone Record. No QuantConnect API call, authentication, compile, cloud
backtest, broker access, order, deployment, database mutation, schedule
change, or epoch change occurred during review.

Validation in the repository `.venv` (Python 3.13.14, Windows): focused
QuantConnect/LEAN/analyser suite **126 passed**; active-document guards **30
passed**; final full suite **4,118 passed / 0 failed / 25 known dependency
warnings in 771.31 seconds**. Repository-wide compilation, all three edited
JSON parses, and `git diff --check` are clean. Final branch/commit/remote
identity is verified around the one authorized push and reported to the owner.

## 7j. Staged alpha QC round 1 review (Codex, 2026-08-16)

The monitor fired only after exact remote
`origin/user/claude/alpha-qc-round-20260816` appeared at pushed head
`ad6475d552c5f9b4da338570cd52ea99c3b63524`, beyond base
`a795ea322de8a50830abc680fd82d49967c5ddd6`. The shared checkout remained on
Claude's branch and was not switched, edited, staged, or committed by Codex.
The review branch and all corrections were made in an isolated worktree.

Commit disposition:

| Commit | Disposition |
|---|---|
| `ad6475d` | **Accepted after product/test and documentation correction.** Preserving all five cloud runs, opening a permanent ledger, refusing partial monthly output, and identifying the impossible peer equality were sound. The slice-only correction measured the skipped latest month instead of true 6-1/12-1 residual momentum; its source-string test could not detect the mistake; and the ledger undercounted looks and misstated decoder/provenance facts. |

Product/test correction `8bf8a82` retains enough history for a 252-session
joint market/leave-one-out-industry regression before the formation window,
sums 105 or 231 formation residuals, and excludes the most-recent 21 sessions.
Follow-up `56bc86d` binds every price to the exact global exchange session and
refuses missing, duplicate, or universe-gap histories rather than treating
adjacent deque values as adjacent daily returns. Behavioral tests cover both
horizons, short/misaligned factor history, and exact/missing/duplicate dates.
Four P2 and one P3 findings are closed; none remains open. Full detail is in
`docs/Review/REVIEW_2026-08-16_ALPHA_QC_ROUND1.md`.

Documentation commit `e1aedc7` creates
`docs/Alpha_Test_Implementation_Plan.md`, corrects `docs/alpha-result.md`, and
updates the Action Plan. The ledger now counts five run-level looks and 80
emitted repeated-look cells, giving a conservative lifetime alpha-cell floor
of 428. It records exact log hashes/backtest IDs while marking absent compile
and project identities. The committed base64 decoder already existed, so no
statistics were computed merely to prove it. No result was promoted to
`assistant/research_findings.json` or `docs/FEATURE_MILESTONE_RECORD.md`.

No QuantConnect API/authentication/upload/compile/backtest/result-read, broker
access, order, deployment, database mutation, scheduler change, or epoch
change occurred during this review. Final local validation on Python 3.13.14:
focused QC suite **13 passed in 2.48 seconds**; active-document suite **30
passed in 0.57 seconds**; full suite **4,122 passed / 0 failed / 25 known
dependency warnings in 795.85 seconds**; repository compilation including
`research/` and `git diff --check` are clean. One earlier final-suite attempt
stopped at a handoff topology-format guard; the declaration was corrected and
the complete green suite was rerun. Final pushed remote identity is reported
to the owner after the single authorized push.

## 7k. Alpha QC Stage 1 review (Codex, 2026-08-17)

The monitor fired only after exact remote
`origin/user/claude/alpha-qc-round-20260816` advanced from last-reviewed
`ad6475d552c5f9b4da338570cd52ea99c3b63524` to pushed head
`dc63eecc9160071ef1590650085d2afe48e42c45`. The shared checkout began and
ended the review on branch `user/claude/alpha-qc-round-20260816` at
`dc63eec`; Codex did not switch, edit, stage or commit there. All durable work
was performed on isolated branch `codex/review-alpha-qc-round2-20260817`.

The ordered range and explicit dispositions are in
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`. Six round-1 Codex commits are
accepted carried-forward history, not relabeled as a fresh review. Claude's
`af045ee` counter-review is accepted without correction. Stage 1 commit
`dc63eec` is accepted only after `b143c60`.

The submitted pure H52 and IDV score helpers were directionally correct, but
the end-to-end experiment was not the frozen one. It scored on the first
session of a calendar month and settled when the next month's entry arrived;
the plan requires prior month-end close, next distinct close entry, and an
exact 21-session outcome. It also rebuilt REP-IDV's 111 historical market
returns from the score-date survivor set and substituted zero for an empty
factor day. Finally, no exact-cadence benchmark or analyser capable of
accepting the Stage 1 spec inventory and 24-cell gate existed.

Correction `b143c60` now:

- freezes the immediately preceding month-end and enters at the current
  first-of-month close without relying on close-callback ordering;
- keeps overlapping cohorts and settles each exactly 21 distinct sessions
  after entry;
- records each day's point-in-time equal-weight universe factor with its
  exchange session and refuses any missing 90+21 factor date;
- preserves separate drift turnover at monthly rebalance while the primary
  outcome remains the fixed 21-session cohort;
- adds `research/lean/alpha_stage1_benchmark.py` with identical timing and
  delisting behavior; and
- adds `scripts/analyse_qc_alpha_stage1.py`, requiring alpha and benchmark
  project/compile/backtest/source hashes, same-date comparison, the 24-cell
  stage gate and the 452-cell lifetime gate.

Two P1 and two P2 findings are closed; none remains open. Focused Stage
1/QC/LEAN safety validation is **74 passed**. A deliberate 20-session mutation
failed the exact-hold regression as intended and was restored. Full final-tree
validation is recorded in the round-2 report and final documentation commit.

No QuantConnect authentication, upload, compile, backtest, result read or
market statistic occurred. No broker, order, deployment, database, scheduler,
policy, mandate, registry or epoch state changed. The alpha-cell exposure
floor therefore remains 428. `docs/alpha-result.md` contains no Stage 1 run;
any run launched before Claude counter-review must be appended as
`PENDING_REVIEW` and counted rather than reused.

## 7l. Full research/QC and documentation audit (Codex, 2026-08-17)

At the owner's request, Codex stopped treating Stage 1 as the audit boundary
and reviewed all research/QC code created or changed during the day's alpha
work. The exact per-commit dispositions and permanent P0-P3 ledger are in
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`. No QuantConnect API,
cloud project, backtest, broker, order, operational database, scheduler, or
epoch state was accessed or changed.

Product corrections `855941a` and `1e2b631` do the following:

- use one current QuantConnect Python API dialect across every LEAN module and
  prevent accidental shadowing of framework-owned members;
- make monthly factors point-in-time, leave the stock out of its industry
  peer factor, align exact sessions, and refuse missing history;
- make Stage 1 use prior month-end, next-close entry, exact 21-session
  outcomes, a cadence-matched benchmark, and full run provenance;
- make the short battery require exact non-overlapping exchange sessions and
  make benchmarks refuse stale closes;
- make analyzers reject incomplete, conflicting, malformed, non-finite, or
  negative evidence and require project/compile/backtest/source identity;
- bound QuantConnect polling by total/no-progress time, including responses
  that never expose numeric progress; and
- repair the older local battery's future-outcome turnover, NAV denominator,
  target-to-target turnover, self-including peer mean, and sequential residual
  regression. The old local results remain invalid because the data and static
  classifications are not point-in-time.

The invalid result narratives, JSON artifacts, and raw logs named in
`docs/alpha-result.md` were removed from active docs at the owner's direction.
Their run IDs, statuses, hashes, look counts, and Git history remain. Frozen
preregistrations and Method V2 remain under `docs/research/` as historical
contracts, each with a current validity note. Review reports now live under
`docs/Review/`, workflow rules under `docs/process/`, operational records
under `docs/operations/`, and architecture records under
`docs/architecture/`. The docs root contains only canonical/milestone/result
documents. `docs/research/Alpha explanation.md` gives the owner a plain-
language explanation of each tested or planned alpha.

There is still **no valid alpha result and no completed alpha milestone**.
The lifetime exposure floor remains 428 cells and five additional run-level
looks. A new QC run starts at R-005 or later only after Claude counter-reviews
the exact final pushed Codex head. Every historical number remains unusable.

Final authoritative validation used the repository `.venv` (Python 3.13.14,
Streamlit 1.60.0): combined research/QC/document gate **247 passed**; repaired
strategy/config regression group **31 passed**; full suite **4,189 passed,
0 failed, 25 known dependency warnings in 687.51 seconds**. Compilation
including `research/`, all 124 Markdown relative links, remaining docs JSON,
active-document layout, and diff checks are clean after the final rerun.

## 7m. Counter-review of the round-2 audit (Claude, 2026-08-17)

Claude counter-reviewed exact pushed head `b4e9ee0` of
`codex/review-alpha-qc-round2-20260817` and fast-forwarded it into
`user/claude/alpha-qc-round-20260816`. Full record:
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW.md`.

Verification was by seven independent mutations against the Codex head,
deliberately different from the mutations the review reported using. Four
were detected (API-dialect/shadowing guards, leave-one-out peers,
fit/measurement separation, turnover lookahead). Three survived, which is
the counter-review's finding set — all the same shape, AQR1-004 one seam
higher: the pure helpers are behaviourally tested but the algorithm's USE
of them was not.

- **CR2-001 (P3, closed):** scoring at the entry close (`end_ago=0`)
  survived the suite; the call site is now pinned.
- **CR2-002 (P3, closed):** a fabricated `0.0` market-factor day survived;
  the recorder's refusal is now behaviourally tested against a stub.
- **CR2-003 (P3, closed):** Stage 1's own `_drift_turnover` copy was
  outside every test loader; it is now executed directly with the Method
  V2 §1.2 cases.

Each closing test was verified to redden under its exact mutation and pass
on the restored tree. All seven Codex commits are accepted; all thirteen
audit findings are confirmed; no product defect was found in the head. No
QuantConnect, broker, database, scheduler, or epoch access occurred.

## 7n. Independent review of Claude's counter-review (Codex, 2026-08-17)

Codex reviewed exact pushed Claude commit `ad3b3a8`, whose only product-tree
change is three regression tests. All three tests are worth retaining and the
commit is **accepted after documentation correction**. Focused validation on
the exact submitted commit passed 48 tests. The independent record is
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW_INDEPENDENT.md`.

One P3 documentation finding, CR2IR-001, was closed: the submitted handoff
inherited pre-merge topology and still described `f0071bc`, an older shared
`main`, an isolated current worktree, and the deleted round-2 Codex branch as
current. Correction `46ebe04` records `origin/main` at `d8a3260`, the submitted
Claude head `ad3b3a8`, and the current Codex branch. No production or QC
algorithm changed, no historical result was rehabilitated, and no QC, broker,
database, scheduler, deployment, or epoch access occurred.

Final validation in the repository `.venv` with Python 3.13.14: focused gate
**48 passed**; full suite **4,192 passed, 0 failed, 25 known dependency
warnings in 968.31 seconds**; compilation including `research/` and final
document/diff/status checks were clean.

## 7o. Final counter-review of the whole correction chain (Claude, 2026-08-17)

After the owner merged the integration branch as PR #242 (`f937bfb`), a
fresh Claude session — independent of the 7m/7n cycle — counter-reviewed the
complete ten-commit chain `b143c60 .. 5730f7b` from the exact object
`5730f7b` on branch `user/claude/alpha-qc-full-counterreview-20260817`. The
named remote branch had already been merged and deleted; the head was
verified via `refs/pull/242/head` and the merge tree proven byte-identical
to `5730f7b`. Full record:
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md`.

All ten commits are accepted (the PR #242 merge as topology). Sixteen
mutations were run: the three CR2 closures each reddened under their exact
defect plus two fresh variants, five fresh mutations against Stage 1 timing/
turnover and three against the local/LEAN residual methodology all reddened,
and three survived — the finding set, all P3 test gaps over correct
behaviour, plus one documentation finding:

- **CCR3-A (closed):** the 24-cell stage family and 428-cell lifetime floor
  in `scripts/analyse_qc_alpha_stage1.py` were unpinned; lowering 428 to 24
  survived the suite. Constants and the emitted report gates are now pinned,
  and the analyser's same-date benchmark refusal is tested end to end.
- **CCR3-B (closed):** the QC poll loop's OUTER deadline was untested; a
  mutation returning a fake result at timeout survived. A behavioural test
  with advancing progress now pins the raise.
- **CCR3-C (closed):** the LEAN legacy-name blocklist missed the leaf
  members these files use (`GrossProfit` alone survived) and legacy enum
  members (`Resolution.Daily`); sixteen names were added and both mutations
  now redden.
- **CCR3-D (closed):** every permanent-ledger SHA-256 is a CRLF
  working-tree hash; hashing the bare Git blobs mismatches on all fourteen
  artifacts, inviting a false tampering conclusion. All fourteen were
  re-verified under LF→CRLF conversion and the convention is now recorded in
  `docs/alpha-result.md`.

Validation on the final tree: focused research/QC/document gate **167
passed**; full suite **4,196 passed / 0 failed / 25 known dependency
warnings in 737.53 seconds**; compilation including `research/`, the 126-file Markdown
relative-link check, docs/mandate JSON parses, and `git diff --check` clean.
No QuantConnect access of any kind, no research look, no broker, database,
scheduler, policy, or epoch change. No historical result was rehabilitated;
the lifetime floor remains 428 and the run ledger remains five.

## 7p. Codex verification of Fable's final counter-review (2026-08-17)

Fable's exact pushed range `5816f6f..6bd962f` was merged by PR #243 at
`4151b3f` and then independently verified commit by commit on
`codex/review-alpha-qc-fable-counterreview-20260817`. All three commits are
accepted after follow-up correction: the Stage 1 gate/deadline/dialect tests
are useful, and the CRLF artifact-hash note is reproducible, but the submitted
“no product defect” and “QC gate satisfied” conclusions did not survive.

Correction `ac96d47` closes four Stage 0 findings:

1. **FQCV-001 (P2):** the short battery exited after its five-session result,
   waited through score staging, and re-entered next session, but charged a
   direct rebalance. It now charges drifted liquidation plus reconstruction;
   identical flat gross-1 books correctly cost 1.0 rather than 0.0.
2. **FQCV-002 (P2):** one CLI default annualized both monthly and short
   families at 12 periods/year. The analyser now infers 12 for monthly and 42
   for the short battery's non-overlapping six-session cycle, records it, and
   rejects a conflicting override.
3. **FQCV-003 (P3):** MAX(20) silently dropped a return with a bad denominator.
   It now requires exactly 21 finite positive closes.
4. **FQCV-004 (P3):** missing industry codes were pooled as code zero. They
   now remain missing and cannot manufacture an industry peer group.

FQCV-005 (P3 documentation) updates the stale `origin/main`, merge, and gate
status. No QC access or new result occurred; no historical status changed;
the lifetime cell floor stays 428 and the run ledger stays five. Focused
validation is 36 QC-battery and 222 broader research/QC tests. The complete
tree passed **4,203 tests / 0 failures / 25 known warnings in 867.87 seconds**;
repository-wide compilation including `research/` was clean. Full review and explicit
commit dispositions:
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_FABLE_COUNTERREVIEW.md`.

**Current launch status: BLOCKED.** Publish the completed Codex branch only
after final validation, then obtain an independent counter-review of its exact
remote head. Do not launch QC from PR #243 or `6bd962f`; that tree has the
known staged-turnover and annualization defects.

*(Superseded by section 7q: the branch was pushed and the counter-review is
complete and accepting.)*

## 7q. Counter-review of the Stage 0 correction (Claude, 2026-08-17)

The required independent counter-review of section 7p's correction ran on
`user/claude/alpha-qc-fable-cr-verify-20260817`. Because Codex's branch was
still local-only, Claude first pushed it unchanged to
`origin/codex/review-alpha-qc-fable-counterreview-20260817` at exact head
`9e45803` to freeze the snapshot, then branched from that object. Full
record:
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_CORRECTION_COUNTERREVIEW.md`.

All three commits (`ac96d47`, `dd664f9`, `9e45803`) are **accepted**. All
four FQCV code findings were reproduced red on the pre-correction tree
`6bd962f` — including the 0.0-versus-1.0 per-period turnover and the
19-return MAX window with a fabricated −100% move — and Claude records
plainly that its own prior "no product defect" conclusion was wrong, with
FQCV-001's edge having been visible in its notes as a misjudged "minor
observation". Seven mutations were run against the corrected head (the
requested FQCV-001/002 mutations included). One survived and became
**FCR-001 (P3, closed)**: the exit leg's drift was unpinned — a long-only
flat-outcome test cannot distinguish drifted from undrifted liquidation, so
a mutation mispricing long/short exits passed; a behavioural test now pins
both asymmetric L/S cases and the wiped-out refusal. The generalized-
instance sweep found one surviving FQCV-004 pattern: **FCR-002 (P3,
closed)** — Stage 1's dead copied ingestion still stored `int(code or 0)`;
it now mirrors the corrected monthly pattern and the directory-wide
missing-industry regression covers the Stage 1 file. Both closures were
verified red under their exact mutations and green restored.

Validation on the final tree: corrected QC battery file **38 passed**;
focused research/QC/LEAN/document gate **176 passed**; full suite **4,205
passed / 0 failed / 25 known dependency warnings in 906.90 seconds**;
compilation including `research/`, the 128-file Markdown link check,
docs/mandate JSON parses, and `git diff --check` clean. No QC access, no
research look, no broker/database/scheduler/epoch change; the lifetime floor
remains 428 and the run ledger remains five.

**Gate status: the independent counter-review Codex required is satisfied
and accepting.** Remaining before launch: a lightweight Codex
acknowledgement of FCR-001/002 (or an owner waiver — the product delta is
one dead-state ingestion guard plus two tests), then the owner's stage-order
choice, then execution from the exact merged reviewed head.

## 8. What is next

1. PR #242 merged the prior Codex integration at `f937bfb`; PR #243 then
   merged Fable's final counter-review at `4151b3f`. Codex's correction
   branch is pushed at `9e45803` and counter-reviewed (section 7q); Claude's
   counter-review branch `user/claude/alpha-qc-fable-cr-verify-20260817`
   carries the FCR-001/002 closures and awaits owner review/merge.
2. **The counter-review gate for `ac96d47` is satisfied.** Remaining:
   Codex acknowledges FCR-001/002 (or the owner waives it), and
   the owner must confirm stage ORDER: the round-2 rerun
   contract centres on Stage 1 (REP-H52/REP-IDV plus cadence-matched
   benchmarks), while plan §5 still requires Stage 0 battery completion.
   Codex's original contract items remain binding, including `855941a`, the
   follow-up local formula correction, Stage 1 timing/factor alignment,
   turnover/NAV behavior, current LEAN syntax, benchmark/analyser refusals,
   and evidence provenance. Only then run the frozen next QC stage. Record
   project, compile, backtest, exact source, log/result hashes, windows, and
   before/after look counts.
3. Append every execution to `docs/alpha-result.md`; never rehabilitate or
   silently recreate historical invalid artifacts. A premature run is
   `PENDING_REVIEW`, still counted, and must be rerun from reviewed source.
4. The owner has completed steps 1 and 2 of the dev-app walkthrough; Stage 2
   steering is confirmed working. Step 3 is in progress against a COPY of
   the development database at
   `data/dev_scratch_withfills.db` with the kill switch engaged. That copy
   carries 108 proposals and 72 broker order events across 17 tickers, all
   buys, so real journaled lots exist for JEPI, JEPQ, NVDY, AVGO, MSFT and
   NVDL. The dev app must be restarted to pick up these rounds.
5. **The remaining REBAL test gap is unchanged:** no test clicks the Streamlit
   trim button through to a saved proposal. Everything below that seam is
   now covered end to end against real journaled fills.
6. REBAL-1 has no Stage 4 in the adopted plan. Any new rebalancing feature
   needs a new owner-approved plan and scope.
7. Resolve whether the 60-day epoch-005 hold means calendar days (roughly
   43 weekday observations) or 60 captured market sessions.
8. The SET-1 design question remains open: whether strict whole-share mode
   should allow a fractional sell only when it closes an entire position.
9. `TRADE1CR-002` is closed as validation hygiene in this review: the two
   synthetic strategy-history helpers now end at the latest completed market
   session rather than the calendar day, so Monday pre-market runs no longer
   manufacture future/stale bars. Runtime freshness behavior is unchanged.

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
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/Alpha_Test_Implementation_Plan.md,
docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md, docs/alpha-result.md and
docs/SESSION_HANDOFF.md. origin/main is 4151b3f after PR #243 merged Fable's
final counter-review (PR #242 at f937bfb merged the counter-review integration
branch; PR #241 at d8a3260 merged the full audit before it). Corrections
855941a and 1e2b631 repair current LEAN Python
syntax, point-in-time/exact-session factors, Stage 1 cadence and benchmark,
strict analyzer provenance, bounded QC polling, old local turnover/NAV,
leave-one-out peers and joint residual regression. Invalid generated result
files were removed only after docs/alpha-result.md preserved their exact
hashes and dispositions (ledger hashes are CRLF working-tree hashes — see
the ledger's verification-convention note). No QC access or new result
occurred; every old result
is unusable, the lifetime floor remains 428, and no alpha milestone completed.
Claude counter-reviewed exact head b4e9ee0 (section 7m, three P3 closures
CR2-001..003), Codex independently accepted ad3b3a8 after a topology
correction (section 7n), and a final independent Claude counter-review of the
whole ten-commit chain from exact head 5730f7b (section 7o and
docs/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md) accepted every
commit, ran sixteen mutations, and closed four P3 gaps (CCR3-A..D) on branch
user/claude/alpha-qc-full-counterreview-20260817. Codex then reviewed Fable's
exact three-commit range after PR #243 and found two P2 Stage 0 methodology
defects plus two P3 input/refusal defects. Correction ac96d47 fixes same-period
entry/exit turnover, per-family 12/42 annualization, strict MAX(20), and
missing-industry grouping; see section 7p and the Fable-counterreview report.
Claude then pushed that branch unchanged at exact head 9e45803 and
counter-reviewed it (section 7q and
docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_CORRECTION_COUNTERREVIEW.md):
all three commits accepted, all four findings reproduced red pre-correction,
seven mutations run, and two follow-up P3 closures (FCR-001 exit-drift pin,
FCR-002 Stage 1 dead-state industry port) on branch
user/claude/alpha-qc-fable-cr-verify-20260817. The ac96d47 gate is satisfied;
before launch, Codex acknowledges FCR-001/002 (or the owner waives it) and
the owner confirms whether Stage 0 battery completion or Stage 1 runs first.
No run occurred and the 428-cell/five-run counts are unchanged.
Append every run rather than overwrite ledger entries; a premature run is
PENDING_REVIEW and still counts.
paper-epoch-005 remains unchanged at 752d3b7 for 60 days; operational
my_policy.json stays 0.50/0.05. Do not merge, deploy, roll the epoch, mutate
the operator database, submit orders, access funded accounts, begin M4, or
enable live trading without explicit owner authority.
```
