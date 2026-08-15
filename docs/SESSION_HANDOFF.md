# Session handoff — REBAL-1 Stage 2 reviewed and counter-reviewed

Prepared: 2026-08-15 by Claude, after counter-reviewing Codex's independent
review and correction of Stage 2. Audience: repository owner, Claude Code,
Codex, and the next verifier.

## 0. Read first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REBAL1_MILESTONE_PLAN.md`
4. `docs/REVIEW_2026-08-15_REBAL1_STAGE2_INDEPENDENT.md`
5. `docs/REVIEW_2026-08-15_REBAL1_STAGE2.md` (Claude's implementation report)
6. `docs/REVIEW_2026-08-15_REBAL1_STAGE1.md`
7. `docs/MANDATE.md` (§2, §4, §6)
8. `docs/OPERATIONAL_FACTS.md`
9. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes deployment, an epoch roll, evidence repair, Stage 3,
M4, funded-account access, live trading, operator-database mutation, or a
scheduled-task change.

## 1. Exact repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- `main` and `origin/main`: `f64b668` (PR #228, complete Stage 1 review
  chain).
- Claude implementation branch:
  `user/claude/rebal1-stage2-buy-steering-20260815`, pushed once as requested.
- Reviewed implementation commits, base-to-tip:
  - `c0d56d592f9a419139b74fa40e5841d9363705ec` — Stage 1 band-state
    correction and Stage 2 product/tests.
  - `7420a9992a715bc1db2be59f1147509a844445a4` — implementation records and
    owner policy decision.
- Codex review branch: `codex/review-rebal1-stage2-20260815`, based exactly on
  `7420a99`.
- Product/test correction: `bdeb61d`.
- The documentation/handoff commit follows `bdeb61d` and the owner authorized
  a final push of the review branch. At preparation time that push was the
  remaining Git step; verify `origin/codex/review-rebal1-stage2-20260815`
  before calling cross-computer synchronization complete.
- No merge or pull request was created. The owner will handle the PR.

Relevant retained history: the epoch-005 observation-clock roll chain is
`4de784e` / `1cb8abf`; both remain operational context for the frozen epoch.
The completed BUY-1 review branch
`codex/review-buy1-suggestion-picker-20260813` and correction `44a7f85` are
historical recovery context, not reopened work.

Recheck `HEAD` and `git status` before any later commit: Claude and Codex
often share this checkout. Preserve any work you did not author.

## 2. Review disposition

Overall: **REBAL-1 Stage 2 accepted after correction; development-only.**

| Commit | Disposition | Notes |
|---|---|---|
| `c0d56d5` | Accepted after correction | Stage 1 `band_state` is sound. Stage 2 needed four P2 and one P3 product/test corrections. |
| `7420a99` | Accepted after correction | Implementation narrative was useful, but durable profile binding and staleness claims were incomplete; current records close that P3 drift. |

Issue summary (all closed; no P0/P1):

- `REBAL2CR-001` P2 — proposal reference prices were Decimal at a JSON
  persistence boundary, so the primary Stage 2 UI action crashed before an
  approval card appeared.
- `REBAL2CR-002` P2 — a budget change could create a new proposal ID while
  reusing a database-unique idempotency key for an equal rounded quantity.
- `REBAL2CR-003` P2 — the allocation profile changed proposal identity but
  was not checked when a stored proposal later entered execution validation.
- `REBAL2CR-004` P2 — retained-card staleness omitted same-day position value
  changes when total equity and pending totals happened to stay unchanged.
- `REBAL2CR-005` P3 — exact lower-edge dollars were reconstructed from
  display floats instead of profile and row Decimal values.
- `REBAL2CR-006` P3 — current records overstated submitted binding/staleness
  and still described the milestone as pending review.

The full evidence, correction, reason, and verification for each item are in
`docs/REVIEW_2026-08-15_REBAL1_STAGE2_INDEPENDENT.md`.

Submitted implementation quality: **6.5/10**. Corrected final tree: **9/10**.
Claude's scope control, buy-only design, projected-order accounting,
lower-edge rule, disclosures, and test breadth were strong. The main action
path nevertheless could not persist a proposal, and three explicit durable
safety requirements were only partially implemented, so the submitted score
cannot be higher.

