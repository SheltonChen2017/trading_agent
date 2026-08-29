# Target-Price Revision ETF Strategy - implementation and session record

Status: **DOCUMENTATION-ONLY PLANNING BASELINE; NOT YET INDEPENDENTLY
REVIEWED OR SCHEDULED FOR IMPLEMENTATION. NO AUTHENTICATED TARGET-PRICE
SOURCE, INGEST, CANONICAL EVENT, SIGNAL, OUTCOME ACCESS, RESEARCH LOOK, ETF
TOPOLOGY, PORTFOLIO, QUANTCONNECT JOB OR RESULT, SHADOW OR PAPER DEPLOYMENT,
BROKER CONNECTION, OR LIVE-TRADING AUTHORITY EXISTS.**

Branch: `codex/strategy-target-price-revisions`

Worktree:
`C:\git\customizedAgent\trading_agent_TargetPriceRevision`

Base commit:
`086b782e43a5ff889e71ec8e26334bb791ccac74`

Governing plan:
`TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf`

Governing plan SHA-256:
`9f00dd56bf7bec79b3f5362bba61fe71768d1f25e6e4350631dafd1253682633`

Governing plan page count: **26**.

Submitted source-plan SHA-256:
`53c549aef18aa1a63e6db8deb184bd654eb8ec637bb4ff3ae03f29abc4a2df0`

The governing PDF and this record are specifications, not research evidence,
deployment approval, or trading authority. Codex is the primary implementer
and Claude is the independent reviewer. This fourth lane is not covered by the
three named lanes' same-branch exception.

## 1. Decision and canonical strategy boundary

The submitted target-price plan is technically feasible, but it was not safe
to implement as written. Its target-specific economics are strong; its timing,
as-of correction handling, contributor independence, hard-validity boundary,
coverage definitions, multiplicity, statistical gates, and automatic
shadow-to-live language were materially weaker than the active Analyst
Revisions V2 contract. The revised PDF retains the useful target-price
research and replaces the unsafe degrees of freedom.

Target-price revisions are a separate research and evidence family from the
rating-only Analyst Revisions V2 strategy.

The canonical target-price event is deliberately narrow:

- admit only a genuine raise or lower with finite, positive prior and current
  targets, stable institution identity, permanent security identity, known
  target currency and share basis, comparable target horizon, and auditable
  public availability;
- initiation, announcement without a comparable prior target, withdrawn,
  suspended, missing, zero, non-finite, unresolvable-currency, and
  ambiguous-correction records receive explicit named dispositions rather
  than being interpreted as revisions or structural zero;
- retain effective/event time, earliest verified public-availability time,
  ingest time, correction/version time, immutable source identity, and
  supersession lineage;
- use an exact intraday timestamp only after its earliest-public-availability
  semantics are proven. Otherwise use the frozen conservative date-only
  exchange-session rule;
- compute the primary stock feature from the split- and currency-consistent
  target change scaled by the point-in-time pre-event stock price. Raw target
  change, percentage target change, target upside, paired-consensus change,
  unexpected residuals, rating actions, and target levels remain separate
  diagnostics or preregistered extensions;
- reconcile raw and vendor-adjusted targets before use so corporate actions
  are not applied twice. Unknown split basis, currency basis, FX vintage, ADR
  ratio, target horizon, or correction state fails the canonical gate;
- permit at most one contribution per institution, security, session, and
  common catalyst at the decision cutoff. Raw analyst/event count is not
  independent breadth; canonical breadth conservatively reflects institution
  and catalyst concentration;
- treat timing, identity, mapping, correction state, split basis, currency,
  target horizon, point-in-time provenance, and required-field completeness as
  binary validity gates. Only noncritical measured diagnostics may affect
  reliability;
- do not call reliability `confidence` unless prospective calibration is later
  frozen, measured, and accepted;
- distinguish missing observations from structural zero. Sparse sectors and
  zero-MAD groups return named invalid/sparse states rather than invented
  epsilon variance; and
- use only information available at the frozen decision cutoff. Later
  corrections become active only at their own availability time and never
  rewrite an earlier decision state.

The stock-level test is the first stop/go decision. A valid canonical null
closes this target-price family; ETF aggregation, a rating blend, or another
diagnostic cannot rescue it.

ETF aggregation, if unlocked, uses point-in-time holdings with a fixed audited
availability lag, permanent security identities, a complete eligible universe,
and at least 99% mapped candidate holdings weight. The canonical ETF exposure
is the raw holdings-weighted stock exposure with monotone reliability
shrinkage; it is not divided by covered weight. Mapping, feature-observed
weight, active-signal weight, concentration, effective count, breadth, overlap,
peer category, and unmapped weight remain separate diagnostics and gates.

