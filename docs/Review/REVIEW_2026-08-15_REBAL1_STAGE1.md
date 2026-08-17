# Independent review — REBAL-1 Stage 1

Date: 2026-08-15

Reviewer: Codex

Base: `01dbed4`

Submitted head: `afa47d9` (PR #226 merge on `main`)

Review branch: `codex/review-rebal1-stage1-20260815`

Correction: `5519a69`

Disposition: **accepted after correction**

## Scope and method

The complete ordered range was reviewed commit by commit, including both
merge commits. The review covered the allocation-profile contract, sleeve
classification, exact-value handling, pending-order projection, policy
feasibility, the read-only Streamlit surface, tests, and current records. PR
#225's per-ticker experiment was also inspected because it entered `main`
inside the range; its removal in the adopted sleeve implementation is the
correct final disposition. The merge trees at `e067ad8` and `afa47d9` are
identical to their merged parents and contain no additional conflict edits.

Material findings were reproduced with regression tests before correction.
The first focused red run produced **17 failures / 48 passes**. The corrected
focused domain and UI suite passed **75 tests**. Generalized searches covered
the exact-money fields, pending-value consumers, policy-conflict status,
profile fingerprints, and sleeve-membership callers. No database, broker,
order, scheduler, deployment, mandate, policy file, or evidence epoch was
accessed or changed.

## Commit-by-commit disposition

| Commit | Disposition | Review result |
|---|---|---|
| `176f7f8` | **rejected** | Its per-ticker target model was exploratory and conflicts with the owner-adopted sleeve profile. No code from it survives the final tree; `6fcdd35` correctly removes both module and tests. |
| `e067ad8` | **rejected** | Merge tree equals `176f7f8`; no separate conflict edits. It is superseded for the same architectural reason. |
| `6fcdd35` | **accepted after correction** | The sleeve-based, read-only design is sound, but six material correctness/failure-direction defects and two minor hardening/presentation defects required `5519a69`. |
| `e03a320` | **accepted after correction** | The plan and evidence framing are sound. Current topology, review state, and projected-order semantics required reconciliation in this records commit. |
| `afa47d9` | **accepted after correction** | Merge tree equals `e03a320`; no separate conflict edits. Its final behavior is accepted with `5519a69` and the accompanying records update. |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| REBAL1R-001 | P2 | Closed | `6fcdd35` | `assistant/portfolio_rebalance.py` | Pending trades changed the asset sleeve but not cash, while status, breach count, and dollar gap used current rather than projected values. The projected portfolio did not conserve equity and could continue reporting a breach after a working order had already corrected it. | A $500 hedge buy moved hedge 5%→10% while cash remained 95%, status stayed underweight, and gap stayed $500. | Stage 1 promises pending-aware projection; internally inconsistent weights can mislead the owner and later duplicate corrective sizing. | Apply the opposite signed pending value to cash; classify bands and compute gaps from projected values. | Red in the initial 17-failure run; focused suite green at 75 tests. |
| REBAL1R-002 | P2 | Closed | `6fcdd35` | `assistant/portfolio_rebalance.py` | Policy conflict detection ignored total-exposure and per-position capacity. The approved 90% invested profile conflicts with the default 50% total-exposure cap, and the 40% growth target cannot fit six names capped at 5% each, yet the page called the profile feasible. | Target/cap arithmetic and two failing regressions. | A target above an active cap is unreachable; presenting its band without disclosure violates the feature's own cap-is-not-target rule. | Add total-exposure and configured-sleeve position-cap feasibility disclosures, retaining cash and leveraged checks. | Both new policy regressions pass; default-policy behavior is now explicit. |
| REBAL1R-003 | P2 | Closed | `6fcdd35` | `assistant/portfolio_rebalance.py` | A present but malformed broker notional fell back to `qty × limit_price`, hiding corruption in the authoritative field. | `notional="broken"`, `qty=10`, `limit_price=100` was measured as $1,000. | Authoritative malformed broker data must fail closed, not be replaced by a plausible estimate. | Derive from quantity and limit only when notional is absent; otherwise mark pending value unknown. | Red then green regression. |
| REBAL1R-004 | P2 | Closed | `6fcdd35` | `assistant/portfolio_rebalance.py` | Unreadable/order rows without tickers were silently ignored; unknown pending residual tickers were not named; unknown cash impact could be hidden, including behind policy-conflict status. | Non-dict and tickerless orders left the report usable; a plain AAPL order vanished from the residual list. | Silently dropping a working order understates exposure and defeats the page's every-holding/every-order honesty contract. | Refuse unidentifiable rows, surface pending-only residual tickers, mark both affected sleeve and cash unknown, and give unknown exposure status precedence. | Parameterized and precedence regressions pass. |
| REBAL1R-005 | P2 | Closed | `6fcdd35` | `assistant/portfolio_rebalance.py` | The public evaluator caught a wrong profile type, then dereferenced it while building the refusal report and crashed. | `evaluate_portfolio_rebalance(snapshot, object())` raised `AttributeError`. | Invalid public input must return the module's documented unusable report, not escape its fail-closed boundary. | Use safe empty profile identity fields on invalid input; fingerprint helper now raises the domain exception. | Red then green public-boundary regressions. |
| REBAL1R-006 | P3 | Closed | `6fcdd35` | `assistant/rebalance_profile.py` | Frozen profiles retained a mutable caller-owned target dict, so targets and behavior could change without a new object or fingerprint event. | Mutating the source dict changed the supposedly frozen profile. | Version/fingerprint binding is unreliable if nested state can mutate in place. | Copy targets and expose an immutable mapping proxy. | Source-mutation and direct-mutation regressions pass. |
| REBAL1R-007 | P3 | Closed | `6fcdd35` | `assistant/rebalance_profile.py` | Blank configured members were skipped and non-text values were coerced into ticker symbols. | Empty, whitespace, `None`, boolean, and integer members were accepted. | Corrupt classification config should refuse visibly rather than silently change portfolio membership. | Require a non-string collection containing only nonblank strings. | Five parameterized corrupt-config regressions pass. |
| REBAL1R-008 | P3 | Closed | `6fcdd35` | `scripts/personal_assistant_ui.py` | Exact decimal money strings were converted through binary float solely for display, risking rounding or infinity for large valid values; residual copy also described pending-only names as held. | Source inspection and presentation regression. | The UI should not weaken exact values preserved by the domain layer or mislabel an open order as a holding. | Format with `Decimal`; rename residual and gap copy to describe projected/current-or-pending exposure accurately. | UI source guard and AppTests pass. |

Issue total: **0 P0 / 0 P1 / 5 P2 / 3 P3; all closed; 0 open.**

## Accepted final behavior and limits

Stage 1 is a read-only sleeve report over a versioned, fingerprinted allocation
profile. It uses exact authoritative values, refuses denominator-corrupting
input, surfaces residual exposure, includes measurable working orders in a
cash-conserving projection, and discloses conflicts between owner targets and
active policy limits. It creates no side, quantity, proposal, approval, or
order. The wide-band research result remains explicitly limited to the
SOXX/SOXL experiment and is not presented as evidence that this portfolio
shape is profitable or protective.

Stages 2 and 3 remain unstarted. This review does not authorize buy steering,
tax-aware trims, automatic rebalancing, deployment, paper-order submission,
live trading, a policy/mandate change, an epoch roll, or operator-database
mutation. Stage 2 should begin only after an owner decision; Stage 3 still
requires separate explicit authorization because it introduces app-initiated
sell preparation.

## Validation

Environment: repository `.venv`, Python **3.13.14**, Streamlit **1.60.0**,
Windows.

- Submitted focused suite: **58 passed**.
- Red proof after adding review regressions: **17 failed / 48 passed**.
- Corrected focused suite (`test_portfolio_rebalance.py` and
  `test_ui_portfolio_rebalance.py`): **75 passed** in 7.17 seconds.
- Full corrected tree: **3,933 passed / 0 failed / 25 known dependency
  warnings** in 629.94 seconds.
- Repository compilation: clean.
- Final diff checks: clean.

The warnings are the existing `websockets.legacy` deprecation and 24 Joblib /
NumPy shape deprecations. No warning is introduced by REBAL-1.
