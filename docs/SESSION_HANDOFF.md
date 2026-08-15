# Session handoff — REBAL-1 Stage 2 implemented

Prepared: 2026-08-15 by Claude, after counter-reviewing Stage 1 and then
implementing Stage 2 of the REBAL-1 plan.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REBAL1_MILESTONE_PLAN.md`
4. `docs/REVIEW_2026-08-15_REBAL1_STAGE2.md`
5. `docs/REVIEW_2026-08-15_REBAL1_STAGE1_COUNTERREVIEW.md`
6. `docs/REVIEW_2026-08-15_REBAL1_STAGE1.md`
7. `docs/MANDATE.md` (§2, §4, §6)
8. `docs/OPERATIONAL_FACTS.md`
9. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes deployment, evidence repair, an epoch roll, M4,
REBAL-1 Stage 3, funded-account access, live trading, operator-database
mutation, or a scheduled-task change.

## 1. Repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- `main` and `origin/main`: `f64b668`, PR #228's merge of Claude's Stage 1
  counter-review on top of PR #227 (Codex's Stage 1 review) and PR #226
  (Stage 1 itself).
- **Current branch: `user/claude/rebal1-stage2-buy-steering-20260815`**,
  branched from `f64b668`. It carries the Stage 1 correction REBAL1CR-002 and
  all of Stage 2, at the owner's direction to keep both on one branch.
- The operational checkout remains separate at frozen commit `752d3b7` in
  active `paper-epoch-005`. No development commit has been copied there.

Relevant recent history:

- `4de784e` / `1cb8abf`: the epoch-005 observation-clock roll chain and
  Codex's correction of it.
- `c048a94`: the owner's decision to keep epoch-005 unchanged for 60 days.
- `6fcdd35` / `e03a320`: REBAL-1 Stage 1 and its records.
- `5519a69` / `ccb00f4`: Codex's Stage 1 review correction and records.
- `832ea6a`: Claude's Stage 1 counter-review.
- The completed BUY-1 review branch remains
  `codex/review-buy1-suggestion-picker-20260813`, correction `44a7f85`. It is
  historical recovery context, not reopened work.

## 2. Owner decision, 2026-08-15: raise the policy, not the profile

Stage 1's review established that the owner-approved sleeve profile could not
be reached under the active policy — 90% invested against a 50%
total-exposure cap, and growth's 40% target against 30% of capacity at
`max_position_pct` 5%. The owner chose to raise the policy rather than lower
the profile, on the basis that this is a small testing and experimentation
account where the extra concentration is acceptable.

The DEVELOPMENT `assistant/my_policy.json` now carries
`max_total_exposure_pct` 0.90 and `max_position_pct` 0.07 (six growth names ×
7% = 42%, clearing the 40% target), version `0.3.0-personal.1`, with the
rationale in its own `notes`.

**The operational checkout was deliberately not touched, and a future agent
must not "finish the job" by copying it across.** `_active_runtime_lineage()`
computes `policy_fingerprint` from the live policy file and
`capture_paper_account_observation()` raises `PaperEvidenceError` when the
epoch's recorded lineage differs, so editing the operational policy during the
60-day hold would make every nightly capture refuse — the epoch-002 stall
exactly. `C:\git\trading_agent_operational` keeps 0.50/0.05 until the owner
authorizes a deployment, which closes epoch-005 on its own account anyway by
changing `code_commit`.

`my_policy.json` is untracked, so this change is local and appears in no
commit. `assistant/default_policy.json` is unchanged: the committed baseline
stays conservative, and a fresh clone still sees the conflict disclosures.

## 3. What this branch contains

**REBAL1CR-002 (Stage 1 correction).** My Stage 1 counter-review fixed
`policy_conflict` masking the band status but left the identical defect one
status along: `unassigned_holdings` also occupies `status`, and the headline
breach count read `status`, so a residual outside its band went uncounted.
`SleeveRow.band_state` is now computed independently of the display label and
`breached` derives from it, so which label a row carries can never change how
many breaches are counted. `band_state` is empty when the band genuinely
cannot be judged, and those rows contribute no breach either way.

**Stage 2 — buy-only cash steering.** `assistant/rebalance_steering.py` plus a
section on the existing Portfolio Rebalancing page. The owner enters a
new-money budget and picks one ticker per under-band sleeve; the module
produces one APPROVE-gated buy proposal per funded sleeve.

Points a reviewer should press on:

- money is sized to the **lower band edge, not the target** — the band's
  purpose is that being inside it is enough;
- **cash and the residual can never receive money**, whatever their band says;
- **an overweight sleeve produces nothing at all**, not even a reduced buy;
- eligibility is measured on the **projected** weight, so money already
  working in an unfilled order counts (the HEDGER-004 duplication);
- an unchosen or unaffordable leg is **named, never silently omitted**; and
- proposals bind to the **allocation-profile fingerprint**, so a profile edit
  cannot reuse an order sized against targets the owner has since changed.

The staleness signature covers profile fingerprint, snapshot date, equity,
ticker choices, budget, and per-sleeve pending values. Stage 1 got staleness
for free by storing nothing; Stage 2 cannot, so it is explicit.

## 4. Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Full settled tree: **3,971 passed / 0 failed / 25 known dependency
  warnings** in 672.57 seconds, with no concurrent edit.
- Focused: 26 steering, 71 rebalance, 16 UI tests.
- Mutation verification: **8 mutations, 8 detected** by exactly the intended
  test. Two only worked on a second attempt — the first versions left the
  refusal in place and so changed nothing observable. A mutation that does
  not create the dangerous behaviour proves nothing about the test.
- `python -m compileall` and `git diff --check`: clean.

Always run the full suite through `.venv\Scripts\python.exe`; a bare
`python -m pytest` uses the user Python, which still has Streamlit 1.52.2 and
produces 14 spurious UI failures.

## 5. Operational truth and owner decision

- `paper-epoch-005` is active on the epoch host at frozen deployed commit
  `752d3b7`. Epochs 001 through 004 are closed and cannot pool evidence into
  it.
- Owner decision, 2026-08-14: epoch-005 runs unchanged for 60 days. Do not
  deploy, roll, or otherwise disturb it. TRADE-1, BUY-1, SET-1, STALL-1,
  HEDGE-1, and REBAL-1 all remain development-only.
- Sixty calendar days is roughly 43 weekday observations, not 60 sessions.
  Whether the owner's target means days or observations is still open.
- The owner may exercise this work with `scripts/launch_dev_app.ps1`; its
  scratch database and default environment kill switch prevent submission.
  `-AllowPaperOrders` reaches the shared Alpaca paper account and must not be
  used while the 60-day hold stands.
- CR-W3 remains a watch item: the first real AEP dividend subtype may fail
  closed around 2026-09-10 and require the reviewed acknowledgement path. Do
  not widen reconciliation tolerance or post a manual compensating entry.

No account identifier, balance, credential value, private artifact content, or
secret is recorded here.

## 6. Next authorized step

1. Independent review of both pieces here — the Stage 1 correction and
   Stage 2. Suggested focus: whether the lower-edge sizing rule is right when
   several sleeves compete for one budget, whether the staleness signature
   misses any input that changes what a proposal means, and whether
   `band_state` now covers every status precedence case.
2. Stage 3 (tax-aware trims) needs its own explicit authorization naming it,
   because it is where rebalancing first sells on the app's own initiative
   rather than on a computed breach or the owner's instruction.
3. Answer whether the 60-day decision means calendar days or 60 captured
   market sessions.
4. The SET-1 design question remains open: whether strict whole-share mode
   should permit a fractional sell only when it closes an entire position.
5. `TRADE1CR-002` remains open and unscheduled: date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` make the full suite unpassable
   between roughly 00:00 and 09:30 ET.

