# Project direction — three strategies developed in parallel

Status: **OWNER-DIRECTED MAIN-LINE COORDINATION RECORD, 2026-08-26;
OWNER-COORDINATED FOURTH-FAMILY AMENDMENT, 2026-08-29.**

This document states the direction of the project while the strategy-research
work is split across three long-lived branches. It coordinates the lanes; it
does not authorize a research outcome run, vendor access, QuantConnect job,
paper/live deployment, broker action, or autonomous trading.

**Owner-coordinated shared-family amendment, 2026-08-29:** the original
three-lane operating topology below remains unchanged. Target-Price Revisions,
which has its own separately governed branch and workflow, is now the fourth
canonical family and the fourth attempt in the shared selection accounting.
The common cutoff session is **2027-08-31**; the untouched shared final holdout
is **2027-09-01 through 2029-08-31**; and the Target-Price Revisions one-shot
lane-validation period is **2026-09-01 through 2027-08-31**. This schedule
originated in the owner-directed Analyst Revisions V2 freeze at `b912459`, was
independently accepted at `1507777`, was accepted by Codex counter-review at
`31c313e`, and is expressly extended to the fourth family by the owner's
current approval. It grants no credential, provider, licensed-row, outcome,
research-look, QuantConnect, QC-processing, broker, paper/live, deployment, or
trading authority.

The exact shared baseline is
`c9dcdb647914acbfcefce187a138f52fcdad0c68`, descended from `origin/main` at
`6156ef9b92737c9b390a96d286b0fbde4ff4b19c`. All three strategy branches began
at that same commit:

| Lane | Long-lived branch | Research objective |
|---|---|---|
| Analyst Revisions V2 | `codex/strategy-analyst-revisions-v2` | Test whether point-in-time stock-level analyst upgrades/downgrades, aggregated through ETF holdings under the owner V2 blueprint, produce an independently validated ETF signal. |
| Insider Buying | `codex/strategy-insider-buying` | Test whether narrowly defined, publicly available Form 4 open-market purchases produce a stock signal that survives stock-first validation and ETF aggregation. |
| Short Interest | `codex/strategy-short-interest` | Test whether official-style twice-monthly changes in short-interest pressure or covering produce useful stock and ETF information without substituting daily short-sale volume. |

The source PDFs, per-lane implementation/session records, shared workflow, and
data-source register live in `docs/Strategy Description/` at the common
baseline. The PDFs govern their respective research designs unless the owner
records a later explicit amendment.

## 1. Operating model

The project uses three Codex implementation sessions and three Claude review
sessions, one pair per strategy. Each lane's agents operate in their own
clone or worktree; two lanes, or two agents inside one lane, never share a
checkout. Work is independent and serialized inside each lane:

1. Codex implements one bounded milestone, validates it, updates the lane
   record, commits, and pushes the lane branch.
2. Claude independently reviews every new Codex commit and changed file,
   records commit dispositions and a P0-P3 ledger, corrects only confirmed
   defects, adds regression guards for its own corrections, updates the lane
   record, commits, and pushes that same branch.
3. Codex counter-reviews every Claude commit, independently reproduces
   material claims, corrects confirmed defects, and adds dangerous-direction
   regressions. If the review is accepted or accepted-after-correction and no
   owner decision blocks progress, Codex implements the next bounded lane
   milestone, validates both stages, updates the lane record, and makes one
   combined push.
4. Claude reviews that exact combined push, and the loop repeats from step 3.

**Owner clarification, 2026-08-26:** the standing Codex counter-review step
remains required. The instruction that removed it was accidental and is
superseded by this operating model.

No implementation, review, counter-review, checkpoint, or handoff branch is
created inside a strategy lane. Only one agent writes or pushes a lane at a
time. No published history is rebased, force-pushed, or rewritten.

## 2. Isolation and documentation ownership

Each strategy branch may change only its own implementation, tests, fixtures,
artifacts, and lane record. It must not change another strategy or silently
introduce a shared abstraction that forces the other lanes to follow it.

During parallel development, strategy-lane agents must not edit:

- `docs/ACTION_PLAN_2026-08-20.md`;
- `docs/SESSION_HANDOFF.md`;
- this main-line direction record;
- the shared workflow/data-source register;
- another lane's source PDF or implementation record; or
- repository-shared files whose change would bind every lane at merge time:
  `requirements.txt`, `config.py`, CI/tooling configuration, and shared test
  or classification manifests.

Each lane keeps its new code, tests, and fixtures in lane-owned modules and
test files named for its strategy, so the eventual merges cannot collide. A
lane that genuinely needs a new dependency or a shared-file change stops and
asks for one common-baseline amendment instead of editing the file on its
branch.

Every lane push updates its own implementation record with exact starting and
ending commits, role, milestone, files, validation, findings, data vintages,
outcome-look accounting, remaining gates, and next authorized step. That
record is the branch-local handoff.

