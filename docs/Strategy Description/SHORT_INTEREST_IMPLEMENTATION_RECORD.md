# Short Interest ETF Strategy — implementation and session record

Status: **CLAUDE REVIEW ROUND ACCEPTED AFTER CODEX CORRECTIONS AT `48fa344`
AND `6ef0ee9`; LANE SI-2A OFFLINE PIT DATA-READINESS TRANCHE IMPLEMENTED AT
`de468f7`, PENDING CLAUDE REVIEW. FULL LICENSED SI-1/FULL SI-2, SIGNAL,
OUTCOME TEST, ETF PORTFOLIO, AND QC ALGORITHM/JOB REMAIN UNIMPLEMENTED.**

Branch: `codex/strategy-short-interest`

Governing owner source: `SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf`, 47
pages, 262,483 bytes, SHA-256
`2f7ccff9bcd35810b11350314fd6e47c7c92e24ac35a866addb82ce66645b14c`.

Codex is the primary implementer. Claude is the independent reviewer. Both
agents work serially on this same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

Owner direction, 2026-08-29: this lane is used only for QuantConnect testing
of the Short Interest strategy. Future code and documentation in this lane
must remain Short Interest/QC-specific; Trading App and Streamlit work are out
of scope. This direction does not itself authorize an external QuantConnect
upload or job run, licensed/provider access, outcome access, deployment, or
trading.

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
| 2026-08-28 | Codex counter-review | `da798f0` -> `60d181a` (correction; this record commit follows) | Counter-review of Claude commits `54c678c` and `da798f0` | Dispositioned both Claude commits, corrected the installer-test coverage regression, and reconciled the review record's scope, arithmetic, shared-file, metadata, and next-step claims in section 7. The earlier Claude row is retained verbatim as historical evidence; section 7 explicitly supersedes its inaccurate clauses. | Pre-correction: the two zero-byte refusal cases passed while the eight-task parity test skipped on the documented Store-Python host. Corrected focused run: **5 passed** (one parity plus four zero-byte/reparse cases). Reverse mutation to the Store alias failed the parity test as intended: **1 failed in 3.44s**; restore returned all five focused cases green. `git diff --check` clean. Python 3.13.14, pytest 9.1.1. No provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | No P0/P1. `SI-CCR-001` P2 and `SI-CCR-002`/`003`/`004` P3 are closed by `60d181a` and this record correction; details in section 7. | Commit the counter-review record. The owner has now explicitly authorized the fixture-only SI-0/SI-1 source-contract tranche; licensed history remains a later full-ingest gate, not a blocker to synthetic contracts and fixtures. |
| 2026-08-28 | Codex implementation | `1de489c` -> `c821b10` (exact code snapshot; this lane-record commit follows) | SI-0/SI-1 source-contract and synthetic-fixture tranche | Added a lane-owned, outcome-free `research/short_interest_etf` package that freezes preregistration, official-snapshot/source/release/revision/security/volume/denominator contracts, conservative next-open availability, named refusals, stable-ID prior-cycle validation, append-only revisions, authenticated immutable vintage storage, and a separate noncanonical daily-short-volume type. Added one two-cycle synthetic official-style fixture and 66 dangerous-direction tests. No signal, provider adapter, licensed ingest, outcome join, ETF, or QC code was added. | Exact tree `c821b10`: **5,294 passed, 2 skipped, 0 failed, 25 known dependency warnings in 2,724.14s (45m24s)**. Final focused set: **77 passed in 18.24s**; 66 new Short Interest tests collected. Four reverse mutations each turned its guard red before textual restore: settlement/publication separation, full-payload event identity, immediate release-calendar prior linkage, and immutable-writer preflight. Full compileall exit 0; `git diff --check` clean. Python 3.13.14, pytest 9.1.1. Synthetic fixture only; no credential, provider, licensed row, outcome, QuantConnect, broker, operator database, scheduler, deployment, order, or trading access; **0 research looks**. | Independent read-only code and adversarial reviews found P1 temporal/prior-link gaps, P2 identity/storage/boundary gaps, and P3 numeric-contract gaps; all were corrected before `c821b10`. Both final dispositions are accepted-after-correction with no remaining P0-P3. Details in section 8. | Finalize and commit this lane record, then push the complete post-`da798f0` range once. Claude independently reviews the exact pushed range before any later implementation. Full licensed SI-1 remains gated on owner-approved historical/vintage data and release/identity/denominator entitlements. |
| 2026-08-28 | Claude review | `da798f0` -> `fee1978` reviewed; corrections at `11063c7` (this record commit follows) | Independent review of the Codex counter-review and the SI-0/SI-1 source-contract and synthetic-fixture tranche | Reviewed all four pushed commits individually. Accepted every finding of the Codex counter-review against my own prior work, including two that were my errors. Audited the new lane package against the owner PDF's frozen V1 specification and the section 3 bounded scope: the preregistration matches the blueprint exactly, the fixture is synthetic (`entitlement: synthetic_fixture_only`, ticker `SYN`), and no signal, ETF, portfolio, provider adapter, licensed ingest, outcome join, or QC code was added. | Complete suite in a clean detached worktree pinned to `11063c7`: **5,296 passed, 2 skipped, 0 failed, 25 known dependency warnings in 3,118.72s (51m59s)**. This independently confirms the implementer's 5,294-pass claim at `c821b10`: my tree is that tree plus exactly my two new tests (5,294 + 2 = 5,296) with the two skips unchanged. Lane suite 68 passed. Ten mutations run: four probing mutations survived and exposed the two findings plus one advisory; my two new guards each turn red against two independent mutants and green on restore; and two of Codex's four claimed mutations were reproduced independently (settlement/publication separation and full-payload event identity each turned exactly one test red). compileall exit 0; `git diff --check` clean. Synthetic fixture only; no credential, provider, licensed row, outcome, QuantConnect, broker, operator database, scheduler, deployment, or order access; **0 research looks**. | Two P3 findings confirmed and corrected in `11063c7`; three P3 advisory observations recorded with no code change. No P0, P1, or P2. Details in section 9. | Codex counter-reviews `11063c7` and this record commit. Full licensed SI-1 ingest remains gated on owner-approved historical/vintage data, archived FINRA dissemination evidence, and identity/denominator entitlements. |
| 2026-08-29 | Codex counter-review + implementation | `0a6561e` -> `6ef0ee9` (exact code snapshot; this lane-record commit follows) | Claude counter-review corrections + lane SI-2A offline PIT data readiness | Dispositioned Claude commits `11063c7` and `0a6561e` accepted after correction. `48fa344` closes exact-type, full-digest, exact-predicate, error-contract, and record-accuracy gaps. `de468f7` adds synthetic-only PIT lifecycle, classification, identity, denominator, ADV, and source-vintage readiness contracts. `6ef0ee9` preserves the active virtualenv during Windows preview validation while still refusing Store aliases. Recorded the owner's Short Interest/QC-only lane direction; no Trading App/Streamlit work was added. | Final complete suite on code snapshot `6ef0ee9`: **5,331 passed, 2 skipped, 0 failed, 26 known dependency warnings in 966.91s (16m06s)**; final SI-focused suite **100 passed in 12.08s**; installer evidence suite **57 passed in 101.79s**; compileall exit 0; `git diff --check` clean. Twelve reverse mutations across the SI-2A and Windows corrections each turned a guard red before textual restore. Synthetic fixtures only; no credentials, provider/licensed rows, outcomes, QuantConnect upload/job, broker, database, scheduler, deployment, order, or trading access; **0 research looks**. | `SI-CCR3-001` through `SI-CCR3-005` are closed with no remaining P0-P3 finding. SI-2A passed independent code/test audit after corrections. Details in sections 10 and 11. | Commit this record and push the four-commit combined round exactly once. Claude reviews that exact pushed snapshot. Full licensed SI-1/full SI-2 and all signals, outcomes, ETF aggregation, and QC algorithm/job work remain gated; future work in this lane stays Short Interest/QC-specific. |

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

