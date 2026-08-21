# Independent review of epoch broker-activity ingestion

Date: 2026-08-10

Reviewer: Codex

Status: **accepted after correction — 0 P0, 0 P1, 0 P2, and 0 P3 open**

Review branch: `codex/review-epoch-activity-ingestion-20260810`

## 1. Exact scope and commit dispositions

The review branch was created from Claude's exact submitted head `8f922a9`.
The base was merged `main` / `origin/main` at `e871f2f`. The ordered range and
cumulative tree were reviewed; no commit was skipped.

| Commit | Disposition | Review result |
|---|---|---|
| `f10b47d` — Ingest broker non-trade activities so CAT fees stop stalling the epoch | **Accepted after correction** | The diagnosis, bounded REST pagination, idempotent fee posting, FILL exclusion, and fail-closed handling of unsupported post-bootstrap activity are sound. Three material defects and one minor boundary defect remained: the parser required fields outside Alpaca's published non-trade schema; a 30-day overlap let pre-bootstrap dividends block reconciliation; activity failure suppressed backup and health; and `page_size` coerced bools, floats, and strings. Corrected in `a8174b9`. |
| `8f922a9` — Record the epoch-stall diagnosis and activity-ingestion fix in the handoff | **Accepted after correction** | It accurately records the observed $0.03 CAT-fee mismatch and fail-closed evidence stall. Its API claims, manual-recovery statement, severity, deployment wording, and next-step sequence were inaccurate or stale. Corrected in the documentation commit containing this report. |

Review correction `a8174b9` was local-only when this report was written;
after counter-review acceptance the branch was pushed to
`origin/codex/review-epoch-activity-ingestion-20260810` under the owner's
standing git-management grant (see §6; still not merged or deployed).
No broker call, database mutation, scheduler
change, epoch action, deployment, or policy change was performed by review.

## 2. Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| EPOCHR-001 | P2 | Closed in `a8174b9` | `f10b47d` | `assistant/portfolio_ledger.py:757-896` | Every FEE required `created_at` and `status="executed"`, although Alpaca's published non-trade activity schema promises neither field. A schema-conforming fee could therefore be rejected and leave the epoch permanently stalled. | Alpaca's OpenAPI `NonTradeActivities` contains `activity_type`, `id`, `date`, `net_amount`, and optional security fields, but no `created_at` or `status`. The new minimal-shape test failed red on the submitted tree. | A broker adapter must accept the provider's documented success shape while retaining a fail-closed time boundary. | Missing status is accepted; an explicitly present non-executed status still refuses. Missing `created_at` is accepted only when the caller proves the request used an exclusive `after` bound exactly equal to the ledger bootstrap. The journal uses a deterministic one-microsecond lower-bound surrogate and never guesses from the opaque activity ID. | `test_sync_broker_activities_accepts_documented_minimal_fee_shape` and the mismatched-bound guard pass; malformed timestamps and statuses still refuse. |
| EPOCHR-002 | P2 | Closed in `a8174b9` | `f10b47d` | `scripts/run_personal_assistant.py:1408`; `assistant/portfolio_ledger.py:783` | The fetch started 30 days before bootstrap, and the ledger rejected unknown types before applying its bootstrap cutoff. Any dividend, interest, or transfer already included in opening cash could block the first reconciliation forever. | Alpaca documents `after` as activities created after the supplied timestamp. The pre-bootstrap DIV regression failed red, as did the test expecting the query bound to equal bootstrap. | Opening-snapshot activity must not be replayed or treated as a new unsupported event. Otherwise a clean deployment may remain unusable despite correct opening books. | The query now starts exactly at bootstrap. The ledger also determines/skips every pre-bootstrap non-trade row before type-specific handling as a defensive local boundary. | `test_sync_broker_activities_skips_all_pre_bootstrap_nontrade_types` and `test_sync_broker_activities_from_alpaca_windows_the_fetch` pass. |
| EPOCHR-003 | P2 | Closed in `a8174b9` | `f10b47d` | `scripts/run_personal_assistant.py:1886-1949` | In `operations-cycle`, an expected fail-closed unsupported activity aborted before snapshot reconciliation, verified backup, and operational health. A dividend could therefore remove the recovery and diagnosis work most needed during the failure. | A call-order regression failed red: submitted code called orders, fills, activities, alert and skipped snapshot, reconciliation, backup, and health. | Unsupported financial activity must still fail the cycle, but one failed stage must not suppress independent recovery controls. | The cycle retains the activity exception, runs snapshot reconciliation, backup, and health, then re-raises the original error so the same critical alert/nonzero result remains. `paper-observation` still fails immediately and writes no evidence. | `test_operations_cycle_preserves_backup_and_health_after_activity_failure` passes and proves the original exception is preserved. |
| EPOCHR-004 | P2 | Closed in this documentation commit | `8f922a9` | `docs/SESSION_HANDOFF.md`; `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md` | The handoff said deploy, then close/start the epoch, and implied deployment itself closes epoch-002. It also put first reconciliation after the new epoch start. Deployment does not close stored epoch state, and starting before clean reconciliation risks immediately stalling epoch-003. | `docs/operations/OPERATIONS_RUNBOOK.md` requires reconcile before epoch start; epoch lineage is explicit durable state. | The operational sequence must preserve lineage and prove clean books before beginning a new immutable evidence window. | The canonical sequence is now: disable tasks; close epoch-002 on its frozen runtime; deploy the reviewed merge; run `ledger-reconcile` and confirm the CAT fees self-heal/match; run readiness; start epoch-003; execute all five drills; re-enable and verify tasks. | Active documents and runbook now state the same ordering. No deployment was attempted. |
| EPOCHR-005 | P3 | Closed in `a8174b9` | `f10b47d` | `execution/alpaca_broker.py:429-481` | `int(page_size)` silently accepted `True`, `1.5`, and `"2"`; the float was truncated. | Three parameterized cases all reached the HTTP path on the submitted tree instead of rejecting at the boundary. | Silent coercion makes pagination behavior caller-dependent and weakens a public adapter boundary. | Require a real non-bool integer in the documented 1..100 range and use it without repeated coercion. | Three red-before-green parameter cases pass. |
| EPOCHR-006 | P3 | Closed in `a8174b9` and this documentation commit | `f10b47d`, `8f922a9` | `assistant/portfolio_ledger.py`; activity tests and handoff | Comments said an operator could manually journal an unsupported dividend and clear the activity error. The sync never checks manual postings and would reject the same broker row on every run. | Source control flow rejects every unsupported post-bootstrap type before consulting journal transactions. | A false recovery instruction can waste an outage window and encourages compensating entries that do not acknowledge the original broker activity safely. | Documentation now states that a deliberate supported handler and reviewed deployment are required. No loose manual-acknowledgement bypass was added. | Source comments, tests, review report, action plan, and handoff use the same recovery rule. |
| EPOCHR-007 | P3 | Closed in this documentation commit | `8f922a9` | active project documents | AP-6 was labelled P1 despite no unsafe execution, duplicate order, broken atomicity, false broker outcome, or severe security impact. The handoff and operational facts also called epoch-002 both stalled and accumulating/continuing daily. | Repository severity rules classify incorrect durable state or missing recovery as P2. The measured state is one captured session and repeated failed observations since 2026-08-07. | Severity inflation and contradictory epoch status obscure the real next action. | AP-6 is P2. Every active document now calls epoch-002 **active in storage but operationally stalled**, with no mandate evidence accumulating. | Documentation consistency tests are run after edits; stale phrases were searched explicitly. |

