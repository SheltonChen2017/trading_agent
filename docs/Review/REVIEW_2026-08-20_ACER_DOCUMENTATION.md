# Independent review - Analyst-Consensus ETF Rotation documentation

Review date: 2026-08-20  
Review branch: `codex/review-acer-docs-20260820`  
Base: `6f571c2f2366de0b2f6ea9fa6c27c2556791ba4e`  
Submitted branch/head: `origin/user/claude/acer-replaces-sbp-20260820` at `f3b960d2d15e54842b198bc11a0c82b51a50c364`  
Merged review head: `origin/main` at `6cdb423b67aefc6c62f2dc35cd27cfb33c049772`

## Scope and disposition

The owner supplied `docs/reference/analyst-consensus-etf-strategy.pdf` as the
design narrative. It was visually rendered and read in full (nine pages). The
PDF is legible, consistently formatted, and correctly labels itself as a
research framework rather than investment advice. Its revision-first signal,
point-in-time holdings requirement, controls, staged gates, and separation of
1x, bearish, and leverage testing are faithfully represented by the Markdown
contract. The Markdown contract correctly governs where it adds the repository
safety requirements the narrative omits: owner freeze, point-in-time audit,
look budget, result ledger, and no execution authority.

| Commit | Disposition | Notes |
|---|---|---|
| `f3b960d` | Accepted after correction | The ACER contract was a sound draft and correctly kept all research and execution actions blocked. It left stale SBP-first entry points, a stale archive-index status, and an unverified machine-local SBR absence claim. These are corrected by the review commits. |
| `6cdb423` | Accepted after correction | PR #286 merge; its tree carries the submitted change relative to first parent and introduces no separate conflict-resolution behavior. The same documentation findings apply. |

## P0-P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| ACERDOC-001 | P3 | Fixed | `f3b960d` | `ACTION_PLAN_2026-08-20.md`; `SESSION_HANDOFF.md` | Current entry points still said Strong-Buy/SBP-0 was the priority and next decision after ACER replaced it. A reader following the top of the handoff could start the superseded program. | The ACER contract and the action-plan ACER section say ACER-0 is next, while the handoff introduction/read order said Strong-Buy first and SBP-0 freeze. | The active handoff and action plan must give one usable next step. | Rewrote current entry points and resume prompt for ACER-0; retained SBP only as historical context. | Active-document consistency tests. |
| ACERDOC-002 | P3 | Fixed | `f3b960d` | ACER plan; SBR preregistration; action plan; handoff | Documents stated that the SBR task was never installed and zero snapshots existed even though the action plan says the machine-local state was never measured. | Contradictory claims in the same current documentation set. | Absence from Git is not proof of absence on the operational machine; false certainty would corrupt future evidence accounting. | Kept the closure and prohibition, but now state only that no snapshot is committed and require measurement before asserting verified absence. | Cross-document text review; active-document consistency tests. |
| ACERDOC-003 | P3 | Fixed | `f3b960d` | `docs/reference/README.md` | The archive index advertised the superseded SBP plan as a draft pending owner adoption and omitted ACER. | SBP's own status is SUPERSEDED and the action plan names ACER priority 1. | The archive index is a common entry point and must not direct work to an obsolete owner decision. | Added ACER and marked SBP superseded in the index; added a regression test for that relationship. | New focused regression test; mutation: changing the SBP row back to “pending owner adoption” fails it. |
| ACERDOC-004 | P3 | Fixed | `6cdb423` | `SESSION_HANDOFF.md`; `ACTION_PLAN_2026-08-20.md` | Current topology and resume instructions stopped at PR #285 / `6f571c2` although PR #286 had merged the ACER snapshot to `6cdb423`. | `origin/main` resolves to `6cdb423`; PR #286 is the reviewed merge. | A handoff must identify the actual starting tree and current review range. | Recorded `6cdb423`, PR #286, and the exact ACER review range while preserving earlier history as historical. | Topology reachability and active-document tests. |

## Result

Conditional acceptance pending final validation: ACER remains a **DRAFT**.
Nothing in this review adopts ACER-0, purchases data, queries QuantConnect,
installs a capture task, creates an order, changes an evidence epoch, or
creates any result. The next permitted step is the owner's ACER-0 decision;
after that, ACER-1 must independently audit the selected vendor and holdings
availability before any backtest.
