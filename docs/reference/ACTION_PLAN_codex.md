# Consolidated implementation action plan — Codex

Status: independent Codex audit for later comparison with
`docs/ACTION_PLAN_claude.md`

Audited base: `ff8c16e` (merge PR #112), 2026-08-02

Scope: every implementation plan, design backlog, status ledger, operational
gate, and architecture-debt record currently tracked under `docs/`. This is a
planning and status artifact; it does not authorize live trading, ML/strategy
promotion, destructive cleanup, paid data acquisition, or external deployment.

## 1. How this plan decides what is done

An item is marked complete only when the planned behavior is present in code,
its relevant tests/contracts exist, and the repository's later status or Git
history supports completion. A document, checked box, fixture, or passing
synthetic test is not by itself implementation or market evidence.

The status terms in this plan are deliberately distinct:

| Status | Meaning |
|---|---|
| **Complete and reviewed** | The software milestone met its reviewed definition of done. |
| **Software complete; real acceptance pending** | The code path works on controlled evidence, but licensed data, host operation, elapsed observations, or another real-world condition remains. |
| **Partial** | Useful reviewed slices exist, but the parent milestone's definition of done is not met. |
| **Not started** | The plan exists, but its product-specific contracts or behavior do not. Existing generic prerequisites do not change this classification. |
| **Blocked** | Progress requires an owner decision, external data/evidence, elapsed calendar time, or another completed milestone. |
| **Deferred/optional** | Deliberately outside the active critical path; revisit only under its recorded criteria. |
| **Prohibited** | Must not be implemented under the current architecture or authority. |

Where documents conflict, current code and reviewed status take precedence;
the active factual sources are `docs/GENERAL_READINESS_STATUS.md`,
`docs/ML_IMPLEMENTATION_STATUS.md`, and `docs/SESSION_HANDOFF.md`. The
implementation plans still control milestone definitions and safety gates.

## 2. Document inventory and authority

| Document | Current role | Disposition |
|---|---|---|
| `GENERAL_READINESS_IMPLEMENTATION_PLAN.md` | Active general engineering roadmap | Keep as the GR milestone contract; use the status companion for completion. |
| `GENERAL_READINESS_STATUS.md` | Current GR implementation ledger | Authoritative for GR-0/GR-1 completion and GR-2..GR-9 non-completion. |
| `ML_IMPLEMENTATION_STRATEGY.md` | Original ML architecture and ML-1..ML-10 definitions | Foundation/reference. Its “begin ML-1” instruction is historical and superseded. |
| `ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md` | ML-LR integrity, evidence, isolation, and promotion gates | Still authoritative for gates and task-specific definitions. Its “begin ML-LR-0” instruction is historical and superseded. |
| `ML_FULL_SYSTEM_EXECUTION_PLAN.md` | Active ML execution overlay | Primary remaining ML sequence; completion qualifiers must come from ML status. |
| `ML_IMPLEMENTATION_STATUS.md` | Current ML implementation ledger | Authoritative for software versus real-data/evidence completion. Earlier paragraphs are historical snapshots when contradicted by later sections. |
| `AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` | Long-term governed prose-to-strategy roadmap | Queued after the ML/general-readiness software prerequisites; AS product chain not started. |
| `UI_FEATURE_CONTROLS_DESIGN.md` | Settings, policy controls, provider status, ticker-suggestions design | Planning only; four owner decisions remain. |
| `PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` | Safe expiry/dismissal design | Deferred and unimplemented; physical deletion remains separately prohibited without explicit authorization. |
| `MCP_JUSTIFICATION_AND_IMPLEMENTATION.md` | Optional read-only evidence-access proposal | Deliberately queued until GR/ML completion and only if its decision criteria still hold. |
| `ALLOCATION_SERVICE_DESIGN.md` | Proposed market-volatility-aware allocation service | Design only except for the reusable `strategy_evaluations` persistence primitive. Fold future work into GR-7 rather than create a competing allocator. |
| `AI_DEBATE_DESIGN.md` | Optional two-position grounded-risk presentation | Multi-position debate is unimplemented; the shipped single-candidate investment committee is a different feature. |
| `ARCHITECTURE_DEBT.md` | Structural debt ledger | Item 1 partial, item 2 open, item 3 resolved. GR-1/GR-2 own the remaining work. |
| `LIVE_PROMOTION_CHECKLIST.md` | Human review gate, never an execution switch | No current authorization; its evidence requirements remain unsatisfied. |
| `OPERATIONS_RUNBOOK.md` | Procedures for implemented operations/evidence machinery | Use only after machine paths, identities, credentials, tasks, and account state are reverified. |
| `DATABENTO_DATA_SOURCE.md` | Databento capture procedures | Operational reference. Its statement that the vintage-correct builder is still missing is superseded by ML-FS-3 software. Real licensed inputs and historical membership are still absent. |
| `ADR_INVESTMENT_COMMITTEE_BOUNDARY.md` | Accepted AI committee authority boundary | Foundation/provider/audit/UI are implemented; the 50-case adversarial replay release gate remains incomplete. |
| `MANDATE.md` | Proposed portfolio objectives and scope | Not approved. Draft targets cannot satisfy promotion gates until owner-approved and fingerprint-bound. |
| `SESSION_HANDOFF.md` | Canonical Git/operational handoff | Must be updated after this plan; its pre-PR-#112 branch state is stale. |
| `TRANSITION_HANDOFF_2026-08-01.md` and dated review reports | Historical evidence | Preserve for audit history, but do not use as current sequencing instructions. The 2026-07-30 findings were fixed by later commits. |

## 3. What is already implemented

### 3.1 Reviewed trading and execution foundation

- Paper mode remains the hard default, exact human approval and fresh
  post-approval validation remain mandatory, and persistent/environment kill
  switches, atomic claim ownership, reservation accounting, idempotent broker
  submission, ambiguous-outcome reconciliation, replacement-chain handling,
  and append-only broker journaling are implemented and tested.
- The four P1 and ten P2 findings in
  `REVIEW_2026-07-30_FULL_CODEBASE.md` were corrected in later commits
  (`07bff4b`, `680f4d7`, and follow-ups); that report is not an open backlog.
- Test isolation now prevents pytest from using inherited broker credentials or
  the operator database. This was a real operational fix, not a plan item to
  repeat.
- The independently reviewed validation/execution baseline at merge `ef77bbf`
  was 2,412 passed, 1 skipped. PR #112 merged its final review and handoff into
  `main` at `ff8c16e`; those later commits are documentation-only.

### 3.2 General Readiness

| Milestone | Audited status | Implemented scope |
|---|---|---|
| GR-0 | **Complete and reviewed** | Typed, read-only five-dimension platform-readiness report and CLI; dimensions cannot mask one another; unavailable inputs block; strategy readiness requires a finding that is both confirmed and production-authoritative. |
| GR-1A | **Complete and reviewed sub-milestone** | Characterization across all five public execution entry points plus extraction of outcome interpretation and kernel helper seams with import/identity boundaries. |
| GR-1B | **Complete and reviewed sub-milestone** | Execution phases decomposed into named kernel helpers; atomic transitions remain in `AssistantStore`; compatibility exports and telemetry fall-through guard are pinned. |
| GR-1C | **Complete and reviewed sub-milestone** | Validation orchestration moved to `assistant/execution_kernel/validate.py` behind call-time facade-derived dependency injection and a zero-module-global runtime-read guard. One class-property fallback remains intentionally kernel-resolved and explicitly tested. |
| GR-1 parent | **Partial** | `assistant/execution_service.py` is still 1,094 lines. Its 281-line execution composition, 221-line manual reconciliation, and recovery orchestration mean the facade is not yet the required thin composition layer. |
| GR-2..GR-9 | **Not started as milestones** | Existing helpers may be reusable, but none meets the relevant plan definition of done. |

### 3.3 Original ML foundation (ML-1 through ML-8)

| Milestone | Audited status | Implemented scope |
|---|---|---|
| ML-1 | **Complete** | Frozen manifests/contracts, canonical hashing, atomic verified artifacts, strict loading, and ML/execution import boundary. |
| ML-2 | **Complete** | Point-in-time feature/label contracts, immutable datasets, leakage-safe transforms, and grouped purged walk-forward splits. |
| ML-3 | **Complete** | Read-only PCA/shrinkage concentration and effective-independent-bet reporting. |
| ML-4 | **Complete as research primitives** | Per-security volatility baselines, models, and evaluation machinery; no authority. |
| ML-5 | **Complete as research primitives** | Earnings-gap mapping, support checks, and fitting primitives. |
| ML-6 | **Complete as observation infrastructure** | Append-only model/prediction/outcome persistence and monitoring primitives. |
| ML-7 | **Partial research foundation** | Cross-sectional ranker/statistical primitives exist; the full historically correct economic experiment does not. |
| ML-8 | **Complete within context-only scope** | Filing/transcript extraction contract and deterministic validation; provider runner/auditing subsequently added under ML-LR-4. |
| ML-9 | **Deferred** | Execution-quality fitting correctly absent pending representative live-order evidence. |
| ML-10 | **Not authorized** | No model output reaches assistant proposals or execution. |

### 3.4 ML-LR readiness milestones

| Milestone | Audited status | Remaining qualifier |
|---|---|---|
| ML-LR-0 | **Software complete and reviewed** | Shared experiment identity and preregistered gates are implemented. |
| ML-LR-1 | **Software complete; real acceptance pending** | Lineage/universe contracts and sidecars work, but no reviewed licensed real dataset currently establishes authoritative coverage. |
| ML-LR-2 | **Software complete and reviewed** | Durable discovery/confirmation runner and reproducible CLI exist. |
| ML-LR-3 | **Software complete; evidence underfilled** | Per-security and portfolio volatility paths work; genuine complete account-session history is insufficient. |
| ML-LR-4 | **Software complete; real confirmation blocked** | Event runner, evaluation, typed forecast, and filing runner exist; authoritative historical event/surprise/revision coverage is absent. |
| ML-LR-5 | **Not started; optional** | Complete historical-universe ranker runner, shared-capital economics, costs/taxes/liquidity/mandate evaluation, confirmation, and task-specific shadow adapter remain. |
| ML-LR-6 | **Software complete for supervised volatility** | Runtime/epoch/scheduler software exists; operating-host installation and elapsed evidence do not. |
| ML-LR-7 | **Software complete** | Epoch monitoring and immutable promotion dossier exist; no real eligible dossier exists. |
| ML-LR-8 | **Software complete** | Read-only CLI presentation exists and remains outside `assistant/`; no trading authority. |
| ML-LR-9 | **Not implemented or authorized** | Human promotion registry and context-only bounded adapter require a later explicit request and real dossier. |
| ML-LR-10 | **Not implemented or authorized** | Limited-capital canary requires evidence and another explicit owner decision. |
| ML-LR-11 | **Deferred/prohibited now** | Representative live execution-quality data does not exist. |

### 3.5 ML Full-System overlay

| Milestone | Audited status | Implemented versus missing |
|---|---|---|
| ML-FS-0 | **Complete** | Ordered overlay and audited baseline exist. |
| ML-FS-1 | **Software complete** | Scheduled paper observation normalizes equity/positions and writes complete-capture manifests idempotently. |
| ML-FS-2 | **Software complete** | Immutable pre-broker execution telemetry joins to authoritative broker lifecycle events and fails closed before submission if mandatory capture fails. |
| ML-FS-3 | **Software complete; real definition incomplete** | Vintage-correct Databento builder, independent universe contract, replay, and online provider exist. No reviewed licensed historical-universe artifact or actual authoritative real batch has been supplied. |
| ML-FS-4 | **Software complete; evidence underfilled** | Frozen portfolio dataset, shared runner, immutable reports, forecasts, and honest refusals exist. Real portfolio history remains insufficient. |
| ML-FS-5 | **Software complete** | Frozen prospective intervals/probabilities/baselines/features/lineage and complete success/refusal schema exist. Prospective quality is unproven. |
| ML-FS-6 | **Preparation software complete; real work not run** | Content-addressed dataset admission, spec attestation, reviewed-run wrapper, and untouched-confirmation request exist. The checked-in discovery spec is unapproved; no authoritative real discovery or confirmation has run. |
| ML-FS-7 | **Infrastructure complete; host acceptance pending** | Independent evidence-health rules, durable alerts, limited-principal task installers, and verifier exist. Tasks, credentials, first runs, delivery receipts, backups/restores, and elapsed sessions are not established on this host. |
| ML-FS-8 | **Not implemented or authorized** | Promotion review, audited context-only registry transition, and assistant-facing read-only adapter remain gated. |
| ML-FS-9 | **Not implemented or authorized** | Deterministic exposure-reducing constraint and canary remain gated behind FS-8 evidence and a second owner request. |

### 3.6 Data, operations, and evidence machinery

- Databento cost estimation, capped downloads, immutable paid DBN retention,
  receipt-timestamped statistics, licensed reference capture, vintage-correct
  adjustment/security resolution, independent universe input, authoritative
  batch replay, and online feature-provider software exist.
- `artifacts/databento/` is present locally, but presence is not provenance,
  completeness, a historical membership source, or authoritative coverage.
- Operations-cycle, watchdog, paper observation, order monitor, ML shadow jobs,
  evidence supervisor, Windows installers, task verifier, backups, recovery
  drill, promotion checks, and durable operational alerts exist as software.
- Current machine state does not prove these controls are deployed: scheduler
  inspection was access-denied, no paper or ML evidence epoch exists in the
  recorded operator database, no paper observations/orders/drills are recorded,
  and alert delivery has not been exercised.
- `config.PAPER_TRADING` is `True`. This audit grants no permission to change
  it or access a funded account.

### 3.7 Product and AI surfaces

- The Streamlit app currently has Briefing, Watchlist, Selling, Propose &
  Approve, and History tabs. It already exposes ticker suggestions inside
  Briefing/Watchlist, a per-run strategy-proposal checkbox, event-fetch choice,
  deterministic allocation, proposal approval/history, and reconciliation
  workflows. There is no Settings & Features tab or dedicated Ticker
  Suggestions tab.
- Optional news summaries, similar-ticker suggestions, allocation commentary,
  and the investment committee use deterministic grounding/validation and
  cannot create or modify proposals.
- The investment-committee provider, audit persistence, exact-input UI cache,
  unavailable state, and execution isolation are implemented. Its required
  50-case frozen adversarial replay corpus is not; the UI remains behind
  `ENABLE_EXPERIMENTAL_COMMITTEE=1`.
- Generic allocation batch execution, inverse-volatility helpers, regime
  classification, and `strategy_evaluations` cadence persistence are reusable.
  The market-volatility-aware allocation service itself is not implemented.
- No multi-position AI debate module exists.
- No proposal `dismissed` lifecycle, expiry sweep, dismissal preview/hash,
  UI/CLI dismissal, or physical purge exists.
- No `mcp_bridge` package or MCP server exists.
- No AI strategy vocabulary, restricted `StrategySpec`, compiler/interpreter,
  data/evaluation compiler, generic strategy backtest adapter, authoring flow,
  registry, Backtest UI, or proposal adapter exists. Generic hashing,
  backtesting, ML research, LLM provider/audit, and proposal infrastructure are
  prerequisites, not completion of AS-0 or later milestones.

## 4. Corrections to stale planning statements

Do not carry these older statements into future implementation prompts:

1. **“Zero confirmed findings” is stale.** The current registry has two
   confirmed findings, but zero findings that are both confirmed and
   production-authoritative. The latter is the correct strategy-readiness gate.
2. **“Begin ML-1” and “begin ML-LR-0” are stale.** Those milestones and much
   later infrastructure are already implemented.
3. **“The Databento vintage-correct builder is missing” is stale.** ML-FS-3
   implemented it. The real blockers are reviewed licensed inputs, historical
   membership, and an actual authoritative build.
4. **“The ML spec library is absent” is stale.** A review-ready volatility
   discovery spec/request exists; it is intentionally unapproved and has not
   been run on authoritative real data.
5. **GR-1 size snapshots are historical.** Current audited values are
   `execution_service.py` 1,094 lines, `execute_approved_paper_proposal()` 281,
   `reconcile_submission()` 221, and `run_proposal_validation()` 294. The
   validation module itself is now 490 lines after the third-round explanatory
   docstring; older 479-line statements describe the pre-confirmation snapshot.
6. **The session handoff's local-only PR-#112 decision is stale.** The review
   branch was pushed and merged into `main` at `ff8c16e`.

## 5. Remaining work, ordered by dependency and risk

### Track A — active engineering critical path

#### A1. Finish GR-1D: manual reconciliation extraction

This is the next code milestone. Move the 221-line
`reconcile_submission()` orchestration behind an explicit call-time dependency
contract while preserving:

- the public `assistant.execution_service` facade and exact exception/import
  identities;
- broker-absence grace behavior, failed/unconfirmed lookups, replacement
  chains, account/intent mismatch halts, reservation hold/release rules, and
  journal failure behavior;
- conditional storage transitions and race recovery in `AssistantStore`;
- broker-absence behavior when the broker module is unavailable; and
- every existing facade monkeypatch seam.

Characterize every branch first, mechanically inventory runtime globals and
the facade import surface, red/green test confirmed findings, mutation-test the
dangerous directions, run full validation, and stop for independent review.

#### A2. Finish GR-1E if the post-GR-1D gap analysis still requires it

Extract or reduce the remaining 281-line execution composition and the recovery
wrappers without moving atomic state ownership out of storage. GR-1 completes
only when `execution_service.py` is genuinely a thin composition/compatibility
layer and each kernel module is independently testable. Do not use a target
line count as a substitute for that definition.

#### A3. GR-2: one ordered risk-check registry

After the facade split stabilizes, inventory every proposal, post-approval, and
pre-submit check and consolidate execution order without reducing coverage.
Freeze the exact check inventory and phases in tests. Include the three open
scatter points in `ARCHITECTURE_DEBT.md`, but preserve the distinction between
proposal suggestions and execution permission.

#### A4. GR-3: executable fault matrix and retained drill evidence

Implement the planned broker timeout/duplicate/restart/mismatch/halt/corporate-
action/staleness/disk/journal/kill-switch matrix using a real isolated SQLite
database and scripted broker. Include the two historical isolation failures:
operator-database test pollution and inherited-credential broker contact. The
harness must write immutable drill results and prove both refusal and absence
of partial state.

#### A5. GR-4: production data honesty

Add production-side data-source contracts, per-data-class freshness SLAs,
provider health, visible surface-specific degradation, and corporate-action
checks without making `assistant/` import `ml/`. Reuse Databento semantics and
records through a narrow neutral adapter; do not duplicate ML lineage logic or
let a caller assert point-in-time status.

#### A6. GR-5: delivered observability

Choose and implement one owner-visible channel, delivery receipts/failures,
severity routing, deduplication, weekly self-test, and the operator dashboard.
Unify the delivery boundary used by ordinary operational and ML evidence
alerts. A JSONL append or SQLite row is not proof that the owner received an
alert.

#### A7. GR-6: recovery, secrets, and portability

Set recovery objectives, restore from a genuine off-machine backup, audit
secret-shaped values across structured outputs, exercise key rotation, add a
database/runtime identity guard, and provide a portable scheduling entry point
with Windows Task Scheduler as one adapter. Verify a second-machine restore in
practice.

#### A8. GR-7: ordinary product completeness

Implement reviewed slices for deterministic rebalance-to-target proposals,
tax-lot consequences, performance attribution, annual tax export, and idle-cash
reporting. Fold the useful parts of `ALLOCATION_SERVICE_DESIGN.md` into the
rebalance slice so the app has one authoritative sizing path. Freeze universe,
regime-threshold calibration, buy-only versus mixed-leg scope, and policy
interaction before coding.

### Track B — long-lead ML/data/evidence work

Track B may prepare owner decisions and licensed inputs in parallel with Track
A, but should not start an evidence epoch on a changing single-worktree runtime.

#### B1. Resolve authoritative data and mandate inputs early

- Select, license, and review a historical constituent-membership source.
- Privately inventory current Databento artifacts/manifests/hashes and determine
  what licensed security/adjustment/statistics history is actually available.
- Approve or revise mandate targets and fingerprint the approved mandate before
  any promotion-quality evidence epoch.
- Define task-specific data for earnings surprise/revision/announcement history
  if earnings research remains in scope.

#### B2. Complete ML-FS-3 real-data acceptance

Build at least one real authoritative, vintage-correct dataset using reviewed
statistics/reference/universe inputs and exact decision cutoffs. Independently
review provenance, licensing, coverage, prefix invariance, adjustments,
rescissions, listings, and membership. Only the normal coverage evaluator may
derive `point_in_time_data=true`.

#### B3. Execute ML-FS-6 discovery and untouched confirmation

After B2, have an identified reviewer attest the immutable discovery spec, run
the real discovery campaign, preserve all reports/refusals, prepare a different
content-addressed confirmation dataset/spec, obtain a separate attestation, and
run untouched confirmation without retuning. A rejection is a valid final
result; it must not be optimized away.

#### B4. Deploy and accept ML-FS-7/operations only on a frozen runtime

After the intended software/configuration baseline is stable, verify paper
account identity and database isolation, install all operational/ML tasks under
a limited principal, perform manual first runs, verify heartbeats and task
results, exercise owner-visible alert delivery and restore, then begin one
lineage-consistent paper/ML evidence epoch. Preserve every refusal and missing
session; do not manufacture elapsed evidence.

#### B5. Accumulate and assess evidence

Collect the mandate's required paper sessions/orders and the separately
preregistered ML monitoring sample in one immutable epoch. Do not pool across
model, provider, code, policy, mandate, account, schedule, or configuration
changes. Generate monitoring and promotion dossiers only after outcomes mature.

#### B6. Keep optional ML work optional

ML-LR-5 ranker economics and earnings/ranker shadow adapters are separate
task-specific tracks. Start them only if the owner prioritizes them after
authoritative data exists. ML execution-quality fitting remains deferred until
representative live orders exist.

### Track C — bounded product backlog after the safety-critical work

#### C1. UI Settings & Features and Ticker Suggestions

Before implementation, the owner must choose session versus durable
preferences, policy-file versus versioned policy-record edits, whether old
suggestion surfaces remain, and master versus per-feature AI toggles. Implement
preferences, authoritative policy changes, secrets/provider status, and safety
status as different control classes. Never expose secret editing or a live
toggle.

#### C2. Proposal history dismissal

Implement `dismissed`, bounded expiry, transactionally bound preview/eligibility
hashes, atomic bulk dismissal, CLI parity, and History visibility only after a
fresh lifecycle gap analysis. Preserve every proposal that reached validation,
override, batching, reservation, submission, or broker state. Physical purge
remains a separately authorized future maintenance plan, not part of C2.

#### C3. Complete the committee release corpus before normal enablement

Build and mutation-verify at least 50 frozen replay cases plus prompt-injection,
memory-poisoning, action-language, citation, numeric/ticker attribution,
privacy, provider-failure, and cache-binding cases. Keep the experimental gate
until that separate review passes.

#### C4. Treat AI debate as optional UX research

First answer whether parallel grounded framings without synthesis are useful.
If yes, implement only side-by-side positions grounded against the same
deterministic fact block, both-or-neither display, no verdict, and no
proposal/policy/execution imports. Do not confuse it with the existing
single-candidate committee.

#### C5. Re-evaluate MCP rather than automatically build it

After GR-5 ships, apply MCP's decision criteria: at least five recurring
unanswered operator questions, dashboard insufficiency, and no higher-leverage
open work. If still justified, build driver-enforced read-only stdio resources
and query tools with frozen inventory/import/redaction guards. Otherwise close
the proposal. MCP write tools remain prohibited.

### Track D — AI strategy authoring, after prerequisite roadmaps stabilize

AS-0 through AS-7 are not partially complete merely because reusable ML,
backtest, LLM, and proposal infrastructure exists. Implement them one reviewed
milestone at a time, in order:

1. **AS-0:** shared strategy identity, evidence, eligibility, authority, and
   refusal vocabulary plus transitive import-closure enforcement.
2. **AS-1:** non-executable, restricted, versioned `StrategySpec` language.
3. **AS-2:** deterministic compiler/interpreter/static analysis and trace.
4. **AS-3:** data-requirement manifest, evaluation-plan compiler, and honest
   capability refusal.
5. **AS-4:** immutable research orchestration and shared-capital realistic
   backtest.
6. **AS-5:** LLM draft/clarification workflow only after deterministic
   validation exists; no generated code or runtime LLM decisions.
7. **AS-6:** multidimensional robustness/usability dossier with no averaged
   pass score.
8. **AS-7:** immutable strategy registry and exact owner-granted non-live scope.

AS-8 paper proposal integration needs an approved strategy, accumulated
evidence, explicit owner authorization, and separate adversarial review. AS-9
monitoring follows an authorized AS-8 deployment. AS-10 funded influence needs
all live gates and another explicit owner request. AS-11 autonomous mutation or
runtime LLM decisions is prohibited.

## 6. Live and promotion gates remain separate

Do not combine these into one vague “go live” milestone:

- **GR-8** is a deterministic risk-reduction canary and requires GR-1..GR-6,
  the entire live checklist, hard enforced caps, stop conditions, and explicit
  owner authorization.
- **ML-FS-8 / ML-LR-9** initially permit only audited context display after a
  real clean dossier and owner review; ML still cannot create/increase trades.
- **ML-FS-9 / ML-LR-10** are later deterministic, exposure-reducing influence
  and a separate tiny canary after a clean context-only period.
- **AS-8** initially permits only an exactly approved strategy to produce
  shadow decisions and separately reviewed human-approved paper proposals.
- **AS-10** is another later funded-scope decision, not implied by AS-8/AS-9.

No current checklist, mandate, evidence epoch, model, strategy, or owner grant
authorizes any of these.

## 7. Owner decisions and external blockers

| Decision/blocker | Needed by | Current state |
|---|---|---|
| Historical universe/reference source, license, and budget | ML B2/B3; later AS research | Unresolved and the highest-leverage external blocker. |
| Mandate targets and fingerprint-bound approval | Evidence/promotion/live gates | Proposed only. |
| Stable operational database/account and treatment of historical contamination | B4 evidence epoch | Recorded databases diverge; no destructive cleanup authorized. |
| Frozen-runtime versus separate deployment topology | B4 | Handoff records a single-installation preference; reconfirm before an epoch because ongoing commits change lineage. |
| Owner-visible GR-5 delivery channel | A6/B4 | Unchosen; JSONL alone is insufficient. |
| Elevated Windows deployment/credential-rotation window | A6/A7/B4 | Not yet available/verified. |
| UI persistence and policy-edit workflow choices | C1 | Four choices remain in the UI design. |
| GR-7 allocation universe, calibration, and sell-leg scope | A8 | Design recommends explicit universe, user-triggered frozen calibration, and buy-only first slice; owner review still needed. |
| Proposal dismissal priority | C2 | Plan exists; no implementation authorization beyond this consolidated planning task. |
| Committee normal-release threshold | C3 | Required 50-case corpus incomplete; experimental flag stays. |
| AI authoring provider/privacy/retention settings | AS-5 | Later owner/provider decision. |
| Historical local-only `a656015` document | Documentation recovery | Exact object remains unavailable; do not recreate it from memory while an exact copy may exist elsewhere. |
| Any funded account or live canary | GR-8/ML/AS live stages | Explicitly unauthorized. |

## 8. Recommended execution order

The dependency-ordered default is:

```text
NOW
  GR-1D manual reconciliation extraction
  -> GR-1E/final thin-facade slice if the gap analysis requires it
  -> independent GR-1 acceptance

NEXT — safety and dependability
  GR-2 risk registry
  -> GR-3 fault drills
  -> GR-4 production data honesty
  -> GR-5 delivered alerts/dashboard
  -> GR-6 recovery/secrets/portability
  -> GR-7 reviewed product-completeness slices

PARALLEL OWNER/EXTERNAL PREPARATION (no authority change)
  authoritative membership/reference-data decision
  + private licensed-artifact inventory
  + mandate decision
  + delivery-channel/deployment-window decisions

AFTER AUTHORITATIVE DATA
  ML-FS-3 real acceptance
  -> ML-FS-6 real discovery
  -> untouched confirmation

AFTER A FROZEN OPERATIONAL BASELINE
  host/task/backup/alert acceptance
  -> one immutable paper/ML evidence epoch
  -> elapsed monitoring and promotion dossier

PRODUCT BACKLOG, ONE REVIEWED SLICE AT A TIME
  UI controls / proposal dismissal / committee corpus
  + GR-7-integrated allocation work
  + optional debate or MCP only if still justified

AFTER GENERAL + ML SOFTWARE PREREQUISITES ARE STABLE
  AS-0 -> AS-1 -> AS-2 -> AS-3 -> AS-4 -> AS-5 -> AS-6 -> AS-7

EXPLICIT LATER AUTHORITY ONLY
  context-only ML review; approved-strategy paper adapter;
  deterministic GR canary; then separately reviewed bounded ML/AS influence
```

The only default next coding instruction from this plan is **GR-1D**. Starting
GR-2, AI strategy authoring, UI controls, proposal cleanup, MCP, ML promotion,
or a canary before GR-1D review would be an explicit owner priority change.

## 9. Per-milestone completion discipline

For every selected milestone:

1. establish the exact base and enumerate every commit for review;
2. perform a fresh gap analysis against current code rather than copying old
   file names or assumptions;
3. freeze behavior/compatibility and dangerous failure directions first;
4. implement one coherent slice on its own branch;
5. retain P0-P3 findings and concrete reasons in the review report;
6. use red/green characterization and reverse-mutation evidence where
   practical;
7. run focused tests, full tests, compileall, and diff/status checks on the
   final tree in proportion to risk;
8. update the relevant status ledger, add exactly two milestone-record
   paragraphs only for genuinely completed functionality, and commit
   `SESSION_HANDOFF.md` separately; and
9. do not push, merge, deploy, spend vendor money, mutate external state, or
   grant authority without the owner's explicit instruction.

## 10. Cross-review protocol with Claude's plan

Keep `ACTION_PLAN_codex.md` and `ACTION_PLAN_claude.md` independent until both
are committed. Then compare them using an explicit difference ledger covering:

- source documents included or omitted;
- every milestone status and its code/test evidence;
- stale statements each plan supersedes;
- ordering and dependency differences;
- owner decisions and external/calendar blockers;
- items proposed for consolidation, deferral, or closure; and
- any statement that could accidentally imply research, paper, proposal, or
  live authority.

Resolve factual differences against code/Git/tests. Present genuine priority
or product tradeoffs to the owner instead of silently choosing. The agreed
result should be written as a new owner-approved final plan; neither agent's
draft should silently overwrite the other.
