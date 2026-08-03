# ACTION_PLAN (Claude) — consolidated done / remaining ledger

Prepared: 2026-08-02, by Claude, at `origin/main` = `ff8c16e` (post PR #112).
Companion: `ACTION_PLAN_codex.md` (Codex's independent version). The two are
to be cross-reviewed and merged into one final plan.

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
the LLM committee foundation is built and gated. What does not exist is:
the last two slices of the execution-kernel split (GR-1D/1E), all of GR-2
through GR-7, every AI *product* plan beyond the committee (strategy
authoring, debate, allocation service, MCP, proposal cleanup, UI settings —
all ~0% built by design), and — most importantly — **any operational
evidence at all**: zero scheduled tasks installed, zero evidence epochs, zero
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
| Execution-kernel import boundary: no direct or transitive path from kernel/assistant/execution/risk roots into `ml` or proposal generation | `tests/test_ml_import_boundary.py` (transitive graph walk, fails closed on unresolvable imports) | reviewed |
| Order lifecycle: idempotent submission, ambiguous-outcome reconciliation, replacement chains, absence-age grace, reservation accounting, telemetry-before-submission | `assistant/execution_service.py` (facade, 1,094 lines), `assistant/order_lifecycle.py`, `assistant/order_reconciler.py` | multiple review rounds |
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

---

## 3. IN PROGRESS — started, not finished

| Item | Remaining | Size |
|---|---|---|
| **GR-1D** — extract the 221-line `reconcile_submission()` (`execution_service.py:697-917`) behind call-time DI | characterize every branch first; enumerate every facade-resolved runtime global (the lesson of GR-1C, three times over); mutation-test confirmed absence, unconfirmed lookup, fresh-404 grace, replacement chains, journal failures | 1 milestone + review |
| **GR-1E** (conditional) — thin the 281-line `execute_approved_paper_proposal` composition + 2 recovery wrappers, then declare GR-1's "thin composition layer" DoD met or explain the residual | assess after GR-1D | 0–1 milestone |
| **Committee release gates** — ADR requires ≥50 frozen replay cases (0 exist), memory-poisoning cases (0), broader injection corpus (3 seeds), a CLI `review unavailable` surface (none); only then remove the experiment gate | corpus authoring + CLI wiring | 1–2 milestones |
| **ML-FS-6 real discovery/confirmation** — spec `research/ml_specs/volatility-discovery-v1.json` is review-ready; no `SpecReviewAttestation` exists | blocked on owner-designated reviewer + real PIT data | owner + data |

---

## 4. NOT STARTED — planned code work, verified absent

| Milestone | Scope (one line) | Verified-absent marker |
|---|---|---|
| GR-2 risk-check registry | one ordered registry of named checks with `applies_at` phases replacing the hand-written ~600-line gate sequence | zero hits for `applies_at`/registry names |
| GR-3 fault-injection drills | `tests/faults/` + `scripts/run_fault_drill.py`, 9 named faults, immutable drill records | neither path exists; only 1 of 5 required drill types has any producer |
| GR-4 data-layer honesty | `PriceSource` protocol, staleness SLAs, provider health, split-between-snapshot-and-submit detection, degradation banner | no protocol in `data/`/`assistant/`; GR-0's `data_integrity` dimension is blocked-by-design until this lands |
| GR-5 alert delivery | a real channel + delivery records + weekly self-test + operator dashboard; alerts are currently recorded but never delivered | no transport code at all |
| GR-6 recovery/portability | off-machine backup restore, secrets audit, key rotation, portable scheduler, second-machine stand-up proven once | zero matches for all markers |
| GR-7 product completeness | mandate-target rebalance proposals, tax-aware sell preview, performance attribution, annual tax export (wash sales), idle-cash management | `wash_sale`/`idle_cash`/attribution: zero hits |
| UI feature controls (M1) | Settings & Features tab (3 control classes), provider/safety status panels, Ticker Suggestions surface — **read-only for policy fields in M1** | UI still has exactly 5 tabs |
| UI feature controls (M2) | protected `allow_new_positions` policy-edit workflow (fingerprint change + proposal invalidation warning) | absent |
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
| AP-1 | P2 | **Operator DB schema is stale**: `execution_telemetry_events` and `portfolio_capture_sessions` are declared in `assistant/storage.py` but absent from `data/trading_assistant.db` (24 tables present). Telemetry/capture chains cannot run until current code opens the DB. | open the DB once with current code before any epoch; verify with `PRAGMA table_info` |
| AP-2 | P2 | **`.gitignore` gap**: ML runtime writes `artifacts/shadow.json`, `artifacts/model/`, `artifacts/{datasets,experiments,reviews}/` — none ignored. First scheduled run dirties the worktree, and evidence capture **refuses a dirty worktree** → silent cadence failure. | extend `.gitignore` before any task install |
| AP-3 | P3 | 118 `portfolio_equity_snapshots` rows are mixed briefing/test-pollution provenance (pre-2026-08-02); any evidence report over them is unreliable | treat pre-2026-08-02 rows as non-evidence; decide retention at epoch start |
| AP-4 | P3 | Doc staleness cluster: `validate.py` figure 479→490 (grew in `7f431b6`); characterization-suite docstring still says "2,040 lines"; STATUS "corrects" a 1,450 figure the plan never contained; GR-1D/1E exist only in SESSION_HANDOFF, absent from plan and status docs; ML status doc has 3 internally stale paragraphs (spec library "not built" vs delivered; "calibration emitted empty" vs wired; ML-FS §2 overstates ML-FS-6) | one doc-reconciliation commit |
| AP-5 | P3 | 4 of 5 `REQUIRED_PROMOTION_DRILLS` have no producer (only `backup_restore` does) — structurally unproducible until GR-3/GR-5 | note in GR-3/GR-5 scope; do not fake |

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

## 8. Proposed sequencing (Claude's recommendation, for negotiation with Codex)

**Phase 0 — hygiene (days):**
AP-1, AP-2, AP-4 doc reconciliation; add GR-1D/1E to the GR status doc.

**Phase 1 — finish the kernel (1–2 milestone cycles):**
GR-1D (reconciliation extraction, characterize-first) → GR-1E assessment →
declare GR-1 done honestly against its DoD.

**Phase 2 — the two milestones that unblock operations:**
GR-5 alert delivery (owner picks the channel — decision needed) and GR-3
fault drills (produces the 4 missing drill types). These two convert the
promotion checklist's drill/alert gates from structurally-impossible to
executable. GR-2 (risk registry) rides along here as pure code consolidation.

**Phase 3 — operational deployment + epoch start (owner-heavy):**
elevated window → dedicated task account → install + verify 8 scheduled
tasks → ledger bootstrap/reconcile → **approve the mandate** → start the
first paper evidence epoch on a frozen commit → run all 5 drills inside it →
let the 60-session clock run. From here on, the machine collects evidence
while development continues un-deployed (model 2 discipline) or pauses
runtime changes (model 1).

**Phase 4 — parallel product work during the evidence window (pick by owner
preference, all non-runtime):**
UI feature controls M1 (near-zero risk, high daily usability) → committee
replay corpus + CLI surface → GR-4 data honesty → GR-7 product completeness →
proposal-history cleanup → UI M2 policy workflow → allocation service.

**Phase 5 — data purchases, whenever decided (independent of code):**
membership vendor decision → Databento statistics/reference captures →
universe/cutoffs artifacts → real authoritative build → real ML discovery/
confirmation under the review-gated campaign.

**Deliberately queued indefinitely:** AI strategy authoring (its own plan
sequences it after ML-LR and GR complete), AI debate (open value question),
MCP (fails its own activation gate), GR-8 (requires everything above plus
explicit authorization).

---

## 9. Owner decisions required (consolidated, deduplicated)

1. GR-1D go-ahead (next code milestone) — and epoch model 1 vs 2 (§7).
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
10. Whether UI feature controls M1 jumps ahead of Phase 2 (it safely can).
11. Session vs durable persistence for UI preferences; policy-edit mechanism
    for M2 (deferred decision, not urgent).
12. Whether to retrieve strategy-tool commit `a656015` from the old computer
    (verified unrecoverable from this clone) or declare it lost.
13. Whether AI debate is worth building at all (its own doc doubts it).
14. `.gitignore` extension for ML artifact paths (AP-2) — trivially yes,
    listed for completeness.

---

## 10. What this plan deliberately does not do

It does not restate every sub-check of every milestone (the per-milestone
plans remain authoritative for their internals); it does not adjudicate
GR-1's "thin composition layer" DoD (that is GR-1E's question); it does not
propose starting any authorization-gated work; and it does not treat any
synthetic/fixture result as market evidence anywhere. The final merged plan
(after cross-review with `ACTION_PLAN_codex.md`) should replace the need to
juggle individual plan docs for day-to-day sequencing, while leaving those
docs as the detailed specs they are.
