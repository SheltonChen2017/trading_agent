# Insider Buying ETF Strategy — implementation and session record

Status: **PLANNED; NO INGEST, SIGNAL, OUTCOME TEST, ETF PORTFOLIO, OR QC
ALGORITHM HAS BEEN IMPLEMENTED.**

Branch: `codex/strategy-insider-buying`

Governing owner source: `INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf`, 33
pages, 945,953 bytes, SHA-256
`f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c`.

Codex is the primary implementer. Claude is the independent reviewer. Both
agents work serially on this same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

## 1. Canonical V1 contract

The initial event family is deliberately narrow:

- SEC Form 4/4-A, non-derivative common stock, transaction code `P`, acquired
  (`A`), officer/director, direct ownership, positive shares and price;
- reported purchase value at least $50,000;
- public EDGAR acceptance time—not transaction date—as availability, with
  next-open execution; date-only data receives a conservative next-day rule;
- `ln(1 + purchase_value / 50,000)` event size, 20-trading-day half-life,
  30-day lookback, winsorized cross-sectional z-score;
- unique-buyer, role, date, dollar breadth, and clustering are separate
  diagnostics rather than hidden score multipliers;
- PIT reverse ETF holdings with a conservative five-trading-day holdings lag
  unless QC `LastUpdate`/availability semantics are proven;
- US long-equity ETFs, at least 252 sessions old, price >= $5, median 20-day
  dollar volume >= $5M, holdings mapping >=90%, at least two seed stocks, and
  seed exposure >=5%; and
- weekly top 3-5 long-only ETFs, max 25% per ETF, 40% sector/theme cap, 35%
  overlap-cluster cap, cash permitted, and no leverage.

Sales, gifts, awards, derivatives, options, Form 5, indirect ownership, 10%
owners, price ranges, joint owners, private `P` transactions, amendments, and
10b5-1 effects must be classified explicitly and fail closed until their
preregistered treatment exists. They must not be silently mixed into the
canonical family.

## 2. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| IB-0 | Freeze Form 4 schema, event inclusion/exclusion, amendment handling, availability, identity, score, horizons, costs, and look budget. | Complete preregistration; no outcomes accessed. |
| IB-1 | Ingest SEC quarterly files plus full-filing XML/metadata into immutable accession-versioned storage. | Reproducible checksums; amendment and duplicate tests; fair-access compliance. |
| IB-2 | Resolve CIK/reporting owner/security/transaction identities point-in-time. | Joint-owner, issuer, ticker-reuse, share-class, and amendment mutations fail closed. |
| IB-3 | Implement canonical stock event score and separate breadth diagnostics. | Golden equations and no outcome imports. |
| IB-4 | Build PIT ETF reverse index and eligibility/aggregation. | Holdings availability/lag, >=90% mapping, seed/exposure gates, and stale-map tests pass. |
| IB-5 | Run stock-level event study first, then industry and ETF topology tests. | Permanent look logged; primary result and null rule honored. |
| IB-6 | Walk-forward ETF portfolio research with fixed costs and baselines. | OOS robustness, turnover, capacity, overlap, and concentration gates. |
| IB-7 | Implement QC algorithm from immutable precomputed/custom signals. | Deterministic parity and failure/scheduling/sizing tests; research-only. |
| IB-8 | Final holdout and promotion dossier. | Owner approval required before paper deployment. |

## 3. First implementation scope

The first Codex session should implement **IB-0/IB-1 structural tests and an
offline fixture parser only**:

1. pin SEC submission, reporting owner, non-derivative transaction, footnote,
   accession, and acceptance-time schemas;
2. encode canonical include/exclude decisions as named outcomes;
3. model original/amended filing lineage without deleting the as-filed row;
4. add dangerous-direction tests for transaction-date availability,
   same-day execution, Form 5 inclusion, indirect ownership, missing price,
   and duplicate joint owners; and
5. update this record before the first push.

No SEC network crawl, outcome join, ETF construction, QC backtest, or broker
work is authorized by this plan.