Only an owner-directed main-line coordination change may update this document,
the Action Plan, or the root Session Handoff while the lanes are parallel.
This prevents three conflicting versions of project-wide state.

### One-time common-remediation exception (owner direction, 2026-08-26)

The owner has authorized one bounded synchronization from
`codex/full-review-p1-remediation-20260826` before the ordinary per-lane loop
resumes. Shared safety fixes from that remediation series may be synchronized
identically to all three named strategy lanes, including the minimum shared
files and regression tests required to preserve those fixes. Analyst-specific
research-layer fixes may be synchronized only to
`codex/strategy-analyst-revisions-v2`; they must not enter the Insider Buying
or Short Interest lanes. Each target lane updates only its own implementation
record with the exact synchronized commits, validation, zero-access accounting,
and remaining review gates.

This is a one-time exception to the shared-file freeze, not a new shared
development model. Synchronization is not acceptance: acceptance remains
withheld until Claude reviews the exact pushed snapshot on each same lane
branch and Codex counter-reviews every Claude commit. The synchronization
grants no credential, provider endpoint, licensed row, or outcome access; no
QuantConnect research or backtest job; no QC processing or upload permission;
no broker or operator-database action; no paper/live deployment; and no
trading authority. After the three owner-directed synchronizations and lane
record updates, this exception expires. Any later common-baseline or shared-
file change again requires a separate owner decision.

## 3. Common implementation discipline

Although the signals differ, every lane follows the same evidence ordering:

1. **Contract and fixture stage:** freeze schemas, point-in-time availability,
   identities, correction/amendment behavior, exclusions, formulas, costs,
   outcome horizons, multiplicity, and the permanent look budget. Use synthetic
   and offline fixtures only.
2. **Immutable data stage:** build content-addressed, versioned ingest with
   exact source lineage and fail-closed refusals. Do not overwrite corrected
   or amended history.
3. **Stock-signal stage:** implement the PDF's canonical stock-level signal
   and keep diagnostics/extensions separate. Prove timing and dangerous
   failure directions before importing outcomes.
4. **Stock-first evidence stage:** preregister and perform the bounded
   stock-level event study. Industry and ETF aggregation cannot rescue a null
   stock hypothesis by post-result tuning.
5. **ETF topology stage:** construct a point-in-time reverse constituent index,
   enforce mapping/coverage/eligibility rules, and compare stock, industry,
   and ETF information honestly.
6. **Walk-forward portfolio stage:** use frozen baselines, realistic costs,
   untouched validation/test periods, capacity, turnover, overlap,
   concentration, and null/underfill rules.
7. **QuantConnect research stage:** reproduce the frozen logic using immutable
   custom/precomputed signals. Vendor APIs must not be called from a backtest.

Canonical work is unlevered. No branch may add leverage, inverse exposure,
options, short selling, machine learning, outcome-informed thresholds, or a
combined ensemble unless its PDF and a later owner-approved milestone
explicitly permit that exact extension.

## 4. Data direction

- Analyst Revisions starts from the existing immutable Massive-Benzinga
  ratings backbone, but still needs V2 ontology/timing/identity/signal/ETF
  implementation and verified vendor-to-QC processing rights.
- Insider Buying uses the free SEC insider datasets plus complete Form 4/4-A
  filing metadata and EDGAR acceptance times. A paid insider feed is optional,
  not a canonical research prerequisite.
- Short Interest needs a licensed historical/vintage security-level source
  such as Intrinio or an equivalent, plus the official FINRA publication
  calendar. Daily short-sale volume is not a substitute.
- All lanes need audited point-in-time security identity, prices/corporate
  actions, ETF constituents/weights, classifications, and relevant
  fundamentals. A generic QuantConnect subscription is not proof of each
  entitlement or historical availability rule.

No credential, licensed row, provider endpoint, or outcome is accessed merely
because a branch exists. Acquisition, structural audit, and research-look
authority remain separate owner decisions.

Structural audits of providers that serve every lane — QuantConnect dataset
entitlements, the security master, prices/corporate actions, ETF
constituents, calendars — are main-line coordination tasks: the owner
authorizes one audit, one agent performs it, and the result is recorded once
by a common-baseline amendment. Three lanes must not separately audit, or
separately characterize, the same shared account.

## 5. Main-line integration direction

Parallel development of the original three lanes ends only after each of those
three canonical strategies has completed its independent
review/counter-review chain and has an honest disposition: accepted,
accepted-after-correction, rejected, or valid null. Target-Price Revisions is
separately governed and does not block the original three-codebase integration
mechanics below. A valid null closes its lane's canonical family; the lane must
not tune or rerun that family to make it pass. Any later hypothesis must be a
separately preregistered family with a new owner-authorized permanent look
budget, and it cannot retroactively rescue the canonical result.

