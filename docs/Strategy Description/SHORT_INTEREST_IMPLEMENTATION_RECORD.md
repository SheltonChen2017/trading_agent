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
| 2026-08-28 | Claude review | `a4f58e6` -> `d28fb3d` reviewed; corrections at `54c678c` (this record commit follows) | Independent review of the owner-authorized common-remediation synchronization and the shared portfolio-equity correction | Reviewed all 16 pushed commits individually. Verified the synchronization is faithful rather than accepting it: 11 of the 12 shared code commits are patch-identical to their merged `main` originals, and the single difference (`2e4748b` vs `8cab638`) is exactly the required removal of the Analyst-only `research/analyst_revisions_v2` licensed-surface entry. No Analyst or Insider content, no frozen shared file, and no Short Interest strategy code entered this lane. | Complete suite on the exact code tree `54c678c`: **5,225 passed, 3 skipped, 0 failed, 25 known dependency warnings in 2,310.10s (38m30s)**. The count reconciles arithmetically against the pre-correction run on this host (5,223 passed / 1 failed / 2 skipped at `d28fb3d`): the non-portable preview test moved from failed to skipped and the new parametrized guard contributed two passes, giving 5,228 collected in both runs. The 63-check active-document suite was rerun green against this record's final text, which is documentation-only and inert to every other test. Focused: 51 passed / 1 skipped in `test_ml_evidence_operations.py`; 72 passed across fault-matrix, proposals and data-integrity; 35 passed across the import-boundary and entry-point manifests. Two mutations run: removing the alias guard from both installers turned my new test red (2 failed) and restore returned it green; reverting the equity fix to per-position summing turned Codex's new test red, independently confirming their claim. compileall exit 0; `git diff --check` clean; 0 PowerShell parser errors across `scripts/`; blueprint SHA-256 re-verified as `2f7ccff9...45b14c`. No provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or order access; **0 research looks**. | Two P2 findings, both confirmed and corrected in `54c678c`: a non-portable installer-preview harness that failed the suite on the owner's documented Store-Python host, and a new interpreter-alias safety guard shipped with no behavioral coverage. No P0 or P1 found. Details in section 6. | Codex counter-reviews this Claude commit. Synchronization and this review are not acceptance of SI-0/SI-1, which remains unstarted and still blocked on the licensed historical/vintage short-interest source. |

## 6. Claude independent review - 2026-08-28 (common-remediation synchronization and portfolio-equity correction)

Reviewer: Claude, dedicated Short Interest lane session, isolated worktree
`C:\git\customizedAgent\trading_agent_short_interest`. Governing documents:
`CLAUDE.md`, `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, and
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`.

**Disposition: accepted after correction.** No P0 or P1 issue was found. Two P2
issues were confirmed and corrected on this lane branch. Acceptance of the
synchronized shared code as *this lane's* baseline does not start SI-0/SI-1.

### 6.1 Exact reviewed snapshot

| Item | Exact value |
|---|---|
| Lane branch | `codex/strategy-short-interest` |
| Lane head before the synchronization | `a4f58e6e0d0cf3d4ca08903e9184846259b17e24` |
| Reviewed remote head | `d28fb3d46bc2eae6427c00eeb8554e179b730bf8` |
| Ordered reviewed range | `a4f58e6..d28fb3d` (16 commits, no merge commit) |
| Ancestry | `a4f58e6` and `0a77b9c` are both ancestors of `d28fb3d`; clean fast-forward, no rebase or rewrite |
| Claude correction commit | `54c678cf3fdfb2a0eb38002817382d5ec5174237` |
| Shared source on `main` | `6770db3` (final patch), merged as PR #315 |

The remote head moved from `0a77b9c` to `d28fb3d` during the review because
Codex pushed the portfolio-equity correction and its records. The additional
three commits were fetched and reviewed in the same pass rather than left for a
later cycle.

### 6.2 Commit dispositions

Every commit received its own disposition; no combined diff was substituted.

