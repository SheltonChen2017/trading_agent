# Independent review — SEP-2 filing-ownership tranche and operator-state hardening

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1; one P2 corrected, plus a
process guard for my own repeated defect.**

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep2-filing-ownership-counterreview-20260822` |
| Review head (full object name) | `b2ac54c1ee23bbad8ae0f69625c38fd4b02b92ad` |
| Base | `07ef9290081ca2920ec73dc73cdc93fbd8386699` (my prior review head) |
| Review branch | `user/claude/review-sep2-filing-20260822` |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `8839c12` | hardens my SEP2D-001 fix: read prefixes, alias/reflection closure | **accepted — correct findings against my own work** | see §3 |
| `4e8fa20` | `ml/filings.py` → `data/filing_extraction.py`, `ml/hashing.py` → `data/hashing.py`, runner reclassified assistant-owned | **accepted after correction** | SEP2F-001 |
| `8661113` | counter-review record | **accepted** | none |
| `1ffb036` | plan tranche record | **accepted** | none |
| `1b50929` | neutral schema-version inventory pin | **accepted** | none |
| `b2ac54c` | handoff and validation record | **accepted** | none |

No merge commit in the range.

## 3. Codex's findings against my own fix are correct — both verified

CRSEP2D-001 says my SEP2D-001 correction had two generalized gaps. I verified
both in an **isolated worktree checked out at my own head `07ef929`**, because
my first attempt — restoring the old guard onto the new tree — produced a
pre-existing failure that masked the mutation result and proved nothing.

| Gap | Result on my head |
|---|---|
| **Alias bypass**: `write_state = store.set_system_state` then `write_state("kill_switch", ...)` | **passed 20/20** — my guard matched only direct `store.set_system_state(...)` calls, so an ordinary bound-method alias walked straight past it and wrote the kill switch |
| **Unbounded reads**: undeclared `store.get_system_state("ledger_bootstrap")` in `run_ml_evidence_supervisor.py` | **passed 20/20** — I bounded writes only |

A precision note in Codex's favour and against a lazy reading of it: the read
gap bites only where `get_system_state` is a granted method. The same read
added to `run_ml_shadow.py`, which lacks that grant, *is* caught by the method
ledger. Codex's claim is accurate for the case that matters.

Both are real defects in my own P2 fix, and the pattern is pointed: my finding
was *"an allowed method name is not an allowed capability"*, and my correction
then bounded one direction (write, not read) and one call shape (direct, not
aliased). I generalized the principle and under-generalized the fix.
`8839c12`'s closure — direct calls only, explicit read and write prefixes,
dynamic keys and unused grants refused — is right, and the alias mutation fails
under it.

CRSEP2D-002 is also correct: my handoff verdict said "one P2" while my report
said "one P2 and one P3". See §5.

## 4. What I verified independently

- **The relocated code is genuinely neutral.** `data/filing_extraction.py`
  imports only the standard library plus `data.hashing`; nothing under
  `assistant/`, `execution/` or `risk/` imports it today; `ml/filings.py` and
  `ml/hashing.py` are now compatibility facades and object identity is pinned.
  `tests/test_ml_import_boundary.py` remains green 8/8.
- **The ownership reclassification is honestly described.** The record states
  it "changes ownership metadata and import direction only" and calls the
  runner "honestly trading-assistant-owned rather than research-hosted
  composition". It does **not** claim the operator-database coupling was
  removed: `scripts/run_filing_extraction.py` still imports `assistant.storage`
  lazily, but as an assistant-owned script that is no longer a crossing. The
  importer count therefore falls 5 → 4 by reclassification, and the record says
  so rather than presenting it as decoupling.
- **Counts reproduce exactly**: 8 assistant / 56 research / 11 composition,
  declared crossings 7 → **6**, operator-database importers 5 → **4**.
- The Action Plan edit is within its own update rule — a concise sequencing and
  residual-surface reference, not implementation detail.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2F-001 | **P2** | Closed | `4e8fa20` | `data/filing_extraction.py`, `architecture/entry_points.json` | Moving `ml/filings.py` into the shared kernel shed the protection it had under `ml/`. `CLAUDE.md` §4 forbids an `ml` import under `assistant/` without a separately approved exact-file adapter milestone, and `tests/test_ml_import_boundary.py` enforced that — but the test detects the `ml` **root**, so relocating the file removed the enforcement while every reason for it survived. The module still carries `PROMPT_VERSION`, `EXTRACTION_SCHEMA_VERSION`, `ExtractedClaim`, `validate_extraction` and `sentiment_is_not_a_signal`. | **Matched control.** `assistant/proposals.py` importing `ml.filings.FilingExtraction` fails 3 guards. The identical class imported as `data.filing_extraction.FilingExtraction` passes **37/37**. Same code, same capability, one spelling caught. | This is precisely the erosion `CLAUDE.md` §4 warns about — "green direct-import tests are not proof that the boundary holds transitively". A safety boundary that can be stepped around by relocating the file is not a boundary. | `architecture/entry_points.json` declares `llm_derived_neutral_contracts` with its rationale, and `test_llm_derived_contracts_keep_their_ml_boundary_after_relocation` keeps those modules out of `assistant/`, `execution/` and `risk/`. **`data/hashing.py` is deliberately excluded** — canonical JSON and SHA-256 carry no ML semantics, and banning a neutral primitive would be over-reach. | Three directions: assistant import **red**, `risk/` submodule-style import **red**, and an over-reach control confirming `data.hashing` **still passes**. Restored green 22/22. |
| SEP2F-002 | P3 | Closed | mine (`07ef929`, `b4b896f`) | `tests/test_active_document_consistency.py` | Twice in consecutive rounds I added a finding to a review report after its verdict line was written and left the `SESSION_HANDOFF` summary behind — SEP2L-002 and SEP2D-002 were each in the archived report's ledger and absent from the handoff. Codex caught both. | Verified at both of my heads: `b4b896f` said "one P3" against a report saying "two P3"; `07ef929` said "one P2" against "one P2 and one P3". | I wrote the resolution for this in the previous round's report and then repeated it in the same round. A third written resolution is worth nothing; the relationship has to be asserted. | New guard: every finding ID a SEP-2 review report raises must appear in the current handoff. Scoped to SEP-2 reports because those handoff sections are current; archived rounds are never retro-edited. | Mutation reproducing the historical failure (dropping `SEP2D-002` from the handoff) is **red**; restored green 55/55. A companion test fails if no SEP-2 report is found, so the guard cannot pass vacuously. |

## 5a. A near-miss in my own process, recorded because it nearly shipped

The SEP2F-001 fix was **committed without the guard in it**, and I caught that
only by reconciling a test count that did not add up.

What happened: my mutation script for verifying Codex's findings used
`git checkout -- tests/test_project_separation_entrypoints.py` as its cleanup.
That file held my *uncommitted* SEP2F-001 guard, so the cleanup silently
reverted it. I then committed and had the manifest declaration
(`llm_derived_neutral_contracts`) with **nothing enforcing it**, under a commit
message that claimed the guard existed — the exact "declaration without
enforcement" defect I have been raising against others all session.

How it surfaced: Codex measured 4,528 and I added three tests, so I expected
4,531. The run returned **4,530**. Rather than record the measured number and
move on, I reconciled the difference, found the entry-point file had 21 tests
on both trees where it should have had 22, and traced it back.

Two rules earned, both narrower than "be careful":

1. **Never use `git checkout --` as mutation cleanup on a file holding
   uncommitted work.** Commit the fix first, or reverse the edit textually. The
   cleanup that protects the tree from a mutation will equally revert the fix
   the mutation is testing. The re-verification for this finding reverses the
   edit instead, with a comment saying why.
2. **A test count that does not reconcile is evidence, not noise.** The
   arithmetic was the only signal that a committed fix was absent; every guard
   was green, because the guard was gone.

## 6. Validation on the final tree

| Check | Result |
|---|---|
| `tests/test_project_separation_entrypoints.py` | 22 passed |
| `tests/test_active_document_consistency.py` | 55 passed |
| Complete suite | **4,531 passed / 0 failed / 25 warnings** in 757.80s — Codex's 4,528 plus three added guards; the reconciliation that exposed §5a |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | SEP2F-001 three directions incl. over-reach control; SEP2F-002 reproduction; both counter-review findings verified on an isolated worktree at my own head; all restored |

## 7. Untested surface, stated plainly

- My SEP2F-001 guard covers **direct** imports by `assistant/`, `execution/`
  and `risk/`. A transitive path through another neutral `data` module would
  not be caught; the existing ML-boundary walker does transitive analysis for
  the `ml` root, but the relocated code is no longer under that root.
- The guard's inventory is declarative. If a future move relocates another
  ML-provenance module into `data/` without adding it to
  `llm_derived_neutral_contracts`, the same erosion recurs — the manifest
  records the principle so the next reviewer can apply it, but nothing detects
  provenance automatically.
- The reclassification of filing extraction to assistant ownership is a
  judgement I accept rather than one I can verify mechanically. It is
  defensible — the contract is neutral, the output is context, and the audit
  row is assistant-owned — but `docs/operations/ML_IMPLEMENTATION_STATUS.md`
  still lists the runner under ML-LR-4, so the two records now describe the
  same file differently.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was accessed
  or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep2-filing-20260822`. SEP-2 remains incomplete: four
research-hosted operator-database importers, 11 composition files, 6 crossings,
per-product launch surfaces, and the shared kernel.
