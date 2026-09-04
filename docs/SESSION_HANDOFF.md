# Session handoff — current project state

Prepared: 2026-08-29 by Codex after the owner directed a separate
Target-Price Revision planning lane and revised research/QC plan; amended by
the owner-coordinated shared-family/final-holdout decision and the approved
TPR-0A implementation round through 2026-08-30. This remains the canonical
generic-workflow handoff for the root project and preserves the 2026-08-28
deferred-remediation state below. The original three strategy lanes remain
independent; this amendment changes shared coordination only and does not edit
their lane-owned artifacts.

## 0B. Owner-directed cross-lane bug-fix integration, 2026-09-04

- The owner directed the dedicated Review lane session to scan all four lane
  records for shared trading-application / test-infrastructure / tooling
  issues that were documented but deliberately not fixed on the lanes,
  confirm each on `main`, fix the confirmed ones on
  `Feature-bug-fix-integration-2026-09-04` (branched from `main` at
  `aefa0ec`), apply the identical commits to every lane branch, and push. The
  owner performs the PR merges. This is the "separate owner decision" the
  frozen-file rule requires; the parallel-workflow file carries the bounded
  exception paragraph.
- Authoritative record: `docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md`
  (fix table, consolidation map, full disposition ledger of every lane item,
  owner decisions requested, validation). Code commits on the integration
  branch: `7f99f303d0b6f5a2a65aa5b5b49f9c52256716d8`,
  `3114a1530f0afa400eb200e79ff218c174657e69`, and
  `6ef66eed77f9b24ea3df8aa538f42de0c871c824` (owner-directed F-8: the
  Target-price self-declared-review test made deterministic across harness
  layouts). Per-lane cherry-pick hashes are recorded in each
  lane record's pointer section, not here.
- Fixed: the sleeve-report / notification-cycle wall-clock mismatch (four
  tests red on `main` since 2026-09-02; `evaluate_sleeves` gains an injected
  `now`); the machine-global runtime emergency stop being latched by a
  child-process test (redirected, plus a conftest guard that fails any test
  whose containment write reaches the real `%LOCALAPPDATA%` stop); missing
  EOL attributes for `research/ml_specs/*.json` and `research/__init__.py`;
  the Briefing smoke fixture's network reach; the stale lane README and
  direction pointer; one overclaiming characterization test name; the
  layout-dependent Target-price self-declared-review test (F-8).
- Not fixed, with reasons in the record: execution-semantics P1/P2 items
  (Insider R-01/R-10/R-12/R-13/R-15/R-16, Analyst CLR-002 residual, CLR-003)
  remain gated behind the queued
  `POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md` plan or an
  owner decision; research-contract items (four-family `1/80` re-freeze,
  duplicate-key loader) route to their lanes; `ml.immutable_io` relocation is
  an integration-milestone item.
- Owner decision, since taken (follow-up 1 below): the real runtime stop file
  on this host was active at generation 42 with 42 test-origin incidents and
  the documented clear path could not run (origin databases are gone); the
  owner directed it cleared.
- Validation on the final integration tree: full suite on `3114a15` in an isolated detached worktree with an external `--basetemp`: 6799 passed, 13 skipped, 25 warnings, 0 failed (2124 s); compileall including `research` clean; `git diff --check` clean. Baseline `main` at `aefa0ec` in the same setup: 4 failed, 6786 passed, 13 skipped (the four wall-clock failures).
- `main` still shows the four wall-clock failures until the integration PR is
  merged; every lane branch carries the same fix commits after this round.
- Owner follow-ups executed the same day: (1) the real
  `%LOCALAPPDATA%\trading_agent\runtime\state\execution-emergency-stop.json`
  on this host (generation 42, 42 incidents, every origin a pytest/temp
  database) was deleted under the runtime's own state fence after a
  byte-identical backup was taken; the runtime now reads it as inactive,
  generation 0, and recreates it on the next real activation. (2) The
  Target-price lane's copy of this handoff, which that lane had been editing
  per round, was restored byte-for-byte to this branch's version and the
  three lane guards that bound it to lane state were retargeted to the lane
  record and Action Plan (`16b3435`, `522da19`, `47103e4` on
  `codex/strategy-target-price-revisions`). (3) The analyst and
  short-interest clone directories were fast-forwarded to their pushed tips.
- (4) On the owner's further direction, the Target-price lane's
  `docs/ACTION_PLAN_2026-08-20.md`, which carried the same class of per-round
  lane edits (nine commits since `main`), was restored byte-for-byte to
  `main`'s version (`e989872` on that branch) and the lane guards that read
  its target block and row for per-round state were retargeted to the lane
  record in the following commit. Both shared coordination documents are now
  identical on that lane and this branch. (5) On owner direction the Action
  Plan's Target-price block and table row were refreshed on this branch as a
  concise 2026-09-04 reference to the lane record's section 8 (replacing the
  2026-08-30 next-action sentence) and mirrored to that lane; they are no
  longer per-round pointers.

