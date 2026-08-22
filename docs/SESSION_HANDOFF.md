# Session handoff — current project state

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
7t). The SBP rounds in sections 7bm through 7bq then superseded that
sequencing text, section 7br records the topology refresh, section 7bs records
Claude's documentation/SBP audit, and section 7bt records Codex's independent
correction review. Section 7bv records the later ACER replacement, 7bw its
independent review, 7bx the counter-review, 7by the vendor audit, 7bz the
independent correction review, 7ca the counter-review of that correction,
7cb the ACER event backbone, 7cc its independent review, 7cd the
counter-review of that review, 7ce the ACER-0A submission, 7cf Codex's
independent correction review, 7cg the counter-review of that review, and
7ch the submitted issuer-identity detector, 7ci Codex's independent
correction review, 7cj the counter-review of that review, and 7ck the
ACER-0A completion proposals. Section 7cl records Codex's independent
correction review of those proposals, 7cm the counter-review of that review,
7cn the local data-capability audit, 7co Codex's independent correction
review of both new commits, and 7cp the counter-review plus the committed
capability checks. Section 7cq records Codex's independent review and
fail-closed correction of those checks, and 7cr the counter-review that
attempted to complete the requirement set. Section 7cs records Codex's
independent correction of the remaining false-completeness path, 7ct the
counter-review that attempted to fix the derivation guard, and 7cu Codex's
independent verification and correction of that guard. Section 7cv records
the provider-neutral capability correction, and section 7cw records the
owner-directed role swap, measured local access state, and documentation
lifecycle reset. Sections 7cx–7cz record the engine amendment and Claude's
review, and section 7da records Codex's counter-review; 7da and section 8 are
the current development state.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

Reordered 2026-08-20 for the ACER priority. The alpha-program reading list
that stood here is preserved in section 9a's archived resume prompt; that
program is closed (`A-001`, `A-002`) and is no longer the entry point.

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-20.md` — the go-to plan (ACER first)
3. `docs/research/ACER_2026-08-20_ACER0A_FREEZE.md` — the **partially frozen
   ACER-2 decision record** and its ACER-0A.1–0A.10 completion ledger
4. `docs/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md` — the ACER
   contract shape; ACER-0A incomplete, ACER-0B deliberately still draft
5. `docs/reference/analyst-consensus-etf-strategy.pdf` — the owner-supplied
   design narrative; the Markdown ACER contract governs where they differ
6. `docs/Archive/Research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md` —
   the closed historical capture contract
7. `docs/Archive/Review/REVIEW_2026-08-19_SBP_PLAN_AMENDMENTS.md` and
   `docs/Archive/Review/REVIEW_2026-08-19_SBP_PLAN_COUNTERREVIEW.md` and
   `docs/Archive/Review/REVIEW_2026-08-20_SBP_PLAN_COUNTERREVIEW_VERIFICATION.md` and
   `docs/Archive/Review/REVIEW_2026-08-20_SBP_REVIEW_AUDIT.md` and
   `docs/Archive/Review/REVIEW_2026-08-20_SBP_DOCUMENTATION_CLEANUP.md` — the full
   SBP review chain, in order
8. `docs/operations/OPERATIONAL_FACTS.md` — machine-local operational truth
9. `docs/operations/OPERATIONS_RUNBOOK.md`
10. `docs/operations/MANDATE.md` (§2, §4, §6)
11. `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
12. `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
13. `docs/research/alpha-result.md` — the permanent run ledger (append-only)
14. `docs/Archive/Plans/Alpha_Test_Implementation_Plan.md` — closed program, historical

Nothing here authorizes a push, merge, pull request, deployment, evidence
repair, epoch roll, M4, funded-account access, live trading, paper order,
operator-database mutation, or scheduled-task change.

## 1. Exact repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Published `origin/main` at audit time: `6cdb423` (ACER review, 2026-08-20).
  PR #286 merged Claude's ACER documentation snapshot `f3b960d`; the
  review branch begins from that exact mainline head.
  Historical at the prior SBP documentation review start, `origin/main` was
  `13355a6`.
  PR #282 at `c289f95` merged the whole eight-commit SBP chain
  `5c42bfd..308ac84` — the
  amendments, the review correction and record, the counter-review, the
  security-age clarification, the verification record, and their handoff
  updates — onto first parent `5e3708e` (PR #281, the post-Stage-0 audit).
  PR #283 merged Claude's topology refresh; PR #284 at `13355a6` merged its
  SBP audit, documentation sweep, and replacement Action Plan. Sections 7bn
  through 7bs are merged history on `main`.
- Codex's documentation-cleanup review branch
  `codex/review-sbp-doc-cleanup-20260820` was based on submitted main head
  `13355a6`. Claude's counter-review branch published it, and PR #285 merged
  the chain, so `390f3ad`, `8d16632`, `1055392`, and `e5ae3d4` are mainline
  history at `6f571c2` and fetchable with `git fetch origin main`.
- Historical, at the 2026-08-17 audit `origin/main` was
  `1457169ba10f6aac0f1fb98b60b92a4607f8331c` (this bullet's original
  "at audit time" wording now belongs to the current head above).
  PR #245 merged Codex's prior verification branch; PR #244 at `b6f577e` merged Claude's exact
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
  `docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md`.
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
- The permanent ledger now contains 30 run-level looks through APQ R-029.
  The reviewed Stage 0/1 runs are VALID but closed null at A-001/A-002; APQ is
  valid and closed null at A-003. Older legacy rows retain their individual
  invalid/refused/unanalysed/provenance states. The closed cross-sectional
  alpha-program floor is 452 cells at A-002; APQ's separate three-cell family
  does not change it.
- `docs/Archive/Plans/Alpha_Test_Implementation_Plan.md` is a **closed historical
  contract**, not the current work queue. The replacement Action Plan puts the
  draft Strong-Buy program first.
- PR #234 first merged the prior Codex REBAL-3V/3W review through
  `f63fe2cb30aa904dec131962a133e1058185427c`; correction `3a506ae` and records
  `dae34d0` are therefore pushed, fetchable, and in `main`.
- Prior local-alpha history: Claude's pushed branch
  `origin/user/claude/alpha-battery-20260815` is exact
  head `046afc3ee39c0fff9c916e88657c43a1b5f4e5f1`; PR #236 merged it at
  `3d58f6b`.
- That prior reviewed literal range was `f63fe2c..3d58f6b`. It contains, in order,
  `db0045a`, `4de88d0`, `046afc3`, and merge `3d58f6b`; all four have an
  explicit disposition in `docs/Archive/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md`.
- That prior review branch was `codex/review-alpha-battery-20260816`.
  Product/test correction `124192ff3e29c3fc62f0c9e8bf95b9aadf216915`
  was merged by PR #237 before current `main`.
- The submitted alpha result and audit artifacts are **invalidated pending a
  clean rerun**. At the owner's direction, invalid generated Markdown, JSON,
  and raw logs were removed from active docs only after their exact identities,
  hashes, and dispositions were preserved in `docs/research/alpha-result.md` and Git
  history. Nothing was promoted to the research registry or Feature Milestone
  Record.
- The operational checkout remains separate and is frozen at `c9d0740`,
  where `paper-epoch-006` is active (roll executed 2026-08-19;
  `paper-epoch-005` was closed the same day, retaining its 3 observations).
  No development commit has been copied there.
  `docs/operations/OPERATIONAL_FACTS.md` is the authority for operational
  state; this bullet only points at it.

Earlier history that remains load-bearing for anyone resuming:

- `4de784e` / `1cb8abf`: the epoch-005 observation-clock roll chain and
  Codex's correction of it. `paper-epoch-005` was the only evidence epoch
  running from 2026-08-13 until the epoch-006 roll closed it on 2026-08-19;
  epochs 001 through 005 are closed and cannot pool evidence into
  epoch-006.
- `c048a94`: the owner's decision to hold epoch-005 unchanged for 60 days.
  Superseded 2026-08-19, when the owner authorized the epoch-006 roll: it
  closed epoch-005 at 3 observations and restarted the 60-session /
  30-order clock on deployed `c9d0740`.
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
ledger is in `docs/Archive/Review/REVIEW_2026-08-15_REBAL1_STAGE3.md`.

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
`docs/Archive/Review/REVIEW_2026-08-15_REBAL1_STAGE3_COUNTERREVIEW.md`.

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
Disposition in `docs/Archive/Review/REVIEW_2026-08-15_REBAL1_STAGE3_END_TO_END.md`.

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

See `docs/Archive/Review/REVIEW_2026-08-15_REBAL1_FEASIBILITY_VISIBILITY.md`.

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

See `docs/Archive/Review/REVIEW_2026-08-15_REBAL1_TRIM_REFUSAL_ACCURACY.md`.

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
`docs/Archive/Review/REVIEW_2026-08-15_REBAL3V_REBAL3W_INDEPENDENT.md`.

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
`docs/Archive/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md`.

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
`docs/Archive/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md`.

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
`docs/Archive/Review/REVIEW_2026-08-16_ALPHA_QC_ROUND1.md`.

Documentation commit `e1aedc7` creates
`docs/Archive/Plans/Alpha_Test_Implementation_Plan.md`, corrects `docs/research/alpha-result.md`, and
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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`. Six round-1 Codex commits are
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
floor therefore remains 428. `docs/research/alpha-result.md` contains no Stage 1 run;
any run launched before Claude counter-review must be appended as
`PENDING_REVIEW` and counted rather than reused.

## 7l. Full research/QC and documentation audit (Codex, 2026-08-17)

At the owner's request, Codex stopped treating Stage 1 as the audit boundary
and reviewed all research/QC code created or changed during the day's alpha
work. The exact per-commit dispositions and permanent P0-P3 ledger are in
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`. No QuantConnect API,
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
`docs/research/alpha-result.md` were removed from active docs at the owner's direction.
Their run IDs, statuses, hashes, look counts, and Git history remain. Frozen
preregistrations and Method V2 remain under `docs/research/` as historical
contracts, each with a current validity note. Review reports now live under
`docs/Archive/Review/`, workflow rules under `docs/process/`, operational records
under `docs/operations/`, and architecture records under
`docs/architecture/`. The docs root contains only canonical/milestone/result
documents. `docs/reference/Alpha explanation.md` gives the owner a plain-
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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2_COUNTERREVIEW_INDEPENDENT.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md`.

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
  `docs/research/alpha-result.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_FABLE_COUNTERREVIEW.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_CORRECTION_COUNTERREVIEW.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_ROUND.md`.

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
`docs/Archive/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_COUNTERREVIEW.md`.

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
ledgered in `docs/research/alpha-result.md` with full identity and structural
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
`docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md`.