The canonical implementation is deterministic. ML and LLM output has no
authority to create, approve, size, submit, cancel, replace, or suppress an
order. No leverage, inverse-ETF overlay, rating/target fusion, or capital
expansion is part of the initial family.

## 2. Relationship to Analyst Revisions V2 and reuse boundary

The Analyst Revisions V2 lane remains a rating-only family and explicitly
classifies price targets as a separate future family. This lane therefore has
its own permanent family identifiers, schemas, event semantics, dataset
lineage, preregistration, look budget, evidence epochs, results, and promotion
decisions.

Only exact, accepted, independently reviewed infrastructure may later be
synchronized or extracted deliberately. Potentially reusable infrastructure
includes immutable snapshot and dataset identity, availability contracts,
permanent security identity, point-in-time holdings, cost calculations,
statistical primitives, portfolio safety controls, preregistration gates, and
import firewalls.

The following must not be inherited:

- rating ontology, rating normalization, or the rating canonical score;
- rating events relabeled as target-price evidence;
- target fields treated as authenticated merely because a rating parser can
  see them;
- result identifiers, permanent-look receipts, multiplicity allocations,
  evidence epochs, production registries, promotion evidence, or review
  acceptance; or
- unaccepted work from another branch.

This lane is based on current `main` at
`086b782e43a5ff889e71ec8e26334bb791ccac74`, not on the unaccepted Analyst
Revisions candidate at `56d6fe0eff32d00b1692b3b17a3838649eeba56b`.
Any later synchronization must name the exact accepted source commit, preserve
provenance, receive target-lane review, and update this record.

Before target-price outcome access, the project-wide multiplicity authority
must either add this fourth selection family to the frozen correction and look
budget or explicitly exclude it from the shared family. The common final
holdout must likewise be amended or explicitly remain unreachable. Silence or
a local configuration value grants no authority.

## 3. Normative version-2 corrections

1. Separate target and rating families, evidence epochs, looks, results, nulls,
   and later integration.
2. Reconcile only the latest event version available by each cutoff, never the
   final state learned later that day.
3. Use the first eligible open after both availability and the frozen batch
   cutoff; date-only rows use the conservative second-open rule. Same-day
   premarket execution is not canonical.
4. Aggregate by stable institution and discount shared catalysts before
   claiming independent breadth.
5. Separate binary validity from measured reliability; prohibit uncalibrated
   confidence.
6. Make split basis, currency, FX vintage, ADR ratio and target horizon hard
   contracts; prohibit double adjustment.
7. Add a complete PIT stock universe, controls, delistings and terminal
   outcomes.
8. Refuse sparse or zero-dispersion normalization rather than inventing
   epsilon variance.
9. Separate identity mapping, feature-observed weight and active-signal weight;
   retain a hard 99% mapped-holdings gate.
10. Freeze PIT peer construction, holdings availability lag and overlap policy
    before ETF outcomes.
11. Register one primary stock cell and every secondary/exploratory trial under
    permanent append-only look authority.
12. Use exact pass/null/invalid/insufficient dispositions. A valid null closes
    the target family; no ETF or secondary rescue.
13. Model commission, spread, square-root impact, capacity, auction gaps,
    rejected/unfilled orders, and 0/5/10/20-bps sensitivities.
14. Keep provider normalization outside LEAN and make QC consume a complete,
    immutable, hash-verified decision packet with no vendor API call.
15. Include explicit exits, stale-addition/risk-reduction separation,
    idempotent intent keys, restart recovery, and reconcile-before-retry.
16. Replace automatic deployment with separately authorized shadow, paper,
    restricted-live, and bounded-unattended stages.
17. Add health/SLO monitoring, fixed capital/risk envelopes, kill switch,
    incident evidence, tested rollback, and new approval for every expansion.
18. Use the generic separate-review topology until the owner explicitly
    extends the three-lane exception.

