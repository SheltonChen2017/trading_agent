# Independent review: APQ-1 allocation-policy LEAN algorithm

Status: **accepted after correction**. Prepared: 2026-08-19. Reviewer:
Cursor Grok 4.6. Isolated worktree
`C:\git\customizedAgent\trading_agent-review-apq1` on
`user/cursor/review-apq1-20260819`. No QuantConnect run. No operator
database. No analyser. No launch-driver change.

The implementation branch is two commits. `origin/main` already contains
PR #270 (`46feb1e`); its second parent is `e2c4a2b` and
`46feb1e^{tree}` equals the implementation tree. This review still
dispositions the named branch. It does **not** start APQ-2 or authorize
a cloud run.

## 1. Snapshot

| Item | Value |
|---|---|
| Branch | `origin/user/claude/apq1-allocation-policy-20260819` |
| Review head (submitted) | `e2c4a2be751f6472accd709d6694dbcbe67f67db` |
| Base | `01508b126c8efb8701dc6698e82b26c1b23de5ee` (first parent of PR #270) |
| Range | `01508b1..e2c4a2b` (2 commits) |
| Review branch | `user/cursor/review-apq1-20260819` from that exact head |

Fetched. APQ-1 definition of done (plan): tests green, `compileall` of
the new module, no QC, not in `FAMILIES`.

## 2. Verdict

**Accept both commits after APQ1-001.** The algorithm matches the frozen
preregistration on instruments, weights, window constants, monthly
month-end cadence, bind-time `_drift_turnover` (same shape as
`universe_benchmark.py`), union-aligned refusal, 24-month INCOMPLETE
floor, empty turnover after a gap, and zero `ACTIVE_UNIVERSE`
assignment. It is not on the Stage 0 launch driver.

Preregistration section 3 requires a **non-finite** close to refuse the
date. The submitted positivity check accepts `inf` (`inf > 0`) and
emits `PROW|…|inf|…`; `NaN` at the boundary failed `value <= 0` (False)
then `_member_returns` returned `None` and the row loop TypeError'd.
Closed in this review with `math.isfinite` and a regression test.

No P0. No P1. One P2 (closed here). Two P3 remain open.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `4b36d14` APQ-1 LEAN algorithm + local tests (no QC) | **Accepted after APQ1-001.** | Weights P0–P3 and 0.10 XLE match prereg §4. `START`/`END`/`MIN_MONTHS` match §2/§5. BIL is an equity, not Lean cash. `_drift_turnover({}, target)` is 0.5 entry; subsequent months use prior-month outcomes (bind-time). One missing ticker drops all four policies; gap month emits empty turnover. `INCOMPLETE` at 2 < 24 with zero `PROW`. No `^ACTIVE_UNIVERSE\s*=`. Not in `scripts/run_qc_stage0.py` `FAMILIES`. Focused tests 6 passed on the submitted tree; 7 after the fix. `compileall` clean. Reverse mutation of the isfinite guard red (inf rows). |
| `e2c4a2b` Record the APQ-1 round | **Accepted** with APQ1-002/003. | Handoff §7aw matches the files. ACTION_PLAN ALLOCATION row records APQ-1 implemented awaiting review. Section 8 was left on the pre-roll SHW-4 paragraph (contradicts §7av already in the same file). |

## 4. Reverse mutation (APQ1-001)

| Mutation | Result |
|---|---|
| `_usable_close`: drop `math.isfinite` (keep `> 0`) | `test_nonfinite_close_refuses_the_boundary_for_all_four_policies` **RED** on `inf` (`PROW\|202202\|P0\|inf\|…`). NaN is already refused by `> 0`. Restored. Test **GREEN**. Suite **7 passed**. |

Submitted-tree reproduction (before the fix): inf → four `PROW` rows
with return `inf`; NaN → `TypeError: 'NoneType' object is not
subscriptable`.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| APQ1-001 | P2 | Closed in this review | `4b36d14` | `allocation_policy.py` `_month_boundary` / `_member_returns` | Non-finite closes are not refused. Inf emits infinite policy returns; NaN crashes instead of INCOMPLETE/aligned refusal. | Prereg §3: "non-finite close on a rebalance date" must refuse that date for every policy. Probe: `SPY=inf` → `PROW\|…\|inf`; `SPY=nan` → TypeError. Sibling batteries use `math.isfinite`. | APQ-2 is specified to refuse non-finite **turnover** tokens, not infinite **returns**; a cloud log with `inf` would be a counted look of unusable evidence. | `_usable_close` requires `math.isfinite` and `> 0`; both ingest and return helpers use it. | New test red without isfinite, green with it. 7 passed. |
| APQ1-002 | P3 | Open | `e2c4a2b` | `docs/SESSION_HANDOFF.md` §8 | §7aw records APQ-1 implemented; §8 still says the next work is the epoch-005 roll and that `origin/main` is `f63ba89`. §7av in the same file already recorded the roll as executed. | Read §7av vs §8 at `e2c4a2b`. | The handoff's "what is next" is the sequencing pointer agents follow. | This review's handoff update points at APQ-2 after APQ-1 review. | Read §8 after this commit. |
| APQ1-003 | P3 | Open | `4b36d14` | `PROW` priced/targeted fields | Emitted rows always set `priced == targeted == len(policy weights)` even though union refusal required all five tickers. P0 logs `1\|1` after a five-name completeness gate. | Rows in `test_two_priced_months_*`. | Harmless while union refusal holds; an analyser that treats `priced` as "names that actually priced in the union" would be wrong. Document at APQ-2. | No product change. | — |

## 6. Explicit non-findings

- Union refusal is stricter than "targeted name only" and matches the
  plan's keep-series-aligned rule (P0 is refused when XLE is missing).
- Last calendar month of the window is not force-settled: with
  `END=(2026, 8, 18)` the last complete month-end is July, which matches
  "last complete US session on or before 2026-08-18".
- Gross/net 0/5/10/25 bps is APQ-2 analyser work, not APQ-1.
- No orders (`orders_count` stays 0). No `ml` import. No paper/live path.
- Local tests use a stub `QCAlgorithm`; they do not prove LEAN `Symbol`
  key identity. A mismatch would fail-closed (every boundary unpriced →
  INCOMPLETE).

## 7. What this review does not authorize

APQ-2 analyser, APQ-3 driver hook, any QuantConnect launch, any
statistic, any paper or live allocation change.
