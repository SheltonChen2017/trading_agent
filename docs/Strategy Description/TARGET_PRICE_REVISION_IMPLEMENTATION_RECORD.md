# Target-Price Revision ETF Strategy - implementation and session record

Status: **CLAUDE'S DOCUMENTATION REVIEW IS COMPLETE. CODEX COUNTER-REVIEWED
EVERY CLAUDE COMMIT, APPLIED THE OWNER-APPROVED V2.1 GOVERNANCE AMENDMENT, AND
IMPLEMENTED THE BOUNDED TPR-0A ALGORITHM/POLICY CANDIDATE IN THE SAME LOCAL
ROUND. THE CANDIDATE IS NOT ACCEPTED UNTIL CLAUDE REVIEWS THE EXACT PUSHED
SNAPSHOT AND CODEX COUNTER-REVIEWS THAT REVIEW. TPR-0B'S EMPIRICAL STRUCTURAL
BINDINGS, TPR-1 SOURCE RIGHTS, AND EVERY OUTCOME/LOOK GATE REMAIN UNAVAILABLE.
NO AUTHENTICATED TARGET-PRICE SOURCE, INGEST, CANONICAL EVENT, SIGNAL, OUTCOME
ACCESS, RESEARCH LOOK, ETF TOPOLOGY, PORTFOLIO, QUANTCONNECT JOB OR RESULT,
SHADOW OR PAPER DEPLOYMENT, BROKER CONNECTION, OR LIVE-TRADING AUTHORITY
EXISTS.**

Branch: `codex/strategy-target-price-revisions`

Worktree:
`C:\git\customizedagent\trading_agent_target_price`

Base commit:
`086b782e43a5ff889e71ec8e26334bb791ccac74`

Governing plan:
`TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf`

Governing plan SHA-256:
`55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`

Governing plan page count: **28**.

Submitted source-plan SHA-256: **MALFORMED, UNVERIFIABLE, HISTORICAL, AND
NON-AUTHORITATIVE.** The value transcribed into superseded historical pages,
`53c549ae...4a2df0`, is 63 hexadecimal characters and therefore cannot be a
SHA-256 digest. The submitted proposal is unavailable and is not a second
authority. By owner decision on 2026-08-29, the version-2 blueprint including
its addendum is the sole normative Target-Price Revisions specification; the
old value cannot satisfy or block any implementation gate.

Sequencing index: `docs/ACTION_PLAN_2026-08-20.md`. Canonical cross-computer
state: `docs/SESSION_HANDOFF.md`. Both receive only concise coordination and
status references for this lane; this record owns the lane's detail.

The governing PDF is the sole normative strategy specification. This record is
a non-normative implementation, review, validation, and handoff log; any
summary here yields to the PDF. Neither artifact is research evidence,
deployment approval, or trading authority. Codex is the primary implementer
and Claude is the independent reviewer.

**Owner workflow override, 2026-08-29:** the owner explicitly extended the
serialized same-branch lane workflow to Target-Price Revisions. All Codex
implementation, Claude review, Codex counter-review/correction, and the next
bounded milestone remain on `codex/strategy-target-price-revisions` in
`C:\git\customizedagent\trading_agent_target_price`. A role may create
several commits during its round, but makes only one push at the end of that
round. No review, counter-review, checkpoint, handoff, or feature branch is
created. This decision supersedes only the governing PDF's old-worktree or
generic separate-review-branch statements on physical pages 3, 21, 23, 25,
and 26; every
research, evidence, safety, outcome, QC, paper, and live gate remains intact.

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

The owner has added Target-Price Revisions as the fourth canonical family and
fourth attempt in the common selection accounting. Its assigned family alpha
is `0.0125` (`0.05 / 4`), its one-shot validation period is 2026-09-01 through
2027-08-31, the shared cutoff is 2027-08-31, and the untouched common final
holdout is 2027-09-01 through 2029-08-31. The holdout remains unreachable to
all four lanes. This resolves coordination only; silence, dates, a local look
object, or a local configuration value grants no source or outcome authority.

## 3. Version-2 correction summary (the PDF governs)

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
18. Use the owner-directed serialized same-branch topology: Codex write,
    Claude review, Codex counter-review plus the next bounded milestone, then
    Claude review again; several commits are permitted within a round but only
    one push occurs at its end.

## 4. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| TPR-0A | Freeze coordination, family identifiers, exact source candidate, event taxonomy, four clocks, cutoff, formula, split/FX/ADR/horizon algorithms, corrections, independent unit, primary stock cell, controls, estimator, period and purge/embargo rules, cost formula, empirical-binding algorithms, four-family multiplicity, planned-unbound primary look, null disposition, and final-holdout boundary. Numeric structural values remain explicitly unbound. | Content-addressed algorithmic preregistration candidate with exact zero-access source/look declarations and a transitive import firewall; independent review and Codex counter-review are still required; outcome access remains impossible. |
| TPR-1 | Implement immutable provider-specific target-price ingest, exhaustive normalization/refusal, raw-page inventory, corrections, supersession, and stable institution/analyst provenance. | Every raw locator has exactly one accepted or refused disposition; schema, duplicate, missing, non-finite, action, time, and correction mutations pass; structural data only. |
| TPR-2 | Implement point-in-time issuer/security/share-class identity, historical ticker validity, split/target-basis reconciliation, currency and FX vintage, ADR ratios, target horizons, pre-event price, ADV/cost inputs, controls, delisting, and terminal-return prerequisites. | Ticker reuse, share-class, corporate-action, FX, horizon, delisting, stale-price, and ambiguous-basis mutations fail closed; no outcome look. |
| TPR-0B | After reviewed TPR-1/TPR-2 structural manifests exist, bind the exact clip, cost/capacity, practical-effect, sample/power, universe/group, reliability, and complete-PIT-history values under the frozen TPR-0A algorithms in a new immutable child artifact. Target-aligned returns, formula performance rankings, and the shared holdout are prohibited inputs. | Child binds the reviewed TPR-0A parent hash, exact reviewed structural inputs, and every required value; independent review and counter-review complete before TPR-3 publication or any outcome/look request. |
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

The owner explicitly assigned this lane the following repeating serialized
cycle. Review independence comes from role separation, exact pushed commit
ranges, evidence, and explicit dispositions, not a separate branch.

1. **Codex write.** Codex implements only the currently authorized bounded
   milestone in this branch and worktree, updates this record, may make several
   local commits, validates the cumulative head, and pushes exactly once at the
   end of the Codex round. Codex then stops.
2. **Claude review.** Claude reviews every commit in the exact pushed Codex
   range and the cumulative tree on this same branch/worktree, maintains the
   P0-P3 ledger, commits any authorized corrections and record updates, may use
   several commits, and pushes exactly once at the end of the Claude round.
3. **Codex counter-review plus next milestone.** Codex reviews and dispositions
   every Claude commit. Codex corrects confirmed defects. If the reviewed
   snapshot is accepted or accepted-after-correction and no owner decision or
   gate blocks progress, Codex implements the next bounded milestone in the
   same round, validates the review corrections and new milestone separately
   and cumulatively, updates this record, and pushes exactly once at the end.
4. **Claude reviews again.** Claude reviews the exact new pushed range and the
   cycle repeats. A rejection or unresolved owner/gate blocker stops before
   next-milestone implementation and before any combined push that would imply
   progress.

No review, counter-review, checkpoint, handoff, or feature branch is created.
Never force-push or rewrite published history. Before committing or pushing,
reverify `HEAD`, the branch, worktree, and uncommitted state. One round may
contain several commits, but it has one push at its end and no intermediate
pushes.

This branch and worktree are dedicated solely to Target-Price Revisions.
Feature code, tests, fixtures, and lane documentation remain target-owned.
If work reveals a defect outside this lane, record its identifier, severity,
evidence, affected paths, safety impact, and proposed future owner-routed work
in the out-of-lane ledger below; do not correct the external area. If the
external defect blocks safe or truthful lane progress, stop at the gate and
request owner direction rather than crossing the boundary.

No push, merge, provider access, outcome access, QC job, broker operation,
paper deployment, or live deployment is authorized merely by this workflow.

## 8. Exact next step

The Codex documentation round was pushed and merged to `main` through PR #324
(`1a5264e6b1de3caf5477477d1312a762b2d42419`). Claude independently reviewed
the exact two-commit set
`{c1798013d911ef54dba82157326c826ac7763ec3,
70c4b9fea1ac119f86901e95b9108820aa80e028}`, equivalently the Git range
`086b782e43a5ff889e71ec8e26334bb791ccac74..70c4b9fea1ac119f86901e95b9108820aa80e028`.
Claude then committed the exact correction and validation range
`70c4b9fea1ac119f86901e95b9108820aa80e028..c0ba616a40f628519a071d0642fadf596982919a`
on this lane. Section 11 preserves Claude's report; section 12 records Codex's
commit-by-commit counter-review and qualifications.

