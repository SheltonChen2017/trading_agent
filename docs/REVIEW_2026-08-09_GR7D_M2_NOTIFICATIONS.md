# Codex review of three-sleeve M2 notifications — 2026-08-09

Audience: repository owner, Claude Code, Codex, Grok, and future reviewers.

Status: **complete; accepted after correction.**

## Scope

- Base: `02484bb` (`main` / `origin/main`, PR #178).
- Claude implementation branch:
  `user/claude/engine-m2-notifications-20260809`.
- Implementation head: `5ff39ed`; implementation commit `8f5acb7` plus
  validation-document commit `5ff39ed`.
- Independent review branch:
  `codex/review-gr7d-m2-notifications-20260809`.
- Independent correction: `c314245`.
- Contract: `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` section 5 M2 and
  its section 4 tax payload, with GR-5 warning batching and GR-4 data
  freshness unchanged.
- Operational exclusion: `paper-epoch-002` continues on the other computer
  at frozen commit `9a91498`; this review did not contact, deploy to, or
  change it.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `8f5acb7` | Accepted after correction | The transition-state architecture, warning routing, anti-nag behavior, re-arm behavior, migration, and briefing failure isolation are sound. M2REV-001 through M2REV-005 correct incomplete coverage handling, a false-flat re-entry path, stale-price acceptance, split alert/state transactions, and the missing plan-mandated unrealized-money payload. |
| `5ff39ed` | Accepted after correction | Correctly binds Claude's validation to `8f5acb7`, but the canonical handoff retained contradictory current-state instructions and described alert/state persistence as safer than it was. M2REV-006 and this review's final documentation supersede those claims. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| M2REV-001 | P2 | Fixed | `8f5acb7` | `assistant/sleeve_notifications.py::_BROKEN_COVERAGE` | A previously tracked lot that vanished while its ticker had `partial` coverage was treated as disposed, so the required coverage-loss warning was suppressed even though the journal could not account for all broker-held shares. | Red regression: two tracked AMD lots became one replayed lot while the snapshot still held 20 shares; report coverage was `partial`, but zero `coverage_lost` activations were emitted. | M2 explicitly requires mid-stream data-coverage loss to surface rather than become silence. Partial coverage is uncertainty, not proof of disposal. | Classify `partial` with `none` and `unavailable` for vanished-lot blindness. | The regression now emits exactly one coverage-loss activation for the vanished lot; focused and full suites pass. |
| M2REV-002 | P2 | Fixed | `8f5acb7` | `assistant/sleeve_notifications.py::run_sleeve_notification_cycle` | Re-entry candidates were called flat solely because the application ledger had no open lot. A broker-held growth ticker acquired outside the journal could therefore be described as having “no open lots” and generate a false re-entry warning. | Red end-to-end regression: a closed historical NVDA ledger plus a snapshot still holding five NVDA shares fetched NVDA and activated re-entry at 150 against a 170 disposal reference. | Broker-held shares mean the position is not flat, regardless of journal coverage. A false action-adjacent warning is materially misleading. | Exclude every ticker present in the current portfolio snapshot from flat re-entry candidates, in addition to requiring no open ledger lot. | The corrected cycle performs no price fetch and emits no re-entry activation for the externally held position. |
| M2REV-003 | P2 | Fixed | `8f5acb7` | `assistant/sleeve_notifications.py::_recorded_close_fetcher` | The GR-4 fetch was recorded but its latest close was consumed without checking the NYSE-session freshness contract. An old close could trigger or clear a re-entry crossing. | Red regression supplied a successful frame ending 2026-08-05 at pinned time 2026-08-09; the original helper had no freshness input and returned 150. | The data layer says consumers of stale series must refuse or visibly degrade. A stale price must pause a watch, not mutate its threshold state. | Pin fetch time, evaluate each ticker's latest session with `evaluate_bar_freshness`, and omit stale/malformed/non-finite closes so the evaluator uses its explicit unavailable-price path. | The stale frame now returns no price; M2's existing paused-not-cleared regression remains green. |
| M2REV-004 | P2 | Fixed | `8f5acb7` | `assistant/sleeve_notifications.py::run_sleeve_notification_cycle`; `assistant/storage.py` | Operational alerts were upserted in separate transactions before the complete watch state was saved. A crash or state-write failure could publish/reopen an alert while leaving its watch inactive, causing the next briefing to count/reopen the same crossing again. | Source ordering showed one committed alert transaction per activation followed by a second state transaction. A failure-injection regression with duplicate state keys now requires both tables to roll back together. | Durable first-crossing semantics require the visible alert and the state transition that justifies it to be one atomic unit; atomic state replacement alone is insufficient. | Add `commit_sleeve_notification_cycle`, sharing the existing alert-upsert SQL and committing all activations plus full next state through one SQLite connection/transaction. | Forced `sqlite3.IntegrityError` leaves both `operational_alerts` and `sleeve_watch_states` empty; anti-nag and genuine re-cross occurrence tests remain green. |
| M2REV-005 | P2 | Fixed | `8f5acb7` | `assistant/sleeve_report.py::_growth_positions`; `assistant/sleeve_notifications.py` | Gain and awaiting-long-term notifications omitted unrealized gain in money, despite the engine plan requiring every reported/notified gain payload to carry it through a decimal path. | Red regression raised `KeyError` for `activation.details["unrealized_pnl_money"]`, and the message contained only percentage and tax timing. | This is a direct definition-of-done miss in the owner-mandated tax-consequence payload. Percentage alone does not communicate the dollar consequence of a taxable review. | Preserve the legacy float display field, add exact-text `unrealized_pnl_money` computed from Decimal price, basis, and quantity, store it in activation details, and show the formatted amount in gain/awaiting messages. | A 10-share $100-basis lot at $160 carries exact text `600` and renders `$600.00`; focused and full suites pass. |
| M2REV-006 | P3 | Fixed | `8f5acb7`, `5ff39ed` | `docs/SESSION_HANDOFF.md`; action plan and engine-plan status | The handoff's newest section said M2 was implemented while its top state and recommended-next-step blocks still said M2 was absent/not started; it also called only the state replacement atomic, obscuring M2REV-004. | Direct document inspection found mutually exclusive current-state claims in the canonical cross-computer handoff. | A stale handoff can make the next computer repeat completed work or start from the wrong commit. | Rewrite current state, final validation, findings, branch topology, and next authorization boundary; update the action plan, milestone record, and engine-plan history. | Cross-document text/diff inspection and `git diff --check` pass; no stale top-level M2-start instruction remains. |

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open** from this review.

## Validation

- Pre-fix focused reproduction on Claude's tree: four behavioral regressions
  failed in their intended directions; the atomic API and exact-money
  contract were absent.
- Corrected focused suite: **141 passed**, 1 environment-only pytest-cache
  warning, in 36.15 seconds across M2 notifications, sleeve reporting,
  GR-4 data integrity, and GR-5 alert delivery.
- Final repository suite: **3289 passed, 0 failed, 0 skipped**, 27 warnings,
  in 366.38 seconds under Python 3.12.13.
- `compileall` passed across every workflow-named package and root module.
- `git diff --check` passed; checkout emitted only expected LF/CRLF notices.
- Review was code- and database-local. No broker call, live order, scheduler
  change, policy change, epoch mutation, or ML/LLM-authority change occurred.

## Assessment of Claude Fable's work

**Rating: 7/10.** The central design was good: a small pure transition
evaluator, explicit watch kinds, durable inactive-to-active semantics,
same-fingerprint re-arming, warning-only GR-5 routing, schema migration,
coverage-loss intent, and briefing failure isolation. The original 17 tests
meaningfully covered anti-nag and recovery behavior.

The score is held back by five material misses, especially the claim that
atomic state replacement protected the cycle while the user-visible alerts
were committed separately. The stale-close and false-flat paths also show
that the tests proved the local state machine more thoroughly than the
real composition boundaries feeding it. This is capable implementation that
needed independent correction before acceptance, not a rewrite.

## Acceptance and next step

M2 is accepted after `c314245`. M3 dividend-earmark accounting and
APPROVE-gated reinvest proposals remain absent and must not be started or
folded into this branch without the owner's explicit authorization. M4
remains deferred. The frozen paper epoch remains untouched.
