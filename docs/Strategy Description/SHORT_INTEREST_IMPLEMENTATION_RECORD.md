# Short Interest ETF Strategy — implementation and session record

Status: **PLANNED; NO INGEST, SIGNAL, OUTCOME TEST, ETF PORTFOLIO, OR QC
ALGORITHM HAS BEEN IMPLEMENTED.**

Branch: `codex/strategy-short-interest`

Governing owner source: `SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf`, 47
pages, 262,483 bytes, SHA-256
`2f7ccff9bcd35810b11350314fd6e47c7c92e24ac35a866addb82ce66645b14c`.

Codex is the primary implementer. Claude is the independent reviewer. Both
agents work serially on this same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

## 1. Canonical V1 contract

- The input is official-style twice-monthly **short interest snapshots**, not
  daily short-sale volume. Daily short volume is never an acceptable proxy.
- Each observation needs current and previous short shares, settlement date,
  public release timestamp, stable security identity, and the volume basis for
  days-to-cover.
- The canonical stock signal is the robust within-sector z-score of the change
  in short-interest ratio. Use point-in-time float only if audited; otherwise
  point-in-time shares outstanding is the canonical denominator.
- `S0` level is a baseline; `S1` delta is canonical; `S2` historical surprise,
  `S3` delta plus days-to-cover, and `S4` residual are separate preregistered
  extensions. Short covering and squeeze risk remain separate constructs.
- Seed the top/bottom 10% of stock scores and use a PIT reverse ETF index.
  Eligible ETFs are US long equity, >=252 sessions old, price >=$5, median
  dollar volume >=$5M, holdings mapping >=80%, and signal coverage >=50%.
- The primary ETF score is the coverage-adjusted holdings-weighted stock
  score. Breadth, counts, concentration, and effective count are reported
  separately.
- Primary monetization is long low-pressure/covering ETFs and underweight or
  avoid high-pressure ETFs. A long-short portfolio is diagnostic. Inverse ETF
  use requires a negative absolute OOS result and a new owner-approved 1x
  implementation milestone.
- Rebalance only after public release, at the next open, and hold until the
  next release; 20 trading days is the fixed-horizon diagnostic. Use 10 bps as
  primary cost with 0/5/20 bps sensitivity. No leverage in canonical V1.

## 2. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| SI-0 | Freeze source, release calendar, revisions, identifiers, denominator, score family, horizons, costs, and look budget. | Complete preregistration; no outcomes. |
| SI-1 | Ingest licensed/official-style snapshots and FINRA release metadata into immutable vintage storage. | Exact settlement/publication separation, revision lineage, duplicate/refusal tests. |
| SI-2 | Resolve PIT security identity, eligibility, shares/float, sector, and ADV. | Ticker reuse, delisting, denominator vintage, and stale-volume mutations fail. |
| SI-3 | Implement `S0`/canonical `S1` plus separately gated extensions. | Golden equations; no daily-short-volume or outcome dependency. |
| SI-4 | Build PIT ETF reverse index, eligibility, coverage, and aggregation. | >=80% mapping, >=50% signal coverage, stale holdings and concentration tests. |
| SI-5 | Run stock-level event study before industry/ETF topology. | Permanent look logged; pressure and covering hypotheses kept separate. |
| SI-6 | Walk-forward ETF research and avoidance/underweight tests. | OOS robustness, costs, capacity, turnover, overlap, and null rule. |
| SI-7 | Implement QC algorithm from immutable precomputed/custom signals. | Deterministic parity and release/scheduling/failure tests; research-only. |
| SI-8 | Final holdout and promotion dossier. | Owner approval required before paper deployment. |

## 3. First implementation scope

The first Codex session should implement **SI-0/SI-1 source contracts and
fixtures only**:

1. pin the snapshot, settlement, publication, revision, security, and volume
   schemas;
2. encode release-time availability and next-open cohorting;
3. separate short-interest snapshots from daily short-volume data at the type
   and import boundary;
4. add dangerous-direction tests for settlement-date trading, missing prior
   snapshots, zero/negative denominators, ticker joins, revision overwrite,
   and short-volume substitution; and
5. update this record before the first push.

