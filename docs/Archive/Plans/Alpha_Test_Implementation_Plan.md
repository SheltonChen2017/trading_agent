# QuantConnect alpha test implementation plan

Status: **CLOSED — historical contract, retained as the record of how the
staged alpha program was run and how it ended.** Stage 0 completed across nine
runs and Stage 1 completed the same week; both are **NULL on every beta-free
cell** (ledger entries `A-001` and `A-002`, 2026-08-18). No IC or long-short
cell cleared its gate, and the long-only cells that did clear a gross-vs-zero
test were carrying market beta the benchmark itself clears. The
cross-sectional alpha program on this universe is closed and is not
launchable: reopening would require a new universe or data source, a fresh
preregistration, and a new owner decision.

The reviewed Stage 0 and Stage 1 QuantConnect runs are **VALID but null**:
their statistics are usable evidence that the frozen tests did not establish
a beta-free edge. That is different from the older legacy runs and artifacts
whose individual ledger entries remain invalid, refused, unanalysed, pending
review, or provenance-incomplete. `docs/research/alpha-result.md` is the permanent,
append-only authority for each run's status, including every refusal. The
workflow, evidence rules, and stage definitions below stayed in force through
the closure and are preserved unchanged; their sequencing statements are
spent. `docs/ACTION_PLAN_2026-08-20.md` decides what happens next.

Historical detail retained: the owner chose Stage 0 first; runs R-005/R-006
both refused with zero cells and exposed a monthly factor-timing defect;
Claude's first fix required a further point-in-time boundary correction on
`codex/review-qc-stage0-run-20260817`; reruns resumed at R-007 without
overwriting either refusal.

Prepared: 2026-08-16

This plan governs historical alpha replication in QuantConnect. It does not
authorize a trade, a registry promotion, or an Alpaca order. QuantConnect is
the point-in-time historical-research lane. Alpaca Paper is reserved for a
later forward/execution test after a hypothesis survives this plan.

## 1. Non-negotiable workflow

For every stage:

1. Claude implements locally without launching a QuantConnect run, commits,
   and pushes the exact stage to
   `origin/user/claude/alpha-qc-round-20260816`.
2. Codex reviews only that pushed remote head in an isolated worktree, gives
   every commit an explicit disposition, corrects confirmed defects, runs
   local validation, updates this plan and the durable records, and publishes
   one `codex/` review branch with one final push.
3. Claude counter-reviews that exact Codex head. Only then may Claude compile
   and run the reviewed algorithm in QuantConnect.
4. Claude appends the run to `docs/research/alpha-result.md`, including failures and
   refusals, before implementing the next stage. Existing entries are never
   overwritten.

No agent may use an unreviewed cloud run to debug an algorithm. A run launched
accidentally still consumes a research look and remains in the ledger. Codex
does not access QuantConnect in its review lane.

## 2. Evidence and result contract

Every cloud execution must record all of the following or be classified
`PROVENANCE_INCOMPLETE` and barred from conclusions:

- stage and frozen specification ID;
- exact Git source commit and SHA-256 of every uploaded source file;
- QuantConnect organization, project ID/name, compile ID, backtest ID/name,
  engine version when exposed, and UTC launch/completion times;
- requested and actual data dates, resolution, normalization mode, security
  type/venue filters, universe definition, membership cadence, and point-in-
  time fields used;
- benchmark, entry/exit timestamps, holding period, portfolio construction,
  turnover definition, and 0/5/10/25-bps-per-side cost scenarios;
- complete raw log path and SHA-256, declared row/date/spec counts, parser
  version, parser command, and result artifact SHA-256;
- the cumulative run-level and hypothesis-cell look counts before and after
  the run; and
- implementation-review branch/head and counter-review disposition.

The result schema must preserve date-level observations. Primary statistics
are date-level Spearman IC plus gross/net return for long-only top 10%,
long-only top 20%, and top-minus-bottom decile. Pooled row significance is
forbidden. Significance uses the existing reviewed stationary bootstrap with
20,000 draws. Report both the stage-family Bonferroni gate and the stricter
lifetime-family gate; a result cannot be promoted by selecting the friendlier
one.

The algorithm or parser must refuse, rather than approximate, when any frozen
specification is missing, output is truncated, factor/universe history is
misaligned, a point-in-time field is unavailable, dates overlap, an identifier
is absent, values are non-finite, or the significance gate is unreachable.
Refusal is a valid result and still a counted real-market run.

