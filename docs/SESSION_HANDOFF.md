# Session handoff — current project state

Prepared: 2026-08-26 by Codex for the owner-directed main-line coordination of
the three-strategy parallel development program.

This concise handoff replaces the SEP-3 pause-transition snapshot. Historical
detail remains at
`docs/Archive/Session/SESSION_HANDOFF_THROUGH_2026-08-25_SEP3_EIGHTH_DRY_RUN.md`
and in `docs/Archive/Review/`.

## 1. Read first

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/ACTION_PLAN_2026-08-20.md`.
3. `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`.
4. `docs/Strategy Description/README.md`.
5. `docs/Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md`.
6. The selected lane's PDF and implementation record.
7. `docs/Strategy Description/THREE_STRATEGY_DATA_SOURCE_REGISTER.md`.
8. `docs/architecture/SEP3_FREEZE_STATE_2026-08-25.md` before any separation
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
- Main-line direction is being prepared on
  `codex/main-three-strategy-direction-20260826`, descended from the shared
  baseline so the strategy branches retain one common history after merge.

The three owner PDFs were inspected as text and visually page by page. Their
page counts, byte sizes, and SHA-256 hashes are pinned in the lane records.
No strategy code, vendor data, outcome, backtest, or QuantConnect job was
executed while creating this baseline.

## 3. Parallel-work exception and handoff rule

During the three-lane phase, agents must not edit this handoff or the Action
Plan on any lane. This common baseline is the one authorized update before the
branches diverge. The relevant lane implementation record becomes that
branch's status, review ledger, validation record, and resume prompt.

The owner-directed main-line coordination surface is
`docs/THREE_STRATEGY_PROJECT_DIRECTION.md`. Only a separately directed
main-line coordination change may update that record, this handoff, or the
Action Plan while strategy branches are active.

Codex implements, Claude independently reviews, and Codex counter-reviews on
the same strategy branch. No review/counter-review branch is created. Work is
serialized: fetch and fast-forward, verify exact branch/HEAD/status, commit one
bounded stage with its record update, then push. Never force-push or rewrite
published lane history.

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

## 8. Resume prompt

```text
Select exactly one strategy lane and use its long-lived codex/strategy-*
branch. Read CLAUDE.md, AGENTS.md, the shared workflow, that lane's owner PDF,
implementation record, and the data-source register. Verify exact branch,
HEAD, upstream, and clean status. Do not edit the Action Plan, Session Handoff,
shared workflow/data register, another lane, or SEP-3. Codex implements one
bounded milestone and updates the lane record before pushing; Claude reviews
the exact pushed commits on the same branch; Codex counter-reviews there.
Access no outcomes or providers unless that exact action is separately
authorized and preregistered; provider access is an open owner decision.
Preserve paper-epoch-006.
```