| # | Commit | Scope | Disposition |
|---|---|---|---|
| 1 | `6b6f355` | Fix boolean coercion in trading policy limits | accepted |
| 2 | `d741e36` | Add cross-process execution dispatch fence | accepted |
| 3 | `734e0dd` | Bind execution authorization to broker context | accepted |
| 4 | `a41aa7b` | Make broker anomaly containment atomic | accepted |
| 5 | `ba60c58` | Fence and drain emergency order cancellation | accepted |
| 6 | `6089944` | Harden dispatch fence across process forks | accepted |
| 7 | `d759062` | Bind broker access to coherent account snapshots | accepted |
| 8 | `298228a` | Close emergency cancel-all indexing races | accepted |
| 9 | `ea97639` | Harden shared trading safety boundaries | **accepted after correction** (`SI-CR1-001`, `SI-CR1-002`) |
| 10 | `2e4748b` | Register shared research input boundaries | accepted; correctly Analyst-stripped |
| 11 | `9a6fa49` | Reconcile three-strategy review workflow | accepted |
| 12 | `81eede4` | Close shared remediation regressions | accepted |
| 13 | `0a77b9c` | Record shared remediation synchronization | accepted |
| 14 | `b4bb0d0` | Fix portfolio equity display aggregation | accepted |
| 15 | `72d6894` | Record portfolio rounding sync | accepted |
| 16 | `d28fb3d` | Record lane full validation | accepted |

### 6.3 P0-P3 issue ledger

Resolved items are retained. There are no P0 or P1 findings.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SI-CR1-001 | P2 | Closed | `ea97639` | `tests/test_ml_evidence_operations.py`, installer preview harness | The preview harness drove both installers with `sys.executable`. On a Microsoft Store Python that is a zero-byte execution alias, which the same commit taught the installers to refuse, so a correct safety refusal surfaced as a suite failure on the owner's documented Windows host. A red suite that is really an environment artifact hides genuine regressions and makes the lane's validation claim unreproducible. | Complete suite on the exact tree `0a77b9c` in this worktree: 5,222 passed, **1 failed**, 2 skipped, against the lane record's claimed 5,223 passed / 0 failed. Isolated rerun showed the installer throwing its zero-byte-reparse-point refusal; `sys.executable` measured at 0 bytes. | The suite must be reproducible on the platform the project actually targets; the defect is in the harness, not in the installer, so the guard must stay and the harness must stop feeding it an input the product legitimately rejects. | Added `_skip_unless_interpreter_can_drive_a_task()` and called it from `_run_installer_preview()`, so the preview skips with an explicit reason when the running interpreter cannot serve as a task interpreter. | The preview test now skips instead of failing on this host; `test_ml_evidence_operations.py` is green at 51 passed / 1 skipped. |
| SI-CR1-002 | P2 | Closed | `ea97639` | `scripts/install_windows_operational_tasks.ps1:69-78`, `scripts/install_windows_ml_shadow_tasks.ps1:78-79` | The new interpreter-alias refusal, which exists to stop a scheduled task from being registered against an interpreter that can never launch, had no behavioral test in either installer. The only related assertion elsewhere checks that a *different* script's source text contains the string "zero-byte". An untested guard can be removed or inverted without any test turning red. | Searched the whole test tree: no test invoked either installer with a zero-byte or reparse-point interpreter; `tests/test_setup_operational_host.py:113` is a source-text assertion about `setup_operational_host`. | A safety check that silently prevents a task registering against an unlaunchable interpreter is exactly the fail-closed behavior that must be pinned by a red/green test, per the dangerous-direction requirement. | Added `test_installer_refuses_zero_byte_interpreter`, parametrized over both installers, building its own zero-byte stand-in so it runs on every Windows host regardless of how Python was installed. It asserts non-zero exit, the exact refusal message, and that no task preview was emitted. | Mutation: replacing `if ($isReparse -or $item.Length -eq 0)` with `if ($false)` in both installers turned the new test red (2 failed); textual restore returned it green (2 passed), with the worktree verified clean afterwards. |

### 6.4 Independent reproduction rather than accepted claims

- **Synchronization fidelity.** Compared stable patch IDs commit by commit
  against the merged `main` originals: `6b6f355`/`1986305`, `d741e36`/`96c3637`,
  `734e0dd`/`4b670f9`, `a41aa7b`/`a8e26d4`, `ba60c58`/`1f0cffa`,
  `6089944`/`f87732f`, `d759062`/`729d7ad`, `298228a`/`0bd8a45`,
  `ea97639`/`bf82838`, `9a6fa49`/`c7f34dd` and `81eede4`/`6770db3` are all
  identical; `81eede4` carries the recorded patch ID
  `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`. Only `2e4748b` differs from
  `8cab638`, and the entire difference is the omission of the Analyst-only
  `research/analyst_revisions_v2` licensed-research surface and its assertion.