## 4. Required data and unresolved gates

- SEC quarterly Insider Transactions Data Sets are free and cover Jan-2006
  onward, but they omit some filing metadata; the complete Form 4/4-A filing
  and EDGAR acceptance timestamp must be joined by accession.
- A durable CIK-to-security/QC Symbol mapping is not established.
- QC prices, security master, fundamentals, and PIT ETF holdings entitlements
  and timing semantics remain to be audited.
- A paid insider feed is optional, not required for canonical history. A
  commercial real-time feed may later reduce live latency but cannot replace
  the SEC filing as provenance without a measured reconciliation.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | Source reviewed and implementation ladder recorded; no code. | PDF text and all 33 rendered pages inspected; no outcome access; 0 looks. | SEC data is sufficient for a canonical offline backbone only when full-filing metadata is joined. | Claude reviews baseline; implementation waits for owner instruction. |
| 2026-08-27 | Codex implementation | `a4f58e6` -> `e770b05` (code snapshot; this lane-record commit follows) | Owner-authorized one-time common remediation synchronization | Synchronized the bounded shared-remediation series through `52518d6`, then identical final shared patch `e770b05` (source `6770db3`, stable patch ID `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`). The range contains no Analyst-only commit or file and no Insider strategy implementation. | Exact lane tree: 5,223 passed, 2 skipped, 25 dependency-deprecation warnings in 36m40s; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean; worktree clean. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or live scheduler access; **0 research looks**. | Independent final audit found no remaining P0-P3 issue in the synchronized shared diff. Synchronization is not acceptance; IB-0/IB-1 has not started. | Push this exact lane-recorded snapshot; Claude reviews every pushed commit on this lane, then Codex counter-reviews every Claude commit before IB-0/IB-1 can begin. |
| 2026-08-27 | Codex implementation | `8a65e3c` -> `f943bfc` (code snapshot; this lane-record commit follows) | Owner-authorized shared portfolio-equity correction | Cherry-picked source fix `1ed0602` into `assistant/portfolio_snapshot.py` and `tests/test_assistant_risk_copilot.py`. The builder now aggregates exact Decimal cash and position values before rounding the single total-equity display, preventing legitimate fractional-share portfolios from failing the strict display/exact integrity check. The validator, policy limits, broker contracts, strategy code, and research gates were not weakened or changed. | Focused portfolio/risk/coherent-snapshot suite: 112 passed, 0 failed, 1 dependency warning in 3.01s; compileall exit 0; `git diff --check` clean. Source correction previously passed the complete 5,442-test suite and a reverse mutation that reproduced display `100.01` versus exact `100`. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | `SYS-FU-P1-006` reproduced: per-position display rounding accumulated into a competing equity total and prevented UI load. Corrected without adding tolerance; pending Claude review and Codex counter-review. IB-0/IB-1 remains unstarted. | Validate and push the exact recorded lane snapshot. Claude then reviews both new commits on this lane before IB-0/IB-1 or any later milestone. |
| 2026-08-27 | Codex validation | `29efc30` -> `29efc30` (exact isolated tested snapshot; this validation-record commit follows) | Portfolio-equity correction final validation | Revalidated the complete Insider Buying lane after its code and required lane-record commits in a detached isolated worktree pinned to `29efc30`; no product file changed during the run. | Complete exact-tree suite: **5,224 passed, 2 skipped, 0 failed, 25 dependency warnings in 1,832.32s (30m32s)**. The earlier focused 112-test suite, 63-test active-document suite, compileall, and diff checks were also green. Fixture-only; no SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | No new P0-P3 finding. `SYS-FU-P1-006` remains implemented but unaccepted pending the required review chain; IB-0/IB-1 remains unstarted. | Commit this validation record and push the complete three-commit lane range; Claude reviews every new commit before IB-0/IB-1 or any later milestone. |
| 2026-08-28 | Claude review | `b4ba4b2` -> this review snapshot | Independent review of the owner-authorized shared remediation synchronization (`a4f58e6..b4ba4b2`, 16 commits) | Verified provenance by stable patch ID (12 of 13 synchronized commits patch-identical to their merged main-line counterparts; the single divergence correctly omits the analyst-only entry-point registration), confirmed the frozen-file freeze held, and reviewed every commit for fail-open, atomicity, money-type, and test-weakening defects. Corrected one confirmed defect and escalated one open P1. Full dispositions and the P0-P3 ledger are in section 6. | Complete suite at `8a65e3c`: 1 failed, 5,222 passed, 2 skipped in 29m07s (the failure is R-02, contradicting the recorded zero-failure claim on this host). After correction: affected file 49 passed, 1 skipped; import-boundary/entry-point/active-document 98 passed; execution-gate and characterization 76 passed; dispatch-fence and cancel-all 89 passed, 1 skipped; broker-binding suites 263 passed, 1 skipped; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean. Final complete suite on the exact pushed tree `58bf2f8`: **5,223 passed, 3 skipped, 0 failed, 25 warnings in 36m32s**. An intermediate complete run under host contention reported 6 `TimeoutExpired` failures against byte-identical code and is recorded as R-19 rather than omitted. Two mutations run and reverted cleanly. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or scheduler access; **0 research looks**. | R-01 (P1, OPEN): strict snapshot coherence refuses submission on any price tick with no risk-reducing-sell exemption, conflicting with the CLAUDE.md section 5 exception; escalated for an owner decision rather than corrected on a lane branch. R-02 (P2) fixed in `1c1d943`. R-03 to R-08 recorded open for counter-review. A second audit then changed the `9406a34` disposition to defect-found: R-09 to R-15 are seven further P1 issues open at HEAD, four verified directly against this host, including a machine-global execution stop currently latched active by test-origin incidents. R-18 records that the same stop defeats cross-lane isolation; R-16, R-17, and R-19 are lower-severity. Nine P1 issues are open in total and none was corrected on this lane, because they are shared execution semantics synchronized from `main`. | Codex counter-reviews every Claude commit in this range, then may begin IB-0/IB-1 in one combined push. R-01 needs an explicit owner decision before it can be closed. IB-0/IB-1 remains unstarted. |

