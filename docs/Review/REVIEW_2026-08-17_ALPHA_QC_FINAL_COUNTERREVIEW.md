# Final counter-review — Codex alpha/QC correction chain before the QC rerun

Date: 2026-08-17
Counter-reviewer: Claude (fresh session, independent of the 7m/7n cycle)
Requested snapshot: `origin/codex/review-alpha-qc-counterreview-20260817`
at head `5730f7b76500e8d8511aa258fb279e390aba2f0b`, base
`d8a32604d32e0d85fb9920b0839445eab13ad5f8`
Review branch: `user/claude/alpha-qc-full-counterreview-20260817`, created
from the exact object `5730f7b`
Disposition: **Accepted. All ten commits accepted; the PR #242 merge is
accepted as topology. Four new P3 findings (CCR3-A..D), all closed in this
review with mutation-verified tests or ledger clarification. No product
defect found; no historical result rehabilitated; the lifetime alpha-cell
floor remains 428 and the run ledger remains five.**

## 0. Snapshot deviation, recorded before anything else

The named remote branch no longer existed when this review began: the owner
had already merged it as **PR #242** (merge commit `f937bfb`, whose tree is
byte-identical to `5730f7b` — verified `git rev-parse f937bfb^{tree} ==
5730f7b^{tree}`, so the merge added no conflict-resolution change) and the
branch was deleted. The exact head survives as `refs/pull/242/head` and is an
ancestor of `origin/main`. The review therefore began from the exact
requested object, not a substitute; the only deviation is that the head is
now also reachable from `main`. No QuantConnect authentication, upload,
compile, backtest, result read, broker access, database mutation, scheduler
change, epoch action, or research look occurred during this review.

## 1. Commit dispositions

Every commit was reviewed individually, not as a combined diff. The seven
already-merged correction commits were re-reviewed rather than inherited.

| Commit | Disposition |
|---|---|
| `b143c60` | **Accepted.** The Stage 1 timing contract was traced in the final tree: features freeze at the prior close (`end_ago=1` at the `_form_and_bind` call site), entry binds at the first distinct session of the new month, cohorts settle at exactly 21 session gaps and overlap independently, and the PIT market factor is recorded prospectively per session from that day's known membership. Five fresh mutations against this surface (M6–M10 below) all reddened. |
| `fd007c8` | **Accepted.** The plan/ledger/action-plan additions match the code they describe; the `452 = 428 + 24` lifetime arithmetic is consistent with the frozen Stage 1 family and the permanent ledger. |
| `65e8bb0` | **Accepted.** The round-2 report's checkable claims reproduce: the 13-finding ledger is internally consistent, the 35-commit disposition table covers the literal range, and the focused-suite counts match what this review measured on the same tree. |
| `2e2a77e` | **Accepted.** The Stage 1 implementation-report addendum honestly reclassifies the "machinery is copied" defence as history rather than assurance, which the CR2-003 evidence (the copy's own turnover was untested) independently supports. |
| `855941a` | **Accepted.** Verified on the axes that matter: all ten LEAN modules parse to one current snake_case dialect with no framework-member shadowing (behavioural check plus the AST guards, which reddened under both a PascalCase call and a `self.fundamentals` assignment in the prior counter-review and under two fresh dialect mutations here); QC polling is bounded for stall, permanently-`None` progress, and — after CCR3-B — the outer deadline; the analyzers refuse missing identity, non-finite values, negative turnover, truncation, and duplicate/overlapping windows; the restored permanent ledger carries every removed artifact's identity and hash (all fourteen re-verified byte-exact under CCR3-D's convention). One guard-inventory gap (CCR3-C) and one untested timeout path (CCR3-B) are closed here as P3 hygiene over correct behaviour. |
| `1e2b631` | **Accepted.** The local joint intercept/market/leave-one-out-industry fit ends exactly where measurement begins, peers exclude the scored stock, and turnover drifts on previous-period outcomes only. Fresh mutations sliding the fit window into the measurement period, re-including the stock in its peer mean, and removing the LEAN fit's intercept all reddened (M11–M13). |
| `b4e9ee0` | **Accepted after documentation correction (CCR3-D).** The reorganization's deleted-artifact inventory matches the ledger's preserved identities exactly, and every one of the fourteen recorded SHA-256 values was reproduced from Git history — but only over CRLF-converted bytes, a convention the ledger did not state; a verifier hashing the bare blobs would wrongly conclude tampering. The ledger now records the convention. |
| `031b5a7` | **Accepted.** Tree-identical to Claude's submitted `ad3b3a8` (verified: empty `git diff`). All three CR2 closures were independently re-verified load-bearing: each reddened under its exact mutation (M1–M3) and under two fresh variants (M4–M5). |
| `46ebe04` | **Accepted.** The topology corrections match the actual remote state measured read-only in this review: `origin/main` moved past `d8a3260`, the round-2 branch is merged-and-deleted, and the integration branch carried the tests forward. |
| `5730f7b` | **Accepted.** Wording-only; it names `46ebe04` explicitly where the prior text said "the following documentation commit". |
| `f937bfb` (outside the stated range; exists on `main`) | **Accepted as merge topology.** Tree identical to its second parent; no conflict-resolution change; it validates no result. |

