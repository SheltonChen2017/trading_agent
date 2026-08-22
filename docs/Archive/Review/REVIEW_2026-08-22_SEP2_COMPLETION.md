# Independent review — SEP-2 completion tranche

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1/P2; two P3.**

This tranche declares SEP-2 complete and writes a durable
`FEATURE_MILESTONE_RECORD.md` entry, so the review question is not only "is the
code right" but **"is the milestone genuinely done against its written
definition"** — `CLAUDE.md` §12 forbids calling a milestone complete because
scaffolding exists.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/counterreview-sep2-filing-completion-20260822` |
| Review head (full object name) | `c7087714be8a976a401472f1710e4faa5e1d55d6` |
| Base | `fa32156307af0da5322694af5595b1e5b831efc6` (my prior review head) |
| Review branch | `user/claude/review-sep2-completion-20260822` |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `624a7fd` | transitive closure of the relocated LLM-contract boundary (SEP2F-003) | **accepted** | none |
| `996ccbc` | SEP-2 completion classification and definition-of-done certificate | **accepted after correction** | SEP2C-001 |
| `f0b3e7c` | counter-review record of my filing-ownership review | **accepted** | none |
| `b29ae2f` | completion state record | **accepted after correction** | SEP2C-002 |
| `1c2afff` | `FEATURE_MILESTONE_RECORD.md` entry | **accepted** | none |
| `c708771` | handoff finalization | **accepted** | none |

No merge commit in the range.

## 3. Is SEP-2 genuinely complete? Measured against its four written bullets

| Plan bullet | Assessment |
|---|---|
| classify every `scripts/` entry point | **Met.** 75 files owned exactly once, recursively enforced, dynamic and relative import forms refused. |
| give each product its own launch surface and dependency declaration | **Met, with a stated reading.** Each product owns launchers (8 assistant, 56 research) and **product-owned launchers carry zero cross-product imports**, which is guarded. Dependency manifests exist and are checked against *actual imports*, not only against each other. No separate per-product launcher binary was created, and none is required by the bullet's wording. |
| split shared data access into explicit interfaces and product-owned implementations | **Met.** Every `data/*.py` is a package marker, neutral contract, provider-neutral service with a written rationale, or a product-owned implementation; `shared_provider_debt` is **0**; and neither product may import the other's provider implementation. |
| keep licensed datasets research-side | **Met and strengthened.** Licensed ACER/Databento surfaces stay out of execution products, and the relocated LLM-derived contract is now blocked both directly and transitively. |

**Residuals reconcile exactly** — declared against measured: composition files
11 = 11, crossing roots 6 = 6, operator-database importers 4 = 4. SEP-1's
invariants hold: direct cross-product imports **0**, authority-to-research
paths **0**.

**The completion claim is honest about what remains.** The plan, the handoff and
the milestone record all state that 11 composition files still connect the
products and are inputs to SEP-3 rather than permanent exceptions. The
milestone record's plain-language paragraph says so in as many words — "Eleven
integration files still connect the products inside this repository" — and
explicitly disclaims creating the new repository, changing scheduled jobs,
touching the paper account, or testing a strategy. Both paragraphs describe the
same scope and neither claims live authority or market edge.

I accept the completion claim.

## 4. Codex's closure of the gap I disclosed

My previous review declared, as untested surface, that my SEP2F-001 guard
covered only **direct** imports and that a transitive path through another
neutral `data` module would not be caught. `624a7fd` closes exactly that with
`test_execution_products_cannot_reach_llm_derived_neutral_contracts`.

Verified by mutation rather than accepted: making `data/mandate_evaluation.py`
— which `assistant/mandate.py` imports — pull in `data.filing_extraction`
creates the indirect path `assistant.mandate → data.mandate_evaluation →
data.filing_extraction`. Codex's transitive guard **fails** on it. My own
direct guard does not report a clean failure there (the induced cycle breaks
collection of the test module), which is precisely why the direct-only form was
insufficient. The closure is correct and it is the right generalization of my
finding.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2C-002 | P3 | Closed | `b29ae2f` | `docs/SESSION_HANDOFF.md` sequencing line | The line was re-attributed from "(owner, 2026-08-21)" to "(owner, 2026-08-22)", but no owner decision on that date is recorded in the Action Plan or anywhere else. | `grep` for an owner decision dated 2026-08-22 across the Action Plan returns nothing; the prior head carried the 2026-08-21 attribution. | The substance is correct — SEP-3 follows from the plan's own milestone ladder — but re-dating the attribution presents a mechanical consequence as a fresh owner act. This repository has a named lesson for exactly that (CDR2-002: a wording chain converted a pending authorization into an assumed one without anyone deciding it), and owner attribution is load-bearing here because owner decisions are what lift gates. | Restored to the standing 2026-08-21 direction, stating explicitly that no separate owner decision was taken on 2026-08-22 and that advancing to SEP-3 grants no authority of its own. | `test_active_document_consistency.py` passes; the attribution now matches the only recorded owner direction. |
| SEP2C-001 | P3 | Closed | `996ccbc` | `tests/test_project_separation_entrypoints.py`, `architecture/entry_points.json` | `test_sep2_definition_of_done_is_reconstructed_not_self_asserted` genuinely reconstructs the three residual counts, but four completion properties — `script_inventory_exhaustive`, `product_launch_surfaces_and_dependencies_pinned`, `data_ownership_exhaustive`, `licensed_research_boundary_pinned` — are hand-set boolean literals. Asserting `is True` on a literal proves only that the manifest says complete, so the certificate did not depend on the guards that establish it. | Mutation: disabling both `test_every_script_is_classified_exactly_once` and `test_data_ownership_is_exhaustive_and_shared_provider_debt_cannot_grow` left the certificate **green**, still certifying those exact properties as true. | The test's own name disclaims self-assertion, and it backs a durable owner-facing milestone record. A completion claim that can outlive the evidence for it is the same class as the name-versus-assertion drift found earlier in this milestone (SEP2L-001, CCX-002). | Each flag now names the guards that establish it (`enforcing_guards`), with a rationale note, and the certificate fails if a named guard is removed or renamed. | Two directions: disabling the two establishing guards **red**; silently renaming the licensed-boundary guard **red**; restored green 23/23. |

**What this finding is not.** The underlying facts were, and remain,
independently enforced by real guards — I re-ran each. This closes the
*linkage* between the certificate and its evidence, not a hole in the boundary
itself, which is why it is P3 and why I accept the completion claim rather than
disputing it.

## 5a. The SEP2F-002 guard fired on its first live use — on me

The guard I added last round, requiring every finding ID a SEP-2 review report
raises to appear in the current handoff, failed during this round's final
validation. The missing ID was **SEP2F-003** — Codex's transitive-closure
finding. My report named it; my handoff described the closure but never
mentioned the ID.

That is the same omission the guard exists to prevent, caught mechanically
rather than by a reviewer on the next round, roughly an hour after it was
written. Recorded because it is the evidence that asserting the relationship
was the right response to a defect I had twice resolved in prose and twice
repeated.

## 6. Validation on the final tree

| Check | Result |
|---|---|
| `tests/test_project_separation_entrypoints.py` | 23 passed |
| Complete suite | **4,533 passed / 0 failed / 25 warnings** in 775.83s — unchanged from Codex's 4,533; this round extended a guard rather than adding one |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | SEP2C-001 two directions; SEP2F-003 transitive closure verified via an indirect path; all restored |

## 7. Untested surface, stated plainly

- Completion is assessed against the plan's **written** bullets. "Give each
  product its own launch surface" is met under the reading that each product
  owns launchers that do not reach into the other; a reader expecting two
  separately installable applications would not consider that done, and SEP-3
  is where that becomes real.
- The `enforcing_guards` linkage checks that a named guard **exists**, not that
  it is meaningful. A guard could be hollowed out while keeping its name. That
  is a smaller gap than the one it closes, and no mechanical check distinguishes
  a real assertion from a vacuous one.
- The 11 composition files and 4 operator-database importers are bounded and
  declared, not removed. The operator database remains assistant-owned with
  research-hosted readers and writers inside reviewed key namespaces.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was accessed
  or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep2-completion-20260822`. With that chain closed, **SEP-3**
is the next milestone: a dry-run extraction manifest with retained history and
exact source commits, followed by the owner's choice between two repositories
plus an explicit shared package, or a permanently partitioned monorepo. SEP-3
authorizes no repository creation, history rewrite, deployment, credential
move, scheduled-task change, or operator-database move.
