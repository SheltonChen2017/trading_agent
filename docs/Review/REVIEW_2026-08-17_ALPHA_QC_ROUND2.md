# Independent review — Alpha QC round 2 / Stage 1

Date: 2026-08-17
Reviewer: Codex
Implementation remote: `origin/user/claude/alpha-qc-round-20260816`
Prior reviewed head: `ad6475d552c5f9b4da338570cd52ea99c3b63524`
Exact last submitted Claude head: `a37e73b`
Full-history base: `006a9d5a887f6fc6da8a4978e1ac2680e941c783`
Review branch: `codex/review-alpha-qc-round2-20260817`
Disposition: **the complete research/QC chain is accepted only after
corrections `b143c60`, `855941a`, and `1e2b631`; no historical result is
usable and no QC run is cleared until Claude counter-reviews the final pushed
Codex head.**

Codex did not authenticate to QuantConnect, upload or compile code, launch or
read a cloud backtest, inspect broker state, or consume a research look. The
shared checkout remained on Claude's branch; all review work occurred in a
separate isolated worktree. At the owner's request,
the original Stage 1 review was subsequently expanded to every research/QC
commit and module created during the 2026-08-16/17 alpha work. The full-audit
addendum below supersedes narrower current-state claims later in this report.

## 0. Full-audit ordered commit dispositions

Every commit in literal history `006a9d5..a37e73b` is dispositioned. Non-alpha
commits are named rather than silently skipped.

| Commit | Disposition |
|---|---|
| `db0045a` | Historical declaration retained; its local data cannot provide confirmation evidence. |
| `3a506ae` | Accepted carried-forward non-alpha REBAL correction; outside research implementation scope. |
| `4de88d0` | **Rejected as evidence**; invalid local result removed after ledger/hash preservation. |
| `dae34d0` | Accepted carried-forward non-alpha review record; paths updated only. |
| `046afc3` | **Rejected as evidence**; invalid universe result/artifacts removed after hash preservation. |
| `f63fe2c` | Accepted carried-forward merge topology; no alpha conclusion added. |
| `3d58f6b` | Accepted only as historical merge topology; merged alpha result rejected. |
| `124192f` | Accepted but superseded by further local turnover/NAV/peer/regression corrections. |
| `f8dc843` | Accepted as partial historical review; updated paths, not current assurance. |
| `821d916` | Accepted as merge topology; it validates no result. |
| `fa5815d` | Method retained; old local executable still violated its peer/joint-regression rules and is corrected in `1e2b631`. |
| `dbadb12` | Accepted as merge topology; no result validated. |
| `361038e` | Accepted after correction; runner identity, bounded waits, and current API contracts required repair. |
| `d3211c9` | Retained as provenance-limited plumbing history, never alpha evidence. |
| `b9efc41` | Accepted after strict ordered-window validation. |
| `3a3132e` | Rejected as submitted; monthly normalization/timing/PIT/residual/basket/API paths corrected. |
| `e3e8a23` | Rejected as submitted; short/benchmark/analyzer session, stale-close, cost, completeness, and provenance paths corrected. |
| `f0cd4fc` | **Rejected as evidence**; reported pass invalid. |
| `6707a97` | Accepted after full packed output and strict parser correction. |
| `a83703e` | **Rejected as evidence**; no pass, null, MAX, quality, or benchmark conclusion survives. |
| `667cbf4` | Accepted after strict benchmark evidence identity/numeric validation. |
| `e8eb558` | Accepted but superseded; full audit found additional API, PIT, session, provenance, stall, and local-method defects. |
| `f4c81dd` | Accepted as historical invalidation record; active-artifact retention language superseded by owner cleanup. |
| `a795ea3` | Accepted as merge topology only. |
| `ad6475d` | Accepted after correction; permanent ledger/refusal direction right, slice formula wrong. |
| `8bf8a82` | Accepted but superseded by full API/PIT/performance/local-formula audit. |
| `e1aedc7` | Accepted and maintained; staged plan and permanent ledger updated here. |
| `56bc86d` | Accepted; exact-session refusal generalized across LEAN tree. |
| `175ab1e` | Accepted as superseded historical finding record. |
| `82ab65f` | Accepted as prior-cycle validation only, not current-tree validation. |
| `20d2cda` | Accepted as superseded handoff history. |
| `af045ee` | Accepted; candid round-1 re-derivation was honest but not exhaustive. |
| `dc63eec` | Rejected as submitted; Stage 1 timing/PIT factor/benchmark/analyzer corrected. |
| `d63bb86` | Reasoning partly useful, assurance superseded because copied machinery was not safe. |
| `a37e73b` | **Rejected and corrected.** Permanent ledger restored. Owner-authorized deletion applies only to invalid generated files after ledger/hash preservation; external QC project deletion cannot reset research looks. |