## 6. Claude review - shared remediation synchronization (2026-08-28)

Reviewer: Claude, dedicated Insider Buying lane review session, working in an
isolated worktree pinned to this branch. Range reviewed: `a4f58e6..b4ba4b2`
(13 synchronized commits plus 3 later lane commits). No `git switch` was used
and no other lane, checkout, or branch was touched.

Owner-directed authority for this range is the one-time common-remediation
exception recorded in `THREE_STRATEGY_PARALLEL_WORKFLOW.md` and
`THREE_STRATEGY_PROJECT_DIRECTION.md`. Synchronization is not acceptance.

### 6.1 Provenance and isolation verification

- 12 of the 13 synchronized commits are **patch-identical** to their
  owner-merged main-line counterparts by `git patch-id --stable`, including
  the final shared patch `e770b05`, whose stable patch ID
  `30e807c0ae2cf05016a2ce17c416daaaa275dcbc` matches the value claimed in the
  section 5 ledger.
- The single intended divergence is `800c689` versus main `8cab638`: the lane
  commit correctly **omits** the analyst-only `research/analyst_revisions_v2`
  entry-point registration and its assertion. Verified by interdiff; exactly
  two lines differ. No analyst-only file, research module, or test entered
  this lane.
- Every frozen-document change in the range traces to the single
  owner-authorized reconciliation commit `52518d6`.
  `docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md` are
  unmodified. No `research/` file changed on this lane.
- No SEC, EDGAR, vendor, QuantConnect, credential, licensed-row, broker,
  operator-database, or scheduler access occurred during this review.
  **0 research looks.** IB-0/IB-1 remains unstarted.

### 6.2 Commit dispositions

