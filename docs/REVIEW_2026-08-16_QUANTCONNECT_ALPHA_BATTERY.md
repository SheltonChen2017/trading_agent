# Independent review — QuantConnect smoke and alpha battery

Date: 2026-08-16
Reviewer: Codex
Implementation remote: `origin/user/claude/quantconnect-smoke-20260816`
Merge base: `dbadb1293dff617a70ce3a36da49326564c5157b`
Monitored pre-push head: `b9efc41e331676356b60a9bd4a566e2c964fcef1`
Exact pushed review head: `667cbf409aae669b6d514e295d4d29f905a9e505`
Review branch: `codex/review-quantconnect-alpha-20260816`
Product/test correction: `e8eb558e79bbdc468f531e9b92de4c175d7a3957`

## Outcome

**Implementation accepted after correction; submitted cloud results rejected.**
The remote branch successfully established useful research plumbing and a
disciplined pre-registration, but the result-producing algorithms did not run
the experiment that document froze. Every monthly, short-horizon, turnover,
cost, benchmark, and significance conclusion committed at the submitted head
is invalid. The historical documents and JSON remain in Git with explicit
invalidation metadata; no statistic was recalculated locally and this review
did not access QuantConnect.

Correction `e8eb558` repairs the local source and analyser. It does **not**
create corrected market evidence. Claude's counter-review must first verify
the changes, then run the corrected exact source on QuantConnect and record
the exact backtest IDs and log hashes. Until that happens, the honest result
is “no valid QuantConnect alpha result.” No feature milestone completed and
no entry belongs in `docs/FEATURE_MILESTONE_RECORD.md`.