## 3. Look accounting at plan creation

Two ledgers are maintained because a cloud execution and a tested statistical
cell are not the same unit:

| Ledger | Count before the next run | Basis |
|---|---:|---|
| Historical declared alpha cells | 348 | local battery 105 + universe battery 63 + corrected QC family 180; the historical 135 declaration was audited to 180 because IC was omitted |
| Additional emitted cells in the five 2026-08-16 corrected-code cloud executions | 80 | short A and B: 5 specs x 4 outcomes x 2 universes = 40; accidental monthly A: 10 x 4 = 40 |
| Lifetime alpha-cell exposure floor | 428 | 348 + 80; this is a conservative floor, not permission to ignore older exploratory variants |
| Additional real-market run-level looks | 5 | monthly B refusal, short A/B, accidental monthly A, and benchmark B all count under Method V2 section 1.10 |

The benchmark execution is a counted research run but is not added to the
alpha-cell denominator. The refused monthly B execution emitted zero cells,
but it still counts at run level. No statistic needs to be calculated for a
look to have been consumed; seeing or saving the market output is enough.

Prospective cells below are frozen now. If all stages run as written, they add
72 cells: 24 replication cells, 24 PEAD cells, 12 hierarchical-momentum cells,
and 12 optional overnight cells. The existing corrected battery's 180 cells
are repeated looks, not a newly invented family.

## 4. Prior-result inventory

| Candidate | Existing project status | Treatment here |
|---|---|---|
| Original dip/up z-score | rejected | no rerun; broad daily-trigger family is low priority and prior nulls are not data-quality-limited enough to justify another look |
| Raw 12-1 momentum | rejected locally; current QC battery evidence invalid/pending | finish the already-frozen corrected QC battery only; no extra variants |
| Residual momentum | rejected locally; QC implementation still required correction | included only in the corrected frozen battery, using a 252-session pre-formation joint market/industry fit and true 6-1/12-1 windows |
| Reversal, industry reversal, abnormal-volume reversal, MAX | historical QC evidence invalid | included only in the corrected frozen battery |
| Gross profitability and quality composites | local data unavailable; QC historical evidence invalid | included only in the corrected frozen battery because QC supplies point-in-time fundamentals |
| 52-week-high proximity | rejected on the current survivor-selected local universe | one method replication on QC's point-in-time A/B/C universes |
| Low idiosyncratic volatility proxy | rejected locally against a single market proxy | one method replication with the exact frozen proxy formula on QC A/B/C; do not relabel it as the Fama-French construction |
| PEAD / earnings-surprise persistence | rejected or unconfirmed on non-point-in-time/current-listing data | dedicated point-in-time feasibility gate, then one frozen event study if QC exposes the required fields |
| Relative/breakout/fundamental/analyst signals | rejected | no immediate rerun; no reason to spend another look before higher-information candidates |
| Macro signals | rejected; one apparent anomaly was a bootstrap artifact | no QC rerun in this program |
| Overnight-gap reversal | rejected | not repeated; the optional candidate below is a different cross-sectional persistence hypothesis and must be labeled new |
| Trend/vol rotations, wide band, defensive carry | strategy/risk-allocation findings, not stock-selection alpha | outside this alpha program |

## 5. Stage 0 — repair and finish the frozen QC battery

This is continuation of the existing 180-cell preregistration, not a new
hypothesis. The source remains split by cadence:

- monthly: ten momentum/quality specifications;
- short horizon: five five-session specifications; and
- monthly equal-weight universe benchmark.

Before any rerun, the residual scores must implement exactly:

1. 252 daily returns for one joint intercept + market + leave-one-out industry
   OLS, ending before the formation period begins;
2. formation residuals from `t-126` through `t-21` for 6-1 and from `t-252`
   through `t-21` for 12-1; and
3. no contribution from the skipped most-recent 21 sessions.

The 2026-08-17 post-counter-review verification also freezes four contracts
that the prior review missed:

1. the five-session short portfolio is liquidated when its outcome settles
   and the next portfolio enters one session later, so turnover is exit plus
   re-entry, not a direct old-target-to-new-target rebalance;
2. the non-overlapping short observations use 42 periods/year (252 divided by
   the six-session score/entry/hold cycle), while monthly observations use 12;
3. MAX(20) requires exactly 21 finite, positive closes and never drops an
   invalid denominator to manufacture a shorter window; and