## 4. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| TPR-0 | Freeze coordination, family identifiers, source contract, event taxonomy, four clocks, cutoff, formula, split/FX/ADR/horizon rules, corrections, independent unit, primary stock cell, controls, periods, purge/embargo, costs, practical-effect threshold, sample/power rule, multiplicity, look budget, null disposition, and final-holdout boundary. | Reviewed, content-addressed executable preregistration; every owner decision resolved; outcome access remains impossible. |
| TPR-1 | Implement immutable provider-specific target-price ingest, exhaustive normalization/refusal, raw-page inventory, corrections, supersession, and stable institution/analyst provenance. | Every raw locator has exactly one accepted or refused disposition; schema, duplicate, missing, non-finite, action, time, and correction mutations pass; structural data only. |
| TPR-2 | Implement point-in-time issuer/security/share-class identity, historical ticker validity, split/target-basis reconciliation, currency and FX vintage, ADR ratios, target horizons, pre-event price, ADV/cost inputs, controls, delisting, and terminal-return prerequisites. | Ticker reuse, share-class, corporate-action, FX, horizon, delisting, stale-price, and ambiguous-basis mutations fail closed; no outcome look. |
| TPR-3 | Implement the canonical stock score, institution/security/session/catalyst aggregation, decay, robust sector normalization, independent breadth, validity, and measured reliability. Keep target upside, paired consensus, unexpected residual, rating action, and target level in separate channels. | Golden equations, sparse/zero-MAD behavior, cutoff slicing, correction lineage, and import-boundary tests pass; no outcome imports. |
| TPR-4 | Register and run the one-shot stock-first study using the frozen primary cell, controls, costs, purged grouped walk-forward design, clustered/block inference, exact multiplicity, and external append-only look spend. | Permanent look receipt recorded. A valid null closes the family. A pass must clear both statistical and frozen practical-effect gates without touching the shared final holdout. |
| TPR-5 | Only after a TPR-4 pass, build the point-in-time ETF reverse index, universe, peer taxonomy, holdings availability, mapping, and reliability-aware aggregation. | At least 99% mapped candidate holdings weight; fixed lag, stale/incomplete holdings, category lineage, unmapped weight, concentration, and bypass tests pass. |
| TPR-6 | Run preregistered walk-forward ETF research and direct-stock, industry, market, liquidity, momentum, rating, and naive-ETF baselines on identical observations. Model commission, half-spread, square-root impact, opening gaps, turnover, and 0/5/10/20-bps sensitivities. | Frozen OOS, robustness, capacity, turnover, concentration, overlap, underfill, cost, and null gates pass. A null or invalid result is retained and cannot be promoted. |
| TPR-7 | Implement QuantConnect research/backtest parity using only verified immutable custom or precomputed signals and complete daily manifests. No vendor API is called by the algorithm. | Offline/QC signal, calendar, cutoff, sizing, cash, cap, cost, stale-data, exit, and refusal parity pass; research-only and no order authority. |
| TPR-8 | Produce the independently reviewed lane dossier, including lineage, look receipts, nulls, sensitivity results, capacity limits, known failure modes, and an integration decision without opening the shared final holdout. | Exact candidate and evidence epoch reviewed; owner and Action Plan decide whether any prospective operational stage is scheduled. |
| TPR-9 | Run deterministic live-data shadow operation with production-shaped manifests, schedules, decisions, monitoring, restart recovery, and reconciliation simulations but no order submission. | Frozen prospective sufficiency rule met; lineage/parity stable; stale, duplicate, restart, missed-cutoff, kill-switch, and alert drills pass with zero order capability. |
| TPR-10 | Run separately authorized QC paper autopilot with frozen configuration, idempotent intent/order keys, buying-power reservations, broker reconciliation, health checks, alerts, stale-data policy, kill switch, audit trail, rollback, and operator runbook. | Preregistered independent paper sessions and statistical/operational sufficiency met; 100% order-state reconciliation; no unresolved critical incident; owner reviews a promotion dossier. |
| TPR-11 | Run a separately authorized restricted-live canary at explicitly frozen account, capital, symbol, order, exposure, loss, schedule, and duration limits. | Explicit owner live authorization, independent review, broker and rollback readiness, prospective evidence sufficiency, and all canary risk/SLO gates pass. No limit or capital expansion is implied. |
| TPR-12 | Promote only under a new explicit authorization to bounded unattended QC operation with fixed capital and risk limits, continuous health/reconciliation, automatic stop rules, durable alerts, restart-safe idempotency, and tested rollback. | Independent review of the exact promotion candidate and prospective record; every SLO, reconciliation, drift, loss, freshness, and recovery gate passes. Each later capital, universe, broker, schedule, or strategy expansion requires another authorization. |

ETF topology is deliberately downstream of the stock-first stop/go test. A
source-capability or schema audit may happen earlier, but no ETF topology may
be tuned against target-price outcomes before TPR-4 passes.

## 5. QuantConnect and bounded-autopilot safety contract

The offline research process owns provider acquisition, normalization,
point-in-time joins, target-price semantics, and immutable signal publication.
QuantConnect consumes only a hash-verified, complete, precomputed decision
artifact. The QC algorithm must not query the ratings vendor, infer missing
targets, silently use a partial universe, or rebuild historical target state
during backtest, shadow, paper, or live operation.

Each QC session binds the strategy version, code commit, dataset and manifest
hashes, configuration, exchange calendar, decision cutoff, evidence epoch, and
eligible universe. Order intent and submission identities are deterministic
and restart-safe. A timeout or network error is ambiguous, not a rejection;
broker reconciliation is authoritative before retry or reservation release.