## 7. Codex counter-review - 2026-08-28

Counter-reviewer: Codex in the dedicated Short Interest worktree. Repository:
`https://github.com/SheltonChen2017/trading_agent.git`. Branch:
`codex/strategy-short-interest`. Exact pushed review head:
`da798f073160dfd8074ff87b19ac942456f9c60c`; `origin/main` observed at
`6a507341896850076c13050da080f888d6eb31aa`. The counter-review correction is
`60d181a958b690f864f3d6463a376d7029908880`, local and one commit ahead of the
lane remote when this record was written. Both Claude commits were reviewed:

| Commit | Disposition | Reason |
|---|---|---|
| `54c678cf3fdfb2a0eb38002817382d5ec5174237` | **accepted after correction** | The zero-byte refusal test was useful, but the change skipped an existing successful-path parity test on the owner's host and left the separate reparse predicate unpinned. Corrected in `60d181a`. |
| `da798f073160dfd8074ff87b19ac942456f9c60c` | **accepted after correction** | The 16 implementation-commit dispositions and two resolved Claude findings are retained, but several record claims were inaccurate or incomplete. This section corrects them without rewriting the append-only Claude row. |

### 7.1 P0-P3 issue ledger

There are no P0 or P1 findings. Resolved issues remain recorded.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SI-CCR-001 | P2 | Closed | `54c678c` | `tests/test_ml_evidence_operations.py` installer preview/refusal tests | The correction made the valid eight-task installer/verifier action-parity test pass by skipping it on the documented Store-Python host. Its new ordinary zero-byte file also did not exercise the installers' distinct reparse-only predicate. This removed successful-path coverage on the project's actual host and left half of the safety predicate mutation-insensitive. | On the exact Claude tree, the zero-byte cases passed but the parity test reported one skip. Both installers reject `reparse OR zero length`, while the helper checked only length. | `CLAUDE.md` forbids skipping a valid test merely to make the suite pass, and both fail-closed predicates must remain behaviorally pinned. | `60d181a` resolves the real running Python process image for the operational policy-identity preflight, keeps the parity test active, and parametrizes both installers over ordinary zero-byte and mocked nonzero-reparse inputs. | Five corrected focused cases passed. Replacing the real image with `sys.executable` reproduced one parity failure in 3.44s; restore returned the five cases green. The reparse cases pass without administrator symlink privileges. |
| SI-CCR-002 | P3 | Closed | `da798f0` | Claude review row and section 6.6 | The record said SI-0/SI-1 was blocked on licensed history, contradicting section 3's authorized contracts-and-synthetic-fixtures scope, which explicitly forbids downloading licensed history. | Section 3 lines 59-75 define a fixture-only first tranche; the owner explicitly directed this session to implement the next milestone after counter-review. | A false blocker would stop authorized structural work or encourage unnecessary provider access. | This counter-review distinguishes the now-authorized synthetic contract tranche from later licensed ingest, provider audit, and outcome gates. | The next step below permits only offline contracts and fixtures and repeats every prohibited access boundary. |
| SI-CCR-003 | P3 | Closed | `da798f0` | Claude review validation arithmetic | The record said both full runs collected 5,228 tests, but `5,223 passed + 1 failed + 2 skipped` is 5,226. | Direct arithmetic; `54c678c` added two parametrized cases, producing 5,228 only on the corrected tree. | Validation counts are lineage evidence and must not be arithmetically impossible. | The corrected facts are 5,226 collected before `54c678c` and 5,228 after it. The earlier row remains historical and is superseded here. | Arithmetic independently recomputed during counter-review. |
| SI-CCR-004 | P3 | Closed | `da798f0` | Claude review lane-isolation and handoff metadata | "No frozen shared file entered this lane" was false: shared coordination and manifest files entered under the authorized one-time synchronization. The record also omitted Python version, repository URL, current `origin/main`, explicit push state, and that both Claude commits required counter-review. | The reviewed range changes `AGENTS.md`, shared coordination/process documents, `architecture/entry_points.json`, and shared tests; Git establishes the exact metadata listed above. | The lane record replaces the root handoff and must be sufficient for exact cross-computer continuation without overstating isolation. | Correct statement: no shared file changed **outside** the owner-authorized one-time remediation synchronization; no Analyst-only content entered this lane. This section records Python 3.13.14, pytest 9.1.1, repository, remote/main state, push state, and both commit dispositions. | `git log`, `git diff --name-only`, branch/upstream resolution, and the ordered two-commit review range were checked directly. |

