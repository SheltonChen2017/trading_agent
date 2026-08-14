# Session handoff — SET-1 counter-review independently verified after correction

Prepared: 2026-08-14 by Codex after independently verifying Claude's SET-1
counter-review and PR #218 merge.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REVIEW_2026-08-14_CODEX_SET1_COUNTERREVIEW.md`
4. `docs/REVIEW_2026-08-14_SET1_COUNTERREVIEW.md`
5. `docs/REVIEW_2026-08-14_SET1_SETTINGS_AND_FRACTIONAL_TRADING.md`
6. `docs/REVIEW_2026-08-14_TRADE1_DISCRETE_TRADING.md`
7. `docs/REVIEW_2026-08-13_OBSERVATION_CLOCK_AND_EPOCH005_ROLL.md`
8. `docs/OPERATIONAL_FACTS.md`
9. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes merge, deployment, an evidence-epoch roll, M4, live
trading, funded-account access, operator-database mutation, or a
scheduled-task change. The owner separately authorized this branch's
publication on 2026-08-14.

## 1. Repository topology and remote availability

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Current `main` and `origin/main`: `7055142` (PR #218), which merged Claude's
  SET-1 counter-review `45a510c`. PR #217 merge `ca0cdf0` is its first parent.
- Codex's SET-1 review branch `codex/review-set1-settings-toggles-20260814`
  is MERGED. Its product/test correction is `89156b7`; its records are
  `6b944ac`, `d4d43cf`, and `55a1110`.
- Claude's counter-review branch `user/claude/set1-counterreview-20260814`
  is MERGED through PR #218. It carries SET1CR-001 … SET1CR-004 and
  `docs/REVIEW_2026-08-14_SET1_COUNTERREVIEW.md`.
- Active branch: `codex/review-set1-counterreview-20260814`, based on exact
  main `7055142`. Product/test correction `29290d9` closes CSET1CR-001 … 003;
  the commit containing this handoff closes the post-merge record drift
  CSET1CR-004. The owner authorized publication on 2026-08-14; the branch
  tracks `origin/codex/review-set1-counterreview-20260814` and the commit
  containing this publication-state update is remotely retrievable.
- Merged-branch cleanup ran on 2026-08-14: twelve merged branches were
  deleted (five local, seven remote). Two unmerged branches were deliberately
  KEPT and are content-redundant with `main`:
  `user/claude/discrete-trading-tabs-20260814` (its three fixes exist in
  `main` in Codex's better form, which additionally handles the
  no-valid-selection case) and
  `codex/review-observation-clock-roll-20260813` (its substantive commit
  `1cb8abf` is in `main`; only an obsolete push-status paragraph is unique).
  Neither should be merged; both can be deleted.

Relevant merged and review history:

- `9e07bf9`: Claude's TRADE-1 counter-review.
- `6085f44`: Claude's SET-1 implementation.
- `a62aa1a`: PR #213, merging SET-1 to main.
- `e6c6748`: integration of main/SET-1 into the TRADE-1 review branch.
- `cfed8c8`: PR #214, merging the combined TRADE-1 review tree to main.
- `89156b7`: Codex's end-to-end SET-1 fractional correction.
- `ca0cdf0`: PR #217, merging that correction to main.
- `45a510c`: Claude's SET-1 counter-review and four corrections.
- `7055142`: PR #218, exact-tree merge of `45a510c`.
- `29290d9`: Codex verification correction on the active local branch.

Carried-forward review anchors that remain part of current recovery history:

- The epoch-005 roll/review chain began at `4de784e` and was independently
  corrected at `1cb8abf`; its full evidence remains in
  `docs/REVIEW_2026-08-13_OBSERVATION_CLOCK_AND_EPOCH005_ROLL.md`.
- BUY-1 was independently corrected on
  `codex/review-buy1-suggestion-picker-20260813` at `44a7f85`, then merged and
  counter-reviewed before this SET-1 work. No BUY-1 review work is reopened.

This verification started from clean exact main `7055142`. No unrelated user
work is included.

## 2. Outcome, commit dispositions, and issue state

Final disposition: **accepted after correction**.

Current verification issue total: **0 P0 / 0 P1 / 1 P2 / 3 P3; all
closed; 0 open**.

- `45a510c`: **accepted after correction**. SET1CR-001 through SET1CR-004
  are sound. The same commit's development launcher protected SQLite but not
  the shared paper account, omitted two supported provider keys, and added UI
  tests that exposed a pre-existing cross-AppTest cache leak.
- `7055142`: **accepted after correction**. The PR #218 merge tree exactly
  equals `45a510c`, with both parents intact. Its active documents became stale
  after the merge and are corrected on this branch.
- `29290d9`: Codex product/test correction: development launches now engage
  the environment kill switch by default, deliberate paper-order testing
  requires `-AllowPaperOrders` without clearing another switch, all five
  supported provider keys reload from user scope, primary instructions use the
  safe launcher, and the sell AppTests clear Streamlit's global cache.

Prior SET-1 implementation/review history carried forward:

- `9e07bf9`: **accepted**. It correctly confirmed the eight TRADE-1 review
  findings and fixed TRADE1CR-001. No further product correction was needed.
- `6085f44`: **accepted after correction**. Its protected controls, strict
  default, fingerprint binding, float refusal, and reserve/solvency split were
  sound. The fractional setting was only dormant authority, not the requested
  working feature; boolean validation, precision/eligibility boundaries, and
  toggle semantics also needed correction.
- `a62aa1a`: **accepted after correction**. The merge had no conflict defect,
  but brought the incomplete feature to main before independent acceptance and
  left current records saying it had not merged.
- `e6c6748`: **accepted after correction**. Product trees combined correctly;
  current state documents were not reconciled with the new topology.
- `cfed8c8`: **accepted after correction**. The final combined tree retained
  the SET-1 findings and a handoff whose requested next step had already
  happened.
- `89156b7`: reviewer correction completing and hardening the feature.
- `6b944ac`: durable review ledger, current Action Plan, and exactly
  two-paragraph SET-1 milestone record.

Prior independent-correction findings:

- P2 SET1R-001: disabling whole-share mode did not reach production sizing,
  execution, submission, or reconciliation.
- P2 SET1R-002: the authority-changing policy field accepted non-boolean
  durable values.
- P2 SET1R-003: no nine-decimal, fractionable-asset, or exact last-mile broker
  boundary existed.
- P2 SET1R-004: float-tolerant reconciliation could accept a one-nanoshare
  order-identity mismatch.
- P3 SET1R-005: the requested settings toggles were checkbox widgets.
- P3 SET1R-006: Action Plan, usage text, and handoff contradicted merged Git
  history and the implemented scope.
- P3 SET1R-007: the first correction draft violated the repository's guarded
  Decimal conversion rule; the complete suite caught all four sites.
- P3 SET1R-008: the first correction draft broke older strict broker seams by
  always sending a new keyword; strict mode now relies on the existing strict
  default and only fractional mode sends the explicit permission.

Claude's four counter-review findings are in
`docs/REVIEW_2026-08-14_SET1_COUNTERREVIEW.md`. The current four-finding
ledger, concrete evidence, corrections, and verification are in
`docs/REVIEW_2026-08-14_CODEX_SET1_COUNTERREVIEW.md`.

## 3. Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Focused policy/sizing/proposal/gate/broker/reconciliation/UI suite:
  **344 passed**.
- Adjacent execution/batch/replacement/UI suite initially:
  **255 passed / 1 failed**; the failure exposed SET1R-008 and passes after
  correction.
- First complete repository run: **3,737 passed / 1 failed / 25 warnings** in
  973.49 s; the sole failure exposed SET1R-007.
- Guard and directly affected rerun after correction: **34 passed**.
- Active-document consistency suite: **26 passed**.
- Complete code + review-record + draft-handoff run: **3,736 passed / 2
  failed / 25 warnings** in 969.03 s. Both failures were current-document
  continuity guards: this reconstructed handoff had omitted the required
  epoch-roll anchors `4de784e` / `1cb8abf` and the completed BUY-1 review
  branch/hash. No production, policy, broker, execution, or UI test failed.
- Post-correction active-document suite: **26 passed**.

Counter-review (`user/claude/set1-counterreview-20260814`), 2026-08-14:

- New suite `tests/test_set1_counterreview.py`: **15 passed**.
- Mutation testing: **5 of 5** corrections detected; each fix reverted
  individually, the intended test confirmed to fail, original bytes
  restored in a `finally`, restoration verified with `git diff`.
- Full repository suite: **3,752 passed / 1 failed** in 848.07 s; the
  failure was this session's own handoff wording tripping the
  merged-commit-reachability guard, since reworded.
- Affected suites re-run after documentation edits: **196 passed**.
- An earlier full run reported 2 failures in
  `tests/test_risk_check_registry.py`; that run overlapped edits to
  `risk/execution_gate.py` and those tests read source from disk. They
  pass on the settled tree. A suite run concurrent with edits validates
  nothing.

Codex verification (`codex/review-set1-counterreview-20260814`), 2026-08-14:

- `git diff --exit-code 45a510c 7055142`: clean; PR #218's merge tree is
  exact.
- Launcher, operational-launcher, and environment-kill-switch contracts:
  **39 passed**; PowerShell parser: clean without executing the app.
- Order-dependent UI sequence before correction: **23 passed / 1 failed**;
  the older sell test passed alone but lost its whole-share widget after the
  preceding AppTests. The fixture now clears Streamlit's data cache.
- Full settled-tree repository suite after product/test correction:
  **3,759 passed / 0 failed / 25 known dependency warnings** in 888.59 s.
- Post-documentation active-record, launcher, SET-1, exact UI-order,
  kill-switch, and operational-launcher checks: **138 passed**.
- Repository `compileall`: clean. `git diff --check` and staged checks: clean
  apart from expected Windows line-ending notices.

All provider/broker seams in tests were local fakes or monkeypatches. No real
broker request, order, funded-account action, operator-database write,
deployment, scheduled-task change, or live-market interaction occurred.

## 4. Completed feature and authority truth

- Settings & Features contains native Streamlit toggles for **Whole shares
  only** and **Enforce a minimum cash reserve**. Both remain inside the typed
  `UPDATE POLICY`, atomic expected-fingerprint workflow.
- `whole_shares_only` defaults to `True`, is validated as an actual boolean,
  and remains strict whenever a caller omits the flag.
- With the setting on, existing whole-share behavior is unchanged and broker
  submission retains the established Alpaca SDK path.
- With the setting off, Budgeted Buying, Discrete Buying, and Discrete Selling
  create exact quantities with at most nine decimal places. Dollar inputs are
  budgets converted to quantities, not broker-notional orders.
- Fractional quantities persist as canonical decimal text in proposals and
  authorization identity. Binary floats are still invalid order input.
- Fresh execution preflight and last-mile submission both require Alpaca's
  asset result to say `fractionable`. Fractional day orders use exact REST
  quantity text and the existing idempotent client order ID.
- Reconciliation prefers the broker's exact decimal quantity and requires
  exact equality; there is no share-count tolerance.
- Turning the reserve control off stores `min_cash_reserve_pct = 0`. It removes
  only the buffer: a buy that would take cash negative still refuses.
- Nothing auto-submits. Typed approval, fresh quote/account checks,
  concentration/exposure limits, duplicates, reservations, kill switch, paper
  mode, and all other existing gates remain in force.
- `scripts/launch_dev_app.ps1` uses `data/dev_scratch.db` and engages the
  environment kill switch by default. `-AllowPaperOrders` is the explicit
  paper-test opt-in and does not clear any inherited or persistent switch.
  The development and operational runtimes still share one Alpaca paper
  account, so ordinary previews must keep the default halt.
- Policy fingerprint changes invalidate prior proposals. Deploying this new
  policy field, even at the safe default, changes execution lineage.

## 5. Operational truth carried forward, not remeasured here

- `paper-epoch-005` remains the only active evidence epoch recorded by the
  durable operational documents.
- Its frozen deployed code is `752d3b7` in
  `C:\git\trading_agent_operational`; this development review did not touch
  that checkout.
- Epochs 001 through 004 are closed and cannot pool into epoch-005.
- The last reliable record expected the first scheduled epoch-005 observation
  after 16:30 Pacific on 2026-08-14. This review did not inspect the operator
  database or scheduler, so it makes no new claim about observation count,
  task result, manifest, lineage, or open alerts.
- CR-W3 remains: the first real AEP dividend subtype may fail closed around
  2026-09-10 and require the reviewed acknowledgement path. Do not widen
  reconciliation tolerance or post a manual compensating entry.

No account identifier, balance, credential value, private artifact content,
or secret is recorded here.

## 6. Next authorized step

1. Claude may independently verify `29290d9` and the documentation commits on
   `origin/codex/review-set1-counterreview-20260814`. The branch is published;
   publication does not authorize merge or deployment. `45a510c` and PR #218
   merge `7055142` are already merged history, not work awaiting review.
2. Answer the one open design question recorded in the counter-review: should
   strict mode permit a fractional sell that closes an ENTIRE remaining
   position? It cannot increase exposure and is the canonical risk-reducing
   action, but it would widen what "Whole shares only" permits across four
   deliberately independent layers. This is an owner decision. Until it is
   answered, the shipped behaviour is: the floor stands, the stranded
   remainder is disclosed, and turning the setting off is the remedy.
3. **Owner decision, 2026-08-14 (supersedes the earlier "epoch-005 is
   expendable" sequencing): epoch-005 runs UNCHANGED for 60 days.** Do not
   deploy, roll, or otherwise disturb it. The practical consequence is that
   TRADE-1, BUY-1, SET-1, the fractional-share path, and the counter-review
   corrections stay development-only for the duration; the operational
   runtime remains `752d3b7`. The owner will exercise new features through
   the development app from time to time, which is compatible with this
   decision as long as `scripts/launch_dev_app.ps1` is used WITHOUT
   `-AllowPaperOrders`: the scratch database and the environment kill switch
   together keep a development session out of the epoch's record. The
   `-AllowPaperOrders` switch reaches the SHARED Alpaca paper account and
   must not be used while this decision stands.
   Cadence measured 2026-08-14, not assumed: `TradingAgent-Paper-Observation`
   is `Ready`, last result 0, and its trigger is `DaysOfWeek: 62` (Mon-Fri)
   at 16:30 local. So 60 calendar days yields roughly 43 observations, not
   60. Whether the owner means 60 days or 60 observations is unresolved and
   should be confirmed before the count is treated as complete.
   Epoch-005 showing 0 observations on 2026-08-14 is CORRECT and not a
   fault: the epoch opened at 16:59 local on 2026-08-13, after that day's
   16:30 observation, which belongs to epoch-004.
4. If the owner later requests deployment, treat the policy-fingerprint change
   as an epoch-closing lineage change and follow the operations runbook; do not
   preserve epoch-005 by pretending the safe default is immaterial.
5. Separately, when requested, perform read-only verification of the scheduled
   epoch-005 observation. Do not infer it from this development review.
6. Still open from TRADE-1: `TRADE1CR-002`, the date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` that make the full suite
   unpassable between roughly 00:00 and 09:30 ET. It belongs on its own
   branch and is unrelated to SET-1.

Do not begin M4, mutate the operator database, alter scheduled tasks, access a
funded account, enable live trading, deploy, or roll an epoch without a new
explicit owner instruction.

## 7. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/REVIEW_2026-08-14_CODEX_SET1_COUNTERREVIEW.md,
docs/REVIEW_2026-08-14_SET1_COUNTERREVIEW.md, and docs/SESSION_HANDOFF.md.
main and origin/main are 7055142 (PR #218), which merged Claude's SET-1
counter-review 45a510c. Codex independently accepted its four trading fixes
after correction on published branch
origin/codex/review-set1-counterreview-20260814. Product/test correction 29290d9
makes the development launcher engage the environment kill switch by
default, requires explicit -AllowPaperOrders without clearing other switches,
loads every supported user-scope provider key, routes primary docs through
the safe launcher, and clears leaked Streamlit data-cache state in the older
sell AppTests. The full settled tree passed 3,759 tests. One design question
remains for the owner: whether strict mode should permit a fractional sell
that closes the entire remaining position. The operational runtime remains
frozen at 752d3b7 under paper-epoch-005; its observation count was not
remeasured. Publication is complete; do not merge, deploy, roll the epoch,
begin M4, mutate the operator database, alter scheduled tasks, access a funded
account, or enable live trading without explicit owner authorization.
```