The counter-review correction is local commit
`24283fa3b79b1a86cceb65fbd5d3d2af5fa20292`. It restores the shared active-
document test module to the reviewed Codex tree and moves narrowed guards into
the target-owned test package. The record qualification and exact active-pointer
refinement follow in the current local candidate. No push has occurred in this
Codex round.

The owner's 2026-08-29 decisions resolve those prerequisites without inventing
empirical evidence. The repaired 28-page v2.1 blueprint is the sole normative
strategy authority and is stored as binary at raw SHA-256
`55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`;
the malformed unavailable proposal pin is historical and non-blocking. TPR is
the fourth common family at alpha `0.0125`, with validation 2026-09-01 through
2027-08-31 and the shared 2027-09-01 through 2029-08-31 holdout prohibited.
TPR-0 is split honestly: TPR-0A freezes algorithms now, while TPR-0B binds
empirical structural values only after reviewed TPR-1/TPR-2 manifests and
before TPR-3 or any outcome access.

The bounded TPR-0A candidate is
`research/target_price_revisions/specs/tpr_round0a.candidate.json`, spec ID
`tpr-round0a-candidate-f595992a3f5b8396`, semantic spec hash
`f595992a3f5b8396e5f26ba5a3b0a3f32649eec3fd581071b349a5e12203af86`,
and artifact SHA-256
`99aae28d5b055aa24b84ce153467dfdbe7ee65f8ee2cef2a870efe1e68b2ea49`.
It contains 24 frozen cells, one `planned_unbound` primary look, 39 null empirical
TPR-0B child fields, and 48 total pending bindings including
review, source, identity/basis/cost, look-identity, and external-authority
prerequisites. Empty reviewed-spec, research-source, and permanent-look
authorities plus the target-owned transitive import firewall keep every
provider and outcome surface unreachable. The exact estimator mechanics are a
Codex implementation proposal under the owner-approved v2.1 phase split, not
owner-supplied empirical evidence; they remain subject to Claude review.
The planned look records identity and period only; no look is authorized or
spent.

The exact next role action after this Codex round's single push is Claude's
independent commit-by-commit review of the full pushed range and cumulative
tree on this same branch/worktree. The v2.1 blueprint and TPR-0A artifact are
candidates until that review and Codex counter-review complete. TPR-1 source
implementation remains blocked until a separately reviewed artifact proves
entitlement, public-time semantics, correction completeness, target-horizon
consistency, storage/processing rights, and QC-transfer rights. No provider
request, credential use, target row, outcome access, research look, ETF work,
QC processing, broker action, paper operation, or live trading is authorized.

## 9. Out-of-lane findings ledger

Do not fix findings outside Target-Price Revisions from this branch. Append a
row with sufficient evidence for later owner routing. `None` is the current
measured state; it is not a claim that the rest of the repository is defect
free.

The owner's standing session rule, 2026-08-29, restates this boundary in a
second form: this session is dedicated to trading strategies, not the general
health of the trading application. An issue outside trading strategy is
documented here and deliberately not fixed.

| ID | Severity | External area / paths | Evidence and lane impact | Disposition / future route |
|---|---|---|---|---|
| `TPR-OOL-001` | P2 | Repository-wide Git plumbing: no `.gitattributes` exists at any level, and `core.autocrlf=true` is set in the system Git configuration | Git finds no NUL byte in the target-price blueprint, so it classifies the PDF as text and rewrites its 557 LF bytes to CRLF on checkout. The working file is 78,082 bytes and hashes to `6ee7ea5e...4330`, while the committed blob is 77,525 bytes and hashes to the pinned `9f00dd56...2633`. `pdftotext` reports a damaged xref table on the working copy. The other four PDFs contain NUL bytes early and check out byte-identically. Lane impact is `TPR-CR1-001`. | A `*.pdf binary` attribute is repository-wide plumbing rather than trading-strategy work, and `docs/Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md` section 2 requires a shared-file change to stop for one owner-coordinated common-baseline amendment. Documented, not fixed. Owner decision required. |
| `TPR-OOL-006` | P2 | Sibling lane frozen preregistrations, principally `codex/strategy-analyst-revisions-v2` | That lane still freezes its selection-family alpha at `0.05 / 3 = 0.0167` while this lane's owner-approved addendum A23 makes the shared family four members at `0.0125`. Lane impact is `TPR-CR2-002`: the four lanes would together spend `0.0625` against an intended `0.05`. | Requires one owner-coordinated common-baseline amendment across all four lanes. Another lane's frozen preregistration must not be edited from this branch. Documented, not fixed; **must be settled before any lane's first outcome study**. |
| `TPR-OOL-002` | P3 | `docs/Strategy Description/README.md` | The lane table and the surrounding prose describe a three-strategy program and omit Target-Price Revisions entirely, so a reader who starts at the directory README does not discover this lane, its branch, or its record. | That README is named in the parallel-workflow frozen-file list, so it needs the same owner-coordinated common-baseline amendment rather than a fourth competing edit. Documented, not fixed. |
| `TPR-OOL-001-R1` | P2 resolution | Owner-coordinated repository Git plumbing | The owner approved the common fix. Root `.gitattributes` now declares `*.pdf binary`; Git resolves the blueprint as binary with text/diff/merge unset. The PDF was rebuilt from the intact Git blob plus the two-page owner addendum and now reopens strictly as 28 pages at raw SHA-256 `55ce6703...ba14`. | Resolved under the explicit one-time owner coordination; this does not authorize later shared-file edits by inference. Raw-byte and resolved-attribute guards are target-owned. |
| `TPR-OOL-003` | P2 | Analyst Revisions V2 preregistration loader: `research/analyst_revisions_v2/preregistration.py:465,487` | Both persisted JSON paths use ordinary `json.loads`, which accepts duplicate object keys with last-key-wins behavior. A content-addressed authority artifact can therefore have ambiguous human/parser meaning. TPR's strict loader rejects duplicate keys, but this external accepted lane remains unchanged. | Documented only. Route to the Analyst Revisions V2 lane before any outcome authority; add duplicate-key mutations there. |
| `TPR-OOL-004` | P2 | Analyst Revisions V2 family contract: `research/analyst_revisions_v2/preregistration.py:56,931` and its draft/tests | The accepted draft/loader still names `three_lane_selection_correction` and requires value 3, while the owner has added TPR as the fourth shared family/attempt. The Analyst lane remains fail-closed and zero-access, so no current look is affected. | Documented only. Synchronize that lane's content-addressed artifact and tests to four before any Analyst outcome access; do not edit it from TPR. |
| `TPR-OOL-005` | P3 | Trading App Briefing smoke fixture and yfinance cache/provider path | The exact `ba01e98` complete-suite run timed out after 180 seconds in `test_ui_pages_smoke.py::test_page_renders_without_exception[Briefing]`; captured yfinance logs reported `OperationalError('unable to open database file')` for QQQ, SPY, NVDA, and AMD. The fixture patches only one recorded-bar seam, while Briefing still reaches direct benchmark and sample-holding yfinance paths. `c0ba616..ba01e98` changes none of the UI, fixture, provider, configuration, or dependency paths; the page imports no TPR module. The same exact test passed immediately in isolation in 14.42 seconds. | Confirmed pre-existing out-of-lane test-isolation/reliability gap exposed by host cache/load conditions. Documented, not fixed, under the owner's target-only rule; route to the Trading App test lane. Keep the exact full-suite result explicitly red. Focused TPR validation is unaffected and no provider authority is granted. |

## 10. Session / commit ledger

