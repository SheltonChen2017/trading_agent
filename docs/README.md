# Documentation map

`docs/ACTION_PLAN_2026-08-20.md` is the only sequencing authority.
`docs/SESSION_HANDOFF.md` is the concise current cross-computer state. Read
those two first; do not infer current work from an archived report or a queued
plan.

## Current coordination records

- `ACTION_PLAN_2026-08-20.md` — priority, gates, and the next authorized step.
- `SESSION_HANDOFF.md` — exact branch/head, current status, validation, and
  resume instructions.
- `FEATURE_MILESTONE_RECORD.md` — completed milestones only.

## Current plan tracks

- `THREE_STRATEGY_PROJECT_DIRECTION.md` — main-line coordination record for
  the three parallel strategy branches and their later integration path.
- `Strategy Description/` — the three active strategy source PDFs, shared
  parallel-workflow contract, per-lane implementation records, and data-source
  register. The former ACER V1 plan is archived.
- `PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md` — architecture-track contract;
  it is currently paused. The exact frozen baseline and restart procedure are
  in `architecture/SEP3_FREEZE_STATE_2026-08-25.md`.

At most one plan per active track belongs at the root. A plan does not start
work by being present here; the Action Plan must schedule it.

## Supporting documentation

- `architecture/` — architecture decisions, debt, and bounded state records.
- `operations/` — current operational facts, runbooks, mandates, and status.
- `research/` — active research records and the permanent run ledger.
- `Strategy Description/` — active owner strategy specifications and lane
  records; PDFs are immutable inputs.
- `Plan/` — queued plans and preregistrations; not authorized by themselves.
- `process/` — mandatory review, handoff, and research-run procedures.
- `reference/` — current reference material.
- `Archive/` — completed, superseded, or replaced history. Archived “next”
  language is never current authority.

## Maintenance rules

Keep detailed evidence in its owning record. Keep the Action Plan concise.
Replace the current handoff when its topology or next-step narrative becomes
materially stale; preserve the replaced version under `Archive/Session/`.
Never copy review reports back to the root, and never duplicate an active plan
between the root and `Plan/`.
