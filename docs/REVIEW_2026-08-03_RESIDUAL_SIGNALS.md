# Independent review — residual, volatility-scaled momentum, and PEAD-persistence candidates

Prepared: 2026-08-03 by Codex.

Topic base: `661a7d4`
Implementation commits: `dcce056`, `a1d2587`
Merged-tree base for review: `711095c`
Merge: `5a6ffd5` (PR #121)
Review branch: `codex/review-pr120-pr121-20260803`
Review correction/report: the commit containing this file

## Commit dispositions

| Commit | Scope | Disposition |
|---|---|---|
| `dcce056` | Residual momentum, residual reversal, volatility-scaled momentum, three-signal runner, and tests | Accepted after RSREV-002 correction; the six-cell denominator was correct before the family was expanded |
| `a1d2587` | PEAD-persistence signal, companion runner, and tests | Accepted after RSREV-001/003 corrections; adding this fourth signal made the other runner's six-cell denominator stale |
| `5a6ffd5` | Merge PR #121 into `main` on top of PR #120 | Accepted after RSREV-001 through RSREV-004 corrections; every topic file is byte-identical to `a1d2587` |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| RSREV-001 | P1 | Resolved | `a1d2587`, `5a6ffd5` | `scripts/run_residual_signal_significance.py` | PEAD persistence was declared cells 7–8 of the same four-signal screen, but the three-price-signal runner still passed `n_tests=6`. Its threshold was `0.05/6 = 0.008333...` instead of the family-wide `0.05/8 = 0.00625`, so a future p-value in `[0.00625, 0.008333...)` would be reported significant only because the runner under-counted the family. | The merged scripts simultaneously defined `N_TESTS = 6` and `N_TESTS = 8`; the PEAD runner explicitly said both belonged to one 2026-08-03 screen. The repository's existing multiplicity guard documents this exact false-positive failure class. | Research reports must use one predeclared family denominator. A reporting-only script has no execution authority, but a false confirmation label can contaminate later strategy decisions and registry evidence. | Add one shared frozen candidate-screen contract listing all four signals and deriving `N_TESTS=8`; both runners import and pass that exact value, and every displayed threshold now derives from it. | New regression test failed red on the merged implementation (shared contract absent and the price runner local value was six), passed after correction, and detected a reverse mutation that removed PEAD from the shared family. No prior positive conclusion changes: the recorded first price run cleared neither the looser alpha/6 bar nor the stricter alpha/8 bar. |
| RSREV-002 | P2 | Resolved | `dcce056`, `a1d2587`, `5a6ffd5` | both significance runners | If the engine output ever lost the `primary` column, each runner fell back to treating the entire sensitivity grid as primary evidence. That is the dangerous failure direction: an interface drift would silently promote discovery, alternate-weighting, and alternate-block rows instead of refusing the report. | Both scripts used `table[table["primary"]] if "primary" in table.columns else table`, despite their own prose saying only one confirmation-period primary row counts. | Evidence selection must fail closed when its schema changes; sensitivity rows are explicitly not independent findings. | Centralize `confirmation_primary_rows()`, require `period`, `direction`, `primary`, and `significant`, require boolean evidence flags, and return only confirmation-primary rows. Both runners validate before printing evidence. | The regression test proves sensitivity and discovery rows are excluded, missing required columns raise, and both runners pass the shared denominator. Replacing the helper with `return table.copy()` was detected. |
| RSREV-003 | P3 | Resolved | `a1d2587` | `signals/pead_persistence.py`, PEAD runner | The PEAD documentation omitted the long-only engine asymmetry. An `up` row tests continuation after beats, but a `dip` row goes long after misses and therefore tests reversal, not the stated downward-persistence/short hypothesis. | `backtest/engine.py` explicitly scores every signal as long; the new residual module documented the same asymmetry, while PEAD persistence did not. | A statistically significant row can still be misinterpreted if the modeled side is unclear. | Document the direction semantics in the signal and runner and require readers to inspect the long-leg edge sign; do not represent the `dip` leg as a modeled short. | Source review plus corrected module/runner documentation; no numerical behavior changed. |
| RSREV-004 | P3 | Resolved | `5a6ffd5` | action plan, milestone record, session handoff | PR #121 merged without updating the adopted sequencing ledger or canonical handoff, leaving new research code invisible to the next agent and making it look like the unreviewed GR-1D topic branch was still the tip of `main`. | Git shows PR #121 at `5a6ffd5`; neither the action plan nor the handoff named either residual commit or the merge. | Merged durable state must be recorded even when it does not change the authorized next milestone. | Record the candidate utilities as reviewed exploratory software, explicitly not a confirmed finding or sequence change, and replace the handoff with the exact merged/reviewed graph. | Final action-plan, feature-record, and handoff cross-check on the review branch. |

No issue remains open.

## Financial and timing review

The implementations are research scanners only. Residual regression moments
are shifted before rolling, appended future rows do not alter earlier
features, benchmark gaps produce missing residuals instead of borrowed market
returns, degenerate benchmark/residual volatility fails closed, and momentum
skips the most recent month. Volatility-scaled momentum enters at the next
open in the runner and uses only trailing closes. PEAD sorts earnings before
slicing, excludes future events, maps after-close/weekend announcements to
their effective reaction day through the existing helper, and states that
yfinance earnings and the current-ticker universe are not point-in-time.

These properties make the code suitable for exploratory tests, not evidence
that any edge exists. The universe has survivorship bias, yfinance data is
adjusted/as-recorded-now, earnings estimates can be restated, no historical
membership source is present, and the runners do not promote a finding or
authorize a proposal. The long-only engine means the loser/miss legs are
controls or opposite-side tests as documented. No registry, policy,
execution-kernel, broker, scheduler, evidence epoch, or live-authority state
changed.

## Verification and conclusion

The merge result was checked against `a1d2587` for all seven topic files and
is exact. Before correction, **137 focused tests passed**, confirming the
implemented causality and backtest contracts but not the cross-runner family
count. After correction, the signal, PEAD, backtest, multiplicity, and block
bootstrap suites passed **138 tests in 58.16 seconds**. The exact six-cell
reverse mutation and the fail-open evidence-selection reverse mutation were
both detected and restored. `compileall` and `git diff --check` were clean;
the complete isolated suite passed **2,485 tests, 1 skipped, 25 warnings in
512.22 seconds**.

Final disposition: **accepted after correction**. The implementation is an
honest **8/10 before review correction and 9.5/10 on the corrected tree**.
The signal formulas, timing discipline, adversarial synthetic fixtures, and
explicit non-point-in-time limitations are strong. The material miss was the
statistical family split: the fourth signal tightened one runner but not the
other, repeating a known false-positive class. The fail-open evidence fallback
was narrower but pointed in the same unsafe direction. This work does not
change the adopted roadmap: GR-1E assessment remains next, and these candidates
remain unpromoted exploratory research utilities.
