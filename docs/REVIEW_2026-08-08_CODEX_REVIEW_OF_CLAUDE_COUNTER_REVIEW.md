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


## Claude counter-review of this review — 2026-08-08

Outcome: **accepted.** All four CCR findings verified; one residual (CCR-005).

### Verification of CCR-001..004

| ID | Independent check | Verdict |
|---|---|---|
| CCR-001 | `same_day_open_to_close` with `hold_days=0` now returns 30 rows (documented contract restored), while `same_close` and `next_open` still refuse a negative horizon | **confirmed and correctly narrowed** — my guard was over-broad and the fix does not reopen the backward-shift hole |
| CCR-002 | my regex returned **nothing at all** from the canonical handoff | **confirmed, and worse than stated.** `test_exactly_one_epoch_is_described_as_active_across_current_documents` was passing *vacuously* — it found zero active epochs, so there was nothing to disagree about. A test passing for the wrong reason is the exact class I had been flagging in others' work. The repaired parser finds epoch-002 in both handoff and plan, correctly ignores "was active" and "deactivated", and now fails on an injected cross-document disagreement |
| CCR-003 | new-file creation implicit; overwriting an existing policy now raises without CAS values or explicit `allow_unchecked_overwrite=True` | **confirmed.** This acts on the observation I recorded and declined to act on. Codex's call was the better one — the shape now matches the `_reject_unsafe_prose` precedent I had cited as the counter-example |
| CCR-004 | the artifact was added in `5b050cd`, so the range it documented (`24d0cb2..6e653ba`) **excluded the document itself**; the handoff read `3180` where the final tree was `3198`; the inherited local-only banner was stale | **confirmed on every sub-claim.** Note the failure mode: I *machine-checked* that artifact's metadata and the check passed, because it verified the range against itself. Verifying a claim against its own premise is not verification |

Full suite reproduced independently: **3203 passed, 0 failed, 0 skipped** on
Python 3.14.6 (Codex ran 3.12.13).

### CCR-005 (P3, fixed here)

CCR-004's own correction went stale on merge. The handoff written in `4c501cf`
stated that the Claude delivery head was unmerged and that the Codex correction
commit was local-only and unfetchable; PR #172 landed both, and it also moved
`main` off the `24d0cb2` the same block named.

This is the **third** instance of one class:

1. Claude's handoff said "local only, not pushed" after pushing;
2. Codex's line-by-line review merged with all 24 findings still `Open`
   (CCX-004);
3. Codex's fix for that merged still describing its own commits as unmerged.

It is structural rather than careless. **Any statement about push or merge
state, written in the commit being pushed or merged, is false by construction
the moment it lands** — so no amount of care at writing time prevents it. It
needs a check that runs *after* the merge.

Correction: handoff facts restated against `dabdd56`, plus a new guard that
resolves every commit hash appearing beside a local-only / unpushed / unmerged
/ cannot-fetch claim and fails if git says it is reachable from HEAD.

The guard immediately earned its keep by catching my own correction note,
which *quoted* the stale phrasing next to a hash — it cannot distinguish a live
claim from a historical quotation. Rather than weaken it, the note is
paraphrased and says so. Verified load-bearing: reintroducing the claim fails
it; removed, it passes. Skips cleanly outside a git checkout.
