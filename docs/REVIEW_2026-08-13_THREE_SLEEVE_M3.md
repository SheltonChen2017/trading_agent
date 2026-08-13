# Codex review of three-sleeve M3 earmark accounting — 2026-08-13

Audience: repository owner, Claude Code, Codex, and future reviewers.

Status: **complete; accepted after correction.**

## Scope

- Exact base: `60ed001` (`main` / `origin/main`).
- Submitted branch: `user/claude/three-sleeve-m3-earmarks-20260813`.
- Submitted head and sole reviewed commit: `7ee4786`.
- Independent review branch: `codex/review-three-sleeve-m3-20260813`.
- Independent correction: `b6685b5`.
- Contract: `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` §1.1 and §5 M3.
- Operational exclusion: active `paper-epoch-004` remains frozen at
  `b837374`; this review made no broker call, deployment, scheduler change,
  policy change, epoch mutation, or live-trading change.

## Commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `7ee4786` | Accepted after correction | The proposal routing, exact-text earmark model, APPROVE-gated integration, read-only status surface, recorded-close pricing, and exactly-once resolution fence are sound. M3REV-001 through M3REV-006 correct two release-after-fill paths, replace caller-asserted funding with a transaction-local journal derivation, hold unknown/corrupt durable state, reject nonpositive stored money, and preserve valid JSON output. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| M3REV-001 | P1 | Fixed | `7ee4786` | `assistant/sleeve_reinvest.py::_has_fill_evidence` | Poll reconciliation stores cumulative `filled_qty`, but M3 read only incremental `fill_qty`; a partially filled cancellation could release already-spent dividend dollars and make them spendable twice. | Red regression planted the exact poll-only event shape (`filled_qty=2`, `fill_qty=NULL`); submitted code resolved the earmark as `released`. Repository order-lifecycle/storage comments confirm polling uses the cumulative field. | Releasing money after a real fill violates M3's exactly-once funding contract and can create a second funded proposal against spent cash. | Inspect both incremental and cumulative fields; any nonzero, negative, or unreadable quantity fails toward consumption. | Regression now resolves `consumed`; complete M3 and full suites pass. |
| M3REV-002 | P1 | Fixed | `7ee4786` | `assistant/sleeve_reinvest.py::earmark_disposition` | Release-class labels ignored fill evidence. The lifecycle permits `broker_rejected` after `partially_filled`, so an actual fill followed by rejection could release the whole earmark. | Red table regression called `earmark_disposition(BROKER_REJECTED, fill_evidence=True)`; submitted code returned `release`. | Once any share fills, no terminal label may return the proposal-time dollars to the pool. | Make credible fill evidence override every known, unknown, or malformed lifecycle label and consume the earmark. | Regression returns `consume`; existing unfilled release cases remain green. |
| M3REV-003 | P2 | Fixed | `7ee4786` | `assistant/storage.py::create_dividend_earmark_with_proposal` | The claimed authoritative storage fence accepted `confirmed_income_text` from its caller. A direct call could persist a funded proposal and earmark in a database with zero dividend income. | Red storage-level regression supplied a claimed `$500` pool against an empty journal; submitted code created a `$300` proposal. | The durable financial boundary must derive funding from authoritative journal rows, not trust a caller assertion. | Remove the asserted-total parameter and derive corporate-action `INCOME:DIVIDENDS` rows inside the same `BEGIN IMMEDIATE` transaction as the reservation and proposal insert. | Empty-journal direct creation now refuses without leaving either row; concurrency/oversubscription tests remain green. |
| M3REV-004 | P2 | Fixed | `7ee4786` | `assistant/sleeve_reinvest.py::dividend_reinvest_status`; `assistant/storage.py::create_dividend_earmark_with_proposal` | An unknown/future durable earmark status was omitted from both displayed unavailable money and the transaction's reserved total, silently returning its dollars to the pool. | Two red regressions changed an active row to `future_state`; submitted status reported `$500` rather than `$200` available, and storage created a second `$300` earmark. | Unknown durable state must reserve more, not less; only an explicit `released` transition proves availability. | Treat unknown statuses as effective `hold` in status and count every status except `released` in the transaction fence. | Both read-view and direct-storage regressions now fail closed. |
| M3REV-005 | P2 | Fixed | `7ee4786` | `assistant/sleeve_reinvest.py::dividend_reinvest_status`; `assistant/storage.py::create_dividend_earmark_with_proposal` | A corrupt negative stored earmark subtracted from unavailable money and could enlarge the dividend pool. | Red regression changed `$300` to `-300`; submitted status accepted it and did not raise. | Invalid durable money must never mint availability or permit a follow-on proposal. | Refuse nonpositive/invalid stored earmark amounts in the read model and transaction fence. | Status raises `SleeveReinvestError`; direct storage creation refuses with no proposal row. |
| M3REV-006 | P2 | Fixed | `7ee4786` | `scripts/run_personal_assistant.py::command_sleeve_reinvest_propose` | `--json` printed human reconcile lines before the JSON document whenever an older earmark transitioned, breaking the public machine-readable surface in a valid state. | Red CLI regression reconciled an expired SOXL proposal before creating NVDL; `json.loads(stdout)` failed on the leading text line. | A documented JSON mode must remain one parseable document across ordinary lifecycle states. | Suppress human transition lines in JSON mode and include structured `earmark_transitions` in the payload. | Regression parses the complete output and verifies the released transition. |

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open** from this review.

## Validation

- Submitted-tree baseline: **3,557 passed**, 25 known dependency warnings,
  in 707.79 seconds.
- Pre-fix reproduction: **7 intended failures** across the six findings; all
  were observed on `7ee4786` before correction.
- Corrected M3 + UI suites: **70 passed** in 17.02 seconds.
- Final repository suite: **3,564 passed, 0 failed/skipped**, 25 known
  dependency warnings, in 662.62 seconds.
- Repository-prescribed `compileall` passed, active-document consistency
  passed **19/19**, and `git diff --check` is clean.

## Assessment and acceptance

The submitted architecture is coherent and appropriately conservative in its
main path: proposals are never auto-submitted, pool writes are paired with
proposal writes, ambiguous proposal states hold, pricing uses the recorded
fresh-close boundary, and the existing execution cap remains authoritative.
The misses were concentrated at composition boundaries—two broker fill
representations, caller versus durable accounting authority, invalid durable
state, and human versus JSON output—rather than the basic routing algorithm.

M3 is accepted after correction `b6685b5`. The branch is local-only, unmerged,
and undeployed. Optional M4 remains deferred; merge, push, deployment, and any
epoch roll require separate owner authorization.