## Commit-by-commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `361038e` | **Accepted after correction** | The results-only client and inert smoke foundation are useful. `e8eb558` adds missing endpoint-contract tests, positive project-id validation, accurate live-call commentary, safe update failure semantics, and real/reversed date refusal. |
| `d3211c9` | **Accepted after documentation correction** | The inert probes are sensible qualitative diagnostics. Their committed report lacks exact cloud project/backtest IDs and log hashes, so it is retained with a provenance limit rather than treated as independently reproducible evidence. |
| `b9efc41` | **Accepted after correction** | Declared run-window retargeting is the right direction. `e8eb558` also refuses impossible dates and reversed windows. |
| `3a3132e` | **Accepted after correction** | Pre-registration preceded the result, but the monthly implementation violated raw/adjusted return separation, next-session entry, delisting, residual regression, fixed-at-entry baskets, construction turnover, and hypothesis-count contracts. Corrected in `e8eb558`; the original results remain void. |
| `e3e8a23` | **Accepted after correction** | The short battery, benchmark, and local analyser are useful architecture. Material timing, delisting, turnover, result-completeness, and benchmark defects are corrected in `e8eb558`. |
| `f0cd4fc` | **Rejected as evidence** | The “one specification clears” result was produced by the defective measurement path and has no committed cloud run identity. The document and JSON are banner-invalidated. |
| `6707a97` | **Accepted after correction** | Log-cap detection was valuable, but dropping long-only 20%, averaging one turnover, and silently deduplicating split logs changed the frozen experiment. `e8eb558` preserves all constructions per date in one full-period packed series and makes parsing fail closed. |
| `a83703e` | **Rejected as evidence** | “Significant and worthless,” the short-horizon passes, MAX interpretation, and benchmark verdict all depend on invalid timing/returns/costs and mismatched comparison windows. The documents are audit history only. |
| `667cbf4` | **Accepted after correction** | Adding the previously untracked benchmark analyser improves reproducibility. `e8eb558` adds turnover-aware costs, exact row validation, aggregate series preservation, input-log hashes, and mandatory backtest identity. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| QCAR-001 | P2 | Closed | `3a3132e`, `e3e8a23`, `f0cd4fc`, `a83703e` | `research/lean/alpha_battery_monthly.py`, `alpha_battery_short.py`, `universe_benchmark.py` | Raw trade bars fed momentum and forward-return arithmetic, so splits became fictitious returns and contaminated every result series. | All three result algorithms set `DataNormalizationMode.Raw` and stored those bars in return windows. | Method V2 requires raw units for the price/cap screen, not split-affected investment returns. | Trade-bar subscriptions are adjusted; raw coarse/fine `Price` remains the screen input. | Source guards plus focused suite. |
| QCAR-002 | P2 | Closed | `3a3132e`, `e3e8a23`, `a83703e` | monthly/short `OnData` and score formation | The promised close `t+1` entry was absent. Short holding days advanced on every `OnData` call, producing about 1,250 alleged non-overlapping five-session observations in only ~3,274 sessions. | Entry was recorded from the scoring bar; `days_held += 1` had no distinct-session guard. The impossible sample count corroborates the source defect. | This changes every outcome, IC, p-value, return, and turnover. | Scores stage at `t`; entry binds on the next distinct daily bar. Short holds exactly five later sessions. | Timing source contracts; corrected count must be confirmed by cloud rerun. |
| QCAR-003 | P2 | Closed | `3a3132e`, `e3e8a23` | settlement and universe exits | Result algorithms neither retained measured names nor used terminal delisting values. They also re-ranked baskets at settlement using future outcome availability. | No battery/benchmark `data.Delistings` path existed; baskets were built only after outcomes were known. | This reintroduces the exact survivorship failure QuantConnect was chosen to fix. | Measured symbols are retained while needed, terminal delisting prices enter outcomes, and baskets are frozen at entry. | Source guards and focused tests; cloud delisting behavior remains counter-review work. |
| QCAR-004 | P2 | Closed | `3a3132e` | monthly residual momentum | “Joint” residual momentum ran sequential univariate regressions, applied the stock market beta to peers, and cumulated the estimation window instead of the final measurement window. Industry means also included the subject stock. | Direct source trace; a synthetic two-factor series reproduces the correct expected residual total. | The implementation contradicted Method V2 §1.7 and invalidated three dependent specs. | One joint intercept/market/leave-one-out-industry OLS is fit before the measurement window and only measurement residuals are summed. | Behavioral regression test. |
| QCAR-005 | P2 | Closed | `3a3132e`, `e3e8a23`, `6707a97` | portfolio turnover and cost analysis | One long-short turnover series was reused for both long-only constructions; first entry was doubled; drift normalization differed from Method V2; compact output averaged turnover before nonlinear metrics; missing turnover became `1.0`. | Source trace and four-name 40/20/20/20 drift reproduction. | Every net return, Sharpe, CAGR, and drawdown claim depended on the wrong cost path. | Three construction-specific per-date turnovers, exact drift formula, fail-closed missing inputs, and benchmark turnover/costs. | Drift and construction-specific regression tests. |
| QCAR-006 | P2 | Closed | `3a3132e`, `6707a97`, `a83703e` | pre-registration and analyser constants/output | The 135 family counted three portfolios but omitted the IC hypothesis used for the headline gate. Short logs also discarded the declared 20% construction and reduced IC precision after seeing log limits. | Analyser computed four p-values per spec/universe while `DECLARED_LOOKS = 135`. | The significance threshold understated the tested family and the output no longer matched the frozen constructions. | Family is 180; all three constructions and monthly-equivalent precision are retained in a full-period packed row. | Count/gate and binary round-trip tests. |
| QCAR-007 | P2 | Closed | `e3e8a23`, `6707a97` | `scripts/analyse_qc_alpha_battery.py` | Split-log merging silently kept the first duplicate and did not verify spec inventories, per-row completeness, scale, overlap, or declared periods. | `drop_duplicates(..., keep="first")` could hide conflicting or truncated evidence. | A plausible partial report is worse than a visible refusal. | Exact schemas, frozen inventories, complete rows, periods, chronological non-overlap, finite turnovers, hashes, and IDs are mandatory. | Parser refusal and overlap regressions. |
| QCAR-008 | P2 | Closed | `e3e8a23`, `f0cd4fc`, `a83703e`, `667cbf4` | benchmark algorithm/analyser/results | The benchmark used raw same-close returns, no terminal delisting arithmetic, no own turnover costs, 155 months versus the battery's 142, yet supported categorical “not one construction beats” claims. | Result document admits the window mismatch; analyser discarded the aggregate date series. | Performance comparisons must share dates, timing, and costs. | Corrected monthly benchmark uses next-session entry, adjusted/delisting returns and per-date turnover; analyser preserves aggregate series and cost scenarios. Historical comparison is invalid. | Focused benchmark parser test; exact comparison awaits rerun. |
| QCAR-009 | P2 | Closed | `f0cd4fc`, `a83703e` | results Markdown/JSON | Result prose promoted passes, nulls, survivorship explanations, and a benchmark verdict despite known Method V2 violations. | The results themselves admit delisting arithmetic was absent while calling the data honest and the conclusions established. | Invalid market evidence must not remain easy to mistake for current evidence. | Markdown and JSON carry explicit invalidation status and correction identity; historical values remain unchanged. | JSON parse and active-document checks. |
| QCAR-010 | P2 | Closed for future runs; historical limitation retained | `d3211c9`, `f0cd4fc`, `a83703e`, `667cbf4` | smoke/results evidence and analysers | Git does not contain the exact project/backtest IDs, input log hashes, upload source identities, or analysis commands that produced the committed JSON. | No identifiers appear in the smoke/result reports or result JSON. | A cloud result without run identity cannot be independently retrieved or tied to the reviewed source. | Future analysers require per-log QuantConnect backtest IDs and record SHA-256 hashes. Historical smoke/result artifacts are marked provenance-limited/invalid. | CLI validation plus parser tests. |
| QCAR-011 | P3 | Closed | `361038e`, `b9efc41` | client, smoke runner, tests | Six new client helpers had no direct payload tests; non-positive project IDs passed; the runner treated every update error as “file absent”; date rewriting accepted impossible/reversed windows; client commentary still said no live call occurred. | Complete commit diff and missing test coverage. | These defects obscure wrong remote mutations and leave maintenance claims stale. | Exact payload tests, positive IDs, single-meaning update failure, real date/order validation, accurate comment. | 126 focused tests. |

