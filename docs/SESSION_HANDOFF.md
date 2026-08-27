# Session handoff — current project state

Prepared: 2026-08-26 by Codex for the owner's requested interim push of the
Analyst/full-project remediation candidate. This is a durable checkpoint, not
an acceptance record: documentation reconciliation, exact-final-tree full
validation, three-lane synchronization, Claude independent review, and Codex
counter-review remain open.

## 0. Interim remediation checkpoint

- Branch: `codex/full-review-p1-remediation-20260826`.
- Exact implementation/merge snapshot before this handoff update:
  `fc05c26bcc19f32b532942d825df3d33dd26bfc9`.
- Governing `origin/main` merged into that snapshot:
  `25724728977696a79547107be3114a52b74fc3fc`.
- Shared safety implementation: `bf82838`; Analyst-only authority layer:
  `e13baa1`; mixed shared/Analyst architecture registration: `8cab638`;
  remediation and Analyst-record checkpoints: `7d4e12f` and `ee17967`.
- Focused validation on the integrated code tree: **344 Analyst/ACER tests
  passed**; **622 execution-safety tests passed and 2 skipped**; repository
  compilation and `git diff --check` passed. These are implementation checks,
  not the still-required final full-suite result or independent acceptance.
- The remediation ledger still requires reconciliation from 84 documented
  IDs to the complete 109-finding inventory (P0=0, P1=46, P2=49, P3=14).
  Governing workflow records and lane records also require their final exact
  synchronization heads and validation evidence.
- The three published strategy branches remain at
  `a4f58e6e0d0cf3d4ca08903e9184846259b17e24`; none has received or published
  this remediation yet. Shared fixes must later reach all three, while
  Analyst-specific code must reach only
  `codex/strategy-analyst-revisions-v2`.
- No provider, licensed row, outcome, QuantConnect job, broker, operator
  database, scheduler, deployment, evidence epoch, paper order, or live order
  was accessed or changed. No research or trading authority was created.
- Analyst identity semantics remain explicit: the measured `768` diagnostic
  count is a **lower bound**, never an **allowlist**; **current-ticker joins are
  prohibited**. **Normative strategy design** and **observed provider**
  availability/history remain separate evidence categories.
- Resume by completing the 109-item ledger and active-document reconciliation,
  running focused plus complete validation on the exact final tree, then
  constructing, validating, and non-force-pushing the three lane updates.

The owner clarification remains binding: the instruction removing Codex
counter-review was accidental and is superseded. The standing lane loop is
Codex implementation, Claude independent review, then Codex counter-review
plus the next bounded milestone before one combined push.

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

## 3. Parallel-work exception and handoff rule

During the three-lane phase, agents must not edit this handoff or the Action
Plan on any lane. This common baseline is the one authorized update before the
branches diverge. The relevant lane implementation record becomes that
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

Lane agents also leave repository-shared merge surfaces unchanged, including
`requirements.txt`, `config.py`, CI/tooling configuration, and shared test or
classification manifests. New code, tests, and fixtures use lane-owned
strategy namespaces. A true shared-file or dependency need stops for one
owner-directed common-baseline amendment.

## 4. Strategy state

### Analyst Revisions V2

The active V2 record is
`docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md`.
Existing `research/acer/` code supplies a reviewed immutable ratings-event
backbone only. It does not implement the V2 firm-specific rating ontology,
institution-stock-day dedupe, 20-session signal, sector standardization,
reliability shrinkage, consensus/novelty diagnostics, ETF mapping, portfolio,
walk-forward study, or QC algorithm. No V2 outcome look exists.

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
Select exactly one strategy lane and use its long-lived codex/strategy-*
branch in its own dedicated clone or worktree. Read CLAUDE.md, AGENTS.md, the
main-line direction, shared workflow, that lane's owner PDF, implementation
record, and the data-source register. Verify exact branch, HEAD, upstream, and
clean status. Do not edit the Action Plan, Session Handoff, shared
workflow/data register, another lane, SEP-3, requirements.txt, config.py,
CI/tooling configuration, or shared test/classification manifests. Codex
implements one bounded milestone in lane-owned files and updates the lane
record before pushing; Claude reviews the exact pushed commits on the same
branch from a separate checkout; Codex then counter-reviews every Claude
commit, corrects confirmed defects, and, only when accepted and unblocked,
implements the next bounded milestone before one combined push. Access no
outcomes or providers unless that exact action is separately authorized and
preregistered; provider access remains an open owner decision. Before any
real-outcome study, freeze the one shared final holdout and three-attempt
selection contract. Preserve paper-epoch-006.
```