| Commit | Subject | Disposition |
|---|---|---|
| `63987ab` | Fix boolean coercion in trading policy limits | Accepted |
| `4e60b63` | Add cross-process execution dispatch fence | Accepted after correction later in range |
| `f602792` | Harden dispatch fence across process forks | Accepted |
| `5d22602` | Bind execution authorization to broker context | Accepted after correction later in range |
| `5fc891f` | Make broker anomaly containment atomic | Accepted after correction later in range |
| `c31f1e3` | Fence and drain emergency order cancellation | Accepted after correction later in range |
| `2fc3dd6` | Bind broker access to coherent account snapshots | Accepted after correction; **one P1 open at HEAD (R-01)** |
| `b4f4532` | Close emergency cancel-all indexing races | Accepted after correction later in range |
| `9406a34` | Harden shared trading safety boundaries | **Defect-found** - seven P1 issues open at HEAD (R-09 to R-15); `assistant/storage.py` is byte-identical between this commit and HEAD, so nothing here was repaired downstream |
| `800c689` | Register shared research input boundaries | Accepted, lane-correct divergence verified |
| `52518d6` | Reconcile three-strategy review workflow | Accepted |
| `e770b05` | fix: close shared remediation regressions | Accepted after correction (**R-02**, corrected here); one silent-row-drop loosening recorded as R-16. It fixes real code and is not a loosen-the-tests commit. |
| `8a65e3c` | docs: record shared remediation synchronization | Accepted |
| `f943bfc` | Fix portfolio equity display aggregation | Accepted, mutation-verified |
| `29efc30` | Record insider lane portfolio rounding sync | Accepted |
| `b4ba4b2` | Record insider lane full validation | Accepted with a correction to its validation claim (**R-02**) |

Commits marked "accepted after correction later in range" had a real defect at
that commit which is already remediated by a later commit inside this same
synchronized range. Each was re-verified at HEAD by reading the fixed code
path, not by trusting a commit message.

### 6.3 P0-P3 issue ledger

Resolved items are retained, never deleted.

| ID | Sev | Status | Issue |
|---|---|---|---|
| R-01 | P1 | **OPEN - escalated to owner, deliberately not corrected here** | Strict execution-snapshot coherence refuses submission on any market-price movement, with **no risk-reducing-sell exemption**. `_execution_snapshot_state_fingerprint` hashes every position `current_price` and `market_value`; `_assert_execution_snapshot_unchanged` (`execution/alpaca_broker.py:857`) requires a byte-identical recapture immediately before broker contact, and both submission paths (`:1481` market, `:1610` limit) call it unconditionally with no branch on `side`. A single tick in any held symbol refuses the order. The direction is fail-closed, so nothing wrong is sent, but CLAUDE.md section 5 states a conservative safeguard must not delay or obstruct a legitimate risk-reducing sell. The branch tests pin the refusal as the specification, so this is a deliberate design that conflicts with a standing safety exception: an owner decision, not a reviewer edit. |
| R-02 | P2 | **FIXED - `1c1d943`** | `e770b05` added `test_windows_verifier_green_actions_match_installer_whatif_previews`, which passes `sys.executable` to the real installer. The installer correctly refuses a Microsoft Store app execution alias, a zero-byte reparse point a scheduled task cannot launch. On a host whose default interpreter is that alias the test failed deterministically, so the recorded zero-failure validation was not reproducible here. Corrected with a skip guard mirroring the installer enforcing condition exactly, reparse point **or** zero length, via `lstat` so the reparse point is not followed. Product behavior unchanged. |
| R-03 | P2 | OPEN - for counter-review | Re-invoking emergency cancel-all against orders already in `pending_cancel` may never satisfy the stability condition, activating a critical reconciliation halt although containment is complete. Fail-closed, a spurious critical alert and never fail-open. Depends on the broker real response to cancelling a `pending_cancel` order; not verified against a live broker, so deliberately not fixed on an unverified assumption. |
| R-04 | P2 | OPEN - for counter-review | The execution timing budget is self-defeating under contention: the snapshot authority window and the dispatch-fence acquisition timeout are both 30 seconds, so a dispatch that waits materially for the fence holds an already-expired snapshot and is refused. Affects a queued risk-reducing sell equally. |
| R-05 | P3 | OPEN | `_validated_authorization_binding` accepts `none`, `null`, and `unknown` as `account_id`, while `broker_contract.py`, `alpaca_broker.py`, and `portfolio_snapshot.py` all reject those sentinels. Not exploitable today; the layer that signs identity has the weakest identity contract of the four. |
| R-06 | P3 | OPEN | Two alert-fingerprint schemes coexist for one category: `activate_reconciliation_halt` still uses the proposal-only form while anomaly containment uses the form suffixed with an anomaly key. An operator acknowledgement of one does not suppress the other. |
| R-07 | P3 | OPEN | A permanent component-equity disagreement is raised as a transient mutation, so it burns the retry budget and is reported as broker state did not stabilize, pointing the operator at a race rather than the real cause. |
| R-08 | P3 | OPEN | Order-level account identity is self-asserted: `portfolio_snapshot.py` passes the same identity object as both expected and observed, making that mismatch check a tautology at those call sites. The durable `assert_expected_broker_account` path remains meaningful. |