Final ledger: **0 P0 / 0 P1 / 0 P2 / 0 P3 open**.

## 3. Provider-contract evidence

The official [Retrieve Account Activities reference](https://docs.alpaca.markets/us/v1.4.2/reference/getaccountactivities-2)
defines `/v2/account/activities`, says `after` returns activities created
after the supplied timestamp, constrains `page_size` to 1..100, and defines
`page_token` as the last activity ID. Alpaca's official
[Trading API OpenAPI](https://raw.githubusercontent.com/alpacahq/alpaca-docs/master/oas/trading/openapi.yaml)
defines the non-trade response without `created_at`, `status`, `description`,
or `currency`; it also identifies `FEE` as USD-denominated. The correction
therefore does not require undocumented fields, does not require a redundant
currency field, and does not infer timestamp semantics from the activity ID.

This is contract validation, not a live provider test. The operational host's
previous read-only diagnosis observed Alpaca extensions such as `created_at`,
but review did not repeat that call or inspect credentials/account data.

## 4. Validation

Environment: Windows, Python 3.13.14, Streamlit 1.60.0.

- Baseline submitted focused set: 100 passed in 14.98s (recorded by Claude).
- Review regressions before correction: 7 failed as intended in 17.02s
  (three strict-type cases plus provider shape, pre-bootstrap ordering, query
  window, and operations recovery).
- Corrected affected modules: **107 passed** in 13.02s.
- Full collected suite: **3334 passed, 0 failed, 0 skipped**, run in four
  deterministic file batches because the desktop command channel timed out
  on a single long-lived run: 1045 in 124.41s; 1025 in 214.14s; 990 in
  131.50s; 274 in 215.19s. Warnings: 25 existing dependency deprecations
  (one websockets, 24 joblib/NumPy).
- The first whole-suite attempts timed out at 120s and 600s without a test
  failure; a verbose diagnostic encountered an output-pipe flush error at its
  external timeout. Those attempts are not counted as passes. The four batch
  selections cover the exact 3334-test collection once by test-file initial.
- Repository-prescribed `compileall`: clean.
- `git diff --check`: clean apart from expected LF-to-CRLF checkout notices.
- Active-document consistency: **8 passed** in 0.18s; broader documentation
  consumers: **98 passed** in 4.17s.
- Narrow non-printing secret-shape scan of the README/docs diff: clean.

## 5. Assessment and operational boundary

Claude's overall quality for this round is **6/10**. The read-only diagnosis
was excellent: it reconciled all fills, isolated three post-bootstrap CAT fees
to the cent, preserved the strict cash tolerance, and chose the correct
idempotent/fail-closed architecture instead of hiding the mismatch. The
implementation also had good pagination bounds and useful targeted tests.
However, three material behaviors made the submitted tree unsafe to deploy as
the epoch recovery: incompatibility with the published provider shape,
pre-bootstrap activity poisoning, and loss of backup/health work on the very
failure path the feature introduces. The deployment instructions were also in
the wrong order. These are substantive review misses, not cosmetic cleanup,
but none was a P0/P1 trading-authority defect and all are now closed.

The accepted code does one narrow thing: it imports broker fees into the
append-only journal so reconciliation can become true again. Unsupported
post-bootstrap dividends, interest, transfers, and corporate actions still
fail closed and require a separately reviewed handler. The correction has not
been merged, pushed, or deployed. `paper-epoch-002` remains active in durable
state but stalled on the separate operational host at frozen commit `9a91498`.

---

## 6. Counter-review (Claude, 2026-08-10) — accepted, all findings verified

Counter-review verified every finding against the code and, where the finding
rested on a provider-behavior claim, against the live paper endpoint
read-only. Verdict: **Codex's review is accepted in full. All seven findings
are confirmed; none is a false alarm. No correction to the correction is
required.** Two watch items are recorded below; neither blocks merge.

### Per-finding verification

| ID | Counter-review verdict | Evidence |
|---|---|---|
| EPOCHR-001 | **Confirmed.** | The live account does send `created_at`/`status` today (re-measured 2026-08-10), so the defect was contract-conformance, not observed breakage — but the published schema promises neither field, and the correction rightly keeps preferring `created_at` when present. |
| EPOCHR-002 | **Confirmed, and strengthened with live evidence.** | (a) The full activity history contains a `JNLC +$100,000` funding journal created 2026-07-26 — inside the submitted 30-day window. Because the submitted code checked unknown-type before the bootstrap cutoff, the first production run would have refused on the account's own funding deposit: the submitted fix was dead on arrival. (b) The load-bearing claim behind the corrected exact-bootstrap window was verified live: `after=2026-08-05T18:22:58Z` returned exactly the three post-bootstrap CAT fees — including the 08-05-dated fee created 08-06T00:06Z — and excluded everything earlier, proving `after` is an exclusive activity-creation-time bound on the real endpoint, not a date-label filter. Codex validated this against documentation only; the live measurement closes that gap. |
| EPOCHR-003 | **Confirmed.** | Code reading of the submitted tree agrees the outer handler skipped snapshot/backup/health; the corrected flow preserves and re-raises the original exception after them. |
| EPOCHR-004 | **Confirmed.** | Epoch lineage is durable database state; deploying a new commit breaks lineage validation but does not close the epoch. The runbook sequence (disable tasks → close → deploy → reconcile matched → readiness → start → drills → re-enable) is correct and consistent across the runbook, action plan, and handoff. |
| EPOCHR-005 | **Confirmed.** | Straightforward boundary tightening. |
| EPOCHR-006 | **Confirmed.** | The submitted comment's manual-`ledger-fee` recovery instruction was false: the sync re-reads the same broker rows every run and never consults manual postings, so the block would persist. No bypass was added — correct. |
| EPOCHR-007 | **Accepted.** | P2 matches the repository severity definitions (incorrect durable state / missing recovery; no unsafe execution or broken atomicity). |

### Reverse-mutation verification of the correction's guards

Each of the four corrected behaviors was reverse-mutated on the corrected
tree; each mutation turned exactly the intended regression test red, and the
real code was restored byte-identical (backup copy) and re-verified green
(107 focused tests):

1. Type-check moved back before the cutoff check →
   `test_sync_broker_activities_skips_all_pre_bootstrap_nontrade_types` failed.
2. Surrogate posting time changed from `created_after + 1µs` to
   `created_after` →
   `test_sync_broker_activities_accepts_documented_minimal_fee_shape` failed.
3. `operations-cycle` made to propagate the activity failure immediately →
   `test_operations_cycle_preserves_backup_and_health_after_activity_failure`
   failed.
4. `page_size` reverted to silent `int()` coercion → all three strict-type
   parameter cases failed.

### Watch items (P3, recorded not fixed)

- **CR-W1 — surrogate/created_at content conflict on provider transition.**
  A fee journaled via the bootstrap+1µs surrogate (minimal schema) whose row
  later gains a `created_at` from the provider would rebuild with a different
  `occurred_at` under the same external id, raising
  `JournalTransactionConflictError` and blocking loudly. Fail-closed in the
  right direction; requires operator investigation if it ever fires. No code
  change: the alternative (accepting changed content silently) is worse.
- **CR-W2 — a future paper-cash top-up stalls the epoch by design.** A
  post-bootstrap `JNLC`/`CSD` deposit is an unsupported type and will fail
  closed until a reviewed handler maps it to the existing
  `record_cash_transfer`. This is the intended behavior, recorded so the
  operator recognizes it; the fix is a small, separately reviewed extension.

### Counter-review validation

Single uninterrupted full-suite run on the exact corrected tree (in addition
to Codex's four deterministic batches): see the session handoff for the
recorded count. Focused modules 107 passed; `compileall` clean;
`git diff --check` clean.