## 2. Verification method

Behavioural, not by reading. Sixteen mutations were applied to the exact
head in this checkout, the relevant suites run, and the tree restored and
`git status`-verified clean after each. Where a mutation reproduces one used
by the 7m counter-review, that is deliberate: the prompt requires the CR2
closures to be independently tested, and a closure only counts as verified
when its exact defect reddens it in a fresh session.

| # | Mutation | Target | Detected? |
|---|---|---|---|
| M1 | Stage 1 scores formed at the entry close (`end_ago=0`) | CR2-001 closure | yes (AST call-site pin) |
| M2 | Market recorder appends a fabricated `0.0` on a thin day | CR2-002 closure | yes (behavioural stub test) |
| M3 | Stage 1's own `_drift_turnover` loses drift (target-to-target) | CR2-003 closure | yes |
| M4 | Stage 1's `_drift_turnover` assumes `0.0` for a missing outcome (fresh) | AQR2-007 family | yes |
| M5 | Holding period 21 → 22 session gaps (fresh) | AQR2-001 | yes |
| M6 | `c.price` → `c.Price` in one screen | AQR2-005 | yes, but only via an incidental text assertion |
| M7 | `gross_profit.value` → `GrossProfit.Value` | AQR2-005 | yes (`Value` is listed) |
| M8 | `gross_profit` → `GrossProfit` alone (lone legacy leaf) | AQR2-005 | **NO — CCR3-C** |
| M9 | Outer poll deadline returns a fake result instead of raising | AQR2-010 | **NO — CCR3-B** |
| M10 | `LIFETIME_CELLS_BEFORE_STAGE` 428 → 24 (lifetime gate loosened ~19×) | AQR2-009 / look accounting | **NO — CCR3-A** |
| M11 | Local residual fit window slides one month into the measurement period | AQR2-011 | yes |
| M12 | Local leave-one-out peers include the scored stock | AQR2-011 | yes |
| M13 | LEAN joint residual fit loses its intercept (fresh axis) | AQR2-006/011 | yes |
| M14 | Re-apply M10 after the CCR3-A closure | closure proof | yes (2 tests) |
| M15 | Re-apply M9 after the CCR3-B closure | closure proof | yes |
| M16 | Re-apply M8, plus `Resolution.DAILY` → `Resolution.Daily`, after the CCR3-C closure | closure proof | yes (both) |

Beyond mutations, the review traced by hand: the Stage 1 leave-one-out
inclusion invariant (a stock outside a day's factor bucket forces refusal of
the whole score, never a wrong peer mean); the monthly battery's fit/measure
window arithmetic (252-session fit ending exactly at `t-21·months`,
measurement through `t-21`, skip of the latest 21); the benchmark's
stale-close refusal and the analyser's same-date enforcement of dropped
benchmark months; the cost convention (`series − turnover × 2 × bps/10⁴`,
consistent with one-way turnover and per-side costs across all three
analyzers); and the PR #242 merge-tree identity.

## 3. Issue ledger

