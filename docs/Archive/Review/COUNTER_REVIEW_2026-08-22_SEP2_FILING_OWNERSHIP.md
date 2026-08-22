# Counter-review — SEP-2 filing-ownership review

Reviewer: Codex, 2026-08-22

Exact Claude branch: `origin/user/claude/review-sep2-filing-20260822`

Exact reviewed head: `fa32156307af0da5322694af5595b1e5b831efc6`

Exact submission base and merge-base:
`b2ac54c1ee23bbad8ae0f69625c38fd4b02b92ad`

## Verdict

**Accepted after correction.** Claude found a real P2: moving the filing
extraction contract out of `ml/` removed the import spelling that existing
execution/ML guards recognized. Its direct guard and provenance declaration
were valuable, but Claude's own report correctly disclosed that the dangerous
transitive form remained unprotected. A direct-only boundary is insufficient
under `CLAUDE.md` section 4, so `624a7fd` extends the existing fail-closed
first-party graph to the relocated LLM-derived contract.

No provider, credential, licensed row, broker, operator database, installed
task, deployment, backtest, outcome, research look, or evidence epoch was
accessed or changed.

## Ordered commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `1adabcb09055600b7526a16256722f00a885913e` | **Accepted after correction** | The direct boundary, manifest rationale, and review/handoff consistency guard are sound. The LLM-derived boundary required transitive closure at `624a7fd`. |
| `fa32156307af0da5322694af5595b1e5b831efc6` | **Accepted after correction** | The review report is unusually candid and its tests/counts reproduce. The disclosed transitive gap was material and the current ML status required a narrow ownership clarification. |

## P0–P3 ledger

| ID | Priority | Status | Finding | Evidence | Correction |
|---|---:|---|---|---|---|
| CRSEP2F-001 | P2 | Corrected | `assistant -> neutral helper -> data.filing_extraction` bypassed Claude's direct-only relocated-contract guard. | A mutation adding `data.sep2_mutation_bridge` and importing it from `assistant.proposals` left the direct guard green but failed the new graph guard with the complete reachable chains. | `624a7fd` uses the existing fail-closed first-party import graph, refuses unresolved reachable dynamic imports, and rejects direct or transitive reach from every `assistant`, `execution`, or `risk` module. The mutation reddened and was textually restored. |
| CRSEP2F-002 | P3 | Corrected in current documentation | `docs/operations/ML_IMPLEMENTATION_STATUS.md` still presented the now assistant-owned runner as though it remained an ML-owned implementation file. | Claude disclosed the mismatch in its untested-surface section; direct comparison reproduced it. | The current record distinguishes neutral extraction contracts, the assistant-owned audited runner, and the retained ML-LR research capability without rewriting history. |

P0: 0. P1: 0. P2: 1 corrected. P3: 1 corrected.

## Independent verification

- Exact merge-base and two-commit Claude range reproduced.
- Claude's 8/56/11 ownership, six crossing-root, and four non-assistant
  operator-store importer counts reproduced.
- The alias-write and undeclared-read counter-review mutations from the prior
  round remain closed.
- The new transitive neutral-bridge mutation fails under `624a7fd` and was
  restored without `git checkout --`, preserving uncommitted work.
- Focused, complete-suite, compile, document, JSON, secret, topology, and
  clean-tree results are recorded in the final handoff for the combined tree.

## Quality rating

**8.5/10.** Claude identified an important boundary erosion, added a useful
process guard, reconciled its test count rather than ignoring it, and clearly
disclosed the limits. The deduction is for accepting a safety boundary while
leaving its known transitive bypass open instead of closing it during review.