## 0. Target-Price Revision fourth-lane planning addition

- The owner directed a new sibling worktree for branch
  `codex/strategy-target-price-revisions`, resolved with
  `git worktree list` rather than a pinned directory, based on exact
  `main` commit
  `086b782e43a5ff889e71ec8e26334bb791ccac74`. The documentation round is
  **pushed and merged**: lane head `70c4b9fea1ac119f86901e95b9108820aa80e028`
  is published and reachable from `origin/main` through PR #324 merge
  `1a5264e6b1de3caf5477477d1312a762b2d42419`. Another computer can retrieve
  it with `git fetch`. Note that the merge preceded the mandated independent
  review recorded below, which was performed afterwards against the same
  published range.
- The owner-approved v2.2 fixed-slot amendment at `bb8dfb6` has completed
  Claude's independent review and Codex's commit-by-commit counter-review.
  Claude's exact correction range is `fe056be..db6a721`, with full review head
  `db6a721d45eb47e1a133744387bf43a1aa1f310c`; all three commits are accepted
  after correction or qualification, with no P0/P1. Sections 17 and 18 of the
  lane record contain the exact dispositions.
- The current zero-access TPR-0A implementation candidate is
  `research/target_price_revisions/specs/tpr_round0a.candidate.json`: spec ID
  `tpr-round0a-candidate-74b096af24c8d481`, semantic hash
  `74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c`,
  and artifact SHA-256
  `17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a`.
  It has 24 frozen cells, 39 null empirical child bindings, and 48 total
  pending prerequisites. The reviewed-spec registry is empty; research-source
  and permanent-look declarations are exact zero-access artifacts. One
  `planned_unbound` primary confirmatory look/cell allocation is `1/80`, but
  no look is authorized or spent. The reviewed-spec registry remains empty,
  and the candidate remains unreviewed for its own registry; completing the
  human review loop grants no positive algorithm authority.
- The cumulative committed validation tree `6b12102` passed the full suite:
  **5,842 passed, 5 skipped, 25 warnings in 1,065.11 seconds**. Full compilation
  including `research` passed. The focused implementation/import suite passed
  with **113 passed, 3 skipped**, the case-insensitive malformed-digest
  regression passed with **2 passed**, and the final pre-validation document
  suite passed with **75 passed**. The final complete target-price plus active-
  document suite passed with **188 passed, 3 skipped in 12.56 seconds**. The
  29-page PDF passed strict-open, hash,
  unchanged-first-28-page, render, and visual checks. The final documentation-
  only bytes were committed and pushed at `fe056be` after the narrow identity/
  document guard passed; exact evidence is retained in the target record rather
  than overwriting history.
- The reviewed Claude range is `6aae73b..2ec0fad`. Codex accepted all six
  commits after correction: the review/validation evidence is credible, while
  the confirmed defects were stale identities/next-state prose, a duplicate
  import, backwards no-recycling semantics, rounded-as-exact arithmetic, two
  append-only ledger rewrites, interim record/test authority instead of the
  sole-authority PDF/artifact, and an uppercase malformed-SHA bypass. Section
  16 of the lane record contains every commit disposition and `TPR-CCR3-*`
  resolution.
- **Owner multiplicity amendment, 2026-08-30.** One shared family of four
  named lanes, total two-sided FWER `1/20 = 0.05`, and one permanent maximum
  allocation of `1/80 = 0.0125` per lane. The named slots remain fixed; an
  unused or withdrawn allocation expires and is never transferred,
  redistributed, or used to recompute the denominator/share. All confirmatory
  cells and looks in one lane must
  together consume no more than `1/80`. The target contract is encoded in the
  v2.2 PDF and authenticated candidate. Sibling-lane artifacts and reviews
  remain in their respective branches. Every outcome gate remains closed;
  the directive grants no new authority.
- The sibling-lane synchronization debt remains `TPR-OOL-006`: under the old
  exact allocations, `3 * (1/60) + 1/80 = 1/16 = 0.0625`, above `1/20`.
  (`0.0167` is only a rounded display of `1/60`.) The permanent-slot directive
  resolves the target contract; each sibling artifact must be corrected and
  reviewed only on its own branch. This target lane does not edit those files
  or grant any lane an outcome look.
- The owner confirmed on 2026-08-30 that the three approvals recorded in
  section 13.1 were genuinely given. Section 14.5 binds them to the exact
  artifacts: the root `*.pdf binary` attribute, blueprint v2.1 at raw SHA-256
  `55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`, and the
  A21 TPR-0A/TPR-0B phase split. The confirmation adds no other authority.
