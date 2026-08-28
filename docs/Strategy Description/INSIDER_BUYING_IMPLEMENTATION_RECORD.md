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
| 2026-08-28 | Claude review | `b4ba4b2` -> this review snapshot | Independent review of the owner-authorized shared remediation synchronization (`a4f58e6..b4ba4b2`, 16 commits) | Verified provenance by stable patch ID (12 of 13 synchronized commits patch-identical to their merged main-line counterparts; the single divergence correctly omits the analyst-only entry-point registration), confirmed the frozen-file freeze held, and reviewed every commit for fail-open, atomicity, money-type, and test-weakening defects. Corrected one confirmed defect and escalated one open P1. Full dispositions and the P0-P3 ledger are in section 6. | Complete suite at `8a65e3c`: 1 failed, 5,222 passed, 2 skipped in 29m07s (the failure is R-02, contradicting the recorded zero-failure claim on this host). After correction: affected file 49 passed, 1 skipped; import-boundary/entry-point/active-document 98 passed; execution-gate and characterization 76 passed; dispatch-fence and cancel-all 89 passed, 1 skipped; broker-binding suites 263 passed, 1 skipped; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean. Two mutations run and reverted cleanly. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or scheduler access; **0 research looks**. | R-01 (P1, OPEN): strict snapshot coherence refuses submission on any price tick with no risk-reducing-sell exemption, conflicting with the CLAUDE.md section 5 exception; escalated for an owner decision rather than corrected on a lane branch. R-02 (P2) fixed in `1c1d943`. R-03 to R-08 recorded open for counter-review. | Codex counter-reviews every Claude commit in this range, then may begin IB-0/IB-1 in one combined push. R-01 needs an explicit owner decision before it can be closed. IB-0/IB-1 remains unstarted. |

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
| `9406a34` | Harden shared trading safety boundaries | Accepted on the checks completed; a line-level audit of storage and calendar internals is carried as a stated residual gate |
| `800c689` | Register shared research input boundaries | Accepted, lane-correct divergence verified |
| `52518d6` | Reconcile three-strategy review workflow | Accepted |
| `e770b05` | fix: close shared remediation regressions | Accepted after correction (**R-02**, corrected here) |
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

Deliberately **not** corrected: R-01 and R-03 through R-08 are owner-level
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

### 6.5 Residual gates and next authorized step

Codex counter-reviews every Claude commit in this range, then may begin
IB-0/IB-1 in the same combined push. R-01 requires an explicit owner decision
before it can be closed: either a preregistered tolerance that distinguishes a
material policy-input change from a price mark ticking, or an explicit
risk-reducing-sell path that does not require a byte-identical recapture.

Stated untested areas: the deep internals of `assistant/storage.py` migrations
and the new `data/exchange_calendar.py` and `assistant/temporal_integrity.py`
modules were exercised only through the suites above, not line-audited by this
review. No SEC crawl, outcome join, ETF construction, QuantConnect job, or
broker action is authorized by this review.