4. a missing/invalid Morningstar industry code remains missing and cannot be
   pooled with other unknowns as a synthetic peer industry.

These corrections change potential Stage 0 costs, net returns, annualized
statistics, and eligible industry/MAX observations. They do not change any
historical ledger count because no cloud run was made during review.

Run A_large, B_core, and C_broad exactly once per monthly, short, and matching
benchmark algorithm from the PR #244 reviewed source. Never split a stateful
calendar. Compare only identical realized dates. Completion requires all nine exact run
identities, complete artifacts, reviewed parsing, 180-cell and lifetime gates,
and an updated ledger. No historical result is rehabilitated.

## 6. Stage 1 — two already-tested method replications (24 cells)

Implementation status (2026-08-17): Claude's exact pushed Stage 1 head
`dc63eec` was independently reviewed before any QC run. The submitted code
formed on the first session of each month and settled at the next month's
entry, so neither the frozen month-end feature cutoff nor the exact 21-session
outcome existed. It also reconstructed all 111 historical market-factor
returns from the current score-date universe and substituted zero on an empty
factor day. Review correction `b143c60` now scores the immediately preceding
month-end at the next distinct close, settles overlapping cohorts after
exactly 21 distinct sessions, records the equal-weight market return from the
membership actually known on each historical date, and refuses a missing
factor date. A cadence-matched benchmark algorithm and strict Stage 1 analyser
were added. Full audit correction `855941a` then standardized the entire LEAN
tree on current Python API names, removed framework-member shadowing, hardened
exact-session/provenance/refusal contracts, and bounded cloud polling. **No
Stage 1 QC run was authorized until Claude counter-reviewed the final pushed
Codex head; that review gate and Codex's follow-up verification are now
complete.**

The invalid generated result Markdown, JSON, and raw logs were removed from
the active docs tree at the owner's direction. This does not reset look counts:
`docs/research/alpha-result.md` permanently preserves every run, status, ID and hash.

Implement these in one monthly algorithm because their score and holding
cadences match. Each specification has 3 universes x 4 tested outcomes = 12
cells; total stage family = 24.

### REP-H52 — 52-week-high proximity

- Classification: method replication of the frozen local signal on a better
  universe, not an exact data replication.
- Score at month-end close `t`: adjusted `close_t / max(adjusted close[t-251:t])`.
- Require 252 valid sessions; no shorter window or imputation.
- Rank descending; top 10%, top 20%, and top-minus-bottom 10%.
- Enter at the next distinct session's close; hold 21 sessions to keep the
  common monthly outcome contract. This deliberately differs from the local
  signal's 126-day hold and therefore answers a narrower one-month portfolio
  question; the difference must be stated, not called exact replication.

### REP-IDV — low idiosyncratic-volatility proxy

- Classification: method replication of the project's rejected market-model
  proxy, not the academic Fama-French three-factor specification.
- Estimate intercept and market beta on 90 prior daily returns, ending before
  the 21-session volatility formation month.
- Residual for each formation day is stock return minus that frozen intercept
  and beta times the point-in-time equal-weight QC market return.
- Score is negative sample standard deviation of the 21 residuals.
- Rank/entry/holding/constructions match REP-H52.
- Do not add industry, size, or factor variants after seeing the result.

Use separate cadence-matched equal-weight benchmarks. Definition of done:
three complete universe runs, one matching benchmark per universe, all 24
cells analyzed, and result-ledger entries whether favorable or not.

The reviewed execution contract uses `research/lean/alpha_stage1_benchmark.py`
for those three benchmark series and `scripts/analyse_qc_alpha_stage1.py` for
analysis. The analyser requires project, compile, backtest and uploaded-source
SHA-256 identity for both alpha and benchmark runs; accepts only `REP_H52` and
`REP_IDV`; requires every alpha date to exist in its same-universe benchmark;
and reports both the 24-cell stage gate and the 452-cell lifetime gate
(`428 + 24`).

## 7. Stage 2 — point-in-time PEAD (24 cells)

This is a new QC event-study implementation of a previously tested idea. It
is not an exact replication of the local yfinance result.

### Mandatory feasibility probe

The probe is inert only if it cannot emit returns or alpha statistics. It must
establish that QC exposes, point in time:

- the announcement timestamp and whether it was before open/after close;
- actual EPS as first reported;
- a consensus EPS value timestamped before the announcement; and
- delisted securities and usable next-session prices.