All findings are P3 hygiene over correct product behaviour at the reviewed
head; none invalidates the audit chain or blocks the QC rerun. Resolved
findings remain here permanently. **0 P0, 0 P1, 0 P2, 4 closed P3, 0 open.**

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CCR3-A | P3 | Closed | `b143c60` | `scripts/analyse_qc_alpha_stage1.py` | The frozen multiplicity gates were unpinned constants: no test asserted `STAGE_FAMILY_CELLS = 24` or `LIFETIME_CELLS_BEFORE_STAGE = 428`, and no test drove the analyser end to end. A silent edit lowering the lifetime floor would loosen the lifetime Bonferroni gate without any red test — the same unpinned-frozen-contract shape as CR2-001..003, one file over. | Mutating 428 → 24 survived 184 research/QC/document tests. | The look-accounting floor is the research contract; the declared gate must be provably wired to the emitted report. | Constants pinned to the permanent ledger; an end-to-end `main()` test asserts the report carries the exact 24-cell and 452-cell gates and thresholds; a sibling test proves a benchmark missing an alpha date refuses. | Both tests red under M10 re-applied (M14), green restored. |
| CCR3-B | P3 | Closed | `855941a` | `scripts/run_quantconnect_smoke.py::_wait_for_backtest` | Both stall tests hold progress constant, so the OUTER `max_wait_seconds` deadline path was untested; a mutation returning a fake result at the deadline survived, and that dict would flow into the provenance summary as if the run completed. | M9 survived 116 tests. | "Times out safely" is a claim about the deadline branch, and only the stall branch was proven. | Behavioural test with progress advancing on every poll until the deadline; expects `QuantConnectError` "did not finish within … inspect". | Red under M9 re-applied (M15), green restored. |
| CCR3-C | P3 | Closed | `855941a` | `tests/test_lean_smoke_test.py::LEGACY_ATTRIBUTES` | The dialect guard's blocklist named chain roots and `Value` but not the leaf members these files actually access, nor legacy enum members. A lone `GrossProfit` leaf and `Resolution.Daily` both survived; `c.Price` was caught only by an unrelated text assertion. LEAN currently aliases legacy names, so this is dialect-consistency hygiene rather than a broken cloud run. | M8 survived 99 tests. | An incomplete blocklist is the CR2 lesson at the guard level: the inventory must cover what the files use. | Sixteen names added (`Price`, `AdjustedPrice`, `GrossProfit`, `TotalAssets`, `TotalDebt`, `NetIncome`, `FreeCashFlow`, `ROE`, `ROA`, `GrossMargin`, `MorningstarSectorCode`, `TotalEquityGrossMinorityInterest`, `Daily`, `Adjusted`, `Raw`, `Delisted`). | Red under M8 and the `Resolution.Daily` variant (M16), green restored; full guard suite green with no false positive. |
| CCR3-D | P3 | Closed | `b4e9ee0` | `docs/alpha-result.md` | Every ledger SHA-256 was computed over CRLF working-tree bytes (`core.autocrlf=true`), but the recovery instruction points at Git history, whose blobs store LF. A verifier hashing `git show b4e9ee0^:docs/<name>` gets a different digest for all fourteen artifacts and would wrongly conclude the ledger is corrupt or tampered. | All fourteen bare-blob hashes mismatch; all fourteen match after LF→CRLF conversion. | The permanent ledger's integrity claim must be reproducible by a reviewer who was not present, on any platform. | A hash-verification-convention note added to the ledger header; no hash, identity, status, or look count changed. | All fourteen artifacts re-verified byte-exact under the documented convention in this review. |

## 4. Observations, not findings

- The benchmark algorithms' `_drift_turnover` copies still differ textually
  from the battery copies (`outcomes[symbol]` vs `.get(symbol, 0.0)`); the
  missing-outcome guard makes the difference unreachable. Carried forward
  from the 7m counter-review; still worth unifying in a future pass.
- The short battery's `MAX_20` window silently skips a return whose
  denominator close is non-positive instead of refusing the symbol, unlike
  the monthly `_returns` positivity refusal. QC adjusted closes are positive
  in practice and the other reversal legs guard `then <= 0`, so this is a
  data-domain edge, recorded rather than churned.
- The short battery's drift turnover is measured at settlement (entry+5)
  while the next entry binds one session later, so one staging session of
  drift goes uncharged. It uses only past data — no lookahead — and the
  cadence matches the declared 5-session outcome contract.
- Stage 1 IC pairs drop a name whose settlement price is unavailable and
  disclose it through the per-row `n` column; basket rows refuse outright.

## 5. Validation on the exact final tree

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Baseline focused gate on the unmodified head `5730f7b`: **163 passed**
  (Stage 1, QC battery, local battery, LEAN safety, active documents) —
  matching the 7m counter-review's recorded count.
- Focused gate with the four closures and this report in place: **167
  passed** across the same five files (163 baseline + 4 new tests; CCR3-C is
  a guard-set extension, not a new test).
- Sixteen mutations above, each with a per-mutation suite run and a
  `git status`-clean restoration.
- Full suite on the final tree (all test and documentation content in
  place): **4,196 passed / 0 failed / 25 known dependency warnings in
  737.53s** — the 4,192 baseline plus the four closure tests.
- Repository-wide compilation including `research/`: clean.
- Markdown relative-link check over every tracked Markdown file: **126
  files, 0 broken links** (the count includes this report).
- Docs and mandate JSON parse: clean. `git diff --check`: clean.
  Staged-content and ordered-commit inspection performed before each commit.

## 6. Scope and safety

Test and documentation changes only: no algorithm, analyser, runner,
proposal, risk, execution, broker, registry, mandate, policy, scheduler,
database, or epoch behaviour changed. No QuantConnect access of any kind
occurred and no research look was consumed. `paper-epoch-005` remains
untouched at `752d3b7` under the owner's 60-day hold. No historical result
was rehabilitated; the lifetime alpha-cell exposure floor remains **428**
(452 after a complete Stage 1 family) and the run ledger remains five.

## 7. Gate status after this review

The counter-review gate for the next QuantConnect runs is satisfied for the
second time, now by a session independent of the 7m/7n cycle. The one open
decision before launching remains the owner's: whether **Stage 0** (finish
the frozen 180-cell battery) or **Stage 1** (REP-H52/REP-IDV plus matching
benchmarks) runs first. Every execution must be appended to
`docs/alpha-result.md` as R-005 or later with full project/compile/backtest/
source/log identity and before/after look counts.
