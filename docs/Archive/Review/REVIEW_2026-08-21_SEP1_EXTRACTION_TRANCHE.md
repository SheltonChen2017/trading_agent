# Independent review — SEP-1 first extraction tranche

Reviewed: 2026-08-21 by Claude.

Scope: the SEP-0 counter-review and the SEP-1 tranche, both merged to `main`.

- SEP-0 counter-review: `02d7a9e`, `6dfc0bc`, `9c12ac3`.
- SEP-1: `9c12ac3..a786074` — eight commits, 17 files, merged as PR #297 at
  `6499c18`.

Review branch: `user/claude/review-sep1-extraction-20260821`, created from
`origin/main` at `6499c18`.

**Outcome: accepted after correction.** No P0 or P1. Two P2 and one P3, all
corrected here. This is the first separation round that moves production code,
and the movement itself is clean.

---

## The headline claim is true, verified independently

SEP-1's central claim is that the one execution-authority-to-research path is
gone. I recomputed the transitive closure with my own scanner rather than
running the submitted guard: from every module under `assistant.allocation_batch`,
`assistant.execution_kernel`, `assistant.execution_service`, `execution/` and
`risk/`, following first-party imports through shared and unclassified roots,
**zero** paths reach `strategy_research`. The ledger's
`allowed_authority_research_paths` is correctly empty rather than emptied.

The extraction is also behaviour-preserving where it matters. I compared the
moved functions as normalized ASTs rather than reading the diff:
`_classify_leveraged` is byte-identical, and `build_portfolio_snapshot` and
`build_portfolio_snapshot_from_alpaca` differ **only** in local variable names
(`p` → `position`, `agg` → `aggregate`), one added type annotation, and
docstring text. No control flow, no validation, no error message except the one
carrying a renamed variable. The compatibility facades preserve object
identity, checked at runtime: `assistant.money.to_decimal is
data.financial_primitives.to_decimal`, `assistant.schemas.EvidenceStatus is
data.evidence_status.EvidenceStatus`, and
`assistant.context_builder.build_portfolio_snapshot is
assistant.portfolio_snapshot.build_portfolio_snapshot`. That matters more than
it looks: `ml/contracts.py` does an `isinstance` check against
`EvidenceStatus`, and a parallel copy would have broken every cross-product
evidence payload silently.

The decimal guard was not weakened. Its allowlist moved one entry
(`assistant/money.py` → `data/financial_primitives.py`) 1:1, gained nothing,
and still scans every tracked `.py` outside `tests/`, so the new location is
genuinely in scope.

Three new guards are directly responsive to cautions in my SEP-0 review: the
shared kernel may not import either product, facades must preserve identity,
and the allocation preflight must keep using the narrow module. The first is
the one I named as "the next boundary worth pinning, and cheap to add".

---

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `02d7a9e` | Accepted after correction | SEP0CR-001 is a valid finding against my own SEP-0 review: I advanced the handoff and Action Plan but left the separation plan's own status calling SEP-0 current. The guard added for it is the problem — SEP1R-002. |
| `6dfc0bc` | Accepted | Counter-review record. Accurate; accepts both my P2s and retains CDR2-005 open. |
| `9c12ac3` | Accepted | Handoff. |
| `18868d3` | Accepted after correction | The extraction itself. SEP1R-001 and SEP1R-003: the move deleted the recorded reasons behind the invariants it carried. |
| `035715a` | Accepted | Plan record; honest that SEP-1 is not complete. |
| `935c5dc` | Accepted | Review-pending state. |
| `7f8c47f` | Accepted | Decimal guard repointed to the canonical implementation; allowlist unchanged in size and still in scope. |
| `ed46797` | Accepted | Record. |
| `4f4d6c8` | Accepted after correction | Evidence for SEP1R-002: this commit exists only because the literal-pinning guard broke on a legitimate state change. |
| `cf9aeac`, `a786074` | Accepted | Handoff and final validation record. Its claimed **4,498 passed / 0 failed / 25 warnings** reproduces exactly on my own run of the same tree, and the mutation claims hold. |