- Claude's independent review of the pushed range `2ec0fad..fe056be` is
  complete: all three commits are **accepted** or **accepted after
  correction**, with no P0 or P1. An independent complete run on the exact
  pushed tree reproduced **5,842 passed, 5 skipped, 0 failed, 25 warnings in
  1,080.30s**, matching the recorded count on the actual pushed head. All
  seven counter-review findings against the prior Claude round are accepted.
  One P2 (`TPR-CR3-001`) and one P3 (`TPR-CR3-002`) were found and closed:
  the record's current-state section still pinned the superseded v2.1
  blueprint and candidate identities, which a new guard now prevents.
- Claude independently reviewed both Codex commits in the exact Git range
  `db6a721..c8c7470`, then made four commits in
  `c8c7470..f21d70851d5e1790be0c308e13e8837a7cd1d008`. Codex has
  counter-reviewed every Claude commit in that four-commit range. The newline
  defect is a P2 fail-closed compatibility defect, not a P1 execution escape:
  five nonempty policy files differed from their blobs on the reviewing
  Windows checkout, while shared `research/__init__.py` was empty and exact.
  The first attributes-only correction fixed fresh checkouts but not an
  ordinary clean fast-forward; section 21 records the LF-normalizing tracked-
  blob migration that closes that gap without changing candidate or authority
  JSON bytes.
- The owner-directed worktree rule remains to resolve this lane from
  `git worktree list`, never from a pinned directory. The corrected guard is
  scoped to current target blocks, accepts sibling-lane text elsewhere, and
  refuses a missing registration when this checkout is on the lane branch.
  No P0 or P1 is open. One pre-existing target P2 (`TPR-CCR5-004`) blocks any
  future positive reviewed-algorithm authority until an independently reviewed
  immutable policy-inventory trust root exists; the reviewed registry is empty
  today. No next implementation milestone is authorized: TPR-1 remains blocked
  on an exact separately reviewed source-rights artifact, TPR-0B remains
  blocked on reviewed TPR-1/TPR-2 structural manifests, and the sibling-lane
  re-freezes under `TPR-OOL-006` still gate outcome access. After this Codex
  round's single push, Claude reviews only its exact correction range.
- The governing planning candidate is
  `docs/Strategy Description/TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf`
  (29 pages; raw binary SHA-256
  `f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`).
  Its authoritative lane state is
  `docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md`.
  The owner declared the version-2 blueprint, including v2.2 addendum A27, the
  sole normative target-price strategy authority. The unavailable submitted
  proposal is not a second authority. Its transcribed 63-character value is
  historical evidence of unavailable provenance only; it cannot be a SHA-256
  digest and cannot satisfy or block an implementation gate.
- The revised plan treats target-price revisions as a separate family from the
  rating-only Analyst Revisions V2 lane. It adopts stock-first null closure,
  cutoff-safe corrections, institution/catalyst independence, binary validity,
  separate mapping/feature/active-signal coverage, immutable QC packets, and
  separately gated shadow, paper, restricted-live, and bounded-unattended
  stages. A valid target-price stock null cannot be rescued by ETF aggregation,
  rating fusion, or a secondary cell.
- The lane has zero authenticated production target events, accepted target
  signals, outcome permits, permanent looks, ETF topologies, nonempty
  portfolios, QC uploads/jobs/results, broker connections, shadow sessions,
  paper/live intents, or promotion approvals. No credential, licensed row,
  provider, outcome, QC, broker, operator database, scheduler, deployment,
  evidence epoch, paper order, live order, or capital surface was accessed.
- Later owner workflow decision, 2026-08-29: Target-Price Revisions uses the
  serialized Codex-write -> Claude-review -> Codex-counter-review plus next
  milestone -> Claude-review loop on the same
  `codex/strategy-target-price-revisions` branch and dedicated worktree. Each
  role may make several commits in its round but pushes exactly once at the
  end. No review, counter-review, checkpoint, handoff, or feature branch is
  created. The worktree is target-price-only; external findings are recorded
  for later owner routing and are not fixed from this lane.
- The owner now includes Target-Price Revisions as the separately governed
  fourth canonical family and fourth attempt in the common selection
  accounting. The common cutoff session is **2027-08-31**, the untouched
  shared final holdout is **2027-09-01 through 2029-08-31**, and the target
  one-shot validation period is **2026-09-01 through 2027-08-31**. The date
  design originated in the owner-directed ARV2 freeze `b912459`, was accepted
  by independent review at `1507777`, accepted by Codex counter-review at
  `31c313e`, and is expressly extended to TPR by the current owner approval.
  All four families must leave the reserve unconsumed.
