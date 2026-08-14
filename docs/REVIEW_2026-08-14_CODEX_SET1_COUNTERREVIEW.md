# Codex independent verification — SET-1 counter-review and PR #218

Date: 2026-08-14
Reviewer: Codex
Submitted tree: `45a510c`
Merged tree reviewed: `7055142` (PR #218)
Review branch: `codex/review-set1-counterreview-20260814`
Product/test correction: `29290d9`
Final disposition: **accepted after correction**

## Scope and method

This review covered every commit added by Claude's counter-review after the
previously accepted `ca0cdf0` base: product/document commit `45a510c` and its
two-parent integration merge `7055142`. `git diff --exit-code 45a510c 7055142`
proved the merge tree is exact. The four SET1CR changes were traced through
quantity authority, proposal validation, daily-budget reservation,
owner-directed selling, and the real Streamlit surface. The development
launcher was reviewed as execution-adjacent operational code rather than as
documentation, and generalized searches covered every current direct
Streamlit launch instruction.

The installed Streamlit 1.60 development skill and its version-matched best
practices were used for the UI checks. No real broker call, order, deployment,
operator-database write, scheduled-task change, evidence-epoch operation,
funded-account access, or live-trading action occurred.

## Commit-by-commit dispositions

| Commit | Type | Disposition | Result |
|---|---|---|---|
| `45a510c` | Claude counter-review, corrections, tests, launcher, and records | **Accepted after correction** | SET1CR-001 through SET1CR-004 are sound and retained. The new launcher was fail-open toward the shared paper account and omitted two supported provider keys; an order-dependent AppTest leak and post-merge record drift also required correction. |
| `7055142` | PR #218 merge | **Accepted after correction** | Both parents are correct and the merge tree exactly equals `45a510c`; the merge necessarily made the branch/topology prose stale, now corrected in the active records. |

## Verified sound — no code correction

- **SET1CR-001:** a positive fractional holding no longer disappears from
  Discrete Selling under strict whole-share mode, and a sellable holding's
  stranded remainder is named with the real protected-policy remedy. The
  strict floor itself remains unchanged.
- **SET1CR-002:** both strict and fractional quantity paths reject values
  above the shared `MAX_ORDER_QUANTITY`; sizing imports the same authority, so
  it cannot drift to produce a quantity the gate refuses.
- **SET1CR-003:** unreadable permissive-mode quantity conversion now refuses
  instead of manufacturing integral zero. Claude accurately labels this
  defense as unreachable through the current durable parser rather than
  claiming a live bypass.
- **SET1CR-004:** daily-budget notional uses the guarded finite Decimal
  boundary. Valid fractional quantities retain exact arithmetic, while
  `NaN`, infinity, and malformed text cannot poison reservation arithmetic.
- Strict remains the default at every omitted-policy boundary; binary floats
  remain invalid; broker `fractionable` is fail-closed; and reconciliation
  requires exact quantity equality.

## Prioritized issue ledger

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| CSET1CR-001 | P2 | Closed | `scripts/launch_dev_app.ps1`, `HOW_TO_USE.md`, `README.md`, UI module docstring | The launcher isolated SQLite but did not engage `TRADING_ASSISTANT_KILL_SWITCH`. With fresh paper credentials loaded, an approved development proposal could therefore reach the same Alpaca paper account and contaminate the active epoch despite a console-only warning. Generalized search found two README commands and the UI's own run instruction bypassing the launcher entirely. | The launcher now blocks submission by default. `-AllowPaperOrders` is an explicit development-paper opt-in and never writes an off value, so inherited and persistent kill switches still win. Primary instructions route through the launcher; the manual recipe pins both database and kill switch. | Six launcher contract tests, the existing kill-switch suite, PowerShell parser check, generalized launch-command search, and the full suite pass. |
| CSET1CR-002 | P3 | Closed | `scripts/launch_dev_app.ps1` | The new launcher claimed supported credentials were refreshed but lifted only Alpaca and Anthropic, omitting the UI's Finnhub and Databento keys. This repeated the earlier FCS-023 stale-parent-shell defect class and made configured development features appear unavailable after key setup or rotation. | Mirror the reviewed five-name operational launcher list without exposing values. | Source contract compares the exact set; operational-host and launcher tests pass. |
| CSET1CR-003 | P3 | Closed | `tests/test_ui_user_directed_sell.py` | AppTests share Streamlit's process-global data cache. Running the discrete-tabs suite before the older owner-directed-sell suite left cached page state that changed the expected share widget shape: the exact sequence failed with 1 failed / 23 passed although the sell file passed alone. | Clear `st.cache_data` in the sell module's offline fixture, matching the isolation discipline already used by adjacent UI suites. | The failure reproduced before correction; the complete settled-tree suite now passes 3,759 tests. |
| CSET1CR-004 | P3 | Closed | Action Plan, milestone record, Session Handoff | After PR #218, the Action Plan still described `cfed8c8` as `origin/main`, its SET-1 row called `ca0cdf0` current main, the milestone called the correction local-only, and the handoff told the next agent to review an already merged Claude branch. | Reconcile all active authorities to `7055142`, record this verification and correction branch, and preserve the deployed epoch separately at `752d3b7`. | Active-document consistency suite and diff checks are required after the record commit. |

Issue total: **0 P0 / 0 P1 / 1 P2 / 3 P3; all closed; 0 open**.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Claude counter-review suite: **15 passed** as part of the affected and full
  runs.
- Launcher, operational-launcher, and environment-kill-switch contracts:
  **39 passed**; `launch_dev_app.ps1` parsed cleanly without execution.
- The pre-correction order-dependent UI sequence failed as described in
  CSET1CR-003; the corrected settled tree passed the full suite.
- Full repository suite after product/test correction: **3,759 passed / 0
  failed / 25 known dependency warnings** in 888.59 seconds.
- Post-record active-document, launcher, SET-1, exact UI-order, kill-switch,
  and operational-launcher checks: **138 passed**.
- `compileall`, `git diff --check`, and staged checks are clean.

The full run occurred on one settled tree. No source or documentation was
edited concurrently with it.

## Untested and explicit boundaries

- The launcher was parse-checked and source-contract tested, not used to
  start a Streamlit server during this review.
- No fractional order has yet been submitted to Alpaca from this code. The
  exact REST quantity path and fractionable-asset rule remain fixture-verified,
  not broker-observed.
- The owner's open design question remains open: strict mode currently does
  not permit a fractional sell solely because it would close the entire
  position. Turning off Whole shares only remains the explicit remedy.

## Operational result

This is development code only. `paper-epoch-005` remains recorded as active
on frozen deployed commit `752d3b7`; this review did not remeasure it. SET-1's
policy-fingerprint change would close that lineage if later deployed. Merge,
push, deployment, epoch roll, funded-account access, and live trading require
separate owner authorization.