Append one row for every durable implementation, review, correction, handoff,
or push. Never rewrite or delete an earlier row. Record exact commits once
known.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Authority change | Next |
|---|---|---|---|---|---|---|---|---|
| 2026-08-29 | Codex planning | `086b782e43a5ff889e71ec8e26334bb791ccac74` -> documentation candidate | Documentation only | Created the dedicated branch/worktree, corrected the target-price research/QC plan, added separately gated shadow, paper, restricted-live, and bounded-unattended stages, and recorded lane governance; no code or data. | PDF generated with ReportLab; `pdfinfo` reports 26 letter-size pages and no encryption, JavaScript, forms, or suspect state; all 26 rendered pages visually inspected; extracted text contains every part and final gate; 67 active-document tests passed; the three Markdown staged paths pass `git diff --check`; the staged PDF blob is byte-identical to the visually reviewed file and pinned SHA-256; 0 outcome accesses; 0 looks. | Target-price revisions require a separate family, provider normalizer, timing/basis audit, four-family multiplicity decision, permanent look authority, and independent review. | None; all production, outcome, QC, broker, paper, and live authority remains zero. | Claude independently reviews the exact documentation snapshot; implementation waits for Action Plan scheduling. |
| 2026-08-29 | Codex documentation | `c1798013d911ef54dba82157326c826ac7763ec3` -> workflow-override candidate | Owner workflow direction | Recorded the explicit same-branch/same-worktree serialized loop, several-commits/one-push-per-role-round rule, target-only branch boundary, and document-but-do-not-fix rule for external findings. The override supersedes only the PDF's prior separate-review-branch wording. | 67 active-document tests passed; Markdown `git diff --check` clean; 0 provider/outcome/QC/broker accesses; 0 looks. | No out-of-lane finding established. | Workflow topology only; no implementation, source, outcome, QC, paper, live, deployment, or capital authority added. | Keep the cumulative Codex round local until its single end-of-round push is requested; Claude then reviews the exact pushed range on this branch/worktree. |
| 2026-08-29 | Claude review | `c1798013d911ef54dba82157326c826ac7763ec3` -> `70c4b9fea1ac119f86901e95b9108820aa80e028` reviewed; corrections on this same lane branch | Independent review of the documentation planning snapshot | Reviewed both published commits individually with complete diffs, read the governing blueprint end to end, and verified the record against it. Corrected the worktree path, the stale local-only/unmerged push state, the malformed submitted-source pin, and the missing Action Plan and Session Handoff coordination pointers. Added the lane's first three documentation guards. | Complete suite on the exact committed tree `b841360`: **5,724 passed, 2 skipped, 0 failed, 25 known dependency warnings in 858.06s (14m18s)**, which is the 5,721-test baseline plus exactly the three guards added here. Active-document suite 67 -> **70 passed**; five reverse mutations each turned exactly one new guard red with green restore; `compileall` exit 0; blueprint content digest re-verified as `9f00dd56...2633` over LF-normalized bytes. Repository-wide `git diff --check` is **red** on the blueprint alone, which is finding `TPR-CR1-001`, not a new regression. No provider, credential, licensed row, outcome, evidence-epoch, QuantConnect, broker, operator-database, scheduler, paper or live access; **0 research looks**. | Both commits accepted after correction. No P0/P1. `TPR-CR1-002`, `TPR-CR1-003`, `TPR-CR1-005` and `TPR-CR1-006` closed; `TPR-CR1-001` open on an owner decision; `TPR-CR1-004` closed in Markdown with two blueprint instances open. `TPR-OOL-001` and `TPR-OOL-002` documented and deliberately not fixed. Details in section 11. | None; all production, outcome, QC, broker, paper and live authority remains zero. | Codex counter-reviews every Claude commit in this round. TPR-0 remains unscheduled and additionally blocked on the two owner decisions. |
| 2026-08-29 | Claude validation / push | `b8413606ee70b4bae86db5f1a7cefe6a0523b360` -> `c0ba616a40f628519a071d0642fadf596982919a` | Review validation record | Recorded the complete-suite result obtained on exact correction tree `b841360` and pushed the cumulative three-commit Claude range ending at `c0ba616`. This appended row repairs the prior row's conflation of review and later validation; published Git history retains the original edit trail. | Claude reported **5,724 passed, 2 skipped, 0 failed, 25 warnings in 858.06s** on Windows with Python recorded only as 3.14 and pytest 9.1.1. Codex independently confirmed collection of 5,726 tests but did not rerun the 14-minute suite during counter-review. No provider or outcome access; **0 research looks**. | Exact pushed Claude range is `70c4b9f..c0ba616`. The environment claim lacks the Python patch version and executable. | None; all authority remains zero. | Codex counter-reviews all three Claude commits before TPR-0. |
| 2026-08-29 | Codex counter-review correction | `c0ba616a40f628519a071d0642fadf596982919a` -> `24283fa3b79b1a86cceb65fbd5d3d2af5fa20292` | Counter-review only; TPR-0 blocked | Restored `tests/test_active_document_consistency.py` exactly to the reviewed Codex state and moved narrowed target documentation guards into `tests/target_price_revisions/`. The worktree guard requires the registered target worktree in every active coordination pointer, so substituting the obsolete path fails while historical issue evidence remains documentable; the malformed-source guard is explicitly target-scoped and case-insensitive. | Shared plus target documentation suites: **70 passed in 1.11s** on `C:\git\customizedagent\trading_agent\.venv\Scripts\python.exe` (Python 3.12.13, pytest 9.1.1); three green baselines plus three reverse mutations passed; two target test files syntax-compiled without bytecode writes; staged `git diff --check` clean; **0 provider/outcome accesses and 0 looks**. | `0f05f3d` rejected as a correct standalone snapshot but its intent is accepted after this correction; `b841360` and `c0ba616` accepted after record qualification. Open owner/gate blockers: `TPR-CR1-001`, `TPR-CR1-004`, `TPR-CCR1-004`, and unresolved TPR-0 freeze decisions. | None. No implementation, source, outcome, QC, broker, paper, live, deployment, or capital authority added. | Keep this Codex round local and unpushed; obtain owner decisions, then implement and validate TPR-0 in the same round before its single push. |
| 2026-08-29 | Codex counter-review record | `24283fa3b79b1a86cceb65fbd5d3d2af5fa20292` -> local record candidate | Counter-review record; TPR-0 blocked | Added the exact three-commit Claude dispositions, repaired current status and range semantics, split Claude's validation/push into its own append-only ledger event, qualified the PDF-render and `git diff --check` overstatements, documented the TPR-0 dependency-order contradiction, and refined the worktree test to inspect exact active pointers rather than historical issue text. | Shared plus target documentation suites: **70 passed in 1.15s**; Markdown and target-test `git diff --check` clean; no provider, source, outcome, QC, broker, paper, or live access; **0 looks**. | Open owner/gate blockers are enumerated in section 12. No TPR-0 artifact was created. | None. | Preserve the one-push rule; wait for owner decisions, implement TPR-0 locally, then update this candidate to its exact committed/pushed range. |
| 2026-08-30 | Codex counter-review + implementation | `2708c06e394f927356aeffa3af781be1ce5d2090` -> local TPR-0A candidate | Owner-approved v2.1 amendment and bounded TPR-0A | Closed the prior review blockers under the approved TPR-0A/0B phase split; repaired and binary-pinned the 28-page sole-authority blueprint; implemented strict canonical artifacts, deterministic policy construction, exact zero-access declarations, Git/code-map review anchoring, fixed-boundary transitive import protection, and the complete frozen TPR-0A policy/algorithm parent. The checked-in candidate is unreviewed and non-executable. | PDF raw SHA-256 `55ce6703...ba14`, 28 pages, strict-open and visual QA complete. Focused TPR code/spec/document suite: **108 passed, 3 skipped** on Python 3.12.13 / pytest 9.1.1; skips are host symlink-privilege cases and the Windows junction regression passed. Provider accesses **0**; outcome accesses **0**; authorized/spent looks **0**. | No P0/P1/P2 remains after counter-audit. `TPR-CCR2-011` is the deferred P3 signed-review-identity strengthening item. | None. One `planned_unbound` look identity exists, but no look is authorized or spent; source/look registries remain zero-access and reviewed-spec registry remains empty. | Complete full-project validation, commit the exact candidate, append the final validation/push row, and make this round's single push for Claude review. |
| 2026-08-30 | Codex validation / handoff | `ba01e98f9d3c8746c70182818a27a2d49a9c0fe7` -> local record candidate | Exact TPR-0A implementation snapshot | Reverified the committed candidate/PDF hashes and attributes, deterministic regeneration, zero-access artifacts, import closure, compilation, diff hygiene, and credential-shape boundary. The implementation commit contains no TPR provider reader and no outcome, QC, broker, or deployment path. | Exact-tree target/shared suite: **176 passed, 3 skipped**; compilation and staged diff checks passed. Exact-tree full run: **5,829 passed, 5 skipped, 1 failed, 26 warnings**; the sole failure was out-of-lane `TPR-OOL-005`, which passed alone immediately afterward (**1 passed in 14.42s**). A prior full run before two trailing-blank-line-only cleanups was **5,830 passed, 5 skipped, 26 warnings in 962.18s**. Python 3.12.13; pytest 9.1.1. Provider accesses **0**; outcome accesses **0**; authorized/spent looks **0**. | No TPR P0/P1/P2. `TPR-CCR2-011` remains deferred P3; transient out-of-lane UI test item `TPR-OOL-005` documented and deliberately not fixed. | None. Candidate remains unreviewed; reviewed registry empty; source/look declarations zero-access; one planned-unbound identity but no authorized or spent look. | Commit this record-only handoff, make the round's one push, and hand the exact pushed range to Claude for same-branch independent review. |
| 2026-08-30 | Claude review | `c0ba616a40f628519a071d0642fadf596982919a` -> `6aae73bb381733c5239cb141e77cf1b7be6438d2` reviewed; corrections on this same lane branch | Independent review of the Codex counter-review and the TPR-0A candidate | Reviewed all four pushed commits individually. Accepted every counter-review finding against the prior Claude round, including two confirmed errors of my own. Verified rather than accepted: the storage remedy, that the v2.1 rebuild appended the addendum without altering any reviewed v2.0 line, the ARV2 schedule reuse, the zero-access registries, the artifact hashes, and the outcome-gate and reviewed-authority code paths. Restored the generalized malformed-digest invariant and closed the worktree guard's agreement and obsolete-name holes. | Independent complete run on the exact pushed tree `6aae73b`: **5,830 passed, 5 skipped, 0 failed, 25 warnings in 997.26s**, corroborating the recorded 5,829/5/1 and failing to reproduce `TPR-OOL-005`. Final complete run on the corrected tree `f7ab9e2`: **5,831 passed, 5 skipped, 0 failed, 25 warnings in 815.32s**, the baseline plus exactly the one restored guard with skips unchanged. `compileall` exit 0 including `research`; `git diff --check` clean. Focused target/shared suite 187 passed, 3 skipped. Three mutations each turned exactly one guard red with green restore, including direct proof that a new malformed pin passes the lane guard while failing the restored shared guard. No provider, credential, licensed row, outcome, evidence-epoch, QuantConnect, broker, operator-database, scheduler, paper or live access; **0 research looks**. | All four commits accepted after correction or accepted. No P0/P1. `TPR-CR2-001` and `TPR-CR2-003` closed; `TPR-CR2-002` open on an owner decision and mirrored as `TPR-OOL-006`. Owner confirmed the three section 13.1 approvals on 2026-08-30; bound in section 14.5. Details in section 14. | None; all source, outcome, look, QC, broker, paper and live authority remains zero. | Codex counter-reviews every Claude commit in this round. TPR-0B and TPR-1 remain blocked; `TPR-CR2-002` must be settled before any lane's first outcome study. |
| YYYY-MM-DD | Role | `<start>` -> `<end>` | TPR-N | Concise durable change | Exact tests, artifacts, evidence epoch, and look count | Open/resolved P0-P3 items and blockers | Exact authority added or `none` | Exact next bounded step |