---

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP1R-001 | P2 | Resolved | `18868d3` | `data/evidence_status.py` | The `EvidenceStatus` move replaced the enum's documentation with "labels describe research maturity only" and **deleted the per-member definitions**. The originals were operational definitions, not commentary: `CONFIRMED` meant "passed out-of-sample + all bootstrap layers + realistic execution/tax"; `REJECTED` meant "failed confirmation, look-ahead correction, or tax/cost modeling". Also lost: that status attaches **per claim, never per strategy**, with the SOXX/SOXL example — drawdown-reduction CONFIRMED while beats-buy-and-hold-on-CAGR REJECTED — which is the case that makes the distinction usable. | Diff of `assistant/schemas.py` against the new `data/evidence_status.py`. The statuses are consumed by `assistant/research_findings.json`, `ml/contracts.py`, `ml/experiments.py` and `ml/shadow_runtime.py`. | This repository's first rule is not overstating evidence, and this enum is the vocabulary that rule is written in. An undefined `CONFIRMED` does not stay undefined — it gets applied on weaker grounds than it has ever meant here, and nothing in code or tests would object. Documentation is the whole enforcement mechanism for this control, so deleting it removes the control. | Definitions restored on the members, plus the per-claim semantics and the worked SOXX/SOXL example, in the module that now owns the type. | Facade identity re-verified after the edit; focused suite 109 passed. |
| SEP1R-002 | P2 | Resolved | `02d7a9e` | `tests/test_active_document_consistency.py` | `test_separation_milestone_state_agrees_across_active_documents` pinned **five exact literals** — the plan's status line, two section headings, and two prose regexes — all of them claims that must **stay** true. The module's own docstring forbids exactly this: "Where a literal string is unavoidable, it is a phrase that should never be true again, never one that must stay true." | Not theoretical: the guard was written in `02d7a9e` and edited in `4f4d6c8`, then again before `a786074`, **inside the same session**, because the milestone legitimately advanced from "SEP-1 next" to "SEP-1 tranche implemented". Two edits in hours is the CCX-002 failure mode running at speed. | A guard that must be rewritten every time reality moves correctly enforces today's state rather than consistency, and the obvious fix each time is to weaken it. It would have required editing again at SEP-2, SEP-3, and on any rewording. | Rewritten as a relationship, the way the epoch guards already work: derive the current milestone id from the plan's own status line, assert exactly one milestone heading is marked current, and require the Action Plan and handoff to name that milestone and not still advertise an earlier one as current. No literal milestone id in the test. | Three mutations red — plan advanced while the others lag; two milestones current at once; status line no longer ACTIVE — and green restored, document byte-identical. It now survives SEP-2 without an edit. |
| SEP1R-003 | P3 | Resolved | `18868d3` | `assistant/portfolio_snapshot.py` | The two moved snapshot builders kept every guard and lost the record of which defect each guard closed: the lowercase-ticker basket-membership miss, the two-AAPL-lots aggregation that let per-position caps be jointly exceeded, the same-instant `current_price` refusal, and the 2026-07-29 finding that a NaN-cash-only guard let `check_policy_compliance()` report zero violations for a corrupt portfolio. `build_portfolio_snapshot_from_alpaca` also lost its caller guidance to check `is_configured()` rather than using `AlpacaNotConfigured` for control flow — guidance about a live broker path. | AST comparison of the moved functions: bodies equivalent, docstrings reduced. | `CLAUDE.md` §8 asks for comments explaining safety invariants and non-obvious failure directions. Each deleted paragraph is a defect someone paid a review round to find, and none is recoverable from the code. A future refactor that "simplifies" the aggregation now has nothing telling it why aggregation exists. | Restored, attributed, and marked with the finding id so the loss is visible rather than silently repaired. | Focused suite 109 passed; no behaviour touched. |

Retained from the previous round: **CDR2-005 (P3, open)** — dynamic imports are
fail-closed for authority reachability but ignored in the direct-edge census,
and reachability records only the first path per start module. Codex's
disposition (resolve during boundary evolution rather than widening this
review) is accepted.

No P0 or P1 issue was identified.

---

## On the counter-review of my SEP-0 work

SEP0CR-001 is correct and I accept it. My review moved the handoff and the
Action Plan amendment to "SEP-0 reviewed, SEP-1 next" and left the separation
plan's own status and headings still calling SEP-0 current — so the three
sequencing authorities disagreed, and a fresh session could have picked either
milestone depending on reading order. That is the same defect class I had just
raised against Codex twice. The finding stands; only its guard needed replacing.

---

## Assessment of the separation, one milestone in

The debt ledger went from 13 direct cross-product edges to **9**, and the
authority path from one to zero, without moving runtime behaviour. The four
edges that left were the genuinely neutral ones — evidence-status types and
decimal primitives — which is the right order: they are the edges where a
shared kernel is obviously correct rather than a judgement call.

The nine that remain are harder in a way worth stating plainly now. Five are
assistant → research calculation or context imports (`context_builder`,
`explanations` ×2, `stock_lookup`, `strategy_proposals` ×2), and those need the
read-only research-result adapter the plan describes — a design step, not a
move. Two are evidence/mandate couplings (`paper_evidence` → `backtest`,
`research_looks` → `backtest`, `backtest.research_report` → `assistant.mandate`)
that require deciding who owns mandate evaluation. None of the remaining nine
is a mechanical extraction, so SEP-1's second half should be expected to take
materially longer than its first.

`scripts/` remains unclassified and uncounted at the entry-point level, and
that is still where the real work is.

---

## Safety and authority disposition

- No proposal, approval, execution, reconciliation, broker, or policy
  behaviour changed. The moved code is byte-equivalent modulo names.
- The execution-authority boundary is **stricter** than before this round: zero
  authority-to-research paths, verified independently.
- ML/LLM boundaries unchanged; `test_ml_import_boundary.py` green.
- ACER untouched; the capability-audit authorization remains **open** and
  fail-closed, as corrected in the previous round.
- `paper-epoch-006` undisturbed — SEP-1 moved no operational file and changed
  no deployed lineage.
- No broker, vendor, credential, operator database, scheduled task, or
  deployment was accessed by the work or by this review.
- No milestone completed: SEP-1 is explicitly a first tranche, and
  `docs/FEATURE_MILESTONE_RECORD.md` is correctly unchanged.

## Validation

Recorded in handoff section 7df with exact counts.

## Assessment

**9/10.** The extraction is careful, the facades preserve identity, the new
guards close a gap I had only flagged, and the honest "SEP-1 is not complete"
is exactly right. The one recurring weakness in this series is visible again in
both P2s: what gets lost is never the code, it is the **reason** — the enum's
definitions, the invariants' provenance — and the one guard added to protect
state was itself written in the form that must be edited whenever state changes.
