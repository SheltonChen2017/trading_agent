# Independent review — Alpha QC round 2 / Stage 1

Date: 2026-08-17  
Reviewer: Codex  
Implementation remote: `origin/user/claude/alpha-qc-round-20260816`  
Prior reviewed head: `ad6475d552c5f9b4da338570cd52ea99c3b63524`  
Exact pushed review head: `dc63eecc9160071ef1590650085d2afe48e42c45`  
Merge-base: `ad6475d552c5f9b4da338570cd52ea99c3b63524`  
Review branch: `codex/review-alpha-qc-round2-20260817`  
Disposition: **Stage 1 accepted only after correction; no QC run is cleared
until Claude counter-reviews the final pushed Codex head.**

Codex did not authenticate to QuantConnect, upload or compile code, launch or
read a cloud backtest, inspect broker state, or consume a research look. The
shared checkout remained on Claude's branch and exact head `dc63eec`; all
review work occurred in a separate isolated worktree.

## 1. Ordered commit dispositions

The remote range from the monitor baseline includes six previously published
Codex commits, Claude's counter-review, and Claude's Stage 1 implementation.
The first six are explicitly dispositioned as carried-forward reviewed
history; this report does not mislabel them as a new independent review.

| Commit | Disposition |
|---|---|
| `8bf8a82` | **Accepted, carried-forward round-1 correction.** Correct residual-momentum formation window; already independently counter-reviewed by Claude in `af045ee`. |
| `e1aedc7` | **Accepted, carried-forward round-1 record.** Created the staged plan and corrected result accounting; already part of the published round-1 review. |
| `56bc86d` | **Accepted, carried-forward round-1 correction.** Refuses misaligned price sessions; already independently counter-reviewed by Claude. |
| `175ab1e` | **Accepted, carried-forward round-1 record.** Records the session-alignment finding without changing product behavior. |
| `82ab65f` | **Accepted, carried-forward round-1 record.** Records the exact final validation from that completed cycle. |
| `20d2cda` | **Accepted, carried-forward round-1 handoff.** Canonical state for the prior cycle; superseded for current state by this review's handoff update. |
| `af045ee` | **Accepted.** Claude independently re-derived all five round-1 findings, candidly documented its own failed residual-momentum fix and inadequate test, and reported no unsupported rehabilitation of prior results. No correction required. |
| `dc63eec` | **Accepted after product/test and documentation correction.** The two pure score formulas were largely correct, but the end-to-end algorithm did not implement the frozen month-end/21-session experiment, reconstructed the historical market factor from future score-date membership, lacked the matching benchmark/analyser path, and did not test those contracts. Corrected in `b143c60`. |

## 2. P0–P3 issue ledger

Resolved findings remain in this table permanently. There are no open findings.