- **Lane isolation.** No file matching Analyst, Insider or ACER changed in the
  range; `docs/SESSION_HANDOFF.md`, `docs/ACTION_PLAN_2026-08-20.md`,
  `requirements.txt`, `config.py` and CI configuration are untouched; the only
  `short_interest` path changed is this record.
- **Risk-reduction asymmetry, the invariant most at risk in this change set.**
  New exposure runs inside `execution_dispatch_fence` in
  `assistant/execution_service.py:737`, so a fence timeout raises and refuses to
  execute (fails closed). Emergency cancel-all uses
  `_enter_best_effort_emergency_fence` in `assistant/order_reconciler.py:71`,
  which returns the failure instead of blocking, and
  `_record_cancel_all_incomplete` still writes a durable critical alert when the
  fence was not held. A safeguard therefore cannot obstruct risk reduction.
- **Portfolio-equity correction.** Reverse-mutated `b4bb0d0` back to summing
  per-position rounded values; Codex's new test failed as they claimed, so the
  regression test is genuine and the fix aggregates exact `Decimal` values
  before a single display rounding.
- **Storage migrations.** No `DROP TABLE`, `DROP COLUMN` or table-rename
  appears in `assistant/storage.py`; 47 idempotent
  `CREATE TABLE IF NOT EXISTS`/`ADD COLUMN` sites, with tests covering fresh
  databases, pre-migration databases, read-only verification, missing databases,
  and detection of dropped tables, weakened indexes, removed foreign keys and
  removed uniqueness.
- **Reservation release.** `AssistantStore.release_execution_reservation`
  returns `rowcount == 1`, so a repeat release reports `False` rather than
  releasing twice, and its docstring forbids use on ambiguous outcomes.
- **Broker completeness.** `_get_orders_for_client` raises
  `BrokerPreflightError` at exactly the 500-order maximum rather than certifying
  a possibly truncated book, and `list_account_activities` bounds its page loop,
  requires an advancing cursor, and refuses rows without an id.
- **Boundaries.** `ml` is imported by no module under `assistant/`, `execution/`
  or `risk/`; the `ml/` changes in `ea97639` add no action-shaped field and only
  move calendar logic into the shared `data/exchange_calendar.py`;
  `resolve_target_session` refuses a horizon the calendar cannot cover instead
  of silently returning a nearer session.
- **No weakened tests in `81eede4`.** Across its 24 test files the patch removes
  31 assertions and adds 77. The removals inspected are relocations or genuine
  contract changes with stronger replacements, for example the non-finite
  equity warning, where one substring check became an exact prefix assertion
  plus a content assertion.
- **Blueprint integrity.** The lane PDF still hashes to
  `2f7ccff9bcd35810b11350314fd6e47c7c92e24ac35a866addb82ce66645b14c`, matching
  both this record and the active-document guard.

### 6.5 Review scope and what was not exhaustively audited

Stated so the counter-review can target the gaps rather than assume coverage.

- The shared series is ~27,000 changed lines. It was authored, audited and
  merged on `codex/full-review-p1-remediation-20260826` and is patch-identical
  to `main` here, so this lane review verified synchronization fidelity,
  lane-scope compliance, governance correctness, validation reproduction, and
  targeted audits of the highest-risk invariants listed in 6.4. It is **not** a
  line-by-line re-audit of every hunk.
- Planned deep dives into the dispatch fence's stale-fence takeover and fork
  handling, reconciler replacement-chain and stranded-claim recovery, the
  coherent-snapshot construction, and the storage/risk-gate precision changes
  were **spot-checked only**; the assisting review agents were terminated by
  session usage limits before completing those passes.
- The Windows scheduled-task installers were validated by parser and by the new
  refusal test. No task was registered, and no scheduler, broker, operator
  database or provider was contacted.

### 6.6 Remaining gates and next authorized step

1. Codex counter-reviews `54c678c` and this record commit, per the restored
   three-step lane loop.
2. Synchronization plus this review is explicitly **not** acceptance for
   SI-0/SI-1. That milestone remains unstarted.
3. The licensed historical/vintage short-interest source, the FINRA publication
   calendar archive, and the QuantConnect entitlement audit all remain open
   owner decisions. Nothing in this review authorizes provider access, a
   research look, a QuantConnect job, or any broker or deployment action.