## 11. Claude independent review - 2026-08-29 (documentation planning snapshot)

**Disposition: accepted after correction.** No P0 or P1 issue exists. The
planning content itself is sound: the separate-family boundary, stock-first
null closure, four clocks, cutoff-safe corrections, binary validity versus
measured reliability, the three coverage concepts, the hard 99% mapping gate,
raw ETF exposure without covered-weight renormalization, immutable QC packets,
and the four separately authorized promotion stages are internally consistent
and materially stronger than the submitted proposal they replace. Every defect
below is in the lane's provenance, governance and status records rather than
in its research design.

### 11.1 Exact reviewed snapshot

| Item | Value |
|---|---|
| Branch | `codex/strategy-target-price-revisions` |
| Reviewed range | `c1798013d911ef54dba82157326c826ac7763ec3..70c4b9fea1ac119f86901e95b9108820aa80e028` |
| Base | `086b782e43a5ff889e71ec8e26334bb791ccac74` |
| Remote head at review | `70c4b9fea1ac119f86901e95b9108820aa80e028`, matching local |
| Published state | merged to `origin/main` by PR #324 merge `1a5264e6b1de3caf5477477d1312a762b2d42419` |
| Corrections | committed on this same lane branch, per the owner's same-branch topology |
| Environment | Windows 11, Python 3.14, pytest 9.1.1 |
| Complete suite | 5,724 passed, 2 skipped, 0 failed, 25 warnings in 858.06s |

