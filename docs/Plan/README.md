# Queued implementation plans

This folder contains plans the owner may schedule later but that are **not
actively being implemented now**. Their specifications and safety gates remain
useful, but none of their internal sequencing language authorizes work. Only
`docs/ACTION_PLAN_2026-08-20.md` can move one of these plans into the active
slot at the root of `docs/`.

Current queued plans:

- `AI_DEBATE_DESIGN.md` — design only; not scheduled.
- `AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` — future advisory authoring
  work; no execution authority.
- `GENERAL_READINESS_IMPLEMENTATION_PLAN.md` — remaining readiness work.
- `HEDGE_POLICY_QC_PLAN.md` and `MAX_PROFIT_POLICY_QC_PLAN.md` — owner-deferred
  research families.
- `MCP_JUSTIFICATION_AND_IMPLEMENTATION.md` — gated proposal.
- `ML_FULL_SYSTEM_EXECUTION_PLAN.md` and
  `ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md` — future ML work; the
  current software/status record remains under `docs/operations/`.
- `THREE_SLEEVE_ENGINE_PLAN.md` — implemented through M3; optional M4 remains
  deferred and unauthorized, so the remaining plan is queued rather than
  active.
- `Research/` — frozen or proposed research contracts for later work.

When the owner activates a plan, move it to the root of `docs/`, update the
Action Plan and Session Handoff, and leave no second copy here.

**How many plans the root may hold (CDR2-004).** At most **one active plan per
track**, not one overall. There are currently two tracks and therefore two
plans at the root: the **research** track
(`ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md`) and the **architecture** track
(`PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`). A third root plan means either a
new track the Action Plan must name, or a plan that should have been archived.
The allowlist in `tests/test_active_document_consistency.py` enforces the
membership; this paragraph is the rule it enforces, so the rule cannot be
changed by editing the test alone.