- Claude's complete six-commit range through `2ec0fad` is accepted after Codex
  correction, and the owner-approved v2.2 fixed-slot TPR-0A snapshot at
  `bb8dfb6` has now also completed Claude review and Codex counter-review
  through `db6a721d45eb47e1a133744387bf43a1aa1f310c`. It remains an unreviewed
  candidate for its own empty reviewed-spec registry. This decision does not
  supply or authorize provider credentials,
  schemas, licensed rows, source evidence, outcome access, a permanent-look
  spend authority, ETF work, QC processing, shadow, paper, live, unattended,
  deployment, broker, or capital authority; all remain zero or separately
  gated.
- Known synchronization debt, deliberately not corrected from the target
  lane: sibling artifacts must encode their permanent named `1/80` slots and
  expiry/no-redistribution semantics in their own branches. They remain
  fail-closed and zero-access; this target branch does not modify them.
- `docs/ACTION_PLAN_2026-08-20.md` receives only the concise sequencing and
  authority reference above. The original three-lane operating topology,
  records, workflow, and data-source register remain unchanged. The target
  same-branch exception and this one-time owner-coordinated shared amendment do
  not extend any later shared-file or other-lane exception by inference.

## 0A. Deferred P2/P3 remediation handoff

- Current documentation branch:
  `codex/document-deferred-p2-p3-remediation-20260828`, created from exact
  integrated root-review baseline
  `da7e0d8b63aeb48a19dca86f0811777c8c74078c`.
- Published `origin/main` at audit time:
  `da7e0d8b63aeb48a19dca86f0811777c8c74078c`. Local `main` matched it before
  this documentation branch was created. This is PR #319's merge of the
  accepted root-remediation counter-review; it does not contain the three
  still-independent strategy lanes.
- Queued-plan record commit:
  `3c55b3c3d522f83201f45c22b9f11bed956cd6e1`. Its authoritative HOW/WHERE,
  sequencing, acceptance and authority record is
  `docs/Plan/POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md`.
- Accepted-after-correction implementation commit:
  `242f8eb7ef5022ed17e86502896ae19e7621e55c` (parent `6a50734`, tree
  `b97cccb5be0a2f19fe96ffc5a194bdfa411a83f3`).
- Authoritative counter-review record commit:
  `699f6bc970f1ab5978c9a994d803b5dc09fc1fbd`. The full P0–P3 ledger,
  six-commit disposition table, corrected historical count, implementation
  record, validation evidence, and open HOW/WHERE plans are in
  `docs/Archive/Review/COUNTER_REVIEW_2026-08-27_ROOT_REMEDIATION.md`.
- All six Claude commits are **accepted after correction**:
  `4fc2c60e41c49056b4c3babf35af3acc56c6e6fe`,
  `0eaf420293733b7a31b4b62e07fe3eb0c2dfdad8`,
  `ae55d865f184d513448e571ebe3e1e8bd863aa34`,
  `eeeab1370923ec0c2bf6f06c643f5d63ec6019c9`,
  `76139b4efb751de8f7fd863a7a5dfc6f2f92da9d`, and
  `6a507341896850076c13050da080f888d6eb31aa`. Merge-tree identity was accepted
  separately from inherited content correctness.
- No P0 remains. The historical Claude report has 45 unique finding IDs, not
  46: P1=2, P2=13, P3=20, and ten invalidly classified P4 rows. `BRK-003` has
  no finding row. Claude's claimed explicit dispositions for 27 earlier
  implementation commits were not present and were not invented here.
- Final implementation validation on the exact code tree: changed/new tests
  **1,681 passed, 0 failed, 1 warning**; complete suite **5,720 passed, 2
  skipped, 0 failed, 25 warnings in 1,843.55 seconds**; repository-wide
  `compileall` exited 0; `git diff --check` was clean; and no likely added
  credential/private-key shape was found. The 70 documentation and remediation
  ledger guards passed after the report update and again after this handoff
  replacement.
- Validation of this documentation change: the 71 active-document/remediation
  guards passed; deleting one queued finding made the new relational guard fail
  and restoration returned it green; and repository-wide `compileall` exited
  0. `git diff --check` was clean and the changed paths contained no recognized
  credential/private-key shape. The complete 5,723-test run reported **5,720
  passed, 2 skipped, 1 failed, 25 warnings in 4,259.71 seconds**. The sole
  failure was a host-load timeout:
  the exact Windows operational-contract verifier exceeded its hard-coded
  30-second PowerShell subprocess limit. It passed both in its complete
  50-test module (**50 passed in 237.75 seconds**) and again alone after the
  full run (**1 passed in 20.19 seconds**). No product assertion failed; the
  complete-suite result is nevertheless recorded as red, not called green.