`docs/FEATURE_MILESTONE_RECORD.md` deliberately has no Stage 2 entry yet;
that file records work that has completed its definition of done AND its
required review.

Do not begin M4, mutate the operator database, alter scheduled tasks, access a
funded account, enable live trading, deploy, or roll an epoch without a new
explicit owner instruction.

## 7. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, docs/REBAL1_MILESTONE_PLAN.md,
and docs/SESSION_HANDOFF.md. main and origin/main are f64b668 (PR #228).
Branch user/claude/rebal1-stage2-buy-steering-20260815 carries two things: the
Stage 1 correction REBAL1CR-002, where unassigned_holdings masked the band
status exactly as policy_conflict had and the headline breach count
undercounted a drifted residual; and REBAL-1 Stage 2, buy-only cash steering
that sizes a new-money budget to the LOWER BAND EDGE of under-band sleeves,
never sells, never steers into cash or the residual, names rather than omits
an unchosen or unaffordable leg, and binds proposals to the allocation-profile
fingerprint. Owner decision 2026-08-15: the policy was raised (dev
my_policy.json 0.90/0.07) rather than the profile lowered; the OPERATIONAL
policy was deliberately left at 0.50/0.05 because a policy-fingerprint change
would stall epoch-005's nightly capture. Full pinned-venv tree: 3,971 passed /
0 failed. Stage 2 has had NO independent review and Stage 3 is not started.
Do not deploy, roll the epoch, mutate the operator database, begin M4, access
a funded account, or enable live trading without explicit owner authorization.
```