| R-09 | P1 | **OPEN - LIVE OPERATIONAL CONDITION, owner action required** | The machine-global runtime execution stop is **currently active on this host**. `C:\Users\<user>\AppData\Local\trading_agent\runtime\state\execution-emergency-stop.json` reads `active: true`, `generation: 16`, `scope: execution_runtime`, with **16 open incidents whose `origin_database` values are all throwaway paths** (pytest temp directories and audit scratch databases), the most recent stamped 2026-08-28. `execution_service` consults this file for every database, so the real operational app would refuse every proposal, **risk-reducing sells included**, until an explicit clear naming the exact incident ids and generation. Verified by reading the file directly, read-only. Deliberately **not cleared**: mutating operational runtime state is an owner action, not a reviewer action. Test suites run by any lane can latch it, so this recurs until the scoping in R-15 changes. |
| R-10 | P1 | OPEN - verified by this review | Read-only and reporting paths latch that machine-global stop. `assistant/storage.py:5876` `_activate_detected_broker_integrity_incident` calls `activate_runtime_emergency_stop` **before and outside** the `if not self.read_only:` guard, and its callers include `get_execution_budget_usage`, `database_integrity_check`, and `AssistantStore.__init__`, which `assistant/readiness.py` invokes as a report. One corrupt historical row therefore lets a readiness poll halt execution. Contradicts CLAUDE.md section 7 (registry status must not be a side effect of presentation) and section 9 (read-only commands leave execution tables unchanged). This is the mechanism behind R-09. |
| R-11 | P1 | OPEN - verified by this review | `_refuse_while_prior_dispatch_is_ambiguous` (`assistant/execution_service.py:427`, called unconditionally) refuses **any** new submission while an earlier dispatch is unresolved, with no branch on `side`, although its own docstring scopes the intent to "do not add account exposure". A timed-out BUY therefore blocks an approved risk-reducing SELL, and the raised `ProposalExecutionError` is converted to `BLOCKED`, so the sell proposal is consumed and must be regenerated and re-approved. |
| R-12 | P1 | OPEN - verified by this review | `get_execution_budget_usage` (`assistant/storage.py:5644`) now issues `SELECT * FROM broker_order_events` with no `WHERE` clause, re-hashing the entire event history on the readiness and pre-dispatch hot path that the deployed monitor polls every 30 seconds. Combined with R-10, a single bad historical row halts the machine. |
| R-13 | P1 | OPEN - reported, structurally confirmed | A skewed or missing broker `submitted_at` escalates to a global halt rather than a skip. `assistant/order_reconciler.py:588` routes `not integrity_ok` into `activate_reconciliation_halt` (persistent kill switch plus runtime-global stop); `assistant/temporal_integrity.py:14` sets a 5.0 second future-skew tolerance; the deployed `OrderMonitor` task polls every 30 seconds. A local clock a few seconds behind the broker can therefore halt all trading unattended, and also suppress stale-order cancellation, itself a risk-reducing action. The prior behavior skipped instead. Tolerance constants and the halt call verified; the end-to-end unattended scenario is not reproduced here. |
| R-14 | P1 | OPEN - reported, not independently reproduced | `held` and `calculated`, both normal in-lifecycle broker states still listed in `KNOWN_BROKER_ORDER_STATUSES` and `ACTIVE_BROKER_ORDER_STATUSES`, now project to `submission_unknown` (`assistant/order_lifecycle.py:45`), which feeds both the R-11 gate and the critical-unresolved set. One order going `held` would make readiness not-ready and block every later proposal. Reported to have no test coverage for either status. |
| R-15 | P1 | OPEN - reported, not independently reproduced | Two further fail-closed traps: a legacy `broker_order_events` row with a naive `event_at` is reported to make the database permanently unopenable read-write with no self-heal, and deterministic snapshot-integrity failures (negative cash, zero entry price, component disagreement) are reported to be retried as transient and then surfaced as "broker state did not stabilize", blocking all submission while naming the wrong cause. Also the scoping question behind R-09: the runtime stop is shared per OS user and ignores the database, so a per-database fault halts every database on the host. |
| R-18 | P1 | **OPEN - cross-lane isolation defeated** | The machine-global runtime execution stop couples the three supposedly isolated strategy lanes. Enumerating the open incident set shows two whose `origin_database` is the **analyst-revisions lane** (`...\codex_arv2_full_tmp\test_real_process_crash_mid_tr0\assistant.db` and `...\trading_agent_analyst_revisions\.codex-test-tmp-counter-review\...\assistant.db`). One lane running its own test suite therefore latches an execution stop that halts every other lane and the operational app. The parallel-workflow contract requires per-lane checkouts precisely so lanes cannot affect one another; that guarantee holds for the filesystem and for git, but not for this per-user runtime file, which ignores its `database` argument. Directly related to R-09 and R-15, and recorded separately because it is a program-level isolation defect rather than only an execution-safety one. Verified by enumerating the live incident set, read-only. |
| R-19 | P3 | OPEN | The Windows verifier and installer-preview tests hard-code a 30-second `subprocess.run` timeout for each PowerShell child process, which makes them load-fragile. On a busy host the identical tree produced 6 `subprocess.TimeoutExpired` failures in `tests/test_ml_evidence_operations.py` and 24 timeout traces overall, and the same file then passed 49 of 49 (1 skipped) in 4m08s once the host was idle. The failure mode is indistinguishable at a glance from a real regression, and it appears exactly when a reviewer runs other work in parallel. A load-independent budget, or a documented serial-execution requirement for this file, would remove the ambiguity. |
| R-16 | P2 | OPEN | `e770b05` changed a zero-share position row from a refusal to a silent `continue` in `assistant/portfolio_snapshot.py`, with no record. A broker feed reporting zero shares for a genuinely held position makes it vanish from the snapshot, so a risk-reducing sell for that ticker reads as not held. Violates CLAUDE.md section 8 (no silent row dropping). The strict Alpaca path is unaffected. |
| R-17 | P2 | OPEN | Two characterization tests are now vacuous: policy revalidation moved earlier, so they fail before any reservation is made and `assert state["reservations"] == []` is trivially true. Deleting the reservation release from the submit kernel reportedly leaves the suite green, although that test was originally created by mutation testing against exactly that deletion. |

