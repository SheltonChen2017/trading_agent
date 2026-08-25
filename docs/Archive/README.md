# Documentation archive

This folder preserves completed, superseded, and obsolete material. Archiving
is not deletion: historical evidence, review dispositions, preregistrations,
and provenance remain intact and searchable, but they no longer look like
current instructions.

- `Plans/` — completed, superseded, or replaced plans. "Completed" describes
  the *implementation*, not always the contract: `SHADOW_OBSERVATION_DESIGN.md`
  is archived because SHW-1..4 shipped, yet it remains the governing
  observation and sufficiency contract for `overlay-epoch-001`, which is still
  accruing toward a 24-month floor. Archived never means "safe to ignore when
  the stream it governs is live" (CDR-008).
- `Research/` — closed research programs' preregistrations and methods. The
  permanent run ledger is **not** here: `docs/research/alpha-result.md` stays
  active, because every future real-outcome execution — ACER's included — must
  append to it and its lifetime look count keeps accruing (CDR-004).
- `Review/` — completed independent review and counter-review reports. New
  reports are written here once their round closes; there is no `docs/Review/`.
- `Operations/` — historical deployment or diagnosis records whose current
  facts are now carried by `docs/operations/OPERATIONAL_FACTS.md`.
- `Reference/` — retired indexes and examples retained for provenance.
- `Session/` — replaced session handoffs. They preserve complete historical
  context but are not current resume instructions.

The superseded Strong-Buy plan is preserved at
`Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md`. Its former successor, ACER V1, was
itself superseded on 2026-08-25 and is preserved at
`Plans/ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md`. The current strategy
contracts are under `docs/Strategy Description/`.

Do not resume work from this folder merely because an archived document says
"next." The current sequence is always in `docs/ACTION_PLAN_2026-08-20.md`.