## 3. Final Stage 2 behavior

`assistant/rebalance_steering.py` and the Portfolio Rebalancing page now:

- consider only non-cash, non-residual sleeves below the lower edge on
  projected exposure;
- count measurable working orders through the Stage 1 report;
- require the owner to choose the ticker within every eligible sleeve;
- split the owner-entered budget proportionally to exact lower-edge
  shortfalls and cap each sleeve there;
- support the active whole/fractional share policy through the shared
  allocation planner;
- name unaffordable legs and display unallocated cash;
- create one ordinary, typed-approval-gated buy proposal per funded sleeve;
- provide no rebalancing sell and no submit-all control;
- bind durable proposals to trading-policy and allocation-profile
  fingerprints, with both checked before broker I/O; and
- hide retained cards after any complete snapshot, report, profile, policy,
  ticker-choice, or exact-budget change.

The target shape and wide band remain the owner's preference, not evidence of
edge. The confirmed SOXX/SOXL turnover result does not establish that this
general portfolio shape is profitable.

The accompanying Stage 1 correction adds `SleeveRow.band_state` independent
of display `status`. A residual can therefore retain the useful
`unassigned_holdings` label while still counting as under/over its band;
unknown pending exposure gets no guessed band state.

## 4. Owner policy decision and local-only state

Stage 1 showed that the approved 90%-invested shape and 40% growth target were
unreachable under the development policy's 50% total-exposure and 5%
per-position caps. The owner chose to raise the development policy rather
than lower the profile for this small testing account.

The ignored, machine-local `assistant/my_policy.json` was changed by Claude to
`max_total_exposure_pct=0.90`, `max_position_pct=0.07`, version
`0.3.0-personal.1`. It is intentionally absent from commits. The committed
`assistant/default_policy.json` remains conservative, so a fresh clone still
shows policy/profile conflicts until its owner supplies a policy.

Do not copy this local policy into the operational checkout during the frozen
epoch. The operational policy remains 0.50/0.05; changing its fingerprint
would make capture lineage disagree and can stall observations.

## 5. Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Claude submitted: 3,971 passed, 25 known dependency warnings in 672.57s;
  113 submitted focused tests passed in 8.89s.
- Codex final focused set (steering, portfolio rebalancing, rebalancing UI,
  execution characterization): **170 passed in 45.60s**.
- Codex final full suite: **3,975 passed, 0 failed, 25 known dependency
  warnings in 647.43s (10:47)**.
- `python -m compileall -q assistant scripts risk tests`: clean.
- `git diff --check`: clean before documentation commit; rerun after records.

The execution-context regression uses an isolated temporary database and
blocks a moved-profile proposal before broker import. No test contacted a
broker or operator database.

## 6. Operational truth and boundaries

- Operational checkout: separate and frozen at commit `752d3b7`.
- Active evidence epoch: `paper-epoch-005`, under the owner's 60-day hold.
- Development Stage 2 is not deployed. Deploying any changed commit would
  change `code_commit` and close the epoch; no deployment is authorized.
- The normal development launcher uses `data/dev_scratch.db` and adds an
  environment kill switch, so unreleased UI work cannot submit by default.
- `scripts/launch_dev_app.ps1 -AllowPaperOrders` remains the explicit owner
  opt-in for testing paper submission. It still shares the Alpaca paper
  account with the frozen runtime, and any submitted order can affect the
  epoch's broker record; use it only as a deliberate test with that
  consequence understood. It does not bypass inherited or persistent kill
  switches.
- Never use a bare Streamlit command: without the launcher, this checkout can
  fall back to the operator database path.
- No account identifier, balance, credential value, secret, or private
  artifact content is recorded here.

## 6b. Counter-review of the Stage 2 correction (Claude, 2026-08-15)

Branch `user/claude/rebal1-stage2-counterreview-20260815`, based on Codex's
review tip `c14acfc`. Ledger in
`docs/REVIEW_2026-08-15_REBAL1_STAGE2_COUNTERREVIEW.md`.