### 7.2 Corrected disposition and next authorized step

The shared-remediation synchronization and portfolio-equity correction are
**accepted after correction** as this lane's baseline. This does not accept or
complete any Short Interest research milestone and does not establish market
evidence.

The owner has explicitly authorized the next bounded deliverable: the
**SI-0/SI-1 source-contract and synthetic-fixture tranche** from section 3.
It may implement lane-owned schemas, release availability/next-open cohorting,
immutable fixture vintages, the official-short-interest versus daily-short-
volume type/import boundary, and dangerous-direction tests. It must not access
credentials, providers, licensed rows, outcomes, QuantConnect, a broker, the
operator database, schedulers, paper/live deployment, or trading. Licensed
historical/vintage data, an archived official FINRA publication calendar,
stable-identity/denominator entitlements, and shared QC dataset audits remain
open gates for full ingest and later milestones; they do not block this
synthetic fixture tranche.

## 8. SI-0/SI-1 source-contract and synthetic-fixture implementation - 2026-08-28

Implementer: Codex in the dedicated Short Interest worktree. Repository:
`https://github.com/SheltonChen2017/trading_agent.git`; branch:
`codex/strategy-short-interest`; implementation commit:
`c821b106ca2679159b0ea51543d1ffafcbbf9fb9`; starting record commit:
`1de489c9e7ce3ca1194a46b40e0d97790c7362f3`; lane remote before the combined
push: `da798f073160dfd8074ff87b19ac942456f9c60c`; `origin/main` observed at
`6a507341896850076c13050da080f888d6eb31aa`.

### 8.1 Bounded delivered scope

- `research/short_interest_etf/preregistration.py` fixes the official open-
  short-position source semantic, XNYS execution calendar, audited-float versus
  canonical PIT-shares denominator order, `S0`-`S4` family with canonical
  `S1`, 20-session diagnostic, 10 bps primary and 0/5/20 bps sensitivity,
  unlevered V1, and a zero outcome-look budget. Preregistration SHA-256:
  `83165e805a8ad91787d10f066b28e14a1d6655d2dd19c4b5efd8a02a1ceeef9f`.
- `contracts.py` pins strict collection, stable security identity, settlement,
  release-calendar, revision, PIT denominator, exact ADV, reported and
  independently recomputed days-to-cover, and snapshot schemas. Financial
  quantities use canonical decimal text; bool, float-coercion, nonfinite,
  negative, zero-divisor, mismatched-security, future-window, and unknown-field
  inputs fail closed. Event identity hashes the complete canonical normalized
  payload rather than trusting a caller-supplied raw digest.
- `availability.py` maps an exact dissemination instant to the first XNYS open
  strictly after it and a date-only release to the next regular-session open.
  Settlement-day publication is structurally refused, and later revision,
  denominator, or volume availability defers the whole snapshot. Retrieval and
  observation timestamps are lineage only; neither grants earlier availability.
