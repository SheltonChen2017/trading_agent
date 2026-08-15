# Session handoff — HEDGE-1 defensive hedge sleeve implemented

Prepared: 2026-08-14 by Claude, after counter-reviewing the epoch stall
detector and then implementing the owner-requested hedging feature.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/MANDATE.md` (§2, §4, §6 — amended by HEDGE-1, prose only)
4. `docs/REVIEW_2026-08-14_EPOCH_STALL_COUNTERREVIEW.md`
5. `docs/REVIEW_2026-08-14_EPOCH_STALL_DETECTOR.md`
6. `docs/OPERATIONAL_FACTS.md`
7. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes deployment, evidence repair, an epoch roll, M4,
funded-account access, live trading, operator-database mutation, or a
scheduled-task change.

## 1. Repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- `main` and `origin/main`: `85338fc`, after PR #222 merged the epoch
  stall-detector counter-review (`57a75fc`) on top of PR #221 (`1babbcf`).
- **Current branch: `user/claude/hedge1-defensive-sleeve-20260814`**, branched
  from `1babbcf` and then merged forward to `85338fc`. It was deliberately
  kept independent of the counter-review so the two could be reviewed
  separately; the price of that independence was a documents-only merge
  conflict once the counter-review landed. Both conflicts were in records
  every branch rewrites (`ACTION_PLAN`, this file), not in code.
- The operational checkout remains separate at frozen commit `752d3b7`. No
  development commit has been copied there.

Relevant recent history:

- `4de784e`: where Claude's epoch-005 observation-clock and roll chain began.
- `1cb8abf`: Codex's independent correction of that roll chain.
- `c048a94`: the owner's decision to keep epoch-005 unchanged for 60 days.
- `60027af`: PR #220.
- `6aa7069` / `4273de6` / `4cb3a0d`: the stall detector, Codex's correction,
  and its records, all merged by PR #221.
- `57a75fc`: Claude's counter-review of that correction, merged by PR #222.
- The completed BUY-1 review branch remains
  `codex/review-buy1-suggestion-picker-20260813`, correction `44a7f85`. It is
  historical recovery context, not reopened work.

## 2. What HEDGE-1 implements

Owner request, 2026-08-14: "add hedging." Two scoping choices were put to the
owner before any code was written, and both bound everything below:

- **hedge type: defensive/inverse ETF sleeve**, not options and not
  research-only analytics; and
- **order path: proposal only, behind typed APPROVE**, not observation-only.

New files:

- `assistant/hedge_sleeve.py` — `evaluate_hedge_sleeve()` and
  `generate_hedge_buy_proposals()`.
- `tests/test_hedge_sleeve.py` (43 tests), `tests/test_ui_hedging.py` (8).

Changed: `config.py` (two new constants), `scripts/personal_assistant_ui.py`
(a `Hedging` page), `HOW_TO_USE.md`, `docs/MANDATE.md`,
`docs/ACTION_PLAN_2026-08-02.md`.

The only genuinely new computation is the **dollar shortfall** between the
current defensive weight and an owner-set target. Share sizing is delegated to
`assistant.allocation_proposals.build_allocation_plan` — the same function the
preview uses — so what is displayed and what is proposed cannot drift apart.

Design decisions worth reviewing rather than assuming:

- **Equal weight, not inverse volatility.** Inverse-volatility weighting is
  what `allocation_proposals` uses, and it is wrong here: it maximizes weight
  where trailing volatility is lowest, which in a defensive basket starves
  whichever instrument actually moves against equities.
- **An unreadable holding refuses everything, including the percentage.** A
  skipped row understates the current hedge weight, which overstates the
  shortfall, which oversizes the purchase. Under-hedging is the smaller error.
  The displayed percentage is suppressed too, because a partial hedge value
  shown as the whole one is the reading that talks someone into buying more.
- **`target_pct=None` is report-only, not invalid.** The page's default state
  has no target; a red refusal on every first visit trains the owner to ignore
  this page's errors. A target that WAS supplied and is unusable still refuses.
- **The page never sells and has no submit-all button.** Trimming a defensive
  position stays on the deliberate Discrete Selling path, and each hedge leg
  takes its own typed approval because a partly-filled multi-leg hedge is a
  different position from the one that was sized.

## 3. Mandate and epoch consequences

**No mandate behavior field changed, and that is the reason this milestone was
buildable at all.** Every instrument (SH, BTAL, TLT, GLD) is a long-only ETF,
and `permitted_instruments` in `assistant/default_mandate.json` already reads
`["equity", "etf"]`. `compute_mandate_fingerprint(load_mandate())` was verified
equal to the owner-approved `approved_fingerprint`, and a regression test now
pins that equality. Active `paper-epoch-005` is therefore unaffected by this
branch.

`docs/MANDATE.md` changes are prose only: the hedge-cost row now says a hedge
can be held (with no cost figure, because none has been measured), the
permitted-instrument row is annotated with its value unchanged, and §6 records
the amendment. §4's shelving of the crisis-response trend-following sleeve
stands — that sleeve needs futures or real shorting, which this milestone
deliberately does not add.

No policy field was added either, so `compute_policy_fingerprint` is unchanged
and this branch carries **no deployment-closes-the-epoch consequence** of its
own. The hedge target is a per-run UI input, not durable policy. Making it a
policy field is a deliberate deferral, and it would change the fingerprint.

Instrument verification, 2026-08-14, via `fetch_historical` and
`yf.Ticker().info`: all four resolve with a full 400/400 requested sessions and
are real, liquid, US-listed ETFs. SH and BTAL are deliberately NOT added to
`LEVERAGED_ETF_TICKERS`; they are 1x, and adding them would silently change
`max_leveraged_etf_pct` enforcement. Their real hazard is daily-reset path
dependence, handled as a disclosure through `config.DAILY_RESET_HEDGE_ETFS`.

## 4. Validation

Authoritative environment: repository `.venv`, Python 3.13.14, Streamlit
1.60.0, Windows.

- `.venv\Scripts\python.exe -m pytest -q` on the merge result: **3,843 passed / 0
  failed / 25 known dependency warnings** in 820.25 seconds, on the settled
  tree with no concurrent edit.
- Before merging `origin/main` forward, the branch alone measured **3,834
  passed / 0 failed** in 625.10 seconds. The counter-review contributes 9
  further tests, which is exactly the difference from the 3,843 measured
  while this work was briefly stacked on that branch.
- Focused: hedge module 43, hedge UI 8, plus ML import boundary, document
  consistency, discrete tabs, allocation proposals, and UI chrome — 142 passed.
- Mutation verification: **12 mutations, 12 detected** by exactly the intended
  tests, covering the unreadable-holding refusal, the suppressed percentage,
  the exact-value preference, bare-string ticker input, de-duplication, equal
  weighting, the target upper bound, the daily-reset disclosure, and
  report-only mode.
- `python -m compileall` and `git diff --check`: clean.

Interpreter trap, worth keeping: a bare `python -m pytest` uses the user
Python, which still has Streamlit 1.52.2. That run reports 14 UI failures from
the missing `AppTest.segmented_control` API and is not a real result. Always
run the full suite through `.venv\Scripts\python.exe`.

## 5. Untested and out of scope

- No test exercises the real Alpaca paper account, a real hedge order, or the
  real price behavior of these instruments. The feature is exercised against
  fixtures.
- **No evidence supports the hedge working.** Fixtures prove software
  behavior. This project has confirmed zero signals as real edge and has not
  measured drawdown reduction for this basket; the module, the page, and every
  proposal say so.
- Options, futures, and short selling remain out of scope.
- The hedge target is not durable policy, so it is not fingerprint-bound and
  does not survive a session.
- No backtest of the sleeve was run. If the owner wants evidence rather than a
  mechanism, that is the separate research-analytics option that was offered
  and not chosen for this milestone.

## 6. Operational truth and owner decision

- `paper-epoch-005` is active on the epoch host at frozen deployed commit
  `752d3b7`. Epochs 001 through 004 are closed and cannot pool evidence into
  it.
- **Epoch-005 recorded its first observation on 2026-08-14**, session
  `2026-08-14`, captured at 23:30:07Z — 16:30 Pacific, on the installed
  trigger. `scripts/check_epoch_cadence.py` reports `HEALTHY`, 1 of 1 expected.
- Owner decision, 2026-08-14: epoch-005 runs unchanged for 60 days. Do not
  deploy, roll, or otherwise disturb it. TRADE-1, BUY-1, SET-1, STALL-1, and
  HEDGE-1 all remain development-only.
- Sixty calendar days is roughly 43 weekday observations, not 60 sessions.
  Whether the owner's target means days or observations is still open.
- The owner may exercise HEDGE-1 with `scripts/launch_dev_app.ps1`; its scratch
  database and default environment kill switch prevent submission.
  `-AllowPaperOrders` reaches the shared Alpaca paper account and must not be
  used while the 60-day hold stands.
- CR-W3 remains a watch item: the first real AEP dividend subtype may fail
  closed around 2026-09-10 and require the reviewed acknowledgement path. Do
  not widen reconciliation tolerance or post a manual compensating entry.

No account identifier, balance, credential value, private artifact content, or
secret is recorded here.

## 7. Next authorized step

1. **Independent review of HEDGE-1.** It has had none. Suggested focus: the
   equal-weight decision, the refuse-don't-skip rule and whether any path
   still reaches sizing with a partially-read basket, the report-only
   contract, and whether the Hedging page's stale-signature binding matches
   the AP-9 / SELL-1 rule the other proposal surfaces use.
2. Answer whether the 60-day decision means calendar days or 60 captured
   market sessions.
3. The SET-1 design question remains open: whether strict whole-share mode
   should permit a fractional sell only when it closes an entire position.
4. `TRADE1CR-002` remains open and unscheduled: date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` make the full suite unpassable
   between roughly 00:00 and 09:30 ET.