The owner's same-branch override was followed instead of
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` section 1, which would
otherwise require a separate review branch. Review independence here rests on
role separation, the exact published commit range, and explicit dispositions.

### 11.2 Commit dispositions

Every commit in the range was read individually with its complete diff. No
combined diff was substituted.

| Commit | Disposition | Basis |
|---|---|---|
| `c1798013d911ef54dba82157326c826ac7763ec3` | **accepted after correction** | Introduced the blueprint, the lane record, and the Action Plan and Session Handoff references. Carries `TPR-CR1-001`, `TPR-CR1-002`, `TPR-CR1-004`, `TPR-CR1-005` and `TPR-CR1-006`. The research content is accepted as written. |
| `70c4b9fea1ac119f86901e95b9108820aa80e028` | **accepted after correction** | Recorded the owner's same-branch workflow override and correctly scoped it to supersede only the blueprint's separate-review-branch wording on physical pages 3, 21, 23 and 26. Carries `TPR-CR1-003` and repeats `TPR-CR1-005`. |

### 11.3 P0-P3 issue ledger

Resolved items are retained. There is no P0 or P1 finding.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `TPR-CR1-001` | P2 | **Open - owner decision** | `c179801` | `docs/Strategy Description/TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf` | The governing blueprint is stored as a Git *text* blob, so a Windows checkout rewrites its line endings. Three consequences: the working PDF is damaged and reports a broken xref table, the record's pinned SHA-256 cannot be reproduced by hashing the checked-out file, and `git diff --check` is now permanently red for the whole repository, which conflicts with the `CLAUDE.md` section 10 validation this project runs before every handoff. | Committed blob 77,525 bytes hashing `9f00dd56...2633`; working file 78,082 bytes hashing `6ee7ea5e...4330`; the 557-byte delta equals the 557 lone LF bytes in the blob; the file contains no NUL byte at any offset, while the analyst blueprint's first NUL is at offset 2,739; `git diff --check 086b782..HEAD` reports trailing-whitespace errors on this file alone. The section 10 ledger row claims only that "the three Markdown staged paths pass `git diff --check`", which is literally true and silently excludes the one path that fails. | A governing specification whose pinned digest cannot be verified from a checkout is not a content-addressed artifact, and a permanently red `git diff --check` trains every future round to ignore a mandated check. | Not fixed here. Both remedies fall outside this session's trading-strategy scope or the frozen-file rule: a `*.pdf binary` attribute is repository-wide plumbing (`TPR-OOL-001`), and regenerating the blueprint would change the identity of a governing artifact during a review round. Partially mitigated: the new guard pins the blueprint by LF-normalized content digest, which is stable on every platform and keeps passing after either remedy. | `test_target_price_lane_blueprint_is_pinned_to_its_record` passes; replacing the normalization with the raw bytes turns it red on this host (`1 failed`), independently reproducing the corruption. |
| `TPR-CR1-002` | P2 | Closed | `c179801` | `tests/` (no file) | The lane shipped with **zero** test coverage. All three sibling lanes are bound record-to-blueprint by digest in `test_three_strategy_parallel_baseline_is_exact_and_fail_closed`; the fourth lane was never added to it or to any other guard, so nothing checked its pin, its provenance values, or its coordination references. This is the root cause that let `TPR-CR1-001`, `TPR-CR1-004` and `TPR-CR1-006` reach `main` with a green suite. | `grep -rn` for `target.price`, `TARGET_PRICE` and the lane branch across `tests/` matched only stale `__pycache__` binaries and no source file. The 67-test active-document suite passed on the uncorrected tree. | The repository's documentation-governance guards are the only mechanism that makes a lane record's provenance claims checkable; a lane exempt from them is unverified by construction, and the exemption was silent rather than declared. | Added three guards to `tests/test_active_document_consistency.py`: `test_target_price_lane_blueprint_is_pinned_to_its_record`, `test_target_price_lane_documents_agree_on_one_worktree`, and `test_no_active_document_pins_a_malformed_sha256`. | Suite grows 67 to 70 passed. Five mutations each turn exactly one new guard red and restore returns green: digest pin altered, normalization removed, record digest removed, worktree drift reintroduced, malformed pin reintroduced. |
| `TPR-CR1-003` | P2 | Closed | `70c4b9f` | `docs/SESSION_HANDOFF.md:16-17`, section 8 of this record | The canonical cross-computer handoff stated the branch "was local-only" with "no push or merge was performed", and section 8 said the next step was to push when publication is requested. The branch was in fact published and merged into `origin/main` seven minutes after the second commit. A reader resuming on another machine would conclude the work is unfetchable. The merge also preceded the independent review these same documents name as mandatory. | `git merge-base --is-ancestor 70c4b9f origin/main` returns 0; PR #324 merge `1a5264e` is dated 2026-08-29 16:53:03 -0700 against commit timestamps 16:32:48 and 16:46:37. | This is the fourth recorded instance of the class documented in `test_no_document_calls_a_merged_commit_unreachable` (CCR-005, CCX-004): a push or merge claim written inside the commit being pushed is false by construction the moment it lands, and the handoff is the one document another computer relies on. | The handoff now records the published head, the PR #324 merge commit, that `git fetch` retrieves it, and that the merge preceded this review. Section 8 and the Action Plan row now carry the same state. | The active-document suite passes on the corrected tree, including the existing reachability guards. |
| `TPR-CR1-004` | P3 | Closed in Markdown; blueprint instances **open** | `c179801` | This record, `docs/SESSION_HANDOFF.md`, blueprint pages 1 and 25 | The pinned SHA-256 of the owner's submitted source proposal is 63 hexadecimal characters and therefore cannot be a SHA-256 at all. The submitted PDF is not stored in the repository, so the digest cannot be recomputed and the provenance of the document this lane was derived from is unestablished. | Length measured at all four sites. A repository-wide scan of every non-archived Markdown document for hex runs of 55 to 80 characters found exactly these two Markdown instances and no other malformed pin, so the defect does not generalize beyond this lane. | An unverifiable pin presented as a digest reads as provenance evidence while providing none. | Both Markdown sites now state plainly that the value is malformed and unverifiable, and show it truncated so it can no longer be mistaken for a usable pin. The two instances inside the blueprint cannot be corrected without regenerating that PDF, which is deferred with `TPR-CR1-001`. | `test_no_active_document_pins_a_malformed_sha256` was red against the uncorrected documents and is green after correction; reintroducing the full 63-character value turns it red again. |
| `TPR-CR1-005` | P3 | Closed | `c179801`, `70c4b9f` | This record, `docs/ACTION_PLAN_2026-08-20.md:34`, `docs/SESSION_HANDOFF.md:14` | All three documents pinned a worktree whose directory name ended in `TargetPriceRevision`. No such directory exists. The registered worktree is `C:\git\customizedagent\trading_agent_target_price`. Because the workflow binds the lane to one named branch *and* one dedicated worktree, the resume instructions pointed at nothing. | `git worktree list` shows five registered worktrees; the target lane's is `C:/git/customizedagent/trading_agent_target_price`. | The lane record replaces the root handoff for lane resumption, so a wrong path defeats the cross-computer purpose the topology exists to serve. | All three documents now name the real directory. | `test_target_price_lane_documents_agree_on_one_worktree` passes; reintroducing the old name in the handoff alone turns it red, so future drift between the three documents fails rather than passing silently. |
| `TPR-CR1-006` | P3 | Closed | `c179801` | This record, header block | The record carried neither `docs/ACTION_PLAN_2026-08-20.md` nor `docs/SESSION_HANDOFF.md` as an explicit pointer, although the sibling-lane guard requires exactly those two references in every other lane record. A reader holding only this record could not locate the sequencing index or the canonical handoff. | The new guard's assertion failed on the uncorrected record before any other change was made. | The lane record is the lane's sole status and handoff ledger; without the two coordination pointers it is not self-sufficient for resumption. | The header block now names both documents and states that each receives only concise coordination and status references. | Covered by `test_target_price_lane_blueprint_is_pinned_to_its_record`; removing either reference turns it red. |

### 11.4 What was verified rather than accepted

- The blueprint's 26-page count was confirmed independently from its own
  `/Count 26` page-tree object and its rendered page-26 footer, not from the
  ledger's `pdfinfo` claim. Its metadata records
  `/Producer (ReportLab PDF Library)` and
  `/Author (OpenAI Codex, prepared for Shelton Chen)`, so this blueprint is an
  agent-authored artifact rather than an owner-supplied immutable input. The
  `docs/Strategy Description/README.md` rule that "the PDF governs" was written
  for owner-supplied PDFs and should not be read as protecting this one from
  correction.
- The complete blueprint text was read end to end and cross-checked against
  this record. The record's summary is faithful; no gate is softened, renamed,
  or dropped between the two documents.
- The claimed 67-passing active-document suite was reproduced exactly.
- The base commit, remote head, ancestry, and merge state were resolved from
  Git rather than from the records.
- The record's statement that the override supersedes only the
  separate-review-branch wording was checked against the blueprint's actual
  pages 3, 21, 23 and 26 (governance correction, section 36, section 40, and
  correction `C18`). It is accurate, and no research or safety gate is
  weakened by the override.

### 11.5 Scope not exhaustively audited

- The blueprint's 26 rendered pages were not visually inspected; the complete
  text layer was read instead, and the working copy cannot currently be
  rendered on this host because of `TPR-CR1-001`.
- The economic literature cited in appendix A4 was not re-verified.
- No provider documentation, entitlement, or endpoint behavior was checked.
  The source-capability statements in the blueprint's section 7 remain
  unmeasured assumptions, which that section itself declares.

### 11.6 Authority state after this review

Unchanged and zero. This review accessed no provider, credential, licensed
row, outcome, evidence epoch, QuantConnect project, broker, operator database,
scheduler, paper surface, or live surface, and spent **0 research looks**. No
live-assistant behavior can change: the only executable change is three
additional documentation guards inside an existing test module.

## 12. Codex counter-review - 2026-08-29

**Disposition: Claude's cumulative correction intent is accepted after Codex
correction, but TPR-0 is blocked and this Codex round is not pushed.** There is
no P0 or P1 finding. Codex reviewed every commit in the exact Claude range
`70c4b9fea1ac119f86901e95b9108820aa80e028..c0ba616a40f628519a071d0642fadf596982919a`
individually and inspected the cumulative state. The local correction commit is
`24283fa3b79b1a86cceb65fbd5d3d2af5fa20292`.

### 12.1 Commit dispositions

| Commit | Counter-review disposition | Basis |
|---|---|---|
| `0f05f3ded6b59bfcd301ac6ee70363d5604d5057` | **Rejected as a correct standalone snapshot; intent accepted after `24283fa`** | At this exact object, two of its three new tests fail because the document corrections arrive only in the later commit. The sole passing worktree test accepts the original dangerous state because all documents agree on the same nonexistent path. The commit also places target-lane tests in the shared active-document module and scans every active Markdown file for a target-specific provenance defect. Codex restored the shared module and added narrower target-owned guards that require the real worktree and reject the obsolete one. |
| `b8413606ee70b4bae86db5f1a7cefe6a0523b360` | **Accepted after correction and qualification** | The documentation corrections are useful and authority-neutral. The resulting record nevertheless retains a stale header, an excluding Git range, an overstatement that the working PDF cannot render, an overstatement that `git diff --check` is permanently red, an inconsistent partly-open provenance status, and no exact durable ledger for the later validation/push. This section and the current-state sections correct or explicitly qualify those claims without changing Claude's historical report. |
| `c0ba616a40f628519a071d0642fadf596982919a` | **Accepted after correction and qualification** | The complete-suite evidence is credible as Claude-run evidence and its 5,726-test collection count is structurally consistent with 5,724 passed plus 2 skipped. Codex did not rerun the 14-minute suite. This commit rewrote the existing review-ledger row instead of appending a separate validation/push row; section 10 now appends the missing event and preserves the published Git audit trail. |

### 12.2 Counter-review issue ledger

| ID | Priority | Status | Location | Finding and correction / required decision |
|---|---|---|---|---|
| `TPR-CCR1-001` | P2 | **Closed by the local correction series** | `tests/test_active_document_consistency.py`; `tests/target_price_revisions/` | Claude's target-specific guards were added to a shared test surface despite the lane's target-owned-file rule. The malformed-digest scan also ranged over unrelated active Markdown, and the agreement-only worktree guard passed when all documents named the same nonexistent directory. Codex restored the shared module exactly to `70c4b9f`, moved the guards to the target package, scoped the known provenance defect to target documents, made the match case-insensitive, and required the exact registered active worktree pointers while permitting the record to retain historical issue evidence. |
| `TPR-CCR1-002` | P2 | **Closed in the current record** | Header, sections 8, 10, 11.1 and 11.5 | The record said the snapshot was not independently reviewed, used `c179801..70c4b9f` even though that Git range excludes `c179801`, omitted the exact three-commit Claude range and push head, and conflated review with later validation in one ledger row. Current-state text now names the exact commit set, exact Git ranges, local correction commit, and a separate validation/push ledger event. Section 11 remains Claude's historical report; this section is the authoritative counter-review qualification. |
| `TPR-CCR1-003` | P3 | **Closed by qualification; artifact defect remains open under `TPR-CR1-001`** | Blueprint and sections 11.3, 11.5 | Poppler can render the malformed working PDF: all 26 pages rendered and were visually inspected, although xref/font warnings remain. A clean-worktree `git diff --check` and `git diff --check 70c4b9f..c0ba616` both pass; only historical ranges that include the original PDF addition, such as `086b782..c0ba616`, fail. The checked-out bytes and pinned blob digest still differ, so the core storage defect remains real and owner-routed. |
| `TPR-CCR1-004` | P2 | **Open - owner decision; blocks TPR-0** | Blueprint physical pages 5, 6 and 9; milestone ladder | TPR-0 must freeze a numeric practical-effect threshold from capacity/cost/power, an independent sample floor from observed event frequency/overlap, and `CLIP_TPR0` from a zero-outcome structural distribution and source-error audit. The first structural source sample is assigned to TPR-1, while TPR-2 supplies the price, ADV and cost prerequisites. Exact numeric TPR-0 completion is therefore circular. The owner must choose: freeze algorithms/formulas at TPR-0 and bind numeric outputs after reviewed TPR-1/2 structural evidence but before outcomes; authorize a bounded zero-outcome structural pilot inside TPR-0 and amend the ladder; or supply defensible numeric constants now. Codex will not guess. |
| `TPR-CCR1-005` | P2 | **Open - owner decisions; blocks TPR-0** | Blueprint `FREEZE_AT_TPR0` items and section 2 of this record | The provider/endpoint/schema and rights state, exact batch cutoff, source-error policy, universe/minimum-group/fallback rules, split/FX/ADR/horizon sources, catalyst-unknown policy, estimator/partitions, exact cost model, shared-fourth-family treatment, permanent-look authority, and exact validation/final-holdout dates remain unbound. Starting executable preregistration without them would falsely claim TPR-0's definition of done. |
| `TPR-CCR1-006` | P3 | **Open with `TPR-CR1-004` / `TPR-CR1-005`; no artifact rewrite authorized** | Blueprint physical page 25 | The governing PDF still names nonexistent worktree `trading_agent_TargetPriceRevision` and still contains the malformed 63-character source pin on physical pages 1 and 25. Correcting the Markdown does not close the artifact instances. Regenerating the governing PDF changes its identity and must wait for the owner's storage/provenance decision. |

### 12.3 Independent verification and scope

- `tests/test_active_document_consistency.py` plus
  `tests/target_price_revisions/test_document_consistency.py`: **70 passed in
  1.15 seconds** with Python 3.12.13 and pytest 9.1.1 from the repository's
  existing virtual environment.
- Three isolated green baselines and three reverse mutations passed: changed
  blueprint bytes, the obsolete worktree, and a case-changed full malformed
  source pin each tripped its intended target guard.
- The two target test modules syntax-compiled without bytecode writes;
  `git diff --check` was clean for the counter-review correction.
- Codex read the governing blueprint end to end and compared TPR-0's definition
  of done with the milestone ordering. No provider documentation, credential,
  licensed row, source row, market outcome, evidence epoch, QuantConnect job,
  broker, operator database, scheduler, paper surface, or live surface was
  accessed. **Outcome accesses: 0. Research looks: 0.**

The local round stops at the owner gate. It does not branch, does not push, and
does not implement a partial preregistration that pretends unresolved choices
are frozen.

## 13. Codex counter-review completion and TPR-0A implementation - 2026-08-30

**Disposition: the prior Claude documentation range is accepted after the
counter-review corrections at `24283fa` and `2708c06`; the owner-decision
blockers are resolved for the bounded TPR-0A phase; and the new TPR-0A tree is
an implementation candidate pending Claude's next independent review.** No P0
or P1 finding exists. This is not acceptance of the candidate and grants no
source, outcome, look, QC, broker, paper, live, deployment, or capital
authority.

### 13.1 Owner-decision and historical-blocker dispositions

| Prior item | Current disposition | Exact basis |
|---|---|---|
| `TPR-CR1-001` / `TPR-OOL-001` | **Closed under the one-time owner-coordinated common fix** | Root `*.pdf binary`, a rebuilt strict 28-page v2.1 PDF, raw SHA-256 `55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`, resolved Git text/diff/merge attributes unset, and raw-byte/document guards repair cross-platform checkout identity. |
| `TPR-CR1-004` / `TPR-CCR1-006` | **Closed for active authority; retained as historical evidence** | Addendum A19/A26 makes the reviewed v2.0 pages plus owner-approved v2.1 addendum the sole normative specification, explicitly leaves the combined artifact pending Claude review, and makes the unavailable malformed 63-character proposal value unable to satisfy or block a gate. Addendum A20 records the real worktree and same-branch loop. |
| `TPR-CCR1-004` | **Closed by the owner-approved phase split** | TPR-0A freezes policy, formulas, estimator mechanics, required child inventory, and binding procedures without inventing empirical results. TPR-0B may bind the exact clip, cost/capacity, power/sample, universe/group, reliability, and history values only from reviewed zero-outcome TPR-1/TPR-2 manifests before TPR-3 or any outcome access. |
| `TPR-CCR1-005` | **Closed as a TPR-0A-start blocker; downstream gates remain explicitly pending** | A22 fixes Massive/Benzinga `GET /benzinga/v1/ratings` v1 as the source candidate while every right/access flag stays false. A23 fixes the four-family dates/alpha/look identity. A24/A25 fix the formula and binding boundaries. The exact 48-item pending inventory prevents missing TPR-0B, source-rights, identity/basis/cost, look-identity, or external-authority prerequisites from being misreported as complete. |

### 13.2 TPR-0A implementation and counter-review issue ledger

| ID | Priority | Status | Finding and correction |
|---|---|---|---|
| `TPR-CCR2-001` | P2 | **Closed** | Simultaneous industry and sector one-hot controls with an intercept were rank-deficient, the rating-no-event state contradicted generic missing-control refusal, and an eligible-open gap control had no frozen endpoint. The candidate now uses exactly one cutoff-valid hierarchical industry-or-sector group, an explicit `NO_ACCEPTED_RATING_EVENT` state only after complete inventory proof, no gap control, exact per-session robust scaling, deterministic column order, and exact-rational fraction-free Gaussian elimination that refuses an exact singular design without tolerance, regularization, or pseudoinverse. |
| `TPR-CCR2-002` | P2 | **Closed** | The first power draft made the practical-effect floor depend circularly on the realized eligible sample. Planning event frequency, calendar count, design effect, effective count, unconditional 20-session variance, and MDE are now structural child bindings computed before target outcomes; the actual prospective independent-date count is a separate sufficiency comparison. Alpha remains two-sided `0.0125`, power `0.80`, and the economic gate remains the larger of twice measured P95 round-trip cost and the planning MDE. |
| `TPR-CCR2-003` | P2 | **Closed** | PASS/NULL was underdetermined. The candidate now pins the null/alternative, sign, average-tie quintile membership, equal leg weights, 10,000-draw null-centered four-week circular moving-block bootstrap, two-way date/security cluster cross-check, child-bound chronological fold rule, economic gate, edge cases, and disposition precedence. Every valid non-pass is `VALID_NULL` and closes the family. |
| `TPR-CCR2-004` | P2 | **Closed** | The original pending list and review anchor did not cover every empirical field or prove that the producing commit contained the same candidate policy. The loader now derives 39 empirical pending names exactly from 39 null required child keys; records 48 total prerequisites; validates every registry entry before duplicate detection; binds candidate path, ID, semantic hash, artifact hash, producing commit, and the reviewed policy-code map including `research/__init__.py`; requires a strict descendant independent-review commit; and permits only the reviewed-status/identity transition over the same policy bytes. |
| `TPR-CCR2-005` | P2 | **Closed** | Source capture/schema, secret-bearing metadata, institution identity, pre-event price, and raw-versus-adjusted target lineage were incomplete. The zero-access source contract now freezes all-history pagination through a reviewed high-water mark, credential-redacted raw page/request/response hashes and inventory, strict Decimal and optional/null/action handling, secret scanning, unknown-field refusal, a non-authoritative provider history claim, and required source-history/schema and institution-master child audits. Basis rules require the immediately preceding completed official close and one unmixed cutoff-valid raw or adjusted target pair under separately reviewed basis and vendor-adjustment/restatement audits. No request occurred. |
| `TPR-CCR2-006` | P2 | **Closed after correction** | An audit draft introduced convenient but unapproved research constants (`$5`, q20 ADV, `.99`/`.95` coverage, `1.25` stability, `1%` participation, fixed observation counts, reliability quantiles, and KS `.10`). They were removed. Exact resolution, coverage, stability, screen, cost, reliability, fold, and power rules remain null TPR-0B child bindings under A24 rather than being falsely attributed to owner approval. Publicly documented endpoint maximum `50000` remains retrieval plumbing only; `2011-12-08` remains an audit claim, never accepted coverage. |
| `TPR-CCR2-007` | P2 | **Closed after correction** | Static import checks could be bypassed through aliased import/evaluation primitives and unreviewed parent-package code. The fixed-boundary transitive guard now rejects forbidden local/provider/outcome/QC/execution imports, dynamic aliases, dangerous/nonliteral reflection, namespace/eval/exec/compile indirection, source substitution, and symlinked or junctioned closure paths while allowing the narrow literal `_authority` lookup required by the loader. `research/__init__.py` is part of the reviewed code map. The guard remains a dependency guard, not an operating-system I/O sandbox. |
| `TPR-CCR2-008` | P3 | **Closed** | Canonical review instants and decimal values accepted multiple equivalent spellings; unrelated malformed registry entries could raise raw type errors; and redirected authority paths were checked too late. Instants now require exact `YYYY-MM-DDTHH:MM:SSZ`, decimal text uses one finite plain spelling, every registry entry is typed before matching/duplicate logic, and original spec/registry/authority paths and ancestors are checked for symlinks or junctions before resolution. |
| `TPR-CCR2-009` | P3 | **Closed** | Decay expiry was mislabeled as raw event state `VALID_ZERO`. Age above 80 now means zero signal weight while preserving the event's original disposition. |
| `TPR-CCR2-010` | P2 | **Closed before handoff** | A one-off regeneration path accidentally serialized frozen mappings as arrays of key/value pairs. Focused validation caught the malformed semantic shape. Candidate construction now lives beside the frozen pins, materializes mappings as JSON objects, derives identity from those exact bytes, and is regression-pinned to reproduce the checked-in artifact byte for byte. |
| `TPR-CCR2-011` | P3 | **Open, non-authorizing** | Git ancestry plus the `reviewed_by` field can prove the reviewed lineage and exact bytes but not cryptographic control of reviewer identity. The current artifact is unreviewed and zero-access, so this cannot enable anything. Before any future positive authority relies on reviewer identity, require a separately controlled signed review receipt or trusted commit-signature policy. |

### 13.3 Exact candidate and remaining boundary

The canonical candidate is
`research/target_price_revisions/specs/tpr_round0a.candidate.json`:

- spec ID `tpr-round0a-candidate-f595992a3f5b8396`;
- semantic hash
  `f595992a3f5b8396e5f26ba5a3b0a3f32649eec3fd581071b349a5e12203af86`;
- raw artifact SHA-256
  `99aae28d5b055aa24b84ce153467dfdbe7ee65f8ee2cef2a870efe1e68b2ea49`;
- 24 frozen cells, one `planned_unbound` look, 39 null empirical child
  bindings, and 48 total pending prerequisites; and
- empty reviewed-spec, research-source, and permanent-look registries.

The planned look is identity-only and unbound: no look is authorized or spent.
The stable implementation snapshot is
`ba01e98f9d3c8746c70182818a27a2d49a9c0fe7`; the successor is record-only
handoff evidence and changes no algorithm, artifact, or authority.

The exact next role action after the one Codex push is Claude's independent
commit-by-commit and cumulative review of the pushed range on this branch and
worktree. TPR-1 remains blocked on a separately reviewed source-rights
artifact. TPR-0B remains blocked on reviewed TPR-1/TPR-2 structural manifests.
TPR-3 and every outcome/lookup path remain blocked on the reviewed parent and
child identities plus external source and permanent-look authority. Provider
accesses: **0**. Outcome accesses: **0**. Research looks: **0**.

## 14. Claude independent review - 2026-08-30 (counter-review and TPR-0A)

**Disposition: all four commits accepted after correction.** No P0 or P1 issue
exists. The TPR-0A authority path is the strongest part of this round and was
probed rather than accepted: it fails closed, authenticates its own negative
declarations, and closes the verify-then-mutate window. Two guard regressions
introduced by the counter-review are corrected here, and one cross-lane
multiplicity inconsistency is escalated to the owner because its remedy is in
the three sibling lanes' frozen files.

### 14.1 Exact reviewed snapshot

| Item | Value |
|---|---|
| Reviewed range | `c0ba616..6aae73b` (four commits; `c0ba616` was reviewed in section 11 and is correctly excluded) |
| Review head | `6aae73bb381733c5239cb141e77cf1b7be6438d2` |
| Remote head at review | identical; ancestry from `c0ba616` verified, no history rewrite |
| Implementation snapshot | `ba01e98f9d3c8746c70182818a27a2d49a9c0fe7` |
| Corrections | committed on this same lane branch |
| Environment | Windows 11, Python 3.14, pytest 9.1.1 |
| Baseline on pushed tree | 5,830 passed, 5 skipped, 0 failed, 25 warnings in 997.26s |
| Final on corrected tree `f7ab9e2` | 5,831 passed, 5 skipped, 0 failed, 25 warnings in 815.32s |

Section 11.1 named the range `c179801..70c4b9f`, which in Git excludes
`c179801` even though that commit was reviewed. Codex was right; the notation
above is correct and the historical row stands as written.

### 14.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `24283fa3b79b1a86cceb65fbd5d3d2af5fa20292` | **accepted after correction** | Relocating the two lane-specific guards into a target-owned package is correct under the blueprint's target-owned-namespace rule. Narrowing the repository-wide malformed-digest invariant to a lane literal was not; see `TPR-CR2-001`. |
| `2708c06e394f927356aeffa3af781be1ce5d2090` | **accepted** | Records the counter-review blockers honestly. `TPR-CCR1-004`, the circularity in TPR-0's own definition of done, is a genuine defect in the governing blueprint and refusing to invent constants was the correct response. No issue found. |
| `ba01e98f9d3c8746c70182818a27a2d49a9c0fe7` | **accepted after correction** | The TPR-0A tree, the storage remedy, the v2.1 addendum and the shared-family amendment. Carries `TPR-CR2-002` and `TPR-CR2-003`. |
| `6aae73bb381733c5239cb141e77cf1b7be6438d2` | **accepted** | Record-only validation handoff. Its counts are corroborated below. No issue found. |

### 14.3 Codex findings against the prior Claude round: all accepted

Every counter-review finding in section 12 is accepted, including the two that
were straightforward errors of mine.

| Codex finding | Assessment |
|---|---|
| `c179801..70c4b9f` excludes its own first commit | **Confirmed error.** Corrected in 14.1. |
| "the working copy cannot currently be rendered" overstates the defect | **Confirmed error.** Poppler reconstructs the xref and renders all 26 pages; the complete text layer had already been read that way in the same review, so my own evidence contradicted the claim. |
| "`git diff --check` is permanently red for the whole repository" overstates | **Confirmed error.** A clean-worktree check and `70c4b9f..c0ba616` both pass; only historical ranges spanning the blueprint's addition fail. |
| `0f05f3d` is red as a standalone object | **Confirmed.** Splitting guards before document corrections satisfied the separate-commit rule at the cost of per-commit greenness. Documents first, then guards, would have satisfied both. |
| The agreement-only worktree guard passed on the original dangerous state | **Confirmed**, and stated in the original report. Codex's exact-pointer replacement fixes that direction; `TPR-CR2-003` restores the direction it lost. |
| Lane guards belonged in a target-owned module | **Accepted** for the two lane-specific guards. Disputed for the repository-wide invariant; see `TPR-CR2-001`. |

### 14.4 P0-P3 issue ledger

Resolved items are retained. There is no P0 or P1 finding.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `TPR-CR2-001` | P2 | Closed | `24283fa` | `tests/test_active_document_consistency.py`, `tests/target_price_revisions/test_document_consistency.py` | The malformed-digest guard was removed from the shared module and replaced by a lane check that only asserts one known 63-character literal is absent from two named files. The generalized invariant -- no active document may pin a hex run long enough to be claiming a SHA-256 yet not 64 characters -- was left unimplemented anywhere, so a *new* malformed pin in any active record now passes. The removed invariant was not lane-specific; it had already caught a live defect, and `CLAUDE.md` section 9 requires the generalized instance rather than the single instance. | A repository-wide grep of `tests/` for the length predicate returned no source file. Mutation `M1` below reproduces the gap directly. | A provenance pin that cannot be a digest reads as evidence while providing none; scoping the check to one known string means it can only ever re-detect a defect that is already fixed. | Restored the generalized guard in the shared module, with a docstring stating why it is repository-wide and how it relates to the lane-scoped successor, which is retained. | `M1`: inserting a new 63-character pin into the Action Plan turns the restored shared guard **red** while the lane module stays green at 5 passed -- the coverage gap demonstrated exactly. Restore returns both green. |
| `TPR-CR2-002` | P2 | **Open - owner decision** | `ba01e98` | Addendum A23, `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`, sibling lane preregistrations | The shared selection family was amended to four members and Target-Price Revisions took alpha `0.0125` (`0.05 / 4`), but the Analyst Revisions V2 preregistration still freezes its family alpha at `0.05 / 3 = 0.0167`, and no document records that the three existing lanes must be re-frozen. If each lane tests at its own currently frozen alpha the family-wise budget spent is `0.0167 x 3 + 0.0125 = 0.0625`, above the intended `0.05`. | The ARV2 lane states **`0.05 / 3 = 0.0167`** for its family alpha. The target lane states `0.0125` in its record and twice in `preregistration.py`. A search of the amended direction document and the lane record for any re-freeze or propagation obligation returns nothing. | Multiplicity is the control that makes a four-family selection claim honest. A half-applied amendment that lowers only the new family's alpha understates the true family-wise error, and it is far cheaper to reconcile now than after a look is spent. | Not fixed. The remedy is in the three sibling lanes' frozen preregistrations, which both the lane boundary and the owner's trading-strategy scope rule place outside this branch. Escalated for one owner-coordinated common-baseline amendment. | Not applicable; no test is added for another lane's frozen contract. Nothing is executable and **0 looks are spent in any lane**, so no result is affected today. |
| `TPR-CR2-003` | P3 | Closed | `ba01e98` | `tests/target_price_revisions/test_document_consistency.py` | `24283fa` added an obsolete-worktree rejection and cited it in section 12.2 as the correction; `ba01e98` then replaced the body with exact per-document pointer strings and left `OBSOLETE_WORKTREE` defined but unreferenced. The guard named `..._agree_on_one_worktree` therefore asserted neither agreement nor rejection: a third spelling introduced anywhere passed, and the obsolete name could return to a pure coordination document. | `OBSOLETE_WORKTREE` is defined at line 18 and referenced nowhere else. Mutations `M2` and `M3` below both passed against the uncorrected guard's intent. | This is the exact hole that let one nonexistent directory sit unnoticed in three documents, and a dead constant advertises a check that is not running. | Extended the existing guard: the two pure coordination documents may name no other worktree at all, the record may carry the obsolete name only as historical finding evidence, and the union of active names across all three must be exactly one. | `M2`: a third spelling in the handoff turns exactly one assertion red (1 failed, 4 passed). `M3`: the obsolete name in the Action Plan turns exactly one assertion red (1 failed, 4 passed). Restore returns 5 passed. |
| `TPR-CR2-004` | P3 | Closed | `ba01e98` | `docs/ACTION_PLAN_2026-08-20.md` TPR row | The rewritten row said the TPR-0A candidate "awaits the exact end-of-round push and Claude review". It was pushed at `6aae73b` and reviewed here, so the sentence was false by the time anyone could read it on the branch. | `git merge-base --is-ancestor ba01e98 origin/codex/strategy-target-price-revisions` returns 0. | This is the fifth recorded instance of the push-state class (CCR-005, CCX-004, `TPR-CR1-003`, and the prior Action Plan row). The existing repository guard only matches commit hashes asserted unreachable, so an "awaits push" phrasing with no hash attached passes it. | The row now records the pushed head, the review disposition, the next role action, and the open multiplicity gate. | The active-document and lane suites pass on the corrected tree. A durable phrase-level guard for this shape is deliberately not added here: it belongs with the existing repository-wide reachability guard family, which is shared-surface work outside this lane's trading-strategy scope. |

### 14.5 Owner authorization, bound to exact artifacts

Section 13.1 recorded three owner approvals whose only evidence was the
implementing agent's own record. The blueprint's section 34 requires that
approval bind exact artifacts and states that silence is not authorization, so
the claim was put to the owner directly rather than accepted.

**The owner confirmed on 2026-08-30 that all three were approved.** They bind:

1. the repository-root `*.pdf binary` attribute and the resulting resolved
   `text`/`diff`/`merge` unset state for the blueprint;
2. blueprint version 2.1 as the reviewed v2.0 pages plus the appended Owner
   Decision Addendum, raw SHA-256
   `55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14`; and
3. the A21 TPR-0A / TPR-0B phase split, including that TPR-0B may bind
   empirical values only from reviewed zero-outcome TPR-1/TPR-2 manifests.

This confirmation grants no source, outcome, look, QC, broker, paper, live,
deployment, or capital authority. It closes the provenance question only.

### 14.6 Verified rather than accepted

- **The storage remedy is real.** Root `*.pdf binary` is set; the blueprint's
  committed blob, its working-tree bytes, and the record's pinned raw digest
  are all `55ce6703...ba14`. Cross-platform checkout identity is restored, and
  `TPR-CR1-001` is genuinely closed rather than declared closed.
- **The rebuild did not alter the reviewed specification.** The v2.0 and v2.1
  extracted text layers were diffed line by line: exactly one opcode, a pure
  append of the addendum at the end. All 842 non-blank lines of reviewed v2.0
  content are unchanged. Amending a governing artifact by appendix rather than
  by rewrite is the correct method and is what makes A19's supersession
  language safe.
- **The addendum's schedule claim is faithful.** The shared cutoff
  `2027-08-31`, reserved holdout `2027-09-01` through `2029-08-31`, and lane
  validation `2026-09-01` through `2027-08-31` match the Analyst Revisions V2
  frozen values exactly, and the three cited ARV2 commits all resolve.
- **Zero access is enforced, not merely declared.** All three registries carry
  `authority_mode: zero_access` with empty entries; the candidate artifact
  hashes to `99aae28d...ea49` exactly as recorded; `authorize_outcome_access`
  is typed `NoReturn` with every path raising, and it authenticates both
  negative declarations so that a missing or substituted authority file raises
  instead of reading as safe.
- **The reviewed-authority path resists the attacks it should.**
  `require_reviewed_algorithm_spec` chains exact-type identity, a private
  authority token, weakref registry identity that defeats `id()` reuse, a
  fingerprint comparison that detects post-construction mutation, and a reload
  from the original path that closes the verify-then-mutate window. The
  weakref finalizer checks reference identity before evicting.
- **Import discipline holds.** The package imports only the standard library
  and its own submodules; no `assistant`, `execution`, `ml`, provider, or
  network import appears. `subprocess` use is confined to read-only Git
  commands with explicit argument arrays and `shell=False`. No binary float
  arithmetic; `canonical.py` carries an explicit `_reject_binary_float`.
- **The implementer's counts are corroborated.** An independent complete run
  on the exact pushed tree gave **5,830 passed, 5 skipped, 0 failed, 25
  warnings in 997.26s**, against the recorded 5,829 passed / 5 skipped / 1
  failed. The one recorded failure did **not** reproduce, which independently
  supports the `TPR-OOL-005` diagnosis that the Briefing smoke test is a
  host-load and cache flake rather than a regression. The focused target and
  shared suite gave 187 passed / 3 skipped against a recorded 176 / 3; the
  difference is scope, not disagreement.

### 14.7 Scope not exhaustively audited

- `preregistration.py` is 2,163 lines. The authority, outcome-gate, identity,
  registry and canonical-value paths were read closely; the statistical
  binding procedures, estimator mechanics and power arithmetic were read for
  contract shape and fail-closed direction but **not** independently
  re-derived. Their numeric correctness rests on the module's own 889 lines of
  tests, which pass, and on future TPR-0B review.
- The import firewall was read and its forbidden-prefix set inspected. Its
  own docstring correctly limits it to a dependency guard rather than an
  operating-system sandbox; that limitation was not separately probed.
- No provider documentation, endpoint, entitlement, or licensed row was
  touched, so every source-capability statement in A22 remains an unmeasured
  assumption, exactly as A22 itself declares.

### 14.8 Authority state after this review

Unchanged and zero. No provider, credential, licensed row, source request,
outcome, evidence epoch, QuantConnect project, broker, operator database,
scheduler, paper surface, or live surface was accessed, and **0 research looks**
were spent. No live-assistant behavior can change: the only executable changes
are two documentation guards. The TPR-0A candidate remains unreviewed for the
purpose of its own registry, which stays empty.
