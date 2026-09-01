# Target-Price Revision ETF Strategy - implementation and session record

Status: **CODEX HAS COUNTER-REVIEWED EVERY CLAUDE COMMIT IN THE EXACT
TWO-COMMIT RANGE `b4e6b88c..8078ce48`. BOTH COMMITS ARE ACCEPTED AFTER
CORRECTION. FIVE P3 FINDINGS AND THEIR CORRECTIONS ARE RECORDED IN SECTION 25;
NO P0, P1 OR P2 WAS FOUND IN THE CLAUDE RANGE. A PRE-PUSH AUDIT FOUND FOUR
DESIGN P2S AND TWO P3S IN CODEX COMMIT `DFAEE5DE`; SECOND CODEX COMMIT
`15CE7F04` CLOSES ALL SIX BEFORE PUSH. THE OWNER
HAS APPROVED THE RECOMMENDED TPR TRUST-ROOT
IDENTITY, EXTERNAL PATH, CUSTODY/ROTATION POLICY, AND NORMAL REVIEWED-CODE
THREAT MODEL. SECTION 25 FREEZES THE BOUNDED TPR-TR0 DESIGN CANDIDATE FOR
CLAUDE'S INDEPENDENT REVIEW. NO DEDICATED TPR SIGNING KEY OR EXTERNAL
ALLOWED-SIGNERS FILE HAS BEEN PROVISIONED, NO SIGNED REGISTRY-ANCHOR COMMIT
EXISTS, AND THE DESIGN
GRANTS NO POSITIVE AUTHORITY. `TPR-CCR5-004` REMAINS OPEN UNTIL THE REVIEWED
DESIGN IS IMPLEMENTED, PROVISIONED, AND SATISFIED BY AN EXACT SIGNED REGISTRY
ANCHOR. `TPR-CCR2-011` SEPARATELY REMAINS OPEN UNTIL REVIEWER-CONTROLLED SIGNING
OR A SEPARATELY SIGNED REVIEW RECEIPT PROVES THE INDEPENDENT REVIEWER'S
IDENTITY. THE TPR-0A V2.2 PDF AND CANDIDATE ARTIFACT BYTES ARE
UNCHANGED; THE REVIEWED-SPEC REGISTRY REMAINS EMPTY, THE CANDIDATE REMAINS
UNREVIEWED FOR ITS OWN REGISTRY, AND NO POSITIVE ALGORITHM AUTHORITY EXISTS.
NO IMPLEMENTATION OR PROVISIONING MILESTONE IS AUTHORIZED BEYOND THIS DESIGN
CANDIDATE.
TPR-1 IS BLOCKED ON AN EXACT SEPARATELY REVIEWED SOURCE-RIGHTS ARTIFACT; TPR-0B
IS BLOCKED ON REVIEWED TPR-1/TPR-2 STRUCTURAL MANIFESTS; EVERY OUTCOME/LOOK GATE
REMAINS UNAVAILABLE.
NO AUTHENTICATED TARGET-PRICE SOURCE, INGEST, CANONICAL EVENT, SIGNAL, OUTCOME
ACCESS, RESEARCH LOOK, ETF TOPOLOGY, PORTFOLIO, QUANTCONNECT JOB OR RESULT,
SHADOW OR PAPER DEPLOYMENT, BROKER CONNECTION, OR LIVE-TRADING AUTHORITY
EXISTS.**

Sibling-lane changes and their independent reviews remain on their respective
branches. Their integration into `main` grants this target branch visibility,
not authority to alter sibling-owned artifacts.

Branch: `codex/strategy-target-price-revisions`

Worktree: the checkout `git worktree list` registers for this branch.
This lane is developed from more than one host, so no absolute directory
is pinned; see `TPR-CR4-002`.

Base commit:
`086b782e43a5ff889e71ec8e26334bb791ccac74`

Governing plan:
`TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf`

Governing plan SHA-256:
`f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`

Governing plan page count: **29**.

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
bounded milestone remain on `codex/strategy-target-price-revisions` in the
worktree `git worktree list` registers for it. A role may create
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

