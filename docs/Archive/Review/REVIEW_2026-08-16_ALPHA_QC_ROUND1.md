# Independent review — staged alpha QC round 1

Review date: 2026-08-16

Reviewer: Codex

Implementation remote: `origin/user/claude/alpha-qc-round-20260816`

Base: `a795ea322de8a50830abc680fd82d49967c5ddd6`

Exact pushed head: `ad6475d552c5f9b4da338570cd52ea99c3b63524`

Ordered range: `a795ea3..ad6475d` (one commit)

Review branch: `codex/review-alpha-qc-round1-20260816`

No QuantConnect API, compile, backtest, broker, order, database, scheduler, or
operational-state access occurred. The shared Claude checkout was not switched
or edited; review and corrections used an isolated worktree.

## Outcome

**Accepted after correction.** Claude correctly preserved all five cloud
executions, the completeness guard correctly refused partial monthly output,
and the impossible peer-length equality was a real defect. The submitted
slice-only correction was not sufficient: it made residual scores run, but
the helper labeled the skipped latest month as the 6-1/12-1 measurement
window. Product correction `8bf8a82` implements the actual formation windows
with a fixed prior 252-session joint factor fit and replaces the source-text
guard with behavioral tests. Follow-up correction `56bc86d` also binds every
deque price to the exact exchange session so a temporary universe exit,
missing bar, or duplicate slice cannot become a fictitious daily return.

None of the committed cloud artifacts is accepted as usable alpha evidence.
They remain audit inputs with explicit refusal, unanalysed, unreviewed-code,
and provenance-incomplete states. No saved output was parsed to calculate a
new statistic during this review.

## Commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `ad6475d` | **Accepted after product/test and documentation correction** | The refusal diagnosis, raw artifact preservation, and long-lived ledger are valuable. The residual fix measured the wrong month, its source-string test could not detect that behavioral error, the ledger undercounted every new real-market run, and several status/provenance/decoder claims contradicted committed evidence. |

## Issue ledger

| ID | Priority | Status | Location | Finding and impact | Evidence | Correction | Verification |
|---|---|---|---|---|---|---|---|
| AQR1-001 | P2 | Closed in `8bf8a82` | `research/lean/alpha_battery_monthly.py` | The slice fix passed `21*months` returns to a helper that treated only the final 21 as the measurement window. `RESIDUAL_MOM_6_1` and `_12_1` therefore summed the month their names require skipping, not the 5/11-month formation interval. Every residual and multi-alpha result would answer the wrong hypothesis. | Direct source trace against raw momentum's `t-21/t-21m` formula, the original runner's explicit `t-21*months..t-21` docstring, and a synthetic path with a huge skipped-month shock. | Retain 520 closes; require a fixed 252-return pre-formation joint market/leave-one-out-industry fit; measure 105/231 formation returns; exclude the final 21. | Two behavioral horizon tests and short/misaligned-history refusal test; focused suite green. |
| AQR1-002 | P2 | Closed in documentation | `docs/Archive/Research/alpha-result.md` | R-001/R-002 said runs did not count until a statistic was computed. Method V2 section 1.10 says every real-market run counts. This understated repeated-look exposure and could make later significance gates too permissive. | Five exact committed cloud logs; two short universes expose 40 cells and the accidental monthly A run exposes 40. | Record five run-level looks, 80 emitted cells, and a conservative 428-cell lifetime exposure floor; keep run and cell ledgers separate. | Ledger and implementation-plan consistency review. |
| AQR1-003 | P2 | Closed in documentation | `docs/Archive/Research/alpha-result.md`, committed logs, `scripts/analyse_qc_alpha_battery.py` | The ledger said no base64 decoder existed, named the monthly-B artifact incorrectly, omitted full hashes/statuses, and implied run identity was closed despite absent compile/project IDs. That could cause duplicate decoder work and overstate reproducibility. | The analyser already parses `B64BLOCK`; its round-trip test passes. Actual artifacts/hashes and embedded backtest IDs were independently matched; project/compile IDs remain absent for four entries. | Correct decoder statement, artifact names/line counts/hashes, status vocabulary, exact backtest fields, and `PROVENANCE_INCOMPLETE` labels. | Source/log/hash cross-check without analysing market statistics. |
| AQR1-004 | P3 | Closed in `8bf8a82` | `tests/test_qc_alpha_battery.py` | The new test asserted source substrings and arithmetic inequality only. It passed while the implementation measured the wrong period. | Reverse reasoning: any implementation containing the two strings passed regardless of output. | Replace it with behavioral 6-1/12-1 tests and fail-closed history/alignment coverage. | The synthetic skipped-month shock would change the old implementation by roughly 21.0 but must contribute zero. |
| AQR1-005 | P2 | Closed in `56bc86d` | monthly `OnData`, `_price`, `_returns`, and factor-universe construction | Price deques contained values but no dates. A security leaving and later re-entering the universe, missing one bar, or receiving a second same-session slice could make non-adjacent closes look like consecutive daily observations and misalign its stock return from market/industry factors. | Direct state trace: the old code appended before its same-session guard, retained deques after removal, and indexed all names by relative deque offset. | Store matching per-symbol sessions and one distinct global session calendar; append only once per date; return a tail only when every date exactly matches; build the residual factor universe from fully aligned histories. | Behavioral exact/missing/duplicate-session test; focused suite green. |

