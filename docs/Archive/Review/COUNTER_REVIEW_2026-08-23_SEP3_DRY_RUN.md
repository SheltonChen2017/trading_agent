# Counter-review — SEP-3 extraction dry run

Reviewer: Codex, 2026-08-23

Reviewed exact remote: `origin/user/claude/review-sep3-dryrun-20260822` at
`a6be87a3860720e1395de385a619daceeb2113c4`

Exact submitted implementation and merge-base:
`1b678481be37dde8dc87dfcd676e2912c727ea1b`

## Verdict and commit disposition

**Accepted after correction.** Claude's ordered review range contains exactly
one commit:

| Commit | Disposition | Reason |
|---|---|---|
| `a6be87a` — record the independent review of the SEP-3 extraction dry run | **accepted after correction** | Its review, blocker, provenance, validation and next-step conclusions reproduce. CRSEP3-001 corrects only its description of PR #303's Git topology. |

Issue ledger: **P0 0 / P1 0 / P2 0 / P3 1**.

## Finding

### CRSEP3-001 — PR #303 was not a fast-forward (P3, corrected in current records)

Claude's archived report says PR #303's merge "is a fast-forward of the
reviewed content." Git shows `8f508ce` has two parents,
`1dcc12b` and the reviewed implementation head `1b67848`; it is therefore a
merge commit, not a fast-forward. The important substantive statement remains
true: `1b67848` is the second parent and both objects have exact tree
`ae6151bd525cc567ab49d08adb739f922eaed100`, so the merged mainline tree is
byte-identical to the reviewed implementation and no implementation content is
stranded. The archived review remains unchanged; this dated counter-review and
the current handoff carry the correction.

## Independent reproduction

- The remote review head was stable at `a6be87a`; its merge-base with the
  submitted branch is exact `1b67848`, and its only changed files are Claude's
  review report and `docs/SESSION_HANDOFF.md`.
- The validator independently reproduces exact source `e642469`, **734**
  tracked paths, inventory SHA-256
  `853a139ca133103f838b66ec5c143566daae951bd2fea1a1f13576718ab72dcb`,
  and exactly-once destinations of **560 trading assistant / 171 strategy
  research / 3 shared contracts**.
- The three shared sources have exact Git blobs `8d41eb8`, `7dba236`, and
  `ea2bff4`. Their imports are limited to the standard library plus the
  declared `pandas` dependency; they contain no provider, broker, database,
  product, licensed-data, dynamic-import, prompt, portfolio-policy, strategy,
  or execution-authority dependency.
- The reconstructed surfaces match: script ownership **8 / 56 / 11**,
  executable launch surfaces **7 / 54 / 10**, and tests **102 assistant / 60
  research / 3 shared / 41 integration**.
- The exact blockers remain **11** composition files, **6** Python crossing
  roots, **4** non-assistant operator-database importers, and a pending
  support-surface partition. Authority remains assistant-owned; licensed
  research remains research-owned; physical extraction, database movement,
  task movement and epoch disturbance remain unauthorized.
- Source inspection finds only read-only Git plumbing calls (`show`,
  `ls-tree`, `cat-file -t`, `rev-parse`) and no write API. Executing the
  validator left the isolated worktree unchanged.
- Claude's CRSEP2C-001 acceptance is correct: the completion certificate now
  invokes the named fixture-free guards instead of proving only that their
  names exist.

The dry run remains evidence about a declared partition, not proof that two
physically extracted repositories or the not-yet-created `agent_contracts`
package run independently. SEP-3 continues by eliminating the residual
crossings and partitioning support/tests before a second dry run. A physical
migration remains separately owner-gated and will close `paper-epoch-006` if
it changes the operational checkout's code lineage.

## Validation

The read-only validator completed with the exact values above. The focused
SEP-3 and entry-point suites passed **29/29**. The existing dangerous-direction
cases independently refused an unclassified retained path, authority moved to
research, licensed research moved to the assistant, a vendor client added to
the shared package, and a case-insensitive target collision. Complete-suite
validation on the tree carrying this report and the final handoff passed
**4,539 / 0 failed / 25 known dependency warnings in 767.53 seconds** on
Python 3.13.14. Compilation, final document, Git, remote-head,
shared-checkout and secret checks are recorded in the separate session
handoff.
