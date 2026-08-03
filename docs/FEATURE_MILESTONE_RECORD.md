# Completed Feature and Milestone Record

This file records only features and milestones that have met their definition
of done and completed required review. Follow
`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` when adding an entry.

Each entry must use this structure and contain exactly the two required prose
paragraphs beneath its heading. Replace the placeholders; do not retain the
labels as separate bullet points.

## `<Feature or milestone name>` — `<completion date>` — `<final commit>`

**Technical:** `<One paragraph describing the implemented behavior,
architecture, interfaces, data/schema changes, safety and compatibility
properties, and final validation in software-development language.>`

**Plain language:** `<One paragraph explaining the same completed
functionality, its value, and its limitations in terms a high school student
can understand.>`

---

Entries for milestones completed before this record existed (GR-0, GR-1A,
GR-1B, and earlier ML milestones) may be backfilled from
`docs/GENERAL_READINESS_STATUS.md` and `docs/ML_IMPLEMENTATION_STATUS.md`
when the owner prioritizes it; absence of an entry below does not mean the
milestone was not completed and reviewed.

## GR-1C — validation orchestration behind call-time dependency injection — 2026-08-02 — merge `2882889` plus follow-up review `c1de927`

**Technical:** GR-1C moved the 315-line body of
`validate_proposal_for_execution()` from the `assistant/execution_service.py`
facade into `assistant/execution_kernel/validate.py::run_proposal_validation()`
behind a frozen `ProposalValidationDeps` contract that the facade constructs
from its own module namespace on every call, so every historically
monkeypatchable facade name — the risk gate `validate_trade_intent`, policy
fingerprint, stored-intent parsing, pending-buy exposure, earnings resolution,
the deferred broker import, `datetime`, `timezone`, `Decimal`, `TradeIntent`,
`to_decimal`, the `ProposalValidationOutcome` constructor, and the
data-integrity/infrastructure failure-classification constants — remains a
live call-time seam after the move. The kernel function performs zero
module-global runtime reads, pinned by a symtable-based structural guard;
each injected seam has a behavioral characterization test proven red on the
pre-correction tree and verified to catch reverse-mutations back to
kernel-local resolution. Validation stays read-only (it reads durable state
and queries the broker; it never claims, transitions, reserves, or submits),
the check order is unchanged, exception identities and the full pre-GR-1C
facade import surface are identity-pinned, and the one deliberate residual —
the `resolved_failure_class` property's kernel-resolved fallback constants —
is documented and pinned by its own test. Completed across implementation
`b4d9b1f`, independent review `465df8d` (merged as PR #109/#110), follow-up
review `c1de927`, and an independent confirmation round that re-verified all
corrections red/green with a six-of-six mutation-detection sweep.

**Plain language:** Before the trading assistant acts on a trade the owner
approved, it runs one final safety checklist: is the approval still fresh, do
the rules still allow this trade, is the emergency stop off, is the price
quote current, and more than a dozen similar questions. That checklist used
to live buried inside one enormous file; this milestone moved it into its own
small, clearly-named module without changing a single question or the order
they are asked in. The subtle part is that the checklist depends on tools —
a clock, a price feed, the rulebook — and our tests work by swapping those
tools for fakes (a frozen clock, a pretend broker) to prove the checklist
reacts correctly. So the move was done by handing the checklist an explicit
toolbox, rebuilt fresh on every call: swap any tool in the outer layer and
the checklist genuinely uses your swap, exactly as it did before the move.
Automated tests now sabotage each tool on purpose and confirm the sabotage is
always noticed. The limitation to remember: this is internal plumbing that
makes the safety code easier to audit and harder to break by accident — it
adds no new trading abilities, and it is not evidence that any trading
strategy makes money.