Deliberately **not** corrected: R-01, R-03 through R-08, and R-09 through R-19 are owner-level
design decisions, unverified against a live broker, or outside a reviewer
surgical-correction mandate on shared code synchronized from `main`.
Correcting them on this lane would also diverge shared execution semantics
from `main` and from the other two lanes.

### 6.4 Validation performed by this review

All runs on this exact lane tree in the isolated worktree.

- Complete suite at `8a65e3c` before correction: **1 failed, 5,222 passed,
  2 skipped, 25 warnings in 1,746.72s (29m07s)**; the failure is R-02. This
  contradicts the section 5 claim of 5,223 passed and zero failed on that
  tree, and the later 5,224 passed claim. Those runs used a non-Store
  interpreter, so the claim is environment-dependent rather than wrong in
  intent.
- `tests/test_ml_evidence_operations.py` after correction: **49 passed,
  1 skipped in 295.56s**; the single skip is the R-02 guard, reported with its
  explicit reason.
- Import-boundary, entry-point classification, and active-document
  consistency: **98 passed in 38.24s**.
- Execution-gate precision and authorization plus execution characterization:
  **76 passed in 28.18s**.
- Dispatch-fence and cancel-all suites: **89 passed, 1 skipped**; the skip is
  the correctly gated POSIX fork test.
