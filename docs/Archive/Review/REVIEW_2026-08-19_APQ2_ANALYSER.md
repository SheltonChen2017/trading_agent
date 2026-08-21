# Independent review: APQ-2 allocation-policy analyser

Status: **accepted**. Prepared: 2026-08-19. Reviewer: Cursor Grok 4.6.
Isolated worktree `C:\git\customizedAgent\trading_agent-review-apq2` on
`user/cursor/review-apq2-20260819`. No QuantConnect run. No operator
database. No APQ-3 driver change. No statistic on a real cloud log.

**Reporting decision (fixed here, before any run):** the optional
excess-mean test family **is reported** in this schema — three cells
(P1/P2/P3 vs P0), two-sided stationary bootstrap, 20,000 draws,
Bonferroni 0.05/3 — with both required labels (`family` identity and
`scope` this-family-only / A-002 untouched). A descriptive table without
a frozen test is an eyeball channel; a fail is the expected outcome and
ends the family. A pass is not trade authorization. Striking the family
after this review would be a new schema, not a post-result choice.

## 1. Snapshot

| Item | Value |
|---|---|
| Branch | `origin/user/claude/apq2-analyser-20260819` |
| Review head | `5364ae6ab400111123623fddcae27643350c3143` |
| Base | `92a00771835319f84233433d82555d21a72c061c` (`origin/main` at fetch; APQ-1 review merge #271) |
| Range | `92a0077..5364ae6` (2 commits) |
| Review branch | `user/cursor/review-apq2-20260819` from that exact head |

Fetched. APQ-2 definition of done: analyser + tests, no QC.

## 2. Verdict

**Accept both commits.** The analyser parses `PROW` only, fail-closes on
the listed corruptions, joins all four policies onto one date set,
reuses reviewed `performance()` / `stationary_bootstrap_p()` /
`bonferroni_threshold()`, charges empty turnover with `fillna(1.0)`,
emits 0/5/10/25 bps nets, descriptive `versus_p0`, and the ratified
optional family. Script-mode `--help` works (S1R-001). It does not
import `analyse` from the alpha-battery analyser. Focused tests **9
passed**. `compileall` clean.

No P0. No P1. No P2. Two P3.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `163c590` APQ-2 analyser and tests (no QC) | **Accepted.** Reporting decision ratified as implemented. | Unknown policy / duplicate / `nan` turnover / `inf` return / `priced != targeted` / wrong member count / misaligned dates / truncated `DATES` / 23-month floor all raise `AllocationLogError`. Magnitude pin: one empty P1 turnover → net 10 bps vs 0 bps delta `1.0 * 2 * 10 / 10000 / 24`. Bonferroni `0.05/3`. Labels in JSON. `DRAWS=20000` with ABR-001 reachability guard. AST: no `analyse` import from `analyse_qc_alpha_battery`. `--help` from `scripts/` cwd exit 0. `fillna(1.0)→0.0` mutation **red** on the magnitude pin; restored green. |
| `5364ae6` Record the APQ-2 round | **Accepted** with APQ2-002. | §7ay states the proposed reporting decision honestly. §8 still said APQ-2 was next (this review updates it). |

## 4. Reverse mutation

| Mutation | Result |
|---|---|
| `fillna(1.0)` → `fillna(0.0)` | `test_report_carries_descriptives_labels_and_pinned_charge` **RED**: delta `0.0` vs `8.33e-5`. Restored. Test **GREEN**. |

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| APQ2-001 | P3 | Open | `163c590` | `_policy_block` `mean_turnover` | Mean turnover uses pandas skipna, so declared-unavailable months (charged 1.0 in **net** returns) are omitted from the mean. | `numeric_turnover.mean()` after leaving empties as NaN. | The primary table's mean turnover understates costed activity whenever the empty-field path fired. | At APQ-5, read `unavailable_turnover_periods` beside the mean; or mean the charged series in a later schema. | Not a silent substitute for the net block. |
| APQ2-002 | P3 | Closed in this review | `5364ae6` | `docs/SESSION_HANDOFF.md` §8 | §7ay records APQ-2 implemented; §8 still pointed at APQ-2 as next. | Read at `5364ae6`. | Sequencing pointer. | This review's handoff names APQ-3 next, no QC. | Read §8 after this commit. |

## 6. Explicit non-findings

- Empty turnover is unavailability; present `nan`/`inf` tokens refuse.
- `priced != targeted` is corruption per APQ1-003; member counts are
  pinned per policy.
- Excess series is date-aligned because both sides are sorted by the
  shared date set.
- Bootstrap is two-sided, block, `(count+1)/(draws+1)`, refuses `n<24`
  (parser already requires 24).
- Transitive `ml.evaluation` import via `run_alpha_battery_20260815` is
  the planned helper reuse; it is not an execution-module `ml` import.
- No orders, no QC launch, no live/paper allocation change.

## 7. What this review does not authorize

APQ-3 launch-driver hook, any QuantConnect backtest, any analyser pass
on a real log, any statistic, any paper or live weight change.
