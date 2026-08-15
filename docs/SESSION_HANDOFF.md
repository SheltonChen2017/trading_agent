# Session handoff — REBAL-1 Stage 3 reviewed and counter-reviewed

Prepared: 2026-08-15 by Claude, after counter-reviewing Codex's independent
review and correction of Stage 3.

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
- `main` and `origin/main`: `45faf1c8259b622a70a805f5b2c679cd6a0be53f`
  (PR #229, Stage 2 counter-review merge).
- Pushed implementation branch:
  `origin/user/claude/rebal1-stage3-tax-aware-trims-20260815`.
- Pushed implementation head:
  `bedeea2bd6a5c6639bff071ac18c8714cda1b8c3`.
- Exact ordered reviewed range from base `45faf1c`:
  1. `0490d9d95dabc0eee190c84e766ca5203a0ccc1e` — product/tests.
  2. `bedeea2bd6a5c6639bff071ac18c8714cda1b8c3` — records.
- Review branch: `codex/review-rebal1-stage3-20260815`.
- Product/test correction:
  `ed6879d5c56ecfa5435b5b73dc661f038add11d5`.
- The documentation commit is the commit containing this handoff, created
  after `ed6879d` as the required separate records commit.
- **The review branch and both review commits are local-only. They have not
  been pushed, merged, or opened as a PR. Another computer cannot fetch them
  until the owner authorizes and performs a push.**
- The worktree must be clean after the documentation commit. Recheck `HEAD`
  and `git status` before any further action because this checkout is shared.

Required historical anchors retained for recovery and topology checks:

- `4de784e` / `1cb8abf` are the epoch-005 observation-clock roll chain and
  its independent correction; `c048a94` records the later owner decision to
  leave that epoch unchanged for 60 days.
- The completed BUY-1 review branch
  `codex/review-buy1-suggestion-picker-20260813` and correction `44a7f85`
  remain historical recovery context. BUY-1 is merged; this is not an
  instruction to reopen or switch to that branch.

The formal review followed the new standing rule: it began only after the
implementation was committed and pushed, then branched from the exact fetched
remote head. Local or uncommitted Claude work was not reviewed.

## 2. Review outcome and commit dispositions

**Accepted after correction.** REBAL-1 Stage 3 now meets its development
definition of done. It remains unmerged and undeployed.

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

## 8. What is next

1. The owner may merge `user/claude/rebal1-stage3-counterreview-20260815`,
   which carries Codex's review commits and the counter-review on top, as a
   single PR. `codex/review-rebal1-stage3-20260815` needs no separate push;
   its commits are contained in this branch.
2. Codex may independently verify the counter-review correction. Note for
   the record: Codex's new rule that formal review starts only from a pushed
   remote snapshot was added in `0c91aa4`, and this counter-review was
   necessarily performed on a LOCAL-only review branch, because that branch
   was never pushed. Pushing this branch makes the whole range remote and
   restores the rule going forward.
3. REBAL-1 has no Stage 4 in the adopted plan. Any new rebalancing feature
   needs a new owner-approved plan and scope.
4. Resolve whether the 60-day hold means calendar days or 60 captured market
   sessions before any operational transition.
5. The SET-1 design question remains open: whether strict whole-share mode
   should allow a fractional sell only when it closes an entire position.
6. `TRADE1CR-002` remains open and unscheduled: date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` can fail between roughly 00:00
   and 09:30 ET.

Do not begin M4, deploy, mutate the operator database, alter scheduled tasks,
access a funded account, enable live trading, submit a paper order, or roll an
epoch without a new explicit owner instruction.

## 9. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/REBAL1_MILESTONE_PLAN.md, docs/REVIEW_2026-08-15_REBAL1_STAGE3.md,
and docs/SESSION_HANDOFF.md. main/origin/main are 45faf1c. Claude's pushed
REBAL-1 Stage 3 head is bedeea2 (0490d9d product, bedeea2 records). Codex
reviewed that exact remote range on codex/review-rebal1-stage3-20260815 and
accepted it after product/test correction ed6879d plus the separate records
commit containing this handoff. The review branch is LOCAL ONLY: do not claim
cross-computer availability until the owner authorizes a push and origin is
verified. Eight P2 and one P3 findings are closed; none remain open. Final
validation is 243 focused and 4,026 full-suite tests, 25 known warnings, clean
compile/diff. All three REBAL-1 stages are complete in development but not
deployed. Formal reviews now begin only from a pushed remote branch and exact
remote head. Do not push, merge, deploy, roll epoch-005, mutate operational
state, submit orders, access funded accounts, begin M4, or enable live trading
without explicit owner authorization.
```
