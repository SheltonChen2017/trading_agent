# Independent review — SELL-1 and branch-cleanup changes

Prepared: 2026-08-13 by Codex

Final disposition: **accepted after correction**. Submitted implementation
quality: **7/10**. The feature kept the proposal/approval/execution boundary
clear and arrived with useful tests, but one exact-share defect reached the
shared gate and could authorize more shares than the broker's exact quantity.

## 1. Scope and repository snapshot

- Base before the reviewed work: `022c456` for the mainline comparison;
  SELL-1 itself branched from `60ed001` and was later integrated with M3.
- Review head: `c3d10ff` (`main` / `origin/main` when review began).
- Review branch: `codex/review-claude-sell1-cleanup-20260813`.
- Correction commit: `3ba3d41` (local-only until the owner authorizes push).
- No deployment, operator-database access, evidence-epoch change, broker
  call, branch restoration, push, merge, or funded action was performed.

## 2. Commit-by-commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `918eecd` | **Accepted after correction** | SELL-1's authority separation, explicit refusals, tax-advisory reuse, CLI, and UI structure are sound. SELREV-001 through SELREV-004 required correction. |
| `dc1233a` | **Accepted after correction in the cumulative tree** | The M3 integration conflict was resolved correctly: both CLI feature families, both UI sections, and the superset document guard survive. No integration-specific code loss was found; inherited SELL-1 defects remained until `3ba3d41`. |
| `08fde9f` | **Accepted after correction in the cumulative tree** | GitHub's PR #203 merge adds no conflict-resolution delta beyond the reviewed integration tree. Its resulting current handoff/action-plan topology became stale and is corrected under SELREV-005. |
| `cbb38cb` | **Accepted after correction** | The deletion event was worth recording, but BRREV-001's absolute unrecoverability claim was disproved locally and the commit did not update all canonical current-state documents. |
| `c3d10ff` | **Accepted after correction in the cumulative tree** | GitHub's PR #204 merge adds no independent tree delta. Final acceptance depends on the code and documentation corrections recorded here. |

## 3. P0-P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SELREV-001 | P1 | Resolved | `918eecd` | `assistant/user_directed_sell.py`; `risk/execution_gate.py` | Exact fractional broker shares were converted to a float before flooring/comparison. `10.999999999999999999` became `11.0`, so both proposal creation and the final gate authorized selling 11 shares—potentially opening a short. | Direct reproduction on the submitted tree printed display shares `11.0`, exact shares `10.999999999999999999`, and `approved=True`. Two new regressions failed red. | Sell quantity cannot exceed broker-confirmed exact holdings; this is a hard, non-overridable execution invariant. | SELL-1 and the shared gate now prefer `shares_exact`, retain Decimal through flooring/summing, and format the exact held amount in the refusal. | Both regressions pass; broader focused suite passes 391 tests. |
| SELREV-002 | P2 | Resolved | `918eecd` | `assistant/user_directed_sell.py` | Proposal-time `shares * price` used binary float arithmetic. A valid sale of 3 shares at $0.10 against a $0.30 cap was refused and incorrectly said only two shares fit. | Direct reproduction plus regression failed red with `created=False`. | Proposal boundaries must match the Decimal execution gate; a user must not receive a false policy refusal at the exact cap. | Price, notional, cap, and fitting-share calculation now use the existing exact Decimal helpers. | Exact-boundary regression passes; focused money and gate suites pass. |
| SELREV-003 | P2 | Resolved | `918eecd` | `assistant/user_directed_sell.py`; `scripts/personal_assistant_ui.py` | Selling all whole shares of a fractional holding was described as closing the entire position even though the fraction remains. | A 10.5-share holding with a 10-share proposal produced both “closes the whole position” and “closes the entire” before correction; generator and real-AppTest regressions failed red. | The displayed financial consequence must match the resulting holding; false closure wording can cause the owner to overlook a residual position. | One shared exact remainder helper now drives generator and UI wording; fractional remainder text is explicit. | Both generator and real UI regressions pass. |
| SELREV-004 | P2 | Resolved | `918eecd` | `scripts/personal_assistant_ui.py` | The UI bound a stored owner-directed proposal only to ticker, not quantity. Changing the selector from 3 to 4 left the old “SELL 3” actionable card rendered under the current 4-share form. | Real AppTest reproduction retained the stored 3-share intent and card after the selector changed; regression failed red. | An actionable card must not look synchronized with input it does not represent; approval would execute the stored quantity, not the newly selected one. | Card rendering now requires both ticker and exact whole-share selection to match; otherwise a stated stale-card notice directs regeneration. | Real AppTest regression passes. |
| SELREV-005 | P3 | Resolved | `08fde9f`, `cbb38cb`, `c3d10ff` | `docs/ACTION_PLAN_2026-08-02.md`; `docs/SESSION_HANDOFF.md` | Current records still said SELL-1 was unmerged and awaited independent review, and directed resumption on deleted topic branches after both PRs had merged. | Git topology showed `main=origin/main=c3d10ff`; the current handoff named `022c456` as main and prescribed the already-completed merge/review. | These files are the repository's sequencing and cross-computer authorities; stale topology causes duplicate work and unsafe resumption instructions. | Action plan and handoff now record PR #203/#204, this independent review, local-only correction state, and the real next step. | Active-document suite and final diff checks are recorded below. |
| BRREV-001 | P3 | Resolved | `cbb38cb` | `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` | The cleanup note said the old equal-weight slice “no longer exists anywhere” and must be rewritten. That was stronger than the evidence and false in this checkout. | `git fsck --unreachable --no-reflogs` plus tree inspection found dangling branch tip `85a77291...` with `assistant/rebalance.py` and 639 tests. | Recovery documentation must distinguish deleted refs from pruned objects; the false claim could cause unnecessary rewriting while recoverable data still exists. | The plan now says no current ref reaches it, records the dangling recovery lead, and warns that it is local-only, non-authoritative, and pruneable. No branch was recreated. | Local object/tree inspection and documentation consistency review. |

Issue totals: **0 P0, 1 P1, 3 P2, 2 P3; all resolved**.

## 4. Validation

- Submitted-tree red proof: **6 failed, 49 passed** across the new SELL-1,
  real-UI, exact-money, and gate regressions; each failure matched its finding.
- Corrected broader focused suite: **391 passed** in 36.40 s.
- Documentation-complete full suite: **3,618 passed, 0 failed, 0 skipped,
  25 known dependency warnings** in 669.76 s under Python 3.13.14 and
  Streamlit 1.60.0.
- After inserting that measured result, the active-document suite passed
  **21 tests**; the ML import-boundary suite, repository compileall (including
  `research`), `git diff --check`, staged-diff checks, narrow secret-shape
  scan, and final status checks passed.

## 5. Boundaries and remaining state

SELL-1 creates only a proposal. It does not recommend a sale, approve or
submit automatically, weaken policy, add live authority, or change a database
schema. Exact approval and a fresh paper-account execution-gate pass remain
mandatory. Limit orders, conditional/scheduled sells, fractional-share
orders, multi-ticker sells, M4, deployment, and an epoch roll remain outside
this review.

Two older proposal generators still derive a whole-share suggestion from the
display float. The corrected shared execution gate now prevents either from
authorizing an exact-share oversell, so this is not an open execution escape;
consolidating proposal-time whole-share flooring can be handled separately
without expanding this review into unrelated strategy behavior.