Priority summary: **0 P0, 0 P1, 4 closed P2, 1 closed P3, 0 open
findings.** The corrected monthly algorithm must be counter-reviewed and rerun;
that external evidence task is not an open code finding.

## Research accounting and evidence disposition

- R-001 monthly B: counted run, zero emitted cells, refused; compile ID absent.
- R-002 short A/B: two counted runs and 40 emitted cells; raw logs retained,
  intentionally unanalysed in this review; project/compile IDs absent.
- R-003 monthly A: counted run and 40 emitted cells; ran unreviewed code and
  is unusable; project/compile IDs absent.
- R-004 benchmark B: counted benchmark run, not an alpha cell; unanalysed;
  project/compile IDs absent.
- R-000 historical battery: remains invalidated and numerically unchanged.

The five exact log SHA-256 values and backtest IDs are recorded in
`docs/Archive/Research/alpha-result.md`. They partially improve QCAR-010 provenance but do not
close it because compile/source-upload identity is incomplete.

## Alpha program created in this review

`docs/Archive/Plans/Alpha_Test_Implementation_Plan.md` freezes the subsequent sequence and
separates incompatible cadences:

1. finish the corrected 180-cell QC battery;
2. replicate 52-week-high proximity and the low-idiosyncratic-volatility proxy;
3. run point-in-time PEAD only if announcement and pre-release consensus fields
   pass a strict feasibility gate;
4. test one frozen hierarchical sector-relative momentum score; and
5. optionally test one cross-sectional overnight-persistence score.

It defines exact formulas, universes, timing, costs, outcomes, look counts,
identifiers/hashes, refusal paths, independent-review gates, and the boundary
between QuantConnect history and later Alpaca Paper forward/execution testing.

## Validation

Final corrected tree, Python 3.13.14 on Windows:

- focused QuantConnect battery suite: **13 passed in 2.48 seconds**;
- active-document consistency suite: **30 passed in 0.57 seconds**;
- full repository suite: **4,122 passed, 0 failed, 25 known dependency
  warnings in 795.85 seconds**;
- repository compilation including `research/`: clean;
- `git diff --check`: clean.

One pre-final full-suite attempt stopped at the active-document topology guard
because the handoff said only `origin/main` rather than the required parseable
`main and origin/main` declaration. The handoff was corrected, the focused
document suite passed, and the complete suite above was rerun from the final
tree. This was a documentation-format failure, not a product-test failure.

## Required counter-review and rerun

Claude must counter-review the final pushed Codex head, especially AQR1-001's
252 + formation + 21-session slicing, AQR1-005's exact-session binding, and
the look-accounting correction. Only
then may Claude rerun Stage 0 in QC. All A/B/C monthly, short, and matching
benchmark runs require exact project, compile, backtest, source and artifact
identity. The pre-existing logs must not be overwritten. The next Claude push
must contain the appended ledger entries and the next stage's code before
Codex reviews it.