- `normalize.py` dispositions every input row as an accepted official snapshot
  or a named refusal. Duplicate source identities, malformed rows, invalid
  semantics, and daily-short-volume substitution cannot be silently dropped or
  coerced.
- `dataset.py` validates the immediately preceding official release-calendar
  cycle by stable `security_id`, retains every revision with immediate
  supersession, derives warm-up versus delta eligibility, and publishes an
  exact-file-set, content-addressed immutable vintage. The loader authenticates
  canonical control bytes, every blob hash and count, directory identity,
  caller-independent preregistration identity, and absence of unknown sidecars.
- `daily_short_volume.py` is a distinct transaction-flow type. It is not
  re-exported by the canonical package and cannot cross the snapshot type,
  normalization, dataset, availability, or AST import boundaries.
- `tests/fixtures/short_interest_etf/official_style_v1.json` is synthetic and
  contains two releases, two snapshot cycles, and zero refusals. Its source-body
  SHA-256 is
  `ef2818ead91c6ebee714eb0c63139a60a2442fb8789462e58840d46605053393`;
  normalized immutable identity is
  `short-interest-vintage-10651715ecb06a2f` with full content SHA-256
  `10651715ecb06a2fb4d703efe9ae8008f41b8d83d8b0e7c148600d7887657df5`.

This tranche implements contracts and synthetic fixtures only. It does not
claim completion of full lane SI-0 or licensed SI-1, does not implement any
stock score, and establishes no market evidence.

### 8.2 Implementation review findings

The implementation was reviewed while uncommitted by two independent,
read-only Codex agents. Findings were reproduced and corrected before the
stable code commit; both final reviews accepted the corrected tree and found
no remaining P0-P3 issue.

| ID | Priority | Status | Location | Finding and unsafe direction | Correction and verification |
|---|---|---|---|---|---|
| SI-M1-001 | P1 | Closed | Release and availability contracts | An exact pre-open timestamp could initially map a release to its settlement-day open. | Publication must strictly follow settlement, and the cohort function defensively refuses a settlement-date execution session. The direct mutation from `<=` back to `<` made the settlement-day test fail: **1 failed in 2.81s**. |
| SI-M1-002 | P1 | Closed | Prior-cycle and warm-up validation | A later row could initially fake a pre-window prior; omitting an intermediate release cycle could turn a multi-period move into a canonical delta; the first stored row was not visibly marked non-delta-eligible. | Prior linkage now follows the immediately preceding in-range release-calendar settlement by stable ID, only the manifest-start cycle may be warm-up, and delta eligibility is derived only when the authenticated prior is visible and share-consistent. Bypassing the calendar link made the omission test fail: **1 failed in 2.28s**. |
| SI-M1-003 | P2 | Closed | Normalized event and nested financial identities | Event IDs initially trusted raw lineage plus a few keys, so changed normalized facts could retain an ID. ADV and denominator records also lacked their own stable security binding. | Event ID now hashes the complete canonical payload; volume and denominator schemas carry `security_id` and must match the snapshot. Reverting event identity to raw hash made the binding test fail: **1 failed in 4.62s**. |
| SI-M1-004 | P2 | Closed | Immutable vintage read/write boundary | The first loader draft did not authenticate canonical `dataset.json` bytes or refuse unknown sidecars, and the writer could begin publication in a pre-squatted directory. | Reader and writer enforce exactly five regular authenticated files, canonical control bytes, immutable exact retries, preflight and post-publication authentication, and content/path identity. Removing preflight made its dedicated test fail before restore: **1 failed in 13.66s**. |
| SI-M1-005 | P2 | Closed | Offline semantic/import firewall | A root-only import check could miss internal price/QC modules, relative daily-volume imports, or future subpackages. | The AST guard recursively applies an exact standard/shared-helper allowlist to every package file and separately forbids canonical imports of the quarantined daily-volume module. Object, row, package-export, and refusal-identity tests pin the runtime boundary. |
| SI-M1-006 | P3 | Closed | Exact financial and error contracts | PIT shares outstanding initially allowed fractional values, and extreme finite DTC inputs could leak `decimal.InvalidOperation` instead of a named typed refusal. | Shares-outstanding denominators require whole positive shares. DTC uses input-sized exact precision, fixed 12-place half-even recomputation, and typed range errors; extreme finite and JSON-float/zero/negative mutations are covered. |

### 8.3 Validation and access accounting

- Exact committed code tree `c821b10`: **5,294 passed, 2 skipped, 0 failed,
  25 known dependency-deprecation warnings in 2,724.14 seconds (45m24s)**.
- Final focused run across the four new Short Interest modules plus the existing
  ML and overlay import boundaries: **77 passed in 18.24 seconds**. The four
  new test files collect **66 tests**.
- Four manual reverse mutations produced the four intended red cases recorded
  in section 8.2; every edit was textually restored, the focused set returned
  green, and the worktree was clean before the code commit.
- Full `compileall` across application, research, and tests exited 0;
  `git diff --check` was clean. The finalized active-document suite passed all
  **63 tests**.
- Only the Git-tracked synthetic fixture was opened. No credential, provider,
  licensed row, market outcome, QuantConnect job/upload, broker, operator
  database, scheduler, paper/live deployment, order, or trading surface was
  accessed. Permanent research-look count remains **0**.

