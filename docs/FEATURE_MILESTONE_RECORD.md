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

## UI feature controls — 2026-08-03 — merge `4c8e959` plus independent review `a6d5254`

**Technical:** The Streamlit application now exposes seven tabs, adding a Settings & Features surface that separates session-only UI preferences, protected authoritative policy edits, and read-only provider/safety status, plus a dedicated research-only Ticker Suggestions surface. Optional-AI master and per-feature flags gate all four LLM call paths without changing deterministic content; `allow_new_positions` and `enable_strategy_proposals` updates validate a new frozen `TradingPolicy`, require the exact typed confirmation, atomically persist a bumped version and changed fingerprint, force a full-app rerun, and leave prior proposals fail-closed under the existing fingerprint check. The editor is bound to the selected policy path and content fingerprint, disabled suggestion sources make no provider call, and the dedicated tab avoids an unused paid curation call. No database schema or execution-kernel contract changed; paper mode, exact approval, kill switches, exposure checks, and live-trading friction remain intact. Independent review reproduced two P2 control-state defects red, corrected them, and validated 236 focused tests plus 2,427 passed, 1 skipped, and 26 warnings in the full Python 3.12.13 suite, with clean compilation and diff checks.

**Plain language:** The app now gives you one clear place to control optional features and see whether important safety systems and data providers are available. You can turn permission to open new paper positions on or off, but changing that rule requires typing a confirmation phrase; the app saves the change, updates the rulebook's identity, refreshes what it shows immediately, and makes older trade proposals unusable so they cannot sneak through under different rules. Tests used a temporary rule file to flip the real button off, on, and off again and confirmed that both the saved setting and the on-screen status changed every time. Stock-suggestion switches now truly stop sources that are turned off. These controls still cannot enable real-money trading, approve an order automatically, or turn a suggestion into a trade, and they do not prove that any stock idea will make money.

## Action Plan Phase 2 hygiene — 2026-08-03 — implementation `34ce463` plus independent review `36c69d3`

**Technical:** Phase 2 closed AP-1, AP-2, and AP-4 with a read-only-by-default `verify_database_schema()` contract and `verify-db-schema` CLI, an explicit `--apply` migration path through the production `AssistantStore` initializer, repository-wide ignoring of machine-local `artifacts/`, and reconciled general-readiness, ML, action-plan, and characterization documentation. Verification builds its reference schema through the real initialization path, requires every declared table and column, compares normalized definitions for every named index and trigger, reports missing and mismatched objects separately, and fails closed on absent databases or weakened enforcement; the independent review proved red that a same-named non-unique active-epoch index and no-op broker-order trigger had incorrectly passed the implementation, then corrected both definition checks. Migration tests preserve legacy rows, the operator database was checked read-only after a verified pre-change backup, and final validation passed 81 focused tests plus 2,441 passed, 1 skipped, and 25 warnings under Python 3.13.14 with clean compilation and diff checks. Table column types and constraints are not compared byte-for-byte, no execution-kernel behavior changed, and no policy, broker, scheduler, evidence epoch, or live authority was modified.

**Plain language:** The project now has a safe inspection command that checks whether its local database contains the pieces the current program expects before evidence collection begins. It only looks unless the owner deliberately asks it to apply upgrades, and it now checks what important safety indexes and triggers actually do instead of trusting their names; the review caught this by replacing two safeguards with weaker look-alikes and proving the original check was fooled. The project also ignores generated models, datasets, and licensed files so scheduled runs do not make the source tree appear modified, and its planning documents now agree about what is finished and what comes next. This is maintenance that makes later paper-operation evidence more dependable; it does not create a strategy, place an order, start evidence collection, or permit real-money trading.
