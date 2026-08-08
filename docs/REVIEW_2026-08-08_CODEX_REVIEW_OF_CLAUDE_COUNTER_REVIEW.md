# Codex review of Claude's counter-review — 2026-08-08

Audience: repository owner, Claude Code, Codex, Grok, and future reviewers.

Status: **complete; accepted after correction.**

## Scope

- Base: `24d0cb2` (`main`, PR #171).
- Claude branch: `user/claude/counter-review-codex-scan-20260808`.
- Exact Claude delivery head: `5b050cd` (pushed, unmerged).
- Reviewed commits, oldest first: `eb5c50a`, `1b108a7`, `152ccbe`,
  `119f2e3`, `6e653ba`, `5b050cd`.
- Review branch: `codex/review-claude-counter-review-20260808`.
- Operational exclusion: `paper-epoch-002` remains on the other computer at
  frozen commit `9a91498`; nothing in this review is deployment evidence.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `eb5c50a` | Accepted after correction | CCX-001 follows the IRS day-after-acquisition counting rule; CCX-002's relationship-based direction is right, but its parser misses uppercase `ACTIVE` and therefore misses the current handoff. |
| `1b108a7` | Accepted | Documentation-only expansion of the verification coverage; no new runtime contract. |
| `152ccbe` | Accepted after correction | The new validation correctly rejects invalid lookbacks and negative forward horizons, but it also rejects `hold_days` in the mode whose documented contract says that parameter is ignored. |
| `119f2e3` | Accepted | Reconciles stale finding dispositions and extends ledger-consistency evidence without changing the historical findings or severities. |
| `6e653ba` | Accepted | Scope audit records a clean negative result over logic-bearing non-Python files; no runtime change. |
| `5b050cd` | Accepted after correction | Useful standalone review artifact, but the handoff and artifact do not distinguish the reviewed implementation head from the actual delivery head, and the handoff retains stale validation and push/merge facts. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CCR-001 | P2 | Fixed | `152ccbe` | `market_analytics.py::run_baseline_forward_returns` | The new unconditional `hold_days >= 1` guard rejects `same_day_open_to_close` calls even though that mode's public contract explicitly ignores `hold_days`. This breaks parity with `run_backtest` and turns a valid research mode into an input error. | `hold_days=0` or a negative value is never used by that branch, but raised before branch selection. | This is a public compatibility regression introduced while fixing the genuinely unsafe negative-horizon direction in the two modes that do use the horizon. | Validate the horizon only in `same_close` and `next_open`; preserve the documented ignored parameter in same-day mode. | Red: 3 failures. Green: 194 combined focused tests. Reverse mutation: the 3 regression cases failed, then restoration passed. |
| CCR-002 | P3 | Fixed | `eb5c50a` | `tests/test_active_document_consistency.py::_active_epochs` | The relationship guard recognized only `active`/`Active`, while the canonical handoff says uppercase `ACTIVE`. A future handoff/action-plan disagreement could therefore pass. | `_active_epochs("`paper-epoch-003` ACTIVE")` returned an empty set. | The test claims to prevent cross-document epoch disagreement; silently omitting the canonical document's spelling defeats that contract. | Parse active and closed status case-insensitively, including the handoff's compact ``epoch ACTIVE`` form. | Red: parser regression failed. Green: 194 combined focused tests. Reverse mutation removing case-insensitivity failed the regression, then restoration passed. |
| CCR-003 | P3 | Fixed | pre-existing, explicitly surfaced by Claude | `assistant/policy.py::save_policy` | Policy compare-and-swap was silently disabled when a caller omitted both expected values. The current UI passes them, but a future authoritative writer could accidentally reintroduce the stale-tab lost-update class. | The function overwrote an existing policy without comparison when both optional values were omitted; tests relied on that implicit bypass for setup. | An unsafe authoritative-write mode should require an explicit opt-in so forgetting CAS fails loudly. | New-file creation remains implicit and safe under the writer lock. Replacing an existing policy now requires expected fingerprint/version or explicit `allow_unchecked_overwrite=True`; contradictory modes are rejected. | Red: unchecked overwrite test failed. Green: 194 combined focused tests including concurrency. Reverse mutation disabling the guard failed the regression, then restoration passed. |
| CCR-004 | P3 | Fixed | `5b050cd` | `docs/SESSION_HANDOFF.md`; `docs/REVIEW_2026-08-08_CLAUDE_COUNTER_REVIEW.md` | Current-state documentation said the merged Codex branch was local-only, named `6e653ba` as the Claude branch head although delivery head is `5b050cd`, and reported `3180` instead of Claude's final `3198` tests. | Direct Git/history and document comparison. | The handoff is the cross-computer authority; incorrect reachability, head, and validation facts can make another computer resume the wrong tree. | The standalone artifact now distinguishes implementation and delivery heads; the handoff is rewritten in the required separate follow-up commit after the correction hash exists. | Artifact metadata corrected here; final handoff diff, secret-shape scan, and clean-history check are recorded in the handoff commit. |

## Independent tax-rule assessment

CCX-001 is accepted. Current IRS Publication 550 states that the holding
period begins on the day after acquisition, includes the disposition date,
and becomes long term only when the property is held more than one year. The
implementation anchors on that first counted market-local day and makes its
first calendar anniversary the first long-term date. This is the best-supported
calendar rule for both leap positions. The application remains advisory:
broker tax records and a qualified tax professional are authoritative for a
filed return.

## Final validation

- Focused restored tree: **194 passed** across tax lots, policy persistence,
  market analytics, backtesting, and active-document consistency.
- Full repository suite: **3203 passed, 0 failed, 0 skipped, 26 warnings** in
  356.09 seconds under Python 3.12.13.
- Reverse mutations: CCR-001 produced 3 intended failures; CCR-002 produced 1;
  CCR-003 produced 1. Each correction was restored and the focused set reran
  green.
- `compileall` passed across every production package, tests, and root Python
  modules named by the repository workflow.
- Every PowerShell file under `scripts/` parsed successfully.
- `git diff --check` passed; only expected LF-to-CRLF checkout notices were
  emitted.

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open** from this review.
`paper-epoch-002` was not contacted or changed.