If any field is missing, ambiguous, revised-only, or cannot be tied to an
as-of timestamp, mark Stage 2 `UNAVAILABLE`. Do not substitute fiscal filing
dates, current consensus, price reaction, or a manually selected ticker list.

### Frozen event specifications

- `PEAD_SURPRISE`: `100 * (actual_eps - consensus_eps) /
  max(abs(consensus_eps), 0.01)`, winsorized cross-sectionally at 1%/99% on
  each event date. The denominator floor is fixed now; report how often it
  binds.
- `PEAD_STREAK4`: same surprise, but eligible only when the current event
  completes at least four same-sign non-zero surprises among the last eight
  causally available events.
- Effective signal date: same session for a pre-open release, otherwise next
  exchange session. Score only after the public timestamp.
- Entry: next session's open after the effective signal date. Exit: close 40
  distinct sessions later, the frozen middle of the prior 20-60-day range.
- Construction: long top surprise quintile, long top decile, and top-minus-
  bottom quintile, reconstituted by event cohort; date-level IC is the fourth
  outcome. Overlapping cohorts must be represented as actual concurrent
  weights and charged realized turnover.
- Family: 2 specs x 3 universes x 4 outcomes (IC plus the three portfolio
  constructions) = 24 primary cells. The 40-session horizon is the only
  primary horizon; 20/60-day values may not be added after seeing the result.

Event and monthly algorithms must never be combined. The benchmark is a
cadence-matched event-date universe return, not a monthly buy-and-hold series.

## 8. Stage 3 — hierarchical sector-relative momentum (12 cells)

This is a new hypothesis. One score only; no weight search.

- Raw name momentum: adjusted `close[t-21] / close[t-252] - 1`.
- Within each Morningstar industry with at least five eligible names, compute
  a winsorized z-score of name momentum.
- For each industry, compute its equal-weight mean raw momentum. Within its
  sector, z-score industry means only when at least three industries exist.
- For each sector, compute the equal-weight mean of its industry means and
  z-score sectors across the market only when at least five sectors exist.
- Final score: equal one-third weight on name-within-industry, industry-
  within-sector, and sector-within-market z-scores. If any leg is unavailable,
  the name is unavailable; weights are not redistributed.
- Rebalance monthly, enter next distinct close, hold 21 sessions, and use the
  standard four outcomes over A/B/C. Family = 1 x 3 x 4 = 12 cells.

Point-in-time industry/sector codes are mandatory. Classification changes are
applied only when QC makes them available; current labels must not be copied
backward.

## 9. Stage 4 — optional cross-sectional overnight persistence (12 cells)

Run only if Stages 0-3 are complete and the owner explicitly keeps it in
scope. This is new and distinct from the rejected single-gap reversal signal.

- Daily overnight return: adjusted `open_t / close_{t-1} - 1` on consecutive
  exchange sessions.
- Score at month-end close: mean of the last 20 valid overnight returns; all
  20 are required.
- Rank descending; standard top 10%, top 20%, and top-minus-bottom 10%.
- Enter next session's open and exit at the open 21 sessions later. The
  outcome is open-to-open total return; also preserve future overnight-only
  return as descriptive, never a second primary outcome.
- A/B/C and standard IC produce 12 primary cells. No reversal leg, 5/10/60-
  day horizon, volatility scaling, or subperiod gate may be added after seeing
  the result.

This algorithm remains separate because open-to-open timing is incompatible
with monthly close-to-close and event-time PEAD accounting.

## 10. Promotion and Alpaca Paper

An alpha can leave QuantConnect only if it:

- clears both its frozen stage-family gate and lifetime-family gate;
- has the expected direction in A, B, and C without one universe carrying the
  entire result;
- remains economically positive after 10 bps per side and has plausible
  turnover/capacity for this account;
- survives the declared subperiod/regime descriptions without a fatal sign
  reversal;
- has complete provenance and independent review; and
- has no unresolved point-in-time, delisting, timing, or classification caveat
  capable of changing the conclusion.

Passing those gates means only `CANDIDATE_FOR_PAPER_FORWARD_TEST`. Alpaca Paper
then tests signal availability, order construction, slippage assumptions,
fractional/whole-share behavior, reconciliation, and live-forward drift. It
does not re-optimize the alpha and is not evidence of profit until enough
independent forward observations exist. No QuantConnect or paper result grants
live-trading authority.
