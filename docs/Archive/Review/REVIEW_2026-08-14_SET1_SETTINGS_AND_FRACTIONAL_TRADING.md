# Independent review — TRADE-1 counter-review integration and SET-1 settings

Date: 2026-08-14
Reviewer: Codex
Base: `a5d5fe3`
Merged source head reviewed: `cfed8c8` (`origin/main`, PR #214)
Correction branch: `codex/review-set1-settings-toggles-20260814`
Correction commit: `89156b7`
Final disposition: **accepted after correction**

## Scope and method

The review covered the complete new history after the previously reviewed
TRADE-1 branch: Claude's TRADE-1 counter-review, Claude's SET-1 implementation,
both integration merges, and the resulting combined tree. Each ordinary and
merge commit received a separate disposition. Production paths were followed
from the Settings & Features controls through policy persistence/fingerprint,
proposal sizing, durable intent JSON, fresh execution validation, broker asset
preflight, submission, and ambiguous-outcome reconciliation. The cash-reserve
direction was traced separately through the existing solvency and reserve
checks. Streamlit behavior was checked against the installed 1.60.0 skill and
AppTest surface. Alpaca's official fractional-order contract was checked for
fractionable-asset eligibility, day time-in-force, and the nine-decimal
quantity limit.

No funded-account call, order, deployment, scheduled-task mutation, operator
database mutation, evidence-epoch operation, or live-market request occurred.

## Commit-by-commit disposition

| Commit | Type | Disposition | Review result |
|---|---|---|---|
| `9e07bf9` | Claude TRADE-1 counter-review | **Accepted** | Correctly confirmed all eight TRADE-1 findings, fixed the deselectable segmented-control state (TRADE1CR-001), and recorded the date-fixture limitation. Its product/test change remains load-bearing. No new product issue found. |
| `6085f44` | Claude SET-1 implementation | **Accepted after correction** | The protected policy controls, strict default, fingerprint binding, float refusal, and zero-reserve/solvency distinction were sound. It did not implement the owner's fractional-share behavior beyond a dormant authority helper, did not validate the new boolean, admitted unsupported precision, used checkbox widgets for requested settings toggles, and left the execution/reconciliation path whole-share-only. Corrected in `89156b7`. |
| `a62aa1a` | PR #213 merge | **Accepted after correction** | The merge itself introduced no conflict-resolution code. It merged SET-1 before independent acceptance and left the Action Plan claiming the work was unmerged; final product and records are corrected on this branch. |
| `e6c6748` | Merge of SET-1 into the TRADE-1 review branch | **Accepted after correction** | Product/test trees combined without losing either feature. The merge retained mutually stale state prose: the handoff still described the pre-counter-review, pre-merge topology while the Action Plan called the already-merged SET-1 branch unmerged. Records are reconstructed in this review. |
| `cfed8c8` | PR #214 merge/resulting `main` tree | **Accepted after correction** | The combined TRADE-1 + counter-review + SET-1 code had no merge-conflict regression. The final tree still contained SET1R-001 through SET1R-006 and a handoff whose next step had already happened. Corrected in `89156b7` and the accompanying record commits. |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SET1R-001 | P2 | Closed | `6085f44` | `assistant/allocation_proposals.py`, `assistant/discrete_trade.py`, `assistant/user_directed_sell.py`, execution kernel, broker adapter | Turning **Whole shares only** off changed a policy value but every production sizing, validation, and broker path still refused or floored fractional quantities. The delivered behavior therefore did not meet the owner's definition of done. | Submitted commit explicitly documented “order path is not yet fractional end to end”; call-site tracing found no production read of the flag outside settings/policy. | A safety setting that promises permission must either work through the full authority path or remain unavailable; a UI-only permission is materially misleading. | `89156b7` threads policy granularity through budgeted/discrete buy and sell sizing, durable intents, gate arithmetic, submission dispatch, broker submission, and reconciliation. | End-to-end test persists and executes `0.5` as exact text with the permissive flag; focused safety suite 344 passed. |
| SET1R-002 | P2 | Closed | `6085f44` | `assistant/policy.py` | `whole_shares_only` was omitted from boolean validation. A hand-edited `0`, empty string, or other non-boolean could select permissive behavior through truthiness instead of failing policy load. | Existing non-boolean mutation test covered every other policy bool but not the new field; direct construction validated malformed values. | This field changes what quantities may be executed. Ambiguous durable policy state must fail closed. | Added the field to the canonical boolean validation boundary. | Extended policy mutation test passes; full suite passed all other policy tests. |
| SET1R-003 | P2 | Closed | `6085f44` | `risk/execution_gate.py`, `assistant/execution_kernel/validate.py`, `execution/alpaca_broker.py` | The permissive helper accepted arbitrary decimal precision and had no broker `fractionable` eligibility check or exact last-mile representation. A later caller could approve a quantity Alpaca must reject or round. | `0.1234567891` was accepted locally; broker preflight result was ignored for fractional eligibility; the pinned SDK coerces `qty` to float. | Local approval must represent an order the selected asset and broker API can actually accept, without changing the authorized digits. | Enforced positive exact quantities with at most nine decimal places, checked the fresh asset flag in validation and again at submission, and used exact JSON quantity text for fractional REST submission while preserving the SDK path for whole shares. | Precision, non-fractionable-asset, exact REST payload, and no-HTTP-on-refusal tests pass. |
| SET1R-004 | P2 | Closed | resulting tree at `cfed8c8` | `assistant/execution_kernel/outcomes.py` | Broker reconciliation compared share quantities through float and a `1e-9` absolute tolerance. Once nine-decimal fractional orders are authorized, that can accept a one-nanoshare identity mismatch under the same idempotency key. | `0.500000001` reconciled as equal to intended `0.5` at the tolerance boundary. | Reconciliation is the evidence used after an ambiguous submission. Material order identity must be exact, not “close enough.” | Prefer broker `shares_decimal` and compare guarded Decimals exactly. | The one-nanoshare mismatch regression test passes; existing numerically equivalent whole representations still match. |
| SET1R-005 | P3 | Closed | `6085f44` | `scripts/personal_assistant_ui.py` | The two requested settings switches were rendered as checkboxes, contrary to the requested toggle behavior and the installed Streamlit settings-widget guidance. | AppTest enumerated both controls under `checkbox`, not `toggle`. | These are durable on/off settings; the toggle control communicates that model consistently and matches the owner's UI request. | Replaced both new settings controls with `st.toggle` without changing the typed `UPDATE POLICY` workflow. | AppTest confirms both toggle labels, protected confirmation, and reserve-off copy. |
| SET1R-006 | P3 | Closed | `a62aa1a`, `e6c6748`, `cfed8c8` | `docs/SESSION_HANDOFF.md`, `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md`, `HOW_TO_USE.md`, UI copy | Current records said merged work was unmerged, requested a counter-review already completed, named `a5d5fe3` as `origin/main`, and described fractional execution as future-only. | Git topology resolves `origin/main` to `cfed8c8`, SET-1 to PR #213, TRADE-1 review to PR #214, and counter-review `9e07bf9` as an ancestor of main. | The handoff and Action Plan are recovery/sequence authorities; contradictory topology can make the next agent repeat work or act on the wrong branch. | Rebuilt the handoff from Git truth, corrected both roadmap rows, updated the usage/UI language, and added this review plus the SET-1 milestone record. | Active-document consistency suite and final diff checks are recorded below. |
| SET1R-007 | P3 | Closed | review worktree before `89156b7` | allocation sizing and reconciliation conversion sites | The first correction draft introduced four bare `Decimal(str(...))` sites, violating the repository's AST-enforced guarded-conversion rule. | Full suite: 3,737 passed and `test_decimal_conversion_guard` named all four sites. | The guard exists because bare conversion accepts non-finite literals and raises the wrong exception class for malformed text. A review correction may not weaken it. | Replaced all four with canonical guarded conversion; also made invalid allocation budgets/weights refuse rather than poison sizing. | Guard plus affected boundary suite: 34 passed. No bare site remains outside the reviewed allowlist. |
| SET1R-008 | P3 | Closed | review worktree before `89156b7` | `assistant/execution_kernel/submit.py` | The first correction draft passed the new keyword even in strict mode, breaking existing broker seams/test doubles whose strict default already enforced whole shares. | Adjacent suite exposed the public compatibility regression; 255 passed / 1 failed before the fix. | SET-1 should add an optional direction without forcing every pre-existing strict adapter to change signature. | Emit `whole_shares_only=False` only for the new fractional direction; omission continues to mean strict. | Failed compatibility case and end-to-end fractional case both pass after correction. |

Issue total: **0 P0 / 0 P1 / 4 P2 / 4 P3; all closed; 0 open**.

## Corrected behavior and safety boundaries

- **Whole shares only** remains `True` by default. Omitted flags at the gate,
  dispatch layer, and broker adapter remain strict.
- With the setting off, Budgeted Buying, Discrete Buying, and Discrete Selling
  create exact share quantities with at most nine decimal places. Dollar mode
  remains a budget converted to a quantity; it is not a broker-notional order.
- Fractional quantities are canonical decimal strings in proposal JSON and
  authorization fingerprints. Binary floats remain rejected as order input.
- Fresh validation and last-mile submission both require the broker asset to
  be marked fractionable. Whole-share orders retain the established SDK path;
  fractional orders send exact quantity text through Alpaca's REST order
  endpoint with day time-in-force and the existing client order ID.
- Reconciliation compares the broker's exact decimal quantity to the intended
  quantity with no tolerance.
- Disabling the cash-reserve switch writes `min_cash_reserve_pct = 0`; it does
  not add a second source of truth and does not disable the negative-cash
  solvency refusal.
- Both changes still require typed `UPDATE POLICY`, atomic expected-fingerprint
  persistence, and proposal regeneration under the new fingerprint.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Focused SET-1, policy, sizing, proposal, gate, broker, reconciliation, and UI
  suite: **344 passed**.
- Adjacent execution/batch/replacement/UI suite before the compatibility fix:
  **255 passed / 1 failed**; the failure was SET1R-008 and passes after repair.
- First complete repository run: **3,737 passed / 1 failed / 25 warnings** in
  973.49 s; the sole failure was SET1R-007's static guard, not an environment
  artifact.
- Guard and directly affected allocation/reconciliation/end-to-end rerun after
  correction: **34 passed**.
- Repository compilation: clean. Working/staged diff checks: clean apart from
  expected Windows line-ending notices.

The final full-suite rerun and active-document consistency result are appended
to the handoff after the documentation tree is complete.

## Operational and authorization result

This review changes development code only. `paper-epoch-005` remains pinned to
deployed commit `752d3b7`; nothing in `89156b7` is deployed. Because the new
policy field participates in `compute_policy_fingerprint`, deploying even its
safe default changes execution lineage and closes the active epoch. Merge,
deployment, epoch roll, funded-account access, live trading, scheduled-task
changes, M4, and operator-database mutation all remain unauthorized unless the
owner gives a separate explicit instruction.
