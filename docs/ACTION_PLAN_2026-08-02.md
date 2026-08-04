# ACTION PLAN — the go-to consolidated done / remaining ledger

Status: **owner-adopted go-to plan** (2026-08-02). After independent audits
by Claude and Codex converged on the same facts, the owner selected this
plan as the single sequencing authority for all workstreams. Codex's
independent draft is preserved at `docs/reference/ACTION_PLAN_codex.md`;
its doc-inventory table and staleness corrections are incorporated by
reference. The individual implementation plans are archived in
`docs/reference/` and remain authoritative for their own milestone
*definitions* — this document decides only *what happens next*.

Owner priority change (2026-08-02): **UI feature controls moved to the
front of the queue** — the owner begins daily paper trading to gather real
transaction data, and the Settings/policy/AI controls directly support
that. Both audits agree this reordering is safe: the UI consumes only the
characterization-pinned execution facade, so it neither blocks nor is
blocked by the remaining GR-1 kernel work.

Prepared: 2026-08-02, by Claude, at `origin/main` = `ff8c16e` (post PR #112);
adopted and reprioritized at `ded68b0` (post PR #113/#114); UI Phase 1
implemented and merged as PR #116 at `4c8e959`, independently accepted
after corrections (`a6d5254`), confirmed by Claude's third round, and the
whole review chain merged as PR #117 at `661a7d4` (2026-08-03).
Phase 2 hygiene was implemented at `34ce463` and independently accepted
after correction on `codex/review-phase2-hygiene-20260803`, then merged as
PR #118 and confirmed through PR #119. GR-1D merged as PR #120 at `711095c`
and was independently accepted at `2f37210`. PR #121 added four exploratory
candidate-signal utilities at `5a6ffd5`; independent review corrected their
family-wide evidence reporting at `6d3603d` without changing roadmap order.

Method: four parallel verified surveys over every implementation plan and
design document under `docs/`, each claim checked against the actual code
(module/function existence, line numbers, table row counts, scheduled-task
enumeration, live read-only database inspection) rather than trusting status
prose. Where this document says "verified", a file path or measurement backs
it; where a status doc disagreed with code, the code won and the discrepancy
is listed in section 7.

Nothing in this document grants authority. Live trading, funded accounts,
model promotion, autonomous execution, and every ML/LLM boundary in
`CLAUDE.md` and `docs/SESSION_HANDOFF.md` remain exactly as constrained.

---

## 1. The one-paragraph state of the project

The platform's **code** is far ahead of its **operations and evidence**. The
deterministic execution path (propose → validate → approve → claim → submit →
reconcile) is built, characterization-frozen, and three-review hardened; the
ML research/shadow stack is software-complete through monitoring and dossier;
the LLM committee foundation is built and gated; the execution-kernel split
(GR-1) is complete after the independently reviewed 2026-08-03 GR-1E
assessment; GR-3 fault drills, GR-5 alert delivery, and GR-2's risk registry
are complete and independently reviewed (2026-08-03). What does not exist is: GR-4, GR-6, GR-7,
every AI *product* plan beyond the committee (strategy
authoring, debate, allocation service, MCP, and proposal cleanup), and — most
importantly — **any qualifying frozen-epoch operational evidence at all**:
zero scheduled tasks installed, zero evidence epochs, zero
drills recorded, zero ledger bootstraps, zero broker lifecycle rows, and the
60-session / 30-order mandate clock has never started. The scarcest resource
on the critical path is not engineering — it is elapsed calendar time on a
frozen runtime, plus a small number of owner decisions and data purchases.

---

## 2. DONE — implemented, reviewed, and verified in code

### 2.1 Execution platform (general readiness)

| Item | Where | Review state |
|---|---|---|
| GR-0 five-dimension platform readiness (never averaged; fail-closed) | `assistant/platform_readiness.py` (683 lines), CLI `platform-readiness` | independently reviewed |
| GR-1A execution characterization freeze (5 public entry points, atomic-claim pin, 4-writer contention) | `tests/test_execution_characterization.py` | independently reviewed |
| GR-1A/B helper + orchestration extraction (7 kernel modules) | `assistant/execution_kernel/{claim,revalidate,submit,outcomes,errors,intents,validate}.py` | independently reviewed |
| GR-1C validation orchestration behind complete call-time DI (15-field frozen `ProposalValidationDeps`; kernel body has zero module-global runtime reads, symtable-pinned) | `assistant/execution_kernel/validate.py` | three review rounds, closed at PR #112 |
| GR-1D manual reconciliation behind complete call-time DI (13-field frozen `ReconciliationDeps`; kernel body has zero module-global runtime reads, symtable-pinned) | `assistant/execution_kernel/reconcile.py` | merged as PR #120; independently accepted at `2f37210` |
| Execution-kernel import boundary: no direct or transitive path from kernel/assistant/execution/risk roots into `ml` or proposal generation | `tests/test_ml_import_boundary.py` (transitive graph walk, fails closed on unresolvable imports) | reviewed |
| Order lifecycle: idempotent submission, ambiguous-outcome reconciliation, replacement chains, absence-age grace, reservation accounting, telemetry-before-submission | `assistant/execution_service.py` (facade, 952 lines), `assistant/order_lifecycle.py`, `assistant/order_reconciler.py` | multiple review rounds |
| Risk-metrics consolidation (`max_drawdown_pct` single source) | `backtest/risk_metrics.py` | closed in ARCHITECTURE_DEBT |

### 2.2 ML stack (all **observation-only**, promotion-blocked by design)

| Item | Where |
|---|---|
| Contracts, manifests, hashing, artifact integrity (ML-1) | `ml/contracts.py`, `ml/hashing.py`, `ml/artifacts.py` |
| PIT features/labels, purged grouped walk-forward splits, immutable datasets (ML-2, ML-LR-1) | `ml/features.py`, `ml/labels.py`, `ml/splits.py`, `ml/datasets.py`, `ml/availability.py` |
| Factor risk, volatility/correlation research, earnings-gap research (ML-3/4/5, ML-LR-3/4) | `ml/factor_risk.py`, `ml/volatility.py`, `ml/earnings_*.py`, `ml/portfolio_*.py` |
| Durable experiment runner + review-gated campaign CLI (ML-LR-2, ML-FS-6 prep) | `ml/experiments.py`, `ml/research_orchestration.py`, `scripts/run_ml_research_campaign.py`, `research/ml_specs/` |
| Supervised-volatility shadow runtime + evidence epochs (ML-LR-6) | `ml/shadow_runtime.py`, `scripts/run_ml_shadow.py` (register/predict/mature/monitor/status/close-epoch) |
| Monitoring reports + promotion dossier (read-only; no registry writes) (ML-LR-7) | `ml/monitoring_reports.py`, `ml/promotion.py`, `scripts/run_ml_promotion_dossier.py` |
| Read-only presentation with action-shape rejection (ML-LR-8) | `ml/presentation.py` |
| Paper portfolio collection + capture manifests (ML-FS-1), pre-broker execution telemetry (ML-FS-2) | `assistant/paper_evidence.py`, `assistant/execution_telemetry.py` |
| Databento ingest/PIT software incl. authoritative builder (ML-FS-3, software only) | `ml/databento_*.py`, `scripts/run_databento_ingest.py` (8 subcommands) |
| Evidence-operations supervisor + Windows task installers + verifier (ML-FS-7, software only) | `ml/evidence_operations.py`, `scripts/install_windows_*.ps1`, `scripts/verify_windows_evidence_tasks.ps1` |

### 2.3 LLM features (all advisory-only, audited)

| Item | Where |
|---|---|
| Investment-committee foundation: schemas, projection with privacy modes, deterministic validators, pure orchestration | `assistant/llm/` (10 files) |
| Real Anthropic provider (typed error codes, bounded timeout, `max_retries=0`) + mandatory audit persistence (audit failure ⇒ review unavailable) | `assistant/llm/anthropic_provider.py`, `committee_service.py` |
| Streamlit surface: sell-only eligibility, exact-input-hash cache binding, double-gated (`ANTHROPIC_API_KEY` AND `ENABLE_EXPERIMENTAL_COMMITTEE=1`) | `scripts/personal_assistant_ui.py` |
| Advisory helpers: news summaries, similar-ticker suggestions, allocation commentary — all with action-language rejection + `ai_runs` audit | `assistant/ai_advisor.py`, `assistant/news_summary.py` |

### 2.4 Process infrastructure (2026-08-02)

Commit-by-commit review with P0–P3 ledger (`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`),
two-paragraph milestone record (`docs/FEATURE_MILESTONE_RECORD.md`), canonical
git-synchronized session handoff (`docs/SESSION_HANDOFF.md`), all wired into
`CLAUDE.md` and the review skill.

### 2.5 UI feature controls (2026-08-03)

The Streamlit app gained its sixth and seventh tabs here (Settings & Features and a
research-only Ticker Suggestions surface; GR-5 later added an eighth, read-only Operations tab). Session-scoped AI preferences gate
all optional LLM surfaces; provider and safety state are read-only; and
`allow_new_positions` / `enable_strategy_proposals` use a protected typed
confirmation, validate-before-write, version/fingerprint-changing persistence
workflow. Independent review added behavioral coverage proving the real UI
toggle persists and refreshes authoritative status in both directions, binds
editor state to the selected policy, and prevents disabled suggestion sources
from calling their providers. Implementation merge: `4c8e959`; accepted after
review correction `a6d5254`; the full review chain (correction, handoff,
third-round confirmation) merged as PR #117 at `661a7d4`.

### 2.6 Exploratory candidate-signal software (2026-08-03)

PR #121 added causal residual momentum/reversal, volatility-scaled momentum,
and consecutive-earnings-surprise persistence scanners plus reporting-only
block-bootstrap runners. Independent review at `6d3603d` made the two runners
share the full eight-cell Bonferroni family, made evidence-column drift fail
closed, and documented PEAD's long-only direction asymmetry. These are
reviewed research utilities, not confirmed findings: yfinance/current-universe
inputs are not point-in-time, no result was promoted, and no proposal,
execution, policy, scheduler, epoch, or live-authority path changed. This
already-merged work does not reorder the adopted next step.

---

## 3. IN PROGRESS — started, not finished

| Item | Remaining | Size |
|---|---|---|
| **GR-1E** — ~~assess the composition + recovery wrappers~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03: no extraction. The 281-line coordinator sequences extracted phases, performs ordinary control/exception/message composition, contains one broker-submission call, and contains no inline financial math, transition SQL, or broker interpretation. Recovery remains around the atomic storage primitive; the claim wrapper may try more than one candidate status. GR-1 is complete against the archived plan's intended §6.4 scope; `allocation_batch.py` debt remains open. See GENERAL_READINESS_STATUS and the GR-1E review report.** | none | complete |
| **Committee release gates** — ADR requires ≥50 frozen replay cases (0 exist), memory-poisoning cases (0), broader injection corpus (3 seeds), a CLI `review unavailable` surface (none); only then remove the experiment gate | corpus authoring + CLI wiring | 1–2 milestones |
| **ML-FS-6 real discovery/confirmation** — spec `research/ml_specs/volatility-discovery-v1.json` is review-ready; no `SpecReviewAttestation` exists | blocked on owner-designated reviewer + real PIT data | owner + data |

---

## 4. Planned-code milestone ledger — current completion state

| Milestone | Scope (one line) | Verified-absent marker |
|---|---|---|
| GR-2 risk-check registry | ~~ordered registry replacing the hand-written gate sequence~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03**: 20-check `RISK_CHECK_REGISTRY` with `applies_at` phases, exact old/new behavior preservation, runner-bound frozen inventory, registry-injection proof, and corrected terminal semantics. Implementation `03895ae`; review correction `0167c67`. | complete |
| GR-3 fault-injection drills | ~~9 named faults + drill harness~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03**: 11 fault IDs / 14 behavioral tests plus an atomic hash-stamped runner. Review corrected active-epoch lineage binding, skipped/abnormal pytest fail-open behavior, the missing F4 critical alert, the absent true `submitting` restart case, partial-state assertions, and artifact atomicity. Records ambiguous_submission/restart_recovery/kill_switch rows only under exact epoch lineage or as explicit verification-only evidence. | complete |
| GR-4 data-layer honesty | `PriceSource` protocol, staleness SLAs, provider health, split-between-snapshot-and-submit detection, degradation banner | no protocol in `data/`/`assistant/`; GR-0's `data_integrity` dimension is blocked-by-design until this lands |
| GR-5 alert delivery | ~~a real channel + delivery records + weekly self-test + operator dashboard~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03**: Windows toast for critical (owner decision), warnings batched to the briefing, immutable `alert_deliveries` records, escalation on failure, storage-verified weekly self-test producing the `alert_delivery` drill, readiness checks, and the Streamlit Operations tab. Review corrected a P2 gap: a durable broken-channel alert now keeps mandatory readiness failed until a later successful self-test proves recovery and acknowledges it. | complete |
| GR-6 recovery/portability | off-machine backup restore, secrets audit, key rotation, portable scheduler, second-machine stand-up proven once | zero matches for all markers |
| GR-7 product completeness | mandate-target rebalance proposals, tax-aware sell preview, performance attribution, annual tax export (wash sales), idle-cash management | `wash_sale`/`idle_cash`/attribution: zero hits |
| Allocation service | delta-vs-target primitive, calibrated regime threshold, cadence, universe list, sizing | only the `strategy_evaluations` table exists |
| Proposal-history cleanup | first milestone: `dismissed` status, preview-first dismissal CLI, History UI; optional later milestone: explicit-trigger expiry sweep; physical purge stays deferred | 19 statuses, no `dismissed`; only `prune-packets` exists (decision packets, not proposals) |
| AI strategy authoring AS-0..AS-7 | prose → StrategySpec → compiler → evaluation plan → orchestrated backtest → dossier → registry | 0% — no `strategy_lab/`, no DSL, no Backtest tab |
| AI debate surface | `assistant/ai_debate.py` parallel-framing design | 0%; its own doc questions whether the safe version is worth building |
| MCP read-only server | `mcp_bridge/` + 9 tools | 0%; GR-5's dashboard prerequisite is now satisfied, but the §3.6 activation gate still fails because the broader GR list is incomplete, no five-question preceding-month need is recorded, and higher-leverage work remains open. |

---

## 5. BLOCKED — not by code, by data / time / authorization

| Blocker class | Items |
|---|---|
| **Data purchase** | authoritative historical index/strategy membership (NOT purchasable from Databento — needs a separate vendor decision); Databento statistics captures per session/vintage (~$0.06/session measured), reference security-master + adjustment-factors snapshots, universe + cutoffs artifacts, then a real `build-authoritative` run; authoritative earnings/consensus event data |
| **Elapsed time on a frozen runtime** | mandate minimums: **60 paper sessions / 30 broker orders inside ONE evidence epoch** (~3+ calendar months); ML shadow evidence duration; 30-day backup-restore-drill freshness window |
| **Owner authorization only** | mandate approval (the only promotion gate satisfiable today with zero data); ML-FS-8/ML-LR-9 promotion registry; ML-FS-9/ML-LR-10 canary; AS-8+ adapters; GR-8 live canary; committee gate removal |
| **Prohibited until conditions change** | ML-LR-11 / ML-9 execution-quality modeling (needs representative *live* order data + explicit authorization); AS-11 autonomous strategy mutation (permanent); GR-9 non-goals (permanent) |

---

## 6. Defects found during this survey (fix cheaply, soon)

| ID | Priority | Finding | Fix |
|---|---|---|---|
| AP-1 | P2 | **Operator DB schema is stale**: `execution_telemetry_events` and `portfolio_capture_sessions` are declared in `assistant/storage.py` but absent from `data/trading_assistant.db` (24 tables present). Telemetry/capture chains cannot run until current code opens the DB. | **Resolved and reviewed 2026-08-03:** `verify-db-schema` and `verify_database_schema()` provide a read-only compatibility check plus explicit `--apply`. The measured operator DB was already current for an unknown historical reason: all required tables/columns were present and every named index/trigger definition matched current code. A pre-change SQLite backup was verified. Table column types and constraints are not compared byte-for-byte. |
| AP-2 | P2 | **`.gitignore` gap**: ML runtime writes `artifacts/shadow.json`, `artifacts/model/`, `artifacts/{datasets,experiments,reviews}/` — none ignored. First scheduled run dirties the worktree, and evidence capture **refuses a dirty worktree** → silent cadence failure. | **Resolved and reviewed 2026-08-03:** `artifacts/` is ignored wholesale and enforced through `git check-ignore` regression coverage. |
| AP-3 | P3 | 118 `portfolio_equity_snapshots` rows are mixed briefing/test-pollution provenance (pre-2026-08-02); any evidence report over them is unreliable | treat pre-2026-08-02 rows as non-evidence; decide retention at epoch start |
| AP-4 | P3 | Doc staleness cluster: `validate.py` figure 479→490 (grew in `7f431b6`); characterization-suite docstring still says "2,040 lines"; STATUS "corrects" a 1,450 figure the plan never contained; GR-1D/1E exist only in SESSION_HANDOFF, absent from plan and status docs; ML status doc has 3 internally stale paragraphs (spec library "not built" vs delivered; "calibration emitted empty" vs wired; ML-FS §2 overstates ML-FS-6) | **Resolved and reviewed 2026-08-03:** reconciled all listed statements, added GR-1D/1E status, and recorded post-PR-#117 state. |
| AP-5 | P3 | 4 of 5 `REQUIRED_PROMOTION_DRILLS` have no producer (only `backup_restore` does) — structurally unproducible until GR-3/GR-5 | **Resolved and independently reviewed 2026-08-03:** GR-3 adds exact-lineage producers for ambiguous_submission, restart_recovery, and kill_switch; GR-5 adds alert_delivery through its storage-verified self-test. All five drill types now have producers. Do not fake any of them. |

---

## 7. The critical-path insight that should drive sequencing

An evidence epoch binds the exact git commit; **any runtime change closes the
epoch, and observations cannot pool across epochs**. Therefore the 60-session
clock only accumulates on a *frozen* runtime. Two workable models:

1. **Freeze-then-collect**: finish the runtime-touching code milestones
   (GR-1D/E, GR-2, GR-4, GR-7 core) first, then freeze and start the epoch.
   Cost: evidence start delayed by the remaining code work.
2. **Pinned operational host**: the operational machine runs a designated
   frozen release commit for the whole epoch while development continues on
   branches that are simply not deployed to it. Cost: discipline (the shared
   dev machine must not run the operational cadence from a moving checkout).

Since development currently happens on the same machine that would run the
cadence, model 1 is the safe default — but the owner should choose, because
model 2 starts the 3-month clock **now** and time is the scarcest input.

---

## 8. Adopted sequencing (owner-approved 2026-08-02)

**Phase 1 — UI feature controls (COMPLETE AND MERGED: implementation
PR #116, review chain PR #117 at `661a7d4`):**
Implemented `docs/reference/UI_FEATURE_CONTROLS_DESIGN.md` as one milestone:
the Settings & Features tab (three control classes), AI master + per-feature
preferences gating all four LLM surfaces, read-only data-source and safety
status panels (reading from the enforcing functions, never re-implementing
checks), the protected policy-update workflow for `allow_new_positions` /
`enable_strategy_proposals` (validation → explicit typed confirmation →
atomic write → version bump → new fingerprint → prior-proposal invalidation
warning), and the dedicated Ticker Suggestions surface. The design's four
open decisions are resolved (§9 item 11). PR #116 merged the implementation
at `4c8e959`; independent review accepted it after two P2 corrections
(`a6d5254`); Claude's third-round confirmation re-verified both corrections
red/green with a three-mutation sweep (all caught) and hardened one
environment-sensitive runtime-identity test the confirmation run exposed.
The review chain from `user/claude/ui-review-confirmation-20260803` merged
as PR #117. No live authority or formal evidence epoch was enabled.

**Phase 2 — hygiene (COMPLETE AFTER INDEPENDENT CORRECTION, 2026-08-03):**
AP-1 schema apply/verify, AP-2 runtime-artifact ignores, and AP-4 document
reconciliation were implemented at `34ce463`. Independent review corrected
one P2 fail-open verifier gap: same-named weakened indexes/triggers must not
pass. The durable disposition and issue ledger are in
`docs/REVIEW_2026-08-03_PHASE2_HYGIENE.md`.

**Phase 3 — finish the kernel (COMPLETE AND INDEPENDENTLY REVIEWED):**
GR-1D reconciliation extraction is implemented, merged as PR #120 at
`711095c`, and independently accepted at `2f37210` with no code correction.
The GR-1E assessment (2026-08-03) declared GR-1 COMPLETE with no further
extraction. Independent review accepted that architectural conclusion after
correcting overbroad measurement, test-history, recovery-call, and
architecture-debt claims. The records are the GR-1E section of
`docs/GENERAL_READINESS_STATUS.md` and
`docs/REVIEW_2026-08-03_GR1E_ASSESSMENT.md`. Phase 4 later completed GR-3,
GR-5, and the independently reviewed GR-2 registry.

**Phase 4 — operational drill/alert prerequisites (COMPLETE AND
INDEPENDENTLY REVIEWED, 2026-08-03):**
GR-3 fault drills and GR-5 alert delivery are COMPLETE AND INDEPENDENTLY
REVIEWED. GR-5 uses Windows desktop toasts immediately for critical alerts,
batches warnings, preserves immutable delivery attempts, and requires a
successful self-test to clear a previous channel-failure condition. GR-2's
risk-check registry was implemented at `03895ae` and independently accepted
after correction at `0167c67`; Claude's counter-review (2026-08-03, appended
to `docs/REVIEW_2026-08-03_CLAUDE_INTEGRITY_GR2.md`) confirmed every finding
and correction, closing Phase 4 with both agents' verification on record.
Phase 5 is next and is owner-heavy; its non-elevated preflight was independently
reviewed and corrected 2026-08-03 on the development machine (installer
previews, CLI producers, fault harness, fail-closed readiness; see
`docs/PHASE5_DEPLOYMENT_SESSION.md` for results and the ordered owner
session). Do not begin its elevated, scheduler, mandate, or epoch actions
without the owner's specific direction and required decisions.

**Phase 5 — operational deployment + epoch start (owner-heavy):**
elevated window → dedicated task account → install + verify 8 scheduled
tasks → ledger bootstrap/reconcile → **approve the mandate** → start the
first paper evidence epoch on a frozen commit → run all 5 drills inside it →
let the 60-session clock run. From here on, the machine collects evidence
while development continues un-deployed (model 2 discipline) or pauses
runtime changes (model 1). Note: the owner's informal paper trading (from
2026-08-03) already accumulates real order/telemetry/ledger data before any
formal epoch; that data informs execution realism but does not count toward
the mandate's 60-session minimum, which requires one immutable epoch.

**Phase 6 — parallel product work during the evidence window (pick by owner
preference, all non-runtime):**
**UI Phase 2 (owner-requested 2026-08-03, jumps to the front of this phase
— the owner is paper trading daily and these directly support it)** →
committee replay corpus + CLI surface → GR-4 data honesty → GR-7 product
completeness (fold in the allocation-service design here, per Codex's
recommendation, so the app keeps one authoritative sizing path).

**UI Phase 2 — four owner requests, grouped into implementation milestones:**

| # | Item | Owner request | Scope and constraints | Size |
|---|---|---|---|---|
| UI-2a | Rename "Watchlist" to **"Buying"** | request 2 | **Completed and independently accepted after correction** at implementation `cbae8e6` plus review `3a29138`, together with UI-2c. User-facing navigation/copy says Buying; internal domain identifiers remain stable. | done |
| UI-2b | History **outcome filtering** | request 4 | **Completed and independently accepted 2026-08-04** at implementation `335c9fc` plus review hardening `9dcff80`. The exhaustive mapping lives beside `STATUSES`, unknown statuses fail-safe to Other/unknown, legacy `executed` stays unresolved, and the read-only SQL query applies filtering before the row limit. Outcome multi-select is primary, exact status is Advanced, and intersections are stated. Review found no runtime defect and added a reverse-mutation-proven large-history UI regression. | done |
| UI-2c | **Left-side navigation** replacing the top tab bar | request 1 | **Completed and independently accepted after correction** at implementation `cbae8e6` plus review `3a29138`. All 8 surfaces route from the sidebar with policy context separate. Review corrected one missed render-control effect: benign page inputs now survive navigation through an explicit whitelist, while approval/override/bulk-submit/cancel/emergency confirmations deliberately do not. | done |
| UI-2d | History **entry removal, persisted** | request 3 | **Implemented (2026-08-04), awaiting independent review.** Dismiss/archive only, never deletion: terminal `dismissed` status (canonical, non-inflight, outcome group Closed without fill), storage eligibility limited to pristine never-broker-touched `proposed`/`expired` rows (children, allocation-batch payload references, and execution-shaped payload evidence all refuse; unreadable batch payloads fail closed), preview-hash-bound all-or-nothing atomic dismissal with idempotent replay, `list_proposals` visibility flags, preview-first CLI `dismiss-proposals`, and the History Manage-unused-proposals expander with default-off archive visibility. Automatic expiry remains a separately approved follow-up; physical purge remains deferred and owner-authorized. | large |

UI-2b's frozen outcome groups are:

- **Awaiting decision:** `proposed`, `override_available`;
- **Processing:** `validating`, `approved`;
- **Broker working / unresolved:** `submitting`, `submission_unknown`,
  `reconciling`, `broker_accepted`, `partially_filled`, `cancel_pending`, and
  legacy `executed` (which means accepted, not confirmed filled);
- **Filled:** `filled` only;
- **Refused / failed:** `blocked`, `validation_failed`, `submission_failed`,
  `broker_rejected`;
- **Closed without fill:** `canceled`, `broker_expired`, `expired`, and the
  future `dismissed` status; and
- **Other / unknown:** any future value absent from the frozen mapping.

The implementation must define this map beside the canonical status constants
and test `set(mapping) == set(STATUSES)`; the UI imports it rather than
reconstructing financial lifecycle meaning.

Sequencing: **UI-2a + UI-2c completed and reviewed** as one navigation
milestone; **UI-2b completed and independently reviewed 2026-08-04**;
**UI-3 (Backtest page) completed and independently reviewed 2026-08-04**;
**UI-2d implemented 2026-08-04, awaiting independent review**. Automatic
expiry, if still desired, follows as
a separately approved lifecycle milestone; physical purge stays deferred.
UI-2d changes runtime durable state even though it grants no execution
authority. If a formal evidence epoch has started under model 1
(frozen runtime) before this work merges, deployment of these changes to the
operational machine waits for the epoch boundary; under model 2 they proceed
on the development side immediately.

Then: proposal-history physical purge remains deferred as before.

**UI-3 — interactive Backtest page (owner-requested 2026-08-04, inserted
into this phase ahead of UI-2d at the owner's direction):**

The owner asked to set up signals and run backtests directly in the UI,
with a graphic showing the result. This is a **read-only research
surface** — the plan below was written before implementation and is the
milestone's contract:

1. **Scope.** One new sidebar page, "Backtest", that (a) selects one of
   the existing price-only `scan_fn` signals from `signals/` (dip/up
   z-score, momentum, relative dip/up, 52-week breakout, 52-week-high
   proximity, vol-scaled momentum — PEAD/fundamentals are excluded in v1
   because they need an earnings feed, and residual momentum/reversal and
   idio vol because they refuse to run without a precomputed residual or
   benchmark feed), (b) exposes that signal's own parameters as widgets
   from a
   frozen inventory, (c) chooses data source, universe scope (whole
   universe or one basket), lookback, and hold horizons, (d) runs the
   walk-forward engine on demand, and (e) renders a multi-horizon summary
   table plus a cumulative-net-return chart per signal direction.
2. **Composition, not reimplementation.** The page calls the SAME
   `backtest/engine.py` functions the CLI scripts call
   (`run_multi_horizon_backtest`, `summarize_multi_horizon`) through a
   thin pure module (`backtest/interactive.py`) holding the frozen signal
   inventory, strict parameter validation (unknown signal or parameter
   fails closed), and chart-frame builders. No backtest math lives in the
   Streamlit script.
3. **Research honesty is part of the definition of done.** Synthetic data
   is the default source and every synthetic result is labeled as a
   plumbing check whose expected win rate is ~50%. Real-data results are
   labeled exploratory: not point-in-time, no multiplicity correction, and
   an on-page statement that confirmatory significance runs only in the
   frozen CLI pipeline (`run_significance_check.py` /
   `run_out_of_sample_check.py`). The page must not compute or display a
   pooled significance number.
4. **Runtime behavior.** Runs execute only on an explicit button click;
   results persist in session state so navigation and widget interaction
   do not re-trigger computation; real-data fetches are cached with a TTL;
   entry timing is the executable `next_open` default and is displayed,
   not chosen.
5. **Boundary.** The page has no path to proposals, approvals, orders,
   policy, or the research registry: no action-shaped controls, no
   registry writes, no execution imports from `backtest/interactive.py`
   (structurally tested). A good-looking chart must lead nowhere.
6. **Tests.** Inventory/validation/chart-frame unit tests; an AppTest
   proving the page renders, a synthetic run completes end to end on a
   small basket/lookback, and the exploratory labeling is present; the
   reachability suite gains the page; the import-boundary suite still
   passes.

Size: medium. Read-only; no persistence schema, lifecycle, or authority
change. UI-2d follows after this milestone's review unless the owner
reorders again.

Status: **completed and independently accepted after correction on
2026-08-04** at implementation `198339d`, documentation `d664402`, and
review correction `540467e`. The submitted architecture and authority
boundary were sound, but review corrected two P2 research-correctness gaps:
empty/partial provider data and impossible signal/history combinations can
no longer look like a fully covered zero-signal run, and the composition
helper no longer truncates fractional integer parameters or accepts invalid
horizons/slippage. Actual coverage, horizons, entry timing, and slippage are
stored with the session result; partial real-data coverage is disclosed.
Review also strengthened exact-frame UI/engine equivalence, real-data caveat
coverage, and the transitive research/authority import boundary. Corrected
validation passed 88 focused tests and 2,613 full-suite tests with 1 skipped
and 25 known warnings; compileall and diff checks were clean. No result was
promoted and no proposal, policy, registry, broker, schema, scheduler, epoch,
ML/LLM, or execution-authority behavior changed.

Sequencing after UI-3 review: **UI-2d is next**, subject to explicit owner
direction. Automatic expiry remains separate and physical purge remains
deferred.

**Phase 7 — data purchases, whenever decided (independent of code):**
membership vendor decision → Databento statistics/reference captures →
universe/cutoffs artifacts → real authoritative build → real ML discovery/
confirmation under the review-gated campaign.

**Deliberately queued indefinitely:** AI strategy authoring (its own plan
sequences it after ML-LR and GR complete), AI debate (open value question),
MCP (fails its own activation gate), GR-8 (requires everything above plus
explicit authorization).

---

## 9. Owner decisions required (consolidated, deduplicated)

1. ~~GR-1D go-ahead/review~~ — **RESOLVED 2026-08-03: granted,
   implemented, merged as PR #120, and independently accepted at `2f37210`.**
   Still open from this item: epoch model 1 vs 2 (§7).
2. Approve the mandate (or first revise its DRAFT §2 targets) — the only
   promotion gate satisfiable today.
3. ~~GR-5 alert delivery channel~~ — **RESOLVED 2026-08-03:** immediate
   critical alerts use Windows desktop toasts; warnings batch into the daily
   briefing. Webhooks remain out of scope.
4. Elevated Windows window for task-account creation + scheduler install;
   credential rotation at the same time.
5. Operator DB path: keep `data/trading_assistant.db` or adopt the runbook's
   `data/paper.db`.
6. Historical-membership vendor selection and funding (not Databento).
7. Databento statistics/reference budget + ticker/session range;
   Reference-API subscription confirmation.
8. Who writes/reviews the vintage-correct adjustment builder; who signs the
   `SpecReviewAttestation` for the volatility discovery spec.
9. Handling of the 118 mixed-provenance equity snapshots (AP-3).
10. ~~Whether UI feature controls jump ahead~~ — **RESOLVED 2026-08-02: yes,
    UI controls are Phase 1** (owner priority change to support daily paper
    trading from 2026-08-03).
11. ~~UI design's four open decisions~~ — **RESOLVED 2026-08-02** with the
    defaults both audits recommended: (a) session-state preferences first,
    durable persistence only if re-toggling proves annoying; (b) policy
    edits write the sidebar-selected policy file through the full protected
    workflow (no new policy-record store yet); (c) existing Briefing/
    Watchlist suggestion surfaces remain alongside the dedicated tab;
    (d) the master AI preference is a hard gate ANDed with per-feature
    toggles.
12. Whether strategy-tool commit `a656015` can be retrieved — **OPEN again
    after independent verification 2026-08-03:** neither the commit nor its
    former local branch resolves in this checkout or the fetched refs. Treat
    that work as unavailable unless another machine or backup still has it;
    do not plan against it as preserved implementation.
13. Whether AI debate is worth building at all (its own doc doubts it).
14. ~~`.gitignore` extension for ML artifact paths (AP-2)~~ — **RESOLVED
    2026-08-03:** `artifacts/` is ignored wholesale and regression-tested.

---

## 10. What this plan deliberately does not do

It does not restate every sub-check of every milestone (the per-milestone
plans, archived in `docs/reference/`, remain authoritative for their
internals); it does not adjudicate GR-1's "thin composition layer" DoD
(that is GR-1E's question); it does not propose starting any
authorization-gated work; and it does not treat any synthetic/fixture
result as market evidence anywhere. This adopted plan replaces the need to
juggle individual plan docs for day-to-day sequencing, while leaving those
docs as the detailed specs they are. Keep it current: when a phase
completes or the owner reorders priorities, update THIS file (and
`docs/SESSION_HANDOFF.md`) rather than resurrecting per-plan sequencing.
