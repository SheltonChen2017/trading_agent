# Session handoff — current project state

Prepared: 2026-08-28 by Codex after completing the main-line counter-review of
Claude's root-remediation review and correction series. This is the canonical
generic-workflow handoff for the root project. The three strategy lanes remain
independent and were not inspected, modified, synchronized, or reviewed here.

## 0. Root-remediation counter-review handoff

- Active local branch:
  `codex/counterreview-root-remediation-20260827`.
- Published base and unchanged local `main`/`origin/main`:
  `6a507341896850076c13050da080f888d6eb31aa`.
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
- Open P2 items: a safe evidence contract for risk-reducing sells when an
  unrelated position row makes the account book incomplete (`BRK-001`), and an
  authenticated corrupt-journal repair/quarantine/restore workflow.
- Open P3 items: independently observed per-order account provenance, exact
  limit-price transport across the final broker boundary, authenticated
  broker-event-ledger checkpoints, bounded Decimal/reporting serialization,
  and explicit documentation/process isolation for the same-process Python
  trust boundary.
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
- No feature milestone completed and no sequencing, gate, or next-step status
  changed, so `docs/FEATURE_MILESTONE_RECORD.md` and
  `docs/ACTION_PLAN_2026-08-20.md` remain unchanged.
- The branch and its commits are local-only; no push was performed. Push only
  if the owner explicitly requests it. Otherwise archive this session until
  the three strategy lanes complete. The owner will then initiate a new
  whole-project review from the exact integrated `main` snapshot.

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
Resume this root task only if the owner explicitly asks to push the completed
counter-review, or after all three strategy lanes are integrated and the owner
initiates the next whole-project review. Read CLAUDE.md, AGENTS.md,
ACTION_PLAN_2026-08-20.md, THREE_STRATEGY_PROJECT_DIRECTION.md, and
COUNTER_REVIEW_2026-08-27_ROOT_REMEDIATION.md. Preserve implementation commit
242f8eb7ef5022ed17e86502896ae19e7621e55c and report commit
699f6bc970f1ab5978c9a994d803b5dc09fc1fbd. Do not modify or synchronize the
Analyst Revisions V2, Insider Buying, or Short Interest branches/worktrees from
this task. If pushing is requested, first verify the current branch, exact
HEAD, clean worktree, unchanged origin/main at 6a50734, and all three local
commits; do not force-push. If starting the later review, begin from the exact
post-integration main snapshot and establish a new bounded commit range under
the generic separate-review-branch workflow. Access no provider, credential,
licensed row, outcome, QuantConnect job, broker, operator database, live
scheduler, deployment, paper-order, live-order, or evidence-epoch surface.
Provider/outcome access remains an open owner decision; obtain that
authorization before any such audit or run. Preserve zero looks,
paper-epoch-006, and the untouched shared final holdout.
```