`docs/FEATURE_MILESTONE_RECORD.md` deliberately has NO HEDGE-1 entry yet. That
file records work that has completed its definition of done *and* its required
review; HEDGE-1 has had no independent review.

Do not begin M4, mutate the operator database, alter scheduled tasks, access a
funded account, enable live trading, deploy, or roll an epoch without a new
explicit owner instruction.

## 8. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, docs/MANDATE.md, and
docs/SESSION_HANDOFF.md. main and origin/main are 85338fc, after PR #222
merged the epoch stall-detector counter-review. One Claude branch is open:
HEDGE-1 on user/claude/hedge1-defensive-sleeve-20260814, branched from
1babbcf and merged forward to 85338fc. HEDGE-1 adds an owner-directed
defensive ETF hedge sleeve: assistant/hedge_sleeve.py computes the dollar
shortfall to an owner-set target and delegates share sizing to
build_allocation_plan; the split is equal weight, an unreadable holding
refuses the whole computation, the page never sells, and each leg takes its
own typed approval. No mandate or policy behavior field changed, so the
owner-approved mandate fingerprint is unchanged and active paper-epoch-005 is
unaffected. Full pinned-venv tree: 3,834 passed / 0 failed. HEDGE-1 has had NO
independent review. Do not deploy, roll the epoch, mutate the operator
database, begin M4, access a funded account, or enable live trading without
explicit owner authorization.
```