Do not download licensed history, join outcomes, construct ETF portfolios,
launch QC, or add inverse/leverage logic in this milestone.

## 4. Required data and unresolved gates

- FINRA publishes official US equity short-interest data and the twice-monthly
  schedule. Its online/API surface is rolling and revisions expose the latest
  value; canonical research needs an immutable historical/vintage route and
  publication calendar.
- Acquire Intrinio Short Interest or an equivalent licensed history with
  settlement date, current/previous short positions, days-to-cover/ADV,
  stable identifiers, corrections, and sufficient delisted-name coverage.
- A source field alone may not establish public availability. Archive the
  corresponding official FINRA publication schedule and derive next-open
  availability conservatively.
- QC prices, security master, fundamentals/shares, sector classification, and
  PIT ETF holdings entitlements/timing remain to be audited.
- Securities-lending data such as borrow cost, utilization, or availability
  (for example ORTEX) is optional V2 research, not a V1 dependency.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | Source reviewed and canonical short-interest contract recorded; no code. | PDF text and all 47 rendered pages inspected; no outcome access; 0 looks. | Historical/vintage short interest is the only clearly missing paid canonical input. | Claude reviews baseline; implementation waits for owner instruction. |
| 2026-08-27 | Codex implementation | `a4f58e6` -> `81eede4` (code snapshot; this lane-record commit follows) | Owner-authorized one-time common remediation synchronization | Synchronized the bounded shared-remediation series through `9a6fa49`, then identical final shared patch `81eede4` (source `6770db3`, stable patch ID `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`). The range contains no Analyst-only commit or file and no Short Interest strategy implementation. | Exact lane tree: 5,223 passed, 2 skipped, 25 dependency-deprecation warnings in 37m54s; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean; worktree clean. No short-interest/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or live scheduler access; **0 research looks**. | Independent final audit found no remaining P0-P3 issue in the synchronized shared diff. Synchronization is not acceptance; SI-0/SI-1 has not started. | Push this exact lane-recorded snapshot; Claude reviews every pushed commit on this lane, then Codex counter-reviews every Claude commit before SI-0/SI-1 can begin. |
| 2026-08-27 | Codex implementation | `0a77b9c` -> `b4bb0d0` (code snapshot; this lane-record commit follows) | Owner-authorized shared portfolio-equity correction | Cherry-picked source fix `1ed0602` into `assistant/portfolio_snapshot.py` and `tests/test_assistant_risk_copilot.py`. The builder now aggregates exact Decimal cash and position values before rounding the single total-equity display, preventing legitimate fractional-share portfolios from failing the strict display/exact integrity check. The validator, policy limits, broker contracts, strategy code, and research gates were not weakened or changed. | Focused portfolio/risk/coherent-snapshot suite: 112 passed, 0 failed, 1 dependency warning in 3.27s; compileall exit 0; `git diff --check` clean. Source correction previously passed the complete 5,442-test suite and a reverse mutation that reproduced display `100.01` versus exact `100`. No short-interest/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | `SYS-FU-P1-006` reproduced: per-position display rounding accumulated into a competing equity total and prevented UI load. Corrected without adding tolerance; pending Claude review and Codex counter-review. SI-0/SI-1 remains unstarted. | Validate and push the exact recorded lane snapshot. Claude then reviews both new commits on this lane before SI-0/SI-1 or any later milestone. |
| 2026-08-27 | Codex validation | `72d6894` -> `72d6894` (exact isolated tested snapshot; this validation-record commit follows) | Portfolio-equity correction final validation | Revalidated the complete Short Interest lane after its code and required lane-record commits in a detached isolated worktree pinned to `72d6894`; no product file changed during the run. | Complete exact-tree suite: **5,224 passed, 2 skipped, 0 failed, 25 dependency warnings in 1,744.53s (29m04s)**. The earlier focused 112-test suite, 63-test active-document suite, compileall, and diff checks were also green. Fixture-only; no short-interest/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. A separate run invalidated by a concurrent main-checkout branch switch is intentionally excluded. | No new P0-P3 finding. `SYS-FU-P1-006` remains implemented but unaccepted pending the required review chain. | Commit this validation record and push the complete three-commit lane range; Claude reviews every new commit before SI-0/SI-1 or any later milestone. |
