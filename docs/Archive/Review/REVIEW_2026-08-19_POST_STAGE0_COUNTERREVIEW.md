# Counter-review: the Codex post-Stage-0 → SBR-1 audit

Status: **audit VERIFIED; all six behavioral corrections confirmed
real by independent red/green reproduction; documentation rewrites
checked accurate; one small record gap closed this round.** Prepared:
2026-08-19. Author: Claude (implementer of most of the audited range),
counter-reviewing `docs/Archive/Review/REVIEW_2026-08-19_POST_STAGE0_THROUGH_SBR1.md`
(Codex, commits `d943339` product/test + `02404d3` docs, on
`codex/review-post-stage0-through-sbr1-20260819`). No QC, broker,
task, or database access.

## 1. Verification method

Every behavioral finding was re-verified by checking out the
PRE-correction file (`d943339~1`) beside the corrected regression
tests and confirming red, then restoring the correction and confirming
green — my own implementations, so the bar is the audit's, not mine:

| Finding | Pre-correction | Corrected |
|---|---|---|
| PTSR-001 LEV same-close re-entry | RED (`test_month_end_sale_waits_for_the_following_month_end`) | green |
| PTSR-002 SBR fractional-count truncation | RED | green |
| PTSR-003 SBR stream-identity drift | RED | green |
| PTSR-004 overlay non-finite crash | RED (named-refusal regression) | green |
| PTSR-005 sufficiency counted unavailable outcomes | RED | green |
| PTSR-006 APQ impossible month label | RED (`DID NOT RAISE`) | green |

The four corrected suites pass together (63 tests). No test function
or assertion was deleted; SBR fixtures were upgraded to the stricter
frozen-config shape the correction introduces. Full-suite/compileall/
diff-check results on the exact final tree are recorded in the handoff
section for this round.

## 2. Judgments on the substance

- **PTSR-001 is a genuine frozen-spec violation I missed**: a
  take-profit trigger on the session before a month-end fills the sale
  AT the month-end close, and the boundary callback then re-entered at
  that same close — a zero-length cash interval where the frozen rule
  requires waiting for the NEXT month-end. The strict
  `session > sale_session` guard is the correct reading. My three
  LEV-1 mutations tested the state machine's boundaries but never
  composed "sale fills exactly on a month-end" with the boundary
  callback — a composition blind spot worth naming.
- **PTSR-002 is worse than the audit states, in a useful way**: besides
  truncating 1.5 → 1, the ORIGINAL `isinstance(value, int)` validation
  would have REJECTED numpy integer scalars from the real provider, so
  in production every ticker would likely have come back
  `available=false` — the success path itself was fixture-blind (tests
  fed Python ints). The `numbers.Integral`-with-bool-exclusion
  acceptance fixes both failure directions at once.
- **PTSR-003's stream-identity binding** (canonical config sha +
  preregistration sha + per-snapshot clean `code_commit`) upgrades the
  manifest to the repository's lineage conventions; the operational
  consequence — a DIRTY operational clone now blocks a monthly capture
  — is the correct fail-closed direction and matches the launch
  driver's own clean-tree rule.
- **PTSR-004/005** close real overlay gaps in the promised-refusal and
  independent-evidence contracts; PTSR-005 especially (an unavailable
  outcome must never satisfy a sufficiency threshold).
- The documentation corrections (PTSR-007..011) were read against the
  ledgers and my session records: the FEATURE_MILESTONE_RECORD entries
  are exactly two paragraphs each, factually consistent (Stage 0/1
  counts, A-003 p-values, 108-member baseline), and correctly exclude
  the partial LEV/SBR milestones; the handoff current-state/constraints
  /resume-prompt replacement is accurate (epoch-006, closed families,
  correct gating of LEV-2 and the SBR install behind this branch's
  merge).

## 3. Findings from the counter-review itself

- **PSCR-001 (P3, closed this round):** the audit's §8 rewrite dropped
  the durable operational lesson from the superseded text — "restart
  the Streamlit app after any operational deploy; a pre-deploy server
  mixes old in-memory modules with new on-disk code" (the
  `open_lot_fingerprint` incident). Moved to its durable home,
  `docs/operations/OPERATIONAL_FACTS.md`, per that file's own rule
  that facts outliving a milestone must not live in the handoff.
- No other dropped content: both parents of every merge in the range
  were verified present where I had independent knowledge, and the
  audit's own commit table matches the pushed history (143 commits,
  spot-checked at the boundaries and at every commit I authored).

## 4. What this counter-review does not do

No QC access; no reinterpretation of any closed result (A-001/A-002/
A-003 stand); no LEV-2 or SBR install start — both remain gated on the
owner merging this branch. The epoch-006 `policy_fingerprint` change
(4a942cbc… → 4086365c…) remains OPEN — this audit did not explain it,
and it stays flagged for the next forensic pass.
