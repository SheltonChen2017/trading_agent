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
assessment. What does not exist is: all of GR-2
through GR-7, every AI *product* plan beyond the committee (strategy
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

The Streamlit app now has seven tabs, including Settings & Features and a
research-only Ticker Suggestions surface. Session-scoped AI preferences gate
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

## 4. NOT STARTED — planned code work, verified absent

| Milestone | Scope (one line) | Verified-absent marker |
|---|---|---|
| GR-2 risk-check registry | one ordered registry of named checks with `applies_at` phases replacing the hand-written ~600-line gate sequence | zero hits for `applies_at`/registry names |
| GR-3 fault-injection drills | ~~9 named faults + drill harness~~ **IMPLEMENTED 2026-08-03** (branch `user/claude/gr-3-fault-drills-20260803`): `tests/faults/` (11 drills: the plan's 9 rows + the two 2026-08-02 isolation regressions) + `scripts/run_fault_drill.py` (hash-stamped report; records ambiguous_submission/restart_recovery/kill_switch drill rows, epoch-bound or verification_only). Awaiting independent review | — |
| GR-4 data-layer honesty | `PriceSource` protocol, staleness SLAs, provider health, split-between-snapshot-and-submit detection, degradation banner | no protocol in `data/`/`assistant/`; GR-0's `data_integrity` dimension is blocked-by-design until this lands |
| GR-5 alert delivery | a real channel + delivery records + weekly self-test + operator dashboard; alerts are currently recorded but never delivered | no transport code at all |
| GR-6 recovery/portability | off-machine backup restore, secrets audit, key rotation, portable scheduler, second-machine stand-up proven once | zero matches for all markers |
| GR-7 product completeness | mandate-target rebalance proposals, tax-aware sell preview, performance attribution, annual tax export (wash sales), idle-cash management | `wash_sale`/`idle_cash`/attribution: zero hits |
| Allocation service | delta-vs-target primitive, calibrated regime threshold, cadence, universe list, sizing | only the `strategy_evaluations` table exists |
| Proposal-history cleanup | `dismissed` status, expiry sweep, preview-first CLI, History UI (10 steps; physical purge stays deferred) | 19 statuses, no `dismissed`; only `prune-packets` exists (decision packets, not proposals) |
| AI strategy authoring AS-0..AS-7 | prose → StrategySpec → compiler → evaluation plan → orchestrated backtest → dossier → registry | 0% — no `strategy_lab/`, no DSL, no Backtest tab |
| AI debate surface | `assistant/ai_debate.py` parallel-framing design | 0%; its own doc questions whether the safe version is worth building |
| MCP read-only server | `mcp_bridge/` + 9 tools | 0%; **fails its own §3.6 activation gate today** (GR-5 dashboard hasn't shipped) |

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
| AP-5 | P3 | 4 of 5 `REQUIRED_PROMOTION_DRILLS` have no producer (only `backup_restore` does) — structurally unproducible until GR-3/GR-5 | note in GR-3/GR-5 scope; do not fake — **GR-3 (2026-08-03, pending review) adds producers for ambiguous_submission, restart_recovery, and kill_switch; only alert_delivery remains unproducible until GR-5** |

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
`docs/REVIEW_2026-08-03_GR1E_ASSESSMENT.md`. Phase 4 (GR-5 alert delivery +
GR-3 fault drills, with GR-2 riding along) is next; GR-5's channel remains an
owner decision.

**Phase 4 — the two milestones that unblock operations (ACTIVE):**
GR-3 fault drills are IMPLEMENTED 2026-08-03 on
`user/claude/gr-3-fault-drills-20260803` (11-drill matrix + harness;
producers added for ambiguous_submission/restart_recovery/kill_switch),
awaiting independent review. GR-5 alert delivery remains blocked on the
owner's channel decision and will add the last drill producer
(alert_delivery). These two convert the promotion checklist's drill/alert
gates from structurally-impossible to executable. GR-2 (risk registry)
rides along here as pure code consolidation.

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
committee replay corpus + CLI surface → GR-4 data honesty → GR-7 product
completeness (fold in the allocation-service design here, per Codex's
recommendation, so the app keeps one authoritative sizing path) →
proposal-history cleanup.

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
3. GR-5 alert delivery channel (email / webhook / push / other).
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
12. ~~Whether strategy-tool commit `a656015` can be retrieved~~ — **RESOLVED
    2026-08-03:** the commit and local branch
    `codex/ai-strategy-tool-doc-v2-20260802` are present in this checkout but
    remain local-only and must be pushed or transferred before changing
    computers if the owner wants to preserve them.
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
