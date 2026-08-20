# Session handoff — full research/QuantConnect audit and documentation reset

Prepared: 2026-08-17 by Codex after a clean-slate review of every research and
QuantConnect module changed during the 2026-08-16/17 alpha work, correction
of the local measurement path, and a validity/organization audit of the
documentation. This section and section 7l supersede earlier alpha current-
state language while retaining the earlier sections as historical review.
Updated later on 2026-08-17 by Claude's FINAL counter-review of the complete
correction chain (section 7o), then by Codex's verification after that review
merged as PR #243 (section 7p), then by Claude's counter-review of Codex's
Stage 0 correction (section 7q), and finally by Codex's independent
verification of that counter-review after PR #244 (section 7r), Claude's
two-run Stage 0 launch (section 7s), and Codex's correction review (section
7t). Section 7t
and the updated topology/next-steps text are the current state.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/Alpha_Test_Implementation_Plan.md`
4. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_FABLE_COUNTERREVIEW.md`
5. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md`
6. `docs/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_ROUND.md`
7. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`
8. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW_INDEPENDENT.md`
9. `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW.md`
10. `docs/alpha-result.md`
11. `docs/Review/REVIEW_2026-08-16_ALPHA_QC_ROUND1.md`
12. `docs/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md`
13. `docs/research/ALPHA_BATTERY_METHOD_V2.md`
14. `docs/research/ALPHA_BATTERY_2026-08-16_QC_PREREGISTRATION.md`
15. `docs/research/Alpha explanation.md`
16. `docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md` (prior local round)
17. `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
18. `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
19. `docs/operations/MANDATE.md` (§2, §4, §6)
20. `docs/operations/OPERATIONAL_FACTS.md`
21. `docs/operations/OPERATIONS_RUNBOOK.md`

Nothing here authorizes a push, merge, pull request, deployment, evidence
repair, epoch roll, M4, funded-account access, live trading, paper order,
operator-database mutation, or scheduled-task change.

## 1. Exact repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Published `origin/main` at audit time:
  `1457169ba10f6aac0f1fb98b60b92a4607f8331c`. PR #245 merged Codex's prior
  verification branch; PR #244 at `b6f577e` merged Claude's exact
  Stage 0 counter-review head `9a7e9fc`; both have tree
  `0fe65449a58aaca1363fc9d4783ee89ccf1cfbcc`. PR #243 merged Fable's exact
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
- Codex verification branch:
  `codex/review-alpha-qc-fable-cr2-20260817`, based on exact Claude head
  `9a7e9fc`. Test correction `39e5d99` closes FCRV-001 by pinning the live
  `_fine` industry-guard call sites across the monthly, short, and Stage 1
  algorithms. No algorithm behavior changes; section 7r records the review.
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

*(Superseded by section 7r: Codex completed the requested acknowledgement
after PR #244 merged the exact counter-review head.)*

## 7r. Codex verification of the Stage 0 correction counter-review (2026-08-17)

Codex reviewed only the pushed remote
`origin/user/claude/alpha-qc-fable-cr-verify-20260817` from exact base
`9e45803` through ordered commits `c2f594e`, `4ee9419`, and `9a7e9fc`.
PR #244 merged that exact head at `b6f577e`; the merge and branch both have
tree `0fe65449a58aaca1363fc9d4783ee89ccf1cfbcc`. Full record:
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md`.

All three Claude commits are **accepted after one P3 test-sensitivity
correction**. FCR-001's drifted long/short exit math and wiped-out refusal
were independently checked and mutation-proven. FCR-002's Stage 1 industry
guard is correct and cannot affect a current result because that copied map
is presently written but not read. No result-changing defect was found.

**FCRV-001 (P3, closed):** Claude extended a helper-only invalid-industry
test to the Stage 1 file, but that test stayed green if the live `_fine`
call site was reverted to `int(code or 0)` while the helper remained correct.
Commit `39e5d99` adds a three-algorithm regression that requires each live
ingestion path to call `_valid_industry_code`, forbids direct conversion of
the Morningstar field, and requires stale-map eviction. The exact Stage 1
call-site mutation fails the new test and the restored implementation passes.
This changes tests only, not QuantConnect behavior.

Focused validation is **242 passed** and the QC battery file is **41 passed**.
The full suite is **4,208 passed / 0 failed / 25 known dependency warnings**;
compilation including `research/` is clean; the active-document gate is **31
passed**; all 131 tracked Markdown links and all 5 tracked docs/assistant JSON
files validate. Final diff, status, staged-content, and ordered-commit
validation is recorded in the verification report. No QuantConnect access,
research look, broker/database/scheduler/epoch mutation, or trade occurred;
the lifetime floor remains 428 and the run ledger remains five.

**Gate status: ACCEPTED.** The algorithm code merged in PR #244 needs no
further correction. Codex's acknowledgement of FCR-001/002 is complete. The
owner must choose Stage 0 or Stage 1, then the selected frozen run must use
the reviewed PR #244 algorithm source and be recorded as R-005 or later with
the complete evidence contract.

## 7s. Stage 0 launch round: two refusals, root cause found and fixed (Claude, 2026-08-17)

The owner authorized QC testing (Stage 0 first, at most two concurrent
sessions, project naming per the new `docs/process/QC_RUN_CONVENTIONS.md`).
Round branch: `user/claude/qc-stage0-run-20260817` (pushed). Facts:

- The org's backtest-node pool allowed only ONE concurrent backtest (a
  second `backtests/create` refused with "no spare nodes"); the two-session
  subscription limit is a live-coding-session resource. Runs proceed
  strictly serially; nothing from the prior day was stuck.
- **R-005** `1. MONTHLY_BATTERY_A_LARGE - 20260817` (project 35285587) and
  **R-006** `2. MONTHLY_BATTERY_B_CORE - 20260817` (project 35285594) both
  completed and REFUSED identically:
  `INCOMPLETE|missing_specs=MULTI_ALPHA_COMPOSITE|RESIDUAL_MOM_12_1|RESIDUAL_MOM_6_1`.
  Full identities, source hashes, and log hashes are in the permanent
  ledger. Run-level look count is now SEVEN; zero cells emitted; the
  428-cell floor is unchanged.
- Per the pre-declared stop rule, Stage 0 halted at two of nine runs. A
  local LEAN-stub simulation (`tests/test_alpha_battery_monthly_sim.py`)
  reproduced the exact signature under LEAN's real event timing and found
  the root cause: daily bars are labeled with the NEXT calendar day, so a
  month ending on a Friday delivers its last bar labeled
  Saturday-the-1st — before that month's selection exists — and
  `_record_factor_returns`, keying membership by the label's month,
  recorded such days with empty industry buckets, poisoning every
  504-session residual window. Fix `0f0611c` binds each factor day to the
  membership in force at record time and reuses that recorded key at score
  time; the simulation reddens under the reverted fix. Stage 1, the short
  battery, and both benchmarks hold no month-keyed membership history and
  are unaffected.
- Also this round: the QC log endpoint requires a literal `query`
  parameter, and the run driver now persists a completion verdict before
  attempting log retrieval.

**Launch gate: Stage 0 reruns are BLOCKED until `0f0611c` is independently
reviewed and counter-reviewed per the standing workflow.** Reruns get new
R-numbers; R-005/R-006 remain counted.

## 7t. Codex review of the Stage 0 launch round (2026-08-17)

Codex reviewed the exact pushed range `423a818..eee4368` from remote branch
`origin/user/claude/qc-stage0-run-20260817`, based on `1457169`. Full record:
`docs/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_ROUND.md`.

The two refusals, the stop decision, seven run-level looks, zero new cells,
and unchanged 428-cell floor are accepted. All five commits are accepted
after correction, but Stage 0 remains blocked pending counter-review of the
Codex head. Findings closed:

- **QCS0R-001 (P1):** `0f0611c` fixed weekend empty buckets but still used a
  new month's selected names and industries for the prior day's return when
  first-of-month selection ran before bar delivery. Correction `2219643`
  snapshots both and retains the prior snapshot at that transition. The real
  class reproduced February labeling red and January's four exact ten-name
  buckets green after correction.
- **QCS0R-002 (P2):** R-006's ledger named source commit `423a818`; its saved
  evidence proves `bfc9b8b` and uploaded hash `428ef88b...3fa40`. The ledger
  now records the exact identity and UTC timestamps.
- **QCS0R-003 (P2):** the driver hashed LF memory while Windows wrote CRLF,
  so neither “raw log” hash matched its file. Both actual and historical
  normalized hashes are preserved; future logs use exact byte writes/hashes.
- **QCS0R-004 (P2):** launch could overwrite a prior evidence JSON/log. New
  runs require a fresh JSON under `artifacts/` and refuse existing identities.
- **QCS0R-005 (P3):** positive run numbers, real YYYYMMDD dates, and the exact
  cloud-returned project id/name are now enforced and recorded.
- **QCS0R-006 (P3):** the runner's duplicate Git identity implementation
  failed the full-suite guard. It now uses the canonical strict
  `assistant.runtime_identity.current_commit()` contract.

Focused validation is **165 passed**; the final runtime-identity/focused gate
is **143 passed**. Full validation is **4,222 passed / 0 failed / 25 known
dependency warnings**; compilation including `research/` is clean; 134
Markdown files have zero broken relative links and all 5 tracked JSON files
parse. Codex did not access QuantConnect or consume
a research look; no operational trading state changed.

**Gate: BLOCKED pending Claude counter-review.** After acceptance, the next
execution is R-007 or later, serial, with a new immutable evidence path.
R-005/R-006 must never be overwritten or renumbered.

## 7u. Counter-review of the launch-round review (Claude, 2026-08-17)

Claude pushed Codex's local branch unchanged to freeze exact head `81db126`,
then counter-reviewed it on `user/claude/qc-stage0-review-verify-20260817`.
Full record:
`docs/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_COUNTERREVIEW.md`.

All three commits accepted; all six QCS0R findings confirmed, including the
P1 in Claude's own boundary fix (new-month selection leaking backward onto
the prior day's bar when both share a slice) — reproduced red on Claude's
exact head — and the CRLF log-hash trap Claude itself had documented as
CCR3-D the same morning. Every hash claim was re-derived independently and
matches. Seven mutations ran: five detected, two survivors closed as
**QCS0CR-001** (the previous-month snapshot could become the RULE —
month-stale membership on ordinary days was unpinned) and **QCS0CR-002**
(`require_clean=True` at the launch commit check was unpinned), both with
mutation-verified tests. Validation on the final tree: focused sim/runner
gate 15 passed; full suite **4,223 passed / 0 failed / 25 known dependency
warnings in 796.73 seconds** (one net new test: QCS0CR-001 strengthens an
existing test in place); compilation, links, JSON, and diff checks clean.

**The Stage 0 rerun gate is satisfied.** The rerun uploads product bytes
from the accepted `81db126` tree (the counter-review adds tests only), runs
serially from **R-007** with new immutable evidence paths and new project
numbers, and the cloud defect is not declared closed until the corrected
monthly run passes its completeness guard in the cloud.

## 7v. Rerun round: R-007 complete-but-unparseable, R-008 die-off; both root causes fixed (Claude, 2026-08-17)

After section 7u opened the gate, the rerun round on
`user/claude/qc-stage0-review-verify-20260817` produced two more counted
runs and exposed two more defects:

- **R-007** (`3. MONTHLY_BATTERY_A_LARGE`, project 35289096) COMPLETED with
  all ten specifications and 142 dates — the weekend-label defect is closed
  in the cloud. But its rows carry per-date spec subsets (specifications
  legitimately skip months independently), which the frozen parser refused
  as truncation: the algorithm's emission contract and the parser's
  completeness contract were never consistent, and this was the first
  monthly run ever to reach the parser. Status: **STALE**, superseded by a
  rerun that emits SPECMETA per-spec counts.
- **R-008** (`4. MONTHLY_BATTERY_B_CORE`, project 35289185) completed with
  `DATES|48` — continuous 2013-02..2017-01, then an eight-year die-off. Root
  cause: an unrecoverable refusal spiral (one all-specs-skip month left the
  settle-coupled `prior_outcomes` empty forever against stale weights).
  Status: **INVALIDATED**.

Both fixes are implemented and committed: drift outcomes now come from each
book's stored entry prices (the Stage-1/benchmark pattern) so refusals
retry and recover, stale-book names survive universe removal, the monthly
battery emits SPECMETA per-spec counts, and the parser accepts ragged dates
only when a complete SPECMETA inventory verifies every per-spec count
(refusing as before otherwise). The extended simulation drives a forced
all-skip month AND pipes the algorithm's own emitted log through the real
parser — red on the pre-fix tree in both directions, green after. Run-level
look count is now NINE; the 428-cell floor is unchanged; focused gate 164
passed.

**Launch gate: Stage 0 remains HALTED pending independent review of these
fixes.** After acceptance: rerun monthly A/B (new R-numbers), then C, the
short battery A/B/C (unaffected by both defects — no cross-period state,
full rows guaranteed by its packed format), and the benchmarks A/B/C.

## 7w. Owner-directed continuation: R-009 parses end to end, R-010 exposes zombie names (Claude, 2026-08-17)

The owner explicitly directed "continue to test. 1 at a time" on the fixed
but not-yet-reviewed tree, so the serial rerun resumed with every entry
ledgered **PENDING_REVIEW**:

- **R-009** (`5. MONTHLY_BATTERY_A_LARGE`, project 35289732, source
  `05929a5`) COMPLETED: all ten specifications, `DATES|142`, ten SPECMETA
  lines, and — for the first time ever — the raw cloud log **round-trips
  through the frozen parser** (619 spec-rows). Parsing only; no statistic
  observed. Both 7v fixes are now cloud-confirmed on A_large.