**Integration state, 2026-08-31.** All four strategy lanes were merged into
`main` (PRs #321, #322, #323 and #325), and this lane was fast-forwarded to
that integration point earlier on 2026-08-31. The histories later diverged;
neither current tip contains the other. Live ahead/behind counts are omitted
because every new lane commit invalidates them. The four-slot multiplicity
amendment nevertheless remains unpropagated: see `TPR-OOL-006`.

**Current qualification, 2026-08-31:** Codex has counter-reviewed Claude's
exact two-commit range
`b4e6b88ccf8a17a60cad91cda94205f61c1b7f90..8078ce4877613adf5f9378cc11258841ac38f76d`.
Both `433b2679` and `8078ce48` are accepted after correction. Section 25
contains their exact dispositions, five P3 findings, corrections, quality
rating, and validation. In the same bounded round, the owner-approved TPR-TR0
trust-root design candidate is frozen for Claude's independent review. The
reviewed implementation snapshot remains
`bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e`.
The sole-authority blueprint is the 29-page v2.2 artifact at raw SHA-256
`f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`.
The current candidate has spec ID
`tpr-round0a-candidate-74b096af24c8d481`, semantic hash
`74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c`,
and artifact SHA-256
`17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a`.

The TPR-0A snapshot remains a zero-access frozen candidate. The reviewed-spec
registry remains empty, the candidate is unreviewed for its own registry, and
`TPR-CCR2-011` still requires reviewer-controlled signing or a separately
signed review receipt before positive authority can rely on reviewer identity;
the owner-attestation anchor in section 25 does not close it. One pre-existing
target P2, `TPR-CCR5-004`, remains open: the runtime policy-path inventory can
remove its own defining file and another policy path while a matching registry
map still passes. The registry is empty today, so this mints no present
authority. The owner has approved the exact TPR-TR0 design inputs in section
25; the design remains non-authorizing until Claude independently reviews it,
Codex counter-reviews that exact review, and a later bounded implementation is
separately completed.

**Integration state, measured 2026-08-31:** the lane and `origin/main` have
since **diverged**, and neither contains the other. The earlier synchronization
statement was accurate when the lane was fast-forwarded earlier on 2026-08-31
and is no longer current; the exact sync point is recorded in the section 10
ledger row for that round.

Sibling-lane changes and their independent reviews remain on their respective
branches. Integration into `main` does not authorize a coordinated edit from
this target lane. TPR-TR0 is the only bounded design milestone in this round;
no implementation or provisioning milestone is authorized beyond this design
candidate. TPR-1 remains blocked
until a separately reviewed source-rights artifact proves
entitlement, public-time semantics, correction completeness, target-horizon
consistency, raw retention, derived processing, and QC-transfer rights. TPR-0B
remains blocked until reviewed TPR-1 and TPR-2 structural manifests exist.
After this Codex round's single push, Claude reviews the exact Codex range
beginning after `8078ce48`; that loop step grants no source, outcome, look, QC,
broker, paper, live, deployment, capital, or trading authority.

### Historical progression (not the current resume instruction)

The remainder of this section preserves how the earlier v2.1 and v2.2
candidates reached their reviews. Its role-next statements are historical,
not current instructions.

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
refinement follow in the current local candidate. That round has since been
published: the lane head is `fe056be6800ea11d6559f817019d1c2902f61620`.

The owner's 2026-08-29 decisions resolve those prerequisites without inventing
empirical evidence. The blueprint, now at version 2.2 with 29 pages
after the appended fixed-slot addendum A27, is the sole normative strategy
authority and is stored as binary at raw SHA-256
`f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`
(the superseded 28-page v2.1 artifact was `55ce6703...ba14`);
the malformed unavailable proposal pin is historical and non-blocking. TPR is
the fourth common family at alpha `0.0125`, with validation 2026-09-01 through
2027-08-31 and the shared 2027-09-01 through 2029-08-31 holdout prohibited.
TPR-0 is split honestly: TPR-0A freezes algorithms now, while TPR-0B binds
empirical structural values only after reviewed TPR-1/TPR-2 manifests and
before TPR-3 or any outcome access.

The bounded TPR-0A candidate is
`research/target_price_revisions/specs/tpr_round0a.candidate.json`, spec ID
`tpr-round0a-candidate-74b096af24c8d481`, semantic spec hash
`74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c`,
and artifact SHA-256
`17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a`
(the superseded v2.1 candidate was `f595992a...af86` at artifact
`99aae28d...ea49`).
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
| `TPR-OOL-006` | P2 | Sibling lane frozen preregistrations, principally `codex/strategy-analyst-revisions-v2` | That lane still freezes its selection-family alpha at `0.05 / 3 = 1/60` while the fixed family now has four permanent `1/80` slots. Under the pre-amendment sibling allocations, exact arithmetic is `3 * (1/60) + 1/80 = 1/16 = 0.0625`, above the family ceiling `1/20 = 0.05`; the displayed `0.0167` is only a rounded rendering of `1/60`. | **Escalated 2026-08-31: this is now a contradiction inside one integrated tree.** With all four lanes merged into `main`, that single tree simultaneously states the analyst lane's "three-lane correction remains 3" with its prospective look carrying `1/60`, no alpha freeze at all in Insider Buying or Short Interest, and this lane's fixed four-slot family at `1/80` naming `analyst-revisions-v2` as one of its slots. Measured directly from the integrated tree, not inferred. The owner froze the four named slots permanently on 2026-08-30 (section 16): each lane's maximum is `1/80`; the named slot remains fixed while an unused or withdrawn allocation expires and is never redistributed or used to recompute the denominator. Sibling-lane corrections and their independent reviews/counter-reviews remain on their own long-lived branches. This target branch does not edit them, and no lane receives outcome authority from this directive. |
| `TPR-OOL-008` | P2 | `research/analyst_revisions_v2/specs/*.json`; `research/ml_specs/*.json` | On the integrated tree the analyst lane's checkout-bytes guard (`test_canonical_production_artifacts_survive_checkout_as_exact_bytes`) **failed on this Windows host**: `legacy_reproduction_registry.json` held CRLF bytes while its committed blob is LF, and `git status` reported clean because the stat cache hid it. Five artifacts were affected. The repository content is correct; only the checkout was stale, and restoring each file from its committed blob turned the test green with `git diff HEAD` empty. The root cause is an attribute strategy difference: the analyst lane protects those files with `*.json -text` only (`text: unset, eol: unspecified`), which lets a pre-existing CRLF working copy persist, whereas this lane now uses `text eol=lf` (`text: unset, eol: lf`) and does not drift. `research/ml_specs/*.json` carry no attribute at all (`text: unspecified`) and Git warns they will be re-converted to CRLF on the next checkout, so their restoration here is temporary and no test currently covers them. | Documented, not fixed. The remedy is to adopt `text eol=lf` in the sibling lanes and give `research/ml_specs` equivalent protection, which touches another lane's and the ML surface's owned files. Route as one owner-coordinated change. The local checkout repair performed during this review changed no committed content. |
| `TPR-OOL-007` | P3 | `docs/THREE_STRATEGY_PROJECT_DIRECTION.md:274-278` | The shared coordination pointer still presents a local TPR-0A candidate whose next action is one push/review; it omits the completed initial review, the six Claude commits through `2ec0fad`, their Codex counter-review, and the current v2.2 candidate at `bb8dfb6`. | Documented, not fixed. The file is shared coordination surface outside this target-only lane; route a concise current-state correction through the appropriate owner-coordinated shared-document round. |
| `TPR-OOL-002` | P3 | `docs/Strategy Description/README.md` | The lane table and the surrounding prose describe a three-strategy program and omit Target-Price Revisions entirely, so a reader who starts at the directory README does not discover this lane, its branch, or its record. | That README is named in the parallel-workflow frozen-file list, so it needs the same owner-coordinated common-baseline amendment rather than a fourth competing edit. Documented, not fixed. |
| `TPR-OOL-001-R1` | P2 resolution | Owner-coordinated repository Git plumbing | The owner approved the common fix. Root `.gitattributes` now declares `*.pdf binary`; Git resolves the blueprint as binary with text/diff/merge unset. The PDF was rebuilt from the intact Git blob plus the two-page owner addendum and reopened strictly as 28 pages at raw SHA-256 `55ce6703...ba14` at that time; the current artifact is the 29-page v2.2 blueprint at raw SHA-256 `f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`, which supersedes that historical resolution state without reopening the finding. | Resolved under the explicit one-time owner coordination; this does not authorize later shared-file edits by inference. Raw-byte and resolved-attribute guards are target-owned. |
| `TPR-OOL-003` | P2 | Analyst Revisions V2 preregistration loader: `research/analyst_revisions_v2/preregistration.py:465,487` | Both persisted JSON paths use ordinary `json.loads`, which accepts duplicate object keys with last-key-wins behavior. A content-addressed authority artifact can therefore have ambiguous human/parser meaning. TPR's strict loader rejects duplicate keys, but this external accepted lane remains unchanged. | Documented only. Route to the Analyst Revisions V2 lane before any outcome authority; add duplicate-key mutations there. |
| `TPR-OOL-004` | P2 | Analyst Revisions V2 family contract: `research/analyst_revisions_v2/preregistration.py:56,931` and its draft/tests | The accepted draft/loader still names `three_lane_selection_correction` and requires value 3, while the owner has added TPR as the fourth shared family/attempt. The Analyst lane remains fail-closed and zero-access, so no current look is affected. | Documented only. Synchronize that lane's content-addressed artifact and tests to four before any Analyst outcome access; do not edit it from TPR. |
| `TPR-OOL-008` | P3 | `research/__init__.py`, shared with the Analyst Revisions V2 lane | `POLICY_CODE_REPO_PATHS` includes `research/__init__.py`, but this lane's new `research/target_price_revisions/.gitattributes` cannot pin a file outside its own subtree. The file is empty today, so newline translation cannot change its bytes and the anchor is unaffected. The moment it gains content on a `core.autocrlf` checkout it would break the reviewed-algorithm anchor exactly as `TPR-CR4-001` did. | Documented, not fixed. `test_policy_code_is_checked_out_as_exact_bytes` asserts the file is still empty and turns red rather than passing silently, which routes a shared `.gitattributes` amendment to the owner at the moment it is actually needed. |
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
| 2026-08-30 | Claude review (owner directive) | `f7ab9e2` -> record candidate | Owner multiplicity amendment | Recorded the owner's cross-lane multiplicity directive: one shared four-attempt family, total two-sided FWER `0.05`, equal unrecycled `1/80` per lane, within-lane multiplicity must subdivide, Analyst V2 re-freezes `3 / 1/60` -> `4 / 1/80`, Insider Buying and Short Interest freeze `4 / 1/80` before outcome authority, TPR unchanged at `1/80`, and every outcome gate stays closed until all four lanes complete their own review and counter-review. Measured this lane's frozen candidate as already compliant and left the artifact untouched. Complete suite on the exact committed tree `b2dbe89`: **5,832 passed, 5 skipped, 0 failed, 25 warnings in 973.79s**, the prior 5,831 plus exactly the one new guard with skips unchanged. Lane and shared documentation suites **178 passed, 3 skipped**; `compileall` exit 0; `git diff --check` clean. New exact-`Decimal` allocation guard; three mutations (recycling via family count, the old `0.0167` share, a second full-alpha look) each turned it red and the byte-identical restore returned it green. No provider, credential, licensed row, outcome, QuantConnect, broker, scheduler, paper or live access; **0 research looks**. | `TPR-CR2-002` closed by owner directive; propagation to three lanes tracked as `TPR-OOL-006`. Details in section 15. | None. The directive tightens a threshold and grants no source, outcome, look, QC, broker, paper, live or capital authority. | Codex counter-reviews this round. The three sibling re-freezes must each run in their own lane before any lane opens an outcome gate. |
| 2026-08-30 | Codex counter-review + v2.2 implementation | `6aae73bb381733c5239cb141e77cf1b7be6438d2` -> `bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e` plus record candidate | Counter-review six Claude commits; freeze the permanent four-slot contract in the sole-authority PDF and TPR-0A artifact | Counter-reviewed `5c452c7`, `f7ab9e2`, `ea7d59f`, `984ea9e`, `b2dbe89`, and `2ec0fad` commit by commit. Applied the owner's clarified contract: the four named lanes remain fixed; each permanently owns at most `1/80`; unused or withdrawn allocations expire and are never redistributed; and all confirmatory cells/looks within TPR sum to at most `1/80`. Appended PDF addendum A27 as v2.2, authenticated the explicit per-cell/look allocation in the content-addressed candidate, and corrected the confirmed documentation/test defects. Sibling artifacts were not edited. | PDF: 29 pages, raw SHA-256 `f6e98eef...ec30b`; first 28 pages text- and pixel-identical to v2.1; page 29 rendered and visually inspected. Focused implementation/import suite: **113 passed, 3 skipped**; focused malformed-digest regression: **2 passed**. Full-tree validation and exact push evidence follow in a later append-only row. Provider/outcome accesses **0**; authorized/spent looks **0**. | No P0/P1. `TPR-CCR3-001` through `TPR-CCR3-007` are closed or documented in section 16; `TPR-OOL-007` is documented and not fixed. | None. This is a stricter zero-access preregistration candidate, not permission to access source, outcomes, QC, broker, paper, live, deployment, or capital surfaces. | Complete full validation, append exact results without rewriting prior rows, commit the handoff, and make this Codex round's single push for Claude's independent review. |
| 2026-08-30 | Codex validation / handoff | `bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e` -> `6b12102b9710efb838e41cefd94cfcecd3ab592d` plus final documentation candidate | Exact v2.2 cumulative candidate validation | Reverified the content-addressed candidate, zero-access registries, PDF identity/binary treatment, current coordination pointers, fixed named slots, allocation expiry/no redistribution, within-lane sum ceiling, and target import boundary. No TPR provider reader, outcome path, QC path, broker path, or deployment path was added. | Exact committed-tree full suite on Python 3.14.6 / pytest 9.1.1: **5,842 passed, 5 skipped, 0 failed, 25 warnings in 1,065.11s**. Full `compileall -q` including `research` exited 0. Final complete target-price plus active-document suite: **188 passed, 3 skipped in 12.56s**; the narrower pre-validation document suite was **75 passed in 2.07s**. PDF raw SHA-256 `f6e98eef...ec30b`, artifact SHA-256 `17a2a902...2650a`, 29 pages, binary attributes set with text/diff/merge unset; `git diff --check` clean. Provider/outcome accesses **0**; authorized/spent looks **0**. | No TPR P0/P1. `TPR-CCR3-001` through `TPR-CCR3-007` are closed. `TPR-OOL-007` remains documented and deliberately unfixed. | None. Reviewed registry remains empty; source/look authority artifacts remain zero-access; TPR-0B, TPR-1, and every operational/trading gate remain blocked. | Commit the final append-only evidence, rerun the focused documentation guards on that documentation-only tree, make this round's single push, and hand the exact pushed range to Claude for independent review. |
| 2026-08-30 | Claude review | `2ec0fad4578c5a408a79740f0e89444922d05346` -> `fe056be6800ea11d6559f817019d1c2902f61620` reviewed; corrections on this same lane branch | Independent review of the Codex counter-review and the v2.2 fixed-slot amendment | Reviewed all three pushed commits individually. Accepted all seven counter-review findings against the prior Claude round, five of which were defects in that round's own work, including a guard docstring that invited the recomputation the owner's directive prohibits. Verified rather than accepted: the second blueprint rebuild is again append-only, the fixed-slot contract matches the directive exactly, the loader enforces it at load time, and no look can exist outside the alpha accounting. Corrected the record's current-state section, which still pinned the superseded v2.1 blueprint and candidate identities. | Independent complete run on the exact pushed tree `fe056be`: **5,842 passed, 5 skipped, 0 failed, 25 warnings in 1,080.30s**, reproducing the recorded count exactly on the actual pushed head rather than its code-tree predecessor. Three mutations on the new guard each turned it red with a text-identical restore returning it green. No provider, credential, licensed row, outcome, evidence-epoch, QuantConnect, broker, operator-database, scheduler, paper or live access; **0 research looks**. | All three commits accepted or accepted after correction. No P0/P1. `TPR-CR3-001` (P2) and `TPR-CR3-002` (P3) closed. Details in section 17. | None; all source, outcome, look, QC, broker, paper and live authority remains zero. | Codex counter-reviews every Claude commit in this round. TPR-0B and TPR-1 remain blocked, and the three sibling-lane re-freezes under `TPR-OOL-006` still gate every lane's outcome access. |
| 2026-08-30 | Claude validation | `5eecce5` -> `5eecce5` (exact tested tree; this validation-record commit follows) | v2.2 review round final validation | Revalidated the complete tree after the review corrections and the new current-artifact guard. No product file changed during the run. Recorded as a distinct appended event rather than by rewriting the review row, which is the correction accepted as `TPR-CCR3-006`. | Complete suite: **5,843 passed, 5 skipped, 0 failed, 25 warnings in 952.86s** — the 5,842 baseline plus exactly the one added guard, skips unchanged. Lane and shared documentation suites **189 passed, 3 skipped**; `compileall` exit 0 including `research`; `git diff --check` clean. No provider, credential, licensed row, outcome, QuantConnect, broker, scheduler, paper or live access; **0 research looks**. | No new finding. `TPR-CR3-001` and `TPR-CR3-002` remain closed. | None. | Make this Claude round's single push; Codex then counter-reviews every Claude commit. |
| 2026-08-30 | Codex counter-review correction | `db6a721d45eb47e1a133744387bf43a1aa1f310c` -> `0af1ca8c9165841373262bff4d173edc48aa1a74` plus final record/handoff correction | Counter-review only; next milestone blocked | Counter-reviewed `da6f7ea`, `5eecce5`, and `db6a721` individually; corrected the contradictory active state, hardened exact-current identity and routing guards, qualified review provenance and validation metadata, and removed the last stale pre-push handoff claim. No product, source, provider, or outcome code changed. | Exact post-guard target plus active-document suite **189 passed, 3 skipped in 13.20s**; preceding narrow document modules **76 passed in 3.71s**; network-restricted full run **5,838 passed, 5 failed, 5 skipped, 26 warnings in 1,282.03s**, with the exact five environment-affected nodes then **5 passed in 11.05s**; full compilation exit 0; mutations rejected; `git diff --check` clean. Python 3.12.13 / pytest 9.1.1. Provider/outcome accesses **0**; authorized/spent looks **0**. | No P0/P1. `TPR-CCR4-001` through `TPR-CCR4-006` are closed or qualified in section 18. | None; registries and zero-access declarations are unchanged. | Commit the final validation handoff and make this round's one push. Claude then reviews the exact correction range; TPR-1 and TPR-0B remain blocked. |
| 2026-08-30 | Claude review | `c8c74704bb9bbda5a756d90afa33666371125a89` reviewed; corrections on this same lane branch | Independent review of Codex's counter-review correction range | Reviewed `0af1ca8` and `c8c7470` individually and the cumulative `c8c7470` tree. Reproduced rather than accepted Codex's two historical claims. Found and corrected a P1 that made the reviewed-algorithm anchor unreachable on the supported Windows checkout, added a lane-scoped `.gitattributes` and a regression guard, and refreshed the working tree to exact blob bytes. No product, provider, source, or outcome code changed. | At the reviewed tip the lane suite was **186 passed, 3 failed, 3 skipped**; after the correction **120 passed, 3 skipped** with the three anchor tests green. Five mutations on Codex's hardened current-state guard and two on the new byte guard each turned red with byte-identical restores returning green. Complete suite on the exact final tree **5,844 passed, 5 skipped, 0 failed, 25 warnings in 2,186.28s**, the 5,843 baseline plus exactly the one added guard; `compileall` exit 0; `git diff --check` clean. Provider/outcome accesses **0**; authorized/spent looks **0**. | Both Codex commits accepted. `TPR-CR4-001` (P1) closed by correction; `TPR-CR4-002` (P2) **open, owner decision required**; `TPR-CR4-003` and `TPR-CR4-004` (P3) closed by qualification. `TPR-OOL-008` documented, not fixed. | None; all source, outcome, look, QC, broker, paper, live and capital authority remains zero. | Codex counter-reviews this range. `TPR-CR4-002` needs the owner to say which worktree path is real before any resume pointer is trusted; TPR-1 and TPR-0B remain blocked. |
| 2026-08-30 | Claude correction under owner direction | `50da9d07a46bcd0770fc3c9219b3d0a187494383` -> this round's head | Owner-directed worktree resolution; closes `TPR-CR4-002` | Replaced the hardcoded lane worktree in the Action Plan, Session Handoff, and record preamble with a `git worktree list` resolution instruction, and rewrote the guard to parse `git worktree list --porcelain` for this branch instead of comparing against a literal. The guard now also forbids any lane directory name in those three current-state surfaces. No product, provider, source, or outcome code changed. | Lane plus shared document suites **190 passed, 3 skipped**; complete suite on the exact final code tree **5,844 passed, 5 skipped, 0 failed, 25 warnings in 2,278.61s**, unchanged in count because the rewritten guard replaces a test rather than adding one; `compileall` exit 0; `git diff --check` clean. Four mutations (repinning a directory in each of the three surfaces, and removing the resolution instruction) each turned the guard red with byte-identical restores returning it green, and the porcelain parser was exercised directly and resolved this checkout. Provider/outcome accesses **0**; authorized/spent looks **0**. | `TPR-CR4-002` closed by owner direction. No P0, P1, or P2 remains open. | None; all source, outcome, look, QC, broker, paper, live and capital authority remains zero. | Codex counter-reviews `ea9d890`..this head. TPR-1 and TPR-0B remain blocked. |
| 2026-08-31 | Codex counter-review + correction | `f21d70851d5e1790be0c308e13e8837a7cd1d008` -> `943edf77ca61cae475e4986b985baab3097adfbc` plus final record candidate | Counter-review only; no next milestone authorized | Counter-reviewed `ea9d890`, `ce74e72`, `50da9d0`, and `f21d708` individually. Corrected ordinary-fast-forward LF migration, exact-byte and worktree-guard sensitivity/scope, current-role routing, and current range/report defects. Candidate/PDF and all authority JSON artifacts are unchanged. | Exact committed correction tree: target plus active-document suite **190 passed, 3 skipped in 13.88s**; network-restricted complete suite **5,844 passed, 5 skipped, 0 failed, 26 warnings in 1,030.57s**; full `compileall -q` exit 0. Exact-byte reverse mutation failed as required and its byte-identical restore passed; active-lane/no-registration and missing-current-instruction probes refused, while sibling text outside target blocks passed. Python 3.12.13 / pytest 9.1.1; system `core.autocrlf=true`. Provider/outcome accesses **0**; authorized/spent looks **0**. | No P0/P1. `TPR-CCR5-001` through `003` and `005` through `007` closed; `TPR-CCR5-004` (P2) open before any positive reviewed-algorithm authority. | None; registries remain empty/zero-access and no look is authorized or spent. | Commit the final record-only evidence, run the exact document guards/diff checks, make this round's single push, and have Claude review only the range beginning after `f21d708` and ending at the new pushed head. TPR-1 and TPR-0B remain blocked. |
| 2026-08-31 | Claude review + main sync | `db6a721d45eb47e1a133744387bf43a1aa1f310c` -> `3f33eea09aedbb8c386ebc355a6c875b76c80f83` reviewed; synchronized to `main` `cf136e259cf628aabdc4220865fccdb5c7204306`; corrections on this same lane branch | Independent review of two Codex counter-reviews and the CR4 round; no new milestone in range | Reviewed all eight pushed commits individually. Accepted all four counter-review findings against the prior Claude round, two of which repeat classes that round had already been corrected on. Fast-forwarded the lane onto the integrated `main` now that all four lanes are merged (PRs #321/#322/#323/#325); the merge-base equalled the lane head so no merge commit or conflict resolution was involved. Corrected the propagation routing whose branch premise the merge invalidated. | Baseline complete run on the synchronized tree: **6,789 passed, 13 skipped, 1 failed, 25 warnings in 1,314.44s**. The single failure was the analyst lane's checkout-bytes guard, diagnosed as a stale working tree rather than a repository defect (`TPR-OOL-008`): five artifacts held CRLF against LF blobs while `git status` reported clean. Restoring each from its committed blob turned the guard green with `git diff HEAD` empty, changing no committed content. Final complete run recorded separately. Adversarial probe of the reviewed-authority path: registry empty, both authority entry points refuse. Three mutations on the new guard each turned it red with text-identical restore. Python 3.14.6, pytest 9.1.1. No provider, credential, licensed row, outcome, evidence-epoch, QuantConnect, broker, operator-database, scheduler, paper or live access; **0 research looks**. | All eight commits accepted or accepted after correction. No P0/P1. `TPR-CR5-001` closed. `TPR-CCR5-004` remains open as Codex recorded it, independently reproduced here and confirmed inert. `TPR-OOL-006` escalated to a single-tree contradiction; `TPR-OOL-008` opened. Details in section 22. | None; all source, outcome, look, QC, broker, paper and live authority remains zero. | Codex counter-reviews every Claude commit in this round. No milestone is authorized: TPR-1 is blocked on source rights, TPR-0B on reviewed TPR-1/TPR-2 manifests, and `TPR-CCR5-004` gates any positive reviewed-algorithm authority. |
| 2026-08-31 | Claude validation | `0e911189` -> `0e911189` (exact tested tree; this validation-record commit follows) | v2.2 review round final validation | Revalidated the complete synchronized tree after the review corrections and the new guard. No product file changed during the run, and all work stayed inside the single named lane worktree. | Complete suite: **6,791 passed, 13 skipped, 0 failed, 25 warnings in 4,093.39s**. Reconciles exactly against the 6,789/13/1 baseline: 6,803 collected before and 6,804 after, with passed rising by two — the repaired analyst checkout guard plus this round's one new guard — and skips unchanged. Lane and shared documentation suites **191 passed, 3 skipped**; `compileall` exit 0 including `research`; `git diff --check` clean. Python 3.14.6, pytest 9.1.1. No provider, credential, licensed row, outcome, QuantConnect, broker, scheduler, paper or live access; **0 research looks**. | No new finding. `TPR-CR5-001` remains closed; `TPR-CCR5-004`, `TPR-OOL-006` and `TPR-OOL-008` remain open and owner-routed. | None. | Make this Claude round's single push; Codex then counter-reviews every Claude commit. |
| 2026-08-31 | Claude review | `cd23f7c8ea893f40b601d4ea791e1d9a14a72e7a` -> `b4e6b88ccf8a17a60cad91cda94205f61c1b7f90` reviewed; corrections on this same lane branch | Independent review of the Codex counter-review round; no milestone in range | Reviewed both pushed commits individually. Accepted all six counter-review findings against the prior Claude round, three of them repeats of classes already corrected. Verified the guard rework is stronger and that all seven new extractors fail closed. Advanced every current-state pointer to this round and corrected a stale present-tense synchronization claim. Did not re-sync to `main`: a fast-forward is no longer possible and a merge was not requested. | Baseline on the exact pushed tree `b4e6b88c`: **6,791 passed, 13 skipped, 0 failed, 25 warnings in 1,386.58s**, reproducing the recorded 6,791/13/0; the recorded 26-warning count is not reconciled. Final complete run recorded separately. Lane and shared documentation suites **192 passed, 3 skipped**. Two mutations on the new sync guard each turned it red with text-identical restore. Python 3.14.6, pytest 9.1.1. No provider, credential, licensed row, outcome, evidence-epoch, QuantConnect, broker, operator-database, scheduler, paper or live access; **0 research looks**. | Both commits accepted. No P0/P1/P2 in range; one P3 (`TPR-CR6-001`) found in the cumulative tree and closed. Counter-reviewed round quality **8/10**. `TPR-CCR5-004`, `TPR-OOL-006` and `TPR-OOL-008` remain open and owner-routed. Details in section 24. | None; all source, outcome, look, QC, broker, paper and live authority remains zero. | Codex counter-reviews every Claude commit in this round. No milestone is authorized; the lane also remains 2 commits behind `origin/main`. |
| 2026-08-31 | Claude validation | `433b2679` -> `433b2679` (exact tested tree; this validation-record commit follows) | Counter-review round final validation | Revalidated the complete tree after the review corrections and the new conditional sync guard. No product file changed during the run, and all work stayed inside the single named lane worktree. | Complete suite: **6,792 passed, 13 skipped, 0 failed, 25 warnings in 1,178.99s** — the 6,791 baseline plus exactly the one added guard, skips unchanged. Lane and shared documentation suites **192 passed, 3 skipped**; `compileall` exit 0 including `research`; `git diff --check` clean. Python 3.14.6, pytest 9.1.1. No provider, credential, licensed row, outcome, QuantConnect, broker, scheduler, paper or live access; **0 research looks**. | No new finding. `TPR-CR6-001` remains closed; `TPR-CCR5-004`, `TPR-OOL-006` and `TPR-OOL-008` remain open and owner-routed. | None. | Make this Claude round's single push; Codex then counter-reviews every Claude commit. The lane remains 2 commits behind `origin/main` and can no longer fast-forward. |
| 2026-08-31 | Codex counter-review + TPR-TR0 design freeze | `b4e6b88ccf8a17a60cad91cda94205f61c1b7f90` -> `15ce7f0475ca2dd91258905fe001782848952ffb` | Counter-review two Claude commits; freeze only the owner-approved signed-registry-anchor design | Accepted `433b2679` and `8078ce48` after correction. Closed five P3 document/guard findings and froze exact principal, external allowed-signers path, signed registry-anchor lineage, custody/rotation policy, and normal reviewed-code threat model for independent review. A pre-push audit found four design P2s and two P3s in first Codex commit `dfaee5de`; second commit `15ce7f04` closes all six. No runtime trust verifier or authority artifact was implemented. | Fetched local/remote head `8078ce48`; red regression proved the stale current topology. Active-document plus target-price suites ended **194 passed, 3 skipped**; exact complete evidence is in section 25.6 and the validation row below. No dedicated TPR signing key, external trust file, signature, provider row, outcome, QC surface, broker surface, or order was created; **0 research looks**. | No P0/P1/P2 in the Claude range. `TPR-CCR7-001` through `011` closed by correction/verification. `TPR-CCR5-004` remains open pending reviewed implementation and a trusted signed registry anchor; `TPR-CCR2-011` separately remains open pending reviewer-controlled signing or a signed review receipt. | None. TPR-TR0 is a non-authorizing design candidate. | Append exact final validation evidence, make one push, then Claude independently reviews every Codex commit beginning after `8078ce48`. |
| 2026-09-01 | Codex validation / handoff | `15ce7f0475ca2dd91258905fe001782848952ffb` -> `15ce7f0475ca2dd91258905fe001782848952ffb` (exact tested tree; this record commit follows) | TPR-TR0 design-round final validation | Revalidated the full repository after all counter-review and pre-push security corrections. No product/runtime file changed, and all work stayed in the named target-price branch/worktree. | Complete suite **6,792 passed, 13 skipped, 2 failed, 25 warnings in 1,278.97s**. Both failures exactly reproduce out-of-lane `TPR-OOL-009`; no TPR test failed. Active-document plus target-price suites **194 passed, 3 skipped in 14.18s**; target document module **12 passed in 1.06s**; `compileall` exit 0 including `research`; `git diff --check` and exact-commit status clean. Python 3.12.13, pytest 9.1.1. Trust directory/file absent; provider/outcome accesses and authorized/spent looks **0**. | `TPR-OOL-009` remains open and documented, not fixed. `TPR-CCR5-004` and `TPR-CCR2-011` remain blocked. No new TPR finding. | None. No source, outcome, look, QC, broker, paper, live, deployment, capital, or trading authority. | Commit this record-only handoff, run final document/diff checks, make the round's one push, then Claude reviews `8078ce48..pushed-head` commit by commit. |
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
| `TPR-CR2-002` | P2 | **Closed by owner directive 2026-08-30; propagation pending in three lanes under `TPR-OOL-006`** | `ba01e98` | Addendum A23, `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`, sibling lane preregistrations | The shared selection family was amended to four members and Target-Price Revisions took alpha `0.0125` (`0.05 / 4`), but the Analyst Revisions V2 preregistration still freezes its family alpha at `0.05 / 3 = 0.0167`, and no document records that the three existing lanes must be re-frozen. If each lane tests at its own currently frozen alpha the family-wise budget spent is `0.0167 x 3 + 0.0125 = 0.0625`, above the intended `0.05`. | The ARV2 lane states **`0.05 / 3 = 0.0167`** for its family alpha. The target lane states `0.0125` in its record and twice in `preregistration.py`. A search of the amended direction document and the lane record for any re-freeze or propagation obligation returns nothing. | Multiplicity is the control that makes a four-family selection claim honest. A half-applied amendment that lowers only the new family's alpha understates the true family-wise error, and it is far cheaper to reconcile now than after a look is spent. | The owner amended the contract on 2026-08-30: one shared family, total FWER `0.05`, an equal unrecycled `1/80` per lane, within-lane multiplicity must subdivide, Analyst V2 re-freezes `3 / 1/60` -> `4 / 1/80`, the other two freeze `4 / 1/80` before outcome authority, and every outcome gate stays closed until the amendment is reviewed and counter-reviewed in all four lanes. Section 15 records it. This lane needed no change and was measured compliant. The three sibling re-freezes are deliberately not performed from this branch. | `test_shared_family_alpha_allocation_is_exact_and_unrecycled` pins the arithmetic and the single-look inventory; three mutations (recycling, the old `0.0167` share, a second full-alpha look) each turn it red with a byte-identical restore returning it green. No test is added for another lane's frozen contract. **0 looks are spent in any lane**, which is also what makes the Analyst V2 re-freeze legitimate rather than post-hoc. |
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

## 15. Owner multiplicity directive - 2026-08-30

**Current qualification:** section 16 and blueprint v2.2 supersede this
section's interim interpretation. The family is not recomputed when a lane is
unused, withdrawn, added, or replaced: it remains the same four named slots,
each with a permanent maximum of `1/80`. Unused or withdrawn allocations
expire and are never redistributed. The target artifact did require amendment
to state and authenticate those rules and to make all confirmatory cell/look
allocations explicitly summable. Therefore the historical statements below
that no artifact change was required, that this record temporarily carried
normative authority, or that a family-size change should recompute the share
are not current instructions.

The owner resolved `TPR-CR2-002` with an explicit cross-lane amendment. It is
recorded verbatim in substance below because it binds four lanes, not only
this one.

### 15.1 The frozen contract

| Element | Frozen value |
|---|---|
| Shared family | The four strategy-selection attempts form **one** family |
| Total two-sided FWER | `0.05` |
| Per-lane allocation | `1/80 = 0.0125`, equal across the four lanes |
| Recycling | **Prohibited.** Unused alpha from any lane is never redistributed |
| Within-lane multiplicity | Must subdivide that lane's `0.0125` further, never consume it again |
| Analyst Revisions V2 | Re-freeze from `3 / 1/60` to `4 / 1/80` |
| Insider Buying, Short Interest | Must freeze `4 / 1/80` **before** receiving outcome authority |
| Target-Price Revisions | Remains at `1/80`; no change required |
| Gate | **All outcome gates stay closed** until the amendment is independently reviewed *and* counter-reviewed in **every** affected lane |

### 15.2 Target-lane compliance, measured

The TPR-0A candidate already satisfies the directive; no artifact change is
required and the frozen candidate is therefore untouched. Measured directly
from `research/target_price_revisions/specs/tpr_round0a.candidate.json`:

- `family_multiplicity.allocation` is
  `equal_bonferroni_across_four_shared_families`;
- `shared_family_count` is `4` and `shared_family_wise_alpha` is `0.05`;
- `assigned_family_alpha` is `0.0125`, and `0.0125 x 4 == 0.05` exactly in
  `Decimal`;
- `look_budget` is `1`, with exactly one permanent look id
  (`tpr-look-stock-primary-001`), one permanent primary cell id
  (`tpr-stock-primary-20d`), and exactly one entry in `looks`; and
- `external_append_only_authority_required` is `true`.

Because the lane holds exactly one inferential look and one primary cell,
there is no within-lane multiplicity to subdivide today. Any future secondary
or exploratory cell must divide the `0.0125`, not draw it again.

The two genuinely new constraints -- no recycling, and mandatory within-lane
subdivision -- are not yet stated in words inside the frozen artifact, which
records the allocation but not those two prohibitions. The candidate is
substantively compliant, so nothing is blocked; the next Codex round should
carry the two prohibitions into the artifact text when it next revises the
spec, and until then this section and the guard below are their authority.

### 15.3 Durable enforcement added

`test_shared_family_alpha_allocation_is_exact_and_unrecycled` pins the
directive as exact `Decimal` arithmetic rather than as the literal `0.0125`,
so the relationship survives a legitimate change in family size: if a lane is
ever added or withdrawn, the guard fails until the per-lane share is
recomputed, which is exactly what "no recycling" forbids doing silently.

Three mutations verify it, each turning the guard red with a byte-identical
restore returning it green:

| Mutation | Result |
|---|---|
| `shared_family_count` 4 -> 3 with the share unchanged (recycling) | red |
| `assigned_family_alpha` reverted to the old `0.0167` | red |
| A second full-alpha look added instead of subdividing | red |

Complete-suite validation on the committed tree `b2dbe89`: **5,832 passed, 5 skipped,
0 failed, 25 warnings in 973.79s**.

### 15.4 Propagation is not performed by this record

> **Superseded in part on 2026-08-31; see section 22.** The branch premise
> below is no longer true: all four strategy lanes were merged into `main`
> (PRs #321, #322, #323, #325), and this lane was synchronized to the
> integrated `main` at that time. It has since diverged from `main`; the
> measured state is in section 8. The per-lane review and counter-review requirement, the
> required actions, and the measured frozen states in the table all still
> stand. The original text is retained unaltered as the record of what was
> true when the directive was recorded.

Recording the directive here does **not** deliver it to the other three lanes.
They are separate long-lived branches, this branch is deliberately unmerged,
and the owner requires independent review and counter-review in every affected
lane. Each lane must therefore run its own round:

| Lane | Required action | Current frozen state |
|---|---|---|
| `codex/strategy-analyst-revisions-v2` | Re-freeze `3 / 1/60` -> `4 / 1/80`; independent review and counter-review | still `0.05 / 3 = 0.0167` |
| `codex/strategy-insider-buying` | Freeze `4 / 1/80` before any outcome authority | not yet frozen |
| `codex/strategy-short-interest` | Freeze `4 / 1/80` before any outcome authority | not yet frozen |
| `codex/strategy-target-price-revisions` | None; already `1/80` and measured compliant | `0.0125`, verified above |

Re-freezing Analyst Revisions V2 is safe specifically because **zero looks have
been spent in any lane** and the change tightens rather than loosens the
threshold (`0.0167 -> 0.0125`). Had that lane already observed its primary
statistic, the same edit would be a post-hoc alpha change and would invalidate
the result rather than correct it. That condition should be re-verified in the
analyst lane at the moment of re-freezing, not assumed from this record.

No lane may open an outcome gate until all four have completed the amendment
under their own review and counter-review.

## 16. Codex counter-review and v2.2 fixed-slot amendment - 2026-08-30

Codex counter-reviewed every commit in Claude's six-commit range
`6aae73bb381733c5239cb141e77cf1b7be6438d2..2ec0fad4578c5a408a79740f0e89444922d05346`
before implementing the owner's clarified fixed-slot contract. The exact
implementation snapshot is `bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e`.
The cumulative candidate remains pending Claude's independent review of this
round's exact single-push snapshot and Codex's later counter-review of every
Claude commit.

### 16.1 Commit-by-commit dispositions

| Claude commit | Disposition | Counter-review basis and correction |
|---|---|---|
| `5c452c7` | Accepted after correction | Restoring the repository-wide malformed-digest guard and tightening the worktree pointer guard were correct. The detector still accepted uppercase malformed hex; `TPR-CCR3-007` makes the compiled expression case-insensitive and adds a permanent uppercase mutation test. |
| `f7ab9e2` | Accepted after correction | The review report and validation evidence are credible. Current-state pointers were stale and the reported `0.0167 * 3 + 0.0125 = 0.0625` mixed rounded and exact arithmetic; `TPR-CCR3-003` and `TPR-CCR3-005` qualify both. |
| `ea7d59f` | Accepted after correction | The complete-suite evidence is credible, but an earlier append-only ledger row was edited instead of appending a distinct validation event. `TPR-CCR3-006` preserves the published history and appends this round separately. |
| `984ea9e` | Accepted after correction | Exact-`Decimal` enforcement was directionally useful. The test duplicated `import json`, and the accompanying prose incorrectly implied family-size recomputation after withdrawal; `TPR-CCR3-001` and `TPR-CCR3-004` correct those defects. |
| `b2dbe89` | Accepted after correction under the owner's explicit clarification | The commit faithfully recorded its then-understood directive, but treated the record/test as temporary normative authority and left the sole-authority PDF and artifact unchanged. The owner expressly approved the permanent four-slot contract, and `TPR-CCR3-002` is closed by blueprint v2.2 plus the authenticated TPR-0A artifact. |
| `2ec0fad` | Accepted after correction | The exact-tree validation evidence is credible, but it repeated the append-only ledger rewrite pattern. `TPR-CCR3-006` records the correction without altering the published commit. |

### 16.2 Counter-review issue ledger

| ID | Severity | Status | Evidence | Resolution |
|---|---|---|---|---|
| `TPR-CCR3-001` | P3 | Closed | `tests/target_price_revisions/test_document_consistency.py` imported `json` twice after `984ea9e`. | Removed the duplicate import. |
| `TPR-CCR3-002` | P2 | Closed by explicit owner authorization and implementation | Section 15 said the record/test temporarily carried the new prohibitions while the sole-authority PDF and content-addressed artifact stayed unchanged. | Added v2.2 addendum A27 and regenerated the authenticated TPR-0A candidate with the fixed lane IDs, permanent slot ceiling, expiry/no-redistribution policy, and explicit confirmatory allocations. The PDF remains the sole normative authority. |
| `TPR-CCR3-003` | P2 | Closed | The record header/section 8, Action Plan, and Session Handoff still described the pre-review v2.1 candidate or named Codex counter-review as the next action. | Updated only the target record and the two required current-state coordination pointers to the v2.2 candidate and Claude-next gate. |
| `TPR-CCR3-004` | P2 | Closed | Section 15.3 said a lane addition or withdrawal should cause the share to be recomputed, contrary to permanent named slots and expiring unused/withdrawn allocations. | Fixed four exact lane IDs and prohibited transfer, redistribution, and denominator recomputation. The named slot remains fixed; its unused or withdrawn `1/80` allocation expires. |
| `TPR-CCR3-005` | P3 | Closed by qualification | The review used rounded `0.0167` as though it were exact while reporting the exact total `0.0625`. | The exact pre-amendment expression is `3 * (1/60) + 1/80 = 1/16 = 0.0625`; `0.0167` is identified only as a rounded display. |
| `TPR-CCR3-006` | P2 | Closed prospectively | `ea7d59f` and `2ec0fad` rewrote prior ledger rows rather than appending distinct events. | Published history is retained. This record adds distinct counter-review/implementation and final-validation rows and restates that prior rows are never rewritten or deleted. |
| `TPR-CCR3-007` | P3 | Closed | The restored malformed-SHA guard matched only lowercase hexadecimal text, allowing a 63-character uppercase digest-like pin to bypass the invariant. | Compiled the detector with case-insensitive matching and added a regression proving uppercase 63-character text fails while a valid uppercase 64-character digest passes. |

No P0 or P1 was found. `TPR-OOL-007` records the one confirmed stale shared
coordination pointer and deliberately leaves it untouched on this branch.

### 16.3 Owner-authorized fixed selection-family contract

The binding contract implemented in this target lane is:

- the fixed family members are `analyst-revisions-v2`, `insider-buying`,
  `short-interest`, and `target-price-revisions`;
- the family's total two-sided FWER ceiling is permanently `1/20 = 0.05`;
- each named lane has a permanent maximum allocation of
  `1/80 = 0.0125`;
- an unused or withdrawn allocation expires and is never transferred,
  redistributed, or used to recompute another lane's maximum;
- every confirmatory cell and look inside one lane must have an explicit
  allocation, and their sum must be no greater than that lane's `1/80`; and
- sibling-lane artifact changes remain on their respective branches.

This authorization is limited to the target PDF and TPR-0A candidate. It
grants no provider, credential, licensed-row, source, outcome, research-look,
QuantConnect, QC, broker, operator-database, shadow, paper, live, deployment,
capital, or trading authority.

### 16.4 Sole-authority PDF v2.2

The amended sole normative specification is the 29-page
`TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf`, raw SHA-256
`f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`.
Addendum A27 on physical page 29 freezes the four named permanent slots, the
expiry/no-redistribution rule, the within-lane `1/80` sum ceiling, target-lane
scope, and unchanged zero-authority gates. The first 28 pages are extracted-
text-identical and pixel-identical to reviewed v2.1; page 29 was rendered and
visually inspected. No prior normative line was silently rewritten.

### 16.5 Authenticated TPR-0A candidate

The regenerated candidate is
`research/target_price_revisions/specs/tpr_round0a.candidate.json`:

- spec ID `tpr-round0a-candidate-74b096af24c8d481`;
- semantic hash
  `74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c`;
- raw artifact SHA-256
  `17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a`;
- 24 frozen cells, 39 null empirical child bindings, and 48 total pending
  prerequisites;
- one `planned_unbound` primary look/cell allocation of `1/80`, with an
  authenticated sum at or below the permanent within-lane ceiling; and
- an empty reviewed-spec registry plus zero-access source and permanent-look
  authority artifacts.

The loader rejects lane-set drift, non-exact decimal text, a transferable or
redistributable slot, duplicate allocation identities, an allocation sum over
`1/80`, inventory/allocation disagreement, or disagreement among the family,
empirical-binding, and acceptance alpha fields. The artifact records a plan;
no look is authorized or spent.

### 16.6 Validation and exact next gate

Before the documentation handoff, the focused implementation/import suite
passed with **113 passed, 3 skipped**, and the focused case-insensitive
malformed-digest regression passed with **2 passed**. PDF strict-open, page-
count, raw-hash, unchanged-first-28-page, render, and visual checks passed.
On exact committed tree `6b12102b9710efb838e41cefd94cfcecd3ab592d`,
the full suite on Python 3.14.6 / pytest 9.1.1 passed with **5,842 passed, 5
skipped, 0 failed, 25 warnings in 1,065.11 seconds**; full `compileall -q`
including `research` exited 0. The
append-only final ledger row above records the exact artifact and handoff
evidence. The final complete target-price plus active-document suite passed
with **188 passed, 3 skipped in 12.56 seconds**. The exact documentation-only
bytes are rechecked with the narrow identity/document guards before commit and
the single push.

After this Codex round's single push, Claude independently reviews every
commit and the cumulative v2.2 tree on this same branch/worktree. TPR-0B,
TPR-1, all outcome access, every research look, ETF/QC work, and every
operational or trading stage remain blocked. A later Codex round must
counter-review every resulting Claude commit before any next milestone.

## 17. Claude independent review - 2026-08-30 (v2.2 fixed-slot amendment)

**Disposition: accepted after correction.** No P0 or P1 issue exists. The
fixed-slot contract is a genuine improvement on what it replaced, including on
the guard this reviewer wrote, and the counter-review of the prior Claude round
was accurate on every point. One P2 remains: the record's own current-state
section still presents the superseded v2.1 artifact identities as current,
which is the exact location the counter-review's `TPR-CCR3-003` named and only
partly corrected.

### 17.1 Exact reviewed snapshot

| Item | Value |
|---|---|
| Reviewed range | `2ec0fad..fe056be` (three commits) |
| Review head | `fe056be6800ea11d6559f817019d1c2902f61620` |
| Remote head at review | identical; ancestry from `2ec0fad` verified, no history rewrite |
| Implementation snapshot | `bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e` |
| Blueprint | v2.2, 29 pages, raw SHA-256 `f6e98eef...ec30b` |
| Candidate | `tpr-round0a-candidate-74b096af24c8d481`, artifact SHA-256 `17a2a902...650a` |
| Corrections | committed on this same lane branch |
| Environment | Windows 11, Python 3.14, pytest 9.1.1 |

### 17.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e` | **accepted** | The fixed four-slot contract, the v2.2 addendum, the regenerated candidate, and the corrections to this reviewer's guards. Verified in 17.5. No issue found. |
| `6b12102b9710efb838e41cefd94cfcecd3ab592d` | **accepted after correction** | The counter-review record and coordination-pointer updates. Carries `TPR-CR3-001`: section 8 was left describing the v2.1 blueprint and the superseded candidate as current, in the same commit that corrected the header for that reason. |
| `fe056be6800ea11d6559f817019d1c2902f61620` | **accepted after correction** | Record-only validation handoff; its counts are corroborated in 17.5. Carries `TPR-CR3-002`. |

### 17.3 Codex findings against the prior Claude round: all accepted

All seven are accepted; five were defects in this reviewer's own work.

| Codex finding | Assessment |
|---|---|
| `TPR-CCR3-001` duplicate `import json` | **Confirmed.** Introduced when wiring the alpha guard's imports. |
| `TPR-CCR3-004` the guard's prose implied recomputing the share after a withdrawal | **Confirmed, and the most important of the seven.** The arithmetic passed on the frozen state, but the stated rationale described recycling as the correct response to a family-size change, which is the opposite of the owner's rule. A future reader following that docstring would have recomputed the denominator, which the directive prohibits. Replacing the count with four permanently named lane slots is the right fix. |
| `TPR-CCR3-005` rounded and exact arithmetic mixed | **Confirmed.** The report wrote `0.0167 x 3 + 0.0125 = 0.0625`; `0.0167 x 3` is `0.0501`, giving `0.0626`. The exact expression is `3 x (1/60) + 1/80 = 1/16 = 0.0625`, and `0.0167` is only a rounded display of `1/60`. |
| `TPR-CCR3-006` ledger rows rewritten rather than appended | **Confirmed.** Section 10 requires appending a row per durable event and never rewriting one. Two validation commits edited an already-committed row instead of appending a distinct validation event. |
| `TPR-CCR3-007` malformed-digest detector matched lowercase only | **Confirmed.** `[0-9a-f]{55,80}` let a 63-character uppercase pin through the invariant it exists to enforce. Extracting a case-insensitive helper with its own direct unit test is a better shape than the inline expression. |
| `TPR-CCR3-003` stale current-state pointers | **Confirmed** for the header, Action Plan and handoff. Incompletely applied; see `TPR-CR3-001`. |
| `TPR-CCR3-002` record and test treated as temporary normative authority | **Accepted.** Deferring the two prohibitions to the next spec revision was the conservative choice at the time, but the owner's approval made carrying them into the sole-authority PDF and the content-addressed artifact available immediately, which is the stronger resolution. |

### 17.4 P0-P3 issue ledger

Resolved items are retained. There is no P0 or P1 finding.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `TPR-CR3-001` | P2 | Closed | `6b12102` | Section 8, "Exact next step" | Section 8 states in the present tense that "the repaired 28-page v2.1 blueprint **is** the sole normative strategy authority and **is stored** as binary at raw SHA-256 `55ce6703...ba14`", and that "the bounded TPR-0A candidate **is** ... spec ID `tpr-round0a-candidate-f595992a3f5b8396` ... artifact SHA-256 `99aae28d...ea49`". All five identities were superseded by the same commit range. Section 8 is where a reader goes for current state, so the record directs anyone verifying artifact identity at superseded digests -- in a lane whose entire discipline is content addressing, that is the failure the hashing exists to prevent. It is also the exact section `TPR-CCR3-003` named, corrected in the header but not here. | The header at lines 25-28 carries the current `f6e98eef...ec30b` and 29 pages; section 8 carries `55ce6703...ba14`, 28 pages, and the superseded candidate triple. The handoff, by contrast, was updated correctly and carries the current identities. | A current-state section that names superseded content addresses is worse than one that names none: it invites a verifier to conclude the tree is corrupt, or to treat a superseded candidate as authoritative. | Section 8 now names the v2.2 blueprint, its digest and page count, and the current candidate identity, and marks the superseded values as historical where they are retained. | New guard `test_exact_next_step_names_the_current_artifacts` asserts section 8 carries the current blueprint digest and current candidate artifact hash. Reverting either to its superseded value turns it red; restore returns it green. |
| `TPR-CR3-002` | P3 | Closed | `6b12102` | Out-of-lane ledger row `TPR-OOL-001-R1` | The row states the blueprint "now reopens strictly as 28 pages at raw SHA-256 `55ce6703...ba14`". The out-of-lane ledger is a current-state routing table, not append-only history, so the present tense reads as today's state; it is 29 pages at `f6e98eef...ec30b`. | Measured directly from the checked-out artifact. | A routing table an owner reads to schedule external work should not describe a superseded artifact as the present one. | The row now records the v2.1 repair as the historical resolution event and names the current v2.2 identity. | Covered by the same guard's blueprint-digest assertion over the record, plus the existing pinned-digest guards. |

### 17.5 Verified rather than accepted

- **The second rebuild is again append-only.** The v2.1 and v2.2 extracted text
  layers were diffed line by line: exactly one opcode, a pure insert of 44
  lines at the end. All 925 lines of previously reviewed content are
  unchanged. Two consecutive amendments have now been made by appendix rather
  than by rewrite, which is what makes the addendum supersession language safe
  to rely on.
- **The blueprint is stored correctly.** Committed blob and working-tree bytes
  are both `f6e98eef...ec30b`; the binary attribute is holding.
- **The candidate artifact matches its pin** at `17a2a902...650a`.
- **The fixed-slot contract implements the directive exactly.** Four named
  lane ids rather than a mutable count; `slot_reallocation` records
  `transferable: false`, `unused: EXPIRES`, `withdrawn: EXPIRES`,
  `redistribution: PROHIBITED`; `within_lane_confirmatory_alpha_ceiling` is
  `0.0125` with an explicit summable allocation list.
- **The two corrections to this reviewer's guards are improvements, not
  substitutions.** Replacing the mutable `shared_family_count` with four
  permanently named slots removes the recomputation the prior docstring
  invited. Replacing `len(looks) == 1` with a summed allocation ceiling is
  strictly better: the inventory-length proxy would have rejected a legitimate
  subdivision into two looks at `0.00625`, while the sum accepts it and still
  refuses any total above `1/80`.
- **The loader enforces the contract, not only the tests.** Membership,
  alphas, reallocation policy, per-allocation bounds, duplicate pairs,
  strict positivity, exact coverage of the permanent inventory and the summed
  ceiling all refuse at load time with typed errors.
- **A look cannot escape the alpha accounting.** `_validate_looks` refuses any
  list that is not exactly one look with the exact frozen id, family, cell,
  period and unbound state, so no second look can exist outside
  `confirmatory_alpha_allocations` in TPR-0A.
- **The loader is relational where the test is frozen.** The loader requires
  `look_budget == len(allocations)` for any future spec, while the test pins
  today's frozen `1`. That division was examined and is correct: pinning a
  frozen preregistration value is the point of freezing it, and subdivision
  would require a reviewed amendment anyway.
- **The counts are corroborated.** An independent complete run on the exact
  pushed tree `fe056be` gave **5,842 passed, 5 skipped, 0 failed, 25 warnings in 1,080.30s**, matching against the recorded 5,842
  passed / 5 skipped / 0 failed on `6b12102`. The implementer validated the
  code tree and then committed a documentation-only successor, disclosing it;
  this run covers the actual pushed head.

### 17.6 Scope not exhaustively audited

- The new loader logic was read in full; the pre-existing statistical binding
  procedures, estimator mechanics and power arithmetic were again read for
  contract shape and fail-closed direction only, not re-derived.
- Page 29 of the blueprint was read as extracted text, not inspected as a
  rendered image.
- No provider, endpoint, entitlement or licensed row was touched. Every
  source-capability statement in A22 remains an unmeasured assumption.

### 17.7 Authority state after this review

Unchanged and zero. No provider, credential, licensed row, outcome, evidence
epoch, QuantConnect project, broker, operator database, scheduler, paper or
live surface was accessed, and **0 research looks** were spent. The reviewed
registry remains empty and the candidate remains unreviewed for its own
registry's purposes. The only executable change in this round is one added
documentation guard.

### 17.8 Final validation on the corrected tree

Recorded as a separate event rather than by amending 17.5, per `TPR-CCR3-006`.

Complete suite on the exact committed tree `5eecce5`: **5,843 passed, 5
skipped, 0 failed, 25 warnings in 952.86s**. That is the 5,842 baseline plus
exactly the one guard added in this round, with skips unchanged. Full
`compileall -q` including `research` exited 0 and `git diff --check` was clean.
The lane and shared documentation suites passed with **189 passed, 3 skipped**.

## 18. Codex counter-review of Claude's v2.2 review - 2026-08-30

**Disposition: accepted after correction and qualification.** Codex reviewed
all three Claude commits individually and the cumulative `db6a721` tree. No P0
or P1 exists. The artifact-identity corrections and validation event are
credible, but the final durable state still contradicted itself about whether
Claude's review had finished, and the new guard could pass with stale current
claims beside the new values. Those defects are corrected in this round. No
next implementation milestone is authorized by the governing PDF or Action
Plan.

### 18.1 Exact counter-reviewed snapshot

| Item | Value |
|---|---|
| Branch / worktree | `codex/strategy-target-price-revisions` / `C:\git\customizedagent\trading_agent_target_price` |
| Previously processed Codex head | `fe056be6800ea11d6559f817019d1c2902f61620` |
| Claude range | `fe056be6800ea11d6559f817019d1c2902f61620..db6a721d45eb47e1a133744387bf43a1aa1f310c` |
| Claude commits, ordered | `da6f7ea7261b63d294134a704792fbc8413e4c55`, `5eecce57789d2b2702085145d09b357d826d65fa`, `db6a721d45eb47e1a133744387bf43a1aa1f310c` |
| Remote / local head at counter-review start | `db6a721d45eb47e1a133744387bf43a1aa1f310c`; identical and clean after a branch-only fetch |
| Implementation snapshot under review | `bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e` |
| Counter-review correction commit | `0af1ca8c9165841373262bff4d173edc48aa1a74` |

### 18.2 Commit-by-commit dispositions

| Claude commit | Disposition | Counter-review basis |
|---|---|---|
| `da6f7ea7261b63d294134a704792fbc8413e4c55` | **Accepted after correction** | Adding a target-owned guard for section 8 was correct. At this exact standalone object, the guard is intentionally red until the next commit changes the record: the current candidate ID and artifact hash assertions already pass, while the current full blueprint digest assertion fails. The guard also checked only positive token occurrence across all of section 8, so a stale labeled candidate could coexist with the current one and pass; it could not verify the section-9 routing row that section 17 credited to it. `TPR-CCR4-002` strengthens the guard around an explicit current block and exact labeled-value sets. `TPR-CCR4-005` records the standalone-red sequencing qualification. |
| `5eecce57789d2b2702085145d09b357d826d65fa` | **Accepted after correction** | The v2.2 identity corrections, independent-review report, and closed `TPR-CR3-001` / `TPR-CR3-002` findings are substantively sound. The same final tree nevertheless retained `pending Claude review` as the current state in the record header/section 8, Action Plan, Session Handoff, and a target guard, while section 17 said review was complete and Codex was next. It also retained a present-tense v2.1 candidate statement. `TPR-CCR4-001` makes every active resume pointer consistent. |
| `db6a721d45eb47e1a133744387bf43a1aa1f310c` | **Accepted after qualification** | Appending a distinct validation event instead of rewriting the prior row correctly follows `TPR-CCR3-006`; its diff is record-only and clean. The 5,843/5/25 result remains credible Claude-run evidence. The record names only Python 3.14, not its patch version or executable, so `TPR-CCR4-003` qualifies reproducibility without altering Claude's historical report. No new behavioral defect was introduced. |

### 18.3 Counter-review issue ledger

| ID | Priority | Status | Commit / location | Finding, reason, correction, and verification |
|---|---|---|---|---|
| `TPR-CCR4-001` | P2 | **Closed by current correction** | `5eecce5`; record header/section 8, Action Plan TPR status, Session Handoff TPR pointers, target documentation guard | The current-state surfaces simultaneously said Claude's review was pending and complete, misrouting the next role and leaving a present-tense v2.1-candidate statement in the exact-next-step section. Durable sequencing must have one current truth. The header, explicit section-8 current block, Action Plan, handoff, and guard now identify the completed Claude range through `db6a721`, this Codex counter-review, the empty reviewed-spec registry, and the blocked TPR-1/TPR-0B gates. Historical role-next prose is bounded beneath a non-current heading. |
| `TPR-CCR4-002` | P3 | **Closed by current correction** | `da6f7ea`; `tests/target_price_revisions/test_document_consistency.py` | The new guard's positive-occurrence assertions did not distinguish current from historical text: two of three already passed before the document correction, and a stale labeled artifact could coexist with current values. Its section-8 slice also could not verify `TPR-OOL-001-R1` in section 9 despite the review report saying it did. The guard now parses an explicit current block, requires exact singleton blueprint/candidate identity claims, pins review completion and blocked-next-state text, and separately checks the routing row's full current PDF identity. |
| `TPR-CCR4-003` | P3 | **Closed by qualification** | `db6a721`; sections 17.1/17.8 | Claude's final evidence gives Python 3.14 and pytest 9.1.1 but omits the Python patch version and executable required for exact reproducibility. The counts/duration are retained as credible Claude evidence; this section does not invent the missing metadata. Codex's own final validation records its exact interpreter separately. |
| `TPR-CCR4-004` | P3 | **Closed by qualification** | Section 17.2 versus 17.4; `TPR-CR3-002` | Section 17.2 says `fe056be` carries `TPR-CR3-002`, section 17.4 attributes it to `6b12102`, while Git blame shows the stale `TPR-OOL-001-R1` row was introduced by `ba01e98` and merely remained in later record-touching commits. Section 17 also says one P2 `remains` although its final ledger closes it. Claude's historical report is retained; the exact origin/carry qualification here controls the counter-review disposition. |
| `TPR-CCR4-005` | P3 | **Closed by successor `5eecce5`** | `da6f7ea` exact standalone tree | The guard-first commit is red by construction until its document correction arrives in the next commit. Static evaluation of the exact parent section shows the candidate ID and artifact assertions true and the current blueprint-digest assertion false. The cumulative pushed tree is green, but future correction series should keep each durable commit green or explicitly mark a red-test checkpoint. |
| `TPR-CCR4-006` | P3 | **Closed by final correction** | `0af1ca8`; `docs/SESSION_HANDOFF.md`; target documentation guard | The first correction left a current handoff bullet saying already-pushed v2.2 documentation bytes would receive a future pre-push run, and the cross-document guard checked only positive tokens over whole files. A stale current-state sentence could therefore coexist with the correct state. The handoff now records the completed v2.2 push as history and names the correction range as Claude's next review input; the guard scopes the Action Plan and handoff current blocks, normalizes case and whitespace, and rejects contradictory pending/pre-push language even when Markdown wrapping changes. |

Counter-reviewed round quality: **8/10**. The substantive review and validation
were strong, but the red standalone guard commit, contradictory active state,
positive-only guard, incomplete environment identity, and imprecise historical
attribution required the corrections and qualifications above.

### 18.4 Milestone and authority decision

The exact v2.2 snapshot at `bb8dfb6` has completed the human independent-review
and Codex counter-review loop required by A27 as a zero-access frozen TPR-0A
candidate. That does **not** create a loader-accepted reviewed algorithm
artifact: the reviewed-spec registry remains empty, the candidate remains
unreviewed for its own registry, and the signed-review-identity strengthening
item `TPR-CCR2-011` remains unresolved before any positive authority relies on
reviewer identity.

No implementation follows this counter-review. A22 keeps entitlement,
earliest-public-time semantics, correction completeness, target-horizon
consistency, raw retention, derived processing, and QC-transfer rights
unestablished, so TPR-1 cannot start. TPR-0B additionally waits for reviewed
TPR-1 and TPR-2 zero-outcome structural manifests. The Action Plan schedules
no bypass or alternate milestone. Provider accesses: **0**. Outcome accesses:
**0**. Authorized or spent research looks: **0**. The reviewed, source, and
look authority surfaces remain empty or zero-access.

### 18.5 Validation

Codex used
`C:\git\customizedagent\trading_agent\.venv\Scripts\python.exe`, Python
3.12.13 and pytest 9.1.1. The complete Target-Price Revisions plus shared
active-document suite passed with **189 passed, 3 skipped in 14.54 seconds**.
The narrower two-document-module run passed with **76 passed in 1.22 seconds**.
An in-memory reverse mutation that retained the current candidate while adding
a second stale labeled candidate was rejected by the exact-singleton guard.
After the final `TPR-CCR4-006` whitespace-normalized current-block correction,
the exact pre-commit suite again passed with **189 passed, 3 skipped in 13.20
seconds**. The preceding two-document-module pass was **76 passed in 3.71
seconds**. A read-only mutation reintroducing the original capitalized and
line-wrapped stale handoff sentence was rejected.

The network-restricted full suite completed with **5,838 passed, 5 failed, 5
skipped, and 26 warnings in 1,282.03 seconds**. All five failures were test-
harness effects of that deliberately isolated run: four temporary Git fixture
paths exceeded Windows path handling under the long sandbox-owned base path,
and one temporary Git subprocess was denied by the sandbox. The exact five
nodes then passed with a short outside-repository base path (**5 passed in
11.05 seconds**). Thus all 5,843 collected passing-test nodes are covered, but
this record does not misstate the first run as a single green full-suite run.

Full `compileall -q` including `research` exited 0. `git diff --check` is clean.
The first focused attempt without an explicit writable base directory failed
only at pytest setup with host-temp permission errors; a repository-local base
was also rejected for changing the intended outside-repository premise of one
Git-boundary test. Both environment deviations were corrected before the
results above. Provider accesses: **0**. Outcome accesses: **0**. Authorized or
spent research looks: **0**.

## 19. Claude independent review - 2026-08-30 (counter-review correction range)

**Disposition: both commits accepted.** Codex's counter-review of the v2.2
Claude round is substantively correct, and its two historical claims reproduce
exactly rather than merely reading plausibly. The hardened guard is real: four
independent mutations turn it red and byte-identical restores return it green.

The round nevertheless shipped a tree that fails three of its own tests on the
lane's registered worktree, because the reviewed-algorithm anchor compares
working bytes against Git blobs while Git for Windows translates newlines by
default. That P1 is corrected here. A separate P2 is left open because it
cannot be resolved without the owner: the lane pins an absolute worktree
directory that does not exist on this machine.

### 19.1 Exact reviewed snapshot

| Item | Value |
|---|---|
| Branch | `codex/strategy-target-price-revisions` |
| Worktree used for this review | `C:\git\customizedAgent\trading_agent_TargetPriceRevision` (see `TPR-CR4-002`) |
| Previously reviewed Claude head | `db6a721d45eb47e1a133744387bf43a1aa1f310c` |
| Codex range reviewed | `db6a721d45eb47e1a133744387bf43a1aa1f310c..c8c74704bb9bbda5a756d90afa33666371125a89` |
| Codex commits, ordered | `0af1ca8c9165841373262bff4d173edc48aa1a74`, `c8c74704bb9bbda5a756d90afa33666371125a89` |
| Local head at review start | `c8c74704bb9bbda5a756d90afa33666371125a89`, fast-forward only, clean tree |
| Ancestry check | `70c4b9f` is an ancestor of the fetched head; no published history was rewritten |
| Interpreter | `C:\git\customizedAgent\trading_agent\.venv\Scripts\python.exe`, Python 3.13.14, pytest 9.1.1 |
| Checkout newline configuration | `core.autocrlf=true`, inherited from Git's system config (see `TPR-CR4-001`) |

### 19.2 Commit-by-commit dispositions

| Codex commit | Disposition | Review basis |
|---|---|---|
| `0af1ca8c9165841373262bff4d173edc48aa1a74` | **Accepted** | The single-current-truth correction is right, and the guard hardening it claims is verified rather than assumed. Reintroducing a second labeled candidate spec ID, a second labeled blueprint digest, or the stale pre-push handoff sentence, and dropping the reviewed Claude head from the Action Plan current block, each turn `test_exact_next_step_names_the_current_artifacts` red, and byte-identical restores return it green. Residual scope is recorded as `TPR-CR4-004`. |
| `c8c74704bb9bbda5a756d90afa33666371125a89` | **Accepted** | The `TPR-CCR4-006` handoff correction removes the last stale pre-push claim, and the whitespace-normalized current-block scoping does what it says: the mutation that reintroduces the original capitalized, line-wrapped sentence is rejected. The record-only diff is clean and adds no authority. |

### 19.3 Reproduced Codex claims

Both historical claims were re-derived from the repository rather than accepted
from the report.

- `TPR-CCR4-004` attributes the stale `TPR-OOL-001-R1` row to `ba01e98`, not to
  `fe056be` or `6b12102`. A pickaxe search of that string over the record
  returns `ba01e98`, `5eecce5`, and `0af1ca8`, so `ba01e98` is the introducing
  commit. **Confirmed.**
- `TPR-CCR4-005` says the guard-first commit `da6f7ea` is red standalone, with
  the candidate ID and artifact assertions already passing and the blueprint
  digest assertion failing. Checking `da6f7ea` out in a throwaway clone
  reproduces exactly that: the run fails on
  `section 8 must name the current blueprint digest`, and a direct read of that
  commit's section 8 shows the candidate ID present, the artifact digest
  present, and the blueprint digest absent. **Confirmed.**

### 19.4 Issue ledger

| ID | Priority | Status | Location | Finding, evidence, and disposition |
|---|---|---|---|---|
| `TPR-CR4-001` | P1 | **Closed by correction** | `research/target_price_revisions/` policy code; `POLICY_CODE_REPO_PATHS` in `research/target_price_revisions/preregistration.py:71-78`; `_review_anchor` | `_review_anchor` requires the working bytes of every policy-code path to equal the reviewed and HEAD blobs. Git for Windows sets `core.autocrlf=true` in its system config, which this host inherits, so five of the six policy paths were checked out with CRLF against LF blobs and the loader refused unconditionally. At the reviewed tip `c8c7470`, `tests/target_price_revisions` plus the shared active-document module reported **186 passed, 3 failed, 3 skipped**, all three failures raising `current policy code differs from the independently reviewed map`. The mechanism was proven, not inferred: a `core.autocrlf=false` clone of the same commit ran `test_preregistration.py` **83 passed, 2 skipped**. The refusal direction is safe, but the reviewed-algorithm authority is unreachable on the supported platform, and a later `git add` of a translated working copy would have rewritten the very bytes the frozen candidate's `policy_code_sha256` map pins. Corrected with a lane-scoped `research/target_price_revisions/.gitattributes` declaring `* -text`, a working-tree refresh so all six paths are byte-identical to their blobs, and the new guard `test_policy_code_is_checked_out_as_exact_bytes`. The fix pins exact bytes; it does not relax the byte-identity control. |
| `TPR-CR4-002` | P2 | **Closed by owner direction; see section 20** | Record header and section 7, `docs/ACTION_PLAN_2026-08-20.md`, `docs/SESSION_HANDOFF.md`, `test_lane_documents_agree_on_one_worktree` | Every lane resume pointer names `C:\git\customizedagent\trading_agent_target_price`, and the guard additionally forbids the two coordination documents from naming `trading_agent_TargetPriceRevision` at all. On this machine that is inverted. `git worktree list` registers the lane branch at `C:/git/customizedAgent/trading_agent_TargetPriceRevision`; the common repository holds `.git/worktrees/trading_agent_TargetPriceRevision`; that worktree's `.git` file points back to it; six worktrees are registered, not the five `TPR-CR1-005` reports; and no case form of `trading_agent_target_price` exists under `C:/git/customizedAgent/` even though the filesystem resolves the other names case-insensitively. The owner's own session instruction also named the `TargetPriceRevision` directory. Deliberately not fixed: a single hard-coded absolute path cannot be true on two machines, so flipping the literal would only move the breakage. The owner should say which host is canonical, or direct that the pointer stop being a machine-specific literal. Until then the durable resume instruction points at nothing on this host. |
| `TPR-CR4-003` | P3 | **Closed by qualification** | Section 18.5 | Codex records **189 passed, 3 skipped** for the target plus active-document suite on the exact tree this round pushed. That does not reproduce on the lane's registered worktree, where the same commit and pytest version give **186 passed, 3 failed, 3 skipped**. The cause is `TPR-CR4-001`, so this qualifies the environment rather than the arithmetic: Codex's numbers are consistent with a checkout that does not translate newlines. Validation records in this lane should name the checkout's newline configuration alongside the interpreter, because that setting alone decides whether the reviewed-algorithm tests can pass. |
| `TPR-CR4-004` | P3 | **Closed by qualification** | `tests/target_price_revisions/test_document_consistency.py`, `test_exact_next_step_names_the_current_artifacts` | The hardened singleton assertions are label-bound. They reject a second digest introduced under the same `raw SHA-256`, `spec ID`, `semantic hash`, or `artifact SHA-256` label, which is the realistic drift, but a superseded digest written under a different label inside the current block still passes: a probe inserting a superseded digest as `SHA-256` rather than `raw SHA-256` left the guard green. This is a scope statement, not a defect claim; the guard does close the failure mode `TPR-CCR4-002` names. Widening it to every 64-hex literal in the current block would be the next strengthening if the owner wants it. |

### 19.5 Validation

All runs used the interpreter in section 19.1 on this worktree.

- Reviewed tip `c8c7470`, before correction: `tests/target_price_revisions`
  plus `tests/test_active_document_consistency.py` gave **186 passed, 3 failed,
  3 skipped in 91.60s**.
- Same commit in a `core.autocrlf=false` throwaway clone:
  `tests/target_price_revisions/test_preregistration.py` gave **83 passed, 2
  skipped in 25.49s**, isolating the cause to checkout newline translation.
- After the correction: `tests/target_price_revisions` gave **120 passed, 3
  skipped in 32.26s**, with the three anchor tests green.
- Mutations on Codex's hardened guard, each applied and reverted with a
  byte-identical restore: a second labeled candidate spec ID, a second labeled
  blueprint digest, the reintroduced stale pre-push handoff sentence, and a
  dropped reviewed Claude head in the Action Plan current block all turned it
  **red**; the baseline and every restore were **green**. A superseded digest
  under a different label stayed green and is recorded as `TPR-CR4-004`.
- Mutations on the new guard: fully removing
  `research/target_price_revisions/.gitattributes` turned it **red**, and a CRLF
  working copy of `canonical.py` turned it **red**; both restores returned
  **green**. Deleting that file while leaving it staged did not turn it red,
  because `git check-attr` resolves attributes from the index; the guard
  therefore detects a committed removal and a translated checkout, which are the
  states that actually reach another machine.
- Complete suite on the exact final tree: **5,844 passed, 5 skipped, 0 failed,
  25 warnings in 2,186.28s**. That is the 5,843 baseline plus exactly the one
  guard added here, with skips unchanged, and it includes the three
  reviewed-algorithm anchor tests that were red at the reviewed tip.
- `compileall -q` over `assistant backtest data execution ml research risk
  scripts signals strategies tests baskets.py config.py market_analytics.py`
  exited 0, and `git diff --check` is clean.

No provider, credential, licensed row, outcome, evidence-epoch, QuantConnect,
broker, operator-database, scheduler, paper or live surface was accessed or
changed. Provider accesses: **0**. Outcome accesses: **0**. Authorized or spent
research looks: **0**. No registry, source-authority, or look-authority artifact
was modified, and no milestone was implemented.

## 20. Owner-directed worktree resolution - 2026-08-30

**Owner direction: use `git worktree list` instead of a hardcoded path.**
This closes `TPR-CR4-002`. The finding's evidence in section 19.4 is
unchanged; only its status cell moved to closed, so the record keeps one
current truth without deleting how the defect was found.

### 20.1 What was wrong with pinning a path

Three lane documents named one absolute directory as the worktree, and the
guard both required that literal and forbade the alternative spelling. The
lane is developed from more than one host, so the pin was wrong on every host
except the one that wrote it, and the guard enforced the wrong name here
rather than catching it. Flipping the literal would have moved the same
breakage onto the other host.

### 20.2 What the documents and guard do now

- The Action Plan, Session Handoff, and record preamble name no directory.
  They say the lane worktree is the checkout `git worktree list` registers
  for `codex/strategy-target-price-revisions`.
- `test_lane_documents_resolve_the_worktree_from_git` replaces
  `test_lane_documents_agree_on_one_worktree`. It requires the resolution
  instruction in all three lane documents, rejects any `trading_agent_*`
  directory name in the two coordination documents and in the record's
  preamble, and then checks that the instruction actually resolves: it parses
  `git worktree list --porcelain`, requires the registered directory to exist,
  and requires it to be this checkout whenever `HEAD` is on the lane branch.
- The record may still name past directories below its preamble, because
  `TPR-CR1-005`, `TPR-CCR1-006`, section 18.1, and section 19 are historical
  evidence rather than resume pointers.
- The old guard's anti-drift intent is preserved and widened. `TPR-CR2-003`
  asked that a second worktree spelling never sit unnoticed beside the first;
  the rule is now that no spelling may appear in a current-state surface at
  all, which fails on every host instead of all but one.

### 20.3 Residual limits

The registered-directory check is skipped when the lane branch is not checked
out anywhere in the repository, which is the case when a historical commit is
reviewed in a detached probe clone. The document assertions still run there,
so the machine-independent half of the invariant is never skipped. The
governing PDF still names the old directory on its physical pages; that
remains `TPR-CCR1-006`, unchanged here, because regenerating the artifact
would change its identity and needs the owner's provenance decision.

### 20.4 Validation

- Lane plus shared document suites: **190 passed, 3 skipped**.
- Complete suite on the exact final code tree: **5,844 passed, 5 skipped,
  0 failed, 25 warnings in 2,278.61s**. The count is unchanged from the
  preceding round because the rewritten guard replaces
  `test_lane_documents_agree_on_one_worktree` rather than adding a test. Only
  this validation text and the ledger row follow that run.
- `compileall -q` over the same paths exited 0 and `git diff --check` is clean.
- Mutations, each applied and reverted with a byte-identical restore:
  repinning a directory in the Action Plan, in the Session Handoff, and in the
  record preamble, and removing the resolution instruction from the Action
  Plan, all turned the guard **red**; the baseline and every restore were
  **green**.
- The porcelain parser was exercised directly rather than only through the
  assertions, and resolved the lane branch to this checkout.

No provider, credential, licensed row, outcome, QuantConnect, broker,
operator-database, scheduler, paper or live surface was accessed or changed.
Provider accesses: **0**. Outcome accesses: **0**. Authorized or spent research
looks: **0**. No milestone was implemented and no authority changed.

## 21. Codex counter-review of Claude's CR4 round - 2026-08-31

**Disposition: accepted after correction and qualification.** Codex reviewed
all four Claude commits individually. The newline diagnosis and the owner's
dynamic-worktree resolution are valid, but the cumulative tree did not meet
its ordinary-fast-forward, current-state, or target-only guard claims. Those
defects are corrected here. One pre-existing target authority-anchor defect is
recorded as an open P2 rather than papered over with an invented trust root.
No next implementation milestone is authorized.

Counter-reviewed round quality: **6/10**. The review found a real Windows
compatibility defect and supplied strong full-suite evidence, but its first
fix did not migrate existing worktrees, used backwards Git-clean-filter
reasoning, overreached into sibling text, retained contradictory routing, and
left several report/range inaccuracies.

### 21.1 Exact counter-reviewed snapshot

| Item | Value |
|---|---|
| Branch | `codex/strategy-target-price-revisions` |
| Worktree | The checkout `git worktree list` registers for that branch; no directory is pinned |
| Previously processed Codex head | `c8c74704bb9bbda5a756d90afa33666371125a89` |
| Claude range | `c8c74704bb9bbda5a756d90afa33666371125a89..f21d70851d5e1790be0c308e13e8837a7cd1d008` |
| Claude commits, ordered | `ea9d890beb478f5a881caaef757a8b15e8d5c0db`, `ce74e72b59d759c447f52d5a6c0ec9fff0846f67`, `50da9d07a46bcd0770fc3c9219b3d0a187494383`, `f21d70851d5e1790be0c308e13e8837a7cd1d008` |
| Synchronization | Branch-only fetch; local clean; fast-forward only; remote and local both `f21d708` before correction |
| Governing PDF | 29-page v2.2, raw SHA-256 `f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b` |
| Local review environment | `C:\git\customizedagent\trading_agent\.venv\Scripts\python.exe`; Python 3.12.13; pytest 9.1.1; system `core.autocrlf=true` |

### 21.2 Commit-by-commit dispositions

| Claude commit | Disposition | Counter-review basis |
|---|---|---|
| `ea9d890beb478f5a881caaef757a8b15e8d5c0db` | **Accepted after correction** | Pinning target policy checkout bytes is required and fresh checkouts become exact. An ordinary clean fast-forward from `c8c7470`, however, leaves the unchanged CRLF policy files in place, so the new guard remains red. `* -text` also makes a later CRLF add persist raw CRLF rather than protecting the LF blob. `TPR-CCR5-001` replaces it with LF text normalization, changes each affected policy blob once, and compares working bytes directly with HEAD. |
| `ce74e72b59d759c447f52d5a6c0ec9fff0846f67` | **Accepted after correction and qualification** | The two Codex commits in `db6a721..c8c7470` are reasonably accepted and the commit is record-only/zero-authority. At this standalone commit, the record says review is complete while the Action Plan and handoff still route it as next; successor `50da9d0` closes that P2. The P1 label, mutation count, affected-file count, Git-add rationale, correction identity, and missing quality score need the qualifications in `TPR-CCR5-005`. |
| `50da9d07a46bcd0770fc3c9219b3d0a187494383` | **Accepted after correction and qualification** | Moving the current coordination surfaces to completed-review state is correct. Its `0af1ca8..c8c7470` two-commit notation excludes `0af1ca8` under Git semantics; `db6a721..c8c7470` is exact. `TPR-CCR5-006` corrects current handoff text and preserves the historical row with an explicit qualification. |
| `f21d70851d5e1790be0c308e13e8837a7cd1d008` | **Accepted after correction** | Resolving the lane with Git rather than a host-specific directory follows the owner direction and works in this checkout. The guard scans entire shared documents and rejects legitimate sibling worktree names, skips resolution entirely when an active lane returns no registration, and accepts a record whose current preamble lost the instruction because historical section 20 still contains it. It also leaves section 8 routing the already-reviewed prior range back to Claude. `TPR-CCR5-002`, `003`, and `007` close those defects. |

### 21.3 Counter-review issue ledger

| ID | Priority | Status | Commit / location | Finding, reason, correction, and verification |
|---|---|---|---|---|
| `TPR-CCR5-001` | P2 | **Closed by current correction** | `ea9d890`; lane `.gitattributes`, five nonempty `POLICY_CODE_REPO_PATHS`, target document guard | The attributes-only change repairs a fresh checkout but does not rewrite unchanged CRLF files during the lane monitor's required clean fast-forward. That leaves the reviewed-authority path fail-closed and the new guard red. The `-text` blob-protection rationale is also backwards: normal text cleaning maps CRLF back to LF, while `-text` can persist raw CRLF. The lane now uses `text eol=lf`; all five nonempty policy blobs carry a no-behavior migration marker so a fast-forward must rewrite them; the shared empty file is untouched; and the guard freezes an independent expected inventory, compares every working file with `git show HEAD:<path>`, and checks `text=set, eol=lf`. Candidate, reviewed-registry, source-authority, and look-authority JSON bytes are unchanged. |
| `TPR-CCR5-002` | P2 | **Closed by current correction** | `f21d708`; record section 8 and current coordination blocks | Section 8 says the prior correction goes to Claude immediately before saying Claude already reviewed it. That is incorrect durable state and misroutes the next role. All current blocks now identify the complete `c8c7470..f21d708` Claude range, this Codex counter-review, the blocked milestone, and the new post-push Claude step. The guard rejects the stale phrase that previously evaded it. |
| `TPR-CCR5-003` | P2 | **Closed by current correction** | `f21d708`; `test_lane_documents_resolve_the_worktree_from_git` | The target-owned guard searches the entire shared Action Plan and Session Handoff for every `trading_agent_*` name. A legitimate sibling-lane pointer therefore turns the TPR guard red, violating the lane boundary. It now scopes assertions to the Action Plan's current target block, handoff section 0, and record preamble; only those target surfaces must omit pinned directories. |
| `TPR-CCR5-004` | P2 | **Open; owner-approved trust-root design required before positive authority** | Pre-existing `_review_anchor`; `POLICY_CODE_REPO_PATHS` and the reviewed registry map | The loader's policy inventory is defined by the same mutable code it is meant to anchor. A controlled fixture removed `preregistration.py` itself plus `canonical.py` from that tuple and from a matching registry map; later changes to both omitted files still allowed `load_reviewed_algorithm_spec` to return reviewed authority. The current registry is empty, so no present authority is minted and all source/outcome/look gates remain closed. A separately frozen immutable inventory, signed manifest, or equivalent external trust root must be designed and independently reviewed before any positive registry entry; inventing that authority design is outside this blocked counter-review round. |
| `TPR-CCR5-005` | P3 | **Closed by correction and qualification** | `ea9d890` / `ce74e72`; section 19 and current header | `TPR-CR4-001` is a P2 meaningful fail-closed compatibility defect under the binding severity table, not P1 unsafe execution. Five of six policy files differed, not every file. The report's hardened-guard evidence contains four red mutations plus one deliberately green limitation, not five red mutations; it has two P3 qualifications, not one; and it omits correction commit `ea9d890` and the required quality rating. Historical text is retained; this section supplies the controlling classification, exact counts, correction identity, and rating. |
| `TPR-CCR5-006` | P3 | **Closed by current correction/qualification** | `50da9d0`; current handoff and appended session row | Git ranges exclude the left endpoint. `0af1ca8..c8c7470` denotes only `c8c7470`, and `ea9d890..f21d708` omits `ea9d890`. Current text uses `db6a721..c8c7470` for the two Codex commits and `c8c7470..f21d708` for all four Claude commits. The earlier append-only session row remains as historical evidence and is explicitly qualified here. |
| `TPR-CCR5-007` | P3 | **Closed by current correction** | `f21d708`; worktree-resolution guard | The guard passes when the active lane branch has no registered worktree, and it searches the whole record for the resolution phrase so historical section 20 can mask a missing current instruction. It now requires a non-null registration whenever HEAD is the lane branch and scopes the record wording to its current preamble. Detached historical probes may still lack a registered lane, but all document assertions continue to run. |

### 21.4 Authority and milestone decision

The sole-authority PDF and TPR-0A candidate artifact are unchanged. The policy
comments and Git attributes change only checkout/anchor mechanics and remain
pending Claude review after this round's one push. The reviewed-spec registry
is empty; source and permanent-look authority artifacts remain exact zero-
access declarations; the candidate remains unreviewed for its own registry;
and no permanent look is authorized or spent. `TPR-CCR5-004` is an additional
gate before positive reviewed-algorithm authority, not permission to build or
populate a registry.

TPR-1 is still blocked on a separately reviewed exact source-rights artifact,
and TPR-0B still waits for reviewed TPR-1/TPR-2 structural manifests. No
provider, credential, licensed row, source sample, outcome, research look,
QuantConnect upload/compile/job, broker, operator database, scheduler, shadow,
paper, live, deployment, capital, or trading authority was accessed or added.
No next implementation milestone was implemented.

### 21.5 Baseline and correction verification

- Exact synchronized `f21d708` baseline: target-price plus active-document
  suites **190 passed, 3 skipped in 14.08s** on the interpreter in section
  21.1.
- Git-range proofs: `db6a721..c8c7470` returns the two intended Codex commits;
  `c8c7470..f21d708` returns all four intended Claude commits. The shorter
  left-endpoint forms omit their first named commit.
- Before correction, an active-lane/no-registration function probe passed the
  worktree test, and the whole-document regex selected a hypothetical
  `trading_agent_insider` sibling pointer. Both are refused or ignored in the
  correct target-scoped direction after correction.
- Final focused/full validation and exact committed-tree evidence follow in
  the append-only session row and section 21.6.

### 21.6 Final validation

- Correction commit: `943edf77ca61cae475e4986b985baab3097adfbc`.
- Target-price plus active-document suites on that exact commit: **190 passed,
  3 skipped in 13.88s**.
- Network-restricted complete suite on that exact commit: **5,844 passed, 5
  skipped, 0 failed, 26 warnings in 1,030.57s**. The warning difference from
  Claude's 25-warning run is environment output, not a test or behavior count.
- Full `compileall -q` over `assistant backtest data execution ml research risk
  scripts signals strategies tests baskets.py config.py market_analytics.py`
  exited 0.
- A real working-byte mutation in `canonical.py` turned the exact-byte guard
  red; the byte-identical restore returned it green. Function probes proved
  that an active lane with no registered worktree and a missing resolution
  instruction in the current record preamble are refused, while a sibling
  worktree name outside the Action Plan's target block is ignored.
- All six policy paths matched their HEAD blobs after restore. The five
  nonempty target policy paths resolve `text=set, eol=lf`; shared empty
  `research/__init__.py` remains byte-empty and outside the lane attribute.
- PDF raw SHA-256 remains
  `f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`;
  candidate raw SHA-256 remains
  `17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a`.
  Reviewed registry, source authority, and look authority artifacts have no
  diff and remain empty/zero-access.
- Final record-only successor: target and active-document guards **77 passed**;
  `git diff --check` and clean status verification complete before
  the one push.

The full suite ran without external network permission and no provider,
credential, licensed row, source sample, outcome, QuantConnect, broker,
operator-database, scheduler, paper, live, deployment, or capital surface was
accessed. Authorized or spent research looks: **0**. No authority changed.

## 22. Claude independent review - 2026-08-31 (two counter-reviews, CR4 round, and main synchronization)

**Disposition: all eight commits accepted or accepted after correction.** No P0
or P1 exists. There is **no new implementation milestone in this range** —
section 21.4 states none was implemented, and that is accurate. The range is
two Codex counter-reviews, one Claude round run on another machine, and its
correction.

### 22.1 Exact reviewed snapshot

| Item | Value |
|---|---|
| Reviewed range | `db6a721..3f33eea` (eight commits) |
| Review head at start | `3f33eea09aedbb8c386ebc355a6c875b76c80f83` |
| Ancestry | `db6a721` is still an ancestor; no history rewrite |
| Synchronization | Fast-forwarded to integrated `origin/main` `cf136e259cf628aabdc4220865fccdb5c7204306`; merge-base equalled the lane head, so no merge commit and no conflicts |
| Integration | All four strategy lanes merged into `main` (PRs #321, #322, #323, #325) |
| Environment | Windows 11; `python` 3.14.6; pytest 9.1.1; system `core.autocrlf=true` |

### 22.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `0af1ca8c` | **accepted** | Codex counter-review of the prior Claude round. Its three findings against that round are valid; see 22.3. |
| `c8c74704` | **accepted** | Blocked-round handoff. Record-only, zero authority. No issue found. |
| `ea9d890b` | **accepted after correction** | The Windows anchor diagnosis was right and the defect real, but `* -text` does not rewrite unchanged CRLF files during an ordinary fast-forward. `TPR-CCR5-001` correctly replaced it; the final state is verified working in 22.5. |
| `ce74e72b` | **accepted after correction** | CR4 review record; qualified by `TPR-CCR5-005` on severity, counts and correction identity. |
| `50da9d07` | **accepted after correction** | Current-state routing; range notation corrected by `TPR-CCR5-006`. |
| `f21d7085` | **accepted after correction** | Resolving the worktree from `git worktree list` follows the owner's direction, but the guard scanned entire shared documents and rejected legitimate sibling names. `TPR-CCR5-002`/`003`/`007` close it. |
| `943edf77` | **accepted** | Codex CR5 counter-review and corrections. Independently verified in 22.5, including the anchor fix and the open `TPR-CCR5-004`. |
| `3f33eea0` | **accepted** | CR5 validation record. No issue found. |

The cumulative tree carries `TPR-CR5-001`, which no single commit in this range
introduced: it became false when the four lanes were merged.

### 22.3 Codex findings against the prior Claude round: all accepted

All three are confirmed, and two are repeats of classes that round had already
been corrected on.

| Finding | Assessment |
|---|---|
| `TPR-CCR4-002` | **Confirmed, including the part that is a verification error rather than a code defect.** The section-8 guard sliced only section 8, so it could not verify the section-9 routing row — yet the review report's `TPR-CR3-002` line claimed that row was "covered by the same guard". Claiming coverage a test does not provide is worse than the missing coverage itself, because it stops anyone looking again. |
| `TPR-CCR4-005` | **Confirmed, and a repeat.** The guard was committed before the document correction, so `da6f7ea` is red as a standalone object. The identical ordering mistake was made in the first round at `0f05f3d` and accepted then. Knowing the rule and repeating it is worse than not knowing it; documents first, then the guard. |
| `TPR-CCR4-001` | **Confirmed, and also a repeat in kind.** The final tree said "pending Claude review" in the header, section 8, Action Plan and handoff while section 17 said the review was complete. That is precisely the current-state-consistency defect that round had just reported in someone else's work. |
| `TPR-CCR4-003` | **Confirmed.** "Python 3.14" without the patch version or executable is not reproducible metadata. This section records `3.14.6`. |

### 22.4 P0-P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|
| `TPR-CR5-001` | P2 | Closed | Section 15.4; record and handoff current-state blocks | Section 15.4 routes the shared multiplicity propagation on the premise that the lanes are "separate long-lived branches" and that "this branch is deliberately unmerged". All four lanes are now merged into `main`, so the premise is false and the routing understates what is possible: the four lane records now sit in one tree, where the amendment can be prepared as one coordinated change instead of four isolated branch rounds. The required per-lane review and counter-review are unaffected. | `git merge-base --is-ancestor` confirms `main` contains the lane; PRs #321, #322, #323 and #325 are all present in `origin/main`. | A routing instruction an owner reads to schedule cross-lane work must not rest on a branch topology that no longer exists. | The historical text is retained unaltered beneath an explicit supersession note; the record's section 8 and the handoff now carry the integration and synchronization state. | New guard `test_current_state_blocks_do_not_call_the_lane_unmerged`. Three mutations — the stale phrase in section 8, in the handoff, and the supersession marker stripped from 15.4 — each turn it red; restore returns it green with text identical. |

### 22.5 Verified rather than accepted

- **The anchor fix works.** All five nonempty `POLICY_CODE_REPO_PATHS` files
  have working bytes identical to their committed blobs on this Windows host
  with `core.autocrlf=true`. The `* text eol=lf` replacement plus the one-time
  blob touch was the correct remedy, and Codex's reasoning that `-text` can
  persist raw CRLF rather than protect the LF blob is empirically right — see
  `TPR-OOL-008`, where the sibling lane's `-text`-only strategy failed on this
  host in exactly that way.
- **`TPR-CCR5-004` is real and I reproduced its mechanism.**
  `POLICY_CODE_REPO_PATHS` is defined inside `preregistration.py`, and that
  module is itself in the inventory it defines, so the anchor can prove only
  *working tree equals HEAD* — never that the inventory was not reduced in the
  same commit. Recording it as open, and refusing to invent a trust root
  inside a blocked round, are both the right calls.
- **It is currently inert.** Adversarial probe: the reviewed registry has zero
  entries, `load_reviewed_algorithm_spec` refuses with "outcome access requires
  an independently reviewed algorithm parent", and `authorize_outcome_access`
  refuses the candidate. No positive authority exists or can be minted today.
- **The synchronization is a true fast-forward.** The merge-base equalled the
  lane head, so `main` already contained every lane commit; no merge commit and
  no conflict resolution were involved, and nothing in the lane's history was
  rewritten.
- **The sibling multiplicity state is measured, not assumed.** See
  `TPR-OOL-006`.

### 22.6 Scope not exhaustively audited

- The 168 commits this lane inherited from the other three lanes were **not**
  reviewed. They arrived through their own lane reviews and owner merges; this
  review covers the eight target-lane commits and the integrated tree's effect
  on target-lane claims.
- The estimator, power and statistical binding procedures were again read for
  contract shape only, not re-derived.
- No provider, endpoint, entitlement or licensed row was touched.

### 22.7 Authority state after this review

Unchanged and zero. No provider, credential, licensed row, outcome, evidence
epoch, QuantConnect project, broker, operator database, scheduler, paper or
live surface was accessed, and **0 research looks** were spent. The reviewed
registry remains empty. No milestone was implemented and none is authorized;
TPR-1 remains blocked on source rights and TPR-0B on reviewed TPR-1/TPR-2
manifests.

### 22.8 Final validation on the corrected tree

Recorded as a separate appended event rather than by amending 22.5, per
`TPR-CCR3-006`.

Complete suite on the exact committed tree `0e911189`: **6,791 passed, 13
skipped, 0 failed, 25 warnings in 4,093.39s**. The duration reflects host load,
not the tree; the earlier baseline of the same suite took 1,314.44s.

The count reconciles exactly against the baseline. The synchronized baseline
was 6,789 passed, 13 skipped and 1 failed, so 6,803 collected; the final tree
is 6,791 passed and 13 skipped, so 6,804 collected. Passed rose by two: the
analyst-lane checkout guard flipped from failed to passed once its stale
working-tree bytes were restored from their committed blobs, and this round
added exactly one new guard. Skips are unchanged.

Full `compileall -q` including `research` exited 0, `git diff --check` was
clean, and the lane plus shared documentation suites passed with **191 passed,
3 skipped**. Python 3.14.6, pytest 9.1.1. The two review commits touch only
lane-owned files; `git diff` against the merge point over
`research/analyst_revisions_v2`, `research/ml_specs` and
`research/short_interest_etf` is empty, so no sibling-lane content was
committed.

## 23. Codex counter-review - 2026-08-31 (Claude integration-review round)

### 23.1 Exact range and commit dispositions

The synchronized, clean baseline was
`cd23f7c8ea893f40b601d4ea791e1d9a14a72e7a`. The exact Claude range is
`cf136e259cf628aabdc4220865fccdb5c7204306..cd23f7c8ea893f40b601d4ea791e1d9a14a72e7a`:
exactly three commits. The much earlier `3f33eea..cd23f7c8` range is not the
review range because it includes the integrated sibling/main history. Codex
reviewed each Claude commit individually under the standing process.

| Commit | Disposition | Basis |
|---|---|---|
| `d9c4a450` | **Accepted after correction** | A guard against stale unmerged-lane claims is useful, but this guard-first commit is red by itself and its claimed current-state scope is broader and weaker than implemented. `TPR-CCR6-003` and `TPR-CCR6-004` control. |
| `0e911189` | **Accepted after correction** | The eight-commit review and integration evidence are substantively useful, but active role/head pointers remained at `f21d708`, and section 22.4 inferred cross-lane edit routing that the owner did not grant. `TPR-CCR6-001` and `TPR-CCR6-002` control. |
| `cd23f7c8` | **Accepted after correction** | The reported validation arithmetic is internally consistent. The cumulative tree retains the two P2s, omits the required quality rating, and inaccurately calls the shared handoff lane-owned. `TPR-CCR6-001`, `002`, `005`, and `006` control. |

No P0 or P1 exists. The 168 inherited integration commits are not part of this
three-commit review. The combined Claude diff changes only the target document
guard, this target record, and the shared root Session Handoff; it changes no
PDF, candidate, target production code, authority JSON, or sibling strategy
artifact.

### 23.2 P0-P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Concrete reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `TPR-CCR6-001` | P2 | **Closed by current correction** | `0e911189`; cumulative `cd23f7c8` | Record preamble/section 8; Action Plan current block/row; Session Handoff current bullet/summary; document guard | Section 22 completed the latest review, but every active pointer still pinned `f21d708`, described the preceding four-commit counter-review, and routed Claude next. A resuming agent would review the wrong range or skip this counter-review. | Exact diff inspection shows section 22 appended while those pointers and `LATEST_CLAUDE_REVIEW_HEAD` remained unchanged. The as-received document guard passed **9 tests** despite that contradiction. | Current coordination state is a safety boundary in the same-branch loop; the wrong role/head can cause a review to be missed or repeated. This repeats the class section 22 itself criticizes. | All six active surfaces now identify the directed `cf136e25..cd23f7c8` Claude range, section 23, this counter-review, and the post-push range beginning after `cd23f7c8`. The guard binds the exact full range in detailed blocks, the exact short range in summary pointers, and rejects both forms of `f21d708`. | The final document-consistency module and 191-test lane/shared-document suite pass; exact full/short directed-range assertions cover every corrected active pointer. Full-suite/compile evidence is appended below. |
| `TPR-CCR6-002` | P2 | **Closed by controlling qualification and current routing** | `0e911189` | Section 22.4; current record, Action Plan, and handoff | The sentence saying merge permits one coordinated change instead of four isolated branch rounds exceeds owner authority and could route sibling edits through this target branch. | Section 22.4 contains the sentence; the sole-authority PDF page 29 and the standing owner rule require each sibling correction/review on its respective branch. Merge ancestry changes visibility, not edit authority. | Cross-lane mutation without an explicit owner exception would violate the target-only worktree/branch boundary and bypass each sibling's serialized review. | Section 23 rejects and supersedes that sentence. Every active target surface now says sibling-lane changes and their independent reviews remain on their respective branches; no sibling artifact is edited. | The corrected guard requires the branch rule and rejects the unauthorized coordinated-change phrase across the record, Action Plan, and both handoff pointers. `git diff --name-only` contains no sibling strategy artifact. |
| `TPR-CCR6-003` | P3 | **Accepted after successor; qualified** | `d9c4a450` | Guard commit before successor `0e911189` | The guard landed before the section-15.4 supersession marker it requires, so the commit is red as a standalone reviewed object. | `git show d9c4a450` contains the new marker assertion but not the marker; `git show 0e911189` introduces the required document text. This is the same guard-first sequencing class as `TPR-CCR4-005`. | Every reviewed commit should be a coherent snapshot; knowingly red intermediate objects impair bisectability and commit-by-commit review. | History is preserved. The commit is accepted only after its successor and this exact qualification; future document/guard pairs must place prerequisite document state first. | Static per-commit inspection proves the dependency; the cumulative corrected guard passes on the final tree. |
| `TPR-CCR6-004` | P3 | **Closed by current correction** | `d9c4a450` | `test_current_state_blocks_do_not_call_the_lane_unmerged` | The guard claimed current-state scope but scanned whole shared documents and all of section 8, while accepting a section-15.4 marker anywhere in the remaining record. Historical/sibling prose could create false failures and an unrelated later marker could mask loss of the local qualification. | Exact source inspection shows whole-document `_doc(...)` calls, an unsliced section 8, and `propagation.lower()` over the entire tail. | A governance guard that over- and under-scopes its evidence can both block legitimate sibling history and miss the target defect it claims to prevent. | The guard now uses the explicit Action Plan current block/TPR row, handoff current bullet/target summary, record preamble/section-8 current qualification, and the exact section-15.4 subsection. | The final 9-test module and 191-test lane/shared-document suite pass. The exact subsection extraction stops at the next H3 marker and all active routing surfaces are asserted. |
| `TPR-CCR6-005` | P3 | **Closed by controlling qualification** | `0e911189`; confirmed at `cd23f7c8` | Section 22 | Claude's review omits the binding process's honest 1-10 implementation-quality rating, leaving review completion evidence incomplete. | Section 22 contains dispositions, scope, authority, and validation but no numeric quality rating. | The rating is a mandatory review output and gives the owner a concise signal about correction burden and repeat-defect quality. | Section 23.3 supplies Codex's honest **6/10** counter-review rating without rewriting Claude's historical report. | The rating and its concrete rationale are present in the controlling counter-review section. |
| `TPR-CCR6-006` | P3 | **Closed by controlling qualification** | `cd23f7c8` (claim); `0e911189` (shared-file edit) | Section 22.8 | “The two review commits touch only lane-owned files” is inaccurate because the review changes the shared root Session Handoff. It overstates scope even though no sibling artifact changed. | `git show --name-only 0e911189` includes `docs/SESSION_HANDOFF.md`; the three-commit combined diff also includes only that shared pointer plus the target guard/record. | Accurate scope reporting is required to distinguish an authorized coordination pointer from prohibited sibling strategy edits. | Section 23 records the correct scope: target-owned guard/record plus one owner-relevant shared coordination pointer; no sibling strategy artifact. | Current `git diff --name-only` and the reviewed-range diff contain no sibling strategy path; the shared handoff is explicitly named rather than called lane-owned. |

### 23.3 Honest implementation-quality rating

**6/10.** Claude's review is substantive, candid about the unreviewed inherited
history, and backed by a complete-suite result. It nevertheless repeats the P2
current-state consistency class it criticizes, overstates what integration
authorizes across lane boundaries, repeats the guard-first sequencing defect,
mis-scopes the guard, omits the required rating, and overstates lane-only file
scope. The accepted-after-correction disposition reflects that mix.

### 23.4 Authority and milestone decision

The sole-authority 29-page v2.2 PDF and authenticated TPR-0A candidate are
unchanged. The reviewed-spec registry remains empty. Authorized/spent research
looks remain **0**. No provider, credential, licensed row, source sample,
outcome, research look, QuantConnect upload/compile/job, broker, operator
database, scheduler, shadow, paper, live, deployment, capital, or trading
surface was accessed or authorized.

No next implementation milestone is authorized. `TPR-CCR5-004` requires an
exact, separately approved and independently reviewed immutable trust-root
design before positive reviewed-algorithm authority. `TPR-CCR2-011` still
requires separately controlled reviewer-identity trust. TPR-1 remains blocked
on a separately reviewed exact source-rights artifact, and TPR-0B remains
blocked on reviewed TPR-1/TPR-2 structural manifests. `TPR-OOL-006` remains
documented for correction within each sibling lane, not from this branch.

### 23.5 As-received and correction verification

- On the exact clean `cd23f7c8` baseline, the document-consistency module
  passed with **9 passed in 1.81 seconds**. That result confirms the prior guard
  did not detect its own stale role/head surfaces.
- Static commit inspection proves `d9c4a450` requires the section-15.4
  supersession marker introduced only by successor `0e911189`; the first commit
  is therefore red standalone even though the cumulative tree is green.
- On the pre-commit correction tree before the final ledger/guard hardening,
  the document-consistency module passed with **9 passed in 2.07 seconds**. The
  target-price plus shared active-document suite passed with **191 passed, 3
  skipped in 133.96 seconds**. Python 3.12.13 / pytest
  9.1.1. `git diff --check` is clean apart from Git's informational future-EOL
  warnings. The sole-authority PDF still hashes to
  `f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`.
- The complete repository suite and compilation were deliberately deferred
  until the correction commit had an exact identity. Section 23.6 records those
  exact-commit gates rather than attributing them to an uncommitted tree.

### 23.6 Exact committed correction validation and blocked handoff

Correction commit:
`84a6fda1e3e4f32aec4d312a1fe0d706fa13da0d`.
The worktree was clean before both required validation gates.

- Network-restricted complete suite on that exact commit, Python 3.12.13 /
  pytest 9.1.1: **6,791 passed, 13 skipped, 0 failed, 26 warnings in 2,802.47
  seconds (46:42)**. The command used an isolated pytest base temporary
  directory and disabled the repository cache provider.
- Full `python -m compileall -q .`, including `research`, exited **0**. The first
  sandboxed invocation exited 1 solely because the sandbox denied writes to
  existing `__pycache__` directories; the identical command rerun with
  worktree write permission exited 0. No source file changed during either
  invocation.
- `git status --short` was clean after validation, and `git diff --check`
  exited 0. The sole-authority PDF remains byte-identical at raw SHA-256
  `f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b`.
- On the validation-record successor, the document-consistency module passed
  with **9 passed in 1.01 seconds**, and the complete target-price plus shared
  active-document suite passed with **191 passed, 3 skipped in 16.72 seconds**.
  `git diff --check` remained clean apart from Git's informational future-EOL
  warning.

The validation-record successor changes only this lane record. Its focused
documentation guards are green before that record-only commit. No provider,
credential, licensed row, source sample, outcome, research look, QuantConnect
surface, broker, operator database, scheduler, shadow, paper, live, deployment,
capital, or trading authority was accessed or added; authorized/spent looks
remain **0**. No next implementation milestone is authorized. After the one
combined push, Claude reviews exactly the Codex range beginning after
`cd23f7c8` and ending at the new pushed head.

## 24. Claude independent review - 2026-08-31 (Codex counter-review round)

**Disposition: both commits accepted.** No P0, P1 or P2 was found in the
range. One P3 was found in the cumulative tree and corrected. **There is no new
implementation milestone in this range** — `git diff --name-only
cd23f7c8..b4e6b88c` over `research/` is empty, and section 23 says none was
authorized. That is the second consecutive round described on handoff as
containing a milestone that contains none.

**Counter-reviewed round quality: 8/10.** The counter-review is accurate and
specific: six real defects in the prior Claude round, three of them repeats,
each with exact evidence. The guard rework is materially better than what it
replaced — six explicitly scoped current surfaces instead of whole-document
scans, and seven extractors that all fail closed on a missing anchor. Two
deductions: while correcting the current-state blocks it left a stale
present-tense synchronization claim inside those same blocks (`TPR-CR6-001`),
which is the class the round was fixing; and its validation logged 26 warnings
against the 25 this reviewer measures on the same tree without reconciling the
difference.

### 24.1 Exact reviewed snapshot

| Item | Value |
|---|---|
| Reviewed range | `cd23f7c8ea893f40b601d4ea791e1d9a14a72e7a..b4e6b88ccf8a17a60cad91cda94205f61c1b7f90` (two commits) |
| Ancestry | `cd23f7c8` is still an ancestor; no history rewrite |
| `research/` changes in range | none |
| Integration | lane and `origin/main` (`aefa0ecc`) have **diverged**: 2 behind, 5 ahead, neither containing the other |
| Environment | Windows 11; Python 3.14.6; pytest 9.1.1; `core.autocrlf=true` |

The lane was **not** re-synchronized this round. A fast-forward is no longer
possible, and merging `main` would add a merge commit to a review round that
was not asked for; the divergence is two sibling-lane record commits with no
bearing on this review. It is recorded here and in section 8 for the owner to
schedule.

### 24.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `84a6fda1` | **accepted** | Counter-review of the prior Claude round plus guard and pointer corrections. All six findings verified valid; the guard rework verified stronger and fail-closed. |
| `b4e6b88c` | **accepted** | Record-only validation. Its 6,791 passed / 13 skipped / 0 failed is reproduced exactly below; only the warning count differs. |

### 24.3 Codex findings against the prior Claude round: all six accepted

| Finding | Assessment |
|---|---|
| `TPR-CCR6-001` (P2) | **Confirmed.** Section 22 completed the review while every active pointer still named `f21d708` and routed Claude next. This is the same current-state contradiction section 22 criticized in Codex's own work, and the third occurrence for this reviewer. |
| `TPR-CCR6-002` (P2) | **Confirmed.** "One coordinated change instead of four isolated branch rounds" reads as inferring cross-lane edit authority from merge ancestry. The ledger row did carry the per-lane caveat, but the sentence should not have implied it either way; merge changes visibility, not authority. |
| `TPR-CCR6-003` (P3) | **Confirmed, third occurrence.** Guard committed before the document state it asserts, so `d9c4a450` is red standalone — after `0f05f3d` and `da6f7ea`. This round pairs each document change with its guard in one commit instead. |
| `TPR-CCR6-004` (P3) | **Confirmed.** The guard scanned whole shared documents and all of section 8 while accepting the 15.4 marker anywhere in the tail — over- and under-scoped at once, and the same over-broad-scan defect flagged one round earlier in the CR4 guard. |
| `TPR-CCR6-005` (P3) | **Confirmed and verified against the source.** The 1-10 rating is binding at `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md:377`. It has been omitted for several rounds; this section supplies it. |
| `TPR-CCR6-006` (P3) | **Confirmed.** "Touch only lane-owned files" was wrong: `docs/SESSION_HANDOFF.md` is a shared root document. The verification command checked only that no sibling *strategy* content was committed, and the claim then overstated it. |

### 24.4 P0-P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|
| `TPR-CR6-001` | P3 | Closed | Record section 8 and 15.4 note; handoff integration bullet | The current-state blocks stated the lane "is synchronized to the integrated `main`" and "now contains every sibling lane's work". Both were true at the fast-forward and became false when `main` advanced. A reader would believe the lane carries the latest sibling work and that no sync is outstanding. | `git merge-base --is-ancestor` fails in both directions; the lane is 2 behind and 5 ahead of `aefa0ecc`. | The same current-state-truthfulness rule the counter-review had just enforced on the review pointers. The claim also hides an outstanding sync from whoever schedules the next round. | All three surfaces now state the measured divergence with its counts, and the historical statements are marked as accurate at the time rather than deleted. | New guard `test_a_present_tense_sync_claim_matches_real_ancestry`; two mutations, one per surface, each turn it red with a text-identical restore. |

### 24.5 Verified rather than accepted

- **The guard rework is stronger, not merely different.** All seven new
  extractors (`_current_qualification`, `_action_current`, `_action_tpr_row`,
  `_handoff_current`, `_handoff_current_review`, `_handoff_target_summary`,
  `_record_preamble`) raise on a missing anchor rather than returning an empty
  string, so a deleted section fails the guard instead of vacuously passing.
  That was checked explicitly, not assumed from the diff.
- **The pointer guard works against its author.** Advancing the round tripped
  it four separate times on surfaces that had not been advanced — the record
  preamble, the Action Plan TPR row, a handoff line and the handoff summary.
  Each was a genuine stale pointer, and it caught a superseded hash this
  reviewer reintroduced while writing the correction.
- **The baseline is reproduced exactly**: 6,791 passed, 13 skipped, 0 failed in
  1,386.58s against the recorded 6,791/13/0. The warning count differs, 25
  here against 26 recorded, which is not reconciled and is noted rather than
  explained away.
- **The analyst checkout guard stayed green** this round without intervention:
  the `-text` files restored last round persist, though `research/ml_specs`
  remains unprotected and will re-convert. `TPR-OOL-008` is unchanged.

### 24.6 Scope not exhaustively audited

- The new sync guard's `contains_main` early-return branch is **not**
  exercised today, because the lane does not currently contain `main`. It is
  reachable only after a future sync and is stated here rather than counted as
  covered.
- The estimator, power and statistical binding procedures were again read for
  contract shape only.
- The 168 commits inherited from sibling lanes remain unreviewed here.

### 24.7 Authority state after this review

Unchanged and zero. No provider, credential, licensed row, outcome, evidence
epoch, QuantConnect project, broker, operator database, scheduler, paper or
live surface was accessed, and **0 research looks** were spent. The
reviewed-spec registry remains empty and `TPR-CCR5-004` still gates any
positive reviewed-algorithm authority. No milestone was implemented and none
is authorized.

### 24.8 Final validation on the corrected tree

Recorded as a separate appended event rather than by amending 24.5, per
`TPR-CCR3-006`.

Complete suite on the exact committed tree `433b2679`: **6,792 passed, 13
skipped, 0 failed, 25 warnings in 1,178.99s**. That is the 6,791 baseline plus
exactly the one guard added this round, with skips unchanged. Full
`compileall -q` including `research` exited 0, `git diff --check` was clean,
and the lane plus shared documentation suites passed with **192 passed, 3
skipped**. Python 3.14.6, pytest 9.1.1.

Scope of correction commit `433b2679`: the lane-owned guard module and lane
record, plus two shared root coordination pointers (`docs/ACTION_PLAN_2026-08-20.md`
and `docs/SESSION_HANDOFF.md`). Validation-record successor `8078ce48` changes
only this lane record. No sibling strategy artifact was changed.

## 25. Codex counter-review and TPR-TR0 trust-root design freeze - 2026-08-31

**Disposition: both Claude commits accepted after correction.** Codex reviewed
`433b2679108300eeec4e61412aad599e538de873` and
`8078ce4877613adf5f9378cc11258841ac38f76d` individually. Five P3 defects are
corrected or closed by exact verification below. No P0, P1, or P2 was found in
the reviewed range.

**Counter-reviewed round quality: 7/10.** Claude's review correctly accepted
the preceding Codex fixes, added a useful ancestry-sensitive guard, and supplied
credible full-suite evidence. Deductions are for retaining one stale current
sync claim, using a self-invalidating current topology count, overstating four
extractors' missing-anchor behavior, misdescribing a two-commit round as one
commit, and omitting validation after its record-only successor.

### 25.1 Exact reviewed snapshot and commit dispositions

| Item | Value |
|---|---|
| Fetched remote head | `8078ce4877613adf5f9378cc11258841ac38f76d` |
| Reviewed range | `b4e6b88ccf8a17a60cad91cda94205f61c1b7f90..8078ce4877613adf5f9378cc11258841ac38f76d` |
| Worktree | clean, named branch `codex/strategy-target-price-revisions`, remote and local tips identical before review |
| `433b2679` | **Accepted after correction.** The prior findings and substantive sync diagnosis are valid; `TPR-CCR7-001` through `003` correct its remaining current-state and guard defects. |
| `8078ce48` | **Accepted after correction.** Its validation totals reconcile and its scope is record-only; `TPR-CCR7-004` and `005` correct its round-count and final-tree-evidence defects. |

### 25.2 P0-P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `TPR-CCR7-001` | P3 | **Closed by current correction** | `433b2679` | Record section 8; ancestry guard | The correction left a present-tense statement that the lane "now contains every sibling lane's work", but the lane and `origin/main` had already diverged. The new guard excluded that paragraph and inspected checkout `HEAD` rather than the named lane ref. | Exact section extraction shows the stale paragraph immediately before the guard's start anchor. Both ancestry directions fail for the named lane and `origin/main`. | A current coordination block must not claim ancestry it does not have, and a lane guard must inspect the lane it governs rather than whichever checkout invokes it. | Section 8 now states the historical fast-forward and current divergence without a present-tense containment claim. The guard includes the integration block and resolves the named local or remote lane ref. | The strengthened focused test failed red on the as-received documents and passes after correction; exact results are recorded in 25.6. |
| `TPR-CCR7-002` | P3 | **Closed by current correction** | `433b2679` | Record preamble/section 8; Action Plan current block; Session Handoff target blocks | The live `2 behind, 5 ahead` count described reviewed parent `b4e6b88c`, not correction commit `433b2679`; each new lane commit made the count stale again. | `git rev-list --left-right --count`: `b4e6b88c...origin/main` is `5 2`, `433b2679...origin/main` is `6 2`, and `8078ce48...origin/main` is `7 2`. | Self-invalidating counts make durable current pointers false as soon as their own correction is committed. | Current pointers state only the stable ancestry fact that neither tip contains the other; exact historical counts remain attached to exact reviewed commits. The guard rejects live ahead/behind counts in current surfaces. | The red focused run failed on the stale preamble count; corrected focused evidence is recorded in 25.6. |
| `TPR-CCR7-003` | P3 | **Closed by current correction** | `433b2679` | `test_document_consistency.py` current-block extractors; record 24.5 | Four of seven helpers required only their opening anchor; a missing closing anchor silently widened their scope to the rest of the document, contradicting the review's fail-closed claim. | `_action_current`, `_handoff_current`, `_handoff_current_review`, and `_handoff_target_summary` used `split(end, 1)[0]`, which succeeds when `end` is absent. | A widened governance scope can accept unrelated trailing evidence or reject unrelated history, recurring from `TPR-CCR6-004`. | One `_bounded` helper now requires exactly one opening anchor and a present closing anchor; all four extractors use it. | Parametrized missing-opening and missing-closing probes both pass by observing the required refusal. |
| `TPR-CCR7-004` | P3 | **Closed by current correction** | `8078ce48` | Record 24.8 | The validation successor called `433b2679` the round's single commit even though the Claude range contains `433b2679` and record-only `8078ce48`. | `git log --reverse b4e6b88c..8078ce48` returns exactly those two commits. | Exact commit scope is mandatory for commit-by-commit review and machine handoff. | Section 24.8 now names correction commit `433b2679` and record-only successor `8078ce48` separately. | Static range inspection and the current exact-range document guard agree on two commits. |
| `TPR-CCR7-005` | P3 | **Closed by current validation** | `8078ce48` | Record 24.8 | Every recorded validation ran on predecessor `433b2679`; none was recorded after the final record-only commit. | Section 24.8 explicitly names `433b2679`, while `8078ce48` is the remote head. | The repository instructions require proportional checks after the last change; predecessor evidence cannot validate later bytes. | This round runs focused document guards and diff/status checks on the received final tree, then repeats proportional and complete validation on the exact correction tree. | Exact results are appended in 25.6 and the post-commit validation subsection. |

### 25.3 Owner-approved TPR-TR0 trust-root design candidate

The owner approved the recommended inputs on 2026-08-31. This section freezes
only the design for independent review; it does not provision a credential,
create a trust file, sign an artifact, populate the reviewed-spec registry, or
mint authority.

| Design field | Frozen candidate |
|---|---|
| Signer principal | `shelton-tpr-reviewer`. It is an owner-controlled **approval/registry-attestation** principal. It authenticates owner approval of the anchor; it does not prove that Claude controls the key or performed the independent review and therefore cannot by itself close `TPR-CCR2-011`. |
| Key type | Dedicated Ed25519 OpenSSH signing key, generated outside every repository/worktree. The private key must be passphrase-protected, owner-controlled, and available only to owner-interactive Git signing - never to the runtime, CI, Codex, fixtures, or logs. No private-key bytes, passphrase, or secret locator may enter repository evidence. |
| External trust file | Exact Windows path `C:\ProgramData\CustomizedAgent\trust\tpr_allowed_signers`; no environment, CLI, repository, or caller override. It is machine-local and is never copied through Git. |
| Signature namespace | Exactly OpenSSH/Git namespace `git`. Namespace substitution refuses. The allowed-signers line names only `shelton-tpr-reviewer`, constrains the namespace to `git`, and uses an `ssh-ed25519` public key. |
| Signed trust object | The trust object is the **registry-anchor Git commit**, not a detached repository manifest and not the earlier `review_commit`. It is derived as the last commit that changed exact path `research/target_price_revisions/specs/reviewed_spec_registry.json`, avoiding a self-referential commit hash inside that registry. |
| Commit lineage | `producing_commit` -> independent `review_commit` -> signed registry-anchor commit -> optional later documentation-only descendants. The repository must be non-shallow with local complete history and lazy object fetching disabled. The registry anchor must be a strict descendant of `review_commit`, an ancestor of `HEAD`, a single-parent non-merge commit, and the source of registry bytes identical to `HEAD` and the working file. Its parent and anchor registry bytes must differ, proving that the derived anchor actually changed the registry. |
| Registry v2 policy | A future still-empty v2 registry freezes non-secret signature format `ssh`, namespace `git`, principal `shelton-tpr-reviewer`, key type `ssh-ed25519`, and an external-path identifier for the exact allowed-signers location. No registry entry is added by this design round. |
| Runtime verification | Before reading any positive registry entry, run Git with `--no-replace-objects` and command-scoped `gpg.format=ssh`, `gpg.ssh.allowedSignersFile`, `gpg.ssh.program=C:/Windows/System32/OpenSSH/ssh-keygen.exe`, and `gpg.minTrustLevel=fully`. Require signature status `G`, trust `fully`, exact principal `shelton-tpr-reviewer`, and an Ed25519 fingerprint present in the validated external file. Repository Git configuration, author/committer names, email, messages, and trailers are never identity evidence. |
| Policy inventory binding | The exact policy-path set remains independently frozen in tests and must equal the registry map in the signed registry-anchor commit. Hash policy/spec blobs from that signed commit, not merely from the earlier `review_commit`; require those signed-anchor, `HEAD`, and working bytes to match. The verifier itself joins the policy-path set. A missing tool/file, malformed or duplicate signer entry, symlink/junction, bad signature/trust/principal/key type, ancestry failure, set mismatch, or byte/hash mismatch refuses. There is no repository trust-file fallback or path override. |
| Persisted lineage | A successfully loaded reviewed algorithm must retain the registry-anchor commit and signing-key SHA-256 fingerprint in its authenticated fingerprint. Reload must reproduce both before any downstream gate can inspect it. |
| Custody and ACL | The directory/file owner is `BUILTIN\Administrators` (`S-1-5-32-544`) and each DACL is protected from inheritance. `SYSTEM` (`S-1-5-18`) and Administrators have full control; `BUILTIN\Users` (`S-1-5-32-545`) has read/execute only; no other ACE exists. Only SYSTEM/Administrators may write, delete, take ownership, or change ACLs; owner provisioning occurs through an elevated administrator context, never a non-admin owner ACE. The canonical trust path and parent chain must be non-reparse paths, and any other write/owner/ACL-control path refuses. The private key remains owner-only and passphrase-protected. ACL evidence records only non-sensitive SIDs, rights, fingerprints, and hashes. |
| Rotation/revocation | Runtime steady state contains exactly one trusted key. For routine rotation, prepare the replacement outside runtime trust, record old/new SHA-256 fingerprints and approval date, sign the next registry anchor under the new key, block positive authority, atomically replace the one-line runtime signer file with the new one-line file, and verify before restoration. For suspected compromise, remove the signer file immediately, remain blocked, require re-review where integrity is uncertain, and install/re-anchor under a new key before restoration. Old keys/fingerprints may remain only in non-runtime audit evidence; runtime trust never retains a compromised key or relies on backdatable `valid-before` history. |
| Threat model | Normal reviewed-code model: the host OS, administrators, Python runtime, OpenSSH executable, and dependencies are trusted. The boundary protects against unauthorized repository changes and self-mutable inventory/registry substitution. A compromised host/runtime is out of scope and would require a separate pre-import verifier outside the repository. |
| Cross-host rule | Every host must receive the externally custodied allowed-signers file and ACL independently. Missing local provisioning is `UNAUTHORIZED`, never a reason to trust a repository copy. |

#### 25.3.1 Exact non-secret file and command contract

The allowed-signers file has exactly one LF-terminated, comment-free line in
every authorized runtime steady state. Rotation occurs only while authority is
blocked and replaces that file atomically; a multi-key runtime file refuses.
`<BASE64_PUBLIC_KEY>` is a design placeholder and must be replaced
by the public half of the dedicated key before the file can exist:

```text
shelton-tpr-reviewer namespaces="git" ssh-ed25519 <BASE64_PUBLIC_KEY>
```

The future verifier invokes Git directly with an argument vector, never through
a shell, from a canonical repository root. It constructs a scrubbed environment
that rejects caller-controlled `GIT_CONFIG*`, object-directory, alternate-object,
replacement-ref, worktree, and repository overrides and sets
`GIT_NO_LAZY_FETCH=1`. These are the literal
logical commands; `<ROOT>` and `<ANCHOR>` are validated absolute-root and
40-lowercase-hex arguments, not interpolated shell text:

```text
git -C <ROOT> rev-parse --is-shallow-repository
git -C <ROOT> --no-replace-objects log -1 --format=%H -- research/target_price_revisions/specs/reviewed_spec_registry.json
git -C <ROOT> --no-replace-objects rev-list --parents -n 1 <ANCHOR>
git -C <ROOT> --no-replace-objects diff-tree --no-commit-id --name-only -r <ANCHOR>^ <ANCHOR>
git -C <ROOT> --no-replace-objects show <ANCHOR>^:research/target_price_revisions/specs/reviewed_spec_registry.json
git -C <ROOT> --no-replace-objects show <ANCHOR>:research/target_price_revisions/specs/reviewed_spec_registry.json
git -C <ROOT> --no-replace-objects -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=C:/ProgramData/CustomizedAgent/trust/tpr_allowed_signers -c gpg.ssh.program=C:/Windows/System32/OpenSSH/ssh-keygen.exe -c gpg.minTrustLevel=fully verify-commit --raw <ANCHOR>
git -C <ROOT> --no-replace-objects -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=C:/ProgramData/CustomizedAgent/trust/tpr_allowed_signers -c gpg.ssh.program=C:/Windows/System32/OpenSSH/ssh-keygen.exe -c gpg.minTrustLevel=fully show -s --format=%G?%x00%GT%x00%GS%x00%GK%x00%GF <ANCHOR>
```

The shallow-repository probe must return exactly `false`. Anchor derivation must
return exactly one lowercase 40-hex object name; `rev-list` must return exactly
that anchor plus one parent; `diff-tree` must return exactly the registry path;
and the two direct blob reads must be unequal. The
verification command must exit zero. The NUL-delimited status record must have
exactly five nonempty fields: `G`, `fully`, `shelton-tpr-reviewer`, the signing
key identifier, and its `SHA256:` fingerprint. The identifier/fingerprint must
normalize to the same Ed25519 public key in the already ACL-validated external
file. Any extra/missing output, warning, fallback, ambiguous signer line, or
unrecognized trust value refuses before the registry is parsed.

The signed Git commit is deliberately preferred over a detached manifest. A
commit signature binds Git's canonical commit object, including its exact tree
and parent lineage, so ancestry and registry bytes share one object identity.
A separately signed detached inventory could also avoid self-reference, but it
would add a second canonicalization, lookup, rollback, pairing, and lifecycle
surface. The signed-commit design is selected because Git already supplies the
canonical object and ancestry machinery this repository uses.

#### 25.3.2 Required implementation test matrix

The later implementation is incomplete unless it covers at least: valid anchor;
missing/unreadable/malformed/duplicate external signer file; repository fallback
or path/config/environment override; wrong namespace, principal, key type,
fingerprint, trust, or signature; unsigned/replaced/non-commit anchor; anchor not
a strict descendant of `review_commit` or not an ancestor of `HEAD`; registry or
policy bytes differing among anchor, `HEAD`, and worktree; missing/extra policy
path including omission of the verifier; shallow/incomplete history, lazy-fetch
dependency, merge anchor, unchanged parent/anchor registry bytes;
symlink/junction or unsafe ACL anywhere
in the trust-path chain; malformed/extra Git status output; routine rotation;
immediate compromised-key removal and refusal; and an unprovisioned second host.

#### 25.3.3 Pre-push design-audit dispositions

| ID | Priority | Status | First seen | Finding | Correction |
|---|---|---|---|---|---|
| `TPR-CCR7-006` | P2 | **Closed before push** | `dfaee5de` | Allowing an unspecified owner ACE could give a non-admin account write or ACL-control authority over the trust root. | The protected-DACL rule now permits only `SYSTEM` and `BUILTIN\Administrators`; owner provisioning requires elevation. |
| `TPR-CCR7-007` | P2 | **Closed before push** | `dfaee5de` | Retaining a compromised key behind `valid-before` permits a signer-controlled historical timestamp to be backdated. | Runtime trust removes a compromised key immediately and remains blocked until re-review/re-anchoring; old material is audit-only. |
| `TPR-CCR7-008` | P2 | **Closed before push** | `dfaee5de` | An owner-signed anchor authenticates owner approval, not Claude's reviewer identity, so it cannot close `TPR-CCR2-011`. | The identity boundary is explicit throughout; reviewer-controlled signing or a separately signed review receipt remains required. |
| `TPR-CCR7-009` | P3 | **Closed before push** | `dfaee5de` | The ancestry guard checked only whether the lane contained `main` while current documents also claimed neither tip contained the other. | The guard now checks both ancestry directions before permitting a divergence claim. |
| `TPR-CCR7-010` | P3 | **Closed before push** | `dfaee5de` | The frozen design lacked literal signer-line/command/output contracts, an adversarial matrix, and an explicit commit-versus-detached-manifest decision. | Sections 25.3.1 and 25.3.2 now freeze each item without provisioning or authority. |
| `TPR-CCR7-011` | P2 | **Closed before push** | `dfaee5de` | Path-limited `git log -1` alone can mistake a shallow-history boundary for the registry-changing anchor. | Runtime requires non-shallow complete local history, no lazy fetch, a single parent, a full commit diff containing only the registry path, and unequal parent/anchor registry bytes. |

### 25.4 Authority and milestone decision

TPR-TR0 is an owner-approved **design candidate only**, pending Claude's
independent review of the exact pushed Codex range and Codex's later
counter-review. No dedicated TPR signing key has been provisioned on this host;
the external allowed-signers path is absent; no fingerprint is frozen; no registry-
anchor commit is signed; and no runtime verifier is implemented in this
round. Key generation is deliberately deferred to an owner-interactive,
passphrase-protected step so no agent receives or logs the passphrase.

Accordingly, `TPR-CCR5-004` remains open until the reviewed design is
implemented and independently reviewed. The owner-signed registry anchor does
not prove the independent reviewer's identity; `TPR-CCR2-011` remains open until
reviewer-controlled signing or a separately signed review receipt is verified.
The reviewed-spec registry remains
empty; provider accesses, outcome accesses, and authorized/spent research looks
remain **0**. TPR-1, TPR-0B, every QuantConnect stage, and all broker, paper,
live, deployment, capital, and trading authority remain blocked.

### 25.5 Scope and validation evidence before the correction commit

- Fetched local and remote lane tips were identical at `8078ce48`; the
  worktree was clean and remained on the one long-lived target branch.
- The strengthened current-document regression ran before the document fix:
  missing-open and missing-close probes passed, while the ancestry/current-
  surface test failed on the stale `2 behind` preamble text. This is the
  required red evidence for `TPR-CCR7-001` through `003`.
- Exact first Codex commit `dfaee5dee73e2210aa42d05b308d40581b27ef4b`
  received a complete baseline run: **6,792 passed, 13 skipped, 2 failed, 25
  warnings in 1,270.49s**. Both failures are out of this lane and are retained
  as `TPR-OOL-009`: `tests/test_sleeve_report.py` fixes its lot/snapshot clock
  at 2026-08-07 while `unrealized_by_lot` reads the live UTC clock. Near the
  one-year boundary, both failing cases therefore report
  `term_if_sold_now = "short"` with `days_to_long_term = 0`. This is a P2
  tax-countdown consistency
  defect outside Target-Price Revisions; it is documented and deliberately not
  fixed here.
- No dedicated TPR signing key, external trust file, signed registry-anchor commit,
  registry entry, source row, outcome, look, QC surface, broker surface, or
  order was created or accessed.

### 25.6 Exact correction and final validation

The exact Codex correction/design commits are:

1. `dfaee5dee73e2210aa42d05b308d40581b27ef4b` - counter-review corrections and
   the first non-authorizing TPR-TR0 design freeze;
2. `15ce7f0475ca2dd91258905fe001782848952ffb` - pre-push security refinements,
   exact command/test contract, and the two-direction current-ancestry guard.

Validation on exact commit `15ce7f0475ca2dd91258905fe001782848952ffb`:

- Active-document plus complete target-price suite: **194 passed, 3 skipped in
  14.18s**. The target document module alone: **12 passed in 1.06s**.
- After this evidence was appended, the final record-candidate active-document
  plus target document suites were **81 passed in 1.59s**; `git diff --check`
  remained clean. The same focused checks are repeated after the record-only
  commit before push.
- Complete repository suite: **6,792 passed, 13 skipped, 2 failed, 25 warnings
  in 1,278.97s**. The only failures were the two exactly reproduced
  `TPR-OOL-009` sleeve-report countdown assertions; no Target-Price Revisions
  test failed. The same two failures occurred on first commit `dfaee5de`
  (**6,792 passed, 13 skipped, 2 failed, 25 warnings in 1,270.49s**), proving
  the security refinement added no failure.
- `compileall` exited 0 across `assistant`, `backtest`, `data`, `execution`,
  `ml`, `risk`, `scripts`, `signals`, `strategies`, `tests`, `research`, and
  the root Python modules. `git diff --check` was clean and the worktree was
  clean at exact commit `15ce7f04`.
- Environment: Python 3.12.13, pytest 9.1.1, Windows. The external
  `C:\ProgramData\CustomizedAgent\trust` directory and exact
  `tpr_allowed_signers` file were both absent after validation.
- Provider accesses **0**; source rows **0**; outcome accesses **0**;
  authorized/spent research looks **0**; QuantConnect, broker, paper, live,
  deployment, capital, and trading actions **0**.

The next role after this round's one push is Claude, independently reviewing
every Codex commit in `8078ce48..pushed-head` one by one. This design review
grants no provisioning or positive authority. `TPR-CCR5-004`, `TPR-CCR2-011`,
TPR-1, and TPR-0B remain blocked exactly as stated above.
