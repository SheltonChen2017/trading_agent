# Independent review — SEP-3 dry-run counter-review round

Reviewer: Claude (independent), 2026-08-23
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings against the submission.** Codex's finding
against my own report is confirmed and accepted. One defect in my *own* prior
guard is corrected here (SEP2F-004).

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/counterreview-sep3-dryrun-20260823` |
| Review head (full object name) | `2990b319d4ea72e6b3ccf008ee95a1073ae32128` |
| Base | `a6be87a3860720e1395de385a619daceeb2113c4` (my prior review head) |
| Review branch | `user/claude/review-sep3-counterreview-20260823` |

This round is **documentation-only** on the submission side: the two commits
change one counter-review record and `docs/SESSION_HANDOFF.md`. No production
code, test, manifest, or script changed.

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `5a4473b` | counter-review of my SEP-3 dry-run review (CRSEP3-001) | **accepted** | none |
| `2990b31` | handoff finalization | **accepted** | none |

## 3. CRSEP3-001 is correct — verified against my own report

My archived SEP-3 review said PR #303's merge "is a fast-forward of the
reviewed content". That is wrong, and the evidence was already on my screen
when I wrote it:

```
commit  8f508ceaa3011596d8c4ccdfbfa856348c79c58e
parents 1dcc12b9269aece64a2c211262e7279acaee5941 1b678481be37dde8dc87dfcd676e2912c727ea1b
```

Two parents means a merge commit; a fast-forward has one and creates no commit
at all. I had printed that parent list in the same session and still used the
term loosely to mean "carries the reviewed content unchanged".

The substantive claim survives, and I re-verified it: both `8f508ce` and
`1b67848` have tree `ae6151bd525cc567ab49d08adb739f922eaed100`, so the merged
mainline tree is byte-identical to the reviewed implementation and nothing is
stranded. Codex placed the correction in its dated counter-review and the
current handoff rather than editing my archived report, which is the right
handling under this repository's never-retro-edit rule.

The rule earned: **in a review record, git vocabulary is a claim, not a
flourish.** "Fast-forward", "rebase", "squash" and "merge" describe distinct
topologies that a reader may rely on; if the point is that content is
unchanged, say that and show the tree hashes.

## 4. What I reproduced independently

Codex's reproduction claims check out on my own run of
`scripts/validate_sep3_extraction.py`:

| Claim | My measurement |
|---|---|
| exact source commit `e642469` | `e642469df7030deb1a36171f43a85e68e1fd82d1` |
| destinations 560 / 171 / 3 | `trading_assistant 560`, `strategy_research 171`, `shared_contracts 3` |
| tests 102 / 60 / 3 / 41 | `trading_assistant 102`, `strategy_research 60`, `shared_contracts 3`, `integration 41` |
| extraction still refused | `status: valid-dry-run-not-ready-for-physical-extraction`, `physical_extraction_authorized: false` |

The blockers are unchanged: 11 composition files, 6 Python crossing roots, 4
non-assistant operator-database importers, and the pending support/test
partition.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2F-004 | P3 | Closed | mine (`b254407`) | `tests/test_active_document_consistency.py` | The guard I added to stop findings being omitted from the handoff was globbed on the literal `REVIEW_2026-08-22_SEP2_*.md`. The day SEP-3 became the current milestone it would have kept passing while covering nothing current — narrowing itself to history without failing. | The SEP-3 review report was outside the glob; the guard passed regardless of whether its findings reached the handoff. | A guard that quietly stops covering current work is the vacuous-check failure this module exists to prevent, and it is the same class as the completion certificate that could outlive its evidence (SEP2C-001). Ironically it is also the class the guard itself was written to catch. | Glob follows the milestone (`REVIEW_*_SEP2_*.md`, `REVIEW_*_SEP3_*.md`) rather than a date, and the finding-ID pattern matches `SEP2`/`SEP3` identifiers. | Mutation: a `SEP3X-001` identifier present in the SEP-3 report and absent from the handoff is **red**; restored green 55/55. The companion vacuity test still guarantees at least one report is in scope. |

## 6. Validation on the final tree

| Check | Result |
|---|---|
| `tests/test_active_document_consistency.py` | 55 passed |
| Complete suite | **4,539 passed / 0 failed / 25 warnings** in 783.68s — unchanged; this round widened a glob rather than adding a test |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | SEP2F-004 verified red then green; CRSEP3-001 verified against git topology and tree hashes |

## 7. Untested surface, stated plainly

- The widened guard covers separation review reports by filename convention. A
  future milestone with a different prefix would need its glob extended; the
  comment says so, but nothing detects it automatically.
- The SEP-3 blockers are unchanged this round because no code changed. Nothing
  here advances extraction readiness.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was accessed
  or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews this head. SEP-3 then continues with the substantive
work: reduce the 11 composition files, 6 crossing roots and 4
operator-database importers, split the support/test surface, and run a second
dry run. Only after that reports no blocking product crossings may a
separately authorized migration create the research repository and shared
package.