- **R-010** (`6. MONTHLY_BATTERY_B_CORE`, project 35289860, source
  `8957e32`) is **INVALIDATED** by a second, distinct state-machine defect:
  `DATES|54` (2013-02..2018-11) with PROGRESSIVE per-spec collapse
  (SPECMETA periods 3..42 instead of ~140). Root cause: **zombie names** —
  a name whose data ends without a delisting event stays in the stale bound
  book at an unpriceable entry, its per-key drift turnover refuses forever,
  and the turnover-gated bind killed each specification the first time its
  book trapped one. A_large never traps one; B_core does readily.

Fix `d305ea0` removes the class, not the instance: **turnover never gates a
result row.** The bind always proceeds; an unpriceable month emits an empty
turnover field; the frozen analyser accepts it as declared unavailability,
charges the conservative full 1.0 one-way (the local `net_of_costs`
convention), and disclosures `unavailable_turnover_periods`. The same
defect class in the local battery (`long_short_returns` dropped a month's
RETURN on a refused drift) is fixed identically. Pinned by a zombie-name
LEAN-stub simulation (real parser + real analyser round-trip) and a local
wiped-out-book return-retention test; four reverse mutations (bind gate,
local gate, parser strictness, analyser refusal) all redden. Run-level look
count is now **ELEVEN**; the 428-cell floor is unchanged.