All six of Codex's findings were re-derived on a worktree at the submitted
tree `7420a99` and all six are real. **REBAL2CR-001 is the one that matters:**
every Stage 2 proposal carried a `Decimal` in `reference_price`,
`save_proposal()` JSON-encodes, so the feature's only action path raised
`TypeError` before an approval card could exist. I had seen the type
discrepancy and written a comment rationalising it rather than asking what
downstream required — documenting a smell is not chasing it. The tests missed
it because they inspected in-memory proposal fields and never drove the
button; the action path had no end-to-end coverage at all.

**The execution-path change was audited separately** and accepted. The
context validator is injected at call time through the frozen
`ProposalValidationDeps` contract rather than imported by the kernel, runs
before `import_broker()`, has exactly one construction site so no other caller
breaks, keys on `evidence_status` so every other proposal family passes
through untouched, uses the same failure class as its six sibling pre-broker
refusals, and reaches `rebalance_profile` through a deferred import that adds
no path toward `ml`.

**One P3 closed (REBAL2CCR-001):** the context check's missing-fingerprint arm
was unpinned. An earlier reading of mine called this a fail-closed gap and
that was wrong — `None != current` refuses the proposal either way. What was
actually lost is the refusal saying *missing* rather than *does not match*,
which would send the owner looking for a profile edit that never happened.
Two regressions now cover it and the untouched-families case.

**Recorded for whoever adds multi-profile support:**
`_validate_proposal_context` compares against the module constant
`OWNER_APPROVED_PROFILE` while `generate_steering_proposals` accepts any
profile. They agree today because the UI passes only the constant. When Stage
0 grows editable or multiple profiles, this must resolve the *active* profile
or every proposal made against a non-constant profile becomes permanently
unexecutable. Fail-closed, so it is a trap for a future change rather than a
present defect, and it is deliberately not fixed here.

Validation on this tree: **3,977 passed / 0 failed** in the pinned `.venv`;
32 steering tests. Eight mutations against Codex's corrections, seven
detected plus the one that became REBAL2CCR-001. The staleness fingerprint
result is worth stating precisely: its payload carries both the portfolio
snapshot and the report, and the report already holds per-sleeve market
values, so removing either alone leaves the property defended by the other.
The test reddens once both are removed — discriminating, not vacuous.

## 7. What is next

No further REBAL implementation is authorized. The owner may merge
`user/claude/rebal1-stage2-counterreview-20260815`, which carries Codex's
review commits and this counter-review on top, through a single PR.

If the owner wants to continue REBAL-1, Stage 3 is the next defined stage but
requires a new explicit instruction naming it. It is the first rebalancing
stage that would let the app originate sells; its design must cover tax lots,
holding periods, realized-gain consequences, pending sells, fractional
remainders, owner-selected ticker/amount/lot strategy, and separate approval.

Other unresolved owner/roadmap items remain:

- clarify whether the 60-day hold means calendar days or 60 captured market
  sessions;
- decide whether strict whole-share mode may sell a fractional remainder only
  when closing the entire position;
- `TRADE1CR-002` date-dependent strategy fixtures remain open/unscheduled;
- GR-6 portability/recovery and later AI product plans remain incomplete in
  the adopted action plan; and
- M4 remains deferred.

Do not begin any of those merely because it is listed here; follow the owner
and `docs/ACTION_PLAN_2026-08-02.md` sequencing authority.

## 8. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/REBAL1_MILESTONE_PLAN.md, docs/SESSION_HANDOFF.md, and
docs/REVIEW_2026-08-15_REBAL1_STAGE2_INDEPENDENT.md. main/origin-main are
f64b668. Claude pushed REBAL-1 Stage 2 once at 7420a99; Codex reviewed that
exact snapshot on codex/review-rebal1-stage2-20260815 and corrected it at
bdeb61d. Stage 2 is accepted after correction: buy-only lower-band steering,
owner ticker selection, separate typed approvals, no submit-all, complete
snapshot/card staleness, budget-safe idempotency, and execution-time active
allocation-profile binding. Final validation: 170 focused and 3,975 full
tests passed. Stage 3 is not started and requires separate explicit owner
authorization. Nothing is deployed; operational commit 752d3b7 remains in
paper-epoch-005. Do not deploy, roll the epoch, mutate operator state, begin
M4/Stage 3, access funded accounts, or enable live trading without explicit
owner authorization. Verify the review branch exists on origin before
claiming cross-computer synchronization.
```
