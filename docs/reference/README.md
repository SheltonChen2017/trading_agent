# Archived implementation plans and designs

Archived 2026-08-02 when the owner adopted `docs/ACTION_PLAN_2026-08-02.md`
as the single go-to sequencing document (agreed by both Claude and Codex
after independent audits; see PR #113/#114 for the two source drafts).

These documents are **not deleted and not obsolete**: each remains the
authoritative *detailed specification* for its own milestones — definitions
of done, safety gates, test requirements, and design rationale. What they no
longer control is *sequencing*: which milestone happens next is decided by
the action plan, not by any individual document's own "begin with X"
instruction (several of those instructions were already stale when archived;
see the action plan's staleness ledger).

When the action plan schedules a milestone, read that milestone's full
section in the relevant document here before implementing — the action plan
deliberately does not restate per-milestone internals.

| File | Still authoritative for |
|---|---|
| `GENERAL_READINESS_IMPLEMENTATION_PLAN.md` | GR-0..GR-9 milestone definitions, DoD, and safety gates |
| `ML_IMPLEMENTATION_STRATEGY.md` | ML-1..ML-10 architecture and boundary rationale |
| `ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md` | ML-LR-0..11 integrity/evidence/promotion gates |
| `ML_FULL_SYSTEM_EXECUTION_PLAN.md` | ML-FS-0..9 execution overlay definitions |
| `AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` | AS-0..AS-11 definitions (AS-11 prohibited) |
| `AI_DEBATE_DESIGN.md` | debate-surface design + its open value question |
| `ALLOCATION_SERVICE_DESIGN.md` | allocation-service design (to fold into GR-7) |
| `MCP_JUSTIFICATION_AND_IMPLEMENTATION.md` | MCP activation criteria and read-only design |
| `PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` | dismissal/expiry design (purge separately gated) |
| `UI_FEATURE_CONTROLS_DESIGN.md` | Settings/AI-toggle/policy-workflow/suggestions design |
| `ACTION_PLAN_codex.md` | Codex's independent audit draft (merged into the adopted plan) |

Documents that did NOT move remain live in `docs/`: status ledgers
(`GENERAL_READINESS_STATUS.md`, `ML_IMPLEMENTATION_STATUS.md`), process
documents, `SESSION_HANDOFF.md`, `MANDATE.md`, `ARCHITECTURE_DEBT.md`,
`OPERATIONS_RUNBOOK.md`, `LIVE_PROMOTION_CHECKLIST.md`,
`DATABENTO_DATA_SOURCE.md`, the committee ADR, and historical review
records.

Code comments written before the archive may still cite `docs/<name>.md`
paths for these files; those citations refer here.