Serial rerun continues per the owner's direction: monthly B_core next
(project #7), then monthly C, short A/B/C, benchmarks A/B/C — every entry
PENDING_REVIEW until Codex reviews `49e8160`..`d305ea0`.

## 7x. Stage 0 battery COMPLETE: nine runs, two more defect classes fixed (Claude, 2026-08-18)

The serial rerun ran to completion overnight. Fourteen cloud runs this
continuation (R-009..R-022, run-level look count now **TWENTY-THREE**),
producing all nine Stage 0 cells on the same fixed tree, every one
ledgered in `docs/alpha-result.md` with full identity and structural
round-trip through the frozen parsers, **no statistic observed anywhere**:

- **Monthly battery:** R-009 (A_large, 619 spec-rows), R-011 (B_core,
  1,233 spec-rows), R-012 (C_broad, 1,089 spec-rows — its first `wait`
  dropped on a transient local DNS failure at 72% and re-attached
  cleanly; the cloud run was unaffected).
- **Short battery:** R-013 (A_large) REFUSED — the packed v1 log layout
  had no way to declare an absent spec-date, so one honest missing MAX_20
  date (2016-01-29) withheld all 2,664 cells. Fix `46221db`: per-date u8
  spec-presence mask (layout `b64block_date_u32_mask_u8_i32x4_u16x3`),
  u16 65535 reserved as the turnover-unavailability sentinel, turnover
  never gates a `_settle` row; the parser decodes both layouts so R-002's
  v1 logs stay readable. R-014 (A_large rerun): identical computation now
  emits all 2,664 cells with the one absence declared. R-015 (B_core,
  periods 508–531 — unreportable under v1) and R-016 (C_broad, periods
  496–523) complete the family.
- **Benchmark:** R-017 (A_large) INVALIDATED — third instance of the
  R-010 zombie defect, in `universe_benchmark.py` which no earlier fix
  touched: the turnover-gated bind died silently at 2015-12 and reported
  48 of ~156 months while "completing" normally (fail-silent, worse than
  R-013's fail-closed). Fix `5b5184a`: bind always proceeds; empty BROW
  turnover field = declared unavailability charged 1.0. R-019 (B_core)
  INCONCLUSIVE then exposed the second-order flaw: requiring EVERY
  entered name to price on the settlement session collapsed coverage to
  94/156 months clustered in delisting-heavy stretches — a selectively
  calm baseline sample that §6's "include missing baseline rows" rule
  forbids. Fix `39b3b89`: months emit over the priced subset
  (≥ MIN_NAMES) with priced AND entered counts in five-field BROW rows;
  the analyser discloses `underfilled_months`. R-020 (B_core, 155/156
  months, worst underfill 99.83% priced), R-021 (C_broad, 155/156), and
  R-022 (A_large, 155/156; its 149 months shared with the superseded
  R-018 match to 0.0) complete the family. R-018 is marked STALE.

Every fix followed the full discipline: ledger the failure first,
regression tests that drive the REAL algorithm through the REAL parser
(`tests/test_alpha_battery_short_emitter.py`,
`tests/test_universe_benchmark_sim.py`), reverse-mutation verification
(seven mutations across the two rounds, all reddened and restored — one
caught a vacuously-passing test, hardened in `075e982`), and the full
battery on the exact final tree (last run: 4,239 passed / 25 warnings,
compileall clean, `git diff --check` clean).

**Review debt is now the sole blocker.** The product range for Codex is
`49e8160`, `d305ea0`, `46221db` (+ test hardening `075e982`), `5b5184a`,
`39b3b89` on `user/claude/qc-stage0-review-verify-20260817`; records
commits interleave. Upon acceptance the nine PENDING_REVIEW runs upgrade,
and only then do the frozen analysers run ONCE with full run identities —
the single step at which statistics are observed (Bonferroni over the
180-cell family; conservative lifetime cell floor grows with this round's
repeats and is recomputed in the ledger at that point).

## 7y. Independent review of the Stage 0 battery range (Cursor/Grok) and Claude's counter-review (2026-08-18)

With Codex tokens exhausted (the section 8 deferral), the owner ran the
independent review through Cursor using Grok 4.6 on 2026-08-18. The
review covered `81db126..de1beac` — the exact 27-commit range Claude
listed, from the last counter-reviewed launch-round head to the battery
tip — and followed the project review process: every commit received an
explicit disposition, focused synthetic-fixture tests were run on
`de1beac` (108 passed), and no frozen analyser touched the nine
PENDING_REVIEW logs. Verdict: all seven product/test commits and all
twenty record commits **accepted**; conditionally cleared for the Stage 0
analyser pass; **Stage 1 blocked** by two P2 findings. Full record:
`docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md`.

Claude counter-reviewed all eight findings the same day
(`docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`,
branch `user/claude/qc-stage0-counterreview-20260818`):

- **S0R-001 (P2, confirmed):** `alpha_stage1_replications.py:444` still
  gates bind on `None` turnover — the R-010 zombie die-off, alive in
  Stage 1. No Stage 1 test covers it.
- **S0R-002 (P2, confirmed):** `alpha_stage1_benchmark.py` retains the
  R-017 bind gate, the R-019 full-book settle gate, and a four-field
  BROW emit; `analyse_qc_alpha_stage1.py` averages turnover with no
  `fillna(1.0)`. Four copies, all confirmed by source.
- **S0R-003 (P3, partially correct):** verified by execution — a literal
  `nan` turnover token is accepted by both battery and benchmark parsers
  and silently relabelled as declared unavailability; the `inf` half of
  the claim is a false alarm (both parsers refuse infinities).
- **S0R-004 (P3, confirmed):** `run_alpha_universes_20260816.py:202`
  never heals `previous` after an unpriceable month.
- **S0R-005 (P3, confirmed):** stale `_rebalance_turnover` docstring in
  the monthly battery still teaches the removed retry contract and cites
  the defective Stage 1 pattern as its exemplar.
- **S0R-006 (P3, resolved):** true at the review snapshot (`28e4c02`);
  PR #249 has since merged `de1beac` into main.
- **S0R-007 (P3, confirmed as wording):** R-022's replication identity
  check computes a numeric comparison over raw returns outside the
  frozen analyser; "no statistic observed" is imprecise. Append-only
  ledger, so the fix is a clarifying amendment later, not an edit.
- **S0R-008 (P3, confirmed and strengthened):** mutation
  `fillna(1.0)→fillna(0.0)` in the battery analyser survives **all 57**
  alpha-analyser tests (reviewer claimed only the two cited). Real code
  restored and re-verified green. Production charge is correct; the gap
  is test coverage only.

Claude's re-run of the generalized-instance grep matched the reviewer's
sibling map exactly; no new copy found. Nothing in the eight findings
invalidates the nine PENDING_REVIEW logs (S0R-001/002/004 are outside
the Stage 0 execution path; S0R-003's nan channel is unexercised by the
nine logs). Owner acceptance of the review pair is the remaining gate
before the ledger upgrade and the single frozen-analyser pass.

## 7z. Owner acceptance, ledger upgrade, and the single frozen-analyser pass (2026-08-18)

The owner accepted the review pair and authorized steps 2 and 3. Executed
in the safe order on branch `user/claude/qc-stage0-analysis-20260818`
(from merged main `c066b1e`, which contains PR #250's review records):

1. **Upgrade first, observe second.** The nine PENDING_REVIEW entries
   were upgraded to VALID and committed (`2be903f`) BEFORE any statistic
   was computed. All nine input-log hashes were re-verified against the
   ledger (9/9 exact matches, including the benchmark analyser's own
   independently computed input hashes).
2. **The single analyser pass** ran once: monthly family, short family,
   benchmark family. Outputs and their SHA-256s are recorded in ledger
   entry **A-001** (`docs/alpha-result.md`).
3. **Headline result:** on the preregistered Bonferroni gate (0.05/180 =
   2.78e-4, 20,000 draws): **IC 0/44 pass; long-short 0/44 pass;
   long-only 6/88 pass; short battery 0/60.** MULTI_ALPHA_COMPOSITE on
   A_large is disclosed insufficient (23 months < the frozen 24
   minimum). Benchmarks: equal-weight CAGR 12.6–14.2%, Sharpe 0.73–0.85.
   The six long-only passes are NOT evidence of stock-selection edge:
   the frozen test is gross-mean-vs-zero, which for long-only carries
   full market beta that the benchmarks themselves would clear, and the
   cells are not observation-matched to the benchmark months. The
   beta-free reads (IC, long-short) fail everywhere. A-001 states these
   limits alongside the result and closes S0R-007 with a clarifying
   amendment to R-022's wording.
4. This was the family's first and only observation; run-level looks
   stay 23; the lifetime cell floor stays 428 under the repeated-look
   convention.

## 7aa. S0R hardening round: Stage 1 siblings closed (2026-08-18)

Branch `user/claude/qc-stage1-hardening-20260818` (from `8c9fdc8`).
Implements the owner-authorized step 3: every open S0R finding is closed
with a regression test, and every fix was reverse-mutation verified
(defect reinstated → new test red → fix restored → green; eight
mutations total, all red).

- **S0R-001** — `alpha_stage1_replications.py` bind no longer gates on
  unavailable turnover; the emitter writes declared-empty turnover
  fields and a SPECMETA inventory (without which one honest ragged date
  would refuse the whole run — the R-007 class, found as a generalized
  instance during this round).
- **S0R-002** — `alpha_stage1_benchmark.py`: bind never gates
  (unpriceable prior names are simply absent from outcomes; the drift
  turnover declares None), settle records underfill over the priced
  subset with BOTH counts (five-field BROW), and
  `analyse_qc_alpha_stage1.py` charges `fillna(1.0)` with
  `unavailable_turnover_periods` and `underfilled_months` disclosure.
- **S0R-003** — both Stage 0 parsers refuse a PRESENT non-finite
  turnover token (`nan` was silently relabelled as declared
  unavailability); the same guard was generalized to the `ic` token,
  which had the identical dropna-before-finite pattern.
- **S0R-004** — `run_alpha_universes_20260816.py` records a wiped-out
  month's return, omits its turnover (charged 1.0 downstream by
  `net_of_costs`), and heals the book.
- **S0R-005** — the monthly `_rebalance_turnover` docstring now teaches
  the never-gate contract (it described the removed retry contract and
  cited the then-defective Stage 1 files as its exemplar).
- **S0R-008** — charge-magnitude pins: exact net-vs-gross
  `mean_period_return` deltas for the battery analyser and the Stage 1
  benchmark block. Verified need: `fillna(1.0)→fillna(0.0)` in the
  battery analyser previously survived ALL 57 alpha-analyser tests.

New tests: `tests/test_alpha_stage1_hardening.py` (4 tests, stub-loaded
real algorithm classes + real analyser CLI end to end), plus 2 in
`tests/test_qc_alpha_battery.py` and 1 in
`tests/test_alpha_battery_research.py`.

Deliberately NOT changed: the settle-side `any(symbol not in outcomes)
→ continue` in the replications/monthly settle is the reviewed, frozen
Stage 0 contract (a fixed portfolio's return is undefined without every
name's outcome; the drop is visible via SPECMETA periods), not a
sibling of the bind defect.

**Validation on the exact final tree:** focused suites green (102);
full `python -m pytest -q`: **4,232 passed, 14 failed, 25 warnings**.
All 14 failures are UI tests (`test_ui_discrete_tabs`, `test_ui_theme`,
`test_ui_user_directed_sell`) and reproduce IDENTICALLY at the
pre-hardening commit `8c9fdc8` in a clean worktree — they are
machine-environment failures, not this round's: the installed Streamlit
is 1.52.2 while `requirements.txt` pins 1.60.0. `compileall` clean;
`git diff --check` clean.

**RESOLVED 2026-08-18 (same day):** the owner enabled Windows long
paths (`LongPathsEnabled=1`, elevated registry change); the pinned
`streamlit==1.60.0` then installed cleanly, all 14 UI tests pass, and
the FULL suite on the exact hardening tree (`602dc0b` product code) is
**4,246 passed, 0 failed, 25 warnings** — the validation record for
this round is now fully green with zero environmental exclusions. The
paragraph below is retained as the record of the original observation.

**Machine-local operational observation (original, now resolved):** this
machine cannot install the pinned `streamlit==1.60.0`: the wheel
contains a file whose absolute path under the Store-Python
site-packages is exactly 260 characters, and `LongPathsEnabled=0`, so
pip fails with `[Errno 2]` and rolls back to 1.52.2 (verified; the
rollback is clean and the UI still runs on 1.52.2). Yesterday's green
full runs imply the downgrade happened between the battery session and
today — plausibly during the Cursor review session's environment
activity. Options: enable Windows long paths (admin registry change),
or a Python install at a shorter prefix. Until then the 14 UI tests
fail on THIS machine only, and the operator UI runs on 1.52.2 rather
than the pinned version.

Stage 1 remains blocked until this round passes independent review.

## 7ab. Independent review of the S0R hardening round: ACCEPTED (2026-08-18)

A fresh, independent Claude session (which did not author the range)
reviewed `de1beac..fba1c0b` per the process doc and **accepted all
eleven commits**: 0 P0, 0 P1, 0 P2, two P3 observations closed without
code change (SHR-001: malformed non-numeric tokens refuse via ValueError
rather than a typed error — same fail-closed direction, cosmetic;
SHR-002: the bind test stubs `_rebalance_turnover` — accepted since the
None contract is mutation-pinned and the helper is a verified copy of
monthly's). The reviewer re-executed SEVEN reverse mutations plus two
extras (stage1 fillna, ic guard) — all red — reproduced the pre-fix
nan-acceptance defect from `8c9fdc8` by execution, proved the SPECMETA
inventory is load-bearing by stripping it from a real emitted log
(parser refused), verified every merge tree equals its second parent,
verified the VALID upgrade preceded the analyser outputs, and agreed
with both contested counter-review classifications AND the deliberate
settle-gate non-change (with four stated reasons). Record:
`docs/Review/REVIEW_2026-08-18_S0R_HARDENING_REVIEW.md`.

**One defect in the review report itself, flagged here as the
acceptance record:** its section 9 claims full validation but the
`python -m pytest -q` line was left as `FULL_SUITE_PLACEHOLDER` — the
reviewer recorded no full-suite run of their own. The report is
committed verbatim (review records are not edited after the fact). The
review tree is byte-identical to `fba1c0b`
(`63ff84119baf7eed14b0b7eb90dae0006e05bd64`, re-verified), on which the
authoring session's full run recorded **4,246 passed / 0 failed / 25
warnings** — so the gap is attributional, not substantive: the
reviewer's own executed evidence (102 focused tests, nine mutation
runs, compileall, git diff --check, probes) stands on its own.

**Net state: the code gate in front of Stage 1 is CLEARED.** The
remaining gate is the owner's decision whether Stage 1's 24-cell
counted family is worth spending given the A-001 nulls — the review
explicitly does not authorize the launch. The reviewer's stated
residual risk carries forward: the stub harness exercises the real
classes but not LEAN's own callback ordering, so Stage 1's first cloud
run must round-trip the frozen parsers before any statistic is read.

## 7ac. Reviewer's correction of section 7ab (2026-08-18, reviewer session)

Section 7ab was written by a DIFFERENT session than the reviewer, at
12:33 local, while the reviewer's own full-suite run was still
executing, and it committed the reviewer's in-progress draft report
(`d905f2b`) taken from the shared worktree. Three corrections of
record, superseding 7ab's wording (7ab itself is retained unedited):

1. **The "one defect" no longer exists and was never a defect of the
   finished review.** The `FULL_SUITE_PLACEHOLDER` was a deliberate
   placeholder in an in-progress draft awaiting the background
   `python -m pytest -q` run. That run completed at 12:40 with
   **4,246 passed / 0 failed / 25 warnings in 946s** — the reviewer's
   OWN independent execution on the byte-identical tree, not a citation
   of the authoring session's figure — and the reviewer filled the line
   in `3a59568`. The final committed report contains no placeholder and
   claims nothing it did not run.
2. **The mutation count is eight, not nine:** five required reverse
   mutations (replications bind gate, benchmark bind gate, benchmark
   settle full-book, battery analyser fillna, battery parser
   turnover_ls) plus three extras (stage1 analyser fillna, ic guard,
   universes book-heal). All eight red, all restored. The review
   document's section 5 is the authoritative list.
3. **Process note for future rounds:** committing another session's
   in-progress working file mid-review is the same shared-worktree race
   this repository has already ledgered once (the PR-merge push race).
   A review report should be committed only by the session that wrote
   it, after it declares the review complete. No harm resulted here —
   the draft was committed verbatim and the reviewer's follow-up commit
   completed it — but the "defect" 7ab flags is an artifact of that
   premature commit, not of the review.

The acceptance itself stands as 7ab states: all eleven commits
accepted, 0 P0–P2, code gate before Stage 1 cleared, Stage 1 launch
remaining an owner decision.

## 7ad. Counter-review of the S0R hardening review: VERIFIED (2026-08-18)

The authoring session counter-reviewed the independent review at
`f84f5fa` (`docs/Review/REVIEW_2026-08-18_S0R_HARDENING_COUNTERREVIEW.md`,
branch `user/claude/s0r-hardening-counterreview-20260818`): all six
tree-identity hashes re-verified exact; the upgrade-before-outputs
timing re-verified (11:02:17 commit vs 11:03:23+ output mtimes;
`de1beac..2be903f` is five docs only); the SHR-001 `abc`-token probe
reproduced (`ValueError`, fail-closed); mutation (e′) — the ic-guard
revert the authoring session had never itself run — re-executed red
then green; the draft-to-final report diff confirmed as solely the
reviewer's own full-suite figure; §7ac's corrections confirmed
accurate, including the eight-mutation count. SHR-002 and the
settle-gate agreement fact-checked and agreed. **The review stands as
the review of record; the Stage 1 code gate remains cleared; the only
remaining gate is the owner's Stage 1 go/no-go.**

## 7ae. Cursor/Grok follow-up review of de1beac..07bb819: accepted, S0R2-001 fixed (2026-08-18)

The owner ran a second Cursor/Grok round over everything since the
previous Cursor head (`de1beac..07bb819`, 20 commits) — a genuine
independent re-verification, not a rubber stamp: it re-read `602dc0b`
claim by claim, ran its own two reverse mutations (both red, restored),
verified all nine owner merge trees, and accepted every commit with 0
P0/P1/P2. It raised two P3s: **S0R2-001** (the nine run headings and
two summary paragraphs in `docs/alpha-result.md` still said
PENDING_REVIEW / "no statistic observed" above A-001 — confirmed and
FIXED this round: headings retitled VALID, dated superseding notes
appended, originals retained) and **S0R2-002** (the `2be903f` upgrade
used VALID where the frozen vocabulary's honest intermediate was
UNANALYSED — closed without change on the final tree; the vocabulary
rung PENDING_REVIEW → UNANALYSED → VALID is recorded for future
rounds). Claude's counter-review executed the review's own §10
checklist in full and verified its checkable claims 100%
(`docs/Review/REVIEW_2026-08-18_S0R_FOLLOWUP.md` and
`…_FOLLOWUP_COUNTERREVIEW.md`). **The `602dc0b` review chain now has
cross-vendor diversity: author + fresh Claude + Cursor/Grok, seventeen
mutation executions across three sessions, all red.** The Stage 1 code
gate remains cleared; the owner's Stage 1 go/no-go remains the only
gate.

## 7af. Owner GO for Stage 1; launch driver extended (2026-08-18)

**Owner decision 2026-08-18: "go stage 1. proceed with the launch
driver."** The go was given against the recommendation on record: run
the preregistered Stage 1 (REP-H52 + REP-IDV with the cadence-matched
benchmark, 24-cell family, gates frozen in
`scripts/analyse_qc_alpha_stage1.py`), with the stated protocol that a
null result ENDS the cross-sectional alpha program on this universe —
no variant mining afterward — and effort redirects to where wins have
actually appeared (portfolio construction, risk, paper-observation
infrastructure). A null is the expected outcome and is treated as a
finding, not a failure.

This round (branch `user/claude/stage1-launch-driver-20260818`, from
`08f23a1`): `scripts/run_qc_stage0.py` gains the two Stage 1 families —
`stage1` → STAGE1_REPLICATIONS (`alpha_stage1_replications.py`) and
`stage1-benchmark` → STAGE1_BENCHMARK (`alpha_stage1_benchmark.py`) —
a two-entry FAMILIES addition; everything else (clean-commit binding,
universe retargeting, naming, evidence JSON, log hashing, serial wait)
is the reviewed Stage 0 machinery unchanged. New regression tests pin
the exact family→file mapping and, against the REAL files, that every
family source retargets each universe by exactly one changed line (the
launch precondition whose failure would otherwise cost a counted look).
Both reverse mutations red then green (dropped entries; a duplicated
ACTIVE_UNIVERSE constant in a real family file).

**Launch sequence from here:** (1) this driver round gets its quick
independent review — launch plumbing is where this project's sneaky
bugs have lived; (2) then six serial cloud runs (2 families × 3
universes, project numbers continuing from 18), one at a time, each
ledgered at launch with full identity, each structurally round-tripped
through the frozen parsers before the next — per the standing
residual-risk note, the stub harness does not test LEAN's callback
ordering, so the first run's round-trip is the real integration test;
(3) the frozen Stage 1 analyser runs ONCE after all six complete
structurally — the only step at which any Stage 1 statistic is
observed (stage gate 0.05/24; lifetime gate 0.05/452).

## 7ag. Driver review accepted; Stage 1 runs begin (2026-08-18)

Cursor/Grok reviewed the launch-driver delta (`08f23a1..f821fb1`) and
**accepted both commits with zero findings**
(`docs/Review/REVIEW_2026-08-18_STAGE1_LAUNCH_DRIVER.md`, pushed on
`user/cursor/review-stage1-launch-driver-20260818`): the diff is the
two-entry FAMILIES table plus tests only; `require_clean=True` and the
log-fetch `query` parameter (the two historical launch-plumbing defect
classes) verified intact and still test-pinned; both reverse mutations
re-executed red; `universe_smoke.py` confirmed correctly excluded.
Claude counter-verified the merge-tree and main-state claims (PR #256
merged the driver; `875d003^{tree}` == `f821fb1^{tree}`). With the
owner GO (7af) and this review, the six serial cloud runs proceed:
project numbers 19–24, stage1 A/B/C then stage1-benchmark A/B/C, one
at a time, each ledgered with full identity and structurally
parser-round-tripped before the next; the frozen Stage 1 analyser runs
ONCE afterward.

## 7ah. Stage 1 complete: NULL on every beta-free cell; the alpha program closes (2026-08-18)

The six serial cloud runs (R-023..R-028, projects 19–24) all completed
structurally on the FIRST attempt with zero refusals — the S0R-hardened
contracts (SPECMETA raggedness, declared-unavailable turnover,
underfill recording, five-field BROW) all proved themselves in the
cloud. The frozen Stage 1 analyser then ran ONCE (ledger entry A-002;
run-level looks ended at 29; lifetime cell floor 428 → 452).

**Result: NULL.** IC 0/6 (best 3.2e-3 vs gate 2.08e-3); long-short 0/6
with three negative Sharpes; the 10/12 long-only stage-gate clears sit
directly on top of their own same-dates equal-weight benchmarks
(cell Sharpes 0.84–1.01 vs benchmark 0.78–0.83) — the matched-benchmark
design did exactly what it was built for, showing the long-only passes
are market beta, not selection.

**The preregistered consequence executed: the cross-sectional alpha
program on this universe is CLOSED** (A-002; owner GO protocol,
section 7af). Two full families (180 + 24 cells) with zero beta-free
passes, after eleven null local signals, against a measured 2–4% MDE
power ceiling. Effort redirects to portfolio construction, risk, and
paper-observation infrastructure.

One operational defect found at the analysis step: the Stage 1 analyser
lacks the `sys.path` bootstrap of its siblings, so script-mode
invocation crashes at import (module-mode `python -m` was used; frozen
bytes unchanged; no data touched by the failed attempt). P3, backlog
for the next hardening round alongside SHR-001.

## 7ai. Stage 1 run-ledger review accepted; S1R-002/003 fixed (2026-08-18)

Cursor/Grok reviewed the runs round (`875d003..dec0a8a`, 7 commits) and
**accepted all seven** as a ledger/process round: 0 P0/P1/P2; sequencing
judged correct and better than Stage 0 (UNANALYSED per run, VALID only
in the A-002 commit, headings and rows together); all six append
commits verified free of analyser output; family arithmetic and both
gates re-checked. Three P3s: S1R-001 (the already-disclosed stage1
analyser sys.path gap — OPEN in the hardening backlog with SHR-001;
its fix must not re-invoke the analyser), S1R-002 and S1R-003 (stale
"Stage 1 still pending" text in handoff §8 and the action plan's
STAGE1 row) — both confirmed and FIXED in this commit with the
originals retained. Claude's counter-review executed the review's
checklist in full and verified every checkable claim
(`docs/Review/REVIEW_2026-08-18_STAGE1_RUNS.md` and
`…_RUNS_COUNTERREVIEW.md`). The closure record is now internally
consistent everywhere: the cross-sectional alpha program on this
universe is CLOSED, and no document any longer suggests otherwise.

## 7aj. Post-closure program: owner adopted 1-2-4-3; hygiene round done; two drafts authored (2026-08-18)

**Owner decision 2026-08-18: adopted the recommended sequence "1-2-4-3"**
— (1) hygiene tail, (2) shadow-observation infrastructure, (4)
wide-band deployment check, (3) defensive-carry preregistration.
Executed this round (branch `user/claude/analyser-hygiene-20260818`):

- **Step 1 DONE (code):** S1R-001 closed — `analyse_qc_alpha_stage1.py`
  gains the sys.path bootstrap its siblings carry, pinned by a
  subprocess test that invokes the real script in script mode; SHR-001
  closed — malformed non-numeric tokens now refuse via typed
  `InvalidLog`/`SystemExit` in both Stage 0 parsers instead of a bare
  ValueError traceback. Three reverse mutations red then restored
  green. No analyser was re-invoked on any QC log. Awaiting the usual
  quick independent review.
- **Step 4 DONE (finding, no work needed):** the wide rebalance band is
  ALREADY DEPLOYED — `assistant/rebalance_profile.py` carries the
  owner-approved (2026-08-15) profile with `band_fraction="0.25"`,
  citing the confirmed wide-band research result as mechanism while
  correctly not overclaiming it as evidence for the exact
  configuration. Nothing to change.
- **Step 2 DRAFT:** `docs/reference/SHADOW_OBSERVATION_DESIGN.md` —
  strategy-agnostic shadow-stream design (frozen-epoch registration,
  append-only observations, declared-unavailable outcomes, §6
  sufficiency reports, SHW-1..4 milestones, hard no-order/no-promotion
  boundaries). Needs owner review/adoption before any implementation.
- **Step 3 DRAFT:** `docs/research/DEFENSIVE_CARRY_2026-08-18_PREREGISTRATION.md`
  — counts the 2026-07-31 probe as discovery look #1; one primary cell
  (20% carry weight) with a composite tail-risk gate, secondary weights
  descriptive only; retrospective walk-forward + block-bootstrap leg
  plus a prospective shadow leg (SHW-4); every threshold marked
  [TO FREEZE] and binding only when the owner adopts and freezes them
  BEFORE any confirmation result. Explicitly not a reopening of the
  closed alpha program (no selection, no ranking).

Next in the adopted sequence: owner review of the two drafts (and the
hygiene round's independent review); then SHW-1 begins as its own
milestone.

## 7ak. SHW-1 implemented after a design correction (2026-08-18)

**Discovery first:** pre-implementation reconnaissance found the project
already HAS a reviewed shadow infrastructure — ML-LR-6
(`ml/shadow_runtime.py`, `scripts/run_ml_shadow.py`
register/predict/mature/monitor, the `ml_*` tables, scheduler
installers) — and that its docstring records the anti-generic-adapter
principle the first SHADOW_OBSERVATION_DESIGN draft violated. The
design was REVISED before any code: no generic framework; each observed
task gets a task-specific runtime following the ML-LR-6 pattern, with
the defensive-carry overlay as the first (and only planned) new stream.

**SHW-1 (branch `user/claude/shw1-overlay-shadow-20260818`):**
`assistant/overlay_shadow.py` — frozen registration / observation /
outcome contracts with the task's own invariants (available ⇒ complete
finite levels and no refusal reasons; refused ⇒ named reasons and NO
levels — partial imputation is unrepresentable; canonical dashed
sessions, aware timestamps, sha256/commit formats, authority-free
status vocabulary). `assistant/storage.py` — three `overlay_*` tables
mirroring the `ml_*` conventions: canonical JSON + sha256 identity,
idempotent exact retries, loud OverlayShadowConflictError on reused
identities with different content, FK-enforced registration so
unregistered or cross-epoch writes are refused, outcomes refused for
missing or refused cycles. Migration is CREATE-IF-NOT-EXISTS idempotent
and tested against a simulated pre-migration database; a full shadow
round trip is proven to leave every non-overlay table byte-identical.
12 new tests; FOUR reverse mutations red then restored (silent-keep on
conflict, settling refused cycles, partial imputation, raw
IntegrityError leak). Import-boundary suite green.

Next milestone in the design: SHW-2 (the register/observe/mature/status
runner CLI), after this round's review.

## 7al. Independent review of post-closure `main` (2026-08-18)

Cursor Grok 4.6 reviewed `66e2723..origin/main` at exact head
`f40c2c1e9bac9f91788605d0274008131a27a932` (PRs #259 and #260 on top of
Stage 1 closure). Report:
`docs/Review/REVIEW_2026-08-18_POST_CLOSURE_MAIN.md`.

**Accepted.** Every commit dispositioned. Focused tests 22 passed on an
isolated worktree. Two reverse mutations red then restored (stage1
script-mode bootstrap; overlay conflict silent-keep). No analyser rerun.
No operator DB open. No product correction in the review.

Five P3, no P0–P2:

- POST-001: storage persists raw dicts, so incomplete `available=True`
  observations that `OverlayObservation` would refuse can still be
  written. Close before SHW-2.
- POST-002: design/handoff overclaim import-boundary coverage and
  “pure computation” in `overlay_shadow.py`.
- POST-003: unused `field` import.
- POST-004: allocation-policy plan is on `main` but ACTION_PLAN does
  not schedule or defer APQ-1, so APQ-0 is incomplete.
- POST-005: SHR-001 typed malformed turnover only; long/short and BROW
  return/count tokens remain bare `ValueError`.

Do not start SHW-2 until POST-001 is decided. Do not start APQ-1 until
the owner writes the ACTION_PLAN line. Keep `paper-epoch-005` on
`752d3b7`; this tree's first `AssistantStore` open would add empty
`overlay_*` tables.

## 7al. Post-closure review counter-reviewed; POST-001..004 + POST-006 fixed (2026-08-18)

The Cursor/Grok post-closure review (`66e2723..f40c2c1`, accepted, five
P3s, isolated-worktree mutations — the shared-worktree lesson adopted)
was counter-reviewed on
`user/claude/post-closure-counterreview-20260818`
(`docs/Review/REVIEW_2026-08-18_POST_CLOSURE_COUNTERREVIEW.md`):

- **POST-001 confirmed by execution and understated** (registration also
  accepted near-empty dicts) — FIXED: storage round-trips every overlay
  payload through the frozen contracts, refuses unknown/action-shaped
  fields, persists the canonical shape; mutation-verified.
- **POST-002 FIXED**: `tests/test_overlay_import_boundary.py` pins both
  directions (direct imports); design wording corrected;
  mutation-verified. **POST-003 FIXED** (unused import).
- **POST-004 addressed to the non-owner limit**: ACTION_PLAN row records
  the allocation-policy track as PROPOSED/UNSCHEDULED; APQ-0 completes
  only on the owner's schedule-or-defer decision; the optional-test
  reporting choice is pinned to APQ-2 review in the plan.
- **POST-006 (missed by the review, found here): main was RED on the
  docs-root canonical test** — PR #260 put the plan at the docs root;
  moved to `docs/reference/` with the prereg pointer updated (placement
  only; frozen content untouched). Docs-only commits still need the doc
  suite.
- Allocation-policy documents accepted as APQ-0 content with two
  recorded interpretation limits (hindsight-conditioned window;
  APQ-2-fixed reporting decision).

**Open owner decisions:** (1) schedule APQ-1 or record deferral;
(2) SHW-2 may start only after this round's POST-001 fix passes its own
review. The operational host stays on its pinned release commit (the
overlay-table CREATE caution).

## 7am. SHW-2 implemented: the overlay shadow runner (2026-08-18)

Owner directed SHW-2 to proceed. (Process note, recorded honestly: the
owner had announced a further Cursor review of the counter-review round,
but no artifact ever appeared — no branch, no document, no worktree; if
it lands later it gets counter-reviewed then. The prior gate, POST-001's
fix, was merged in PR #263.)

Branch `user/claude/shw2-overlay-runner-20260818`:
`scripts/run_overlay_shadow.py` — register / observe / mature / status,
mirroring the ML shadow adapter split (pure cycle math in
`assistant/overlay_shadow.py`: completed month-end derivation,
whole-sleeve returns that refuse on ANY bad member, wide-band
`advance_overlay`). Task semantics implemented exactly as designed:
PROSPECTIVE baseline at the latest completed month-end (history never
backfilled), gap month-ends occupy their cycle slots as refusal rows,
each advance uses ONE fetch for boundary consistency (adjusted-close
revision safety), the band state persists via the new
`combined_carry_weight` contract field (restart-safe, auditable;
required when available, forbidden on refusals), idempotent reruns,
closed epochs refuse observations, registration binds the
preregistration document's sha256 plus a clean commit, and every
command failure records a durable `shadow_overlay` operational alert.
`status` prints counts only — sufficiency is SHW-3.

Tests: 12 new runner tests (hand-computed band math both sides of the
band, gap spanning, refusal naming, alert-on-failure, idempotency) plus
a contract test for the weight invariants; SHW-1's helpers updated for
the new field. FIVE reverse mutations red then restored: band gate
removed, baseline backfilled, gap rows skipped, partial imputation,
alert dropped. Example config at
`docs/reference/overlay_shadow_config.example.json`.

Deliberately NOT included: Windows scheduler installation (deferred to
SHW-4 stream start — there is no stream to schedule yet) and any
performance/sufficiency output (SHW-3). SHW-4 registration still
requires the owner to freeze the defensive-carry preregistration's
[TO FREEZE] gates first.

## 7an. Independent review of SHW-2 (2026-08-19)

Cursor Grok 4.6 reviewed `d4c04c4..354a233` at exact head
`354a233243d676aae05b1dc3bf53b29d6b96c2b3`
(`origin/user/claude/shw2-overlay-runner-20260818`). Report:
`docs/Review/REVIEW_2026-08-19_SHW2_OVERLAY_RUNNER.md`.

**Accepted with P2 blockers.** All three commits dispositioned. Focused
tests 28 passed. One reverse mutation red then restored (baseline
target = first completed month-end). No operator DB. No product
correction in the review.

- **SHW2-001 P2:** first `observe` writes an available baseline at 100.0
  even when a member has no close on that session (probed: DDD missing
  on 2026-02-27).
- **SHW2-002 P2:** `mature` stores a multi-month span in
  `monthly_returns` (probed: Feb→May gap, universe return 1.0 on
  cycle 2026-02-27).
- SHW2-003/004/005 P3: closed-stream test incomplete; design still
  lists SHW-2 scheduler wiring; float band math / non-PIT Yahoo.

Do not start SHW-3 or register a live overlay epoch until SHW2-001 and
SHW2-002 are fixed. Keep `paper-epoch-005` on `752d3b7`.

## 7an. SHW-2 review counter-reviewed; both P2 blockers fixed (2026-08-19)

Cursor/Grok reviewed SHW-2 (`d4c04c4..354a233`) and accepted the range
with two P2 blockers and three P3s
(`docs/Review/REVIEW_2026-08-19_SHW2_OVERLAY_RUNNER.md`, on
`user/cursor/review-shw2-overlay-runner-20260819`). Claude's
counter-review (`…_SHW2_COUNTERREVIEW.md`, same branch) reproduced both
P2 probes exactly and fixed everything fixable:

- **SHW2-001 (P2, fixed):** the prospective baseline now refuses unless
  every member is priced on the target session — the reviewer caught a
  t0 partial imputation that would have killed the series permanently
  (every later boundary unpriceable); the stream heals at the next
  month-end. Mutation-verified.
- **SHW2-002 (P2, fixed):** `mature` settles only row-adjacent AND
  calendar-adjacent available pairs; a multi-month gap span can never
  persist as `monthly_returns`. Mutation-verified.
- **SHW2-003/004 (P3, fixed):** closed-epoch gate now tested; scheduler
  wiring formally moved to SHW-4 in the design.
- **SHW2-005 (P3, split):** observations now carry a structural
  `point_in_time_data=false` that no caller can override
  (mutation-verified); the Decimal-band-math half is DECLINED with
  recorded rationale (observation analytics on float closes, not an
  authoritative money path; the frozen config already stores Decimal
  strings; any future financial authority must revisit).

SHW-3 unblocks once this fix round passes review. SHW-4 still requires
the owner's defensive-carry gate freeze.

## 7ao. SHW-2 fix round independently verified (2026-08-19)

Cursor Grok 4.6 verified `78258af..128aac8` at exact head
`128aac8b57e643b4eb8cfa098dc164ea31fb8a52`. Report:
`docs/Review/REVIEW_2026-08-19_SHW2_FIX_VERIFICATION.md`.

**Both P2s closed.** `27cb6dc` and `128aac8` accepted. Focused tests 32
passed. Reverse mutations: baseline price-check drop red; available-only
mature zip (original SHW2-002 bug) red; calendar-only drop still green
(row adjacency carries the fixture). Restored; tree left clean.

Leftover P3s: SHW2-006 (calendar belt unpinned) and SHW2-007 (stale
`or_closed` test name). Neither reopens a P2.

SHW-3 is unblocked for these findings and still needs its own scheduled
milestone. SHW-4, gate freeze, scheduler, live epoch, and any order
remain unauthorized. `paper-epoch-005` stays on `752d3b7`.

## 7ao. SHW-2 fix verification accepted; SHW2-006/007 closed (2026-08-19)

Cursor independently verified the counter-review fixes
(`docs/Review/REVIEW_2026-08-19_SHW2_FIX_VERIFICATION.md`): both P2s
confirmed closed with its own reverse mutations, the Decimal
declination accepted — and its mutation (c) caught an overclaim in the
counter-review: deleting ONLY the calendar maturity guard stayed green,
because the gap-span fixture's refusal rows already break row
adjacency. The calendar belt was real code but unpinned. Corrections
made this round: **SHW2-006 closed** — a new fixture inserts two
available observations in non-adjacent months with NO intervening row
(bypassing observe, targeting `mature` directly) and pins that nothing
settles; the calendar-only mutation now reds exactly that test
(re-executed, restored green). **SHW2-007 closed** — the stale
`…_or_closed_stream` test name renamed to match its actual coverage.
Lesson recorded: a compound mutation proves the pair, not each guard —
pin belts separately.

SHW-3 remains unblocked for findings and awaits the owner scheduling
it; SHW-4 awaits the gate freeze.

## 7ap. SHW-3 implemented: sufficiency reporting (2026-08-19)

Branch `user/claude/shw3-sufficiency-20260819` (from merged main
`553da76`). The `sufficiency` subcommand emits the section-6 fields —
observation unit (adjacent-month matured outcomes, non-overlapping),
the preregistered required count, the independent matured count, a
MET/NOT_MET verdict, and concrete insufficiency reasons — and NOTHING
else: no statistic at any count, with the report itself recording that
gate evaluation is a separate owner-authorized single pass. The
required count became a REGISTRATION contract field
(`required_observation_count`, positive integer, no default — every
stream preregisters its own; CLAUDE.md §6's no-universal-threshold
rule made structural). The report is anchored to the FROZEN
registration value; a drifted config requirement refuses loudly with a
durable alert. Read-only against the database (byte-identical snapshot
pinned by test). Five new tests; THREE reverse mutations red then
restored (boundary >= flipped to >, requirement re-anchored to the
live config, a statistic key planted in the report). CLI/file only per
open decision 3's default — no UI surface.

SHW-1..3 are now all implemented. Remaining before the stream goes
live (SHW-4): this round's review, the owner's freeze of the
defensive-carry [TO FREEZE] gates, registration binding the frozen
document, and the scheduler installation deferred to SHW-4.

## 7aq. Independent review of SHW-3 (2026-08-19)

Cursor Grok 4.6 reviewed `553da76..a384be7` at exact head
`a384be7b3c332dc40f9996fd2706ab4c01fd0d3d`
(`origin/user/claude/shw3-sufficiency-20260819`). Report:
`docs/Review/REVIEW_2026-08-19_SHW3_SUFFICIENCY.md`. Written from an
isolated worktree so the shared checkout could stay on Claude's
gate-freeze branch.

**Accepted.** Both commits dispositioned. Focused tests 38 passed. Two
reverse mutations red then restored (`>=` to `>` at the MET boundary;
requirement read from live config). No operator DB. No product
correction.

Two P3s, no P0–P2: SHW3-001 (closed epoch cannot run sufficiency);
SHW3-002 (example `24` is not an owner freeze of the draft prereg).

SHW-4 remains blocked on the owner's `[TO FREEZE]` freeze, then
registration + scheduler. Keep `paper-epoch-005` on `752d3b7`.

## 7ar. SHW-3 review counter-reviewed; SHW3-001 fixed (2026-08-19)

Cursor/Grok accepted SHW-3 (`553da76..a384be7`) with two P3s, working
in an isolated sibling worktree
(`docs/Review/REVIEW_2026-08-19_SHW3_SUFFICIENCY.md`). Counter-review
(`…_SHW3_COUNTERREVIEW.md`, on the review branch): **SHW3-001
reproduced and FIXED** — sufficiency now reads closed epochs (a closed
stream's evidence stays reportable forever; the report carries
`stream_status`) while observe/mature keep the strict write gate, both
pinned in one test with the fix mutation-verified. **SHW3-002 was
correct at its snapshot and is discharged by events**: the owner's gate
freeze (`d0912e0`) postdates the review, no registration against any
draft ever occurred, and SHW-4 binds the frozen document's SHA-256.

With SHW-1..3 implemented and reviewed, the preregistration frozen, and
all five owner decisions recorded, **SHW-4 is the next milestone**:
registration + first baseline + owner-approved operational release
advance + scheduler install, dedicated `data/shadow_overlay.db`.

## 7as. Owner decision batch: gates frozen, APQ-1 scheduled, Stage 2 closed (2026-08-19)

(Recorded on the gate-freeze branch while sections 7aq/7ar were being
written on the review branch; renumbered 7as at merge. Decisions 2-5
chronologically preceded 7ar's counter-review, which already cites
the freeze commit `d0912e0`.)

Four owner decisions recorded on
`user/claude/dc-gate-freeze-20260819` (docs-only round):

1. **SHW-3 review**: already running (owner-initiated); this round does
   not touch the SHW-3 branch.
2. **Defensive-carry gates FROZEN as proposed** ("yes accept as is"):
   `docs/research/DEFENSIVE_CARRY_2026-08-18_PREREGISTRATION.md` now
   carries zero draft placeholders — composite gate 15% relative maxDD
   reduction / 10% relative ES improvement / 80% upside-capture floor;
   ≥8 calendar-year folds (fewer refuses the study as underpowered);
   retrospective gate 2/3-fold consistency AND block-bootstrap p<0.05
   on the ES delta; 24 required prospective months
   (`required_observation_count=24` at SHW-4 registration). The freeze
   commit precedes every confirmation computation, registration, and
   statistic; changes now require a new named preregistration. SHW-4
   binds this document's SHA-256 as of this commit.
3. **APQ-1 SCHEDULED** — APQ-0 complete; the allocation-policy LEAN
   algorithm + local tests begin serially after the SHW-3 review
   settles (one milestone per branch, review between).
4. **Stage 2 PEAD CLOSED** without implementation (inside the A-002
   closure; QC point-in-time consensus data almost certainly
   unavailable; poor prior). Action-plan row records the reasons and
   the reopening bar.

5. **Host DECIDED 2026-08-19 ("i'll follow your recommendation"):**
   a DEDICATED shadow database file (`--database
   data/shadow_overlay.db`) — the frozen paper-epoch-005 operator DB is
   never opened by a newer tree (the standing overlay-table CREATE
   caution stays satisfied) — with the scheduled task running from the
   OPERATIONAL CLONE once its release advances to a commit containing
   SHW-1..3. The release advance is itself an owner-approved deploy
   step at SHW-4 time. Until then the stream does not run on a
   schedule; a manual first registration/baseline from a reviewed
   commit remains possible if the owner wants the clock started before
   the release advance.

## 7at. SHW-4 sub-step 1 EXECUTED: the defensive-carry stream is LIVE (2026-08-19)

Owner go ("go SHW-4"). On branch
`user/claude/shw4-stream-start-20260819`:

- **Committed stream config**
  (`docs/operations/overlay_shadow_defensive_carry_config.json`,
  commit `3c9105d`): generated programmatically from `config.UNIVERSE`
  (104 members, verified no overlap with the carry basket and no
  duplicates) + TLT/IEF/SHY/GLD, carry weight 0.20, band 0.25,
  `required_observation_count=24` — all per the FROZEN preregistration.
- **Registered** `defensive-carry/overlay-epoch-001` into the canonical
  shadow database `C:/git/trading_agent_operational/data/shadow_overlay.db`
  (dedicated file beside the operational backups; the operator DB was
  never opened): preregistration sha256 `5479d6b6459a…`, code commit
  `3c9105d`, registration hash `39fca6264e29…`.
- **First baseline observation recorded, AVAILABLE, at 2026-07-31**
  (levels 100.0 for universe/carry/combined; carry weight 0.20) — all
  108 members priced on July's final session; the SHW2-001 completeness
  gate passed on real market data. Observation hash
  `56bfcd3cf351b02d…`. **The 24-month prospective clock is running.**
- First sufficiency report: NOT_MET, 0/24 matured months (correct — a
  matured month needs the next adjacent month's observation; August
  matures at the first September session's observe).

**Canonical shadow DB path decision (records the host decision's
mechanics):** one physical file,
`C:/git/trading_agent_operational/data/shadow_overlay.db`, regardless
of which checkout invokes the runner — the dev checkout can run manual
cycles against it now, and the operational scheduler points at the same
file after the release advance. This avoids the two-checkouts /
two-databases split.

**Remaining SHW-4 sub-steps, paused for the owner — and the pinning
check is DONE with a material finding:**
`scripts/install_windows_operational_tasks.ps1` runs every paper task
with `WorkingDirectory` = the clone and NO commit pin — the checkout IS
the pin. **Advancing the operational clone therefore changes the code
the paper-epoch-005 cadence executes: a lineage change that closes the
epoch.** Owner options for sub-step 2:

- **(a) RECOMMENDED — defer the advance**: run the shadow cycle
  manually each month from the dev checkout against the same canonical
  DB (one command after the month's first sessions; next due after
  2026-08-31 settles). Zero risk to epoch-005; install the scheduler at
  the next NATURAL release advance / epoch roll.
- **(b) Advance now with a planned epoch roll** to paper-epoch-006,
  following the established roll process (close the epoch BEFORE
  deploying — the epoch-003 lesson). Epoch-005 is only ~6 days old, so
  the lost accumulation is small; this buys full automation
  immediately.
- **(c) A third, shadow-only pinned checkout** for the scheduler —
  no paper-epoch interaction, at the cost of another checkout to
  manage; would amend decision 5's mechanics.

**Owner chose (b) 2026-08-19.** Execution order per
`docs/EPOCH_005_ROLL_PLAN.md`'s preconditions and the runbook:

1. THIS branch completes with the scheduler installer
   (`scripts/install_windows_overlay_shadow_task.ps1`, ML-installer
   pattern: elevation + store-alias preconditions, WhatIf preview,
   exact-name verification; daily weekday triggers at 17:45/17:55/18:05
   ET — after the paper 16:30 window and the ML shadow chain — with the
   monthly cadence enforced by the runner's idempotency; it never
   touches the Paper-* or ML-Shadow-* tasks).
2. **Round review, then owner merge** — the roll plan's precondition 4
   requires a REVIEWED mainline deploy target.
3. Execute the roll (owner present, not near the 16:30 local
   observation window): disable the four Paper tasks → close
   paper-epoch-005 on the still-current commit → deploy the reviewed
   main tip into the operational clone → `ledger-reconcile` matched →
   `readiness` → start paper-epoch-006 on the exact deployed commit →
   all five drills → re-enable tasks → verify the first SCHEDULED
   paper observation binds the new lineage.
4. Install the overlay shadow tasks (elevated) pointing at the
   canonical shadow DB and the committed config; verify the first
   scheduled no-op run.

The stream itself is already live and unaffected by the roll timing —
manual cycles cover any gap.

Epoch-005 cost note for the record: closing it discards its accrued
paper evidence (epoch started 2026-08-13; the roll plan's rule — the
cost only grows — argues for executing promptly after review).

## 7au. Independent review of SHW-4 stream start: ACCEPTED AFTER CORRECTION (2026-08-19)

Cursor Grok 4.6 reviewed `a384be7..a6a690c` (12 commits; the request
said 11) at exact head `a6a690c29b5eefef7d227d8fde5b4990cad6da19` from
isolated worktree `trading_agent-review-shw4`. Report:
`docs/Review/REVIEW_2026-08-19_SHW4_STREAM_START.md`.

**Accepted after correction.** SHW3-001 independently mutation-verified
(strict gate restored in `command_sufficiency` → closed-epoch
sufficiency test red; restored green). Stream config matches
`sorted(config.UNIVERSE)` (104) + sorted carry basket, no overlap,
0.20/0.25/24. Freeze has zero `[TO FREEZE]` and precedes registration.
Shadow DB read-only: registration hash `39fca6264e29…`, prereg
working-tree SHA `5479d6b6459a…`, baseline `2026-07-31` available,
observation hash `56bfcd3cf351b02d…`. Installer `-WhatIf` only; Store
alias rejected; no Overlay-Shadow task created. Paper installer
WorkingDirectory pinning claim confirmed.

**P2 SHW4-001 closed here:** merge `039e5cf` dropped action-plan row
`STAGE2-PEAD-CLOSED-20260819`; restored. **P3 SHW4-002 closed here:**
ALLOCATION-POLICY row still said UNSCHEDULED; aligned with APQ-1
SCHEDULED. Open P3: SHW4-003 (prereg SHA is CRLF checkout bytes, not
the git blob) and SHW4-004 (`-TaskPrefix` unconstrained).

`origin/main` already contains PR #267 at `f63ba89` (tree identical to
`a6a690c`). This review is the independent disposition of that tree. It
does **not** run the epoch roll or install the overlay tasks.

## 7au. SHW-4 review counter-reviewed; all findings closed (2026-08-19)

Cursor/Grok reviewed `a384be7..a6a690c` (12 commits — correcting my
11-count) and accepted after correction
(`docs/Review/REVIEW_2026-08-19_SHW4_STREAM_START.md`): its P2 was a
real defect in MY conflict resolution — merge `039e5cf` silently
dropped the owner's STAGE2-PEAD-CLOSED action-plan row while the
handoff narrative kept it; the reviewer restored it (SHW4-001) and
aligned the contradictory ALLOCATION-POLICY row (SHW4-002). The
counter-review (`…_SHW4_COUNTERREVIEW.md`) verified both fixes,
reproduced the SHW4-003 hash split by independent recomputation
(checkout CRLF `5479d6…` = the live binding vs git blob LF `96fc51…`)
and closed it as documented at the hash site, and closed SHW4-004 with
ENFORCEMENT: the installer now refuses any TaskPrefix colliding with
`TradingAgent-Paper*` / `TradingAgent-ML-Shadow*` (throw verified by
execution; default preview unaffected). Lesson recorded: verifying a
conflict resolution means grepping for every row of BOTH parents.

**The roll plan's reviewed-mainline precondition is met.** Remaining:
the owner-present epoch roll (close 005 → deploy → start 006 → drills)
and the elevated overlay task install, then this round closes.

## 7av. Epoch-006 roll EXECUTED; overlay scheduler installed; SHW-4 complete (2026-08-19)

Owner-present, runbook order, all verifications green — the full record
lives in `docs/operations/OPERATIONAL_FACTS.md` (the epoch-006 section;
this handoff intentionally does not restate host facts). Summary:
preconditions cleared (6 overnight connectivity alerts verified
recovered and acknowledged, books matched, clean trees, reviewed target
`c9d0740`), `paper-epoch-005` closed 19:47:49Z with its 3 observations,
`c9d0740` deployed, reconcile matched on the new runtime (overlay
migration applied at the sanctioned moment), readiness green,
**`paper-epoch-006` active 19:48:54Z** bound to `c9d0740`, 5/5 drills,
tasks re-enabled and proven (manual start → result 0, healthy
heartbeat), and the three `TradingAgent-Overlay-Shadow-*` tasks
installed against the dedicated shadow DB.

**SHW-4 is COMPLETE**: stream live (baseline 2026-07-31), scheduler
installed, roll executed, round reviewed and counter-reviewed. The
defensive-carry 24-month prospective clock runs unattended from here.

Deferred same-day verifications: (1) the first scheduled
`paper-observation` under epoch-006 (16:30 local today) must bind the
deployed lineage before epoch evidence is called accumulating; (2) the
overlay tasks' first firing (14:45 local) should print `up to date` —
that no-op is the scheduled-execution proof. One flag for the next
thorough review: epoch-006's `policy_fingerprint` differs from 005's
while every other identifier is unchanged (see the facts entry).

**Codex returns tonight for a thorough audit of the last two days.**
Suggested range: everything since `de1beac` (2026-08-18's Stage 0
acceptance) through current main — the Stage 0 closure, Stage 1
campaign, post-closure pivot, SHW-1..4, the allocation-policy docs, the
gate freeze, and this roll. All review records live in `docs/Review/`;
the per-round handoff sections 7z–7av are the narrative index.

## 7aw. APQ-1 implemented: the allocation-policy LEAN algorithm (2026-08-19)

Owner go ("start APQ"). Branch
`user/claude/apq1-allocation-policy-20260819`:
`research/lean/allocation_policy.py` implements the FROZEN
preregistration exactly — four policies (P0 100 SPY; P1 40/60 SPY/BIL;
P2 40/20/20/20 SPY/BIL/XLP/XLV; P3 35/55/10 SPY/BIL/XLE) on fixed
instruments with no universe screen and deliberately NO ACTIVE_UNIVERSE
assignment (pinned by regex test so the Stage 0 retargeter has nothing
to rewrite); monthly month-end cadence with target-weight returns from
adjusted closes (BIL never modeled as Lean cash); bind-time drift
turnover per the reviewed `_drift_turnover` definition (true 0.5 entry
cost on the first measured month; DECLARED-unavailable empty field
after any gap); UNION-wide ALIGNED refusal — one unpriceable ticker
drops the boundary for all four policies, keeping the series on one
date set; INCOMPLETE with zero rows below the frozen 24-month floor.
Emits `POLICIES|` / `DATES|` / six-field `PROW` rows. NOT added to the
launch driver (APQ-3).

Two real defects caught by the tests during implementation: closes were
ingested before the boundary settled (every boundary looked unpriced),
and turnover was initially charged with the row's own month's outcomes
instead of the prior month's drift (the bind-time convention). Six
tests with hand-computed month math; THREE reverse mutations red then
restored (refusal skipped, completeness floor removed, wrong-month
turnover). `compileall` clean.

Next: APQ-2 (the analyser + tests, still no QC) after this round's
review — the reporting decision (optional excess-mean test family in or
out of the JSON schema) is fixed at that review per the plan's
counter-review note.

## 7ax. Independent review of APQ-1: ACCEPTED AFTER CORRECTION (2026-08-19)

Cursor Grok 4.6 reviewed `01508b1..e2c4a2b` (both commits on
`origin/user/claude/apq1-allocation-policy-20260819`) from isolated
worktree `trading_agent-review-apq1`. Report:
`docs/Review/REVIEW_2026-08-19_APQ1_ALLOCATION_POLICY.md`. No QC.

**Accepted after APQ1-001.** Weights, window, union refusal, bind-time
turnover, 24-month floor, and no `ACTIVE_UNIVERSE` match the frozen
preregistration. `FAMILIES` was not extended (APQ-3). Submitted tree:
6 tests passed. Inf closes emitted `PROW` `inf` rows; NaN TypeError'd —
prereg §3 requires non-finite refusal. Fix: `_usable_close` uses
`math.isfinite`; new test red without the guard, green with it (7
passed). Open P3: stale §8 at `e2c4a2b` (this section replaces it);
`priced`/`targeted` log the policy size, not the five-name union.

`origin/main` already contains PR #270 at `46feb1e`. This review does
not start APQ-2.

## 7ax. APQ-1 review counter-reviewed; all findings closed (2026-08-19)

Cursor/Grok accepted APQ-1 after correction
(`docs/Review/REVIEW_2026-08-19_APQ1_ALLOCATION_POLICY.md`): its P2 was
real and mine — the positivity check accepted `inf` into emitted
returns and let `NaN` crash, where the frozen preregistration requires
non-finite closes to refuse the date. The reviewer fixed it
(`_usable_close` with `math.isfinite` + regression test); the
counter-review (`…_APQ1_COUNTERREVIEW.md`) re-ran their mutation (red,
restored green, 7 passed) and closed the two P3s: the stale handoff §8
(reviewer-fixed) and the `priced`/`targeted` semantics, now documented
in the plan's APQ-2 section so the analyser cannot misread them.
Humbling pattern recorded: the same non-finite class I hardened the
PARSERS against (SHR/S0R-003) got written into a new EMITTER days
later — finiteness guards belong at every boundary, both directions.

**APQ-2 is unblocked** (analyser + tests, no QC; the excess-mean
reporting decision is fixed at its review).

## 7ay. APQ-2 implemented: the allocation-policy analyser (2026-08-19)

Owner go ("start APQ-2"). Branch `user/claude/apq2-analyser-20260819`:
`scripts/analyse_qc_allocation_policy.py` — a strict PROW parser that
refuses, typed: unknown policies, duplicate (date, policy) rows,
non-finite returns, PRESENT non-finite turnover tokens (empty stays the
declared-unavailability channel, charged fillna(1.0)),
`priced != targeted` as corruption (the APQ1-003 semantics), truncated
DATES, policy date sets differing from P0's, and anything under the
frozen 24-month floor. Reports per-policy gross/net at 0/5/10/25 bps
(reviewed `performance()` + `time_under_water`), mean/unavailable
turnover, and the descriptive `versus_p0` block.

**Reporting decision, proposed for ratification at this round's
review (the pre-run deadline the plan set):** the optional excess-mean
test family IS reported — three cells, two-sided stationary bootstrap
20,000 draws, its own frozen 0.05/3 gate, carrying BOTH required
labels (family identity; explicit this-family-only scope, NOT added to
the closed alpha program's floor). Rationale: a descriptive table
alone invites eyeballing differences with no calibration; the test is
the guard against over-reading it, and a fail is the expected outcome
that ends the family either way. The reviewer may strike the test
from the schema; that is exactly the decision this review fixes.

Gate reachability guarded (draws must resolve 0.05/3 — the ABR-001
class); script-mode bootstrap included (S1R-001); the alpha battery's
`analyse()` is not called (AST-pinned). Nine tests; THREE reverse
mutations red then restored (fillna unpinned, nan-turnover guard
dropped, alignment check dropped). Next: this round's review fixes the
reporting decision, then APQ-3 (the launch-driver hook).

## 7az. Independent review of APQ-2: ACCEPTED (2026-08-19)

Cursor Grok 4.6 reviewed `92a0077..5364ae6` (both commits on
`origin/user/claude/apq2-analyser-20260819`) from isolated worktree
`trading_agent-review-apq2`. Report:
`docs/Review/REVIEW_2026-08-19_APQ2_ANALYSER.md`. No QC.

**Accepted.** Nine tests passed. `fillna(1.0)→0.0` mutation red on the
S0R-008 magnitude pin, restored green. Parser refusals and APQ1-003
count semantics hold. **Reporting decision RATIFIED:** the optional
excess-mean family stays in the schema (3 cells, 20,000-draw two-sided
stationary bootstrap, 0.05/3, both labels). Striking it now would be a
new schema. Open P3 APQ2-001: `mean_turnover` skipna omits months that
net returns charge at 1.0.

This review does not start APQ-3 or authorize a cloud run.

## 7az. APQ-2 review counter-reviewed; schema ratified (2026-08-19)

Cursor/Grok accepted APQ-2
(`docs/Review/REVIEW_2026-08-19_APQ2_ANALYSER.md`) and — the round's
real event — **ratified the reporting decision before any run exists**:
the excess-mean family is IN the schema (3 cells, 0.05/3, both labels);
striking it later would be a new schema, never a post-result choice.
Counter-review (`…_APQ2_COUNTERREVIEW.md`): the fillna mutation re-run
red/green; **APQ2-001 reproduced** (skipna `mean_turnover` reports 0.0
where the net blocks charge a 0.25 mean) and closed as documented at
the plan's APQ-5 section per the reviewer's guidance; APQ2-002 (stale
§8, third occurrence — note to self recorded: touch §8 in the same
commit as any new 7-series section) reviewer-fixed and verified.

**APQ-3 (launch-driver hook) is next**; APQ-4's single cloud run stays
owner-gated behind the APQ-1..3 review chain.

## 7ba. APQ-3 implemented: the launch-driver allocation hook (2026-08-19)

Owner merged the APQ-2 review (PR #272) and said "proceed to APQ3".
Branch `user/claude/apq3-driver-hook-20260819` off `95a7210`. No QC.

Changes to `scripts/run_qc_stage0.py` per the plan's APQ-3 section:

- `FAMILIES["allocation"] = ("ALLOCATION_POLICY", LEAN /
  "allocation_policy.py")` and `UNIVERSE_FREE_FAMILIES =
  frozenset({"allocation"})`.
- New `_resolve_universe(family, universe)`: a universe-free family
  REFUSES a supplied `--universe` (a silently ignored flag would
  misdescribe the run); every other family refuses a missing one.
  `--universe` is now optional at argparse level; enforcement moved to
  this validator.
- `launch()` uploads a universe-free family's reviewed bytes UNCHANGED
  (still sha256-hashed, still `require_clean=True`), guarded by an
  anchored `^ACTIVE_UNIVERSE\b` refusal in case the file is ever
  misclassified; screened families retarget exactly as before.
- `_project_name` drops the universe segment when universe is None:
  `{n}. ALLOCATION_POLICY - {YYYYMMDD}`.

Tests (`tests/test_qc_stage0_runner.py`, 18 passed): the
every-family retarget test now skips `UNIVERSE_FREE_FAMILIES`; new
tests pin the allocation mapping + no-ACTIVE_UNIVERSE-declaration (the
frozen file's docstring MENTIONS the constant, so the pin uses the same
anchored regex as the launch guard, not a substring), retargeter
refusal on the real file, both `_resolve_universe` refusal directions,
and the universe-free project name. Both plan-required reverse
mutations run separately, red, restored green: (A) removing
`allocation` from `UNIVERSE_FREE_FAMILIES` → 3 failures including the
launch-precondition retarget test; (B) dropping `require_clean=True` →
the QCS0CR-002 pin fails.

APQ-3 does NOT authorize a run: APQ-4's single cloud launch remains
owner-gated behind independent review of APQ-1..3.

## 7bb. Overlay tasks never fired: S4U logon dead on the host (2026-08-19)

Same-day check of the overlay tasks' first scheduled firing found the
14:45/14:55 occurrences silently skipped (no run attempt, no error,
NextRun rolled to tomorrow). Root cause: the overlay installer
registered with **LogonType=S4U**, which Credential Guard blocks on
this domain-joined host — the exact known failure mode in
`tests/test_setup_operational_host.py` that already forced every
working paper task to Interactive. Installer default fixed to
Interactive this round; the live repair needs ONE elevated owner
command (recorded in `docs/operations/OPERATIONAL_FACTS.md`). Science
impact none: the runner is idempotent and monthly-cadence, and today's
firings would have been `up to date` no-ops.

## 7bc. Independent review of APQ-3: ACCEPTED AFTER CORRECTION (2026-08-19)

Cursor Grok 4.6 reviewed `95a7210..1a63c8c` (both commits) from
isolated worktree `trading_agent-review-apq3`. Report:
`docs/Review/REVIEW_2026-08-19_APQ3_DRIVER_HOOK.md`. No QC.

**Accepted after APQ3-001.** Driver tests 18 passed. Plan mutations
reproduced: empty `UNIVERSE_FREE_FAMILIES` reds 3 tests; dropping
`require_clean=True` reds QCS0CR-002. Allocation bytes stay unretargeted
and hashed. Overlay installer default Interactive is correct for this
host. **P2 closed here:** the facts repair one-liner omitted mandatory
`-PythonPath`/`-DatabasePath`/`-ConfigPath` and would not re-register.
Open P3: paper installer source still defaults S4U; APQ-3 and the
overlay ops record share one branch.

This review does not execute APQ-4 or the elevated overlay reinstall.

## 7bd. APQ-3 review counter-reviewed; S4U class closed repo-wide (2026-08-19)

Counter-review (`docs/Review/REVIEW_2026-08-19_APQ3_COUNTERREVIEW.md`)
VERIFIED the review. APQ3-001's closure was confirmed live twice over:
the owner hit the missing-parameter prompts in real time, and the
completed command re-registered all three overlay tasks — which now
show `LogonType=Interactive` and, decisively, **actually ran (exit 0)
on manual start**, as the expected no-ops (`shadow_overlay.db`
unchanged at 1 registration / 1 baseline observation / 0 outcomes;
sufficiency artifact rewritten 15:45 local). The first AUTOMATIC
firing (2026-08-20 14:45 local) is the remaining trigger proof.

APQ3-002 was confirmed and GENERALIZED: the sibling sweep found THREE
S4U defaults (paper installer, ML-shadow installer, and the verifier's
`ExpectedTaskLogonType` — the last would fail correct tasks and pass
misregistrations). All three now default Interactive; the dependent
mock updated; a mutation-verified scan test
(`test_every_task_logon_type_default_is_interactive`) keeps the class
closed. APQ3-003 acknowledged, no split of pushed history.

## 7be. APQ-4 EXECUTED: the single allocation-policy cloud run (2026-08-19)

Owner merged the APQ-3 counter-review (PR #273, main `5694975`) and
gave the GO ("go APQ-4"). Branch
`user/claude/apq4-cloud-run-20260819` off that merge. The one
authorized backtest ran: project `35377356`
(`25. ALLOCATION_POLICY - 20260819`), compile
`929dd05d…`, backtest `b9696f67…`, source uploaded UNCHANGED at
`5694975` (sha `86fb7a3f…`), launched 22:59:13Z, completed 22:59:27Z.

Frozen-parser round-trip: **STRUCTURALLY COMPLETE, first attempt** —
54 months (202202..202607, the full expected window), all four
policies on one shared date set, 216 rows, 0 declared-unavailable
turnovers, 0 refusals; 54 ≥ the 24-month floor. **No statistic
observed** (`parse_log` only; the algorithm holds no QC positions, so
QC's runtime stats are untouched-account boilerplate). Ledgered as
**R-029 UNANALYSED** in `docs/alpha-result.md`; run-level look
29 → 30. Raw log stays machine-local under `artifacts/` (hash in the
ledger); QC market data is never committed.

Owner is separately having Cursor draft two new plan proposals ("max
profits", "hedging") — they will need frozen preregistrations and
family scoping at counter-review; the A-002 closure is not reopenable
through them.

## 7bf. APQ-5 OBSERVED: NULL on the gate; the family is CLOSED (2026-08-19)

Owner merged APQ-4 (PR #274, main `c4fd16d`) and gave the GO ("go APQ5
now"). Branch `user/claude/apq5-analyser-pass-20260819`. The log hash
was re-verified against the ledger, then the frozen analyser ran ONCE
with full run identity — the family's only statistic observation.

**Result: 0 of 3 cells pass the 0.05/3 gate** (P1 p=0.080, P2 p=0.121,
P3 p=0.214); every candidate's monthly excess vs P0 is NEGATIVE.
Descriptively P1/P3 bought much smaller drawdowns (−7% to −8% vs P0's
−20%) at ~40% of the return — a risk-preference trade, not an edge;
Sharpe/drawdown differences are descriptive fields with no frozen
test, and none is claimed. Ledgered as **A-003**; **R-029 upgraded
UNANALYSED → VALID in the same commit** per the plan's rung. The
allocation-policy QC family is **CLOSED**: one cloud run and one
analyser pass, both spent; no reruns or tweaks. Paper/live use of any
weights is a separate owner decision on the Alpaca/REBAL stack.

## 7bg. Owner strategy → LEV + SBR preregistration drafts (2026-08-19)

The owner described a three-step strategy (Strong-Buy universe with
inverse-volatility weights → leveraged ETF of the holding-heaviest
funds → threshold take-profit) with the goal "beat NASDAQ and SPY".
Feasibility probe first: **QuantConnect has no point-in-time
analyst-ratings dataset** (Morningstar = fundamentals only; Benzinga
on QC = news; the only recommendations set tracks CNBC personalities),
and today's consensus against old prices is look-ahead — the same wall
that closed Stage 2 PEAD. The owner adopted the two honest paths
("I think both B and C are worth testing"):

- **LEV family (Path B)** — the leveraged-ETF engine, testable now:
  TQQQ take-profit/re-entry state machine (L1..L4: +20%/+40% × next
  month-end / −10% pullback re-entry), window 2011→run date including
  the 2022 −80% drawdown, 8 cells at 0.05/8 (vs TQQQ buy-and-hold =
  the edge test; vs QQQ = the stated goal, with the frozen label that
  a QQQ-pass without an L0-pass is LEVERAGE, not skill), after-tax
  37%/20% descriptive column per the SOXL lesson, one run + one pass.
- **SBR capture stream (Path C)** — monthly snapshots of NASDAQ-100
  analyst consensus, point-in-time BY CONSTRUCTION (capture time =
  knowledge time), task-specific runtime per ML-LR-6, Interactive
  logon + first-firing verification per the S4U incident, and a hard
  look rule: joining snapshots to subsequent prices is FORBIDDEN until
  a separate SBR-2 evaluation preregistration freezes after ≥12
  snapshots.

Both preregistrations were **FROZEN by owner adoption the same day
("as-is")**, recorded in each document's section 7. Explicitly outside the A-002 closure (fixed
instruments / new data source + fresh preregistration + owner
decision). Milestones after adoption: LEV-1 (LEAN algo), LEV-2
(analyser + driver hook), LEV-3 (one run), LEV-4 (one pass); SBR-1
(capture script + task). One branch + independent review each.

## 7bi. Max-profit and hedge QC plans proposed (2026-08-19)

Cursor Grok 4.6 wrote **docs-only** proposals on
`user/cursor/max-profit-hedge-plans-20260819` (branched from `5694975`,
so its records predate APQ-4/5 and LEV; this merge reconciles them —
the section was renumbered from its original 7be, which collided with
main's). No LEAN, no driver change, no QC from that lane.

- **MPQ (levered growth; owner revised to 3x before any run):** G0
  100% SPY; G1 100% TQQQ; G2 70/30 TQQQ/SPY; G3 50/30/20
  TQQQ/SPY/SOXL (cap). Daily-reset decay disclosed. Composite gate:
  higher net-10bps CAGR vs G0; worse maxDD/Sharpe disclosed, not
  auto-fails. Optional excess-mean bootstrap (0.05/3) report-vs-omit
  frozen at MPQ-2 review.
- **HPQ (static overlay, NOT the HEDGE-1 UI):** H0 100% SPY; H1 90/10
  SPY/SH; H2 80/20 (SH cap); H3 90/10 SPY/BTAL. Composite gate: ≥10%
  relative maxDD improvement, ≥75% upside capture when H0 CAGR is
  positive, ≤4pp CAGR sacrifice.

Both use APQ's 2022+ window and one-run-one-pass shape. Both families
were subsequently placed **ON HOLD by owner decision 2026-08-19**.

## 7bj. Counter-review of the MPQ/HPQ plans (2026-08-19)

Counter-review record:
`docs/Review/REVIEW_2026-08-19_MPQ_HPQ_PLANS_COUNTERREVIEW.md`. Both
plans ACCEPTED as proposals with pre-freeze corrections applied in
this round (they are drafts — editing before the owner freeze is the
right time): the stale "while APQ-4 is in flight" sequencing replaced
(APQ closed as A-003 the same day), the MPQ-3 driver-family reference
corrected (`allocation` is the existing universe-free family, not
`defensive_carry`), an explicit descriptive-classification label added
to both composite gates (they carry no p-values; only the optional
bootstrap families do), the MPQ↔LEV overlap disclosed in both
directions (LEV's L0-vs-SREF already contains MPQ's G1-vs-G0 question
descriptively on a longer window), and a BTAL liquidity note added.
The handoff/action-plan merge collisions from the stale branch base
were resolved with every row verified present (SHW4-001 lesson).

## 7bk. SBR-1 implemented: the Strong-Buy capture runtime (2026-08-19)

(Numbered 7bk at authoring time because the then-unmerged MPQ/HPQ
plans branch already claimed 7bi/7bj — the MHP-001 collision class,
avoided; this merge interleaves all three cleanly.)
Owner priority ("implement the strong buy plans"). Branch
`user/claude/sbr1-ratings-capture-20260819` off `aa87bf1`. Per the
frozen capture preregistration:

- `scripts/capture_analyst_ratings.py`: task-specific runtime (ML-LR-6
  precedent, deliberately not the overlay framework). Monthly snapshot
  of analyst recommendation counts for the frozen universe; per-ticker
  failures recorded `available=false` with the error class, never
  dropped; months labeled in MARKET time (a 00:30Z capture is the
  previous ET month); canonical JSON lines with pinned LF bytes (a real
  Windows `\r\n` translation defect was caught by the hash test and
  fixed); append-only snapshots + sha256 manifest; refusals for orphan
  snapshots, manifest/file hash mismatch, missing files, naive
  timestamps, malformed configs. No evaluation imports (AST-pinned):
  joining snapshots to prices stays forbidden until SBR-2.
- `docs/operations/strongbuy_ratings_config.json`: frozen 102-ticker
  NASDAQ-100 universe, deterministically extracted from the Wikipedia
  constituents wikitext (provenance + retrieval time recorded; a lossy
  model-extraction first attempt was REJECTED for hallucinated
  tickers).
- `scripts/install_windows_strongbuy_capture_task.ps1`: ONE
  daily-weekday task at 17:15 ET, Interactive logon (covered by the
  repo-wide S4U scan test automatically), protected-prefix denylist
  now including the overlay family, Store-alias interpreter guard.

15 tests; 3 reverse mutations red then restored (UTC month labeling,
orphan-refusal removal — whose first regex attempt was a silent no-op,
caught and re-run as a real mutation — and bool-count acceptance).
Remaining for SBR-1 completion: independent review, then the
owner-present elevated install and a first-firing verification.

## 7bl. Counter-review of the Codex audit: VERIFIED (2026-08-19)

Counter-review record:
`docs/Review/REVIEW_2026-08-19_POST_STAGE0_COUNTERREVIEW.md`. All six
behavioral corrections were independently re-verified red on the
pre-correction files and green after (including the APQ month-label
DID-NOT-RAISE); no test was deleted or weakened (SBR fixtures upgraded
to the stricter frozen shape). Substantive judgments: PTSR-001 is a
real frozen-spec violation my LEV-1 mutations missed (a composition
blind spot — sale filling exactly on a month-end vs the boundary
callback); PTSR-002 is WORSE than stated — the original `isinstance
(value, int)` would also have rejected the real provider's numpy
integers, so production's success path was fixture-blind; PTSR-003's
dirty-tree capture block is the correct fail-closed direction. Doc
rewrites checked accurate against the ledgers. One gap closed
(PSCR-001, P3): the dropped app-restart-after-deploy lesson moved to
its durable home in OPERATIONAL_FACTS. The epoch-006
`policy_fingerprint` change (4a942cbc… → 4086365c…) is NOT explained
by this audit and stays flagged.

## 7bm. Complete Strong-Buy portfolio plan revised (2026-08-19)

At the owner's request, Codex reviewed the proposed Strong-Buy direction and
drafted the missing complete portfolio contract at
`docs/reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md`. The draft preserves the
already frozen SBR-1 capture-only preregistration. It does not rewrite or
silently expand that authority.

The important correction is conceptual: the frozen LEV family is a generic
TQQQ take-profit/re-entry experiment. It never consumes analyst ratings,
builds the inverse-volatility stock basket, reads point-in-time ETF holdings,
or measures the combined portfolio's look-through concentration. It therefore
cannot validate the owner's complete strategy. The successor draft instead
defines P0–P4 so ratings selection, inverse-volatility sizing, ordinary ETF
overlap, and leverage are tested one at a time. It proposes including every
stock that passes fixed ratings thresholds, a 63-session inverse-volatility
window with a 10% direct-stock cap, a weight-based holdings-overlap score, a
5% leveraged sleeve, and a 15% look-through issuer cap.

The draft also closes the largest evidence risk in the earlier sequence:
freezing SBR-2 only after viewing twelve captured rating distributions could
turn those same months into calibration leakage. Under the successor, the full
rule must freeze before any admissible snapshot is joined to later prices;
anything captured before adoption is calibration-only and excluded from the
confirmatory outcomes. Official same-index ETF mappings and point-in-time
holdings capture are new required gates. Threshold exits remain a later,
separate hypothesis rather than being mixed into the base overlay test.

Status is **DRAFT — not adopted, not frozen, not scheduled**. No code, QC,
broker, scheduled-task, deployment, or operational-state change occurred.
The owner must decide the proposed thresholds, caps, cost assumptions,
candidate ETF pairs, and minimum evidence floor before SBP-0 can complete.

## 7bn. SBP plan amendments submitted (2026-08-19; corrected by 7bo)

This is the implementer's submitted account of the section 7bm draft review.
Its quantitative and authority claims are **superseded by the independent
review in section 7bo**. Submitted verdict: **it should become the
primary plan** — it writes the test my SBR preregistration deferred, and
its P0..P4 decomposition (one decision isolated at a time) is exactly the
structure that would have prevented Stage 0/1's beta-as-edge readings.
Five pre-adoption amendments are applied in its section 11 (SBPA-001..005),
made now precisely because no data exists yet:

- **SBPA-001, the load-bearing one:** the 50% minimum ETF overlap was
  UNREACHABLE, so P3/P4 would have refused every month while the study
  still read as complete. A **declared structural feasibility check**
  (basket weights built per sections 4–5 vs a cap-weight proxy for QQQ
  holdings; **no returns, no benchmark, no performance** — a structural
  quantity, not a price-linked look) measured overlap of **33.8%** holding
  every candidate and **7–18%** for realistic 20–30 name baskets:
  inverse-vol weighting and cap-weighted holdings are structurally
  opposed (the low-vol names that earn the biggest basket weights carry
  ~0.5% each in the fund; NVDA/AAPL/GOOGL/MSFT dominate the fund but are
  mid-to-high vol). Threshold set to **10%** as a degeneracy floor, with
  the relative "highest overlap wins" rule doing the selection work. The
  check also exposed a **recorded limitation**: with an NDX-only candidate
  universe, any broad Nasdaq fund covers 100% of any basket, so the
  ETF-selection step is partly degenerate and P3/P4 substantially measure
  "add 5% of a broad fund (or its 3x)". Making that step informative needs
  a broader candidate universe = a NEW preregistration, never a silent
  edit to the frozen SBR capture universe.
- **SBPA-002:** an unusable 63-session price window disqualifies THAT
  TICKER (matching the ratings-unavailable path) instead of refusing the
  whole month; the month refuses only below the 8-stock floor. The
  original rule was inconsistent and would burn irreplaceable months.
- **SBPA-003:** P4−P3 is DESCRIPTIVE ONLY — it is ≈10% incremental index
  beta, and clearing a family gate on 24 months would require the index
  near 35–40%/yr, i.e. measuring the market. Frozen family is **3 cells
  at 0.05/3**.
- **SBPA-004:** declared power, frozen in advance — 24 monthly
  observations detect only ≈**0.6%/month (7–8%/yr)**, so a null means "no
  edge large enough to see", not "no edge"; extending for power requires
  a new preregistration rather than bolting months onto a scored family.
- **SBPA-005:** SBP-0 supersedes the SBR-2 evaluation step (freeze before
  the first capture rather than after twelve), recorded reciprocally in
  the capture preregistration. Zero snapshots exist at adoption, so every
  future outcome is confirmatory.

**LEV becomes SECONDARY** (fast historical read on the leverage/timing
half; not evidence for this strategy). Honest headline recorded in the
plan's new section 10: this is a **two-year instrument** — first analysis
pass around **September 2028** — with no admissible historical shortcut.

## 7bo. Independent review of SBP amendments: ACCEPTED AFTER CORRECTION (2026-08-20)

Codex formally reviewed exact pushed branch
`origin/user/claude/sbp-plan-amendments-20260819`, base `5e3708e`, single
submitted commit `5c42bfd`, and exact head `5c42bfd`. The one commit is
**ACCEPTED AFTER CORRECTION**. Review report:
`docs/Review/REVIEW_2026-08-19_SBP_PLAN_AMENDMENTS.md`.

Correction `5c3bf45` closes five P2 and two P3 findings. The submitted 33.8%
value was one unpreserved all-candidate probe, not a hard ceiling over
renormalized selected subsets; no code, inputs, official holdings identity,
price window, or hashes made the table reproducible. Its values are rejected
as evidence. The proposed 10% overlap floor remains visible only as an owner
policy choice. Ticker-level price exclusion was also rejected because it
deletes a stock after the signal selects it and changes “every qualifying
ticker” into a data-availability-selected basket; whole-month refusal is
restored.

The review also corrected P3/P4 look-through exposure to use 95% of the direct
core plus the ordinary same-index ETF weights (scaled by stated leverage for
P4), because literal leveraged-fund holdings can be derivatives rather than
constituent exposure. Unsupported 35–40%-annual-return and 0.6%-monthly power
claims were withdrawn. The inferential family is three one-sided cells at
0.05/3 with a fixed three-month mean stationary-bootstrap block; P4−P3 remains
descriptive because its main difference is intentional beta. SBP-0 must add an
80%-power sensitivity table before adoption. Two inherited Codex-draft defects
were also closed: 8 names cannot sum to 100% under a 10% cap (minimum is now
10, with P1=P2 disclosed at exactly 10), and 63 returns require 64 consecutive
closes plus immutable price-input lineage.

The frozen SBR capture preregistration no longer declares itself superseded
before the owner acts. SBP may replace SBR-2 only upon explicit adoption and
after machine-local snapshot state is measured. No code, QC access, market
data, broker access, scheduler mutation, deployment, or operational-state
change occurred. No milestone entry was added because SBP remains a draft.

Validation on the corrected tree: active-document tests 31 passed; the first
full run crossed local midnight and produced one synthetic-UI date mismatch
(4,347 passed / 1 failed / 25 warnings), the exact test then passed alone, and
the unchanged same-date full rerun passed **4,348 / 0 failed / 25 warnings** in
665.15 seconds. Python 3.13.14; required compileall plus `research/` passed;
diff check passed. Review record/Action Plan commit `2a26353`. Branch
`codex/review-sbp-plan-amendments-20260819` and all Codex commits are
**local-only, not pushed or merged** at this handoff.

## 7bp. Counter-review of the SBP review submitted (2026-08-20; clarified by 7bq)

Record: `docs/Review/REVIEW_2026-08-19_SBP_PLAN_COUNTERREVIEW.md`. All three
rejections of my amendments are correct, and **SBPA-001 was refuted by
re-running my own probe**: baskets built from the highest index-weight
candidates renormalize to 51–68% overlap, so 33.8% was a property of the
particular baskets I tested, never a ceiling — "50% is unreachable" was
unsupported, and the missing artifact/hashes criticism is correct by this
repository's own standards. Those re-check numbers carry the same defect, so
they are used only to withdraw my claim, never to establish one; the 10%
floor stands purely as a disclosed owner policy proposal. SBPA-002 is
correctly rejected (deleting a signal-selected stock is the forbidden
silent-row-drop, and the missingness is plausibly outcome-correlated), as is
SBPA-004 (my 0.6%/month was a two-sided rejection boundary against an assumed
tracking error, not power, and the frozen test is one-sided). The review's
own catches are accepted and two are material: minimum basket 8 → **10** (a
10% cap cannot sum to 100% below ten names — my 8 was a guaranteed refusal
path) and the **leveraged look-through correction** (derivative-based funds
make literal holdings an invalid look-through).

**One new proposal, SBPA-006:** rejecting SBPA-002 leaves a permanent-stall
path — a candidate with fewer than 64 completed sessions can NEVER produce
the frozen window, so under whole-month refusal alone it refuses every month
until it seasons. Fix that respects the rejection entirely: make listing
history an **eligibility precondition** decided with the ratings rules before
any selection exists (nothing deleted post-selection; a broken window for an
eligible stock still refuses the month). The argument is arithmetic, not
empirical; an exploratory check did find two current candidates at 46 and 47
sessions, which SBP-0 must re-verify from the provenance-bound source.

## 7bq. Independent verification of SBP counter-review: ACCEPTED AFTER CORRECTION (2026-08-20)

Codex reviewed the one newly pushed commit on
`origin/codex/review-sbp-plan-amendments-20260819`: prior verified head/base
`9d02ee5`, submitted commit and exact remote head `f75e793`. Explicit
disposition: **ACCEPTED AFTER CORRECTION**. Record:
`docs/Review/REVIEW_2026-08-20_SBP_PLAN_COUNTERREVIEW_VERIFICATION.md`.

Claude's retractions are correct and its new SBPA-006 concept is useful: a
security too young to supply 64 completed closes may be excluded before
ratings selection rather than stalling every month until it seasons.
Correction `aadb238` closes one P2 and two P3 findings. The age gate must use
frozen official first-trading-date evidence plus the exchange calendar—not
provider row count. Otherwise missing market data for an old security could
make it look young and silently exclude it, recreating SBPA-002. Once a
security passes the age gate and ratings select it, every close in the exact
64-close window remains mandatory; a missing/invalid close refuses the whole
month.

The correction removes unproven 46/47-session counts from the operative plan,
records that machine-local snapshot state was not measured, changes the
“permanent stall” description to temporary-until-seasoned, fixes the
counter-review date to 2026-08-20, and moves detailed review narrative out of
the active contract. Action Plan/review-record commit `ae07450`. Validation:
31 focused active-document tests passed; full suite **4,348 passed / 0 failed /
25 warnings** in 879.47 seconds; Python 3.13.14; required compileall plus
`research/` and diff check passed. No code, QC, broker, market-data, scheduler,
deployment, or operational-state action occurred. SBP remains a draft and no
milestone record was added.

Remote topology at this handoff: Claude's submitted counter-review is pushed
at `origin/codex/review-sbp-plan-amendments-20260819` head `f75e793`. The new
review branch `codex/review-sbp-counterreview-20260820`, correction `aadb238`,
record `ae07450`, and this handoff are **local-only until the owner authorizes
a push**.

## 8. What is next

**Current (2026-08-20): the SBP amendment round is independently ACCEPTED
AFTER CORRECTION (7bo); Claude's counter-review and proposed SBPA-006 are also
independently ACCEPTED AFTER CORRECTION (7bq). The complete successor remains a
DRAFT — not adopted, frozen, scheduled, or implemented. No SBP code before an
owner-approved SBP-0 freeze. LEV remains separate and cannot validate SBP.**
Codex reviewed exact pushed range
`81db126340818fe2c2c9efa16c77af8f1d37568f..3055fecd1caf490c852a446c03da760d2878af5a`
(143 commits) on
`codex/review-post-stage0-through-sbr1-20260819`. The audit found and
corrected six behavioral/evidence defects: LEV month-end sales could
re-enter at the same close instead of the following month-end; SBR
silently truncated fractional provider counts and did not bind its
frozen stream/config/preregistration or per-snapshot code commit;
overlay observation crashed on non-finite provider closes instead of
recording a named refusal; overlay sufficiency counted unavailable
outcomes; and the APQ parser accepted impossible month labels. The
canonical documentation status/path contradictions were also corrected.
No QuantConnect access, broker access, deployment, scheduled-task
mutation, or operational database mutation occurred.
Product/test corrections are committed separately at `d943339`; the
review report dispositions all 143 submitted commits.

**Sequencing:** Stage 0 and Stage 1 are closed null (A-001/A-002).
APQ is closed null (R-029/A-003). SHW-4 is live and collecting its
prospective 24-month stream. The current SBP counter-review verification branch
is local-only. The owner
should first review the corrected proposed values in
`docs/reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md`. If accepted, SBP-0 must
verify official ETF pairs, machine-local snapshot count, the optional
structural artifact, and power sensitivity before freezing. Until adoption,
the frozen SBR-2-after-12-captures rule remains the authority; no snapshot may
be joined to subsequent prices. The SBR Interactive scheduled-task install is
owner-present and remains unperformed. LEV-2 may proceed only as the separate
TQQQ timing study, not as SBP evidence. MPQ/HPQ remain on hold. Active paper
evidence is `paper-epoch-006`;
the next operational observation is governed by
`docs/operations/OPERATIONAL_FACTS.md`.
1. ~~The Stage 0 review happened (section 7y) — owner acceptance is the
   remaining gate.~~ DONE: the owner accepted the review pair 2026-08-18
   and the single frozen-analyser pass has run (section 7z, ledger entry
   A-001). Stage 0 is CLOSED as evidence-complete: no IC or long-short
   cell cleared the gate; six long-only cells cleared a beta-carrying
   gross-vs-zero test that the benchmark itself would clear. Next
   milestone: the S0R hardening round (S0R-001/002/003/004/005/008) so
   Stage 1 — which adds the cadence-matched benchmark-same-dates
   comparison those six cells need — can launch on reviewed code.
   UPDATE: the hardening round is IMPLEMENTED, validated (section 7aa),
   and INDEPENDENTLY REVIEWED AND ACCEPTED (section 7ab).
   FINAL UPDATE (closes review finding S1R-002): the owner gave the GO,
   Stage 1 RAN AND CLOSED NULL the same day (sections 7af–7ah, ledger
   A-002). Nothing about Stage 1 is launchable any more; the
   cross-sectional alpha program on this universe is CLOSED.
2. **Original review context (superseded):** With Codex tokens exhausted, the owner ran the
   independent review through Cursor (Grok 4.6) instead on 2026-08-18. It
   reviewed the full range `81db126..de1beac` (27 commits, every commit
   dispositioned), accepted all seven product/test commits and all twenty
   record commits, and raised eight findings (S0R-001..008: two P2
   blocking Stage 1 only, six P3). Claude counter-reviewed every finding
   the same day: five confirmed, one confirmed-and-strengthened by
   mutation (S0R-008 — `fillna(1.0)→fillna(0.0)` survives ALL 57
   alpha-analyser tests, not just the two cited), one partially correct
   (S0R-003 — the `nan` half verified by execution, the `inf` half a
   false alarm), one resolved by topology (S0R-006 — PR #249 merged
   `de1beac` into main after the review snapshot). Records:
   `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md`
   (Cursor) and
   `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`
   (Claude). None of the eight findings invalidates the nine
   PENDING_REVIEW logs. **Next: the owner accepts or rejects the review
   pair. On acceptance, upgrade the nine ledger entries and run the
   frozen analysers ONCE with full run identities — the only step where
   any statistic is observed. Stage 1 stays blocked until S0R-001 and
   S0R-002 are ported with regression tests (S0R-003/004/005/008 belong
   in the same hardening round).**
2. ~~Claude must counter-review `codex/review-qc-stage0-run-20260817`~~ —
   DONE and accepting (section 7u); superseded by section 7v's halt.
2. PR #244 merged Claude's Stage 0 correction counter-review at `b6f577e`;
   the merge tree is byte-identical to exact reviewed head `9a7e9fc`.
   Codex independently accepts that range in section 7r. Its only correction
   is a test-only P3 call-site guard merged via PR #245 at `1457169`.
   Superseded for sequencing by section 7s: the owner chose Stage 0 first,
   and the launch round then found the residual-factor event-timing defect.
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

Standing operational constraints at this review snapshot:

- `paper-epoch-005` is historical and closed. `paper-epoch-006` is the
  active evidence epoch on the operational release recorded in
  `docs/operations/OPERATIONAL_FACTS.md`. Do not deploy, roll, or disturb
  it without a new explicit owner instruction; a runtime change closes
  the epoch because code lineage cannot pool.
- **The operational checkout's `my_policy.json` stays at 0.50/0.05.** The
  development copy carries 0.90/0.07 so the approved profile is reachable,
  and it is untracked so no commit contains it. Copying it across would
  change the policy fingerprint and stall the active epoch exactly as
  epoch-002
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
docs/SESSION_HANDOFF.md, docs/reference/ALLOCATION_POLICY_QC_PLAN.md,
docs/reference/SHADOW_OBSERVATION_DESIGN.md, docs/alpha-result.md, and
docs/Review/REVIEW_2026-08-19_POST_STAGE0_THROUGH_SBR1.md. The exact
independently reviewed pushed range is
81db126340818fe2c2c9efa16c77af8f1d37568f..3055fecd1caf490c852a446c03da760d2878af5a
(143 commits). The Codex correction branch is
codex/review-post-stage0-through-sbr1-20260819. Stage 0/1 and APQ are
closed null; SHW-4 is live; LEV-1 and SBR-1 are accepted only after the
review corrections and still require merge/counter-review. Do not run
QC, install the SBR task, deploy, trade, mutate an operational database,
or roll paper-epoch-006 without the owner's separate authorization.
```

## 9a. Archived 2026-08-17 resume prompt (historical only)

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/Alpha_Test_Implementation_Plan.md,
docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md, docs/alpha-result.md and
docs/SESSION_HANDOFF.md. origin/main is b6f577e after PR #244 merged Claude's
Stage 0 correction counter-review head 9a7e9fc with an identical tree. PR #243
at 4151b3f merged Fable's final counter-review (PR #242 at f937bfb merged the
counter-review integration branch; PR #241 at d8a3260 merged the full audit
before it). Corrections
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
user/claude/alpha-qc-fable-cr-verify-20260817. Codex then independently
accepted its exact three-commit range and FCR-001/002 after one P3 test-only
hardening: helper correctness did not prove the live Stage 1 ingestion called
the helper, so commit 39e5d99 pins all three `_fine` call sites and stale-code
eviction. No algorithm behavior changed. See section 7r and
docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md.
The code-review gate is satisfied; before launch, the owner confirms whether
Stage 0 battery completion or Stage 1 runs first.
No run occurred and the 428-cell/five-run counts are unchanged.
Append every run rather than overwrite ledger entries; a premature run is
PENDING_REVIEW and still counts.
paper-epoch-005 remains unchanged at 752d3b7 for 60 days; operational
my_policy.json stays 0.50/0.05. Do not merge, deploy, roll the epoch, mutate
the operator database, submit orders, access funded accounts, begin M4, or
enable live trading without explicit owner authority.
```