- Broker-binding suites (authorization binding, atomic reconciliation anomaly,
  broker order contract, coherent broker snapshot, alpaca broker):
  **263 passed, 1 skipped**.
- `compileall` exit 0; PowerShell parser 0 errors on both changed scripts;
  `git diff --check` clean.

**Mutations run, so a fix is provably load-bearing:**

- `f943bfc` reverted to per-position rounded aggregation caused
  `test_snapshot_builder_aggregates_exact_values_before_display_rounding` to
  fail with a total_equity display value of 100.01 disagreeing with exact
  evidence of 100, reproducing the claimed defect exactly. The file was
  restored clean.
- The R-02 guard predicate was boundary-tested: a real non-empty interpreter
  does **not** skip, so coverage is preserved on a provisioned host; a
  zero-byte file skips; and a **missing** interpreter does not skip, so an
  absent interpreter still fails loudly instead of being masked.

### 6.4a Validation provenance for this push

Stated precisely, so that no claim is broader than what was actually run.

The complete suite was run three times on this lane:

1. Tree at `2eb3f5d`: **5,223 passed, 3 skipped, 0 failed, 25 warnings in
   2,262.86s (37m43s)**.
2. Tree at `f5f3ec5`, run while other review work loaded the host:
   **6 failed, 5,217 passed, 3 skipped in 3,411.17s (56m51s)**. All six
   failures were `subprocess.TimeoutExpired` on PowerShell child processes in
   `tests/test_ml_evidence_operations.py`, against a code tree byte-identical
   to run 1. Re-running that file alone on an idle host gave **49 passed,
   1 skipped in 248.76s**, so the failures were host contention, not a
   regression. This is recorded as R-19 rather than dismissed, and the red
   run is reported here rather than omitted.
3. Complete code tree at `58bf2f8`, run with no competing load:
   **5,223 passed, 3 skipped, 0 failed, 25 warnings in 2,192.66s (36m32s)**.
   `compileall` exit 0 and `git diff --check` clean on that same tree.

The pushed tip is one commit beyond run 3. That commit adds this record text
only and changes no code; it was revalidated with the 63-check
active-document consistency suite and `git diff --check`. No claim here rests
on a run that predates the code it describes.

The three skips are the two pre-existing platform skips plus the R-02 guard
added by this review.

### 6.5 Residual gates and next authorized step

Codex counter-reviews every Claude commit in this range, then may begin
IB-0/IB-1 in the same combined push. R-01 requires an explicit owner decision
before it can be closed: either a preregistered tolerance that distinguishes a
material policy-input change from a price mark ticking, or an explicit
risk-reducing-sell path that does not require a byte-identical recapture.

The storage, calendar, and temporal-integrity audit that was in progress when
this section was first drafted has since completed; its findings are R-09
through R-17 above and the `9406a34` disposition was corrected from accepted
to defect-found accordingly. Of the seven P1 issues, four (R-09 to R-12) were
independently verified by this reviewer against the running system and the
code paths; R-13 was structurally confirmed at its constants and call site;
R-14 and R-15 are recorded as reported and still need independent
reproduction during counter-review.

**R-09 needs owner attention before the next operational run**, independently
of this lane: the host emergency stop is latched active by throwaway test
databases and would refuse live paper proposals, including risk-reducing
sells. It was deliberately left untouched. No SEC crawl, outcome join, ETF construction, QuantConnect job, or
broker action is authorized by this review.
