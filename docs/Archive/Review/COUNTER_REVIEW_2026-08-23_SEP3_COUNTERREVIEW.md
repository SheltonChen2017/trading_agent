# Counter-review — Claude's SEP-3 counter-review round

Reviewer: Codex, 2026-08-23

Reviewed exact remote: `origin/user/claude/review-sep3-counterreview-20260823`
at `18afbf4045ceb4f00be5d42e4f66d582ea195e61`

Exact submitted base and merge-base:
`2990b319d4ea72e6b3ccf008ee95a1073ae32128`

## Verdict and commit disposition

**Accepted after correction.** Claude's ordered review range contains exactly
one commit:

| Commit | Disposition | Reason |
|---|---|---|
| `18afbf4` — review the SEP-3 counter-review and unpin the finding guard | **accepted after correction** | Claude correctly accepts both submitted commits and correctly identifies SEP2F-004. CRSEP3R-001 closes a remaining fail-open in the generalized finding-ID grammar. |

Issue ledger: **P0 0 / P1 0 / P2 0 / P3 1**.

## Findings and dispositions

### Claude's SEP2F-004 — confirmed and accepted

The prior `REVIEW_2026-08-22_SEP2_*.md` glob was date- and milestone-pinned.
It excluded the current SEP-3 report while the companion vacuity test remained
green on historical SEP-2 files. Claude's replacement correctly brings both
SEP-2 and SEP-3 independent-review reports into scope. The exact submitted
active-document suite passes 55/55, and the read-only SEP-3 validator
reproduces source `e642469`, destinations 560 / 171 / 3, test partitions 102 /
60 / 3 / 41, extraction refusal, and blockers 11 / 6 / 4 plus the pending
support/test partition.

Claude's acceptance of CRSEP3-001 also reproduces. PR #303 is a two-parent
merge, not a fast-forward, while merge commit `8f508ce` and reviewed head
`1b67848` share exact tree `ae6151bd525cc567ab49d08adb739f922eaed100`.

### CRSEP3R-001 — multi-part finding IDs escaped the generalized guard (P3, corrected)

Claude generalized the filename scope but changed the identifier expression to
`SEP[23][A-Z]?-nnn`, which permits only one optional letter. Its demonstrated
`SEP3X-001` mutation was detected, while equally valid round-qualified forms
such as `SEP3CR-001` and `SEP3CR2-002` were ignored. Adjacent separation
review chains already use multi-part round suffixes, so the guard could again
pass while a later review finding was absent from the current handoff.

Regression proof was red on exact Claude head `18afbf4`:
`_FINDING_ID.fullmatch("SEP3CR-001")` returned `None`. Correction commit
`ab91271` accepts an arbitrary non-empty-or-empty uppercase/digit suffix after
the milestone number, adds direct grammar coverage for `SEP2F-004`,
`SEP3CR-001`, and `SEP3CR2-002`, and renames the stale SEP-2-only helper,
tests, and failure text to their actual separation-wide scope. The targeted
grammar test and full active-document module pass. An end-to-end mutation that
added report-only `SEP3CR-999` failed with that exact missing identifier and
passed after textual restoration.

No production, manifest, provider, broker, database, task, deployment,
backtest, outcome, research-look, or evidence-epoch behavior changed.
`paper-epoch-006` remains untouched. SEP-3 is still incomplete and physical
extraction remains separately owner-gated.

## Validation

Focused active-document validation passes **56/56** after the correction.
The targeted dangerous-direction grammar test failed red on Claude's submitted
parser and passes green after `ab91271`; the end-to-end omitted-finding
mutation also failed red and was restored. The combined active-document,
SEP-3 dry-run, and entry-point gate passes **85/85**. The complete suite passes
**4,540 / 4,540** with 25 known dependency warnings in 763.31 seconds.
Compilation, document, Git, remote-head, shared-checkout, and narrow-secret
checks are recorded in the separate session handoff.

## Next step

After this review chain closes, continue the already-authorized bounded SEP-3
implementation: reduce the 11 composition files, six Python crossing roots and
four non-assistant operator-database importers; partition support and tests;
then run a second dry run. Nothing here authorizes physical repository
creation or migration.
