# Session handoff — current project state

Prepared: 2026-08-29 by Codex after the owner directed a separate
Target-Price Revision planning lane and revised research/QC plan; amended by
the owner-coordinated shared-family/final-holdout decision and the approved
TPR-0A implementation round through 2026-08-30. This remains the canonical
generic-workflow handoff for the root project and preserves the 2026-08-28
deferred-remediation state below. The original three strategy lanes remain
independent; this amendment changes shared coordination only and does not edit
their lane-owned artifacts.

## 0. Target-Price Revision fourth-lane planning addition

- The owner directed a new sibling worktree at
  `C:\git\customizedagent\trading_agent_target_price` on branch
  `codex/strategy-target-price-revisions`, based on exact `main` commit
  `086b782e43a5ff889e71ec8e26334bb791ccac74`. The documentation round is
  **pushed and merged**: lane head `70c4b9fea1ac119f86901e95b9108820aa80e028`
  is published and reachable from `origin/main` through PR #324 merge
  `1a5264e6b1de3caf5477477d1312a762b2d42419`. Another computer can retrieve
  it with `git fetch`. Note that the merge preceded the mandated independent
  review recorded below, which was performed afterwards against the same
  published range.
- Before the current owner-coordinated round began, the dedicated target
  worktree was clean at local head `2708c06`, exactly two local commits ahead
  of published `c0ba616`. Those commits complete the Codex counter-review and
  remain unpushed; this round's single lane push has not occurred.
- The current local TPR-0A implementation candidate is
  `research/target_price_revisions/specs/tpr_round0a.candidate.json`: spec ID
  `tpr-round0a-candidate-f595992a3f5b8396`, semantic hash
  `f595992a3f5b8396e5f26ba5a3b0a3f32649eec3fd581071b349a5e12203af86`,
  and artifact SHA-256
  `99aae28d5b055aa24b84ce153467dfdbe7ee65f8ee2cef2a870efe1e68b2ea49`.
  It has 24 frozen cells, 39 null empirical child bindings, and 48 total
  pending prerequisites. The reviewed-spec registry is empty; research-source
  and permanent-look declarations are exact zero-access artifacts. One
  `planned_unbound` primary look identity records the family and period, but
  no look is authorized or spent. The candidate is pending Claude review of
  the exact single-push snapshot and subsequent Codex counter-review.
- The stable implementation snapshot is
  `ba01e98f9d3c8746c70182818a27a2d49a9c0fe7`. On its exact tree, all
  target/shared tests pass (**176 passed, 3 host symlink-permission skips**),
  compilation and diff/identity checks pass, and the full repository run had
  **5,829 passed, 5 skipped, 1 out-of-lane failure, 26 warnings**. The sole
  failure was an out-of-lane Briefing smoke-fixture isolation gap: unpatched
  direct yfinance paths timed out with cache errors, while the exact test
  passed immediately alone in 14.42 seconds. It is recorded as `TPR-OOL-005`
  and was not fixed from this target-only lane. No TPR P0/P1/P2 remains; the
  only TPR P3 is future cryptographic reviewer-identity strengthening before
  any positive authority.
- Claude's independent review of the pushed range `c0ba616..6aae73b` is
  complete: all four commits are **accepted after correction** or accepted,
  with no P0 or P1. An independent complete run on the exact pushed tree gave
  **5,830 passed, 5 skipped, 0 failed, 25 warnings in 997.26s**, corroborating
  the recorded counts and failing to reproduce `TPR-OOL-005`, which supports
  the flake diagnosis. Two guard regressions from the counter-review were
  corrected and mutation-verified: the repository-wide malformed-digest
  invariant was restored to the shared module, and the lane worktree guard
  again rejects a third spelling and the obsolete directory name.
- One P2 is **open and owner-routed**: `TPR-CR2-002` / `TPR-OOL-006`. The
  owner-approved addendum makes the shared selection family four members with
  target alpha `0.0125`, but Analyst Revisions V2 still freezes `0.05 / 3 =
  0.0167` and no document records a propagation obligation. At their current
  frozen alphas the four lanes would spend `0.0625` against an intended
  `0.05`. Nothing is executable and no lane has spent a look, so no result is
  affected, but this must be settled by one owner-coordinated common-baseline
  amendment before any lane's first outcome study. It was deliberately not
  fixed from this branch because the remedy is in sibling lanes' frozen files.
- The owner confirmed on 2026-08-30 that the three approvals recorded in
  section 13.1 were genuinely given. Section 14.5 binds them to the exact
  artifacts: the root `*.pdf binary` attribute, blueprint v2.1 at raw SHA-256
  `55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`, and the
  A21 TPR-0A/TPR-0B phase split. The confirmation adds no other authority.
- The next step is Codex's counter-review of every Claude commit in this
  round. TPR-0B and TPR-1 remain blocked on their own gates.
- The governing planning candidate is
  `docs/Strategy Description/TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf`
  (28 pages; raw binary SHA-256
  `55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`).
  Its authoritative lane state is
  `docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md`.
  The owner declared the version-2 blueprint, including its owner-decision
  addendum, the sole normative target-price strategy authority. The unavailable
  submitted proposal is not a second authority. Its transcribed 63-character
  value is historical evidence of unavailable provenance only; it cannot be a
  SHA-256 digest and cannot satisfy or block an implementation gate.
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
- Claude's documentation review is accepted after correction, and Codex has
  counter-reviewed all three Claude commits locally through `2708c06`. The
  owner-approved bounded TPR-0A algorithm/policy candidate is now implemented
  locally under the lane record and approved shared schedule; it remains
  unaccepted pending Claude's review of the exact pushed range. This decision
  does not supply or authorize provider credentials,
  schemas, licensed rows, source evidence, outcome access, a permanent-look
  spend authority, ETF work, QC processing, shadow, paper, live, unattended,
  deployment, broker, or capital authority; all remain zero or separately
  gated.
- Known synchronization debt, deliberately not corrected from the target
  lane: the Analyst V2 draft/loader still names
  `three_lane_selection_correction` and pins value 3. Analyst V2 remains
  fail-closed and zero-access, but that lane-owned contract and its tests must
  be synchronized to four before any Analyst outcome access.
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
`codex/strategy-target-price-revisions` in the dedicated target worktree. No
provider-specific target reader/normalizer, authenticated target event,
permanent target look authority, stock score, ETF topology, portfolio, QC
algorithm, prospective shadow/paper evidence, or live authority exists. The
unreviewed TPR-0A candidate is
`tpr-round0a-candidate-f595992a3f5b8396`, semantic hash
`f595992a3f5b8396e5f26ba5a3b0a3f32649eec3fd581071b349a5e12203af86`,
artifact SHA-256
`99aae28d5b055aa24b84ce153467dfdbe7ee65f8ee2cef2a870efe1e68b2ea49`,
with 39 null empirical child bindings and 48 total pending prerequisites. One
`planned_unbound` look identity exists, but no look is authorized or spent.
The submitted plan is replaced by the sole-normative corrected stock-first
blueprint whose later QC/autopilot stages remain individually owner-gated.
The exact next action is the single end-of-round Codex push followed by Claude
review of that exact range on the same branch, not TPR-1 or data access.

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
