# Session handoff — current project state

Prepared: 2026-08-27 by Codex after the owner-authorized P1/P2/P3 remediation,
one-time three-lane synchronization, and post-merge portfolio-equity correction.
Amended 2026-08-27 by Claude with the independent review of the root
remediation range (section 0A). This is a durable implementation handoff, not an
acceptance record: Codex counter-review of the review commits remains mandatory,
and the three lane branches still require their own independent review.

## 0. Remediation implementation handoff

- The root remediation was merged to `main` through PR #314 and PR #315; exact
  merged head is `9e9843e9fc332cbbed63480834abe2c3f093a652` and the temporary root branch was
  deleted after merge.
- The portfolio-equity correction is **merged**: branch
  `codex/fix-portfolio-equity-rounding-20260827` was merged as PR #316 at
  `e6a654dcf4fed67b5abbd1d312bb8031bc91fe2d` and no longer exists. Exact code
  commit `1ed06022d7f811a5977239be71e99c2fd7d37952` fixes an owner-reproduced
  P1 where summing already-rounded position displays produced a total-equity
  display that disagreed with the exact aggregate and prevented the paper
  assistant UI from loading. The builder now aggregates exact Decimals and
  rounds once; the strict integrity validator was not weakened.
- Exact root code snapshot before this record-only update:
  `66168eda687d42a3cfda45a05e0de8f7781d3b87`. The final shared follow-up is
  `6770db3bc3934c4b0872d0cea6a256c28dec2cc8`; the isolated Analyst-only
  follow-up is `66168ed`. This handoff and the remediation ledger are the only
  later root-tree changes in the record commit.
- The complete 110-finding ledger is retained at P0=0, P1=47, P2=49, P3=14.
  `SYS-FU-P1-006` records the post-merge correction. Codex found no generalized
  second snapshot-construction instance; this does not substitute for the
  owner-required independent reviewer.
- Post-merge correction validation: focused portfolio/risk/coherent-snapshot
  suite **112 passed, 0 failed, 1 dependency warning**; reverse mutation failed
  the new regression at display `100.01` versus exact `100`; complete suite
  **5,442 passed, 2 skipped, 0 failed, 25 dependency warnings in 1,944.33s
  (32m24s)**; required repository-wide compileall exited 0 and `git diff --check`
  was clean. Validation used fixtures only; Codex did not access a broker,
  provider, credential, account, order, or operator database.
- Exact root validation: touched-surface suite **922 passed in 313.42s**;
  complete suite **5,441 passed, 2 skipped, 0 failed, 25 dependency-
  deprecation warnings in 2,083.27s (34m43s)**; required repository-wide
  compileall exited 0; PowerShell parser reported 0 errors; `git diff --check`
  was clean; and the narrow secret-shape scan found no likely credential
  literal. After the record-only documentation edits, the 362-test
  documentation/active-contract regression set passed in 125.06 seconds and
  was rerun after this result was recorded on the final documentation tree.
- The owner-authorized synchronization was non-force-pushed and then verified
  at these exact remote heads:
  - Analyst Revisions V2:
    `d8d0ad6e86dee1b05a5f62f3dd9d53c7b51b9729` (validated code
    `653a9c01ac12863db2d7488154014a662c893add`; 5,434 passed, 2 skipped,
    25 warnings in 39m14s).
  - Insider Buying:
    `8a65e3ca38cdc6f0feff8f3d7f6c8ae4a722b83d` (validated code
    `e770b059f06dd8af9a52bd6dd96f7f83af2fc835`; 5,223 passed, 2 skipped,
    25 warnings in 36m40s).
  - Short Interest:
    `0a77b9cd2fb8f96ced51194ce68060b6a08b3de9` (validated code
    `81eede4ef8de10609d4b5375b795abf916132dd0`; 5,223 passed, 2 skipped,
    25 warnings in 37m54s).
- The three shared landing commits have stable patch ID
  `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`. Ancestry and range checks proved
  that neither Analyst hardening commit nor any of its five-file surface
  entered Insider Buying or Short Interest. Each lane changed only its own
  implementation record after code validation.
- The post-merge `SYS-FU-P1-006` correction has not been copied to any strategy
  lane. The one-time common-remediation synchronization authority expired and
  grants no authority for a later shared-file synchronization by inference.
- No provider, credential, licensed row, outcome, QuantConnect job, broker,
  operator database, live scheduler, deployment, evidence epoch, paper order,
  or live order was accessed or changed. No research or trading authority was
  created; Analyst consumed **0 research looks**.
