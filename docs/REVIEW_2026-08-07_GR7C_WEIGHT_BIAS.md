# Independent review — GR-7c follow-ups (cash-flow skip + weight bias) — 2026-08-07

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `58a10ab` (prior independent GR-7c acceptance).
Review head before corrections: `fbc9ed2` (`main` tip, PR #164 merge).
Review branch: `user/grok/review-gr7c-weight-bias-20260807`.

| Commit | Disposition |
|---|---|
| `0e84c40` Counter-review GR-7c: refuse when a skipped point carried a cash flow | accepted after correction (GR7CFOLLOW-001 shows the kept path was still wrong; skip refusal retained) |
| `63d38a8` Merge PR #163 | accepted (merge-only) |
| `6cebe09` Fix a capture-frequency bias in the GR-7c invested-weight average | accepted after correction (GR7CFOLLOW-002/003 disclosure and human-CLI label) |
| `fbc9ed2` Merge PR #164 | accepted (merge-only) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout stays frozen at `9a91498` under `paper-epoch-002`.

## 2. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR7CFOLLOW-001 | P1 | Resolved | `0e84c40` / pre-existing wiring on `1da4154` | `evaluate_attribution` Observation construction; CLI snapshot mapping | `portfolio_equity_snapshots.total_equity` is **post-flow** broker equity. Attribution passed it as `Observation.value_before_flow`, so deposits were credited as return and landed in selection. CFPS-GR7C-001 closed only the *skip* path. | Pure deposit series 100→200(+flow100)→200 reported `portfolio_pct=33.3333` (selection same); `portfolio_performance_report` reports 0%. | A performance report whose residual is mostly a bank transfer fails the milestone's honesty contract. | `value_before_flow = total_equity - flow`; document snapshot convention; reject `total_equity - flow < 0`. | `test_a_deposit_is_not_counted_as_a_gain`, `test_cli_deposit_on_kept_snapshot_is_not_counted_as_return`; mutation restoring old wiring fails both at `33.3333` |
| GR7CFOLLOW-002 | P3 | Resolved | `6cebe09` | attribution payload | Session-equalized weight had no method/unit fields; operator cannot tell point-mean vs session-equalized from JSON. | Payload exposed only `average_invested_weight_pct`. | Same class as GR7CREV-004: method must travel with the number. | Added `average_invested_weight_method` / `_unit`. | Asserted in deposit CLI + session-equalization tests |
| GR7CFOLLOW-003 | P3 | Resolved | residual of GR7CREV-005 | human CLI print | Non-JSON path always printed "cash drag" even when `w>100%`. | Hardcoded string at human output. | Label honesty must hold on the default operator surface, not only JSON. | Conditional label from weight; print method. | `test_human_cli_does_not_call_leverage_cash_drag` |

Prior ledger items GR7CREV-001..005 and CFPS-GR7C-001/002 remain resolved; CFPS-GR7C-001's skip refusal is necessary but was not sufficient alone (see GR7CFOLLOW-001).

## 3. What was confirmed sound

- Session-equalized BoP weight math in `6cebe09` (mean of per-session means over `ordered[:-1]`).
- Skip-with-nonzero-or-unreadable-flow refusal (`_note_skip`).
- Reconciliation still asserted on unrounded values; test slack for rounded report fields is appropriate.
- No provider-fetch / execution writes on the attribution CLI path.
- Selection remains labelled residual; sector Brinson still correctly undefined.
- Nothing deployed mid-epoch.

## 4. Quality score

Claude follow-ups submitted: **8/10** (weight-bias fix strong; cash-flow skip real but incomplete vs snapshot convention).
Corrected tree: **9.5/10**.

## 5. Validation

Windows, Python 3.13.

- Focused: **35 passed**.
- Mutation: restoring `value_before_flow=point.total_equity` fails both deposit tests at `33.3333`; restored green.
- Exact final tree: **2955 passed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

Nothing deployed mid-epoch.
