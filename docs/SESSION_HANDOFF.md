# Development session handoff

Prepared: 2026-08-04 after Codex independently reviewed and corrected
Claude's UI-3 interactive Backtest page.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Current outcome

UI-3 is **complete and independently accepted after correction**. No P0 or
P1 issue, live-authority escape, broker interaction, secret exposure, or
durable-state change was found. Claude's architecture was strong: the ninth
Streamlit page composes the existing walk-forward engine through a pure
research helper, defaults to synthetic data, fixes executable entry timing at
`next_open`, caches real yfinance data, persists results without automatic
reruns, labels research limitations, and exposes no proposal/order/policy or
registry action.

Review resolved two P2 research-correctness findings and one P3 proof gap at
`540467e`:

- empty/partial provider responses and impossible signal/history combinations
  can no longer appear as a fully covered zero-signal result;
- fractional integer parameters are no longer truncated, and invalid
  horizons or negative/non-finite slippage fail closed;
- completed session results now retain actual data coverage, selected
  horizons, entry timing, and slippage, with missing/short histories disclosed;
- UI/engine equivalence compares complete DataFrames instead of row counts;
  a stored-real-result AppTest pins the exploratory/coverage warnings; and
- the research boundary is enforced across the complete reachable first-party
  import graph, not merely direct imports.

The review is documented in
`docs/REVIEW_2026-08-04_UI3_BACKTEST_PAGE.md`.

## 2. Canonical Git state