- Analyst identity semantics remain explicit: the measured `768` diagnostic
  count is a **lower bound**, never an **allowlist**; **current-ticker joins are
  prohibited**. **Normative strategy design** and **observed provider**
  availability/history remain separate evidence categories.
- Resume with Claude reviewing every commit in each exact pushed lane range on
  the same long-lived lane branch. Codex then counter-reviews every Claude
  commit. Do not start a new lane milestone, provider audit, outcome run, or
  deployment before that chain and the relevant owner gates close.

The owner clarification remains binding: the instruction removing Codex
counter-review was accidental and is superseded. The standing lane loop is
Codex implementation, Claude independent review, then Codex counter-review
plus the next bounded milestone before one combined push.

Historical coordination detail remains at
`docs/Archive/Session/SESSION_HANDOFF_THROUGH_2026-08-25_SEP3_EIGHTH_DRY_RUN.md`
and in `docs/Archive/Review/`.

## 0A. Independent review of the root remediation (Claude, 2026-08-27)

- Review branch `user/claude/review-root-remediation-20260827`; full record in
  `docs/Archive/Review/REVIEW_2026-08-27_ROOT_REMEDIATION_INDEPENDENT.md`.
  Reviewed range `2572472..e6a654d` — **27 commits**, covering the 22-commit
  remediation series (PR #314, PR #315) **and** PR #316's portfolio-equity
  rounding fix. Every commit carries an explicit disposition; all three merge
  commits were reviewed as commits and each merge tree is byte-identical to its
  topic-branch parent, so no commit or content was stranded.
- **Disposition: accepted after correction, conditional on the P1 band and
  `VAL-001` being closed.** No P0. The ledger is P0=0, **P1=2**, P2=13, P3=21,
  P4=10 (46 findings). Severities were calibrated against reachability on a
  production path, per this repository's own FCS-007 lesson.
- **`main` does not currently pass its own test suite (`VAL-001`, P2).** PR #316
  added a 110th ledger finding (`SYS-FU-P1-006`) without the paired update to
  `tests/test_remediation_ledger_consistency.py`, whose expected family counts
  and grand total are deliberately hard-coded. Four tests fail. Reproduced in a
  throwaway detached worktree pinned at `e6a654d`, so it is a property of the
  commit. The recorded PR #316 validation of "5,442 passed, 0 failed" cannot
  describe that tree — 5,442 is exactly its collection count, so the run
  predated the ledger commit.
- Reviewer validation, two trees:
  - tree of `9e9843e` (≡ `6906a6c`, the remediation series head):
    **5,441 passed, 2 skipped, 0 failed, 25 warnings in 1,878.57s** —
    reproduces the implementer's recorded root-range validation exactly.
  - review head `e6a654d`: **4 failed, 5,438 passed, 2 skipped, 25 warnings in
    1,495.77s**. `compileall` exited 0; `git diff --check` clean; a narrow
    secret-shape scan matched nothing.
- The two P1s share one root cause and are recorded as one systemic finding:
  the remediation hardened the execution path fail-closed without carrying
  CLAUDE.md section 5's risk-reduction exception through the new guards.
  `EXE-001` (an unrelated ambiguous dispatch blocks every sell, reproduced end
  to end through the real execution path) and `STO-001` (one corrupt
  broker-event row makes a writable store unconstructable, removing emergency
  cancel-all, with no repair command). `BRK-001` is the same class held at P2
  only because no trigger is demonstrated reachable against a real broker. The
  earnings blackout and `cancel_all_open_orders` are the two places the rule
  *was* applied correctly.
- Two claimed properties are not met at their stated strength: `AR-FU-P1-010`
  (`ARV-001`/`ARV-002` — reviewed-policy identity is a self-rehash, not held out
  of band) and `SYS-P2-005` (`POL-002` — the integrity validator is not shared
  with the execution gate).
- Independently reproduced as correct: the 110-finding ledger is internally
  consistent; cross-process dispatch-fence exclusion demonstrated between two
  live processes; the ML/research import boundary closed transitively from eight
  execution-capable roots; the research layer's zero-access outcome and
  nonempty-portfolio gates unbreakable under direct attack; legacy operator
  databases upgrade safely; and the Analyst-only follow-up `66168ed` is absent
  from both other lanes.
- The review consumed **zero** research looks and touched no provider,
  credential, broker, operator database, scheduled task, deployment, or evidence
  epoch. `paper-epoch-006` is untouched.

### 0A.1 Corrections applied (owner-authorized, 2026-08-27)

- Branch `user/claude/fix-risk-reduction-guards-20260827`, which merges the
  review branch so the record and the corrections travel together. Detail is in
  section 7A of the review report; this is the summary.
- **`VAL-001` closed.** The ledger guard's expectations now match the
  110-finding ledger, and `SYS-FU-P1-006`'s status line was normalized to the
  canonical wording with its commit retained in the entry body. The guard was
  not weakened and no finding's substance was changed — its own three mutation
  tests still pass. **`main` is green again.**
- **`EXE-001` closed.** `_refuse_while_prior_dispatch_is_ambiguous` is now
  exposure-increasing only, mirroring the earnings blackout's registry scoping.
  A risk-reducing sell completes while an unrelated proposal is stranded in
  `submission_unknown`; an exposure-increasing buy still refuses without broker
  contact.
- **`STO-001` closed.** `AssistantStore` gains an explicit, default-off
  `permit_contained_integrity_failure`. Ordinary construction still refuses a
  damaged broker-event ledger; only `cancel-all-orders` opts in, so emergency
  cancellation stays reachable while containment holds the kill switch active. A
  scope test pins the opt-in to exactly that one command.
- **`BRK-001` deliberately deferred** — a partial position book cannot safely
  drive the gate's exposure and sell-exceeds-held checks, so what the gate
  validates for a sell against an incomplete book is an owner/design decision,
  not an implementation detail. It is also the only finding whose trigger is not
  demonstrated reachable against a real broker.
- Validation on the corrected tree: full suite **5,448 passed, 2 skipped, 0
  failed, 25 warnings in 1,430.00s**; `compileall` exited 0; `git diff --check`
  clean. No existing test was weakened, skipped, or deleted; no broker,
  provider, operator database, scheduled task, deployment, or evidence epoch was
  touched.
- Still open for Codex: the remaining 11 P2 findings, all P3/P4 items, and
  `BRK-001`'s design decision. The remediation ledger's per-finding statuses
  remain Codex's to update after counter-review.

## 1. Read first

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/ACTION_PLAN_2026-08-20.md`.
3. `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`.
4. `docs/Archive/Review/COUNTER_REVIEW_2026-08-26_THREE_STRATEGY_DIRECTION.md`.
5. `docs/Strategy Description/README.md`.
6. `docs/Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md`.
7. The selected lane's PDF and implementation record.
8. `docs/Strategy Description/THREE_STRATEGY_DATA_SOURCE_REGISTER.md`.
9. `docs/architecture/SEP3_FREEZE_STATE_2026-08-25.md` before any separation
   discussion and `docs/operations/OPERATIONAL_FACTS.md` before operational
   work.

## 2. Exact baseline and branches

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Published `origin/main` at audit time:
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
Plan on any lane. The completed owner-directed one-time remediation
synchronization was the sole exception; it is exhausted. The relevant lane
implementation record is that branch's status, review ledger, validation
record, and resume prompt.

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
three lanes must not build it independently. After canonical strategies are
independently validated, the owner must schedule a separate integration
milestone for merge order, common schemas, late fusion, cross-signal
correlation, risk budgets, combined costs/turnover/capacity, untouched final
holdout, QC parity, paper deployment, monitoring, reconciliation, kill switch,
and explicit promotion. No leverage is planned for the canonical strategies.

Before any lane performs its first real-outcome study, the owner must freeze
one common final-holdout cutoff and reserved period that all three lanes leave
unconsumed. The combined evidence threshold must treat the three lanes as one
selection family. A valid canonical null closes its family; it is not tuned or
rerun to pass. Any later hypothesis needs a separately preregistered family
and a new owner-authorized permanent look budget.

## 8. Resume prompt

```text
Do not begin another strategy milestone. Read CLAUDE.md, AGENTS.md, the Action
Plan, THREE_STRATEGY_PROJECT_DIRECTION.md, the shared workflow, and the chosen
lane record. In a separate clean checkout, Claude independently reviews every
commit from a4f58e6 through the exact published lane head: Analyst d8d0ad6,
Insider 8a65e3c, or Short Interest 0a77b9c. The review stays on that same
long-lived lane branch, gives every commit an explicit disposition, retains a
P0-P3 ledger, mutation-checks dangerous boundaries, updates only that lane's
record, and pushes any authorized correction without rewriting history. Codex
then counter-reviews every Claude commit and reruns affected plus full
validation before acceptance or any next milestone. The root remediation
branch uses the generic separate-review-branch workflow if it is reviewed as
its own generic workstream. Access no provider, credential, licensed row,
outcome, QuantConnect job, broker, operator database, live scheduler, or
deployment surface. Provider/outcome access remains an open owner decision;
preserve zero looks, paper-epoch-006, and the untouched shared final holdout.
```