Claude counter-reviewed all eight findings the same day
(`docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`,
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
   entry **A-001** (`docs/research/alpha-result.md`).
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
`docs/Archive/Review/REVIEW_2026-08-18_S0R_HARDENING_REVIEW.md`.

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
`f84f5fa` (`docs/Archive/Review/REVIEW_2026-08-18_S0R_HARDENING_COUNTERREVIEW.md`,
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
two summary paragraphs in `docs/research/alpha-result.md` still said
PENDING_REVIEW / "no statistic observed" above A-001 — confirmed and
FIXED this round: headings retitled VALID, dated superseding notes
appended, originals retained) and **S0R2-002** (the `2be903f` upgrade
used VALID where the frozen vocabulary's honest intermediate was
UNANALYSED — closed without change on the final tree; the vocabulary
rung PENDING_REVIEW → UNANALYSED → VALID is recorded for future
rounds). Claude's counter-review executed the review's own §10
checklist in full and verified its checkable claims 100%
(`docs/Archive/Review/REVIEW_2026-08-18_S0R_FOLLOWUP.md` and
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
(`docs/Archive/Review/REVIEW_2026-08-18_STAGE1_LAUNCH_DRIVER.md`, pushed on
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
(`docs/Archive/Review/REVIEW_2026-08-18_STAGE1_RUNS.md` and
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
- **Step 2 DRAFT:** `docs/Archive/Plans/SHADOW_OBSERVATION_DESIGN.md` —
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
`docs/Archive/Review/REVIEW_2026-08-18_POST_CLOSURE_MAIN.md`.

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
(`docs/Archive/Review/REVIEW_2026-08-18_POST_CLOSURE_COUNTERREVIEW.md`):

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
`docs/Archive/Reference/overlay_shadow_config.example.json`.

Deliberately NOT included: Windows scheduler installation (deferred to
SHW-4 stream start — there is no stream to schedule yet) and any
performance/sufficiency output (SHW-3). SHW-4 registration still
requires the owner to freeze the defensive-carry preregistration's
[TO FREEZE] gates first.

## 7an. Independent review of SHW-2 (2026-08-19)

Cursor Grok 4.6 reviewed `d4c04c4..354a233` at exact head
`354a233243d676aae05b1dc3bf53b29d6b96c2b3`
(`origin/user/claude/shw2-overlay-runner-20260818`). Report:
`docs/Archive/Review/REVIEW_2026-08-19_SHW2_OVERLAY_RUNNER.md`.

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
(`docs/Archive/Review/REVIEW_2026-08-19_SHW2_OVERLAY_RUNNER.md`, on
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
`docs/Archive/Review/REVIEW_2026-08-19_SHW2_FIX_VERIFICATION.md`.

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
(`docs/Archive/Review/REVIEW_2026-08-19_SHW2_FIX_VERIFICATION.md`): both P2s
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
`docs/Archive/Review/REVIEW_2026-08-19_SHW3_SUFFICIENCY.md`. Written from an
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
(`docs/Archive/Review/REVIEW_2026-08-19_SHW3_SUFFICIENCY.md`). Counter-review
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
`docs/Archive/Plans/EPOCH_005_ROLL_PLAN.md`'s preconditions and the runbook:

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
`docs/Archive/Review/REVIEW_2026-08-19_SHW4_STREAM_START.md`.

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
(`docs/Archive/Review/REVIEW_2026-08-19_SHW4_STREAM_START.md`): its P2 was a
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
gate freeze, and this roll. All review records live in `docs/Archive/Review/`;
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
`docs/Archive/Review/REVIEW_2026-08-19_APQ1_ALLOCATION_POLICY.md`. No QC.

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
(`docs/Archive/Review/REVIEW_2026-08-19_APQ1_ALLOCATION_POLICY.md`): its P2 was
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
`docs/Archive/Review/REVIEW_2026-08-19_APQ2_ANALYSER.md`. No QC.

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
(`docs/Archive/Review/REVIEW_2026-08-19_APQ2_ANALYSER.md`) and — the round's
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
`docs/Archive/Review/REVIEW_2026-08-19_APQ3_DRIVER_HOOK.md`. No QC.

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

Counter-review (`docs/Archive/Review/REVIEW_2026-08-19_APQ3_COUNTERREVIEW.md`)
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
**R-029 UNANALYSED** in `docs/research/alpha-result.md`; run-level look
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
`docs/Archive/Review/REVIEW_2026-08-19_MPQ_HPQ_PLANS_COUNTERREVIEW.md`. Both
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
- `docs/Archive/Operations/strongbuy_ratings_config.json`: frozen 102-ticker
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
`docs/Archive/Review/REVIEW_2026-08-19_POST_STAGE0_COUNTERREVIEW.md`. All six
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
`docs/Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md`. The draft preserves the
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
`docs/Archive/Review/REVIEW_2026-08-19_SBP_PLAN_AMENDMENTS.md`.

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
`codex/review-sbp-plan-amendments-20260819` was still awaiting the owner's
push authorization when this section was written. PR #282 (`c289f95`) has
since merged it, so `5c42bfd`, `5c3bf45`, and `2a26353` are fetchable
mainline history.

## 7bp. Counter-review of the SBP review submitted (2026-08-20; clarified by 7bq)

Record: `docs/Archive/Review/REVIEW_2026-08-19_SBP_PLAN_COUNTERREVIEW.md`. All three
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
`docs/Archive/Review/REVIEW_2026-08-20_SBP_PLAN_COUNTERREVIEW_VERIFICATION.md`.

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

Remote topology, corrected 2026-08-20 after the merge. This section was
written while both branches still awaited the owner's push authorization; PR
#282 (`c289f95`) has since merged the whole SBP chain into `main`, so
Claude's counter-review `f75e793`, correction `aadb238`, record `ae07450`,
and handoff `308ac84` are all mainline history, reachable with
`git fetch origin main`. The superseded sentence claimed the opposite: a
push/merge status written inside the commit being merged is false by
construction the moment it lands, which is the CCR-005 class
`test_no_document_calls_a_merged_commit_unreachable` exists to catch — and
did catch here.

## 7br. Post-merge topology correction (docs only, 2026-08-20)

Branch `user/claude/handoff-topology-refresh-20260820`, from `main` at
`c289f95`.

`tests/test_active_document_consistency.py::test_no_document_calls_a_merged_commit_unreachable`
was RED on `main`: section 7bq still described its own correction commit as
local-only after PR #282 had merged it. That is the CCR-005 class exactly as
its docstring predicts — a push/merge status written inside the commit being
merged is false the moment it lands, so only a check that runs after the merge
can catch it. This round
is that check being honoured rather than edited.

Corrected, all documentation:

- **Section 1** named `origin/main` as the 2026-08-17 head
  `1457169…` and the operational checkout as frozen at `752d3b7` in
  epoch-005. It now declares `c289f95` (PR #282 merged the eight-commit SBP
  chain `5c42bfd..308ac84` onto first parent `5e3708e`) and the operational
  checkout as frozen at `c9d0740` under `paper-epoch-006`, pointing at
  `docs/operations/OPERATIONAL_FACTS.md` as the operational authority. The
  literal phrase the topology guard parses ("Published `origin/main` at audit
  time: `<hash>`") was deliberately kept so the guard keeps binding; the
  superseded head is retained as an explicitly historical bullet.
- The two load-bearing history bullets no longer imply epoch-005 is running:
  it was the only epoch from 2026-08-13 until the epoch-006 roll closed it on
  2026-08-19, and the owner's 60-day hold decision (`c048a94`) is marked
  superseded by that authorized roll.
- **Sections 7bo, 7bq, and the section 8 sequencing sentence** stated the
  branches were local-only or awaiting a push. All three now record the merge.
  Push/merge claim words are kept out of the same clause as the hashes they
  describe, because the guard's parser reads a claim within 80 characters of a
  hash — wording that merely happened to fall outside that window would be
  luck, not a fix.

Verified: every hash named in sections 7bn–7bq is an ancestor of
`origin/main` (checked with `git merge-base --is-ancestor`, ten hashes, all
reachable). Validation: `tests/test_active_document_consistency.py` 31 passed
(red → green on the guard above, which is the regression evidence — the
failure existed on `main` before this branch); full suite and `git diff
--check` recorded in the round's handoff commit message. No code, contract,
schema, CLI, migration, research result, ledger entry, milestone status, QC
access, broker access, scheduled task, deployment, or operational database
changed. No milestone record entry was added: correcting stale prose is not a
milestone.

Not corrected here (out of the requested scope, still stale, and named so the
next round can decide): `docs/Archive/Plans/Alpha_Test_Implementation_Plan.md`'s status
header still says Stage 0 is halted with reruns beginning at R-007, though
Stage 0 and Stage 1 closed null as A-001/A-002; and
`docs/operations/GENERAL_READINESS_STATUS.md` /
`docs/operations/ML_IMPLEMENTATION_STATUS.md` still cite their companion plans
at pre-2026-08-17 `docs/` paths that now live under `docs/reference/`.

## 7bs. SBP review audit, documentation sweep, and the new Action Plan (2026-08-20)

Branch `user/claude/sbp-review-audit-20260820`, from `a2b69eb`. Owner
instructions, in order: audit Codex's SBP amendments review; then compare all
documentation against what the project actually does; then replace the Action
Plan with the Strong-Buy initiative first.

**1. Audit of `docs/Archive/Review/REVIEW_2026-08-19_SBP_PLAN_AMENDMENTS.md`:
SUSTAINED** (`docs/Archive/Review/REVIEW_2026-08-20_SBP_REVIEW_AUDIT.md`). All seven
findings verify against the plan text, correction `5c3bf45`, and Git; the
one-commit range `5e3708e..5c42bfd` is complete; every claimed correction is
present. Six findings the review did not make are recorded, four of them plan
defects now proposed as **SBPA-007..010**:

- **SBPA-007 (P2)** — the 15% look-through issuer cap cannot bind at the
  proposed 5% sleeve and 3x leverage. Binding needs one issuer at 36.7% of the
  ordinary fund (`0.95*0.10 + 0.05*3*w >= 0.15`); the P3 form needs 110%. The
  gate and its refusal class are inert as written. This is SBPR-006's class
  inverted: the review caught a state the rule always refuses and missed a
  gate that never fires.
- **SBPA-008 (P2)** — section 4 cites that per-issuer cap as the mitigation
  for inverse-volatility concentration in "economically related stocks". A
  per-issuer cap cannot constrain a cluster of distinct issuers in one
  industry, and no industry limit exists in the plan.
- **SBPA-009 / SBPA-010 (P3)** — months with exactly 10 eligible names are
  structural zeros in P2−P1 (the cap forces equal weights, so P2 = P1), and
  the overlay-block alignment rule lets descriptive P4 availability delete
  inferential P3−P2 months. Both decide which months count, so both must be
  settled before the freeze.
- Two findings need no plan change: the report's Verification column cites a
  document-consistency suite that is insensitive to the defects it closed, and
  the required power table should cover the frozen bootstrap's own behaviour
  at mean block length 3 over 24 months (~8 effective blocks).

**2. Documentation-versus-reality sweep.** Claims were checked against code
and Git rather than against other documents. Verified accurate: every CLI
command named in the runbook and handoff exists; policy defaults match the
mandate (5% position, 50% exposure, 20% leveraged, 10% cash, $5,000 order);
`assistant/default_mandate.json` is approved with autonomous execution false;
the SBR config carries exactly 102 tickers; the modules named across the plans
exist. Corrected: the UI is **14 pages**, not the ten the README described,
and its page names changed with TRADE-1/HEDGE-1/REBAL-1 (README now lists
Budgeted/Discrete Buying, Policy Based/Discrete Selling, Hedging, and
Portfolio Rebalancing, and the stale "Watchlist tab" references are gone);
`docs/Archive/Plans/Alpha_Test_Implementation_Plan.md` no longer says Stage 0 is halted with
reruns beginning at R-007, since Stage 0 and Stage 1 closed null; the two
`docs/operations/*_STATUS.md` companions had pre-reorganisation `docs/` paths
and now say plainly that their milestone content is a dated snapshot;
`docs/Archive/Reference/README_legacy.md` gained the three missing archive rows. Measured
figures that documents had quoted stale: `platform_readiness.py` 856 lines
(not 778), `execution_service.py` 1,062 (not 900), `assistant/llm/` 9 modules
(not 10). The new plan cites paths and behaviour instead of line counts.

**3. `docs/ACTION_PLAN_2026-08-20.md` replaces the 2026-08-02 plan**, which is
archived at `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md` with a superseded
banner. The successor is 317 lines against the predecessor's 769 (785 after
its banner) and is
organised by priority: Strong-Buy first (SBP-0 freeze is the only thing
blocking the path, and it should happen **before** the SBR task install so no
month is spent as calibration-only), then keeping the running paper and
overlay evidence honest, then LEV as an explicitly secondary historical study,
then everything unscheduled. It carries a measured state-of-the-project
section, the documentation corrections above, the standing safety constraints,
and a closed-history section that retains verbatim the ledger rows
`tests/test_active_document_consistency.py` pins (AP-7..AP-11, SELL-1, BUY-1,
QC-2, GR-7d, AP-8b) so no guard was weakened to fit a new document.
`CLAUDE.md`, `AGENTS.md`, the handoff's read-first list and live resume
prompt, and the guard suite's twenty pinned references now name the successor;
historical citations in code comments and archived plans were repointed to the
archive path rather than rewritten.

Validation is recorded in section 8. No code behaviour changed anywhere in
this round: the only non-documentation edits are the guard suite's document
name and three comment/docstring path corrections. No QuantConnect access,
broker access, market data, scheduled task, deployment, epoch action, or
operational database mutation occurred, and no plan value was adopted or
frozen — SBP-0 remains the owner's to decide.

## 7bt. Independent review of the SBP audit and documentation cleanup (2026-08-20)

Codex reviewed the exact merged range `c289f95..13355a6` on
`codex/review-sbp-doc-cleanup-20260820`, including all five commits and both PR
merge commits. The merge trees are identical to their submitted second-parent
trees; neither merge added hidden conflict-resolution edits. Every commit is
dispositioned in
`docs/Archive/Review/REVIEW_2026-08-20_SBP_DOCUMENTATION_CLEANUP.md`.

Verdict: **ACCEPTED AFTER CORRECTION**. Correction/review commit `390f3ad`
closes one P2 evidence-status contradiction and five P3 plan/handoff defects.
The corrected documents distinguish reviewed **VALID but null** Stage 0/1
evidence from invalid legacy runs; treat the 15% issuer cap as impossible for
P3 but a possible rare-tail P4 gate; retain exactly-10-name months as genuine
zero outcomes in primary P2−P1; align inferential P3−P2 without descriptive
P4; separate bootstrap power as SBPA-011; and restore one contiguous amendment
ledger. Three new guards failed on the submitted tree and pass after the
correction. No application behavior or research result changed.

Validation after the substantive correction: 50 focused tests passed in 2.52
seconds; the first full suite passed **4,351 / 0 failed / 25 warnings** in
947.30 seconds. The full suite was then rerun on the completed review tree
including this handoff content and again passed **4,351 / 0 failed / 25
warnings** in 872.04 seconds. Python 3.13.14; required compileall plus
`research/` and `git diff --check` passed. After recording these exact numbers,
the 50 focused document/contract tests were rerun on the final prose. That
branch was published by the counter-review round and merged by PR #285.

## 7bu. Counter-review of the documentation-cleanup corrections: ACCEPTED (2026-08-20)

Branch `user/claude/sbp-doc-cleanup-counterreview-20260820`, from Codex's exact
head `8d16632`. Record:
`docs/Archive/Review/REVIEW_2026-08-20_SBP_DOC_CLEANUP_COUNTERREVIEW.md`.

**Snapshot deviation:** Codex's branch was local-only, so the snapshot was
frozen by branching from the exact local object and pushing this branch, which
publishes `390f3ad` and `8d16632` as ancestors.

**Verdict: ACCEPTED.** All six findings confirmed, including the P2, which is a
real defect in my own round: I carried forward "every historical QuantConnect
result remains invalid" from the 2026-08-17 audit without re-checking, while
the ledger marks R-009..R-028 VALID with null observations at A-001/A-002. The
floor is 452 at A-002, not 428, and the ledger holds 30 run-level looks, not
five. Calling a null result invalid is not a wording slip — it invites
re-running a question already answered. SBDC-002 (my "structurally inert" cap
claim overstated an empirical fact as a contractual one), SBDC-003 (excluding
exactly-10-name months would change the estimand, and my variance claim was
wrong — appending a zero to positive values raises variance), SBDC-005 (my
amendment rows were separated from their table by a blank line and rendered
outside it) and SBDC-006 are likewise confirmed. Verified independently: both
PR merge trees are byte-identical to their submitted heads (`9009239`=`a2b69eb`,
`13355a6`=`a77c6a5`), and the three new guards reproduce 3/3 red on the
pre-correction documents through a `trap`-protected restore.

Five counter-review items closed (CRV-001..005): the R-029 ledger entry's
heading said `(UNANALYSED)` while its own Validity row said `VALID` — SBDC-001's
exact class, missed by both reviews, now corrected without touching the upgrade
history; two of the new guards pinned must-stay-true literals against this
module's own documented doctrine and are now relationship regexes, re-verified
red; the contiguity guard raised `StopIteration` instead of naming the missing
amendment; SBP plan §6 now states the core block's alignment rule, closing for
P1−P0/P2−P1 what SBDC-004 closed for P3−P2; and SBPA-011 now also requires the
expected frequency of exactly-10-name months, since those genuine zeros dilute
the detectable effect.

One owner-facing consideration is recorded as a **question, not a finding**:
registered index funds' diversification rules may keep any single issuer far
below the 36.7% weight SBPA-007's gate needs. This repository holds no evidence
for that, so SBP-0's existing official-issuer-document check is where it must be
sourced. No plan text asserts it.

Validation on the final tree: the full suite ran **4,350 passed / 1 failed /
25 warnings** in 775.01 seconds, and the single failure was
`test_current_review_documents_have_no_validation_placeholders` firing on the
unfilled result token in this very sentence — the guard doing exactly its job.
After substituting these measured numbers, the focused document/contract suite
(`test_active_document_consistency.py` + `test_proposal_outcome_groups.py`)
passes 50, including that guard. The confirming full run on the exact pushed
tree (`1055392`) then passed **4,351 / 0 failed / 25 warnings** in 706.64
seconds. Codex's corrected tree was independently reproduced at
**4,351 passed / 25 warnings** in 920.88 seconds before this round's changes.
Python 3.13.14; `compileall` over the required surface passed; `git diff
--check` passed. No product behaviour, research result,
QuantConnect access, broker access, scheduled task, deployment, epoch action, or
operational database changed. SBP remains a DRAFT; SBP-0 is still the owner's
decision.

## 7bv. ACER replaces the Strong-Buy program by owner decision (2026-08-20)

Branch `user/claude/acer-replaces-sbp-20260820`, from `main` at `6f571c2`
(PR #285 merged the documentation-cleanup review chain).

**Owner decision:** the Analyst-Consensus ETF Rotation program (ACER) replaces
the Strong-Buy portfolio program as priority 1. The owner supplied the source
specification as a PDF, now versioned at
`docs/reference/analyst-consensus-etf-strategy.pdf`
(sha256 `3700ab4b…`, 138,347 bytes). Its operative contract shape for this
repository is `docs/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md`
(ACER-0..7), status DRAFT — nothing frozen, purchased, scheduled, or run.

**What ACER is, and why it is not SBP re-plumbed.** The signal moves from
consensus *levels* to per-firm *revisions* with freshness decay; the held
instrument moves from a stock basket to ETFs scored as the sum of
point-in-time constituent weights times holdings' signals, filtered on breadth
and analyst coverage. It is permitted under the A-002 closure because it
brings all three of what that closure requires: a new data source, a fresh
preregistration, and an owner decision.

**Consequences handled rather than left implicit:**

- `docs/Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md` is **SUPERSEDED while
  still a draft** — never adopted or frozen, so no capture, evidence, result,
  or operational state changes. Retained in full with SBPA-001..011 and its
  four-round review chain.
- The frozen SBR capture preregistration is **CLOSED before its first verified
  capture**, with the reason recorded in the document itself: ACER's primary
  signal is the per-firm revision, and monthly bucket counts cannot
  reconstruct per-firm actions — a count moving 12 to 13 Buys names no firm,
  no date, and no prior rating, and offsetting actions inside a month are
  invisible. **No snapshot is committed and the task must not be installed**;
  the machine-local task and artifact state has not been measured, so neither
  is a verified absence claim. The capture code, tests and installer stay in
  the tree for any future level-based hypothesis.
- LEV is unchanged and still separate; MPQ/HPQ remain on hold; the closed
  families A-001/A-002/A-003 remain closed.

**Concerns recorded in the plan before any result exists**, because this
repository requires the prior to be disclosed in advance and the source
document does not carry it: eleven local signals, Stage 0's 180 cells, Stage
1's 24 and APQ's 3 all closed null; post-recommendation drift is heavily
arbitraged in the literature; ETF aggregation dilutes toward the fund's common
factor, so large-cap technology ETF scores will be strongly collinear and
ranking ETFs partly re-ranks one factor; the source document declares no
family size, gate, or run budget, which ACER-0 must fix; ACER-2's control set
(earnings dates, standardized surprise) is a second dataset and a second
budget line that a ratings subscription does not cover; and a QuantConnect
cloud dataset cannot be hashed by this project, a real gap against the
content-addressing rule that every run record must disclose.

**ACER-2 is the decisive milestone** — do stock-level revisions carry
incremental out-of-sample information after momentum, earnings, size,
liquidity, volatility and sector controls? It needs no ETF holdings, no
inverse products and no leverage, and a null there closes the program for one
data purchase rather than a seven-stage build. Everything from ACER-3 onward
is contingent and deliberately unscoped.

**New guard:** `test_a_superseded_program_is_not_also_the_next_owner_decision`
pins the relationship that partial replacement breaks — whichever plan
declares itself superseded must not also own the Action Plan's blocking
decision. Written as a relationship, not a literal, so it survives the next
replacement.

**Process note against myself:** during this round a mutation harness used
`git checkout HEAD -- <files>` as its restore while the work was still
uncommitted, which reverted two files of finished edits. Nothing was lost
beyond rework, and the edits were re-applied and re-verified, but the rule is
now explicit: **commit before mutating, so the restore point is the work
rather than its absence.**

Validation on the final tree: the full suite ran **4,351 passed / 1 failed /
25 warnings** in 727.13 seconds, the single failure being
`test_current_review_documents_have_no_validation_placeholders` firing on the
unfilled result token in this sentence — deliberately routed through a token
that guard recognises, so filling it in was enforced rather than remembered.
After substitution the focused document/contract suite passes 51, including
that guard and the new supersession guard. The suite total is now 4,352 tests
(4,351 before this round's addition). Python 3.13.14; `compileall` over the required surface
passed; `git diff --check` passed. No data was purchased, no QuantConnect run
occurred, no scheduled task changed, no broker or operational state changed,
and no ACER value is frozen — ACER-0 remains the owner's decision.

## 7bw. ACER documentation independent review (2026-08-20)

Codex reviewed the owner-supplied nine-page source PDF visually and reviewed
the exact pushed implementation commit `f3b960d` plus PR #286 merge
`6cdb423` on `codex/review-acer-docs-20260820`. Both commits are **accepted
after correction**. Correction commit `e4bef19` fixes four P3 documentation
findings: the Action Plan and current handoff now lead with ACER rather than
the superseded SBP decision; the reference index lists ACER and marks SBP as
historical; claims that the SBR task/snapshots are absent now distinguish no
committed artifact from unmeasured machine-local state; and topology/resume
instructions name PR #286 / `6cdb423`. A regression test fails if the index
again calls superseded SBP "pending owner adoption." The source PDF is
visually sound and remains a research narrative; the Markdown ACER contract
governs where the two differ.

Focused active-document validation passed **36 tests in 0.69s**. The full
suite exited 0 on the corrected review tree; an independent collection counted
**4,353 tests**. A no-bytecode source compilation validated 427 Python files,
and `git diff --check` passed. No data purchase, QuantConnect access, broker
access, scheduler change, deployment, operational database action, epoch
change, or order occurred. This review does not adopt ACER-0. The current
review branch is local-only and must not be described as published until the
owner explicitly authorizes a push.

## 7bx. Counter-review of the ACER documentation review: ACCEPTED (2026-08-20)

Branch `user/claude/acer-review-counterreview-20260820`, from Codex's exact
head `832b7cf`. Record:
`docs/Archive/Review/REVIEW_2026-08-20_ACER_DOCUMENTATION_COUNTERREVIEW.md`.

**Snapshot deviation:** Codex's branch was local-only in the worktree
`trading_agent_codex_acer_review`; the snapshot was frozen by branching from
the exact object and pushing this branch, which publishes `e4bef19`, `73efc11`
and `832b7cf` as ancestors.

**Verdict: ACCEPTED.** All four findings confirmed against the documents, both
claimed mutations reproduced, nothing deleted or weakened. Two are defects in
my own round that re-reading my own text would not have surfaced:

- **ACERDOC-001** — I rewrote the Action Plan for ACER and added section 7bv,
  but never touched the handoff reading list a new session starts from, which
  still said "Strong-Buy priority" and sent the reader to SBP-0. The entry
  point pointed at the superseded program while the plan behind it pointed at
  ACER.
- **ACERDOC-002** — the ACER plan asserted "zero snapshots exist and the
  scheduled task was never installed" while the Action Plan row I wrote in the
  same commit said that state was never measured. Absence from Git is not
  absence on the operational host, and I had corrected this exact overclaim in
  my own draft two rounds earlier before reproducing it.

ACERDOC-003 (the archive index still advertised SBP as "draft pending owner
adoption" with no ACER row) and ACERDOC-004 (topology stopped at PR #285 while
PR #286 had merged) are also confirmed. Codex additionally **rendered the
source PDF visually and read all nine pages**, which is better evidence of
faithful representation than my own stdlib text extraction, whose garbled
formulas I had flagged.

**Four counter-review items closed (ACRV-001..004):**

- The new index guard used `next(...)`, so a deleted row raised `StopIteration`
  with no message — the same defect CRV-003 closed one round earlier and which
  this guard reproduced. Now asserts exactly one row with a diagnostic
  message; both mutations re-verified red.
- **My own overstatement, which the review did not catch:** the plan asserted
  ETF scores "will be strongly collinear" with no correlation computed — the
  unsupported-quantity error that sank SBPA-001, reproduced inside the
  document that cites it as a lesson. Now labelled reasoning rather than
  measurement, with ACER-3 required to measure realized cross-sectional
  correlation and report it beside any ranking result.
- The unmeasured machine-local SBR state was correctly flagged but assigned to
  nobody. ACER-1 now must measure task presence and snapshot count on the
  operational host, read-only, and record it in `OPERATIONAL_FACTS.md`.
- The review reported an exit code and a collection count but no pass/fail
  counts, which `CLAUDE.md` §10 requires; measured independently below.

Validation at submission: the full suite ran **4,352 passed / 1 failed /
25 warnings** in 953.04 seconds, the single failure being
`test_current_review_documents_have_no_validation_placeholders` firing on the
then-unfilled result token; after substitution only the focused suites reran.

**Codex follow-up accepted (2026-08-20), two P3s, both mine:** this section
was numbered 7bw although the reviewed head's own review section already used
7bw — the MHP-001 numbering-collision class; renumbered to 7bx with
cross-references updated. And the substitute-then-focused pattern above left
the final pushed tree without a completely green full-suite run — a
validation-record gap, not a product defect (Codex independently reran the
relevant file: 36 passed). Both corrected in the follow-up round below, which
also changes its ordering so the green run precedes the recorded sentence
rather than chasing it.

Follow-up round validation (branch `user/claude/acer-cr-followups-20260820`):
all prose above this paragraph was finalized first, with no placeholder token,
and the full suite then ran completely green on that tree — **4,353 passed /
0 failed / 25 warnings** in 709.06 seconds, Python 3.13.14. This paragraph and
the recorded numbers are the only later change; the focused document/contract
suites reran on the final prose, `compileall` over the changed surface passed,
and `git diff --check` passed. That closes the ACRV-004-adjacent gap Codex
raised: the green run now precedes its own record instead of being displaced
by it. Codex's disputed vendor figures ($1,500/yr Zacks — owner-reported;
1995/14,000+ delisted — web-search summaries; 1985 — Codex's own reading) are
confirmed absent from every committed document and remain chat-level claims
for the vendor audit. No product behaviour changed. Python 3.13.14; `compileall` over the required
surface passed; `git diff --check` passed. No data purchase, QuantConnect
access, broker access, scheduled-task change, deployment, epoch action, or
operational database mutation occurred. ACER remains a DRAFT and ACER-0
remains the owner's decision.

## 7by. Benzinga vendor data audit: read-only, snapshot A complete (2026-08-20)

Branch `user/claude/acer1-benzinga-audit-20260820` (stacked on the 7bx
follow-ups branch, since both touch this file). Owner authorized the
subscription purchase and a strengthened read-only audit; the key is the
`MASSIVE_API_KEY` user environment variable (verified set, length only — the
value appears nowhere). Record:
`docs/research/BENZINGA_RATINGS_2026-08-20_DATA_AUDIT.md`. Tool:
`scripts/audit_benzinga_ratings.py` with refusal-direction tests
(`tests/test_benzinga_ratings_audit.py`, 4 tests, both refusal mutations
verified red then restored from a committed restore point).

**Snapshot A**: 587,046 rows, 2011-12-08 → 2026-08-20, 596 pages, 399 MB,
every yearly partition naturally terminated, per-page SHA-256s in the
manifest, stored under gitignored `artifacts/benzinga_audit/
benzinga-ratings-20260820T233055Z` (immutable; the tool refuses to overwrite
a snapshot and refuses hash mismatches and incomplete snapshots at analysis).

**Findings, condensed** (full detail in the audit record):

- **Delisted coverage PASSES** — the decisive question. SIVB (240 rows to
  2023-03-13), FRC (207 to 2023-04-26), SBNY, TWTR, ATVI, and 15 more
  acquired/bankrupt names carry pre-delisting rating history. This does not
  prove every action since original listing is present. OTC
  `-Q` successors are absent (acceptable; outside any investable universe).
- **Rename/reuse hazard, the audit's most important defect find:** FB has 0
  rows (history re-keyed to META) while ANTM kept its history — opposite
  handling of two renames; BBBY merges the dead retailer with the Beyond
  Inc. reuse under one symbol; FISV rows begin 2025-12. Ticker-keyed joins
  are unsafe across renames; ACER must join through a security master with
  reuse boundaries. The Massive delivery contains neither ISIN nor exchange,
  so company name and ticker are cross-reference inputs, not identity keys.
  QC symbol-mapping cross-reference remains open.
- `previous_rating` missingness (44%) is structural — 100% of initiations,
  correctly — and the transitions ACER uses are ~99% complete on upgrades
  and downgrades. Zero duplicate `benzinga_id`. 46 inconsistent transitions
  (0.008%) become a named refusal class.
- **Timezone convention is evidenced, not vendor-confirmed:** modern `time`
  offsets look like Eastern. [Corrected by the 2026-08-20 counter-review,
  section 7ca: delivered `last_updated` values are **all ISO-8601 `Z`**
  (587,046 of 587,046 measured on the raw bytes), not timezone-naive as this
  section previously said; the naive-looking example was a culture-rendered
  display artifact.] ACER still uses no intraday timestamp: every action
  becomes eligible next session after the later action/update date, a rule
  kept for its conservatism. Correct date parsing finds 557,748 same-date,
  29,259 later-date, and **39 reverse-order** records; the latter are
  refused. The earlier text comparison falsely reported zero negative gaps.
- Disclosed data limitations: 2017 rows are ~35% below neighbouring years;
  the distinct-firm count declines 265 → ~120-150 across the history.
- **Licence wording separated correctly:** the owner is right that the
  all-caps text is an investment-advice disclaimer, not a strategy-testing
  prohibition. Separate preserved Market Data clauses still restrict
  non-display/derived-work use and third-party transfer unless the
  dataset-specific entitlement changes that default. The local personal
  structural audit may continue. Raw or reconstructable ratings stay off QC
  until the order terms or written permission cover that upload; otherwise
  use local LEAN. Retention/deletion obligations must be taken from the
  governing dataset-specific terms rather than declared unambiguous while
  their applicability is unresolved.

The three governing ToS pages are preserved raw and hashed under
`artifacts/benzinga_audit/tos-20260820/` (a gap the owner exposed by asking
where the licence quotes came from: the first citation rested on a
summarizing fetch, below this project's bar for load-bearing text; every
quoted clause is now re-verified against the preserved bytes).

Open items: snapshot B restatement diff (compare by stable `benzinga_id`);
dataset-specific permission before any raw/reconstructable upload to QC; QC
symbol-mapping cross-reference with ambiguity refusals. No backtest, no price
join, no research look, no ledger entry: this was a data audit under the
owner's explicit read-only instruction.

Validation on the final tree: full suite **4,357 passed / 0 failed / 25
warnings** in 912.13 seconds (4,353 prior tests plus this round's four
refusal tests), run on the complete code and prose before this validation
sentence and the ToS-preservation paragraphs were added; the focused
document/contract suites and the new audit tests reran on the final prose.
Python 3.13.14; `compileall` over the changed surface passed;
`git diff --check` passed.

## 7bz. Independent review of the ACER-1 Benzinga audit (Codex, 2026-08-20)

Exact pushed source:
`origin/user/claude/acer1-benzinga-audit-20260820` at
`35efda1b6f477eba697c99c76e665016792c0c9a`, base `8f681f9`, ordered range
`13e8081`, `062f27f`, `eec4823`, `35efda1`. Review branch:
`codex/review-acer1-benzinga-20260820`. Full record:
`docs/Archive/Review/REVIEW_2026-08-20_ACER1_BENZINGA_AUDIT.md`.

Disposition: `13e8081` accepted; `062f27f`, `eec4823`, and `35efda1`
accepted after correction. No P0/P1 issue. Six P2s were confirmed: the
analysis did not authenticate the manifest or its row-count graph; comparison
could hide blank/duplicate IDs; incompatible timestamp formats were compared
lexically; a timezone-naive update field was treated as unambiguous UTC; the
licence correction overreached from an advice disclaimer to unsupported QC
upload permission; and the delivered rows lack an issuer identifier (zero
ISIN/exchange fields). One P3 final-validation-order issue is closed by this
review.

Product/test correction `2274691` verifies the manifest before trusting it,
validates page and partition structure/counts, refuses unsafe or duplicate
page references, refuses missing/duplicate comparison IDs, parses the two
observed update formats, and reports issuer-identity missingness plus
timezone-neutral update-date facts. Snapshot A reread cleanly under these
checks: 587,046 rows; 557,748 same-date updates; 29,259 later-date updates;
**39 update dates preceding the action date**; 22,582 more than 90 days
later; zero ISIN and exchange values; 17 missing company names.

The frozen safe ACER timing rule is now next-session eligibility after the
later action/update date for every row and era; the 39 reverse-order records
are refused. Raw or reconstructable ratings remain machine-local unless the
dataset-specific terms or written permission expressly permit upload to QC;
local LEAN is the fallback. Snapshot B and an ambiguity-refusing
security-master/QC mapping remain open. No price join, backtest, research
look, API call, broker access, deployment, scheduled-task change, or
operational mutation occurred. ACER-1 and ACER-0 are not complete.

The review branch and its commits are **local-only** until the owner
authorizes a push. Another computer cannot fetch this review yet. Final test
counts: focused audit/document suites **45 passed**; full suite after all
substantive corrections **4,362 passed / 0 failed / 25 warnings** in 921.00
seconds; Python 3.13.14; full required `compileall` passed. After inserting
these counts, the focused 45 reran on the final prose; `git diff --check`,
staged-content inspection, ordered-commit inspection, and shared-checkout
branch/HEAD verification passed. The 25 warnings are one third-party
`websockets` legacy deprecation and 24 Joblib/NumPy shape deprecations.

## 7ca. Counter-review of Codex's audit correction (Claude, 2026-08-20)

Scope: Codex's correction commits `2274691`, `9dcd54f`, `0f3e0a4`, which the
owner merged to `main` via PR #288 (merge `7ab2f80`). This supersedes 7bz's
closing status note, which was written before the owner authorized that
merge: the review is now published and fetchable from any machine.
Branch: `user/claude/acer1-audit-counterreview-20260820` off that merge.
Full record: `docs/Archive/Review/REVIEW_2026-08-20_ACER1_AUDIT_COUNTERREVIEW.md`.

What was verified, against the immutable Snapshot A raw bytes and by running
the corrected tool end to end:

- **ACER1R-001/002/006 confirmed exactly as written.** The hardened loader
  authenticates `manifest.sha256`, page structure, and the page/partition
  row-count graph, and passes end to end on the real snapshot; comparison
  refuses blank/duplicate identities; `isin` and `exchange` are not merely
  empty — the keys do not exist on any of the 587,046 rows.
- **ACER1R-003's counts reproduce exactly** by independent reparse:
  557,748 same-date, 29,259 later-date, 39 reverse-order, 22,582 more than
  90 days later. The original "zero negative gaps" claim was indeed false.
- **CCRV-001 (P2, fixed this round): ACER1R-004's factual premise is
  false.** A byte-level census finds **all 587,046 `last_updated` values are
  ISO-8601 `Z`** — zero legacy `MM/DD/YYYY` values, zero missing. The
  review's naive example `10/09/2023 12:28:43` matches how PowerShell's
  `ConvertFrom-Json` culture-renders a `Z` timestamp; it is a display
  artifact, not wire format. The review's stated defect mechanism for
  ACER1R-003 (mixed-format lexical comparison) therefore cannot occur in
  this payload; the real original defect was never counting the
  before-direction at date level plus trailing-`Z` inflation. The frozen
  date-level next-session rule is **kept** — it stands on conservatism, not
  on the naive-format premise — and the era-split offset measurement is
  restored to "strong internal evidence, not vendor-confirmed". Corrected in
  the audit record §5, the action plan, and section 7by above.
- **CCRV-002 (P3, fixed this round):** the parser docstring claimed legacy
  timestamps were "observed"; none exist in Snapshot A. Reworded as
  defensive parsing; the behavior and its test are unchanged.
- **New measurement:** each of the 39 reverse-order rows has `time` matching
  the update instant's US-Eastern wall clock within 25 seconds to ~9 minutes
  while `date` sits one day after the update's UTC date — a systematic
  next-day-dating anomaly. Refusal remains the right handling.

ACER1R-005 (keep raw/reconstructable data off QC until dataset-specific
permission exists; local LEAN fallback) is a boundary judgment, not a
factual claim, and is accepted unchanged. ACER1R-007 stays closed. No
regression test pins CCRV-001 because the falsehood is about machine-local
snapshot bytes CI cannot see; the audit record now carries the reproduction
method instead. No API call, price join, backtest, research look, or
operational mutation occurred in this round.

Validation on the final tree: full suite **4,362 passed / 0 failed / 25
warnings** in 587.56 seconds (the same third-party `websockets` and
Joblib/NumPy deprecations as 7bz); focused audit + document-consistency
suites reran green on the final prose after these counts were inserted;
Python 3.13.14; full required `compileall` passed; `git diff --check`
passed. One instructive intermediate failure: the first full run failed
`test_no_document_calls_a_merged_commit_unreachable` because this section's
draft quoted 7bz's reachability phrase within range of a merged hash — the
guard behaving exactly as designed; the prose was reworded rather than the
guard weakened.

## 7cb. ACER analyst-event backbone built (Claude, 2026-08-20)

Branch: `user/claude/acer-event-backbone-20260820`, off `1c110d6`. Full
measurement record:
`docs/research/ACER_EVENTS_2026-08-20_BACKBONE_COVERAGE.md`.

Scope: **data plumbing only.** Verified vendor snapshot in, canonical
event dataset out. No price join, no outcome, no ranking, no signal, no
network call, no research look, no `R-nnn` entry, and no ACER milestone
completes. ACER-0 remains unfrozen and this code deliberately contains
nothing that would pre-empt it.

New `research/acer/` package:

- `snapshot.py` — the **single authoritative** snapshot-verification rule,
  consolidated out of `scripts/audit_benzinga_ratings.py` (whose hardened
  checks came from ACER1R-001/002). The audit script now delegates to it and
  re-raises `SnapshotError` as `SystemExit`, so its CLI messages and its
  existing tests are unchanged. Two copies of "what makes a snapshot
  trustworthy" could have drifted apart; now there is one.
- `normalize.py` — vendor rows to `NormalizedEvent`, with every excluded row
  becoming a named `Refusal`. Implements the frozen rule
  `available_date = max(action_date, last_updated UTC date)` at **date
  level**, and deliberately derives **no** UTC action timestamp: the
  Eastern reading of `time` is measured but not vendor-confirmed, and the
  frozen rule does not need it. Rating strings stay unmapped because the
  scale is an ACER-0 decision.
- `dataset.py` — content-addressed immutable persistence through
  `ml.immutable_io.publish_immutable_bytes`, plus the coverage summary.
  Refusals are hashed into the dataset identity, so a build that quietly
  started discarding rows cannot produce an identical-looking dataset.

`scripts/build_acer_events.py` runs it. Measured on Snapshot A: **587,046
input rows to 584,916 events, 99.64% retention**, 2,130 named refusals
(2,008 missing rating, 46 inconsistent transition, **39 reverse-order**, 37
missing firm), 9,677 distinct tickers, 507 distinct firms, and **29,187
events (4.99%) whose availability defers past their action date** — the
measured price of the conservative rule. Dataset
`acer-analyst-events-19c9d8e0b00da299`, written under gitignored
`artifacts/acer_datasets/`; a rebuild is an idempotent no-op returning the
same id.

**The headline is not the 99.64%.** Row usability is not readiness. Issuer
identity is still unresolved: 9,677 tickers, zero ISIN, zero exchange, and
the FB/ANTM/BBBY hazard intact. That number is the size of the security-master
problem ACER-2 must solve before any price join, and it is the reason this
milestone stops here.

`tests/test_acer_normalization.py` (39 tests) covers the availability
boundaries (including a non-UTC offset that would defer a day if honoured
and not if truncated), every refusal class, caller-mutation, deterministic
ordering, dataset immutability and tamper detection, and three AST
invariants: the package may not import authority or outcome code, may not
make a network call, and may not hard-code a rating scale. Five mutations
were applied and all five were detected — collapsing availability to the
action date (4 failures), accepting reverse-order rows (1), tracking
duplicate ids only for accepted rows (1), assuming a naive `last_updated`
is UTC (2), and keeping inconsistent transitions (11) — with the source
restored from a backup copy in a `finally` block.

Validation on the final tree: full suite **4,401 passed / 0 failed / 25
warnings** in 670.50 seconds — 4,362 prior tests plus this round's 39, with
the same third-party `websockets` and Joblib/NumPy deprecations as earlier
rounds. Focused ACER + audit + document suites reran green after these
counts were inserted. `compileall` over the full required surface plus the
new `research/` package passed; `git diff --check` passed. Python 3.13.14.

One process note worth carrying forward: an earlier full run on this branch
was stopped and discarded rather than recorded, because the draft parked a
validation-placeholder token in this section — the exact pattern
`test_current_review_documents_have_no_validation_placeholders` forbids, and
it fails on any occurrence, including one written only to describe itself.
The fix is the ordering this repository already settled on: finalize the
prose carrying no token at all, run the suite green, then insert the
measured numbers and rerun the focused suites.

Untested surface, stated plainly: the backbone has been exercised against
exactly one real snapshot. Restatement behaviour across two snapshots is
untested until Snapshot B exists, and no test covers a vendor payload whose
`last_updated` format differs from Snapshot A's uniform ISO-8601 `Z`.

## 7cc. ACER event-backbone independent review (Codex, 2026-08-20)

Exact submitted snapshot: pushed
`origin/user/claude/acer-event-backbone-20260820` at
`b8c46ce3c5b747ff4825ddb293ddfb526c1b684e`, one commit after base and
merge-base `1c110d663d23455ebd7d4cfc0420b20ac01affe1`. Disposition:
**accepted after correction**. Review branch
`codex/review-acer-event-backbone-20260820` was local-only when this section
was written; it has since been counter-reviewed (section 7cd) and merged, and
the branch is deleted. Product/test
correction `61abd6aeb8b2889bf9943b97af8224cd49a8c2d0` and
review/documentation `aea84f4cc017f6e6a31091dee388c55b3e9b07fc` are committed
separately; this section is the final handoff commit. Full record:
`docs/Archive/Review/REVIEW_2026-08-20_ACER_EVENT_BACKBONE.md`.

No P0/P1 issue. Six P2s and one P3 were confirmed. The original normalizer
kept the first valid occurrence of a duplicated vendor id; the identity
loader authenticated only content blobs while accepting forged lineage,
counts, contract version, and dataset id; the diagnostic
`--allow-incomplete` override could publish a canonical dataset; rows and
the recorded source-manifest hash came from two separate manifest reads;
the `eastern_action_time_era` label overstated vendor-confirmed semantics;
the public persistence boundary trusted caller order and allowed duplicate
event ids; and directional no-change detection was case/whitespace-sensitive.
All are corrected and regression-pinned. Firm-specific punctuation aliases
remain deliberately unmapped for ACER-0.

The corrected dataset contract is v2. Read-only normalization of Snapshot A
reproduced the same substantive coverage — 587,046 rows to 584,916 events
and 2,130 refusals, 29,187 deferred beyond action date, 9,677 tickers, and
507 firms — so no result or research claim changes. Contract hardening and
the honest era label correctly change the derived identity to
`acer-analyst-events-b06de2e5c03fdf5e` (content
`b06de2e5c03fdf5e2e096e2b3abeeb337f7c68ee786ec65af38c233cd090b6e8`,
events
`e46b5e508eab896215ccca5a9b50ea289a8ca3cd4094a24e64f51b6ede2632c5`,
refusals unchanged at
`469493672fb38497ed5ad326849c4005c9f213ec24db2cde34a5e6a92087f3c2`).
The old machine-local v1 dataset
`acer-analyst-events-19c9d8e0b00da299` is superseded and must not be used.
The corrected v2 identity was derived in memory only; no licensed dataset
was written during review. Materialize it only after counter-review.

Validation on the corrected tree: focused ACER + audit **61 passed**;
focused plus active-document consistency **97 passed**; full suite **4,414
passed / 0 failed / 25 known third-party warnings** in 900.40 seconds under
Python 3.13.14; required `compileall`, including `research/`, passed; and
`git diff --check` passed. Final read-only fetch confirmed the submitted
remote still exactly `b8c46ce3c5b747ff4825ddb293ddfb526c1b684e`; ordered Codex
commits were inspected; immediately before this handoff commit the only
working-tree change was `docs/SESSION_HANDOFF.md`.

The shared checkout remained on
`user/claude/acer-event-backbone-20260820` at exact `b8c46ce`; Codex used an
isolated worktree. No API/network call, price join, backtest, research look,
broker access, deployment, task change, or operational mutation occurred.
This is still partial ACER plumbing, so no feature-milestone entry is added.
The next gate remains counter-review, then ambiguity-refusing issuer mapping;
Snapshot B, ACER-0 freeze, control data, and licence boundaries remain open.

## 7cd. Counter-review of the backbone review (Claude, 2026-08-20)

Branch: `user/claude/acer-backbone-counterreview-20260820`, based on Codex's
`06333ec`. Full record:
`docs/Archive/Review/REVIEW_2026-08-20_ACER_BACKBONE_COUNTERREVIEW.md`.

**All seven of Codex's findings are confirmed.** The two with the largest
blast radius were reproduced empirically against my own original code rather
than accepted from the write-up: loading `normalize.py` from `b8c46ce` as a
standalone module and feeding it two valid rows sharing one id returned **1
event and 1 refusal**, confirming ACERBR-001's silent first-row authority;
feeding it a downgrade from `" Buy "` to `"buy"` returned **1 event**,
confirming ACERBR-007. My own duplicate test had covered only the
refused-first case, which is exactly why the accepted-first path survived.

Independent identity reproduction from Snapshot A matched Codex's claimed
hashes exactly. One byproduct is worth keeping: the corrected refusals blob
hashed **identically to the v1 build**, which independently proves the more
permissive transition comparison added no refusals here and that the 46-row
count is unchanged.

Two defects were found in the corrections and fixed this round. **CCBR-001
(P3):** `build_identity` validated its lineage inputs' emptiness and format
but not their type, so a non-string raised a bare `AttributeError` — a
boundary that authenticates on read but crashes on write is half a boundary.
**CCBR-002 (P3):** after the transition comparison became case- and
whitespace-insensitive, the refusal detail still read
`previous_rating == rating == 'x'`, asserting a textual equality the check
no longer requires and discarding the values an investigator needs. Refusal
details are serialized into the frozen dataset, so that is an evidence
defect rather than a message. **CCBR-003 (P3, recorded only):**
`load_identity` requires an exact contract-version match, so a future bump
would make earlier datasets unverifiable by our own tooling — correct for
consumption, but a future bump should decide deliberately whether
verification-only reads of older versions are needed.

Because CCBR-002 changes the refusals blob, the dataset identity moves to
`acer-analyst-events-73c36f9de1841b0a` (content hash `73c36f9de1841b0a…`,
refusals `0c862521…`); the events blob is byte-identical to Codex's
`e46b5e50…`. Coverage numbers are unchanged: 584,916 events, 2,130 refusals,
99.64% retention. **The dataset is still not materialized** — this identity
was computed in memory. The superseded v1 directory
`acer-analyst-events-19c9d8e0b00da299` is deliberately left on disk rather
than deleted: it is the only copy of a superseded artifact whose producing
code no longer exists, and `load_identity` refusing it on contract version
is the enforcement.

I also accepted Codex's correction to my prose claiming the date-level rule
"costs the study nothing measurable in sample size" — I had measured rows,
not signal, and the corrected wording says so.

Validation on the final tree: full suite **4,417 passed / 0 failed / 25
warnings** in 716.37 seconds — Codex's 4,414 plus this round's one new test
and two added parametrized cases. Focused ACER + audit suites: 64 passed.
Document-consistency guards were rerun green after every documentation edit,
including after these counts were inserted; no code changed after the full
run began. `compileall` over the required surface including `research/`
passed; `git diff --check` passed; Python 3.13.14. The two new tests were
mutation-checked: reverting the refusal detail to the equality wording and
removing the type guard each turn their test red, and both sources were
restored from backup copies in a `finally` block.

A process note against myself: the first draft of this section contained a
full-suite count and a runtime that had not been measured — the count was a
prediction and the timing was invented. Both were removed before any run was
recorded, and the real count differs from the predicted one, which is the
whole reason the rule exists. A validation record must be transcribed from a
completed run, never anticipated.

No API call, network access, price join, backtest, research look, broker
access, deployment, task change, or operational mutation occurred. No ACER
milestone completes and no feature-milestone entry is added. Remaining
gates are unchanged: ambiguity-refusing issuer mapping, Snapshot B, the
ACER-0 freeze, the earnings-control dataset, and dataset-specific permission
before any reconstructable-data upload to QuantConnect.

## 7ce. ACER-0A partial freeze and two read-only measurements (Claude, 2026-08-20)

Branch: `user/claude/acer0a-freeze-20260820`, off `b58947e`. The owner issued
ten decisions; this round records them and performs the two read-only
measurements they authorized. **No purchase, price join, outcome access,
backtest, upload, or ACER-2 run occurred, and nothing operational was
changed.**

**The freeze is split, and that is the substantive decision.**
`docs/research/ACER_2026-08-20_ACER0A_FREEZE.md` freezes the owner's decisive
stock-level choices, but not yet an executable ACER-2 preregistration;
ACER-0B — ETF benchmark and investability choices — stays deliberately
unfrozen so they are not forced before a stock-level signal is shown to
exist. ACER-3's run budget is **zero** until the owner separately freezes
ACER-0B.

ACER-2 is **six cells, not twelve**: two encodings x three half-lives (21,
63, 126 sessions) x one coverage-neutral per-firm mean x one 21-session
horizon. Raw sum was cut as a second aggregation because it mainly rewards
analyst coverage. Primary cell named in advance (notch change, 63 sessions),
primary statistic out-of-sample residualized cross-sectional IC, expected
sign frozen positive, threshold Bonferroni **0.05/6** applied to the primary
cell itself — deliberately more conservative than testing a designated
primary at 0.05. Secondary cells are descriptive only. A null primary closes
ACER with no post-result tuning. Budget: unlimited synthetic tests that never
touch real outcomes, one development execution, one confirmation execution;
corrected reruns may repair code but never the hypothesis, and each is still
a counted look. Stock universe frozen point-in-time with named refusals; ETF
thresholds deferred. Local LEAN is authoritative and reconstructable Benzinga
rows stay off QuantConnect absent explicit permission evidence; QC access is
read-only symbol mapping only. Control data has a **candidate, not an
adoption**: the Benzinga Earnings expansion, $99 for a one-month structural
audit against eight criteria, with `eps_surprise_percent` distrusted and our
own standardized-surprise formula frozen afterwards.

**Ten items are named as still-open (ACER-0A.1–0A.10) and must close before
the single development run.** The one I want the next reader to notice is
ACER-0A.1: the owner's condition that the result "must not be driven by one
year, sector, or a small number of securities" is frozen in principle but
carries no number, and an unquantified robustness condition is decided while
looking at the result — the exact failure the freeze exists to prevent. The
document proposes a concrete rule (leave-one-year-out, leave-one-sector-out,
and removal of the top 1% of contributing securities, each retaining sign and
significance) and explicitly marks it as **awaiting owner confirmation rather
than frozen**, because inventing the threshold silently would be the defect.
The other items include the surprise formula, value source, local data
inventory, exact rating scale and signal construction, all control/outcome
formulas, estimation/significance and split protocol, error-slot and
confirmation rules, and point-in-time universe semantics. Also flagged: a
one-month audit subscription that is then cancelled re-raises the
deletion-on-termination question, so an evidence snapshot may not outlive it.

**SBR-1 measured absent** (`docs/operations/OPERATIONAL_FACTS.md`): the
`TradingAgent-StrongBuy-Capture` task is not registered, no task matching
StrongBuy/Capture/Ratings exists, and zero `snapshot-*.jsonl` files or
capture manifests exist under any plausible root. The capture's output
directory is caller-supplied at install time, so the search was by artifact
filename rather than by a single default path. The closure now rests on a
measurement instead of on absence of repository evidence. Nothing was
installed or running, so there was nothing to stop for.

**At the recorded read-only instant, both reconciliation alerts were stale
state rather than a live mismatch**
(`docs/Archive/Operations/RECONCILIATION_ALERTS_2026-08-20_DIAGNOSIS.md`). Seven of
22 long reconciliation gaps match a Windows sleep window exactly; 15 were
not correlated. The paper tasks are registered `WakeToRun=False`, while
`StartWhenAvailable=True` queues missed time-based starts for catch-up. Both
alerts carry `matched=True, mismatches=0, errors=0`, and 20 clean
reconciliations have completed on a 10-minute cadence since the last failure
at 02:49Z. Nothing was acknowledged, closed, altered, or repaired. The
recommendation is to acknowledge (owner action), decide deliberately about
sleep or `WakeToRun`, and **not** loosen the 30-minute or 5-minute
thresholds, which are real execution-readiness gates.

**A correction I owe the record:** earlier in this session I twice reported
epoch-006 as having "11 observations". That was the all-epoch total. Per
epoch: 001=1, 002=1, 003=1, 004=3, 005=3, **006=2** — one for each trading
session since the epoch opened, so nothing is missing, but the epoch is 2 of
its required 60, not 11.

**Overlay tasks closed as a byproduct.** The outstanding proof — the first
*automatic* firing after the Interactive reinstall — succeeded: Observe
14:45, Mature 14:55, Sufficiency 15:05 local on 2026-08-20, all
`LastTaskResult=0`, with the operational `shadow_overlay.db` unchanged at 1
registration / 1 baseline observation / 0 outcomes. `OPERATIONAL_FACTS.md`
and the action plan previously described this as pending.

Validation on the final tree: full suite **4,417 passed / 0 failed / 25
warnings** in 677.78 seconds, unchanged from the previous round because this
round changed no code. `compileall` over the required surface including
`research/` passed; `git diff --check` passed; Python 3.13.14. The
document-consistency guards were rerun green after every edit, including
after these counts were inserted.

One guard finding worth recording, because it was a real staleness and not a
false positive: `test_no_document_calls_a_merged_commit_unreachable` failed
on this branch. Section 7cc and the resume prompt still described Codex's
review branch, and the product-correction commit it names, as unreachable —
which stopped being true when the owner merged PR #290. Both places were
corrected to say the branch had that status when written and has since been
merged and deleted. The guard was not weakened, and it fired twice here: the
first draft of this very paragraph reproduced the pattern by quoting the hash
beside the claim it was describing.

## 7cf. Independent ACER-0A freeze review (Codex, 2026-08-21)

Exact submitted remote: `origin/user/claude/acer0a-freeze-20260820` at
`3a98fefb0808e4e9e4b3bc185ee59c12b1449bac`, based on and merge-based at
`b58947e589c6fa92ed498f57f68ba0590048303f`. The range contained exactly one
commit, which is **accepted after correction**. Full report:
`docs/Archive/Review/REVIEW_2026-08-20_ACER0A_FREEZE.md`.

Review branch: `codex/review-acer0a-freeze-20260820`. Ordered Codex commits
before this handoff are:

1. `edc0612` — correct the ACER-0A freeze, operational scheduler facts and
   active-document regression guards;
2. `08955d6` — record the independent review and corrected action-plan state;
3. this separate handoff commit (the branch tip).

The owner authorized exactly one final push after all work completed. This
branch is intended to be published once to
`origin/codex/review-acer0a-freeze-20260820` for Claude's counter-review; the
final reviewer report must verify the exact remote head. No intermediate push
was made.

**Findings:** two P2 research-governance issues, one P2 operational-fact issue
and one P3 active-document consistency issue were confirmed and resolved.
The submitted record called ACER-0A frozen even though outcome-sensitive
signal, control, residualization, fold, significance, date-split,
confirmation and point-in-time membership choices remained open. Its one-plus-
one run budget also failed to say what happens when an error/refusal consumes
a slot. The alert diagnosis generalized seven checked sleep gaps to all 22
and incorrectly described a missed timed task as skipped despite installed
`StartWhenAvailable=True`; Microsoft and the installer say it is queued for
catch-up. Active plan sections also retained pre-measurement SBR and
pre-purchase ratings claims.

**Correction:** the owner's selected values remain frozen, but ACER-0A is now
accurately labelled a **partial decision freeze, not an executable
preregistration**. ACER-0A.1–0A.10 must all close before any real
signal/outcome join. The run slots are provisional and cannot be replaced or
expanded until the owner freezes the error/refusal and confirmation rule. The
operational record now says seven of 22 gaps were correlated, distinguishes
`WakeToRun=False` from `StartWhenAvailable=True`, and describes catch-up as
conditional: it may capture the same session or refuse/no-op after the
session/freshness boundary. No operational setting or row changed.

Independent validation on the final corrected tree: focused documents/task/
paper-evidence tests **59 passed in 8.77s**; full suite **4,420 passed / 0
failed / 25 warnings in 834.29s** on Python 3.13.14; required `compileall`
including `research/` passed; `git diff --check` passed. Read-only task and
SQLite `mode=ro` checks confirmed the installed settings, submitted alert
payloads and epoch counts. No QuantConnect, Massive/Benzinga or broker API
was accessed; no outcome, signal, licensed row, run or research look was
consumed. Application/execution code did not change, so paper mode, approvals,
kill switch and broker lifecycle were out of scope rather than re-proven.

## 7cg. Counter-review of the ACER-0A review (Claude, 2026-08-21)

Branch: `user/claude/acer0a-cr-issuer-mapping-20260821`, based on Codex's
`e9eb120`. Full record:
`docs/Archive/Review/REVIEW_2026-08-21_ACER0A_COUNTERREVIEW.md`.

**All four findings confirmed.** ACER0AR-001 is the most serious defect found
against my work in this program: I labelled a document a freeze while its
**primary encoding was not computable**. "Ordinal rating-notch change" is the
designated primary cell, and no notch scale exists in the freeze, the ACER
plan, or the code — `tests/test_acer_normalization.py` actively forbids one
pending ACER-0. I had written that guard myself, so I knew the scale was
undecided, and still froze a primary cell that depended on it. The same hole
covers residualization form, Pearson-versus-Spearman IC, folds and purge, and
period boundaries. Reclassifying to a partial decision freeze with
ACER-0A.5–0A.10 is the honest shape.

ACER0AR-003 was verified by fresh measurement rather than accepted: there are
**four** `TradingAgent-Paper-*` tasks, not the three I wrote a completeness
claim about; `PaperObservation` carries `DaysOfWeek=62` (Mon–Fri) with a
16:30−07:00 boundary, confirming the corrected "weekdays at 23:30Z"; and
`OperationsCycle` repeats at `PT10M`. My worse error was rhetorical: the
diagnosis document disclosed that only 7 of 22 long gaps were inspected, and
then my handoff and action-plan summaries asserted that *every* long gap
matched a sleep window — the caveat was dropped exactly where the claim got
stronger. I had also written that a firing inside a sleep window is "skipped
rather than deferred" while quoting the `StartWhenAvailable=True` setting
that queues missed starts.

**One residual defect fixed (CCR0A-001, P3):** the ACER0AR-002 correction
left two adjacent bullets in contradiction — one describing how "a corrected
rerun may repair code", the next saying the section does not authorize a
third corrected run. With exactly two slots, any corrected rerun *is* a third
run. Rewritten to say plainly that none is authorized now, and that the
listed constraints would apply only if the owner authorizes one under
ACER-0A.9.

**One item surfaced without change (CCR0A-002):** Codex relabelled a document
the owner explicitly called "the ACER-0A freeze" to "PARTIAL FREEZE". I agree
with the substance and left it, because no owner decision was weakened and
the frozen decisions remain binding — but a reviewer changing the label on an
owner act should be visible to the owner rather than discovered later.

Codex's three new guards were mutation-tested and all three detect their
regression. I also checked specifically that the scheduler guard's predicate
is true — the installer does contain `-StartWhenAvailable` — because a
conditional guard whose predicate is false is a green test that verifies
nothing.

**Standing workflow note:** per the owner's 2026-08-20 instruction this
branch carries the counter-review *and* the next feature, against
`CLAUDE.md` sections 3 and 11 which ask for one milestone per branch. That is
the owner's explicit instruction, recorded here so a reviewer reads it as
intent rather than drift; the two are kept as separate commits so each can
still receive its own disposition.

## 7ch. Issuer-identity ambiguity detector (Claude, 2026-08-21)

Same branch as 7cg, per the owner's relay instruction. Full record:
`docs/research/ACER_2026-08-21_ISSUER_IDENTITY_MEASUREMENT.md`.

**A hard blocker was found before any code was written, and it needs an
owner ruling.** The named next ACER-1 step is an ambiguity-refusing security
master join, authorized in owner decision 8 as read-only QuantConnect
symbol-mapping work. Neither half of that path exists on this host:

- **No local LEAN and no LEAN data.** `C:\Lean`, `C:\git\Lean` and
  `C:\ProgramData\QuantConnect` are absent, and no `map_files` directory
  exists anywhere under `C:\git`. Owner decision 9 makes local LEAN
  authoritative; there is no local LEAN. Open item **ACER-0A.4 now has a
  negative answer, not an unmeasured one.**
- **The QC client cannot reach data endpoints by design.**
  `research/quantconnect.py` allowlists only `projects/`, `files/`,
  `compile/`, `backtests/`, `optimizations/` and `authenticate`, with a
  comment stating the rule exists so `data/read` "cannot sneak through".
  That is a reviewed control; widening it is an owner decision, not a
  refactor, so I did not touch it.

So I built the half that needs no external data: `research/acer/identity.py`
measures which tickers carry evidence that a raw-ticker join is unsafe, from
the audited corpus alone. Measured over Snapshot A: **2,885 of 9,677 tickers
(29.8%) flagged, covering 35.7% of events** — 2,478 with multiple company
names (1,981 rename-shaped, 497 reuse-shaped after a ≥365-day gap), 600
sharing a name with another ticker, 766 interleaved, 9 unnamed.

Most of that is cosmetic vendor label churn — `Amazon`→`Amazon.com`,
`McDonalds`→`McDonald's`, `SVB Financial Group`→`SVB Finl Gr`. The detector
compares case and whitespace only and deliberately does **not** alias
punctuation or corporate suffixes, because deciding two spellings are one
issuer is a security-master decision of the same class as the rating scale.
The count is reported as measured rather than tuned down by loosening the
comparison; the decision-relevant subsets are the 497 reuse-shaped flags and
the 600 cross-ticker collisions.

Genuine finds: **GOOG and GOOGL both carry `Alphabet`**; **FISV and FI both
carry `Fiserv`** with FISV starting 2025-12-22 (the predicted re-keying); and
a real vendor defect — **CPRI carries one event labelled
`Chipotle Mexican Grill`** on 2026-02-04 between two `Capri Holdings` eras,
found only because interleaving is detected rather than smoothed over.

**The result that matters most is negative: this detector misses BBBY.** The
vendor labels all 270 BBBY events `Bed Bath & Beyond` from 2012 through 2026,
including events after the 2023 bankruptcy when the symbol was reused by an
unrelated issuer. It never relabels, so no name signal exists and the
submitted detector reported BBBY as *unambiguous* — a false negative on the
exact hazard that motivated the work.
Two consequences: the 2,885 flags are a **lower bound**, and an unflagged
ticker is not established as safe; and an external security master with
listing/delisting dates is **required**, not a better heuristic. That makes
the blocker above load-bearing. The limitation is pinned by
`test_a_reuse_the_vendor_never_relabels_is_NOT_detected` rather than left in
prose.

Validation on the final tree: full suite **4,439 passed / 0 failed / 25
warnings** in 662.25 seconds — 4,420 from the reviewed tree plus this round's
19 identity tests. `compileall` over the required surface including
`research/` passed; `git diff --check` passed; Python 3.13.14. Five mutations
of the detector were applied and all five were detected: aliasing punctuation
in the name comparison, dropping the cross-ticker refusal, swapping the
reuse/rename labels, ignoring unnamed events, and dropping interleaving
detection. The source was restored from a backup copy in a `finally` block.

Untested surface, stated plainly: the detector has been exercised against one
snapshot and synthetic cases only. Its false-negative class is characterized
but not bounded — nobody knows how many BBBY-shaped reuses exist, because
finding them is precisely what needs the security master this host lacks.

**Independent-review correction:** section 7ci supersedes this section's
safety-shaped `unambiguous` verdict, detachable refusal-list output, and
order-sensitive 766 interleaving count. The submitted measurement remains
historical evidence; it must not be used as an eligibility boundary.

## 7ci. Independent review of the issuer-identity diagnostic (Codex, 2026-08-21)

Codex reviewed exact pushed range
`e9eb12010c317df9cedcb610c50e1375531404e1..703693bc43b62c7f6f23ed5c42e0a4f7a99b278c`
from `origin/user/claude/acer0a-cr-issuer-mapping-20260821`, including both
submitted commits in order. Commit `7b56e10` is **accepted**. Commit
`703693b` is **accepted after correction**. The durable review record is
`docs/Archive/Review/REVIEW_2026-08-21_ACER_ISSUER_IDENTITY.md`, committed with the
corrected active research status at
`d248e0ec5b19f23512e1b820d8d23c5fb397c5b9`.

The review closed four findings. Three were P2: the absence of name evidence
was mislabeled `unambiguous` and exposed through a bare refusal-list export;
the report discarded source/code/result lineage while the shared clean-code
helper omitted ignored Python under `research/`; and ticker case could split
one symbol into two assessments. One P3 made same-day interleaving dependent
on vendor/caller row order and described every sub-365-day change as having
no gap. Correction commit
`1805ec7b96bc62afd6c1f6019ec68b9b8f9587f5` replaces the verdicts with
`name_based_ambiguity_evidence` and
`no_name_based_ambiguity_evidence`, exports only immutable lineage-bound
diagnostic JSON with a lower-bound warning, binds verified source,
normalized-dataset, clean-code, contract, and assessment identities,
includes `research/` in clean-code detection, canonicalizes ticker case, and
adds a deterministic same-day tie-break. Three dangerous-direction tests
were proved red on the submitted code before passing on the correction.

The corrected clean-commit Snapshot A result remains 2,885 flagged tickers
and 208,653 flagged events (35.6723%), but deterministically reports **768**
interleaving flags rather than the submitted 766. Its exact lineage is source
manifest `51954daea8432136b9c99fb4d5088e0c672664e9384475635110dd33e08a2e85`,
normalized dataset `acer-analyst-events-73c36f9de1841b0a` under contract v2,
diagnostic contract v1, clean code `1805ec7b96bc62afd6c1f6019ec68b9b8f9587f5`,
and assessment SHA-256
`8a020211e8ef5482abcceaa78a6d5f374bf8c0e9f60e2593db461d4f7b304a0b`.
BBBY now receives `no_name_based_ambiguity_evidence`, which states only that
the vendor names did not reveal its known symbol reuse; it is not a safety
verdict.

No vendor API, QuantConnect, price, outcome, signal, backtest, broker,
scheduled task, operator database, or deployment path was touched, and no
research look was consumed. The measurement is accepted only as a
name-evidence lower-bound diagnostic, **not an allowlist** and not a security
master. Issuer mapping remains blocked pending an owner-selected external
point-in-time security-master path. No milestone completes.

Validation on the completed review tree: the focused ACER/lineage/document
surface passed 128 tests; the complete repository suite passed **4,446 tests
with zero failures and 25 warnings in 661.90 seconds** on Python 3.13.14; the
active-document suite passed 40 tests before this result was recorded; and
the required `compileall` surface including `research/` passed. Final
active-document, diff, status, ordered-commit, narrow-secret, exact-remote,
and shared-checkout checks gate the single authorized push.

## 7cj. Counter-review of the identity review (Claude, 2026-08-21)

Branch: `user/claude/acer-identity-cr-prereg-20260821`, based on `84bec5d`.
Full record: `docs/Archive/Review/REVIEW_2026-08-21_ACER_IDENTITY_COUNTERREVIEW.md`.

**All four findings confirmed by reproduction against my submitted code.**
ACERIDR-001 is the best finding of the round and it is against me: I wrote a
document and a test both stating the flag set is a lower bound, then shipped
an API whose verdict constant read `unambiguous` for a ticker that same test
proves is a known reuse. The prose was right; the code contradicted it, and
the code is what a later join reads. The 6,792 unflagged tickers were one
careless join from being treated as an allowlist.

ACERIDR-003 is worse than its write-up suggests: feeding my submitted code
rows keyed `case` and `CASE` produced **two separate identities, both
`unambiguous`** — one symbol's two issuers escaping detection entirely.

A method note on ACERIDR-004 worth keeping: my first probe used a same-day
`A,B,A` sequence and showed no order dependence, because that sequence is a
palindrome and reversing it changes nothing. A non-palindromic `A,A,B` versus
`B,A,A` reproduced the defect immediately. A symmetric probe cannot detect an
asymmetry, and I nearly recorded a false "did not reproduce" on that basis.

I reproduced the corrected measurement from a clean tree and matched Codex's
figures exactly: assessment SHA-256 `8a020211…`, 768 interleaving flags,
2,885 flagged tickers, 208,653 of 584,916 events. The change to
`assistant/runtime_identity.py` was examined specifically because it touches
an execution-capable package during a research review: it adds `"research"`
to `_RUNTIME_SOURCE_PATHS`, which **strengthens** the clean-runtime check, and
adds no import, authority, or execution behaviour.

**One P3 fixed (CCRID-001):** the diagnostic artifact binds to `code_commit`,
which changes on any later commit — including documentation-only ones that
cannot affect the measurement — so a re-run to the same path refuses on
differing bytes. The refusal is correct but reads as tamper detection when
the measurement is substantively identical. Documented in the CLI rather than
redesigned: give each run its own path, and treat
`identity_assessments_sha256` as the stable content identity.

**One item recorded without change (CCRID-002):** the deterministic same-day
sort means a genuine same-day name alternation can no longer be seen as
interleaving. That is the correct trade — same-day vendor order never
established chronology — and is recorded so it is not later mistaken for lost
coverage.

The recurring shape of my errors in this program is now clear enough to name:
three of these four findings are cases where I wrote the correct caveat in
prose and then contradicted it in code.

## 7ck. ACER-0A completion proposals (Claude, 2026-08-21)

Same branch as 7cj, per the owner's relay instruction. Full record:
`docs/research/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`.

Codex's review named the next research task as closing ACER-0A.1–0A.10
without inspecting outcomes. Most of those need owner rulings, so this round
drafts **concrete proposals for 0A.5–0A.9** — the ones that can be specified
from what is already known — so the owner accepts, amends, or rejects
options rather than facing a blank page. **Nothing here is frozen**, and the
document says so in its status line; ACER-2 remains blocked regardless.

The rating scale is proposed from measurement, not guesswork. The corpus
contains **54 distinct rating strings**, and coverage is extremely
concentrated: the top 19 cover **99.57%** of 584,916 events, with 34 strings
below 500 events accounting for 0.43%. The proposal is a five-level ordinal
scale with an explicit refusal class rather than a default — `mixed`,
`fair value`, `not rated` and `tender` express no position on a buy-to-sell
axis, and defaulting an unknown string to hold would manufacture a
zero-notch observation from missing information and dilute the signal toward
zero. Three genuinely arguable assignments are named rather than hidden:
`speculative buy`, the relative-performance band strings, and the
firm-idiosyncratic neutrals (`sector weight`, `perform`, `peer perform`),
which the proposal maps globally *because* a firm-specific map would be
easier to tune after the fact.

One design point worth the owner's attention: **encoding (b) can be made
independent of the rating scale entirely.** Taking direction-only sign from
the vendor's own `rating_action` field — measured as clean values
`upgrades` / `downgrades` / `maintains` / `initiates_coverage_on` /
`reiterates` and a small tail — means that half of the six-cell family does
not depend on ACER-0A.5 at all, and is immune to the equal-spacing
assumption the notch encoding carries.

0A.6 proposes the decay equation with **age counted in trading sessions
rather than calendar days**, per-firm state replacement so the aggregate is a
consensus rather than a sum over duplicate opinions, and a minimum-coverage
floor. 0A.7 proposes open-to-open 21-session outcomes, within-session
winsorization and z-scoring, and **Spearman rather than Pearson** because the
notch encoding is ordinal with heavy mass at zero. 0A.8 proposes the
development/confirmation split, purge-and-embargo sized to the 21-session
overlap, the session as the independent observation unit, and a frozen
bootstrap seed and draw count so the p-value is reproducible. 0A.9 proposes
slot-failure rules that turn on whether outcomes were **read**, which is a
checkable property of the code path rather than a judgement about intent.

Validation on the final tree: full suite **4,446 passed / 0 failed / 25
warnings** in 657.06 seconds, unchanged from the reviewed tree because this
round changed no behaviour — the only code edit was a CLI docstring.
`compileall` over the required surface including `research/` passed;
`git diff --check` passed; document-consistency guards reran green after
every edit including after these counts were inserted; Python 3.13.14.

Untested surface, stated plainly: **none of the ACER-0A.5–0A.9 proposals is
implemented or tested.** They are specification text. The rating-scale
proposal in particular has been checked for coverage against the corpus
vocabulary but not exercised by any mapping code, so the 99.57% figure
describes string frequency, not a working implementation.

## 7cl. Independent review of ACER-0A completion proposals (Codex, 2026-08-21)

Codex independently reviewed exact remote
`origin/user/claude/acer-identity-cr-prereg-20260821` from merge-base
`84bec5d9b78e83aced548b54ec43ef75183fa512` through pushed head
`020110b7af635187606fbe24469a78c2325711c9`. Commit `3e92b84` (identity
counter-review) and commit `020110b` (completion proposals) are both
**accepted after correction**. The complete disposition and P0-P3 ledger is
`docs/Archive/Review/REVIEW_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`.

Six findings were closed. Four P2 methodology defects would have permitted
materially different or invalid implementations: normalizing by the sum of
decay weights canceled absolute decay; action and state transitions were not
closed over missing, conflicting, refused, repeated, or expired events;
validation outcomes fit the model used to call their own residuals
out-of-sample; and the named stationary bootstrap disagreed with the
repository's circular moving-block implementation. Two P3 record defects
were also closed: the measured refusal vocabulary omitted eleven strings,
and the preceding counter-review grouped commit dispositions and left one
issue outside P0–P3.

Product/specification correction `1eb3649` now supplies an implementable draft
contract for owner consideration: live events expire at `2 * H`, the aggregate
is `sum(w * value) / N_live` with `N_live >= 3` and must not divide by the
weight sum; action allowlists, sign checks, fail-closed state clearing, and all
fifteen measured refused rating strings are explicit; seven annual
development folds fit pooled OLS on purged/embargoed training rows only and
apply those coefficients to validation without refitting; the 21-session
embargo is immediately before validation; and significance calls the exact
existing circular moving-block tool with block length 21, 10,000 draws, seed
20260821, a two-sided test, and pre-outcome synthetic-null calibration. Review
record/action-plan/freeze updates are in `0d29b7a`; final validation was added
in `4fbea95`.

The existing machine-local licensed Snapshot A was read through its verified
loader only to reproduce aggregate vocabulary counts: 584,916 normalized
events, a 54-string union (53 current / 47 previous), 99.567% top-19 current
coverage, and 2,530 current events across 34 sub-500 strings. No row or
licensed payload was committed or disclosed. No vendor API, QuantConnect,
price/outcome join, signal, backtest, broker, operator database, task, or
deployment path was touched; no research look was consumed.

Validation on the corrected review tree: four new guards failed red on exact
Claude head `020110b` and passed green after correction; active-document suite
**44 passed in 0.72 seconds**; focused ACER identity/runtime/document suite
**78 passed in 8.86 seconds**; complete repository suite **4,450 passed / 0
failed / 25 warnings in 741.68 seconds** on Python 3.13.14; required
`compileall` including `research/` passed. Final diff, status, ordered-commit,
remote-head, secret, and shared-checkout checks passed immediately before the
single handoff push.

Nothing in this review freezes ACER-0A.5–0A.9 or authorizes an earnings
purchase, licensed-data transfer, signal/outcome join, or test run. The owner
must still accept or amend the corrected proposals; ACER-0A.1–0A.10 and their
data dependencies must all close before implementation. No feature milestone
completed, so `FEATURE_MILESTONE_RECORD.md` was correctly left unchanged.

## 7cm. Counter-review of the proposal review (Claude, 2026-08-21)

Branch: `user/claude/acer-prereg-cr-20260821`, based on `734d521`. Full
record: `docs/Archive/Review/REVIEW_2026-08-21_ACER_PREREG_COUNTERREVIEW.md`.

**Independent correction:** the CCPR-001 state-semantics concern remains a
real owner choice, but the quantitative scan below is not decision-grade. It
used raw ticker/raw firm groups before identity resolution, counted all later
state replacements rather than the incremental non-directional-zero events at
issue, and approximated sessions from calendar days. The submitted percentages
are historical invalid evidence and were withdrawn from the active proposal.

**All six findings confirmed, two by direct computation, and both of those
are serious defects in my draft.**

**ACERPR-001** is the worst thing I have put in a specification. My proposed
aggregation `sum(w·notch)/sum(w)` is a weighted mean, and a weighted mean
cancels any common factor. Evaluated at H=63, three equally-aged +1 actions
score **1.0000 at ages 0, 63, 252 and 756 sessions alike** — a three-year-old
rating scoring identically to today's. The half-life is a *frozen family
dimension*, and my formula would have made it very nearly inert and the three
half-life cells near-duplicates. Codex's `sum(w·notch)/N_live` scores 1.0000,
0.5000, 0.0625, 0.0002 at those ages: coverage-neutral and still decaying.

**ACERPR-003** is circular by construction: I proposed regressing each
session's outcome on that session's controls, taking the residual, and
calling the correlation with it out-of-sample. Fitting on the realized
outcomes you then score against is in-sample by definition. The residual was
orthogonal to the controls by fitting, not by prediction.

**ACERPR-004** named a stationary bootstrap with an "expected block length"
while `backtest.engine.bootstrap_edge_significance_by_block` documents and
implements a **circular moving-block** bootstrap with fixed length — two
different algorithms would have satisfied my written name, so the
preregistered threshold was not reproducible. **ACERPR-005** reproduced
exactly: 54 strings in the union, my table listed 39, and the 15 unmapped
ones are precisely those Codex enumerated; I had disclosed four.
**ACERPR-006** is a fair process finding against my counter-review record's
shape, and Codex's edits to that record are structural only — no finding was
removed, weakened, or re-graded.

**One new P2 raised and measured (CCPR-001).** Codex's correction makes
non-directional actions create a zero event that *replaces* the firm's prior
state, and `maintains` is 59.7% of all events — so a later `maintains`
silently erases an earlier upgrade's decayed signal. That is not symmetric
across the frozen half-life dimension. Measured on Snapshot A: of 121,637
directional actions, 28.9% are never superseded, the median time to
supersession is 212 calendar days, and the share truncated before one
half-life elapses is **7.1% at H=21, 19.1% at H=63, and 32.2% at H=126**. The
longest half-life loses nearly a third of its signal to truncation while the
shortest loses a fourteenth — so a cell that cannot realize its longer memory
is partly measuring the state rule rather than memory length. That is the
same *class* of problem as ACERPR-001, arriving inside the fix for it.

I did not change the rule. The measurement and two named alternatives —
keep the zeroing and accept the asymmetry, or let non-directional actions
leave the prior revision decaying untouched — are added to the proposal for
the owner to rule on before any freeze.

This is the third consecutive round in which a correction needed a
correction. That is the gate working, not failing.

## 7cn. Can ACER-2 run locally? Data-capability audit (Claude, 2026-08-21)

Same branch as 7cm, per the owner's relay instruction. Full record:
`docs/research/ACER_2026-08-21_LOCAL_DATA_CAPABILITY_AUDIT.md`.

**Independent correction:** the negative result below applies to the current
**EDGAR/yfinance path**, not every local route. Repository-wide local
feasibility remains unresolved because the audit omitted the existing
**Databento** research path (`ml/databento_source.py`, `ml/databento_pit.py`,
`ml/databento_authoritative.py`). That path is an unmeasured candidate: no
local artifact or visible credential was present during review, and its ACER
history, delisted coverage, terminal-return semantics, access, cost, and
licence remain unaudited. Section 7co is authoritative over the original
repository-wide conclusion retained below.

ACER-0A.3 and 0A.4 were open with unmeasured answers. Both are now answered,
and both are **negative** — the second decisively so.

**The binding obstacle is not the missing security master.**
`data/pit_universe.py` is this repository's genuine point-in-time capability,
and its own docstring states the two limits that settle this: "**Prices for
delisted securities are unavailable**… the current ticker map and price
provider do not supply their bars", and "**No delisting returns**, so a
company that leaves the universe leaves without a final return. This biases
results upward and the size of the bias is not knowable from this data."

The frozen ACER-0A universe requires delisted securities to remain eligible
while historically listed; the proposed outcome is a 21-session forward
return. The local path supplies the first and not the second, for exactly the
population whose absence creates survivorship bias — the failure this project
has already measured in its own legacy universe, where SIVB, SBNY and FRC are
absent. A locally-run ACER-2 would produce an upward-biased result whose bias
could not be bounded.

Two supporting findings from the submitted audit: the production read-path
price provider declares
`provides_point_in_time_lineage = False` in its own contract and its bars are
adjusted as of fetch date; and **no local book-value source exists at all**,
so the proposed value control (ACER-0A.3) has no implemented source. The
original “sole local provider” and repository-wide conclusions are invalidated
by the correction note above.

A specification mismatch was also caught before it could be frozen: ACER-0A.7
proposes **GICS** sector dummies, while the only locally available sector
information is **SIC codes** via EDGAR. Freezing one and implementing the
other would be a silent substitution.

**One finding reshapes the security-master blocker rather than removing it.**
`pit_universe.py` already establishes the right principle — "`cik` is the
primary key, never the ticker" — and CIK is exactly the durable issuer key
the ratings feed lacks. But `fetch_ticker_map` is documented as "CIK ->
ticker for companies that **still have a listed ticker today**", so it
resolves survivors and omits the dead names, which are the ones that matter.
EDGAR is a promising route, not a finished one.

The submitted option set omitted the existing Databento path and is superseded
by the corrected audit. Amending the universe to drop delisted names remains
**not recommended** because it reintroduces the survivorship problem.

Validation on the final tree: full suite **4,450 passed / 0 failed / 25
warnings** in 662.69 seconds — identical to the reviewed tree, because this
round changed **no code at all**. `compileall` over the required surface
including `research/` passed; `git diff --check` passed; the
document-consistency guards reran green after every edit, including after
these counts were inserted; Python 3.13.14.

Untested surface, stated plainly: sections 7cm and 7cn are analysis and
specification text. The truncation percentages in CCPR-001 come from an
aggregate scan of the snapshot and use a 252/365 calendar-to-session
approximation; they are not produced by any tested code path. The
capability audit quotes existing module docstrings and contracts rather than
executing them.

## 7co. Independent review of ACER preregistration counter-review and local-data audit (Codex, 2026-08-21)

Codex reviewed exact remote
`origin/user/claude/acer-prereg-cr-20260821` from merge base
`734d521da23267deda49fb6ce8f91d35b4d09cd0` through ordered commits
`5372d231755c9417b8df1889dd15339577cd3f4d` and
`f93e24d7cbb282cac407a2c8b17c4eba6d90c064`. Both commits are **accepted
after correction**. The complete record is
`docs/Archive/Review/REVIEW_2026-08-21_ACER_PREREG_AND_LOCAL_DATA_AUDIT.md`.

Three findings were confirmed. **ACERLDR-001 (P2):** the submitted CCPR-001
scan did not isolate the effect it claimed to measure, used unresolved raw
ticker/firm keys and a calendar approximation instead of exact NYSE sessions,
and had no committed reproducer. Its 7.1%/19.1%/32.2% figures are therefore
withdrawn as decision evidence. The two state-semantics alternatives remain
owner choices; neither was selected. A later measurement must use resolved
issuer and rating-firm identities, exact sessions, and separate directional,
non-directional and expiry incidence. **ACERLDR-002 (P2):** the local-data
audit omitted the repository's existing Databento capture, security-master
and vintage-adjustment path. The current EDGAR/yfinance path is inadequate,
but repository-wide local feasibility remains unresolved until Databento is
audited. **ACERLDR-003 (P3):** missing terminal outcomes are disqualifying,
but the aggregate bias direction is not known until the omitted exits are
measured; the documentation no longer promises a deterministic sign.

Correction `32a16b0` updates the active evidence and adds three dangerous-
direction document guards; review record/action-plan commit `a2bca7f` records
the independent disposition and corrected current state. Review-only
inspection found no local Databento
artifact and no credential visible to the review process; no vendor API was
called, no data was downloaded or purchased, no rating was joined to a price
or outcome, and no research look occurred. The next gate is an explicit owner
authorization for a zero-outcome Databento structural capability/cost/licence
audit, or an owner choice of another point-in-time source or a read-only QC
data path. The Benzinga Earnings audit, final issuer mapping and all remaining
ACER-0A freeze decisions remain open.

Validation on the corrected review tree: the three new guards failed red on
the exact pushed documents and passed after correction; the active-document
suite passed **47/47**; the focused ACER normalization/identity, Databento
source/PIT/authority and document suites passed **179/179**; the complete
repository suite passed **4,453 / 0 failed / 25 warnings in 751.09 seconds**;
and required `compileall` including `research/` passed on Python 3.13.14.

## 7cp. Counter-review, and checking instead of asserting (Claude, 2026-08-21)

Branch: `user/claude/acer-databento-capability-20260821`, based on `381615b`.
Full record: `docs/Archive/Review/REVIEW_2026-08-21_ACER_DATA_AUDIT_COUNTERREVIEW.md`.

**All three findings confirmed; nothing found to correct in Codex's work.**
First round in this program with no counter-finding, and the reason is that
two of the three are the same failure of mine recurring.

**ACERLDR-001, confirmed from my own printed output.** CCPR-001's percentages
existed to help the owner choose between zeroing a prior revision and letting
it decay. My scan counted *every* later action as a supersession, and my own
breakdown shows 21,044 upgrades and 17,826 downgrades among 86,519 — **45%
are directional actions that replace state under both rules**. The numbers
never discriminated between the two options they were produced to inform.

**ACERLDR-002, and worse than Codex stated.** I called yfinance the sole
local price source while ~130KB of reviewed Databento capture code sits in
`ml/`. **My own action plan already said so** — line 91 names "the Databento
ingest/point-in-time software" in a section I wrote. I searched `data/` and
generalized to "the repository".

**ACERLDR-003.** I took `pit_universe.py`'s "biases results upward" and
presented it as established across the whole exit mixture. Cash acquisitions
and mergers need not have negative terminal returns, and I had measured no
exit types. The missing terminal outcome is disqualifying without assuming
its sign.

### The pattern, named precisely

Three consecutive rounds, same class of defect: the identity round's document
and test said "lower bound" while the API constant said `unambiguous`; the
proposal round's prose described a decaying signal while the formula
cancelled its own weights; this round's action plan named Databento while my
audit said yfinance was the only source. **Each time the prose was right and
the artifact contradicted it**, because I asserted a property of this
repository from a partial look instead of checking it.

### The response is code, not another document

`research/acer/capability.py` resolves each ACER-2 data requirement by
reading a contract, an import, or a pinned dependency, and every finding
carries the evidence it read. Re-running is cheap, and a capability that
disappears flips a status instead of leaving a stale sentence in a document.
Result over seven requirements: **1 available, 4 unavailable, 2 unmeasured,
6 blocking, `acer2_runnable: false`.**

Two design choices matter. `UNMEASURED` is a distinct status from
`UNAVAILABLE`, because Databento capture code exists and has never been
exercised for ACER — calling it either way is a claim nobody has earned. And
**credential presence is deliberately not consulted**: a key proves access,
not history depth or delisted coverage, and a test asserts the key never
reaches the evidence string.

One finding is a correction to my own earlier negative: the **NYSE
trading-session calendar is available** — `pandas_market_calendars==5.4.0` is
pinned and `data/market_data.py` already builds the NYSE calendar. My
`calendar_days × 252/365` approximation in CCPR-001 was never necessary,
which is the same failure again in miniature.

Validation on the final tree: full suite **4,467 passed / 0 failed / 25
warnings** in 706.11 seconds — 4,453 from the reviewed tree plus this round's
14 capability tests. `compileall` over the required surface including
`research/` passed; `git diff --check` passed; document guards reran green
after every edit including after these counts were inserted; Python 3.13.14.
Four mutations were applied and all four detected: inferring Databento
availability from module presence, removing the evidence guard, permitting
the available-and-blocking incoherence, and reporting the delisting-return
gap as available. Source restored from a backup copy in a `finally` block.

Untested surface, stated plainly: these checks read contracts and pinned
dependencies, so they establish what the repository *declares*, not what a
vendor would actually deliver. A capability reported `UNMEASURED` stays
unmeasured until someone exercises it; the checks cannot promote it.

## 7cq. Independent review of the ACER capability checker (Codex, 2026-08-21)

Codex reviewed exact remote
`origin/user/claude/acer-databento-capability-20260821` from merge base
`381615bffc97195b34b2db34ddb4369f50123aeb` through ordered commits
`477b9971f52770b2d4cb920414de9a02681f2fee` and
`9304f9cc9ccc6f734a4c90b0a1469b6f1e76436d`. The counter-review commit is
**accepted**; the capability-checker commit is **accepted after correction**.
The complete record is
`docs/Archive/Review/REVIEW_2026-08-21_ACER_DATABENTO_CAPABILITY.md`.

Three P2 findings were reproduced. **ACERDCR-001:** the submitted
`CapabilityFinding` allowed an unavailable or unmeasured required input to be
non-blocking, contradicting its own fail-closed contract. **ACERDCR-002:**
`summarize_capabilities()` accepted a caller-selected subset, so passing only
the available calendar finding returned `acer2_runnable=true` while omitting
all six blockers. **ACERDCR-003:** the checker called a package “importable”
after `find_spec()` only; a simulated broken import still returned calendar
status `available` and non-blocking.

Correction `c9ee971` makes every unavailable or unmeasured requirement block,
requires the exact seven-requirement checklist once each before summarizing,
and imports the pinned calendar package and constructs its NYSE calendar.
Review record/action-plan commit `907ccac` and formatting follow-up `8ae1933`
preserve the dispositions, ledger and corrected sequencing state.
Four dangerous-direction cases failed red on exact pushed `9304f9c` and pass
green after correction. The factual current result is unchanged: one
available, four unavailable, two unmeasured, six blocking, and
`acer2_runnable=false`.

No credential was read and no vendor, QuantConnect, broker, database, task,
deployment, price, outcome, LEAN run, backtest, or research look was touched.
The checker proves local declarations and installed capability only; it does
not establish that Databento supplies ACER's required data. Databento remains
unmeasured and the owner authorization gate for a zero-outcome structural
capability/cost/licence audit is unchanged. No ACER milestone completes.

Validation on the corrected review tree: the four dangerous-direction cases
failed red on exact pushed `9304f9c` and the capability suite passed **18/18**
after correction; the expanded focused ACER/calendar/Databento/import-boundary
and document set passed **215/215 in 12.82 seconds**; the active-document gate
passed **47/47**; the complete repository suite passed **4,471 / 0 failed /
25 warnings in 658.86 seconds**; and required `compileall` including
`research/` passed on Python 3.13.14.

## 7cr. Counter-review, and the mirror-case rule (Claude, 2026-08-21)

Branch: `user/claude/acer-capability-cr-20260821`, based on `2251983`. Full
record: `docs/Archive/Review/REVIEW_2026-08-21_ACER_CAPABILITY_COUNTERREVIEW.md`.

**All three findings confirmed by execution**, and every one is a fail-open
path in a module I wrote specifically to fail closed. My submitted class
accepted `status=unavailable, blocks_acer2=False`; my
`summarize_capabilities([calendar_finding])` returned **`acer2_runnable =
True`**, so omitting the six blocking checks produced a green verdict; and I
labelled `find_spec` "importable" without importing anything or building the
calendar, so a broken installation would have reported the one non-blocking
capability as available.

A method note worth keeping: my first probe of the subset defect appeared to
*refute* it, because loading the old module from a temporary directory broke
its `REPO_ROOT` and the calendar check failed for an unrelated reason.
Re-running with the module inside the repository tree reproduced the defect
at once. That is the second time this session a flawed probe nearly produced
a false "did not reproduce" — the first was a palindromic ordering test.

**One new P2 raised and fixed (CCCR-001).** Codex's correction makes the
summary refuse anything but "the complete ACER-2 requirement set exactly
once" — and that set omitted **earnings surprise**, which ACER-0A.7 names as
a required control and ACER-0A.2 tracks as an unpurchased dataset. A guard
enforcing completeness over an incomplete checklist converts a visible gap
into an assertion that nothing is missing. Added
`check_earnings_surprise_control` (unavailable, blocking: the only local
earnings module is yfinance-backed and exposes the vendor's `surprise_pct`,
the value ACER-0A.5 declines to trust), and wrote down
`_CONTROLS_COVERED_BY_PRICES` so the claim that momentum, size, liquidity,
volatility and analyst coverage need no separate source is auditable rather
than assumed. The assessment now reports **8 requirements, 1 available, 5
unavailable, 2 unmeasured, 7 blocking**.

### The generalization, narrower than "be careful"

Four consecutive rounds, same shape: the identity constant said
`unambiguous` while its document said "lower bound"; the proposal's formula
cancelled the decay its prose described; the data audit contradicted my own
action plan; and a module promising to replace assertion with checking
contained three paths that asserted readiness without checking it.

In each case I wrote the guard for the direction I was thinking about and
left the mirror direction open — available-and-blocking guarded but
unavailable-and-non-blocking not; the full checklist tested but not the
subset; the pinned dependency checked but not the actual import. **The rule
that keeps working is to ask, for every guard, what its mirror case is.**
That question is what produced CCCR-001 against Codex's own correction.

Validation on the final tree: full suite **4,473 passed / 0 failed / 25
warnings** in 738.43 seconds — 4,471 from the reviewed tree plus this round's
two new capability tests. `compileall` over `research/` and `tests/` passed;
`git diff --check` passed; document guards reran green after every edit
including after these counts were inserted; Python 3.13.14.

Untested surface, stated plainly: the earnings-surprise check reads
`data/earnings_data.py`'s source text for `yfinance` and `surprise_pct`. It
establishes that the module is the wrong kind of source for a point-in-time
control; it does not exercise the module, and it would not detect a future
earnings source added elsewhere in the repository. That is the same
partial-look failure this section describes, bounded here by naming it.

## 7cs. Independent review of capability-checker completion (Codex, 2026-08-21)

Reviewed exact remote branch
`origin/user/claude/acer-capability-cr-20260821` at
`6fc00409249da1d0a4acf23c704f8381e550e5d9`, merge-base `2251983`, in ordered
range `ff8ba6b`, `6fc0040`. Review branch:
`codex/review-acer-capability-completion-20260821`. Full record:
`docs/Archive/Review/REVIEW_2026-08-21_ACER_CAPABILITY_COMPLETION.md`.

Commit `ff8ba6b` is **accepted**: it correctly reproduces all three prior
Codex findings and preserves the method error in its first probe. Commit
`6fc0040` is **accepted after correction**: earnings surprise was a real
omission, but adding it did not complete the data-requirement set.

**ACERCCR-001 (P2, corrected in `14a3a83`):** the submitted eight-item
checklist still omitted four inputs while asserting completeness. The frozen
size control is log market cap and therefore needs point-in-time shares, not
prices alone. The frozen total-return outcome needs point-in-time corporate
actions. ACER-0A.10 separately requires historical security type and primary
listing, which durable issuer identity does not establish. And the normalized
ratings-event corpus is ACER's signal input, not an assumption outside an
`acer2_runnable` verdict. The checker now gives all four their own blocking
finding. On this isolated review tree the honest summary is **12
requirements: 1 available, 6 unavailable, 5 unmeasured, 11 blocking,
`acer2_runnable=false`**.

The material test was red on the submitted implementation: collection failed
because the new corporate-action check did not exist. After correction, 24
capability tests pass, including source-disappearance mutations that force
the normalized-corpus, shares, corporate-action, and security-eligibility
checks to `unavailable` and blocking. The adjacent ACER focused set passes
107 tests. No P0, P1, or P3 finding was identified. No milestone completes,
no real outcome was read, and ACER-2 remains unauthorized and blocked.

Final validation: 24 capability tests, 107 adjacent ACER tests, and 154
active-document/focused tests passed. The complete suite passed **4,481 / 0
failed / 25 dependency warnings in 740.68 seconds** on Python 3.13.14.
`compileall` over application, research, scripts, and tests passed. Final
document, diff, staged-content, ordered-commit, secret, remote-head, and clean
status checks passed before publication. The shared checkout remained on
`user/claude/acer-capability-cr-20260821` at `6fc0040` and was not modified.

## 7ct. Counter-review: the guard that failed its own test (Claude, 2026-08-21)

Branch: `user/claude/acer-capability-completion-cr-20260821`, based on
`40a0a37`. Full record:
`docs/Archive/Review/REVIEW_2026-08-21_ACER_COMPLETION_COUNTERREVIEW.md`.

**ACERCCR-001 confirmed on every limb.** Last round I raised an
incompleteness finding against this checklist, fixed it by adding one
requirement, and asserted completeness again — while still omitting four
more, including **the ratings corpus itself**, which is ACER's signal input.
Also confirmed: point-in-time security type and primary listing (the frozen
universe rule), point-in-time corporate actions (the outcome is a
split- and dividend-adjusted total return), and point-in-time shares
outstanding — because the frozen size control is *log market cap*, which
prices alone cannot produce, so my placement of size in
`_CONTROLS_COVERED_BY_PRICES` was wrong. Twelve requirements now, eleven
blocking.

**The instructive failure is mine, and it is inside the fix.** I wrote a
guard that derives the control list from the frozen document so completeness
would stop depending on my memory. **That guard did not detect the omission
it was written for.** It matched controls against the joined requirement
strings with a loose `any(word in requirements)` test, and a regex that
stopped at the period inside "ACER-0A.2" left the fragment
`earnings surprise (acer-0a` — whose `(acer-0a` substring matched
`_REQ_SECTOR`'s own text `"sector classification (ACER-0A.7 proposes GICS)"`.
The missing control counted as accounted-for by an unrelated requirement.

I found it only by mutation-testing the guard against the two omissions that
had **actually happened**: removing the size requirement turned it red,
removing the earnings requirement left it green. Half-working, and it looked
healthy. Fixed by stripping parentheticals from the whole document before
matching, and replacing the substring search with an explicit
`_CONTROL_ACCOUNTING` map asserted by **exact set equality**. Both real
omissions now fail the guard.

### Two rules earned, narrower than "be careful"

1. **Test a new guard against the specific failures that already happened**,
   not invented ones. Testing only the size case would have shipped a broken
   guard that passed.
2. **A completeness check must compare sets exactly**, never by substring.
   Substring matching cannot distinguish "this requirement covers that
   control" from "these two strings share characters".

The pattern across five rounds is now precise: fuzzy reasoning let my prose
claim completeness it did not have, and fuzzy matching let my guard claim
coverage it did not have. Same defect, one level down.

Validation on the final tree: full suite **4,482 passed / 0 failed / 25
warnings** in 705.08 seconds. `compileall` over `research/` and `tests/`
passed; `git diff --check` passed; document guards reran green after every
edit including after these counts were inserted; Python 3.13.14. The repaired
derivation guard was mutation-tested against both omissions that actually
occurred, and now fails on each.

Untested surface, stated plainly: the derivation guard reads one frozen
document's control sentence. It does **not** derive the universe, outcome, or
signal-input requirements from their documents — those four were added by
review, not by a check, so the same class of omission remains possible for
every requirement outside the control list. Extending the derivation to the
universe and outcome rules is the obvious next hardening and has not been
done.

## 7cu. Independent verification of the completion counter-review (Codex, 2026-08-21)

Codex reviewed the exact unreviewed range after prior review head `40a0a37`:
Claude counter-review `438fb9156672808318c0bf81783d86dd9d3e4e3c` and merge
commit `25cc6d4fca1918d05cd75db8acc4203fb07f5341`. The merge tree is
byte-identical to its Claude parent. Both commits are **accepted after
correction**; the complete ledger is
`docs/Archive/Review/REVIEW_2026-08-21_ACER_COMPLETION_COUNTERREVIEW_VERIFICATION.md`.

Two P2 defects were reproduced. First, the claimed exact accounting still
accepted any string beginning with `derived from`; changing a dependency to
`derived from nothing` therefore remained green. The corrected map names
exact members of the twelve-requirement set for every control, including both
prices and shares for size and the ratings corpus rather than prices for
analyst coverage. Second, the guard parsed the completion **proposal** while
calling it frozen, although the governing ACER-0A freeze explicitly says the
proposal is not an owner decision. The guard now derives control names from
the actual owner freeze. Because GICS remains only a proposal, the local SIC
candidate is honestly `unmeasured`, not `unavailable`. The result is now one
available, five unavailable, six unmeasured, eleven blocking, and
`acer2_runnable=false`.

One P3 documentation defect was also corrected: the current resume block
still told the next agent to counter-review work that section 7ct had already
counter-reviewed. No milestone completes and no vendor, credential, licensed
row, QuantConnect/LEAN outcome run, price join, backtest, research look,
broker, task, operational database, deployment, or trading surface was
accessed or changed.

## 7cv. Provider-neutral ACER capability correction (Codex, 2026-08-21)

The owner asked Codex to correct the capability inventory after a plan-to-code
comparison found that it required **Databento by name** in addition to the
point-in-time price/reference capabilities ACER actually needs. Branch
`codex/fix-acer-provider-neutral-capabilities-20260821` separates required
capabilities from optional provider diagnostics. `CapabilityFinding` remains
strictly fail-closed for every required input; a new `ProviderFinding` carries
Databento's structural evidence without a readiness-block field, and the
required summary refuses provider records. The current required result is
eleven capabilities: one available, five unavailable, five unmeasured, ten
blocking, and `acer2_runnable=false`. Databento remains an unmeasured candidate
and can satisfy nothing until audited, but an independently adequate QC, CRSP,
or other approved route will no longer remain blocked merely because
Databento was not selected.

The dangerous-direction mutation reinserted Databento into the required-check
tuple; the new regression failed, then the real implementation was restored
and all 34 focused capability tests passed. No vendor API, credential,
licensed row, purchase, download, price/outcome join, QuantConnect/LEAN run,
research look, broker, database, task, deployment, or trading surface was
accessed. The repository records the Benzinga Analyst Ratings expansion as
purchased. It records only authorization—not purchase—for the separate $99
Benzinga Earnings structural audit, and no current subscription supplies the
remaining required market/reference/fundamental and terminal-return inputs.

## 7cw. Role swap, local access measurement, and documentation lifecycle reset (Codex, 2026-08-21)

The owner assigned **Codex as the ACER implementer and Claude as the
independent reviewer** for the next development rounds. Codex completed the
provider-neutral correction on branch
`codex/fix-acer-provider-neutral-capabilities-20260821`: product/test commit
`2f4e41d`, documentation-lifecycle commit `a1dc779`, and archived-path test
correction `0a94bef`, followed by review-skill path correction `b0f7dec`.
That branch was local-only when this section was written. **Superseded: it was
pushed and merged by PR #293 at `7f7e93a`, and every commit named above is now
an ancestor of `main`.** Claude's independent review of the whole merged range
is section 7cz.

A names-only environment measurement found `MASSIVE_API_KEY`, `QC_USER_ID`,
and `QC_API_TOKEN` present in the current Codex desktop process;
`DATABENTO_API_KEY` was absent. None of those names was present in Windows
User or Machine environment storage, so another process need not inherit the
same values. No secret value was printed or committed. The `lean` command is
now installed and the owner reports completing authentication and workspace
initialization; the later local measurement described below supersedes the
earlier missing-command observation. Credentials establish possible
authentication only: they do
not prove dataset entitlements, licence permission, coverage, or fitness for
ACER. No Massive, Benzinga, QuantConnect, Databento, broker, or other service
was called in this round.

The documentation tree now follows lifecycle rather than document type. The
root contains only the current working set: Action Plan, ACER plan, Session
Handoff, and Feature Milestone Record. Queued work is under `docs/Plan/`;
implemented, closed, or superseded material is under `docs/Archive/`;
process, operations, active research evidence, and current references retain
their functional subfolders. Lifecycle indexes explain the rule. The final
inventory is four root files, thirteen files under `docs/Plan/`, 167 under
`docs/Archive/`, seven active research records, and three active references.
Repository links and active-document guards were updated, and a path-integrity
scan found no missing `docs/...` targets.

The purchased Benzinga Analyst Ratings expansion is enough for the analyst-
event side of ACER-1, not for ACER-2. Separate evidence/entitlements remain
required for earnings estimates and standardized surprise, point-in-time
prices and delisted coverage, terminal delisting returns, durable issuer and
security identity, historical security type/primary-listing eligibility,
corporate actions and total-return adjustment, point-in-time shares, value
fundamentals, and sector taxonomy. The first complete run exposed thirteen
archived Strong-Buy capture tests that still named the pre-move paths; those
references were corrected and the focused capability/document/capture set
passed **98 tests**. The final complete suite passed **4,487 tests / 0 failed
/ 25 warnings** in 1,011.51 seconds. `compileall` passed over the full project,
including `research/` and `tests/`; diff checks and document-path integrity
passed. No milestone entry was added because this round corrects readiness
and repository organization rather than completing an ACER milestone.

The owner then added the standing documentation rule implemented in
`ce066a8`: every implementation/review commit series must update the
authoritative associated record whose truth changed and this Session Handoff,
but no unrelated documents. The Action Plan is now explicitly a thin
sequencing index; it changes only for priority, milestone status, gates, or the
next authorized step, and then only by linking to the detailed associated
record. Documentation-only and handoff commits do not recursively trigger
another documentation cycle. The new active-document guard passed **48
tests** after the policy was recorded.

The owner then completed the Windows LEAN CLI authentication and organization-
workspace initialization. Codex independently observed the LEAN executable,
`C:\QuantConnect\ACER`, and that workspace's `lean.json`; it did not read the
configuration or credentials. Docker was not visible on the current Codex
desktop process's `PATH`, so a local sample backtest remains the installation's
unverified end-to-end proof at that point rather than a completed ACER research
run; section 7cx supersedes that pending observation. Commit
`3cefeb1` adds the active reference
`docs/reference/LOCAL_LEAN_WINDOWS_SETUP.md`, covering Docker/WSL 2, supported
Python and CLI installation, `PATH` repair, the intentionally invisible token
prompt, removal of embedded clipboard whitespace without printing the token,
safe option parsing, Windows clock repair, an isolated workspace, sample-data
verification, and cloud-versus-local data boundaries. No user ID, API token,
credential value, licensed data, or research outcome is recorded. This makes
the lifecycle inventory three active references rather than the two counted
before the guide was added. The Action Plan is unchanged because installation
documentation did not change sequencing, milestone status, a gate, or the
next authorized step. The focused active-document suite passed **48 tests**
on the guide commit.

## 7cx. Local LEAN installation verified end to end (Codex, 2026-08-21)

At the owner's request, Codex verified the newly installed local engine
without reading or printing credentials. LEAN CLI `1.0.228` returned
successfully, `lean whoami` exited zero with its output suppressed, and the
isolated `C:\QuantConnect\ACER` workspace contained `lean.json`, `data\`, and
the generated `InstallationTest`. Docker Desktop was running from the user's
per-user installation, and its client and server both reported `29.7.2`.
Because the Codex desktop process predates the installations, its inherited
`PATH` still lacks the `lean` and `docker` command names; both full executable
paths worked, and a new PowerShell should inherit the updated paths.

The generated five-day SPY sample then completed through local LEAN Engine
`2.5.0.0` with official image digest
`817716616e7a5875964fc111a1ddd898cead5151c4d46e2007977fd03370ee24`.
It processed 3,943 bundled sample data points; all 13 data requests succeeded
and zero failed. This was installation proof only: it did not read ratings,
join an ACER signal to an outcome, consume an `R-nnn` research look, access a
broker, place a trade, or establish any ACER dataset entitlement or licence.
The first image acquisition took about an hour but completed normally; the
image is now cached locally.

Commit `2ec7f61` updates the setup guide, ACER plan, local-data capability
audit, issuer-identity record, and the Action Plan's concise gate statement.
The engine-installation blocker is resolved, but ACER-0A.4 remains open because
no approved point-in-time market/reference/fundamental data, mapping files, or
terminal-delisting-return source has been inventoried or materialized. The
focused active-document suite passed **48 tests**; diff and narrow secret
checks passed. No feature milestone entry was added because installing the
research engine does not complete an ACER milestone.

## 7cy. ACER engine amended to QuantConnect Cloud (Codex, 2026-08-21)

The owner explicitly superseded the earlier local-LEAN-authoritative ruling
before any ACER outcome was observed. QuantConnect Cloud is now the
authoritative engine for ACER historical and outcome backtests. Local LEAN
remains installed and verified, but its project role is limited to
implementation, unit/synthetic/integration tests, and bundled sample
validation. No local QuantConnect Security Master or US Equity-history
purchase/download is planned unless the owner later reverses this decision.

Commit `0bd5fff95ff42030111ce0d03c0c0c74e1ba3b65` applies the ruling consistently
to the active ACER plan, ACER-0A freeze, Action Plan, local-capability audit,
issuer-identity record, and Windows setup guide. The amendment does not make
ACER-2 runnable: a zero-outcome QuantConnect Cloud audit must still establish
actual point-in-time coverage and semantics for prices, mappings, historical
eligibility, corporate actions, fundamentals, shares and sector. Terminal
delisting returns and permission to transfer reconstructable Benzinga data
remain separate gates. Cloud-run provenance must use dataset/version
disclosures, project/compile/backtest identifiers, source-code SHA, and hashes
of any permitted uploaded custom data because cloud-resident datasets cannot
be hashed locally. No upload, outcome join, backtest, or research look was
authorized or performed. The focused active-document suite passed **48
tests**; diff and narrow secret checks passed. No feature milestone entry was
added because this is an execution-policy amendment, not a completed ACER
milestone.

## 7cz. Independent review of the Codex documentation-lifecycle range (Claude, 2026-08-21)

First round under the new role split: Codex implements, Claude reviews.
Branch `user/claude/review-codex-doc-lifecycle-20260821`, created from
`origin/main` at `98e1d63`. Full record:
`docs/Archive/Review/REVIEW_2026-08-21_CODEX_DOC_LIFECYCLE.md`.

Reviewed the complete ordered range `25cc6d4..98e1d63` — twenty commits,
four merged PRs (#292–#295), 242 files — commit by commit, merges included.
**Accepted after correction.** No P0 or P1. Four P2 and four P3 findings,
all corrected here.

What is genuinely good, said before the findings: the reorganization moved
~180 documents with **zero** broken `docs/...` references, verified by
resolving every such target in every tracked file. And the provider-neutral
capability split (`2f4e41d`) is a real conceptual correction rather than a
weakening — ACER needs *capabilities*, not a named vendor, and
`acer2_runnable` stays `false` because everything Databento would have
supplied is still separately required and blocking.

**The findings cluster on one shape: claims about state, written inside the
commit that changes the state.**

- **CDR-003 (P2)** — the handoff told the next session that merged mainline
  work was "local-only" and "must be independently reviewed before merge"
  (all eight commits are ancestors of `origin/main`), and that "There is no
  local `lean` command" while section 7cx of the same file records LEAN CLI
  `1.0.228` verified. This is CCR-005 for the fourth recorded time.
- **CDR-002 (P2)** — the cloud-engine amendment rewrote freeze §8's first
  bullet and left its third authorizing "read-only **symbol-mapping** work
  only". That document governs for ACER-2 where documents differ, so the
  governing record forbade the cloud capability audit that the ACER plan, the
  local-data audit and §8 all schedule as the next step. Widened to
  "read-only, zero-outcome structural work" with every prohibition intact.
  Also recorded there: with a cloud engine the ratings-transfer gate stops
  being a side condition and becomes a **blocking dependency** — the selected
  architecture needs a permitted representation of the signal in Cloud.
  Counter-review retained that gate but corrected the supporting overstatement:
  QC offers separate Download licences, so its terms do not categorically
  forbid local data; this project has not purchased or authorized that route.
- **CDR-004 (P2)** — the permanent append-only run ledger was filed under
  `docs/Archive/`, a folder whose index says "completed, superseded, and
  obsolete material" and "Do not resume work from this folder", while ACER's
  two authorized slots must each append an `R-nnn` entry to it. Moved to
  `docs/research/alpha-result.md`; 27 files repointed; the ledger header and
  the Archive index now say plainly that it is active and why.
- **CDR-001 (P2)** — during the migration, two lifecycle guards had their
  bodies wrapped in `if re.search(r"Status: \*\*SUPERSEDED", sbp):`.
  **Mutation-proved on the reviewed tree**: rewording that one status line to
  `RETIRED` left both tests green with every assertion unrun. The first guard
  also lost the relationship framing it was written with. Repaired by parsing
  the status once and asserting it; the same mutation now fails both tests
  and passes restored, with the document byte-identical afterwards.
- **CDR-005 (P3)** — the Action Plan attributed 1/5/6/11 to the isolated
  review tree; checking out `14a3a83` in a detached worktree and running the
  summarizer gives 1/**6**/**5**/11, matching the review report and §7cs.
- **CDR-006 (P3)** — "Historical review reports … are never retro-edited",
  asserted in the commit that rewrote paths inside **68** of them. The rule
  now protects findings, dispositions, counts and validation results, and
  records the mechanical path-migration exception.
- **CDR-008 (P3)** — `Archive/Plans/` is defined as completed or superseded
  material, yet the Action Plan cites `SHADOW_OBSERVATION_DESIGN.md` there as
  the authority for `overlay-epoch-001`, which is live and accruing toward a
  24-month floor. The file was deliberately not moved; the Archive index now
  distinguishes a completed implementation from a still-governing contract.
- **CDR-007 (P3)** — the LEAN/Docker installation is machine-local truth that
  lived only under `docs/reference/` and said "this machine" on a repository
  with **two** hosts. Measured read-only: `whoami` → `REDMOND\sheltonchen`,
  the **epoch host**; `C:\QuantConnect\ACER` present; `lean`/`docker` absent
  from a pre-install shell. Recorded in `OPERATIONAL_FACTS.md` with what I
  measured separated from what Codex recorded, plus the note that Docker
  Desktop is now resident on the machine running `paper-epoch-006`.

Two things recorded without a code change, in the review report: the
merged-commit guard's blind spot (hash and claim in different sentences —
which is why it passed on `origin/main` while the claim was false), and that
`CQC-001`'s unverified QuantConnect `success` check stops being dormant under
a cloud engine.

Nothing in this round touched a vendor API, credential, licensed row, price,
outcome, backtest, research look, broker, scheduled task, operator database,
deployment, or epoch. `paper-epoch-006` is undisturbed. No milestone
completed, so `docs/FEATURE_MILESTONE_RECORD.md` is unchanged.

Validation on the final tree: full suite **4,488 passed / 0 failed / 25
warnings** in 843.24 seconds on Python 3.13.14. This round adds **no** test:
`origin/main` at `98e1d63` and this branch both collect 4,488, measured in a
detached worktree — CDR-001 repaired two existing guards rather than adding
one. (Section 7cw's 4,487 was measured mid-series, before the range's last
guard landed; it is not a discrepancy with this count.)
`compileall` over the required surface including `research/` and `tests/`
passed; `git diff --check` passed; the repository-wide `docs/...` link scan
reported **0** missing targets after the ledger move; the active-document
guards passed **48/48**, rerun after every edit including after these counts
were inserted. An earlier full run was started before the last documentation
edits and is therefore not the validating run; it was rerun on the exact final
tree.

Untested surface, stated plainly: this round changed documentation and one
test module. The capability checker's behaviour is unchanged by me, and it
still establishes only what this repository *declares* — not what any vendor
would deliver. The host measurements are point-in-time observations of one
machine; the second host was not measured and nothing here claims anything
about it.

## 7da. Codex counter-review of Claude's lifecycle review (2026-08-21)

Exact submitted remote head
`origin/user/claude/review-codex-doc-lifecycle-20260821` at
`cc05ce76676e9aa8798bf03bba39aa12ff881d7e`, merge-base `98e1d63`, ordered
commits `b4129d2`, `f14e152`, `cc05ce7`. Counter-review branch
`codex/counterreview-claude-doc-lifecycle-20260821`. Durable record:
`docs/Archive/Review/REVIEW_2026-08-21_CLAUDE_DOC_LIFECYCLE_COUNTERREVIEW.md`.

**Accepted after correction.** Claude's eight original findings and their
corrections remain accepted. Four counter-review findings are closed:

- **CDCR-001 (P2):** the transfer gate remains load-bearing, but the claim
  that QC categorically forbids data downloads was false. QC offers separate
  Download licences; this project has not purchased or authorized one and
  Cloud remains the selected engine. No ratings representation — including
  normalized events or derived features — may be presumed transferable. The
  applicable agreement or written permission must cover the exact
  representation sent to QC.
- **CDCR-002 (P3):** CDR-003b is no longer deferred. The merged-state guard
  now catches the exact adjacent-sentence branch form that shipped, excludes
  negated and historical claims, and avoids paragraph-wide matching. Red on
  the submitted parser: 2 failed / 1 passed; corrected regressions: 3 passed;
  active-document suite: 50 passed.
- **CDCR-003 (P3):** CDR-006's migration count was one high. Exact rename
  detection shows 139 moved reports: 68 content-changed and 71 byte-identical.
  Current records are corrected; the submitted report retains dated notes.
- **CDCR-004 (P2):** the current resume prompt still asked the owner to
  authorize the QC structural audit after governing freeze §8 had authorized
  it. The prompt now directs the authorized audit and requires it to remain
  inside that narrow boundary; a relationship guard fails on the stale form.

The two owner-facing conclusions are now precise. The next technical step is
still the already authorized read-only, zero-outcome QC Cloud capability
audit. Separately, ACER-2 remains blocked until the ratings agreement or
written permission covers the exact representation to be uploaded, its Cloud
use, storage/retention/deletion and permitted outputs. Neither gate authorizes
an upload, outcome join, backtest, research look or purchase.

No vendor API, credential value, licensed row, price, outcome, backtest,
research look, broker, task, operator database, deployment or epoch was
accessed or changed. Historical capability split 1/6/5/11 was independently
reproduced at detached `14a3a83`; required compileall passed. The complete
suite passed **4,491 tests / 0 failures / 25 dependency warnings** in 918.62
seconds on Python 3.13. Final Git/status checks follow before handoff. No
milestone completed.

## 7db. Project separation begins with a machine-checked boundary (Codex, 2026-08-21)

Owner direction changed the current implementation task from ACER capability
work to separating the mixed repository into a trading assistant product and
a strategy-research product. Codex created
`codex/project-separation-boundary-20260821` from clean `origin/main` at exact
head `1fbf6395879b464381238fb770afc83482898663`. The active, reversible migration
sequence is `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`; this does not
replace ACER's evidence plan or close any ACER gate.

SEP-0 makes no runtime move. Commit `d31604f` adds the machine-readable
`architecture/project_boundaries.json` and a fail-closed AST boundary test.
The current ownership baseline is trading assistant (`assistant/`,
`execution/`, `risk/`), strategy research (`research/`, `backtest/`, `ml/`,
`signals/`, `strategies/`, `baskets.py`), temporary shared surface (`data/`,
`config.py`, `market_analytics.py`), and unclassified `scripts/`. Every one of
the **13 direct cross-product imports** is recorded with a migration reason;
an added edge or a stale ledger edge fails. Commit `6bc11f8` records the active
plan and the concise sequencing reference in the Action Plan.

The transitive check found one genuine authority violation that folder-level
inspection would have missed:
`assistant.allocation_batch -> assistant.context_builder -> signals.regime`.
It is pinned as the only current authority-to-research path, not blessed as an
API. Any expansion fails. SEP-1 must remove it first by extracting broker
portfolio-snapshot construction from the broad context builder, then reduce
the remaining cross-product ledger through neutral evidence schemas,
financial primitives, mandate inputs/outputs, and a read-only research-result
adapter. Physical repository extraction is deliberately deferred until those
boundaries and every mixed script entry point are reviewed.

Validation on the settled tree: the focused separation and active-document
suites passed **54 tests**; repository-wide compileall, including `research/`
and `tests/`, passed. The pre-handoff complete suite passed **4,494 tests / 0
failures / 25 dependency warnings in 811.86 seconds**; the complete suite on
the exact three-commit tree repeated **4,494 / 0 / 25 in 944.57 seconds** on
Python 3.13.14. No vendor, broker, operator database, scheduled task,
deployment, backtest, research look, credential, licensed row, or evidence
epoch was accessed or changed. SEP-0 remains pending Claude's independent
review of the exact pushed snapshot; it is not yet a completed milestone.

## 7dc. Independent review of SEP-0 (Claude, 2026-08-21)

Branch `user/claude/review-sep0-boundary-20260821`, created from Codex's exact
pushed head `f4be89a` (merge base `origin/main` `1fbf639`). Full record:
`docs/Archive/Review/REVIEW_2026-08-21_SEP0_PROJECT_SEPARATION.md`.

**Accepted after correction.** No P0 or P1; two P2 and three P3, one of which
is recorded open rather than fixed.

Said first because it is the substance: **the census is exact.** I recomputed
the cross-product import graph with an independent scanner rather than reusing
the submitted code — **13 direct edges, matching the ledger with no additions
and no stale entries.** I also checked an assumption the whole plan rests on:
the "temporary shared kernel" (`data/`, `config.py`, `market_analytics.py`)
imports **neither** product today, so the shared designation is honest and the
13-edge count is not understated through that route. And the transitive check
found `assistant.allocation_batch -> assistant.context_builder ->
signals.regime`, a real authority-to-research path no folder-level review
would surface, pinned as a violation rather than blessed.

**CDR2-001 (P2).** The import graph walked only classified roots, so a chain
stepping through an unclassified root left the audit entirely — including the
declared, 67-file `scripts/` root, and any new top-level package, because
nothing required the manifest to classify one. The module's own docstring
claimed authority modules cannot reach research "through any first-party
import chain"; that was false at the boundary of the classified set. Four
mutations, all reported **clean** before the fix and **red** after: a new
unclassified package reaching `signals`; `assistant` through it; **`risk/`
(an authority root) through it**; and the live-shape `risk/` -> `scripts/` ->
research. No package imports `scripts` today, so this was latent rather than
live — which is exactly what the guard exists to prevent. Fixed by traversing
pending-classification roots (they resolve to no product, so no edge is added,
only the chain is followed) plus a mirror-case assertion that every
first-party Python root is classified, `tests` exempt.

**CDR2-002 (P2), and its first step was mine.** Across three commits a pending
owner authorization became an assumed one and was then pinned by a test. My
earlier CDR-002 widened freeze §8's scope sentence while keeping its verb
("is authorized"); the handoff then read the widened scope as permission and
replaced "**before** any provider call, **obtain** the owner's authorization"
with "perform the **authorized** audit"; and `25adfd2` added a guard requiring
that wording and forbidding the resume block from asking for authorization at
all. Meanwhile Action Plan §7 item 1 — in the document `CLAUDE.md` names as
the sequencing authority — still lists that authorization as an open decision
covering **both** the Massive and QuantConnect accounts, and freeze §8 never
mentioned Massive. Corrected fail-closed: freeze §8 is now explicitly a scope
limit rather than the authorization, the resume block obtains authorization
before any provider call, and `25adfd2`'s guard is replaced by a relationship
test that fails whenever the two documents disagree, in either direction.
**This needs an owner ruling:** if the audit was meant to be authorized, say
so and both documents flip together. No provider call has been made.

**CDR2-003/004 (P3).** The Action Plan amendment did not say how SEP relates
to ACER's priority-1 standing (only the handoff did), and the docs root gained
a second active plan by adding one string to a test allowlist while
`docs/Plan/README.md` still described activation in the singular. Both now
state the rule where a reader will find it.

**CDR2-005 (P3), recorded open.** Two asymmetries in the new guard: an
unresolvable dynamic import is an offender in the authority check but ignored
in the cross-product census, and the authority DFS reports only the
first-traversed chain per start module while the manifest pins exact chain
strings. Neither is a fail-open on the authority boundary; both are design
questions for SEP-1 rather than review edits.

**On the owner's actual question — is separation feasible?** On this evidence,
yes, and measuring is what made it answerable. Thirteen crossings and one
transitive path is a small, named debt for a codebase this size, and the
direction is favourable: assistant→research edges are mostly presentation and
context, research→assistant edges are mostly type and primitive reuse, and
both extract cleanly behind neutral contracts. Three cautions are in the
review report: `scripts/` is the real work and is still uncounted at the
entry-point level; the shared kernel is clean now and nothing yet stops it
acquiring a product dependency; and physical extraction changes the
operational checkout's lineage, which closes `paper-epoch-006` — the epoch
clock, not review order, is the binding constraint on SEP-3.

Also recorded plainly: Codex's counter-review corrected a real overstatement of
mine (QuantConnect does sell Download licences, so "their terms forbid the
reverse direction" was too absolute), broadened the transfer gate from
reconstructable rows to any representation of the licensed signal, and fixed
the merge-state parser blind spot I had declined to fix. That work is accepted.

Validation. Submitted snapshot `f4be89a`: full suite **4,494 passed / 0 failed
/ 25 warnings** in 1,177.97 s, reproduced independently and matching §7db.
Corrected tree: full suite **4,494 passed / 0 failed / 25 warnings** in
924.94 s on Python 3.13.14 — unchanged in count, because this round replaced
one guard with another and added assertions to existing ones rather than
adding tests. `compileall` over the required surface including `research/` and
`tests/` passed; `git diff --check` passed; the focused document, separation
and ml-boundary guards passed, rerun after every edit including after these
counts were inserted.

One earlier run of the same tree reported two failures in
`tests/test_ui_allocation_review.py` at 5,036 s — roughly five times the normal
duration, because three full pytest sessions were overlapping on this host.
Both tests pass in isolation and pass in the clean 924.94 s run above. Recorded
rather than dropped, and **not** closed as resolved: the standing FPS-003 rule
is that an intermittent failure is not settled by a later green run. If either
reappears without contention, capture the full traceback.

Untested surface, stated plainly: this round changed two test modules and four
documents. The boundary guard proves what the repository's **import graph**
declares; it says nothing about runtime coupling through configuration,
subprocess invocation, the operator database, or shared files, and `scripts/`
remains unclassified so its entry-point coupling is still uncounted.

## 7dd. Counter-review of Claude's SEP-0 review (Codex, 2026-08-21)

Codex counter-reviewed exact remote
`origin/user/claude/review-sep0-boundary-20260821` at
`e195fbeb5360df7895f63b6a986878e226d4aec3`, whose merge base is the exact
SEP-0 submission `f4be89a96cbdfeaf78a52119a8bb8590d6499494`. Review branch:
`codex/counterreview-sep0-boundary-20260821`. Full record:
`docs/Archive/Review/COUNTER_REVIEW_2026-08-21_SEP0_PROJECT_SEPARATION.md`.

All three Claude commits are **accepted after correction**. Claude's
CDR2-001 traversal fix and CDR2-002 fail-closed authorization correction are
valid. Codex found one additional P2, SEP0CR-001: section 7dc and the resume
block advanced to SEP-1, but the active separation plan still called SEP-0
"in implementation" and the Action Plan still called it the current bounded
milestone. Commit `02d7a9e` advances both sequencing authorities and adds a
three-document consistency guard. Reverting the separation-plan status made
that guard fail; restoring it returned the focused boundary/document suite to
**55 passed**. Commit `6dfc0bc` records the counter-review and retains CDR2-005
as an open P3 design issue.

Final validation on the exact counter-review tree: **4,495 passed / 0 failed /
25 warnings in 768.80 seconds** on Python 3.13.14; compileall including
`research/` passed; diff check passed; the worktree was clean before this
handoff-only update. Claude's reviewed remote head remained exact and the
shared checkout remained on `user/claude/review-sep0-boundary-20260821` at
`e195fbe`. No provider, broker, licensed data, operator database, scheduled
task, deployment, outcome run, research look, or evidence epoch was accessed
or changed. SEP-0 is accepted after correction. This branch is committed for
the owner's authorized single final push; the final report must verify the
exact remote head before SEP-1 begins.

## 7de. SEP-1 first extraction tranche (Codex, 2026-08-21)

Codex began SEP-1 on fresh branch
`codex/sep1-portfolio-snapshot-boundary-20260821` from finalized, pushed SEP-0
counter-review head `9c12ac32041f3873d59dbac593fcd1ef082aa727`.
Implementation commit `18868d3` extracts manual and Alpaca portfolio snapshot
construction into `assistant.portfolio_snapshot`, changes allocation preflight
to import that narrow module, and removes the former
`assistant.allocation_batch -> assistant.context_builder -> signals.regime`
authority path. The authority exception ledger is now empty.

The same commit moves the neutral `EvidenceStatus` and exact decimal helpers
into `data/`, preserving `assistant.schemas.EvidenceStatus` and
`assistant.money` as identity-preserving compatibility facades. Four
ML-to-assistant edges are removed, reducing the exact direct debt ledger from
**13 to 9**. The boundary suite now also refuses shared-kernel imports back
into either product. Dangerous-direction mutations independently proved that
restoring the old allocation import fails both direct and transitive guards,
and that a shared-module import of `assistant.schemas` fails the new direction
guard.

Commit `035715a` records the tranche in the active separation plan. Commit
`935c5dc` keeps the active-document state guard aligned with the review-pending
status. The first full-suite attempt exposed two stale assertions in the
repository-wide raw-decimal guard: it still required the implementation to
reside in `assistant.money.py`. No product behavior failed. Commit `7f8c47f`
points that guard at `data.financial_primitives` while retaining the assistant
facade; commit `ed46797` records the correction. Its focused
guard/precision/boundary suite passes **16 tests**. Commit `4f4d6c8` advances
the three-document state guard from "implement SEP-1" to "review the
implemented SEP-1 tranche"; the final document/boundary/decimal set passes
**61 tests**.

Final validation on the exact branch tree through handoff commit `cf9aeac`:
**4,498 passed / 0 failed / 25 warnings in 683.88 seconds** on Python 3.13.14.
The broader focused extraction
suite passed **239 tests / 17 warnings**, the final active-document/boundary
suite passed **58 tests**, and both dangerous-direction mutations failed for
the intended reason before restoration. Required compilation, diff/status,
ordered-commit, secret and remote/shared-checkout checks follow this handoff
update and are reported with the final push.

SEP-1 is **not complete**. Nine direct cross-product imports remain, including
the read-only research-result adapter and provider-neutral mandate/evidence
contracts. No physical second repository was created, no script was
classified, and no runtime authority, broker, provider, licensed data,
database, scheduled task, deployment, research outcome, or evidence epoch was
accessed or changed. This tranche stops for Claude's independent review after
the owner's authorized single final push.

## 7df. Independent review of the SEP-1 extraction tranche (Claude, 2026-08-21)

Branch `user/claude/review-sep1-extraction-20260821`, from `origin/main` at
`6499c18`. Full record:
`docs/Archive/Review/REVIEW_2026-08-21_SEP1_EXTRACTION_TRANCHE.md`. Scope: the
SEP-0 counter-review (`02d7a9e`, `6dfc0bc`, `9c12ac3`) and the eight SEP-1
commits `9c12ac3..a786074`, merged as PR #297.

**Accepted after correction.** No P0 or P1; two P2 and one P3.

**The headline claim holds, verified independently rather than by rerunning
the submitted guard.** I recomputed the transitive closure with my own
scanner: from every execution-authority module, following first-party imports
through shared and unclassified roots, **zero** paths reach strategy research.
The extraction is also behaviour-preserving where it counts — comparing the
moved functions as normalized ASTs, `build_portfolio_snapshot` and
`build_portfolio_snapshot_from_alpaca` differ only in local variable names,
one type annotation, and docstring text. Facade identity is preserved at
runtime for `to_decimal`, `EvidenceStatus`, and the snapshot builders, which
matters because `ml/contracts.py` does an `isinstance` check that a parallel
copy would have broken silently. The decimal guard was not weakened: its
allowlist moved one entry 1:1 and `data/` is genuinely in its scan scope.

Three new guards answer cautions from my SEP-0 review directly — shared kernel
may not import either product, facades must preserve identity, allocation
preflight must keep the narrow module. The first is the one I named as the
next boundary worth pinning.

**SEP1R-001 (P2).** The `EvidenceStatus` move deleted the per-member
definitions — `CONFIRMED` meaning "passed out-of-sample + all bootstrap layers
+ realistic execution/tax", and the rest — along with the per-claim-not-per-
strategy semantics and the SOXX/SOXL example that makes them usable. This
enum is the vocabulary this project's evidence discipline is written in, and
documentation is the entire enforcement mechanism for it; an undefined
`CONFIRMED` gets applied on weaker grounds and nothing in code objects.
Restored in the module that now owns the type.

**SEP1R-002 (P2).** The milestone-state guard added for SEP0CR-001 pinned five
exact literals that must **stay** true, which this module's own docstring
forbids. Not theoretical: it was written in `02d7a9e`, edited in `4f4d6c8`,
and edited again before `a786074` — twice in one session, because the
milestone legitimately advanced. Rewritten as a relationship: derive the
current milestone from the plan's status line, require exactly one heading to
mark it current, and require the other two authorities to name it. Three
mutations red, restored green; it now survives SEP-2 without an edit.

**SEP1R-003 (P3).** The moved snapshot builders kept every guard and lost the
record of which defect each closed — the lowercase-ticker miss, the two-lot
aggregation that let per-position caps be jointly exceeded, and the 2026-07-29
NaN-cash finding where `check_policy_compliance()` reported zero violations
for a corrupt portfolio — plus the caller guidance to check `is_configured()`
rather than using `AlpacaNotConfigured` for control flow. Restored.

**On the counter-review of my own SEP-0 work:** SEP0CR-001 is correct and
accepted. I advanced the handoff and Action Plan to "SEP-0 reviewed, SEP-1
next" and left the separation plan's own status calling SEP-0 current, so the
three sequencing authorities disagreed — the same defect class I had just
raised against Codex twice. The finding stands; only its guard needed
replacing.

**Where separation stands.** 13 direct edges to 9, and one authority path to
zero, with no runtime behaviour moved. The four that left were the genuinely
neutral ones, which is the right order. The remaining nine are harder and
should be expected to take longer: five are assistant→research calculation or
context imports needing the read-only adapter (a design step, not a move), and
three are evidence/mandate couplings that require deciding who owns mandate
evaluation. `scripts/` is still unclassified and uncounted, and is still where
the real work is.

Validation: full suite **4,498 passed / 0 failed / 25 warnings** in 823.40
seconds on Python 3.13.14 — the same count Codex reported for the
submitted tranche, reproduced independently. That run covered every code
and test correction in this round; the later documentation edits (this
section, the review report, the plan status) changed no test count, and
the document guards were rerun green after each. `compileall`
over the required surface passed; `git diff --check` passed; the focused
document, separation, decimal-guard, ml-boundary and context-builder suites
passed **109/109**, rerun after every edit including after these counts were
inserted.

Untested surface, stated plainly: this round changed one enum's documentation,
two docstrings, and one guard. The moved production code was verified
equivalent by AST comparison and by the existing suite, not by new behavioural
tests — SEP-1 deliberately added none, because it moved code rather than
changing it.

## 7dg. Counter-review of Claude's SEP-1 review (Codex, 2026-08-21)

Codex counter-reviewed exact remote
`origin/user/claude/review-sep1-extraction-20260821` at
`a728ebc907d9f21c660e6c6dff569129f57ca0bd` in isolated branch
`codex/counterreview-sep1-extraction-20260821`. The remote DAG merge-base is
the exact submitted SEP-1 head `a7860747dc2f33a902c871a5c247f74b7e956eff`;
mainline integration `6499c18` and Claude commits `ffb2208`, `4ca744a`, and
`a728ebc` each have an explicit disposition in
`docs/Archive/Review/COUNTER_REVIEW_2026-08-21_SEP1_EXTRACTION_TRANCHE.md`.

**Accepted after correction.** No P0 or P1; one P2 and one P3.

**SEP1CR-001 (P2, resolved).** Claude correctly replaced a guard that pinned
milestone-specific literals, but the replacement only required `SEP-1` to
appear somewhere in each long historical document. It passed while this
handoff's canonical resume prompt still told the next session to review the
already-reviewed SEP-1 branch. The strengthened guard now derives the
milestone id from the plan but scopes the matching marker to the Action Plan's
current sequencing amendment and to handoff sections 8 and 9. It failed red
against the stale handoff before these two current sections were corrected.

**SEP1CR-002 (P3, resolved here).** Claude's report says five
assistant-to-research calculation/context imports plus three evidence/mandate
couplings remain, but its own list contains **six** calculation/context edges:
context builder (1), explanations (2), stock lookup (1), and strategy
proposals (2). Six plus three is the manifest's exact nine. The historical
review remains intact; this section and the counter-review are the correction.

The substantive acceptance is unchanged. The manifest contains nine direct
cross-product edges and no authority exception; execution-authority roots
cannot reach strategy research; shared modules do not import either product;
facades preserve runtime identity; compatibility and monkeypatch seams pass;
and portfolio/broker behavior is unchanged. CDR2-005 remains an explicit open
P3 concerning dynamic-import census and first-path reporting asymmetries.

Counter-review test correction `9949983` strengthens the relationship guard;
review-record commit `af4f83e` preserves all dispositions and findings.
On the corrected code/test tree, the focused document, separation, decimal,
ML-import, context-builder, and allocation suite passed **157 tests / 1
dependency warning in 39.00 seconds**. The complete suite passed **4,498 tests
/ 0 failures / 25 dependency warnings in 698.14 seconds** on Python 3.13.14.
Required compilation, including `research/` and `tests/`, passed; the boundary
JSON parsed with exactly nine direct edges and zero authority exceptions; and
`git diff --check` passed. Active-document and separation checks are rerun
after these final documentation inserts. No provider,
credential, broker, licensed data, operator database, scheduled task,
deployment, backtest, outcome, research look, or evidence epoch was accessed
or changed. SEP-1 remains incomplete and no feature milestone was recorded.

## 7dh. SEP-1 second neutral-contract tranche (Codex, 2026-08-22)

After the owner merged the accepted SEP-1 counter-review, Codex continued on
fresh isolated branch `codex/sep1-research-contracts-20260821` from merged
main `d97d1d88b36aa099302b97f386113e441c1ce587`. Product/test commit
`636d164` removes five of the nine remaining direct product crossings while
preserving every existing public import path by exact object identity.

Three product-neutral contracts now own the previously misplaced behavior.
`data.portfolio_metrics` owns portfolio/risk statistics,
`data.mandate_evaluation` owns structural metric-versus-limit evaluation, and
`data.research_statistics` owns Bonferroni arithmetic. Volatility measurement,
threshold calibration, and regime classification move to the existing neutral
`market_analytics` root. The old `backtest.risk_metrics`,
`backtest.research_report`, `backtest.engine`, `assistant.mandate`, and
`signals.regime` import surfaces remain compatibility facades or re-exports;
tests prove they resolve to the canonical object rather than a parallel copy.

Assistant context construction, stock lookup, paper evidence, and research-look
accounting now depend on the neutral implementations. The machine ledger is
therefore exactly **four direct cross-product imports** and **zero authority
exceptions**. The four retained imports are intentionally policy-heavy:
`assistant.explanations` to `signals.breakout` and `signals.scanner`, plus
`assistant.strategy_proposals` to `signals.regime` and
`strategies.vol_target_rotation`. They require typed, read-only result adapters
in the next tranche; moving those calculations into shared code would conceal
product ownership rather than solve it.

Focused affected-module validation passed **200 tests / 1 dependency warning**.
The complete repository validation and exact published head are reported with
this branch's owner handoff. No provider, credential,
licensed row, broker, operator database, task, deployment, backtest, outcome,
research look, or evidence epoch was accessed or changed. SEP-1 remains
incomplete; no feature milestone is recorded, and `scripts/` classification
remains SEP-2 work.

## 7di. Independent review of the second SEP-1 tranche (Claude, 2026-08-22)

Branch `user/claude/review-sep1-contracts-20260821`, created from the exact
pushed head `52f4c2f` (merge base `d97d1d8`). Full record:
`docs/Archive/Review/REVIEW_2026-08-22_SEP1_CONTRACTS_TRANCHE.md`. Scope: the
three tranche commits `636d164`, `e36f480`, `52f4c2f`, plus formal
dispositions for the three PR #298 counter-review commits (`9949983`,
`af4f83e`, `92b9a1b`) that revised my own prior corrections.

**Accepted after correction. No P0/P1/P2; one P3.** The cleanest tranche of
the separation so far, and the largest calculation move.

What was verified independently rather than accepted from the submission:
all thirteen moved functions (plus `compute_portfolio_metrics`) AST-compared
old-tree-vs-new — every difference is annotation, rename, temp-fold, one
unpinned error-message rewording, or a benign `float()` cast; **the owner's
approved mandate fingerprint recomputes stable** against
`assistant/default_mandate.json` (the move could not silently invalidate the
2026-08-04 approval, and did not); exception identity preserved by
same-object aliasing (`PortfolioMetricsError` imported *as*
`ResearchReportError`, base class `ValueError` unchanged); facade identity
holds at runtime across all eleven public seams; the independent census
finds exactly the **4** declared edges (9 → 4) with **zero**
authority-to-research paths; the shared modules import no product code; and
a mutation restoring the removed `research_looks -> backtest.engine`
crossing turns the census guard red.

**SEP1B-001 (P3, corrected):** third consecutive tranche in which moved code
arrives intact and its recorded reasons do not. Restored at the new
canonical locations: the 2026-07-31 P2#5 bool-rejection rationale in
`_metric_check`; the round-before-int float-imprecision rationale in
`expected_shortfall_pct`; and `calibrate_volatility_threshold`'s
apply-the-same-value-to-confirmation discipline sentence — the look-ahead
rule that justifies the function's existence. Graded P3 rather than
repeating SEP1R-001's P2 because the class is narrowing: `_capture_pct`
kept its joint-masking rationale (with the reproduced 50%→16.67% figure)
and `expected_shortfall_pct` gained a fails-closed docstring.

On the counter-review of my own work: **SEP1CR-001 accepted and verified by
guard-swap** — my guard passed against my own documents while Codex's failed
against the same documents, so my `assert current in text` was vacuous
against the 344 KB handoff; Codex's canonical-marker fix keeps the
no-literal-milestone-id property. **SEP1CR-002 accepted** — my
five-plus-three arithmetic was wrong; my own parenthetical listed six.

Also recorded: the shared kernel grew by three modules under plan §2's
"or be split as ownership becomes clear" clause, with the plan's new policy
line ("putting their calculations in the shared kernel would hide product
policy rather than separate it") correctly fencing the four remaining
policy-heavy edges into adapter work, not moves.

Validation on the final tree: full suite **4,498 passed / 0 failed / 25
warnings** in 772.28 seconds on Python 3.13.14 — identical in count to my
independent run of the submitted snapshot (764.37 s), because this round's
corrections are comments, docstrings, and documents only;
`compileall` over the required surface passed; `git diff --check` passed;
focused boundary/document/metric/mandate/regime suites passed (89 + 100
across the two focused runs), rerun after every edit including after these
counts were inserted. Mutation evidence: census-guard red on a restored
crossing; fingerprint stability re-verified after the corrections.

Untested surface, stated plainly: the equivalence argument rests on AST
comparison plus the existing suites; no new behavioural tests were added
because the tranche moves code rather than changing it, and the one
observable change (an unpinned error message) is asserted by nothing.

## 7dj. Codex counter-review of SEP-1 contracts review (2026-08-22)

Codex counter-reviewed exact Claude remote head `dd30257` on isolated local
branch `codex/counterreview-sep1-contracts-20260822`. Exact ordered Claude
range: `e6384b7`, `072382b`, `dd30257`, based on submitted Codex head
`52f4c2f`. Full record:
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP1_CONTRACTS_TRANCHE.md`.

**Accepted after correction.** Claude's SEP1B-001 is confirmed: all three
rationales existed before the move, accurately explain dangerous behavior,
and were restored without changing code. The four-edge import census, zero
authority exceptions, shared-kernel direction, runtime alias identity, and
approved mandate fingerprint were reproduced independently.

Three P3 corrections close here. **SEP1CCR-001:** Claude's report
enumerates **twelve**, not eleven, compatibility seams. Same-object runtime
identity and `except ResearchReportError` behavior are preserved, but the
moved exception now reports `data.portfolio_metrics.PortfolioMetricsError` as
its module/name metadata, so no byte-for-byte exception-serialization claim is
made. **SEP1CCR-002:** the prior blanket licensing blocker is superseded.
Massive's investment-advice disclaimer is not a personal-research ban, and
its Analyst Ratings documentation explicitly lists backtesting rating impact
as a use case. A separate permission letter is not automatically required.
Before QuantConnect custom-data processing, verify the purchase-specific order
form and additional terms; they may already grant the use, and this review has
not inspected them. This wording correction authorizes no provider call,
upload, data work, backtest, or research look. **SEP1CCR-003:** the permanent
facade guard pinned only 8 of the 12 function aliases and omitted the exception
alias despite Claude's broader manual check. It now pins every function seam
and `ResearchReportError is PortfolioMetricsError`.

Validation on the final counter-review tree: focused affected suites **253
passed / 0 failed / 1 warning** in 33.62 seconds; complete suite **4,499 passed
/ 0 failed / 25 warnings** in 699.19 seconds; required `compileall` including
`research/` passed. No product code changed; SEP-1 remains incomplete, its
four policy-heavy crossings remain exact, and no feature milestone is
recorded. Ordered local commits before this final handoff commit:
`5fcdd41` (complete facade-identity guard), `43d49c7` (counter-review record and
plan precision), and `c89a900` (ratings-terms correction and regression
guard). The counter-review branch is local-only pending owner push instruction.

## 7dk. SEP-1 final research-result adapter tranche (Codex, 2026-08-22)

After completing the counter-review in section 7dj, Codex continued on fresh
branch `codex/sep1-research-result-adapters-20260822`. Product/test commit
`a8c2b77` removes SEP-1's final four direct cross-product imports without
moving research policy into the shared kernel.

The new boundary has three pieces. `data.research_results` defines immutable,
provider-neutral measurement contracts. `research.assistant_results` owns the
existing scanner, trend, volatility, and target calculations.
`scripts.product_composition` is the temporary mixed-root entry-point seam
that builds those results and supplies them to the assistant. The assistant
no longer imports a signal or strategy module; neither product imports the
temporary seam or the other product.

The proposal result is bound to the exact stable/leveraged ticker pair,
as-of timestamp, ordered close histories, and current production parameters.
The assistant refuses missing results and rejects wrong tickers, altered
history, changed parameters, mismatched dates, malformed values, or targets
above the configured leveraged cap. The explanation path likewise refuses a
missing or wrong-ticker result rather than silently displaying no trigger.
Production UI and CLI entry points now use the composition seam. Proposal,
policy, human approval, paper broker, reconciliation, operator database, and
execution authority are unchanged.

The machine-readable ledger now contains exactly **zero direct product
crossings** and **zero execution-authority exceptions**. Guards require both
counts to remain zero, prevent either product from importing the temporary
composition module, and pin result immutability and the altered-history
refusal. `scripts/` remains deliberately unclassified until SEP-2.

Validation on the final tree: affected boundary/behavior suites **87 passed**;
assistant UI/CLI/module-hygiene suites **205 passed**; active-document plus
boundary checks **61 passed**; complete suite **4,505 passed / 0 failed / 25
warnings** in 684.12 seconds; required compilation including `research/`
passed; `git diff --check` passed. No provider, licensed row, broker, task,
deployment, operator database, backtest, outcome, research look, or evidence
epoch was accessed or changed. The shared operational checkout remained clean
on `user/claude/review-sep1-contracts-20260821` at exact head
`dd302570fe25654cc516d178cae7e2722138ce11`.

**Next:** Claude independently reviews the exact pushed implementation head.
SEP-1 is implementation-complete but not review-complete; SEP-2 must not begin
until Claude's review and Codex counter-review close this chain. No feature
milestone is recorded yet.

## 7dl. Independent review of the SEP-1 adapter tranche (Claude, 2026-08-22)

Branch `user/claude/review-sep1-adapters-20260822`, created from the exact
pushed head `71d8500` (based on my own prior head `dd30257`). Full record:
`docs/Archive/Review/REVIEW_2026-08-22_SEP1_ADAPTER_TRANCHE.md`. Scope: all
seven commits — the counter-review of my second-tranche round and the final
adapter implementation.

**Accepted after correction. No P0/P1/P2; two P3.** The hard tranche, done
the way this repository does things: refusals instead of defaults, hashes
instead of trust, authority untouched.

Verified independently: **zero** cross-product edges (4 → 0) and **zero**
authority-to-research paths on my own scanner; no product imports the
temporary `scripts/product_composition` seam, and the research producer
imports nothing from the assistant. The assistant re-derives every binding
it can check itself — ticker pair, as-of date, parameters SHA-256, exact
close-series SHA-256s — and refuses mismatches; a missing result raises
rather than reading as "no rebalance" or "no signal"; the pair-not-held path
returns `[]` before any result use, checked in source order. The producer
reproduces the old inline trend/vol-target sequence exactly, and the UI/CLI
swap is import-aliasing onto wrappers that keep the old signatures, so both
existing call sites and the Briefing double-fetch optimization survive.
Stated plainly: binding hashes prove the result was computed *for* those
inputs, not *correctly from* them — trust is unchanged from when the same
code was imported directly, and every target still passes the deterministic
gate, policy caps, and typed approval.

**SEP1C-001 (P3, corrected):** the assistant-side cap refusal (research
target above `max_leveraged_weight` must raise) had no regression coverage —
the producer self-caps, so no honest fixture can reach the check with a
violating value. Added the test; mutation red with the check disabled, green
restored.

**SEP1C-002 (P3, corrected):** the licence-boundary correction rests on a
claim about a live vendor page. I verified it at the source on 2026-08-22 —
Massive's Analyst Ratings documentation lists "Market sentiment tracking,
portfolio alerts, **backtesting rating impact**, trend analysis", with no
restriction language on the page — and added the dated URL-and-quote note to
the freeze bullet, with an instruction to re-verify or preserve bytes before
any preregistration relies on it. The correction itself is **accepted**: it
changes the presumption, not the gate — verify-before-upload survives,
"any ratings representation" keeps the breadth, and nothing is authorized.

On the counter-review of my own round: **all three findings accepted.**
SEP1CCR-001 — I called twelve seams eleven, my second arithmetic slip in two
rounds, and my serialization wording outran my evidence. SEP1CCR-003 — my
manual identity census exceeded the guard I actually shipped. Both of
Codex's fixes are right.

**SEP-1's implementation side is complete against its definition of done:**
authority path removed first, neutral contracts extracted, calculation
imports replaced with typed input-bound results, ledger 13 → 9 → 4 → 0 with
no exception broadened, and all proposal/approval/execution/reconciliation
authority still solely in the trading assistant. Per the rule the submitted
tree itself records, SEP-1 is *marked* complete — and its feature-milestone
entry written — only after Codex counter-reviews this review's corrections.

Validation on the final tree: full suite **4,506 passed / 0 failed / 25
warnings** in 710.36 seconds on Python 3.13.14 — Codex's claimed 4,505
plus this round's one new cap-refusal test. (An earlier run reporting the
same 4,506 was discarded as non-validating: my test was appended and a
two-second mutation ran while it executed, so it validated neither tree;
the count above is a clean rerun on the exact final tree.) Codex's own
4,505 / 0 / 25 for the submitted snapshot is accepted on its record;
`compileall` over the required surface passed; `git diff --check` passed;
focused separation/strategy/explanation/document suites **141 passed** plus
doc guards **53/53**, rerun after every edit including after these counts
were inserted. Mutations: cap-check disable → new test red; both verified
restored byte-identical.

Untested surface, stated plainly: the equivalence argument for the moved
strategy logic rests on side-by-side source comparison and the existing
suites; the composition seam is exercised by the new generic-pair tests but
not by a live UI session in this review.

## 8. What is next

**Current implementation sequencing (owner, 2026-08-21):** **SEP-1 is the
current bounded milestone.** SEP-0 is accepted after correction (sections
7dc–7dd). SEP-1's first extraction tranche is
implemented in section 7de and **independently reviewed in section 7df
(accepted after correction)**. Its second neutral-contract tranche is
implemented in section 7dh and **independently reviewed in section 7di
(accepted after correction)**. Its final research-result adapter tranche is
implemented in section 7dk and **independently reviewed in section 7dl
(accepted after correction; two P3 corrections awaiting Codex
counter-review)**; the direct crossing
and authority-exception counts are both zero. SEP-1's implementation is
complete against its definition of done, and it is marked complete — with
its feature-milestone entry — only after Codex counter-reviews the 7dl
corrections. The former pinned
`assistant.allocation_batch -> assistant.context_builder -> signals.regime`
authority path is removed. ACER remains the first
research program, but its next Cloud capability audit is not the current code
implementation task. The separation work grants no outcome-run, vendor,
broker, deployment, database, task, or epoch authority.

**One owner decision is waiting (CDR2-002):** whether the read-only,
zero-outcome capability audit of the Massive and QuantConnect accounts is
authorized. Action Plan §7 item 1 lists it as open and the documents now read
fail-closed; if it was meant to be granted, say so and both flip together.

**Current (2026-08-20, superseding everything below):**
`docs/ACTION_PLAN_2026-08-20.md` is the go-to plan and puts the
**Analyst-Consensus ETF Rotation program (ACER)** first. SBP is superseded and
its capture task must not be installed. Snapshot A's structural audit is
accepted after correction, and the counter-review of that correction is
complete (section 7ca): one factual premise in the review was overturned by
byte-level measurement, the frozen timing rule was kept on its honest
rationale, and every structural hardening was verified end to end. The
review chain for the vendor audit is closed. The event backbone was
implemented in section 7cb and independently accepted after correction in
section 7cc: 584,916 canonical events at 99.64% retention, with issuer
identity deliberately unresolved. That review chain closed with the
counter-review in section 7cd, which confirmed all seven findings and fixed
two defects in the corrections; the whole round is merged.

**ACER-0A owner decisions are partially frozen and independently corrected**
(sections 7ce–7cf,
`docs/research/ACER_2026-08-20_ACER0A_FREEZE.md`): six cells, a named primary,
Bonferroni 0.05/6, a provisional two-slot budget, and numeric point-in-time
stock thresholds. The executable preregistration is still incomplete.
**ACER-0B is deliberately not frozen** and ACER-3's budget is zero until it
is. QuantConnect Cloud is the authoritative ACER historical/outcome backtest
engine; local LEAN is development/test-only. The purchase-specific terms for
processing a ratings representation through QuantConnect remain unverified;
neither permission nor prohibition is presumed, and no upload is presently
authorized. Current QC authority is read-only, zero-outcome structural
auditing only.

What ACER needs next, in order: close the ten named open items
(ACER-0A.1–0A.10). **Independently corrected proposals now exist for 0A.1 and
0A.5–0A.9**
(`docs/research/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`) and are
accepted as drafts after the review in section 7cl, but still await owner
confirmation — they are not freezes. Then run the $99
one-month Benzinga
Earnings **structural audit** and only then adopt or reject that control
dataset and freeze the standardized-surprise formula; and run Snapshot B
after the declared interval.

The current EDGAR/yfinance path cannot satisfy the frozen delisted-outcome
requirement and is not the selected execution path. **QuantConnect Cloud
capability and semantics remain unmeasured for ACER.** The already reviewed
Databento capture/reference/vintage-adjustment modules remain an unmeasured
fallback candidate for requirements the cloud audit cannot close, especially
terminal delisting returns. Any such fallback audit must establish access,
history, known-delisted coverage, terminal-return semantics, price/volume and
corporate-action completeness, licence, and cost before any purchase,
download, or outcome work.

The provider-neutral capability checker now carries eleven required
capabilities and reports one available, five unavailable, five unmeasured, ten
blocking and `acer2_runnable=false`. Databento is a separate unmeasured
provider diagnostic, not a twelfth requirement. The checker cannot substitute
for an external audit of whichever market/reference provider is selected.

**The issuer-mapping step is BLOCKED pending the QuantConnect Cloud structural
audit (sections 7ch–7ci and 7cw–7cy).** Local LEAN, authentication, Docker, and
the bundled sample execution are verified but are not the ACER backtest path.
Credentials and a working engine do not prove cloud access, coverage, or
semantics for the required security master. The next authorized technical
step is a narrow read-only, zero-outcome QC cloud audit; audit Databento or
nominate another source only for requirements the cloud path cannot close.
Do not purchase/download local QC datasets under the current engine ruling.
This cannot be
deferred by improving the heuristic: name evidence provably misses the
BBBY-class reuse, so the 2,885 flagged tickers are a lower bound and an
unflagged ticker is `no_name_based_ambiguity_evidence`, not established as
safe. The corrected deterministic interleaving count is 768. **ACER-2 remains
the decisive milestone:** a null primary result closes the program. No
purchase beyond the authorized $99 audit, no ACER price or outcome join, no
ACER backtest, no QC upload, and no paper execution is authorized. LEV remains
separate and cannot validate ACER. The SBP history is retained, and SBR-1 is
now closed on a measurement rather than an assumption.

**Review status of the current mainline (added 2026-08-21, section 7cz).**
The whole Codex range `25cc6d4..98e1d63` is merged **and independently
reviewed**; nothing on `main` is awaiting review. The corrections from that
review are on `user/claude/review-codex-doc-lifecycle-20260821`. Two of them
change where a reader must look: the permanent run ledger is
`docs/research/alpha-result.md` (not under `docs/Archive/`), and freeze §8
now authorizes read-only, **zero-outcome structural** QuantConnect work
rather than symbol mapping alone — which is what makes the scheduled cloud
capability audit consistent with its governing document. Section 7dj
supersedes the blanket permission-letter interpretation: personal research is
not prohibited by the investment-advice disclaimer, while the applicable
order form and additional terms still need to be checked for the selected
QuantConnect custom-data processing. Raw rows, normalized events and derived
features must not be presumed either transferable or prohibited before that
terms check.
QuantConnect separately offers Download licences for local internal LEAN use,
but this project has not purchased or authorized that route and the owner has
selected Cloud as the authoritative ACER engine.
Section 7da counter-reviews Claude's exact `cc05ce7` review head, retains all
eight submitted corrections, and closes four counter-review findings: the
licensing premise, the adjacent-sentence guard gap, the 139/68/71 report
migration count, and the stale request to re-authorize the already authorized
cloud audit.

### Historical superseded checklist (retained for audit only)

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
prospective 24-month stream. The SBP counter-review and its independent
verification are merged into `main` by PR #282. The owner
should first review the corrected proposed values in
`docs/Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md`. If accepted, SBP-0 must
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
   `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md`
   (Cursor) and
   `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`
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
3. Append every execution to `docs/research/alpha-result.md`; never rehabilitate or
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
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-20.md,
docs/SESSION_HANDOFF.md, docs/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md,
docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md,
docs/Archive/Review/REVIEW_2026-08-20_ACER1_BENZINGA_AUDIT.md,
docs/Archive/Review/REVIEW_2026-08-20_ACER_EVENT_BACKBONE.md,
docs/Archive/Review/REVIEW_2026-08-20_ACER0A_FREEZE.md,
docs/Archive/Review/REVIEW_2026-08-21_ACER_PREREG_AND_LOCAL_DATA_AUDIT.md,
docs/Archive/Review/REVIEW_2026-08-21_ACER_DATABENTO_CAPABILITY.md,
docs/research/BENZINGA_RATINGS_2026-08-20_DATA_AUDIT.md,
docs/operations/OPERATIONAL_FACTS.md,
docs/research/ACER_EVENTS_2026-08-20_BACKBONE_COVERAGE.md, and
docs/research/ACER_2026-08-20_ACER0A_FREEZE.md, and docs/research/alpha-result.md.
The vendor-audit and event-backbone review chains are closed and merged
(sections 7ca and 7cd). Codex is now the implementer and Claude the reviewer.
Sections 7cv–7cy are **merged mainline**. PRs #293, #294 and #295 put
`2f4e41d`, `a1dc779`, `0a94bef`, `b0f7dec`, `ce066a8`, `3cefeb1`, `2ec7f61`
and `0bd5fff` on `main` at `98e1d63`. Section 7cz is Claude's independent
review of that whole range; section 7da is Codex's counter-review of exact
Claude head `cc05ce7`, accepted after four corrections. **QuantConnect Cloud is now the
authoritative ACER backtest engine (7cy); local LEAN is development/test
only.** **ACER-0A decisions are partially frozen,
but its executable preregistration is incomplete; ACER-0B is deliberately
not frozen.** The dataset
identity is `acer-analyst-events-73c36f9de1841b0a` and has not been
materialized; earlier ids are superseded. Stage 0/1 and APQ are valid but
closed null; SHW-4 is prospective. SBP is superseded by ACER and SBR-1 is
closed on a measurement. The CCPR-001 truncation percentages are withdrawn:
they did not isolate the proposed state-semantics choice. The current
EDGAR/yfinance path cannot support ACER's delisted outcomes, but Databento is
an existing **unmeasured candidate**, not a validated solution. The corrected
capability checker reports eleven required capabilities — one available, five
unavailable, five unmeasured and ten blocking — and refuses incomplete
checklists or provider diagnostics; Databento is separately reported as an
unmeasured optional provider. It does not replace vendor evidence. **SEP-1 is
the current bounded milestone.** Its first extraction tranche was independently
reviewed and accepted after correction in section 7df. The second SEP-1
neutral-contract tranche is implemented in section 7dh on
`codex/sep1-research-contracts-20260821` and was independently reviewed and
counter-reviewed in sections 7di–7dj. The final adapter tranche is implemented
in section 7dk on `codex/sep1-research-result-adapters-20260822` and awaits
Claude's independent review. It reduces the exact direct-crossing ledger from
four to zero without an authority exception. Review that exact pushed head;
do not reopen the first two tranches. SEP-2 must wait until this review chain
closes under `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`. ACER
remains the first research program, and its next research step is the narrow read-only,
zero-outcome QuantConnect Cloud capability audit (entitlements, coverage,
semantics) -- which Action Plan section 7 item 1 still lists as an OPEN
owner decision covering both the Massive and QuantConnect accounts, so
obtain that authorization before any provider call. Before any ratings
representation is processed through QuantConnect custom data, verify the
purchase-specific order form and additional terms. Massive's
investment-advice disclaimer does not ban personal ACER research, its Analyst
Ratings documentation names backtesting rating impact as a use case, and a
separate permission letter is not an automatic blocker. Do not assume either
permission or prohibition without the applicable terms. The current Codex process
can see names-only Massive and QC credential variables, but this does not
establish entitlements. Once authorized, stay inside freeze §8's read-only,
zero-outcome scope limit and measure access, coverage, licence, and cost
without joining outcomes. Also close ACER-0A.1–0A.10, run the separately
authorized Benzinga Earnings
structural audit before adopting that control dataset, resolve issuer mapping
with ambiguity refusals, and take Snapshot B after the declared interval.
Local LEAN is installed and verified (CLI `1.0.228`, workspace
`C:\QuantConnect\ACER`, Docker `29.7.2`, sample run through Engine `2.5.0.0`)
on the epoch host, but it is NOT the ACER backtest path. A shell opened before
that install may not have `lean`/`docker` on `PATH`; use the full executable
paths. Do not upload reconstructable ratings until the purchase-specific
third-party-processing terms are verified. Do not join ratings to prices or outcomes, run
a backtest, deploy, trade,
acknowledge or alter an operational alert, mutate an operational database, or
roll paper-epoch-006 without separate authorization.
```

## 9a. Archived 2026-08-17 resume prompt (historical only)

```text
Read CLAUDE.md, docs/Archive/Plans/ACTION_PLAN_2026-08-02.md,
docs/Archive/Plans/Alpha_Test_Implementation_Plan.md,
docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md, docs/research/alpha-result.md and
docs/SESSION_HANDOFF.md. origin/main is b6f577e after PR #244 merged Claude's
Stage 0 correction counter-review head 9a7e9fc with an identical tree. PR #243
at 4151b3f merged Fable's final counter-review (PR #242 at f937bfb merged the
counter-review integration branch; PR #241 at d8a3260 merged the full audit
before it). Corrections
855941a and 1e2b631 repair current LEAN Python
syntax, point-in-time/exact-session factors, Stage 1 cadence and benchmark,
strict analyzer provenance, bounded QC polling, old local turnover/NAV,
leave-one-out peers and joint residual regression. Invalid generated result
files were removed only after docs/research/alpha-result.md preserved their exact
hashes and dispositions (ledger hashes are CRLF working-tree hashes — see
the ledger's verification-convention note). No QC access or new result
occurred; every old result
is unusable, the lifetime floor remains 428, and no alpha milestone completed.
Claude counter-reviewed exact head b4e9ee0 (section 7m, three P3 closures
CR2-001..003), Codex independently accepted ad3b3a8 after a topology
correction (section 7n), and a final independent Claude counter-review of the
whole ten-commit chain from exact head 5730f7b (section 7o and
docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md) accepted every
commit, ran sixteen mutations, and closed four P3 gaps (CCR3-A..D) on branch
user/claude/alpha-qc-full-counterreview-20260817. Codex then reviewed Fable's
exact three-commit range after PR #243 and found two P2 Stage 0 methodology
defects plus two P3 input/refusal defects. Correction ac96d47 fixes same-period
entry/exit turnover, per-family 12/42 annualization, strict MAX(20), and
missing-industry grouping; see section 7p and the Fable-counterreview report.
Claude then pushed that branch unchanged at exact head 9e45803 and
counter-reviewed it (section 7q and
docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_CORRECTION_COUNTERREVIEW.md):
all three commits accepted, all four findings reproduced red pre-correction,
seven mutations run, and two follow-up P3 closures (FCR-001 exit-drift pin,
FCR-002 Stage 1 dead-state industry port) on branch
user/claude/alpha-qc-fable-cr-verify-20260817. Codex then independently
accepted its exact three-commit range and FCR-001/002 after one P3 test-only
hardening: helper correctness did not prove the live Stage 1 ingestion called
the helper, so commit 39e5d99 pins all three `_fine` call sites and stale-code
eviction. No algorithm behavior changed. See section 7r and
docs/Archive/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md.
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