| ID | Severity | Status | Finding and evidence | Correction and verification |
|---|---|---|---|---|
| AQR2-001 | P1 | **Resolved** | The frozen plan says score at month-end close, enter the next distinct close, and hold exactly 21 sessions. Submitted `OnData` called `_form_scores()` on the first selected session of a month, bound entry on the following session, and `_bind_staged_entry()` settled the old cohort only when the next monthly entry arrived. Calendar months contain variable numbers of exchange sessions, so every feature cutoff and outcome could answer a different experiment. | `b143c60` detects the first distinct session of a new month, freezes features at the immediately preceding close, enters at the current close, supports overlapping cohorts, and exits each at exactly 21 session gaps. A deliberate 20-session mutation makes the new behavioral test fail. |
| AQR2-002 | P1 | **Resolved** | REP-IDV's submitted `_index_returns(names, count)` applied the score-date survivor set backward to all 111 historical factor days. It also emitted `0.0` when a factor day had no usable names. That is neither point-in-time membership nor a valid refusal and can change regression residuals and ranks. | The corrected algorithm records each day's equal-weight return from the universe membership known that day, binds it to the exact exchange session, and refuses the whole score date if any of the 90+21 factor observations is missing or misaligned. Tests cover a numeric factor series with one missing session. |
| AQR2-003 | P2 | **Resolved** | Stage 1's definition of done requires a cadence-matched benchmark and controlled analysis of all 24 cells. The push contained only the alpha algorithm; the existing benchmark uses next-month settlement, and the existing analyser rejects the two Stage 1 spec IDs and applies the 180-cell battery gate. A cloud run would therefore have no valid comparison or result path. | Added `alpha_stage1_benchmark.py` with the same month-end/next-close/exact-21 cadence and terminal outcomes. Added `analyse_qc_alpha_stage1.py`, which accepts only the two frozen specs, requires project/compile/backtest/source-hash identity for alpha and benchmark runs, requires every alpha date in the same-universe benchmark, and reports the 24-cell stage and 452-cell lifetime gates. The shared battery parser now accepts an explicit frozen spec set without weakening its default inventory. |
| AQR2-004 | P2 | **Resolved** | Submitted tests exercised the pure formulas but not feature cutoff, entry, exit, market-factor membership/alignment, benchmark availability, or analysis provenance. Its formation-month test added the same constant to every day, then claimed the shock “must register”; sample standard deviation correctly removes that constant, so the assertion could not demonstrate the stated behavior. | Added behavioral timing, exact-hold, missing-factor, Stage 1 parser, benchmark and run-identity tests; expanded the directory-wide LEAN safety tests to cover both new result algorithms. The misleading statement is no longer relied upon as evidence of timing or residual sensitivity. |

Severity summary: **0 P0, 2 resolved P1, 2 resolved P2, 0 P3, 0 open.**

## 3. Formula and evidence disposition

- REP-H52's pure score uses 252 aligned adjusted closes and includes the score
  close in the trailing peak, matching `close_t / max(close[t-251:t])`.
- REP-IDV fits intercept and beta on 90 returns ending before its 21-return
  formation window, freezes those coefficients, and uses negative sample
  standard deviation of the 21 residuals. It remains a market-model proxy,
  not a Fama–French replication.
- Rankings freeze top 10%, top 20%, and top-minus-bottom decile baskets at
  entry. Each construction retains its own drift-aware turnover and terminal
  delisting outcome.
- Universe screens remain the preregistered A/B/C screens; raw coarse/fine
  values determine eligibility while adjusted trade bars determine returns.
- No favorable, unfavorable, refused, or unavailable Stage 1 market result
  exists yet. The lifetime alpha-cell floor remains 428 until a reviewed run
  emits cells. A full Stage 1 family would move that gate to 452 cells.

## 4. Required counter-review and QC rerun

Claude must counter-review the exact final pushed Codex head, especially:

1. month-transition scoring with `end_ago=1` and exact 21-session cohort exit;
2. point-in-time daily market-factor recording and missing-session refusal;
3. turnover over the actual interval between monthly entries, kept separate
   from the fixed 21-session outcome cohort;
4. terminal delisting handling in alpha and benchmark cohorts;
5. strict Stage 1 parser identity and same-date benchmark gates.

Only after that counter-review may Claude run each alpha universe and its
matching benchmark. Every execution must be appended to `docs/alpha-result.md`
with project, compile, backtest, source SHA-256, raw-log SHA-256, review head,
counter-review disposition, and before/after look counts. Any earlier run is
`PENDING_REVIEW`, still counted, and cannot be reused.

## 5. Validation

Validation is recorded on the exact final local tree before the single
authorized push. No test result in this section is a QuantConnect result.

- focused Stage 1/QC/LEAN safety suite: **74 passed**;
- deliberate holding-period mutation: **detected** (1 expected failure), then
  restored before all final tests;
- full suite, compilation, document checks, diff/status and shared-checkout
  identity: recorded in the final documentation/handoff commit after rerun.

## 6. Scope and safety

This correction changes research measurement only. It changes no proposal,
risk, execution, broker, registry, mandate, policy, deployment, scheduler,
database or evidence-epoch behavior. It supplies no evidence of edge and no
trading authority. `paper-epoch-005` and the operational checkout remain
untouched.