- The seven carried findings remain open and mandatory: `RCR-014` and
  `RCR-015` are P2; `RCR-016` through `RCR-020` are P3. Their source evidence
  remains unchanged in the archived counter-review. The queued plan refines
  how and where they must be corrected, how each closes, and how the final
  integrated tree must be reviewed.
- These findings principally belong to the trading assistant / paper-live
  product, broker/event storage, reporting and process boundary. Only the
  provider-neutral Decimal primitive tranche of `RCR-019` belongs to the
  temporary shared kernel. None of the seven is a research/QC strategy defect,
  although the future Full Project Review must independently review the merged
  research/QC product and the integration seam.
- Current row hashes are unkeyed consistency evidence, not cryptographic
  authentication. The future recovery and checkpoint work must share one
  explicit threat model and must not claim deletion, reorder, rollback or
  hostile-rewrite resistance without an ordered prefix and an appropriate
  authority outside the mutable database.
- `ARV-001` through `ARV-014` remain delegated to the Analyst Revisions V2
  lane. They are not accepted, closed, or implemented by this root review.
  Insider Buying and Short Interest were likewise untouched. No feature-lane
  record was changed.
- Analyst identity semantics remain explicit: the measured `768` diagnostic
  count is a **lower bound**, never an **allowlist**; **current-ticker joins are
  prohibited**. **Normative strategy design** and **observed provider**
  availability/history remain separate evidence categories.
- No provider, credential, licensed row, outcome, QuantConnect job, broker,
  operator database, live scheduler, deployment, evidence epoch, paper order,
  live order, or research look was accessed or changed.
- This documentation is not a feature milestone, so
  `docs/FEATURE_MILESTONE_RECORD.md` remains unchanged. The owner-directed
  future gate was added concisely to `docs/ACTION_PLAN_2026-08-20.md`; the
  implementation detail stays in the queued plan.
- The root counter-review remains **DONE**. This documentation task does not
  reopen it and grants no remediation authority now. The next Full Project
  Review may begin only after all three feature branches complete their lane
  review loops, the owner merges those exact heads into `main`, and the owner
  explicitly starts the review/correction work from that integrated commit.
- Until that explicit activation, do not implement `RCR-014` through
  `RCR-020`, start a new whole-project audit, edit a strategy lane, unfreeze
  SEP-3, or infer provider, research-look, QC, broker, operator-database,
  deployment, paper-order, live-order or trading authority.

The owner clarification remains binding: the standing strategy-lane loop is
Codex implementation, Claude independent review, then Codex counter-review
plus the next bounded milestone before one combined push. That lane-specific
workflow did not authorize edits from this generic root review.

Historical coordination detail remains at
`docs/Archive/Session/SESSION_HANDOFF_THROUGH_2026-08-25_SEP3_EIGHTH_DRY_RUN.md`
and in `docs/Archive/Review/`.

