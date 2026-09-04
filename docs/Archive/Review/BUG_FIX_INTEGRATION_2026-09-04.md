# Cross-lane bug-fix integration — 2026-09-04

Prepared by Claude (the dedicated Review lane session) under the owner's
2026-09-04 direction:

> In each lane's review steps, it was found that there are some app/project-
> related issues. Most of them are P2–P4 findings. In each lane session, I
> asked both you and Codex to document the findings, but not fix them yet.
> [...] 1) Scan each lane's lane-specific documentation, look for the
> documented issues. 2) When issues are found, try to test under MAIN branch
> (or branched off from Main). If confirmed, fix the issue in both Main branch
> and Feature branch. 3) Document the fix in both main and feature branches.
> 4) Push. The branch off from main should be named
> `Feature-bug-fix-integration-2026-09-04`. I will do the PR merge myself.

This is the "separate owner decision" that the frozen-file rule in
`docs/Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md` section 2
requires; that file carries the matching bounded-exception paragraph. It is a
bug-fix integration only: it accepts no lane milestone and grants no
provider, outcome, look, QuantConnect, broker, operator-database, deployment,
paper, live, or trading authority.

## 1. Identity

| Item | Value |
|---|---|
| Base | `main` at `aefa0ec` (PR #326 merge) |
| Integration branch | `Feature-bug-fix-integration-2026-09-04` |
| Code/test commits | `7f99f303d0b6f5a2a65aa5b5b49f9c52256716d8` (fix set) and `3114a1530f0afa400eb200e79ff218c174657e69` (clock pass-through in the notification cycle; guard decoder) |
| Lane records scanned (branch tips) | Analyst `6a157e9`, Insider `c7b9f2f`, Short interest `edc49f8`, Target-price `dff9b11` |
| Lane application | The identical code commits are cherry-picked onto each of the four `codex/strategy-*` branches; each lane record's pointer section names its own resulting hashes. |
| Merge | Owner performs the PR merges. |

## 2. Method

1. Each lane's implementation record was read in full at its branch tip and
   every item recorded as out-of-lane / documented-but-not-fixed was extracted
   with its recorded severity, evidence, and line references (nothing was
   re-rated). The four lanes independently documented the same shared defects
   several times; section 4 consolidates them.
2. Every candidate was tested against `main` at `aefa0ec` first, in an
   isolated detached worktree, never in a lane checkout. Only reproduced
   defects were fixed. Each fix has a regression test shown red before the
   fix or red under a deliberate mutation of the fix, with the real code
   restored afterwards.
3. Fixes are confined to shared application, test-infrastructure, and
   repository-tooling files. No file under `research/<lane>/`,
   `tests/<lane>/`, or any lane blueprint/record was changed, and no
   lane-owned `.gitattributes` was altered.
4. Items that are research-contract decisions, execution-semantics design
   questions, environment notes, or already queued under the owner-gated
   `docs/Plan/POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md`
   were deliberately left unfixed; section 5 gives the reason for each.

## 3. Fixes (each confirmed on `main` before the change)

| Fix | Lane items consolidated | Confirmed on `main` | Change | Regression / mutation evidence |
|---|---|---|---|---|
| **F-1 Sleeve-report clock seam** | TPR-OOL-009, SI-OOL-002, Insider IB0H-OOL01, Analyst ARV2WL-D11 | Full suite on `aefa0ec`: **4 failed** — `tests/test_sleeve_report.py` (`test_default_gain_review_is_fifty_percent_and_long_term_gated`, `test_every_lot_row_carries_the_tax_mechanism_fields`, `test_report_carries_no_action_shaped_field`) plus `tests/test_sleeve_notifications.py::test_awaiting_long_term_notifies_once_and_upgrades_to_gain_review`, which no lane had recorded. Fixtures pin `_NOW` (2026-08-07 / 2026-08-09) but `evaluate_sleeves` classified lot age against the wall clock, so lots crossed the one-year boundary on 2026-09-02. | `assistant/sleeve_report.py`: `evaluate_sleeves(..., now: datetime \| None = None)` threads the instant through `_growth_positions` to `unrealized_by_lot(..., now=now)`. `assistant/sleeve_notifications.py::run_sleeve_notification_cycle` now passes its own `at` as `now`, so lot terms, `evaluated_at`, and price freshness share one clock. CLI/UI callers pass nothing and keep the live clock. Both test modules pin `now=_NOW`; new regressions `test_evaluate_sleeves_classifies_lot_age_at_the_injected_clock_not_wall_time` and `test_cycle_classifies_lot_age_at_its_own_clock_not_wall_time` (lot at 364 days: awaiting at the clock, gain review three days later). | Both files green after the fix. Mutations: `now=None` into `_growth_positions` → `1 failed`; drop `now=at` in the cycle → `1 failed`. |
| **F-2 Runtime-stop leak from the crash test** | Insider R-09, R-18, R-20, R-22 (root cause); SI section 6.5 fence coverage note | The REAL `%LOCALAPPDATA%\trading_agent\runtime\state\execution-emergency-stop.json` on this host is `active`, generation 42, with **42 open incidents whose every `origin_database` is a pytest/temp database**. `tests/test_atomic_reconciliation_anomaly.py::test_real_process_crash_mid_transaction_leaves_no_anomaly_without_halt` spawns a child interpreter that starts from the real runtime root, and its containment write latches the machine-global stop; the operational application on this host would refuse every proposal, risk-reducing sells included. | The child script sets `assistant.dispatch_fence._RUNTIME_FENCE_ROOT` to a directory under `tmp_path` before importing `assistant.storage`. | The real file stayed at generation 42 / 42 incidents through every run of the fixed test and both full-suite runs; no incident with this session's base temp appeared. |
| **F-3 Leak guard in `tests/conftest.py`** | Same as F-2 (prevents recurrence from any future test) | n/a (new control) | The autouse `_isolate_execution_runtime_authority` fixture's teardown calls `_assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)`, which reads the real stop file and fails the test if any open incident's `origin_database` lies under this session's pytest base temp. It never mutates operator state and ignores incidents from other sessions, so concurrent suites cannot trip it. It decodes with a `JSONDecoder.decode` bound at import, because it runs in the teardown of tests that legitimately patch `json.loads` with a must-not-run sentinel (the insider SEC nesting-cap tests errored at teardown in the first full run before this was bound). | `tests/test_runtime_stop_leak_guard.py` (3 tests): fires on a crafted leak, silent for a foreign origin, silent without a file. The guard also fired end-to-end at teardown on the crafted leak before the test removed it. |
| **F-4 Shared exact-byte EOL attributes** | TPR-OOL-008, TPR-OOL-010, SI-SYNC-001 (root-cause class), Insider #27, Analyst #4 | `git check-attr text eol -- research/ml_specs/*.json research/__init__.py` resolved `unspecified` on `aefa0ec`; with `core.autocrlf=true` these check out CRLF and no longer match their committed blobs or recorded digests while `git status` stays clean through the stat cache. | Root `.gitattributes` adds `research/ml_specs/*.json -text` and `research/__init__.py text eol=lf` (the latter is byte-compared by the TPR reviewed-algorithm anchor). Lane-owned attribute files untouched. | `tests/test_shared_research_eol_attributes.py` (4 tests, `git check-attr`-based so it is deterministic on stale checkouts). Mutation (strip the new lines): `3 failed, 1 passed`. |
| **F-5 Briefing smoke isolation** | TPR-OOL-005 | Observed once by Codex as a 180 s timeout with yfinance `OperationalError('unable to open database file')`; not reproducible on demand (host-load flake). The fixture patched one recorded-bar seam only; Briefing still reached `fetch_historical` on `data.market_data`, `assistant.context_builder`, `assistant.macro_context`, and the UI module. | `tests/test_ui_pages_smoke.py::_isolated_app_environment` stubs `fetch_historical` on every importing module so the page cannot reach the network or the yfinance SQLite cache. | Briefing smoke passes under the hardened fixture; the failure mode is unreachable rather than merely rarer. |
| **F-6 Stale shared coordination documents** | TPR-OOL-002, TPR-OOL-007, Insider #30, TPR unnamed README "PDF governs" note | Verified by reading: `docs/Strategy Description/README.md` described a three-strategy program with Insider/Short-interest at "planning/baseline" and omitted the fourth lane; `docs/THREE_STRATEGY_PROJECT_DIRECTION.md` still said the TPR-0A candidate's "next action is one exact-snapshot push" although PR #324 merged it. | README rewritten for four lanes with a directory-index posture (no per-round milestone identifiers); DIRECTION gains a dated status paragraph that corrects the stale sentence without altering any allocation or gate; the parallel-workflow file gains the 2026-09-04 exception paragraph. | `tests/test_active_document_consistency.py`: 69 passed. |
| **F-7 Overclaiming test name** | Insider R-17 | `test_an_unsupported_order_type_blocks_and_releases_its_reservation` asserts an empty reservation set, but its refusal happens during policy revalidation before any reservation exists, so the assertion cannot protect the release kernel. The other test the finding named (`test_early_refusals_never_create_a_reservation`) had already been renamed on `main`. The post-reservation release path is behaviorally frozen by `test_pre_submit_telemetry_failure_releases_budget_without_broker_contact` (takes a real reservation, observes `submission_failed` with none left). | Renamed to `test_an_unsupported_order_type_fails_policy_revalidation_before_reserving`; docstring names the test that owns the release path; no assertion removed. | 3 characterization tests pass; no document referenced the old name. |

`ARV2-UNRELATED-001` (the Target-price test
`tests/target_price_revisions/test_preregistration.py::test_self_declared_review_and_registry_substitution_refuse`,
recorded by the Analyst lane as asserting a stale message) was also tested on
`main` at `aefa0ec`. It is **not** a stale message and nothing in that lane
fixed it (the file is unchanged since `bb8dfb6`): the outcome depends only on
where pytest's `tmp_path` lives. With an external `--basetemp` it passes
(`1 passed`); with a repository-local `--basetemp` — the layout Codex's
sandbox uses — `tmp_path` sits inside the Git worktree, the loader correctly
reaches its "reviewed spec and registry must be committed and clean" refusal
instead of the intended "not in a Git repository" refusal, and the regex fails
(`1 failed`, reproduced here). This is the same mechanism the Short-interest
lane recorded as `SI-OOL-003`. The test is lane-owned, so it is routed to the
Target-price lane rather than edited here (section 5.1).

## 4. Consolidation map

| Shared defect | Reported by |
|---|---|
| Sleeve-report wall-clock mismatch | TPR-OOL-009, SI-OOL-002, IB0H-OOL01, ARV2WL-D11 (+ the unrecorded `test_sleeve_notifications` instance) |
| Machine-global runtime stop latched by throwaway test databases | Insider R-09/R-18/R-20/R-22 (SI section 6.5 notes the fence deep-dive gap) |
| Missing EOL attributes for shared exact-byte research files | TPR-OOL-008/-010, SI-SYNC-001, Insider #27, Analyst #4 |
| Stale lane README / direction pointer | TPR-OOL-002/-007, Insider #30 |
| Briefing smoke not isolated | TPR-OOL-005 |

## 5. Items examined and deliberately not fixed

Dispositions: **ALREADY-FIXED** (closed on `main` before this work),
**NOT-REPRODUCED**, **OWNER-DECISION** (a research-contract, coordination, or
operational-state decision that is not a code defect this session may
settle), **GATED-BY-PLAN** (owned by the queued
`POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md` plan or the
same execution-semantics review the owner has not started), **DESIGN**
(deliberate, documented behavior; changing it is a contract change, not a bug
fix), **INTEGRATION-ITEM** (belongs to the later four-lane integration
milestone), **ENVIRONMENT** (host/harness observation, no repository change).

### 5.1 Target-price lane

| ID | Sev | Disposition | Reason |
|---|---|---|---|
| TPR-OOL-001 / -001-R1 / TPR-CR1-001 | P2 | ALREADY-FIXED | Root `*.pdf binary` landed under the 2026-08-30 owner coordination; re-verified by `test_root_gitattributes_keeps_pdfs_binary`. |
| TPR-OOL-006 / TPR-CR2-002 | P2 | OWNER-DECISION | Sibling multiplicity re-freeze (`1/60` → `1/80`, three-lane → four-family) is a preregistration-contract change inside each lane's frozen research artifacts; the owner's 2026-08-30 directive routes it through each lane's own review/counter-review, not a shared fix. |
| TPR-OOL-003 / -004 | P2 | OWNER-DECISION | Analyst lane's `json.loads` duplicate-key tolerance and `three_lane_selection_correction=3` are that lane's content-addressed authority artifacts; editing them from outside changes frozen contract bytes. Routed to the Analyst lane. |
| TPR-CR2-004 (deferred half) | P3 | DESIGN | A phrase-level "awaits push" guard for the shared reachability-guard family is a new heuristic control, not a reproduced defect; the concrete Action Plan row was already fixed in-lane. |
| TPR-CR4-002 | P2 | ALREADY-FIXED | Closed by owner direction (`git worktree list`). |
| Shared three-lane baseline test omits TPR | — | DESIGN | The fourth lane is bound by its own guards under `tests/target_price_revisions/`; duplicating them in the three-lane test adds no protection. |
| Process doc vs same-branch override | — | OWNER-DECISION | The parallel-workflow file already records the owner's same-branch override; the general process document remains the default for non-lane work. |
| Sandbox path length / `--basetemp` / mixed working-copy endings | — | ENVIRONMENT | Harness usage; no repository change. |
| `test_self_declared_review_and_registry_substitution_refuse` depends on `tmp_path` location (ARV2-UNRELATED-001 / SI-OOL-003) | P3 | routed to this lane | Lane-owned test under `tests/target_price_revisions/`; reproduced on `main` with a repository-local `--basetemp`. Suggested fix: make the not-in-a-repository case independent of the harness temp location (`GIT_CEILING_DIRECTORIES` or an explicit outside-repository directory). |

### 5.2 Short-interest lane

| ID | Sev | Disposition | Reason |
|---|---|---|---|
| SI-SYNC-001 (stale CRLF Analyst spec copies) | out-of-lane | ENVIRONMENT (root-cause class closed by F-4) | The Analyst specs already carry `-text`; stale working copies are machine-local and are restored from the committed `HEAD` blob (never `git add --renormalize` under `-text`, per SI-CCR11-001). F-4 closes the remaining unprotected shared files. |
| SI-OOL-003 (repo-local basetemp breaks a TPR test) | — | routed to the Target-price lane (same as ARV2-UNRELATED-001) | Reproduced here with a repository-local `--basetemp`. The refusal ordering is intended; the lane-owned test should stop depending on `tmp_path` being outside every Git worktree (e.g. `GIT_CEILING_DIRECTORIES`, or an explicit outside-repository directory). |
| PDF whitespace under `git diff --check` | — | ENVIRONMENT | Historical ranges predating `*.pdf binary`; the current tree is clean. |
| SI-CR2-005 (`ml.immutable_io` dependency) | P3 | INTEGRATION-ITEM | Same as Insider R-23 below. |
| Section 6.5 spot-check disclosure | — | not a defect | Coverage-boundary statement; the fence-leak mechanism itself is closed by F-2/F-3. |
| B1–B6 (mixed endings, host skip variance, dependency warnings, interpreter spread, interrupted run) | — | ENVIRONMENT | No repository change. |

### 5.3 Insider-buying lane

| ID | Sev | Disposition | Reason |
|---|---|---|---|
| R-01 (snapshot coherence has no risk-reducing-sell exemption) | P1 | GATED-BY-PLAN / OWNER-DECISION | Shared execution semantics; Codex marked it "OPEN / owner decision". Changing the pre-contact coherence rule for sells is an execution-policy change that needs the owner's explicit decision, not a bug fix. |
| R-02 | P2 | ALREADY-FIXED | Store-alias skip carried into `main`. |
| R-03 | P2 | not reproduced (provider-conditional) | Hypothesis about `pending_cancel` broker behavior; unverifiable without a live broker. |
| R-04 | P2 | withdrawn | False positive per Codex. |
| R-05, R-06, R-07, R-08 | P3 | GATED-BY-PLAN | Execution-path consistency items (sentinel account ids, dual alert fingerprints, permanent disagreement reported as transient, tautological identity check). Real but P3, in the reviewed broker/execution path; they belong to the queued full-project P2/P3 remediation rather than a cross-lane bug-fix pass. |
| R-09 / R-20 / R-22 (the debris itself) | P1 | OWNER-DECISION | The root cause is closed (F-2/F-3). The existing file with 42 test-origin incidents is operator runtime state on this host; the documented clear path requires clearing from each origin database, which no longer exists. Whether to delete or hand-edit the file is the owner's call — see section 6. |
| R-10 (read-only paths latch the runtime stop) | P1 | GATED-BY-PLAN / OWNER-DECISION | Fail-closed-on-integrity design; loosening it changes when a corrupt row halts execution. |
| R-11 | P1 | ALREADY-FIXED | `EXE-001` on `main` (`_refuse_while_prior_dispatch_is_ambiguous` exempts sells). |
| R-12 (unbounded event re-hash on the hot path) | P1 | GATED-BY-PLAN | Performance/design; latency never measured. |
| R-13 (clock skew escalates to halt) | P1 | GATED-BY-PLAN / OWNER-DECISION | Tolerance and halt policy are owner-level safety choices. |
| R-14 (`held`/`calculated` → `submission_unknown`) | P1 | DESIGN | `assistant/order_lifecycle.py` declares `_KNOWN_BUT_AMBIGUOUS = {"calculated", "held"}` on purpose; treating them as active is a contract change. |
| R-15 (three fail-closed traps) | P1 | GATED-BY-PLAN | Migration and runtime-stop design. |
| R-16 (non-strict builder drops zero-share rows) | P2 | OWNER-DECISION | Introduced by reviewed remediation `e770b05` for the read-only builder; the strict execution builder still refuses. Restoring the refusal in the read-only path changes UI/report behavior on real accounts. |
| R-17 | P2 | **FIXED (F-7)** | See section 3. |
| R-18 (per-OS-user stop couples lanes) | P1 | root cause FIXED (F-2/F-3); namespace DESIGN | The runtime stop is deliberately database-independent; the leak from tests is closed. |
| R-19, IB01-R05 | P3 | ENVIRONMENT | Load-fragile subprocess timeouts; not reproducible on an idle host. |
| R-23, IB1B-R11/IB1C-R16/IB1D-CR06(A), IB1H-R02 | P3 | INTEGRATION-ITEM | Relocating `ml.immutable_io` to a neutral module and consolidating the lanes' duplicated immutable-I/O helpers is the four-lane integration milestone's work (SEP-3 remains frozen). |
| IB0H-OOL01 | — | **FIXED (F-1)** | |
| #27 stale CRLF Analyst specs | — | see SI-SYNC-001 | |
| #28 parallel-phase documents | — | OWNER-DECISION | The parallel phase is still active on all four lanes; this record and the workflow exception paragraph are the owner-coordinated amendment for this pass. |
| #29 `qc_first_plan.py` stale alpha | — | OWNER-DECISION | Same as TPR-OOL-006. |
| #30 README | — | **FIXED (F-6)** | |
| #31 prunable worktrees, #32 stale stash | — | ENVIRONMENT | Host repository hygiene; not touched by this session. |
| #33 handle flakes, #35 PDF whitespace, #36 CRLF notice | — | ENVIRONMENT | |
| SYS-FU-P1-006 | P1 | ALREADY-FIXED | On `main` at `1ed0602`. |

### 5.4 Analyst-revisions lane

| ID | Sev | Disposition | Reason |
|---|---|---|---|
| CLR-002 residual (`assistant/tax_lots.py` float) | P2 | GATED-BY-PLAN | Separate money-path conversion milestone with an additive migration; not a surgical fix. |
| CLR-003 (cancel-all waits behind a stuck fence holder) | P2 | GATED-BY-PLAN / OWNER-DECISION | Requires bounded broker operations and a stop-request design; the 180 s bound was rejected as unproven. |
| CLR-005 (absolute kill switch) | P3 | OWNER-DECISION (made 2026-08-27) | Deviation documented by owner choice. |
| #4 root `.gitattributes` | — | **FIXED (F-4)** | Root file exists since OOL-001; the shared gaps are now closed. |
| ARV2ENV-001 / -002, #16 interpreter divergence, #14 PDF whitespace | — | ENVIRONMENT | |
| ARV2R8-002 (three dropped lane tests) | — | OWNER-DECISION | Whether `main`'s suite supersedes them is an Analyst-lane record question. |
| ARV2R7-002 / ARV2R8-003 (two Claude sessions on one lane) | — | OWNER-DECISION | Coordination, not code. |
| ARV2-UNRELATED-001 | P3 | routed to the Target-price lane (lane-owned test) | Not a stale message: passes with an external basetemp, fails with a repository-local one (section 3). Same mechanism as SI-OOL-003. |
| ARV2WL-D11 | P3 | **FIXED (F-1)** | |
| ARV2WL-D10 (calendar test gap) | P3 | not a defect | Test-inventory observation; calendar behavior was probe-verified by the lane. Candidate for a later coverage pass. |
| ARV2WL-D02 | P2 | partially closed in-lane | Archived record stays frozen history. |
| #13 "six files flagged by deeper sweeps" | — | unenumerable | The record never names them. |
| #15 `test_policy_code_is_checked_out_as_exact_bytes` reads `HEAD` | — | DESIGN | Commit-state gate by intent. |
| ARV2WL-D06 (two import-firewall implementations) | P2 | INTEGRATION-ITEM | Cross-lane consolidation. |

## 6. Owner decisions requested

1. **Runtime-stop debris on this host.** `%LOCALAPPDATA%\trading_agent\runtime\state\execution-emergency-stop.json` is active at generation 42 with 42 open incidents, all from throwaway test databases. The documented clear path cannot run because those origin databases no longer exist. This session did not modify the file. Options: delete it (the runtime recreates a clean state) or hand-clear it; either is an operator action on host state.
2. **Multiplicity re-freeze in the Analyst, Insider, and Short-interest lanes** (TPR-OOL-006/-004, Insider #29): each lane must adopt the four-family `1/80` contract through its own review loop before any outcome authority.
3. **`ml.immutable_io` relocation and immutable-I/O helper consolidation** (Insider R-23 family, SI-CR2-005, ARV2WL-D06): schedule as part of the four-lane integration milestone.
4. **Execution-semantics P1/P2 items** (Insider R-01, R-10, R-12, R-13, R-15, R-16; Analyst CLR-002 residual, CLR-003): all remain open and documented; they need the owner to start the queued full-project review or to authorize a dedicated execution-semantics milestone.
5. **Two Claude sessions on the Analyst lane** (ARV2R7-002): coordination decision.
6. **`docs/SESSION_HANDOFF.md` divergence on the Target-price lane.**
   `codex/strategy-target-price-revisions` rewrote the shared handoff's
   section 0 in `0ba9e54`, `7f55652`, and `dff9b11` (integration-state and
   2026-09-03 review-state bullets), so it no longer matches `main`'s copy;
   the other three lanes carry `main`'s copy exactly. This integration's
   handoff commit is therefore applied to the integration branch only (the
   workflow freezes the shared handoff on lanes; each lane record carries its
   own pointer section instead). The two handoff versions will need one
   reconciliation when that lane is re-merged.

## 7. Validation

Baseline, `main` at `aefa0ec`, isolated detached worktree, external
`--basetemp`: **4 failed, 6786 passed, 13 skipped, 25 warnings in 2168 s** —
the four wall-clock failures named under F-1 and nothing else.

First fix commit `7f99f30`, same setup: **1 failed, 6797 passed, 13 skipped,
25 warnings, 2 errors in 2163 s.** The failure was the unrecorded
`test_sleeve_notifications` wall-clock instance; the two errors were the
insider nesting-cap tests' teardown hitting the guard's `json.loads` call.
Both are closed by the follow-up commit (F-1 cycle pass-through, F-3 bound
decoder), whose exact hash and full-suite result are:

`3114a1530f0afa400eb200e79ff218c174657e69`, same isolated-worktree setup: **6799 passed, 13 skipped, 25 warnings, 0 failed, 0 errors in 2124 s (0:35:24)**. The real runtime emergency stop remained at generation 42 / 42 incidents through the run, with no incident originating under the run's base temp.

Focused evidence on the final tree:

- `tests/test_sleeve_notifications.py`, `tests/test_sleeve_report.py`,
  `tests/test_runtime_stop_leak_guard.py`,
  `tests/test_insider_buying_sec_edgar_acceptance_snapshot.py`: 279 passed,
  2 skipped (before the cycle regression was added; the notification file
  then passed again with the new test).
- Three reservation characterizations in
  `tests/test_execution_characterization.py`: 3 passed.
- `tests/test_active_document_consistency.py` after the document edits: 69
  passed.
- Mutations: sleeve seam → `1 failed`; cycle pass-through → `1 failed`; EOL
  attributes stripped → `3 failed, 1 passed`; crafted runtime-stop leak →
  guard raises.
- `python -m compileall -q assistant backtest data execution ml risk scripts
  signals strategies tests research baskets.py config.py market_analytics.py`:
  clean.
- `git diff --check`: clean.

Untested paths: the Briefing flake (F-5) cannot be reproduced on demand, so
its closure rests on the seam census, not on a red-then-green run; the leak
guard's real-file read was exercised on this host only.