Repository: https://github.com/SheltonChen2017/trading_agent

    base/main/origin-main = 1286966 (post PR #140)
    Claude implementation = 198339d
    Claude documentation/handoff = d664402
    Claude branch = user/claude/ui-3-backtest-page-20260804 (pushed)
    Codex correction = 540467e
    Codex review records = 538eae9
    first pushed replacement handoff = 8be0f20
    Codex branch = codex/review-ui-3-backtest-20260804
    canonical handoff = branch-tip commit containing this file

The Codex review branch was pushed and `8be0f20` was verified byte-for-byte
against GitHub with `git ls-remote` after one transient connection timeout;
this post-push handoff update is the final branch-tip commit and must also be
remote-verified. UI-3 has not been merged and Codex has not opened a pull
request.

## 3. Commit-by-commit dispositions

- `198339d` — **accepted after correction**. Core engine composition, frozen
  six-signal inventory, routing, caching, session behavior, caveats, chart
  semantics, and read-only authority boundary are correct. `UI3REV-001` and
  `UI3REV-002` required production corrections; `UI3REV-003` required stronger
  regression proof.
- `d664402` — **accepted after documentation replacement**. Its plan/README
  accurately described the submitted intent and its handoff accurately marked
  UI-3 awaiting review. Completion status, validation, and coverage-limit text
  are superseded by the corrected review records and this handoff.
- `540467e` — **accepted**. Corrects data coverage/sufficiency and strict
  experiment validation, strengthens stored attribution, exact-frame
  equivalence, real-result warnings, and transitive research boundaries.
- `538eae9` — **accepted**. Updates the adopted action plan and README, adds
  the binding review report, and adds the required two-paragraph completed
  milestone record.
- `8be0f20` — **accepted**. Replaces the canonical handoff with the completed
  corrected-review state.

## 4. P0-P3 issue summary

| ID | Priority | Status | Summary |
|---|---:|---|---|
| UI3REV-001 | P2 | Resolved at `540467e` | Empty/partial real data and insufficient signal history could be presented as a valid full-scope no-signal result. UI-3 now fails empty/impossible runs, stores actual coverage, and visibly discloses missing or short histories. |
| UI3REV-002 | P2 | Resolved at `540467e` | Fractional integer parameters were silently truncated and invalid horizons/slippage reached the engine. All numeric experiment boundaries now validate finite values and fail closed without changing the requested experiment. |
| UI3REV-003 | P3 | Resolved at `540467e` | Equivalence checked row counts only, real-result warnings lacked an AppTest, and the authority boundary checked direct imports only. Exact frames, stored-real warnings, frozen history semantics, and transitive reachability are now regression-tested and mutation-proven. |

No P0 or P1 issue was found. See the review report for the full reason,
evidence, correction, and verification columns retained for each item.

## 5. Completed UI-3 behavior and limits

The Backtest page exposes six price-only signal scanners: dip/up z-score,
cross-sectional momentum, relative dip/up, 52-week breakout, 52-week-high
proximity, and volatility-scaled momentum. PEAD/fundamentals remain excluded
because they require an earnings feed; residual momentum/reversal and
idiosyncratic volatility remain excluded because they require precomputed
residual or benchmark inputs.

The page offers synthetic or yfinance data, whole-universe or basket scope,
signal-specific parameters, history length, and fixed hold-horizon choices.
An explicit Run button is the only computation trigger. It renders a
multi-horizon summary and an equal-weight running sum of per-signal net
returns by direction. The chart is explicitly not a compounded portfolio
equity curve; overlapping holds and no capital constraint remain disclosed.

Synthetic output is a plumbing check whose expected win rate is about 50%.
Real output is exploratory, not point-in-time, uncorrected for multiple looks,
and not evidence of edge. Confirmatory significance/out-of-sample work remains
CLI-only. No UI result can create, approve, size, submit, cancel, reconcile, or
dismiss a proposal/order, write the research registry, or change policy.

## 6. Validation

Environment: Python 3.13.14.

- Submitted focused baseline re-run: 72 passed in 138.52s.
- Initial corrected UI-3 unit/AppTest set: 33 passed in 51.25s.
- Final corrected adjacent focused set: 88 passed in 144.16s.
- Full suite on exact code commit `540467e`: 2,613 passed, 1 skipped,
  25 warnings in 633.75s.
- Compileall over required packages/root modules: clean.
- `git diff --check`: clean.

Red/green evidence:

- twelve strict-validation/data regressions failed on the submitted behavior
  and passed after correction;
- the impossible 252-session breakout on 160 rows failed red, then rejected
  clearly after correction;
- forcing zero slippage in the UI failed exact-frame comparison on every
  `net_return_pct`, then passed after restoration;
- suppressing incomplete-coverage presentation failed the stored-real-result
  AppTest, then passed after restoration; and
- an indirect `backtest.interactive -> backtest.engine -> assistant` import
  failed with the complete chain, then passed after restoration.

The 25 warnings are the existing WebSockets legacy and joblib/NumPy
deprecations. Tests do not call the live yfinance network path; deterministic
fixtures exercise empty, partial, short-history, attribution, and presentation
semantics without an external request.

## 7. What is next

Per `docs/ACTION_PLAN_2026-08-02.md`, UI-2d is the next planned UI milestone,
but **do not start it without owner direction**. Its first release is durable
dismiss/archive, never physical deletion: add terminal `dismissed`, hide it by
default while retaining audit/idempotency data, and permit it only for narrowly
defined never-broker-touched proposals. It needs its own branch,
migration/concurrency coverage, and independent review. Adding `dismissed`
must update UI-2b's exhaustive outcome map.

Automatic expiry remains a separately approved optional lifecycle milestone.
Physical purge remains deferred and separately owner-authorized.

Phase 5 operational deployment/epoch start remains owner-heavy. Do not run
elevated installer actions, install scheduled tasks, approve the mandate, or
start a formal evidence epoch without the owner's explicit direction and the
decisions in `docs/PHASE5_DEPLOYMENT_SESSION.md` section 2.

## 8. Machine-local and safety state

The owner's Streamlit app may be running from an earlier checkout. This review
did not stop, restart, or interact with it. No Alpaca endpoint, operator
database, scheduled task, research registry, evidence artifact, or external
data provider was contacted or mutated. All tests used their isolated data.

At review start, only the primary worktree was registered. Claude and Codex
share this checkout, so re-check `HEAD` and `git status` before every future
stage/commit and preserve work not authored by the current agent.

On resume, read in this order:

1. `CLAUDE.md` and `AGENTS.md`;
2. `docs/ACTION_PLAN_2026-08-02.md`;
3. this handoff;
4. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`; and
5. `docs/REVIEW_2026-08-04_UI3_BACKTEST_PAGE.md`.

Suggested resume prompt: "Read the required repository instructions and the
canonical handoff, then verify local/remote Git state. Do not start UI-2d or
Phase 5 actions until the owner explicitly directs them."