### 8.4 Disposition, remaining gates, and next step

The bounded **SI-0/SI-1 source-contract and synthetic-fixture tranche is
implemented but not yet independently accepted by Claude**. It freezes the
offline boundary needed for later data work; it does not satisfy the full
licensed SI-1 ingest exit gate and creates no strategy evidence.

Still unresolved and intentionally absent: a licensed historical/vintage
short-interest source, archived official FINRA dissemination evidence, real
stable-identity and PIT denominator/ADV entitlements, split/restatement and
delisted-name coverage audits, QC data/holdings timing, every outcome join,
`S0`/`S1` computation, ETF construction, and deployment authority.

Commit this record and push the complete range after
`da798f073160dfd8074ff87b19ac942456f9c60c` once. Claude then independently
reviews every pushed Codex commit on this same lane. Codex must counter-review
every resulting Claude commit before any later milestone. No later
implementation is authorized by this entry.

## 9. Claude independent review - 2026-08-28 (counter-review and SI-0/SI-1 source-contract tranche)

Reviewer: Claude, dedicated Short Interest lane session, isolated worktree
`C:\git\customizedAgent\trading_agent_short_interest`. Governing documents:
`CLAUDE.md`, `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`,
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`, and the owner blueprint
`SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf`.

**Disposition: accepted after correction.** No P0, P1, or P2 issue was found.
Two P3 issues were confirmed and corrected; three P3 advisory observations are
recorded without a code change. Accepting this tranche accepts an offline
contract and fixture boundary only. It creates no market evidence, completes no
research milestone, and authorizes no later implementation.

### 9.1 Exact reviewed snapshot

| Item | Exact value |
|---|---|
| Lane branch | `codex/strategy-short-interest` |
| Previous reviewed head | `da798f073160dfd8074ff87b19ac942456f9c60c` |
| Reviewed remote head | `fee1978e6854468f4c0dbae51fcb0823107aef43` |
| Ordered reviewed range | `da798f0..fee1978` (4 commits, no merge commit) |
| Ancestry | `da798f0` is an ancestor of `fee1978`; clean fast-forward, no rebase, and both earlier Claude commits are preserved |
| Claude correction commit | `11063c7` |
| Python / pytest | 3.13.14 / 9.1.1 |

### 9.2 Commit dispositions

| # | Commit | Scope | Disposition |
|---|---|---|---|
| 1 | `60d181a` | Preserve installer preview coverage in counter-review | accepted |
| 2 | `1de489c` | Record short-interest counter-review | accepted |
| 3 | `c821b10` | Implement short-interest source contracts and fixtures | **accepted after correction** (`SI-CR2-001`, `SI-CR2-002`) |
| 4 | `fee1978` | Record short-interest source-contract milestone | accepted |

### 9.3 The counter-review against my own prior work is accepted in full

All four Codex findings were independently checked rather than conceded.

- `SI-CCR-001` (P2) is **correct and its fix is better than mine**. My skip gave
  up the successful-path eight-task parity contract on the owner's own host.
  I had wrongly concluded the real interpreter was unusable: the ACL-denied
  binary is `python.exe` inside the package directory, while the running
  process image that `60d181a` resolves is `python3.13.exe`, which executes
  normally. Verified here: the five focused cases pass on this Store-Python
  host. The mocked `Get-Item` used for the reparse-only predicate is safely
  scoped, because each installer calls `Get-Item` exactly once.
- `SI-CCR-002` (P3) is correct. Section 3 authorizes a fixture-only tranche and
  forbids downloading licensed history, so naming licensed data as an SI-0/SI-1
  blocker conflated full ingest with the synthetic contract scope.
- `SI-CCR-003` (P3) is correct and was my arithmetic error. The pre-correction
  run collected 5,226, not 5,228; only the corrected tree collected 5,228.
- `SI-CCR-004` (P3) is correct. Shared coordination files, `AGENTS.md`,
  `architecture/entry_points.json`, and shared tests did enter this lane under
  the authorized one-time synchronization, so "no frozen shared file entered
  this lane" overstated isolation. The accurate statement is that no shared
  file changed outside that authorization and no Analyst-only content entered.

### 9.4 P0-P3 issue ledger

Resolved items are retained. There are no P0, P1, or P2 findings.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SI-CR2-001 | P3 | Closed | `c821b10` | `research/short_interest_etf/dataset.py` snapshot type check; `research/short_interest_etf/availability.py` `snapshot_execution_cohort` | Both boundaries deliberately require the exact `ShortInterestSnapshot` type, and their error text advertises that rule, but no test distinguished it from `isinstance`. A later simplification to `isinstance` would admit a subclass that overrides validated behaviour and carry non-canonical semantics into the immutable dataset under a canonical name, with no test turning red. | Replacing the dataset check with `isinstance` left 26 tests green; replacing the availability check with `isinstance` left 20 tests green. No lane test constructs a subclass; the daily-volume record is a separate class and is refused either way. | A deliberate fail-closed predicate must stay mutation-sensitive; this is the same standard the counter-review correctly applied to my own unpinned reparse predicate. | Added `test_snapshot_subclass_cannot_substitute_for_the_exact_canonical_type`, which builds a subclass impostor from the fixture snapshot and requires both boundaries to reject it. | The new test turns red against the mutated dataset check and against the mutated availability check, and returns green after textual restore of each. |
| SI-CR2-002 | P3 | Closed | `c821b10` | `research/short_interest_etf/contracts.py` `CollectionManifest.sha256` | The manifest's own content digest is reached by no caller in the package and by none of the 67 lane tests, so it could silently stop identifying its manifest and the first consumer would inherit a digest that cannot distinguish two collections. | Replacing the property body with `raise AssertionError` left all 67 lane tests green, proving it is never evaluated. The sibling `PREREGISTRATION.sha256` is both consumed by dataset lineage and asserted by a test. | A frozen contract's identity surface must be pinned rather than left unexercised, and pinning is less destructive than removing a property a later consumer is expected to use. | Added `test_collection_manifest_digest_is_deterministic_and_content_bound`, asserting a stable 64-character digest, reproducibility, and sensitivity to two independent manifest facts. | The new test turns red against a constant-digest mutant and against a mutant that drops one field before hashing, and green on restore. |
| SI-CR2-003 | P3 | Open (advisory, no change) | `c821b10` | `research/short_interest_etf/availability.py` `release_execution_cohort` | The `cohort.session <= release.settlement_date` fallthrough is unreachable: `contracts.py:358` already refuses any release whose date does not strictly follow settlement, and an exact release timestamp must carry the same Eastern date. | Replacing the whole branch with `if False:` left the 12 availability tests green, because no constructible input reaches it. | No fix is proposed. The branch is deliberate defence in depth and section 8.2 already describes it as defensive. It is recorded so that a future reader does not mistake a surviving mutation there for a coverage hole. | None. | Reachability traced to the constructor invariants at `contracts.py:358` and the Eastern-date pin. |
| SI-CR2-004 | P3 | Open (advisory, no change) | `c821b10` | `research/short_interest_etf/availability.py` `snapshot_execution_cohort` | The conservative rule selects the latest cohort with `max(..., key=lambda cohort: cohort.opens_at)` over ISO strings. Lexicographic order matches chronological order only while every value has identical width, because `2026-08-11T13:30:00.5Z` sorts before `2026-08-11T13:30:00Z`. | Verified empirically that `session_open_instant` yields microsecond 0 for regular and half-day sessions, so every `opens_at` is whole-second and the current comparison is correct. | No current defect and therefore no change. Recorded because this is the single most safety-critical function in the lane, and comparing the parsed instant would remove the latent ordering hazard permanently if sub-second availability is ever introduced. | None. | Empirical precision check across regular and early-close sessions. |
| SI-CR2-005 | P3 | Open (advisory, no change) | `c821b10` | `research/short_interest_etf/dataset.py` import of `ml.immutable_io` | The lane package depends on `ml`. This is correct today, but it means the lane package can never be imported by execution-capable code without breaching the ML import boundary. | `ml/immutable_io.py` is the only immutable-byte publisher in the repository, so reuse is right and a parallel copy would be worse; nothing under `assistant/`, `execution/`, `risk/`, or `scripts/` imports the lane package, so no transitive path exists; and the lane's own boundary test allow-lists the module explicitly. | No fix. Recorded as a forward constraint for SI-7 and the later integration milestone, when a QuantConnect or execution-adjacent consumer would have to take a non-`ml` path to immutable storage. | None. | Import graph inspected from the execution-capable roots and from the lane package. |

### 9.5 Independent verification of the implementation

- **Frozen specification matches the owner PDF.** The preregistration pins the
  official open-short-position semantic, XNYS, canonical PIT shares outstanding
  with audited float preferred, the `S0`-`S4` family with canonical `S1`, a
  20-session diagnostic, 10 bps primary cost with 0/5/20 sensitivity, unlevered
  V1, and a **zero outcome-look budget**. Every field is `init=False`, so a
  caller cannot override a frozen choice. These agree with the blueprint's
  frozen V1 specification and with section 1 of this record.
- **The fixture is synthetic.** `fixture_kind` is
  `synthetic-short-interest-official-style-v1`, the manifest entitlement is
  `synthetic_fixture_only`, the source is `synthetic-official-style-short-
  interest`, and the only security is the invented `SYN` / `sec-synth-001`. No
  licensed row is present, consistent with the section 3 prohibition.
- **Scope is respected.** The range adds no signal computation, ETF
  aggregation, portfolio, provider adapter, credential use, outcome join, or
  QuantConnect artefact. It touches no other lane and no shared file.
- **The daily-short-volume firewall holds at four independent levels**: a
  separate class that is not a subclass, absence from the package exports, an
  exact-type refusal at both the dataset and availability boundaries, and an
  AST guard that forbids canonical modules from importing the quarantined
  module. Its refusal is also bound into the immutable dataset identity, so a
  rejected row cannot be silently dropped.
- **Availability is conservative in the right direction.** A snapshot becomes
  tradable only at the first open after the latest of its release, its revision
  publication, its volume-basis availability, and its denominator availability,
  so a late input defers the whole snapshot rather than being ignored.
- **Codex's own evidence was spot-checked, not assumed.** Two of its four
  claimed mutations were reproduced independently: weakening the
  settlement/publication separation to `<` and reverting event identity to the
  caller-supplied raw digest each turned exactly one test red. Its reported
  test counts also reconcile with my own measurements on this host.

### 9.6 Review scope and what was not audited

- `contracts.py` and `dataset.py` were reviewed for the safety-critical
  properties named above and exercised by mutation at four sites. They were not
  re-derived line by line; the strict-schema, refusal, and immutable-storage
  behaviour is taken from the 68 lane tests plus the mutations recorded here.
- No licensed, provider, or market data exists to test against, so every claim
  in this tranche is a claim about software behaviour on a synthetic fixture.
  Consistent with `CLAUDE.md`, that is **not** evidence of any market edge, and
  no part of this review constitutes research evidence.
- The Windows installer behaviour reviewed in section 6 was re-verified only
  through the corrected focused tests; no scheduled task was registered.

### 9.7 Remaining gates and next authorized step

1. Codex counter-reviews `11063c7` and this record commit.
2. Full licensed SI-1 ingest remains gated on an owner-approved historical or
   vintage short-interest source, archived official FINRA dissemination
   evidence, and stable-identity, denominator, and ADV entitlements. None of
   these is required for, or unblocked by, this synthetic tranche.
3. SI-2 and every later milestone remain unauthorized. No outcome join, ETF
   construction, QuantConnect job, provider access, deployment, or trading
   authority follows from accepting this tranche, and the permanent research-
   look count remains 0.

## 10. Codex counter-review - 2026-08-29

### 10.1 Exact reviewed snapshot and dispositions

| Fact | Value |
|---|---|
| Branch/worktree | `codex/strategy-short-interest` in `C:\git\customizedagent\trading_agent_short_interest` |
| Remote starting head | `0a6561e0f436b81d31d0c0d843fb8b666733fc06` |
| Claude commits reviewed | `11063c7` and `0a6561e` |
| Underlying implementation/review range inspected | `da798f0..0a6561e`, including the earlier shared-test correction in `60d181a` |
| Codex review correction | `48fa344858015c4bb5ce95697a9ce6c3e0eed365` |
| Next bounded implementation | `de468f768c199f008601301c8f025f697b3508ce` |
| Full-suite follow-up correction | `6ef0ee92bad51c2f27725510c76a367698cd5594` |

- `11063c7`: **accepted after correction**. Its two targeted guards are valid,
  but the same exact-type policy and full-payload digest policy were not yet
  pinned across the complete canonical boundary.
- `0a6561e`: **accepted after correction**. The record correctly captured the
  main review result, but overstated lane isolation and did not contain the
  later counter-review findings, corrections, milestone, or owner direction.
- No P0-P3 issue remains open in this counter-reviewed round. The historical
  Claude text remains intact; this section supersedes only the inaccurate or
  incomplete claims identified below.

### 10.2 P0-P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction and verification |
|---|---|---|---|---|---|
| SI-CCR3-001 | P2 | Closed in `48fa344` | `contracts.py`, `dataset.py`, `availability.py` | `CollectionManifest` and nested `SecurityIdentity`, `VolumeBasis`, and `DenominatorObservation` subclasses could override serialization after validation; release/refusal collection boundaries were not uniformly exact-type. That could decouple validated semantics, PIT time, and authenticated bytes. | Enforced exact canonical types at each boundary, made the errors advertise exactness, and added malicious-subclass tests. Relaxing the covered manifest, nested-contract, release, or refusal predicates turns a guard red. |
| SI-CCR3-002 | P3 | Closed in `48fa344` | Manifest/preregistration digest tests | The manifest test bound only two fields and the preregistration test only the digest length, so a partial-payload hash could survive. | Tests now require equality with `hash_payload(...to_payload())` for the complete canonical payload. A mutant hashing only `snapshot_name` and `source_version` fails. |
| SI-CCR3-003 | P3 | Closed in `48fa344` | `ReleaseCalendarEntry` and `SnapshotRefusal` dataset boundaries | The deliberate exact-type predicates had no subclass-impostor tests. | Added targeted tests that turn red when either predicate is relaxed. |
| SI-CCR3-004 | P3 | Closed by `48fa344` and this record | Review diagnostics and record claims | The availability refusal omitted the exact-type rule, and section 9.5 said no shared file was touched even though `60d181a` changed shared `tests/test_ml_evidence_operations.py`. | Corrected the error contract. This record now distinguishes authorized/shared prior work from the lane-owned SI implementation rather than claiming no shared-file change. |
| SI-CCR3-005 | P2 | Closed in `6ef0ee9` | `tests/test_ml_evidence_operations.py::_preview_interpreter` | The earlier Windows correction always used the base process image. In an active virtualenv that loses installed dependencies, making the preview parity test fail with `ModuleNotFoundError: pandas_market_calendars`. | Preserve a runnable `sys.executable`; fall back to the process image only for a zero-byte, non-regular, inaccessible, or reparse-point Store alias. Dedicated runnable/zero-byte/reparse tests and the complete evidence-operations suite are green. Three reverse mutations independently turn those guards red. |

### 10.3 Counter-review evidence

- The first complete run on `de468f7` was intentionally not hidden: **5,327
  passed, 2 skipped, 1 failed, 26 warnings in 1,125.97s**. The sole failure
  reproduced `SI-CCR3-005` on the owner's active virtualenv.
- After `6ef0ee9`, the exact code snapshot passed **5,331 tests**, skipped 2,
  failed 0, and emitted 26 known dependency warnings in **966.91s**. The full
  `test_ml_evidence_operations.py` file passed **57 tests in 101.79s**.
- The final SI-focused contracts/availability/dataset/import-boundary set
  passed **100 tests in 12.08s**. Compileall exited 0 and `git diff --check`
  was clean. The final host used Python 3.12.13 and pytest 9.1.1; Python 3.13
  was not available on its `PATH`.
- Twelve dangerous-direction mutations were run and textually restored: nine
  for SI-2A temporal, identity, lineage, denominator, ADV, prior-cycle, and
  corporate-action rules; three for the Windows interpreter selection. Every
  intended guard turned red.
- Independent code and test audits reported no remaining P0-P3 issue. All work
  was synthetic/offline; no research outcome was accessed and the permanent
  research-look count remains **0**.

## 11. Lane SI-2A offline PIT data-readiness tranche - 2026-08-29

### 11.1 Scope and naming

This bounded prerequisite tranche implements the blueprint's point-in-time
security-master, lifecycle, sector-classification, denominator, volume, and
data-validity requirements before any signal can exist. The lane label
**SI-2A** means "offline PIT data readiness"; it is not the blueprint's
experimental **SI-2** ETF aggregation round. Full licensed SI-1, full SI-2,
and all outcome-bearing work remain unimplemented.

The implementation is `de468f7` and consists only of:

- `research/short_interest_etf/pit_eligibility.py`;
- `tests/fixtures/short_interest_etf/pit_reference_v1.json`; and
- `tests/test_short_interest_pit_eligibility.py`.

### 11.2 Implemented safety contracts

- `PitReferenceManifest`, `SecurityLifecycleObservation`,
  `SectorClassificationObservation`, `PitReferenceBundle`, and
  `StockDataReadiness` are strict, canonical, exact-type contracts with named
  refusal codes.
- Joins use stable security IDs, never ticker as permanent identity. Lifecycle,
  classification, and identity must be effective and available by the release
  execution cohort; classification is evaluated at the executable release
  session, not backdated to settlement.
- Ambiguous overlaps, an already-delisted security, unresolved merger,
  share-class, split, or ticker-change state, and identity that expires before
  execution fail closed. A later delisting remains visible without being
  backfilled into an earlier decision.
- Missing prior history is distinct from a prior snapshot superseded before
  its first executable open.
- Denominator and ADV lineage are content-bound. This tranche supports audited
  PIT shares outstanding only; unaudited float is refused. ADV must end at the
  settlement session and carries its complete lineage hash.
- The complete source vintage and dataset relation are authenticated, sector
  taxonomy identity is carried forward, and bundle/readiness hashes are
  deterministic, order-invariant, and content-bound. Eligible/visible sets are
  cached only by execution instant plus reference identity.
- Exact execution session/open and canonical refusal/provenance fields are
  preserved in every readiness result. No price, market-cap, signal, ETF,
  outcome, or portfolio field is accepted by this boundary.

### 11.3 Validation and exclusions

The new PIT module's own suite passed **26 tests in 10.33s** after all guards
were added. Nine reverse mutations individually proved the stable-ID lifecycle
join, execution-time classification, exact lifecycle type, execution-valid
identity, full readiness hash, audited-denominator refusal, settlement-bounded
ADV, prior-state distinction, and complete corporate-action firewall.
Together with the prior SI tranche, the final SI-focused set passed 100 tests;
the complete repository result is recorded in section 10.3.

This tranche deliberately adds no signal calculation, price or market-cap
threshold, stock-liquidity threshold, selected ADV window `K`, ETF aggregation,
provider/licensed adapter, outcome join, QuantConnect algorithm or job, broker
or deployment integration, or trading authority. It used only the authenticated
synthetic fixture and consumed **0 research looks**.

### 11.4 Remaining gates and next step

1. Claude independently reviews the exact single pushed combined round,
   including `48fa344`, `de468f7`, `6ef0ee9`, and this record commit. Codex
   counter-reviews every resulting Claude commit before further implementation.
2. Full licensed SI-1 still requires an owner-approved historical/vintage
   source, archived official FINRA dissemination evidence, and the required
   entitlements. Full real-data SI-2 requires an audited PIT security master,
   lifecycle/delisting, shares-or-audited-float, sector, and ADV sources.
3. The float path is absent by design; shares outstanding is the only accepted
   denominator in this tranche. Price, market-cap/liquidity thresholds, and the
   exact ADV window `K` remain unfrozen and must not be invented.
4. Per the 2026-08-29 owner direction, every next milestone in this branch must
   stay Short Interest/QC-specific. Trading App/Streamlit work is out of scope.
   An external QuantConnect upload/job run still requires explicit authority.
