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
- Contract: `docs/Plan/THREE_SLEEVE_ENGINE_PLAN.md` section 5 M2 and
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


## Claude counter-review of this review — 2026-08-09

Outcome: **accepted, with one correction to a correction and one residual
fixed** (M2CR-001, M2CR-002 below). All six findings verified as confirmed
by pre-fix reproduction; all five code fixes independently re-mutated.

### Independent verification

Every code finding was reproduced by running the reviewed head's module
(`5ff39ed`) side by side with the corrected one:

| ID | Independent pre-fix reproduction | Verdict |
|---|---|---|
| M2REV-001 | two tracked AMD lots, one dropped from the replay while the snapshot held 20 shares (coverage `partial`): pre-fix zero coverage-lost activations, fixed exactly one | **confirmed** — silence under partial coverage was real |
| M2REV-002 | closed NVDA ledger (sell fill at 170) plus a snapshot still holding 5 NVDA: pre-fix built a re-entry reference for a broker-held position; fixed excludes it | **confirmed** — a false action-adjacent warning on a position the owner still holds |
| M2REV-003 | injected provider frame ending 2026-08-05 at pinned now 2026-08-09: pre-fix returned `150.0`, fixed returns nothing and the paused-not-cleared path takes over | **confirmed** — my fetcher consumed a recorded fetch without the freshness contract GR-4 exists to enforce |
| M2REV-004 | injected a failure after the alert write on the pre-fix path: alert committed (1) with zero watch states — a torn write that would re-count the crossing next briefing; fixed leaves both tables empty | **confirmed** — and my handoff had explicitly called the state save "atomic" while the ALERT sat outside it, a claimed guarantee the code did not enforce |
| M2REV-005 | pre-fix activation details had no `unrealized_pnl_money` and the message carried only the percentage; fixed carries exact-text `600` and renders `$600.00` | **confirmed** — plan §4 requires money on every gain payload; the report had it (after GR7DREV-005), the notification did not |
| M2REV-006 | current handoff inspected: the "start M2" instruction and "M2 absent" state claims are gone; remaining "not started" mentions are historical or about M3 | **confirmed and correctly fixed** |

Storage consolidation verified: `upsert_operational_alert` now DELEGATES to
`_upsert_operational_alert_in_connection` — one SQL text, no drift-prone
duplicate. Disposition denominator verified: the two dispositioned commits
are exactly `git log 02484bb..5ff39ed`.

Independent re-mutations, distinct from the review's where possible
(including splitting the atomic commit back into per-alert transactions,
which the rollback regression caught): five of five failed the intended
tests; files restored byte-for-byte by SHA-256.

### M2CR-001 (P2, fixed here): M2REV-001's fix over-corrects on proven disposals

Classifying `partial` as blindness is right for an UNEXPLAINED vanish, but
the correction as shipped also fires a false coverage-lost alert on a
journal-PROVEN disposal inside a partially covered position: sell an
app-recorded lot while pre-app shares keep the position `partial` forever —
which is exactly what the owner's real AVGO/MSFT positions become the day
more shares are bought through the app — and the vanished lot triggers
"the watch is blind" on every legitimate sale.

The replay itself distinguishes the two cases: a consumed lot is named by a
`RealizedComponent.lot_id`. Correction: `evaluate_watch_transitions` now
takes `disposed_lot_ids` (the cycle passes the ledger's realized lot ids)
and a vanished lot that the journal proves was sold is a disposal under ANY
coverage value; only an unexplained vanish alerts. Red test written first
(false alarm reproduced on the review's tree), fix applied, both directions
pinned (the unexplained-vanish protection from M2REV-001 remains covered),
reverse mutation of the skip fails the test.

### M2CR-002 (P3, fixed here): mojibake introduced by the PREVIOUS review's
correction — and missed by my previous counter-review

`docs/Plan/THREE_SLEEVE_ENGINE_PLAN.md` §1.1 contained literal bytes
`Ã¢â‚¬â€` (a double-encoded em-dash) rendered as `â€”`, introduced by
`f8dde7a` (GR7DREV-005's documentation edit) and present in the file bytes
— verified with a byte-level scan, unlike the earlier console-side
false alarm of the same shape. My own counter-review of that round
machine-verified numbers and mutations but never scanned the edited prose,
so the miss is shared. Repaired byte-exactly; a tree-wide scan finds no
other instance.

### Validation

Full suite on the exact counter-reviewed tree (both corrections applied):
recorded in the follow-up commit. Focused: 23/23 notification tests
including the two new guards. The review's own numbers reproduced: its
focused 141 matched before my additions.

### On the assessment

7/10 with "the tests proved the local state machine more thoroughly than
the real composition boundaries feeding it" — accepted as accurate, and it
names the recurring shape precisely: M2REV-002/003/004 all live at the
seams (snapshot↔ledger, fetch↔freshness, alert↔state) rather than inside
the evaluator my tests concentrated on. Boundary tests deserve the same
budget as core-logic tests.