## 0a. Additional full-audit findings

These extend the Stage 1 ledger below. All are resolved; none authorizes a
result or a trade.

| ID | Severity | Status | Finding | Correction / verification |
|---|---|---|---|---|
| AQR2-005 | P1 | Resolved | LEAN files mixed legacy/PascalCase and current Python API members; one algorithm shadowed framework-owned `fundamentals`, making real QC execution unusable while local tests passed. | `855941a` standardizes all ten LEAN modules, renames the cache, and adds AST guards against legacy members and framework shadowing. |
| AQR2-006 | P1 | Resolved | Monthly factors were not fully point-in-time, peers could include self, exact gaps could look adjacent, and repeated factor rebuilding was impractically expensive. | PIT daily aggregates, historical membership, leave-one-out peers, exact-session refusal, and one-pass factor state. |
| AQR2-007 | P1 | Resolved | Old local turnover used current/future outcomes, wrong NAV, and target-to-target universe turnover. | `855941a` uses previous outcomes only, post-return NAV, fail-closed drift, and drift-aware universe turnover; tests pin 15% and no lookahead. |
| AQR2-008 | P2 | Resolved | Short results could use stale/duplicate/non-adjacent sessions; benchmarks could accept stale closes. | Exact close/volume sessions and strict stale/gap/duplicate refusal. |
| AQR2-009 | P2 | Resolved | Analyzers accepted incomplete/conflicting/malformed/non-finite/negative evidence and incomplete run identity. | Strict specs, finite domains, positive periods, exact project/compile/backtest/source identity, and same-date benchmarks. |
| AQR2-010 | P2 | Resolved | QC polling could wait forever when progress stayed `None`; source/compile identity was incomplete. | Bounded total/no-progress waits including permanent `None`, source SHA, compile IDs, and do-not-relaunch-blindly diagnostics. |
| AQR2-011 | P1 | Resolved | Local industry reversal included self and residual momentum used sequential regressions against Method V2. | `1e2b631` uses row-valid leave-one-out peers and one frozen joint intercept/market/industry fit ending before measurement; direct numeric tests pin both. |
| AQR2-012 | P2 | Resolved | Permanent ledger deletion and root-level invalid artifacts would erase or confuse research history; links assumed old layout. | Ledger restored/expanded, invalid files removed only after hashes, docs organized, links updated, plain-language glossary added. |
| AQR2-013 | P3 | Resolved | Full-suite validation reproduced the standing `TRADE1CR-002` test defect: synthetic strategy histories ended on the calendar day and therefore became future/stale data before a Monday market close. | Both test helpers now end on `expected_latest_completed_session()`; runtime freshness behavior is unchanged and the 31 affected strategy/path tests pass in the pinned environment. |

Full-audit severity summary including the four Stage 1 findings below:
**0 P0, 6 resolved P1, 6 resolved P2, 1 resolved P3, 0 open.**

Result disposition: five cloud runs and 80 repeated cells remain counted; the
conservative lifetime floor remains 428. Invalid generated Markdown/JSON/logs
were removed from active docs at owner direction, while
`docs/alpha-result.md` preserves every identity, hash, provenance gap, and
validity status. No Feature Milestone entry was added because no alpha result
is valid.

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

- combined research/QC/LEAN/document gate: **247 passed in 3.62 seconds**;
- local formula/turnover focused gate before the combined run: **129 passed**;
- completed-session/config-path regression group: **31 passed**;
- authoritative full suite in repository `.venv` (Python 3.13.14, Streamlit
  1.60.0): **4,189 passed / 0 failed / 25 known dependency warnings in
  687.51 seconds**;
- repository compilation including `research/`, 124-file Markdown relative-
  link check, remaining docs JSON parse, active-doc layout guard, and
  `git diff --check`: clean after final rerun;
- deliberate Stage 1 holding-period mutation: detected, then restored before
  final validation.

An earlier non-authoritative attempt used the system interpreter's Streamlit
1.52.2 instead of the repository-pinned 1.60.0. It correctly exposed one
moved-config path and the standing pre-market fixture defect, both corrected;
its UI-hook failures disappeared in the pinned environment and are not counted
as final-tree failures.

## 6. Scope and safety

This correction changes research measurement only. It changes no proposal,
risk, execution, broker, registry, mandate, policy, deployment, scheduler,
database or evidence-epoch behavior. It supplies no evidence of edge and no
trading authority. `paper-epoch-005` and the operational checkout remain
untouched.