Priority summary: **0 P0, 0 P1, 10 closed P2, 1 closed P3, 0 open code
findings.** Corrected cloud evidence is still externally pending and is not
counted as an open code finding.

## Corrected rerun contract for Claude's counter-review

1. Counter-review `e8eb558` and reproduce every QCAR finding locally before
   using cloud resources.
2. Run each corrected algorithm from the exact final Codex remote head. Do
   not reuse the submitted compiled snapshots or JSON.
3. Monthly battery: one full 2012-01-01 through 2024-12-31 run for each of
   A/B/C. Short battery: also one full-period run per universe. Its binary
   output exists specifically to avoid state-breaking date splits.
4. Corrected monthly benchmark: one full-period run per universe. It is a
   valid comparison only after aligning the preserved aggregate series to
   the alpha dates and applying the same cost scenario. It is not a
   cadence-matched benchmark for short-horizon claims; do not revive those
   claims without a separately frozen matching benchmark.
5. Pass every input log to the corrected analyser with the exact
   QuantConnect backtest ID. Preserve analyser JSON, log SHA-256, exact
   command, project/backtest identity, source head, universe, and window.
6. Confirm the short sample count is consistent with non-overlapping
   score/next-session-entry/five-session-hold cycles; confirm every log's
   complete frozen spec inventory and `orders placed: 0`.
7. Recompute the 180-hypothesis gate and report cumulative research-look
   accounting separately. Do not call this an independent pre-registered
   discovery: it is a post-result repair and replication.
8. Replace neither historical Markdown nor JSON. Create newly dated
   corrected artifacts and explicitly compare them with the invalidated
   submission.

## Validation

- Focused QuantConnect client/LEAN/analyser suite: **126 passed**.
- Active-document consistency suite: **30 passed**.
- Full repository suite: **4,118 passed / 0 failed / 25 known dependency
  warnings in 771.31 seconds** (Python 3.13.14, Windows).
- Repository-wide Python compilation, all three edited JSON parses, and
  `git diff --check`: **passed**.
- Final clean-branch, ordered-commit, and remote-head verification occurs
  immediately before/after the one authorized push and is reported to the
  owner; no intermediate push is permitted.

No QuantConnect API call, authentication, upload, compile, cloud backtest,
broker access, order, deployment, operational database mutation, scheduled
task change, or epoch change occurred during this review.