Because the common outcome evaluation must be untouched by all four families, the
one shared final-holdout boundary is frozen at cutoff session **2027-08-31** with
reserved period **2027-09-01 through 2029-08-31**. Every family's
preregistered split must leave that shared period unconsumed. Target-Price
Revisions uses the distinct one-shot validation period **2026-09-01 through
2027-08-31** and may not use the holdout. The common evaluation treats the
four canonical families as one selection family: its evidence thresholds must
account for the fact that surviving strategies were selected from four
attempts. This shared selection accounting does not merge their lane-level
family IDs, permanent look budgets, or evidence epochs. The common four-family
outcome evaluation remains prohibited until Target-Price Revisions also has an
independently reviewed honest disposition and the owner separately schedules
that evaluation.

The owner then schedules a separate integration milestone. That milestone
must:

1. select and record a deterministic merge order;
2. reconcile only genuinely shared schemas or storage contracts after seeing
   all three reviewed implementations;
3. freeze late-fusion rules, signal correlations, capital/risk budgets,
   turnover, overlap, concentration, and failure behavior without consulting
   the final holdout;
4. build the deterministic combined-evaluation harness with realistic costs,
   while leaving the common four-family outcome evaluation disabled until the
   prerequisite above is satisfied;
5. implement and independently verify one QuantConnect algorithm whose
   research inputs cannot acquire execution authority; and
6. require separate owner approval for paper deployment, evidence collection,
   and any later live promotion.

The ultimate target is a single supervised/autopiloted QuantConnect trading
agent, but reaching that target is a sequence of evidence and authorization
gates—not an automatic consequence of merging three codebases. It must retain
risk limits, reconciliation, monitoring, incident handling, kill switch,
rollback, and a safe no-signal/no-data state.

## 6. Relationship to project separation and operations

SEP-3 remains frozen and incomplete at its independently accepted eighth dry
run. Strategy development does not authorize physical repository extraction,
change the planned two-product-plus-tiny-shared-contract topology, or resolve
any SEP-3 blocker. SEP may resume only by a later owner instruction.

`paper-epoch-006` remains untouched. Nothing in this direction changes the
current assistant's human-approval, paper-only, policy, exposure,
reconciliation, or execution-gate boundaries.

## 7. Historical 2026-08-26 completion and current shared amendment

Claude may independently review this main-line coordination record and the
common branch baseline. After that review, each Codex strategy session starts
only the first contract/fixture milestone named in its own implementation
record. No lane starts a real-outcome study or QuantConnect execution by
inference.

**Claude review, 2026-08-26 (owner-directed):** the coordination record and
the common baseline `c9dcdb6` were reviewed against the workflow, the
data-source register, all three lane records, and the consistency tests; the
three published lane heads were re-verified at the stated baseline commit.
The direction was accepted with four amendments incorporated above: per-lane
checkouts, a frozen shared-file list with lane-owned namespaces, a shared
final-holdout reservation with cross-lane selection accounting, and
single-execution main-line audits for shared providers.

**Codex counter-review, 2026-08-26:** accepted after correction (`a6cc4fb`);
the commit disposition and P0-P3 ledger are in
`docs/Archive/Review/COUNTER_REVIEW_2026-08-26_THREE_STRATEGY_DIRECTION.md`.
The owner later clarified that removing future counter-reviews was accidental;
the standing counter-review-plus-next-milestone loop remains required, as
recorded in section 1.
Finalization — publishing this record, merging it to `main`, and
fast-forwarding the three lane branches onto the merged head so every lane
carries the final coordination documents — precedes the creation of the three
Claude lane review sessions. After finalization, each Codex strategy session
starts only the first contract/fixture milestone named in its own
implementation record.

**Current amendment step, 2026-08-30:** the historical three-lane
finalization above is complete and remains unchanged. The separately governed
Target-Price Revisions lane has a local owner-approved TPR-0A candidate; its
next action is one exact-snapshot push followed by Claude review and Codex
counter-review on that lane's same branch/worktree. This shared record freezes
only four-family selection accounting and the common final-holdout boundary;
it grants no source, outcome, look, QuantConnect, broker, deployment, paper,
live, or integration authority.

**Status update, 2026-09-04 (owner-directed bug-fix integration):** the
"one exact-snapshot push" named in the 2026-08-30 step above has happened. The
Target-Price Revisions documentation round is merged through PR #324
(`1a5264e6b1de3caf5477477d1312a762b2d42419`), and that lane has since
completed further same-branch Claude review and Codex counter-review rounds
recorded only in its lane record. This paragraph corrects the stale
next-action sentence (`TPR-OOL-007`); it changes no allocation, gate, or
authority. The owner-directed cross-lane bug-fix integration of 2026-09-04 is
recorded in `docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md`.
