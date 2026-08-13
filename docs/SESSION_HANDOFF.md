# Session handoff — three-sleeve M3 implemented, pending independent review

Prepared: 2026-08-13, after the owner authorized M3 of the three-sleeve
engine ("start") and its implementation completed on a milestone branch.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

Read, in order:

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` (sections 1.1, 5 M3, and
   the 2026-08-13 change-control entry)
4. `docs/OPERATIONAL_FACTS.md`
5. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
6. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`

The action plan remains the sequencing authority. Nothing in this session
authorizes M4, deployment, an epoch roll, live trading, or any funded
action.

## 1. Repository topology

- `main` / `origin/main`: `60ed001` (PR #200 merge). Earlier today the
  owner merged PR #197 (counter-review), #198 (AP-11), #199 (post-merge
  records), and #200 (AP-11 review counter-review), and every merged
  branch was deleted locally and on the remote.
- Unmerged remote branches deliberately kept: `origin/Funny`
  (unidentified, owner to decide) and
  `origin/user/claude/gr-7d-rebalance-targets-20260806` (the superseded
  2026-08-06 equal-weight GR-7d slice, kept as the archived record per the
  three-sleeve plan's prior-decision disclosure).
- This session's milestone branch:
  `user/claude/three-sleeve-m3-earmarks-20260813`, created from `60ed001`.
  One milestone only (M3), stopped for independent review per the plan's
  own milestone rule.

## 2. M3 — what was implemented

Definition: `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` §5 M3 as revised
by §1.1 (dividend income funds pending decline-review adds first; earmark
records make each dividend dollar spendable exactly once; never
auto-submitted). The change-control entry dated 2026-08-13 records the
implemented semantics; the review-relevant decisions:

- **Pool population**: broker-confirmed corporate-action dividends only
  (`source == "corporate_action"` against `INCOME:DIVIDENDS`) — narrower
  than the M1 report's income display, disclosed in the payload. A
  positive income posting refuses the measurement rather than netting.
- **Earmark lifecycle**: created atomically WITH the proposal in one
  `BEGIN IMMEDIATE` transaction (`create_dividend_earmark_with_proposal`)
  whose in-transaction pool fence is the concurrency authority; released
  or consumed exactly once through a status-fenced conditional UPDATE
  (`resolve_dividend_earmark_if_active`, rowcount discipline mirroring
  `release_execution_reservation`).
- **Disposition rule**: provably-unspent terminals release (blocked,
  validation_failed, submission_failed, broker_rejected, expired,
  dismissed); `filled` consumes; `canceled`/`broker_expired` release only
  with zero recorded fill quantity and consume otherwise (partial-fill
  dollars never return to the pool); everything else — including
  `submission_unknown`, `reconciling`, legacy `executed`, unknown future
  statuses, and an earmark whose proposal row is missing — HOLDS.
- **Routing**: active `decline_review` and `reentry_decline` watches (M2
  state) both outrank leveraged reinvestment; the reinvest route is
  refused with the pending tickers named. Eligible reinvest candidates
  come from `config.DIVIDEND_REINVEST_TICKERS`; `max_leveraged_etf_pct`
  stays the untouched execution-time backstop.
- **Surfaces**: CLI `sleeve-reinvest` (read-only status; active earmarks
  of terminal proposals display their derived effective disposition
  without writing) and `sleeve-reinvest-propose` (reconciles durably,
  prices through the GR-4 recorded-close path with M2's freshness check,
  refuses without a fresh close); a Buying-page expander (read-only
  render, writes only in the button handler); a briefing reconcile hook
  with M2-style failure isolation.
- **Files**: `assistant/sleeve_reinvest.py` (new),
  `assistant/storage.py` (new table + three methods),
  `scripts/run_personal_assistant.py` (two commands + briefing hook),
  `scripts/personal_assistant_ui.py` (Buying expander),
  `tests/test_sleeve_reinvest.py` (62 tests),
  `tests/test_ui_sleeve_reinvest.py` (1 AppTest), plan + action-plan
  documentation.

Deliberately NOT implemented: M4 prepared trim proposals (deferred by
default), auto-submission of anything, changes to policy caps, any
notification additions beyond the reconcile lines in the briefing, any
deployment.

## 3. Validation (repository venv, Python 3.13.14 / Streamlit 1.60.0)

- `tests/test_sleeve_reinvest.py`: **62 passed** — includes the exact
  disposition table, atomic-create refusal paths, exactly-once resolve,
  reconcile idempotency, partial-fill consumption, read-only status
  proof, write-allowlist proof (only `trade_proposals` +
  `sleeve_dividend_earmarks`), payload lexical guard, and CLI handlers.
- Mutation evidence (each restored and re-verified green): disabling the
  IN-TRANSACTION pool fence initially stayed green because the
  module-level pre-check shadowed it — a direct storage-level test was
  added and now reddens on that mutation; dropping the resolve status
  fence, ignoring fill evidence on cancellation, and releasing unknown
  statuses each reddened their tests.
- Focused: sleeve report + notifications + import boundary — **146
  passed**; UI smoke — **1 passed**.
- Penultimate tree: **3,556 passed, 1 failed, 25 known dependency
  warnings** in 748.15 s — the single failure was the extended placeholder
  guard correctly rejecting this section's own then-unfilled tokens.
- Exact final tree differs from that run only by this validation text;
  the doc-consistency suite (the only tests reading this file) was rerun
  green on the final text: **19 passed**.
- Repository-prescribed `compileall` (venv) and `git diff --check`: clean
  (only the expected LF→CRLF working-copy notice).

## 4. Operational truth — do not disturb the epoch

- `paper-epoch-004` is the only active evidence epoch, frozen at `b837374`
  in `C:\git\trading_agent_operational`. M3 does not touch it.
- AP-8, AP-9, QC-2, AP-10, AP-11, and (once reviewed and merged) M3 are
  development code riding the next owner-authorized epoch roll.
- CR-W3 watch unchanged (first real AEP dividend subtype ~2026-09-10;
  JNLC still requires operator judgement; never widen reconciliation
  tolerance or use a manual compensating entry).
- Note for the roll that deploys M3: the dividend pool starts from the
  operator ledger's confirmed corporate-action dividends, which already
  exist in the operator database — the pool will be non-zero on first
  deploy, and nothing spends it without an explicit owner-approved
  proposal.

## 5. Next step

Independent review of `user/claude/three-sleeve-m3-earmarks-20260813`
(the standing loop's next move), then owner-directed merge. No
`FEATURE_MILESTONE_RECORD` entry until the milestone completes review.
Open owner decisions, unchanged: epoch-roll timing, the
physical-media-only off-machine backup, the `origin/Funny` branch, and
M4 (deferred by default).

## 6. Resume prompt

```text
Verify a clean worktree. Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/reference/THREE_SLEEVE_ENGINE_PLAN.md (1.1, 5 M3, 2026-08-13 entry),
and docs/SESSION_HANDOFF.md. Review the branch
user/claude/three-sleeve-m3-earmarks-20260813 against main commit by
commit. Do not merge, deploy, touch the operator database, or roll
paper-epoch-004 without a new owner instruction.
```
