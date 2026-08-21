# Independent review — GR-7c performance attribution — 2026-08-06

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `d3f50db` (`main`, post GR-7b / PR #162).
Implementation: `1da4154`.
Review branch: `user/grok/review-gr7c-attribution-20260806`.

| Commit | Disposition |
|---|---|
| `1da4154` GR-7c: attribute return to cash drag and a labelled residual | accepted after correction (GR7CREV-001..005) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout stays frozen at `9a91498` under `paper-epoch-002`.

## 2. Issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| GR7CREV-001 | P2 | Resolved | `evaluate_attribution` `_amount` | NaN/Inf `realized_cost`/`realized_tax` raised raw `ValueError` from `to_decimal`; CLI catches only `AttributionError`. | Normalize to `AttributionError`. | `test_nan_realized_cost_refuses_as_attribution_error` |
| GR7CREV-002 | P2 | Resolved | CLI invested derivation | `invested = max(0, equity - cash)` silently treated cash>equity as all-cash, hiding corrupt snapshots. | Skip with explicit `cash exceeds equity` reason. | `test_attribution_cli_skips_cash_exceeding_equity_instead_of_clamping` |
| GR7CREV-003 | P2 | Resolved | tests | No CLI read-only proof (CLAUDE.md §9); GR-7b had one. | Assert execution + `data_provider_fetches` unchanged. | `test_attribution_cli_leaves_execution_and_evidence_tables_untouched` |
| GR7CREV-004 | P3 | Resolved | CLI help / argparse | `--minimum-observations` help said "valuation points" but sufficiency counts **sessions**; `--limit` accepted non-positive ints. | Session-accurate help; `_positive_int` for both. | Parser types |
| GR7CREV-005 | P3 | Resolved | `allocation_meaning` | Always labelled "Cash drag" even when average weight > 100% (leverage / negative cash), inverting the narrative. | Conditional meaning when `w > 1`. | `test_overinvested_weight_does_not_claim_cash_drag` |

## 3. What was confirmed sound

- Single SPY bucket matching paper-evidence; sector Brinson correctly treated as undefined without mandate weights.
- Beginning-of-period weights; deposit/flow handling via `time_weighted_return`.
- Selection labelled residual, not skill; cost/tax outside the identity.
- Session-based sufficiency (not intraday point inflation); recorded `session_date` not UTC-derived.
- Read-only CLI: snapshots only, no packet/provider fetch; account-key isolation.
- No UI in this milestone (ACTION_PLAN scoped to module + CLI) — accepted.
- No `ml` import; no proposal/execution path change.

## 4. Quality score

Submitted: **8.5/10**.
Corrected: **9.5/10**.

Strong modelling honesty (BoP weights, session sufficiency, residual labelling). Misses were failure-mode packaging: silent clamp, exception typing, missing read-only test, and a label that lied under leverage.

## 5. Validation

Windows, Python 3.13.

- Focused: **35 passed**.
- Exact final tree: **2947 passed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

Nothing deployed mid-epoch.

## 6. Claude counter-review of this review

All five findings **accepted**. Two deserve specific acknowledgement:

- **GR7CREV-002 was worse than "a silent clamp".** The submitted code
  clamped `max(0.0, equity - cash)` under a comment that claimed it would
  "clamp **and report**". It did not report. A comment asserting a
  guarantee the code does not provide is the specific thing CLAUDE.md §8
  forbids, and it would have persuaded the next reader not to look.
- **GR7CREV-004** was self-inflicted drift: the `--minimum-observations`
  help text was written before sufficiency changed from valuation points to
  sessions and was never updated, so the CLI documented the superseded
  model. Grok also correctly reused the existing `_positive_int` helper
  rather than adding a parallel validator — verified it exists and is the
  same one `--stale-after-seconds` uses.

GR7CREV-001/003/005 confirmed as described. The `w > 1` case in 005 is real:
`(w-1)*R_b` is *positive* under leverage when the benchmark rises, and
calling that "cash drag" inverts the narrative for an account holding
negative cash.

### Residual finding from this counter-review

| ID | Priority | Status | Issue | Correction |
|---|---|---|---|---|
| CFPS-GR7C-001 | P2 | Resolved | **Skipping a valuation point drops its external cash flow, silently reintroducing the deposit-as-gain error.** The chain links across the gap, so the equity jump the deposit caused is read as return. Reproduced: dropping a point whose $100 deposit doubled equity reports **+100%** where the honest answer is 0%. This hole is **originally mine** — the pre-existing "no benchmark close" skip had it — and GR7CREV-002's new `cash > equity` skip widened it. Narrow to reach, severe when reached: a performance report whose headline number is mostly a bank transfer. | All three skip sites now route through `_note_skip`, which inspects the snapshot's `net_external_flow`. Any skipped point carrying a non-zero — or unreadable — flow refuses the whole report rather than publishing a return it cannot stand behind. A skip with no flow still proceeds, since no money moved and the chain stays honest. |

Also added: a test that the CLI never pools two account keys into one
return series (the operator database holds both the live paper account and
`manual:manual` sample rows), which was implemented but unpinned.

Mutation result: removing the refusal fails
`test_cli_refuses_when_a_skipped_snapshot_carried_an_external_flow`;
restored green.