## 1. Read first

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/ACTION_PLAN_2026-08-20.md`.
3. `docs/Plan/POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md`.
4. `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`.
5. `docs/Archive/Review/COUNTER_REVIEW_2026-08-27_ROOT_REMEDIATION.md`.
6. `docs/Archive/Review/COUNTER_REVIEW_2026-08-26_THREE_STRATEGY_DIRECTION.md`.
7. `docs/Strategy Description/README.md`.
8. `docs/Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md`.
9. The selected lane's PDF and implementation record.
10. `docs/Strategy Description/THREE_STRATEGY_DATA_SOURCE_REGISTER.md`.
11. `docs/architecture/SEP3_FREEZE_STATE_2026-08-25.md` before any separation
   discussion and `docs/operations/OPERATIONAL_FACTS.md` before operational
   work.

## 2. Exact baseline and branches

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Historical three-lane baseline `origin/main`:
  `6156ef9b92737c9b390a96d286b0fbde4ff4b19c`.
- The owner directed deletion of merged branches; after cleanup only `main`
  and `origin/main` remained.
- Three published long-lived lane branches were created from one identical
  committed documentation baseline:
  - `codex/strategy-analyst-revisions-v2`
  - `codex/strategy-insider-buying`
  - `codex/strategy-short-interest`
- Each corresponding `origin/codex/strategy-*` remote head was verified at
  `c9dcdb647914acbfcefce187a138f52fcdad0c68`. Branch publication is not a
  research run, merge, deployment, or trading authority.
- Main-line direction was implemented at
  `d00c0e0eb7bae35df34aa031404cdb7940d84301` on
  `codex/main-three-strategy-direction-20260826`. Claude amended and accepted
  it at the stable pushed head
  `c88ac4f379aba996b48fb7f70e5210edda3c7320`.
- Codex counter-reviewed Claude's sole commit as **accepted after correction**.
  The null-result correction and coordination regression guard are
  `a6cc4fb4b9cf83d1651226983e5e80c9bce104a8`; the exact commit disposition and
  P0-P3 ledger are in
  `docs/Archive/Review/COUNTER_REVIEW_2026-08-26_THREE_STRATEGY_DIRECTION.md`
  at `bcd2e79`. The owner later clarified that an instruction removing future
  counter-reviews was accidental; counter-review remains a required stage in
  every lane cycle.

The three owner PDFs were inspected as text and visually page by page. Their
page counts, byte sizes, and SHA-256 hashes are pinned in the lane records.
No strategy code, vendor data, outcome, backtest, or QuantConnect job was
executed while creating this baseline.

Counter-review validation before finalization: the three focused direction
checks passed, all 61 active-document checks passed, the common-holdout
dangerous-direction mutation failed as intended and restored green, and
`compileall` including `research/` passed. The first complete-suite attempt
reported 4,570 passed and one active-document failure: this handoff's resume
prompt had lost the exact statement that provider access remains an open owner
decision. That counter-review-introduced wording defect was corrected and the
61 active-document checks passed again. A shared-checkout complete rerun then
passed 4,571 tests, but another session changed three unstaged coordination
files while it was running. Codex therefore repeated the complete suite in a
clean detached worktree at exact commit
`80e76e765ca66ad2735aa1c74a6a4228a519e537`: **4,571 passed, 0 failed, and 25
known warnings in 1,626.69 seconds**. The temporary worktree was clean and was
removed. The concurrent unstaged workflow edits were preserved and excluded
from every counter-review commit.

Owner-clarification restoration, 2026-08-26: the standing Codex
counter-review-plus-next-milestone loop was restored on
`codex/restore-counterreview-workflow-20260826` without changing `main`
directly. The three focused coordination checks passed; deleting the exact
counter-review stage heading made the guard fail and restoration returned it
green; all 61 active-document checks passed; `compileall` including
`research/` passed; and the complete suite passed **4,571 tests with 0
failures and 25 known warnings in 1,644.79 seconds**. No provider, outcome,
QuantConnect job, broker, operator store, deployment, or strategy runtime was
accessed or changed.

One-time common-remediation synchronization, 2026-08-27: the owner-authorized
exception was completed from `codex/full-review-p1-remediation-20260826` and
published at the three exact heads in section 0. Shared patches are identical;
Analyst-only code is present only on the Analyst lane. This synchronization did
not accept a strategy or authorize the next milestone, and the exception is now
exhausted.

## 3. Parallel-work exception and handoff rule

During the three-lane phase, agents must not edit this handoff or the Action
Plan on any of the three named lanes. The completed owner-directed one-time
remediation synchronization was their sole implementation exception; it is
exhausted. The owner's 2026-08-29 direction created a separate fourth planning
lane and later explicitly assigned that target lane the same serialized
same-branch review loop. This coordination update does not edit an existing
lane record, revive the exhausted synchronization exception, or grant a
shared-file exception. Each named lane's implementation record remains that
branch's status, review ledger, validation record, and resume prompt.

The owner-directed main-line coordination surface is
`docs/THREE_STRATEGY_PROJECT_DIRECTION.md`. Only a separately directed
main-line coordination change may update that record, this handoff, or the
Action Plan while strategy branches are active.

Each lane uses a dedicated isolated clone or worktree. Codex implements,
Claude independently reviews, and Codex counter-reviews on the same strategy
branch, but agents and lanes do not share a checkout. No
review/counter-review branch is created. After Claude pushes its review,
Codex counter-reviews every Claude commit and corrects confirmed defects. If
accepted or accepted-after-correction and no owner decision blocks progress,
Codex then implements the next bounded milestone, validates both stages,
updates the lane record, and makes exactly one combined push. Never
force-push or rewrite published lane history.

After the exhausted one-time exception, lane agents again leave repository-
shared merge surfaces unchanged, including `requirements.txt`, `config.py`,
CI/tooling configuration, and shared test or classification manifests. New
code, tests, and fixtures use lane-owned strategy namespaces. A later true
shared-file or dependency need stops for a new owner-directed common-baseline
amendment; the completed synchronization grants no continuing inference.

## 4. Strategy state

### Analyst Revisions V2

The active V2 record is
`docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md`.
The synchronized candidate now implements a strict zero-access safety and
contract layer for immutable snapshots/datasets, canonical event/refusal and
revision lineage, availability timing, permanent identities, rating ontology,
stock-score primitives, sector validity, holdings/topology evidence, decimal
costs, constrained all-cash-safe portfolio construction, preregistration, and
outcome authorization refusal. The checked-in production source authority and
all production source/classification/cost/rank catalogs remain empty; no
provider-specific accepted-row normalizer, authenticated production event,
real stock score, nonempty research portfolio, outcome study, walk-forward
result, or QC algorithm exists. The candidate is unaccepted until Claude
reviews the exact pushed range and Codex counter-reviews every Claude commit.
No V2 outcome look exists.

The V1 identity scan's 768 interleavings remain a lower-bound warning; an
unflagged ticker means `no_name_based_ambiguity_evidence`, never a safety
allowlist. A durable external security master is still required.

The former ACER V1 plan/source/freeze/proposals/audits are archived and marked
superseded. Their data lineage and null priors remain valid historical
evidence; their strategy parameters are not current instructions.

### Insider Buying

The active record is
`docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md`. It is a
new lane. No SEC ingest, Form 4 classifier, identity map, signal, ETF score,
portfolio, or QC algorithm exists. The SEC quarterly datasets and full EDGAR
filings are the canonical free source; public acceptance time governs.

### Short Interest

The active record is
`docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md`. It is a
new lane. No ingest, signal, ETF score, portfolio, or QC algorithm exists.
Canonical V1 requires official-style twice-monthly short-interest snapshots;
daily short-sale volume is prohibited as a proxy. A licensed historical/vintage
short-interest source is the clearest missing paid input.

### Target-Price Revisions

The active lane record is
`docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md`.
It is a separate fourth planning lane under the owner-directed serialized
same-branch, one-push-per-role-round workflow. All feature implementation,
review, counter-review, and next-milestone work stays on
`codex/strategy-target-price-revisions` in the dedicated target worktree. The
v2.2 implementation snapshot is `bb8dfb6`; the latest Claude review head is
`f21d70851d5e1790be0c308e13e8837a7cd1d008`, and Codex's four-commit
counter-review/corrections are recorded in section 21 of the lane record. No
provider-specific target reader/normalizer, authenticated target event,
permanent target look authority, stock score, ETF topology, portfolio, QC
algorithm, prospective shadow/paper evidence, or live authority exists. The
unreviewed TPR-0A candidate is
`tpr-round0a-candidate-74b096af24c8d481`, semantic hash
`74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c`,
artifact SHA-256
`17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a`,
with 39 null empirical child bindings and 48 total pending prerequisites. The
reviewed-spec registry remains empty, and the candidate remains unreviewed for
its own registry. One
`planned_unbound` confirmatory look/cell allocation exists at `1/80`, but no
look is authorized or spent.
The submitted plan is replaced by the sole-normative corrected stock-first
29-page v2.2 blueprint whose later QC/autopilot stages remain individually
owner-gated. No next implementation milestone is authorized: TPR-1 remains
blocked on exact reviewed source rights and TPR-0B remains blocked on reviewed
TPR-1/TPR-2 structural manifests. `TPR-CR4-002` is closed: the lane worktree
is resolved from `git worktree list` rather than a pinned path. One target P2,
`TPR-CCR5-004`, remains open and blocks positive reviewed-algorithm authority
until an immutable policy-inventory trust root is independently reviewed; it
does not open TPR-1 or any source/outcome/look gate. Claude reviews the exact
Codex correction range after this round's single push.

## 5. Data acquisitions and confirmations

The assumed Massive-Benzinga Analyst Ratings subscription is sufficient to
begin a structural V2 ratings audit, not to prove every needed dataset or
license. The assumed QuantConnect subscription does not establish entitlement
to US ETF Constituents, US Equity Security Master, US Equities, US Fundamental
Data, local downloads, or vendor-data processing in Object Store.

Owner priorities are:

1. obtain/confirm a historical-vintage short-interest license (Intrinio or
   equivalent) with corrections, stable IDs, delisted coverage, and export/QC
   processing rights;
2. confirm exact QC dataset entitlements and holdings availability semantics;
3. confirm Massive and short-interest vendor permission for the exact raw,
   normalized, or derived representation sent to QC Cloud;
4. obtain a PIT ETF reference feed if QC cannot supply historical product
   classification, inception, AUM, and holdings availability; and
5. optionally add PIT earnings controls. EPS-revision and lending/ORTEX data
   are later extensions, not canonical blockers.

SEC insider history is free; the work is careful accession/version ingestion,
acceptance-time handling, identity resolution, and fair-access compliance.

## 6. Separation and operational state

SEP-3 is the current bounded milestone and remains **FROZEN, PAUSED, and
incomplete** at its independently accepted eighth
dry run. Physical extraction is false and unauthorized. Its six dual-use data
modules, `config`, 11 composition files, six Python crossing roots, four
non-assistant operator-store importers, 42 integration tests, non-test
documentation ownership, equivalence-test placement, and runtime topology
remain open. Strategy work neither advances nor weakens SEP-3.

`paper-epoch-006` remains untouched. Nothing in this baseline authorizes
provider credential access, licensed-row retrieval, broker access, operator
database changes, scheduled tasks, deployment, backtests, outcomes, evidence
epochs, paper orders, or live trading.

Separation finding identifiers retained for audit routing:
`CRSEP2-001`, `CRSEP2C-001`, `CRSEP2D-001`, `CRSEP2D-002`, `CRSEP2F-001`,
`CRSEP2F-002`, `CRSEP2L-001`, `CRSEP3-001`, `CRSEP3A-001`,
`CRSEP3MPCR-001`, `CRSEP3MPCR-002`, `CRSEP3MPCR-003`, `CRSEP3R-001`,
`CRSEP3R2-001`, `CRSEP3S-001`, `CRSEP3ST-001`, `CRSEP3ST-002`, `SEP2-001`,
`SEP2-002`, `SEP2-003`, `SEP2-004`, `SEP2-005`, `SEP2-006`, `SEP2-007`,
`SEP2C-001`, `SEP2C-002`, `SEP2D-001`, `SEP2D-002`, `SEP2F-001`,
`SEP2F-002`, `SEP2F-003`, `SEP2F-004`, `SEP2L-001`, `SEP2L-002`,
`SEP2P-001`, `SEP2P-002`, `SEP2P-003`, `SEP3AR-001`, `SEP3CR-001`,
`SEP3CR-999`, `SEP3CR2-002`, `SEP3R-001`, `SEP3R-002`, and `SEP3X-001`.

## 7. Integration boundary

The ultimate target is one autopiloted QuantConnect trading agent, but the
three existing lanes and the separately planned Target-Price Revision lane
must not build the combined agent independently. The target lane may prove
standalone QC parity and later bounded operations under its own gates, but
multi-signal fusion remains a separate owner-scheduled integration milestone
for merge order, common schemas, late fusion, cross-signal correlation, risk
budgets, combined costs/turnover/capacity, untouched final holdout, QC parity,
paper deployment, monitoring, reconciliation, kill switch, and explicit
promotion. No leverage is planned for the canonical strategies.

The owner has frozen one common final-holdout cutoff for all four canonical
families: cutoff session **2027-08-31**, with **2027-09-01 through 2029-08-31**
reserved and inaccessible to every lane. Target-Price Revisions has the
distinct one-shot validation period **2026-09-01 through 2027-08-31**. The
combined evidence threshold treats the four families as one selection family
and accounts for selection from four attempts, while each lane retains its own
family ID, look budget, evidence epoch, and valid-null closure. A valid
canonical null is not tuned or rerun to pass; any later hypothesis needs a
separately preregistered family and a new owner-authorized permanent look
budget.

The four lane IDs are permanent slots inside total two-sided FWER `0.05`.
Each lane is capped at `1/80`; the named slot remains fixed while an unused or
withdrawn allocation expires, is never redistributed, and does not change the
denominator or another lane's maximum.
All confirmatory cells and looks within one lane must together consume no more
than `1/80`. Sibling-lane artifact changes remain on their own branches.

This shared schedule and multiplicity decision grants no outcome access. TPR
and every other lane remain unable to consume the holdout, and TPR has no
provider, source, permanent-look, or QC authority merely because its dates are
now frozen.

## 8. Resume prompt

```text
The root counter-review is complete. Do not start another whole-project review
until the Analyst Revisions V2, Insider Buying, and Short Interest lanes have
each completed their implementation/review/counter-review chain, the owner has
merged their exact final heads into main, and the owner explicitly activates
the post-integration Full Project Review and correction program. Then begin
from the exact fetched main head and read CLAUDE.md, AGENTS.md,
ACTION_PLAN_2026-08-20.md,
POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md,
THREE_STRATEGY_PROJECT_DIRECTION.md, all three final lane records,
COUNTER_REVIEW_2026-08-27_ROOT_REMEDIATION.md, and the SEP-3 freeze record.
Review every commit and merge since da7e0d8 plus the cumulative tree. Apply
authorized corrections for every newly confirmed P0-P3 finding and close all
seven carried findings RCR-014 through RCR-020. Report research/QC,
paper-live, shared-kernel, architecture and integration conclusions
separately; do not treat the seven assistant/shared findings as research
defects. Use the generic independent-review workflow and preserve exact commit
dispositions. Access no provider, credential, licensed row, outcome,
QuantConnect job, broker, operator database, live scheduler, deployment,
paper-order, live-order, evidence-epoch or SEP-3 surface by inference.
Provider/outcome access remains an open owner decision; obtain that
authorization before any such audit or run. Preserve zero looks,
paper-epoch-006, the untouched shared final holdout, and the frozen SEP-3
manifest.
```