Missing, stale, incomplete, corrupt, late, rollback, or lineage-mismatched
inputs block new or increasing exposure and create a durable refusal and
alert. Those safeguards must not block legitimate risk-reducing exits. The
kill switch, broker reconciliation, reservations, health monitoring, and
alerting remain available even when the signal path fails.

Shadow, paper, restricted live, and bounded unattended operation are distinct
states. Completion of one does not authorize the next. Backtests and fixtures
prove software behavior only; they are not prospective evidence or trading
authority.

## 6. Authority and evidence state

| Capability or evidence | Current count/state | Authority |
|---|---:|---|
| Authenticated production target-price sources | 0 | None |
| Purchased entitlement, credential use, or provider transfer permission | 0 | None |
| Immutable production raw snapshots | 0 | None |
| Accepted canonical target-price events | 0 | None |
| Accepted production identity, split, FX, price, cost, or terminal-return artifacts | 0 | None |
| Canonical target-price stock scores | 0 | None |
| Point-in-time target-price ETF topologies or scores | 0 | None |
| Outcome-access permits | 0 | None |
| Permanent target-price research looks spent | 0 | None |
| Shared final-holdout accesses | 0 | None |
| Nonempty target-price portfolios | 0 | None |
| QC uploads, jobs, backtests, or results | 0 | None |
| Shadow sessions | 0 | None |
| Paper intents or orders | 0 | None |
| Funded broker connections | 0 | None |
| Restricted-live intents or orders | 0 | None |
| Unattended-live intents or orders | 0 | None |
| Paper, live-canary, unattended, or capital-expansion approvals | 0 | None |

Creating this branch, worktree, PDF, and record changes none of these entries.

## 7. Review and repository topology

The same-branch workflow is an owner exception for exactly three named strategy
lanes and does not extend to this lane by inference. The generic repository
workflow applies unless the owner explicitly changes it:

1. Codex implements one bounded milestone on
   `codex/strategy-target-price-revisions` and stops at a stable, committed
   snapshot.
2. Claude independently reviews that exact snapshot commit by commit on a
   separate `user/claude/...` review branch, maintains the P0-P3 ledger, and
   records an explicit disposition for every commit.
3. Corrections and acceptance follow the standing review and handoff process;
   no next milestone begins until the current snapshot is accepted and the
   Action Plan schedules the next bounded scope.
4. Every implementation or review series updates this authoritative record and
   `docs/SESSION_HANDOFF.md`. The Action Plan receives only a concise reference
   when sequencing, milestone status, a gate, or the next authorized step
   changes.
5. No push, merge, provider access, outcome access, QC job, broker operation,
   paper deployment, or live deployment is authorized merely by this record.

## 8. Exact next step

The exact next step is independent review of the documentation-only baseline,
not TPR-1 implementation or data acquisition:

1. commit the revised PDF and this record on
   `codex/strategy-target-price-revisions`;
2. Claude reviews the exact committed documentation snapshot on a separate
   review branch;
3. Codex resolves or dispositions every review finding and leaves a clean,
   accepted planning snapshot; and
4. only an explicit Action Plan scheduling decision may then start TPR-0.

If scheduled, TPR-0 is limited to the content-addressed preregistration and
zero-outcome structural controls named above. It grants no provider purchase
or credential use, real-data normalization, outcome access, research look, ETF
construction, QC processing, broker action, paper operation, or live trading.

## 9. Session / commit ledger

Append one row for every durable implementation, review, correction, handoff,
or push. Never rewrite or delete an earlier row. Record exact commits once
known.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Authority change | Next |
|---|---|---|---|---|---|---|---|---|
| 2026-08-29 | Codex planning | `086b782e43a5ff889e71ec8e26334bb791ccac74` -> documentation candidate | Documentation only | Created the dedicated branch/worktree, corrected the target-price research/QC plan, added separately gated shadow, paper, restricted-live, and bounded-unattended stages, and recorded lane governance; no code or data. | PDF generated with ReportLab; `pdfinfo` reports 26 letter-size pages and no encryption, JavaScript, forms, or suspect state; all 26 rendered pages visually inspected; extracted text contains every part and final gate; 67 active-document tests passed; the three Markdown staged paths pass `git diff --check`; the staged PDF blob is byte-identical to the visually reviewed file and pinned SHA-256; 0 outcome accesses; 0 looks. | Target-price revisions require a separate family, provider normalizer, timing/basis audit, four-family multiplicity decision, permanent look authority, and independent review. | None; all production, outcome, QC, broker, paper, and live authority remains zero. | Claude independently reviews the exact documentation snapshot; implementation waits for Action Plan scheduling. |
| YYYY-MM-DD | Role | `<start>` -> `<end>` | TPR-N | Concise durable change | Exact tests, artifacts, evidence epoch, and look count | Open/resolved P0-P3 items and blockers | Exact authority added or `none` | Exact next bounded step |
