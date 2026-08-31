# Analyst Revisions V2 and Full-Project Review

**Review date:** 2026-08-26

**Reviewer:** Codex

**Disposition:** Rejected as implementation-ready; conditionally accepted only as an honest, incomplete research foundation

**Status of every finding:** Open; this was a review, not an authorized correction pass

**Trading authority:** None. This report does not authorize provider access, outcome access, a QuantConnect run, paper deployment, live deployment, or a policy change.

## 1. Executive conclusion

The project has two distinct products:

1. A deterministic, human-approved Alpaca paper assistant with a propose, validate, approve, claim, submit, journal, and reconcile lifecycle. The intended boundary is paper-only, fail-closed, and non-autonomous.
2. A research workbench that is now organizing three stock-first strategy lanes. Analyst Revisions V2 is intended to normalize point-in-time analyst rating changes, establish whether stock-level revisions contain incremental information, and only then aggregate validated stock information through point-in-time ETF holdings. A later integration milestone may combine independently validated strategies under one untouched shared holdout.

The documentation is unusually candid about what does not exist. Analyst Revisions V2 has no implemented V2 signal, outcome join, ETF score, portfolio, or QuantConnect algorithm. The existing research/acer package is V1 foundation plumbing: snapshot verification, event normalization, dataset identity, name/ticker diagnostics, and a historical-data capability audit. It must not be described as a completed V2 strategy.

The present foundation is not yet suitable as the backbone for all future strategies. The central problems are:

- research evidence identity proves file hashes but not semantic completeness, exactly-once row coverage, strict row schemas, or producing-code/configuration lineage;
- the V2 blueprint has unresolved or internally inconsistent timing, independence, normalization, ETF coverage, cost, portfolio-state, holdout, and milestone-order contracts;
- legacy analyst scripts can still consume mutable real outcomes outside the new look ledger;
- the paper execution boundary does not bind authorization to one coherent broker account snapshot, has a kill-switch dispatch race, accepts insufficiently validated broker order evidence, and can split an identity anomaly from the global halt intended to contain it;
- authoritative numeric policy fields accept JSON booleans;
- several supporting data, backtest, storage, ML-maturity, and operations-health contracts can certify malformed or temporally invalid evidence.

### Prioritized count

| Area | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| Analyst/research, including blueprint and coordination contracts | 0 | 0 | 17 | 7 |
| Remaining project, deduplicated across execution and system reviews | 0 | 6 | 13 | 3 |
| **Total** | **0** | **6** | **30** | **10** |

No P0 was found. No current live-trading escape, committed credential, or direct secret-logging path was found. All six P1 findings concern credible unsafe paper execution or an authoritative policy weakening. They still require correction before this assistant should be treated as a trustworthy execution backbone, and none may be carried into live promotion.

### Immediate operating recommendation

- Do not promote to live trading.
- Do not begin an Analyst Revisions V2 real-outcome study.
- Do not run the rejected legacy analyst scripts as new evidence.
- Keep provider access and any paid data acquisition behind the existing owner-authorization gate.
- Freeze new discretionary paper submissions until SYS-P1-001 through SYS-P1-006 are corrected and independently reviewed. Risk-reducing cancellation and legitimate risk-reducing sells must remain available.
- Preserve paper-epoch-006 evidence; this review does not authorize an operational deployment or epoch roll.

## 2. Scope, exact state, and moving-checkout caveat

The review started from:

- repository: trading_agent;
- branch: codex/main-three-strategy-direction-20260826;
- start/review snapshot: 9b2643a9d6f0d19410acfe2385c16b17a1defa34;
- base: 6156ef9b92737c9b390a96d286b0fbde4ff4b19c.

During the read-only review, another session advanced the coordination branch to 79d37324760a252d00cbf32998d65ad8eb2fd18b, merged that exact tree to main at 62b716f882e71c3e0ed220bccb59c7184e7bfd87, and switched the shared checkout to codex/strategy-analyst-revisions-v2 at c9dcdb647914acbfcefce187a138f52fcdad0c68. This reviewer did not undo that concurrent work.

The production files cited in this report are byte-identical between c9dcdb6 and the original 9b2643a review snapshot. The changes from 9b2643a to 79d3732 are confined to the counter-review record and session handoff; the merge tree at 62b716f is identical to 79d3732. Coordination documentation was therefore reviewed through 79d3732, while production findings apply to both c9dcdb6 and 9b2643a.

The existing untracked tmp tree belongs to another session and was preserved. The only durable file created by this review is this report.

## 3. Severity and final disposition

- **P0:** catastrophic active or imminent loss, live-authority escape, immediately exploitable secret exposure, or unrecoverable corruption.
- **P1:** credible unsafe execution, duplicate-order or broker-outcome risk, broken safety atomicity, serious security failure, or authoritative risk-policy weakening.
- **P2:** material incorrect state/evidence, meaningful fail-open or fail-closed behavior, missing recovery, statistically invalid research, or failure of a milestone definition of done.
- **P3:** inaccurate documentation, weak test sensitivity, maintainability/defense-in-depth weakness, or a low-risk edge case without current safety impact.

**Overall disposition: rejected as implementation-ready.** The existing ACER foundation may remain as an explicitly legacy/incomplete input, but ARV2-0 and ARV2-1 do not meet definition of done. The execution assistant may not be used as a future live backbone until the P1 ledger is closed. The active Action Plan remains the sequencing authority; the repair order in this report is a dependency recommendation to be incorporated by an owner-authorized plan amendment, not a competing plan.

---

# Part I — Research Layer and Analyst Revisions V2

## 4. Research finding ledger

| ID | Priority | Finding | Status |
|---|---|---|---|
| AR-P2-001 | P2 | Snapshot verification authenticates bytes, not semantic completeness | Open |
| AR-P2-002 | P2 | Dataset identity does not prove exactly-once source coverage or code/config lineage | Open |
| AR-P2-003 | P2 | Frozen dataset loader does not strictly validate identity or JSONL row schemas | Open |
| AR-P2-004 | P2 | V1 contract-version naming and row schema can be confused with V2 and cannot represent correction lineage | Open |
| AR-P2-005 | P2 | Rejected legacy analyst scripts remain runnable, unregistered outcome paths | Open |
| AR-P2-006 | P2 | ETF effective-contributor equation is mathematically invalid at and near zero | Open |
| AR-P2-007 | P2 | Event-based effective breadth contradicts institution/common-event independence | Open |
| AR-P2-008 | P2 | Fractional data quality can soft-admit rows that the blueprint says must be refused | Open |
| AR-P2-009 | P2 | Existing date-only availability is one session earlier than the literal V2 rule | Open |
| AR-P2-010 | P2 | Sparse/zero-MAD stock and ETF normalization is undefined | Open |
| AR-P2-011 | P2 | ETF mapping and coverage do not prove a complete, valid holdings book | Open |
| AR-P2-012 | P2 | Cost equation mixes incompatible portfolio-return and per-trade units | Open |
| AR-P2-013 | P2 | Hysteresis and the five-ETF cap have no deterministic conflict resolution | Open |
| AR-P2-014 | P2 | A heuristic evidence-quality score is mislabeled confidence | Open |
| AR-P2-015 | P2 | Measured 2011–2012 history conflicts with the blueprint's 2013 provider-history statement | Open |
| AR-P2-016 | P2 | ARV2 milestone order builds ETF topology before the stock-first stop/go test | Open |
| AR-P2-017 | P2 | ARV2-0 is not yet an executable preregistration and the lane-final holdout wording conflicts with the shared holdout | Open |
| AR-P3-001 | P3 | Issuer diagnostic accepts unauthenticated dataset-shaped dictionaries | Open |
| AR-P3-002 | P3 | ACER boundary tests inspect direct imports but not the transitive import closure | Open |
| AR-P3-003 | P3 | Provider-URL credential redaction is case-sensitive and incomplete | Open |
| AR-P3-004 | P3 | Legacy price-target path accepts nonfinite values and unknown aggregation semantics | Open |
| AR-P3-005 | P3 | Generic IC bootstrap does not enforce block length against the outcome horizon | Open |
| AR-P3-006 | P3 | Active-document tests do not fully pin lower-bound/not-allowlist and precedence semantics | Open |
| AR-P3-007 | P3 | Root mandate and QuantConnect factual statements drift from current project history | Open |

## 5. Detailed research findings and repairs

### AR-P2-001 — Snapshot verification authenticates bytes, not semantic completeness

**Where**

- research/acer/snapshot.py:31-55, 68-151
- scripts/build_acer_events.py:56-83
- scripts/audit_benzinga_ratings.py:142-202
- tests/test_acer_normalization.py:538-569
- tests/test_benzinga_ratings_audit.py:26-67, 104-127

**Verified failure**

A hash-valid manifest containing complete=true and an empty partitions list is accepted and yields zero verified rows. String values such as complete="false" and terminated_naturally="false" are truthy and are treated as true. The verifier does not require exact boolean types, a frozen requested year range, unique contiguous partitions, unique page sequences, page/year alignment, manifest-total reconciliation, or the absence of unreferenced raw pages. The incomplete override returns the same loose rows/hash shape as a complete capture, so a direct caller can accidentally publish it.

**Why it matters**

A truncated future capture can acquire a legitimate manifest hash and canonical-looking identity. File integrity is not source completeness. This is a foundation-level P2 because every later point-in-time claim depends on knowing exactly what was captured.

**How and where to fix**

1. In research/acer/snapshot.py, replace the tuple return with a frozen VerifiedSnapshot type. It must contain exact manifest bytes/hash, a named schema version, source row count, completeness state, requested bounds, partition/page coverage, page locators, and verification time.
2. Require exact booleans, exact allowed manifest keys, a nonempty expected partition inventory, unique contiguous years, unique ordered pages, page rows that fall inside the declared partition, exact total counts, and no unreferenced raw page.
3. Introduce a separate IncompleteDiagnosticSnapshot type. Dataset publication must accept only VerifiedSnapshot; do not use an allow_incomplete flag that preserves the publishable type.
4. Stamp every incomplete diagnostic artifact INVALID_INCOMPLETE_DIAGNOSTIC_ONLY.
5. In scripts/build_acer_events.py, make the type boundary—not a CLI if statement—the publication guard.

**Acceptance tests**

- Empty complete manifest refuses.
- String booleans refuse.
- Missing or duplicated middle year refuses.
- Missing/duplicated page, page-number gap, out-of-year row, count mismatch, and unreferenced page refuse.
- An incomplete diagnostic cannot type-check or run through dataset publication.
- A complete synthetic snapshot publishes and round-trips.

### AR-P2-002 — Dataset identity does not prove exactly-once coverage or producing lineage

**Where**

- research/acer/dataset.py:34-44, 59-166
- scripts/build_acer_events.py:64-84
- docs/ACTION_PLAN_2026-08-20.md:381-390
- docs/Archive/Research/ACER_V1/ACER_EVENTS_2026-08-20_BACKBONE_COVERAGE.md:29-35, 67-79

**Verified failure**

One normalized event can be removed while retaining the same source manifest hash; build_identity still creates a valid new dataset ID. There is no invariant that event_count plus refusal_count equals the verified source row count, no event/refusal ID disjointness check, and no binding to producing commit, normalizer/schema hash, configuration hash, evidence epoch, or build recipe.

**How and where to fix**

1. Have normalization return a frozen NormalizationResult bound to VerifiedSnapshot.
2. Carry a stable source-row locator into every accepted event and refusal.
3. Enforce exactly one terminal disposition per source row, source-row count equality, unique source locators, and disjoint event/refusal IDs.
4. Bind a clean producing commit, package/schema identifier, normalizer source hash or reviewed build identifier, configuration hash, provider contract, and evidence epoch into the identity.
5. Remove the public ability to build identity from loose event/refusal lists plus a caller-supplied manifest hash.
6. Narrow the Action Plan's claim from fully authenticated to the exact properties actually proved until this fix is complete.

**Acceptance tests**

Dropped row, extra row, duplicate disposition, event/refusal overlap, wrong source locator, dirty producing tree, or changed schema/config must refuse. An exact complete result must produce a deterministic identity, while a legitimate commit/config/schema change must produce a different identity.

### AR-P2-003 — The frozen loader is not a strict persisted-evidence boundary

**Where**

- research/acer/dataset.py:169-254
- CLAUDE.md:231-247

**Verified failure**

load_identity checks required identity keys but permits unknown keys. Because its content hash is derived only from a known subset, an attacker or accidental editor can add safety-shaped fields such as point_in_time_data=true or v2_ready=true without invalidating the hash, and the loader returns those fields. events.jsonl and refusals.jsonl are byte-hashed and line-counted but never parsed against a strict row schema.

**How and where to fix**

- Reject every identity key outside the exact versioned schema.
- Parse every JSONL row after byte-hash verification.
- Enforce exact keys, canonical date/timestamp formats, enum vocabularies, identifier syntax, finiteness, sort order, uniqueness/disjointness, and canonical reserialization.
- Return typed frozen records and a typed identity, never an unrestricted dictionary.
- Version migrations explicitly; never reinterpret old bytes through a new schema.

**Acceptance tests**

Unknown/safety-shaped identity keys, invalid JSON, missing/extra row keys, noncanonical dates, duplicate IDs, nonfinite numerics, out-of-order rows, and noncanonical serialization must refuse. A valid artifact must round-trip byte-for-byte.

### AR-P2-004 — V1/V2 contract ambiguity and missing correction lineage

**Where**

- research/acer/dataset.py:31-44
- research/acer/normalize.py:80-120
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:46-76, 94-103

**Problem**

The legacy foundation calls itself dataset contract version 2 even though it is not Analyst Strategy V2. Its normalized row drops or cannot establish provider firm/analyst identities, permanent issuer/security/share-class identities, effective/provider-publication/available/ingestion instants, raw-row locator/hash, immutable version ID, supersedes relation, correction/withdrawal/tombstone state, ontology version, mapping evidence, and producing lineage. A one-time current-state Snapshot A also cannot reveal how provider rows are amended, deleted, or restated over time.

**Required design**

Create a separate lane-owned package, preferably research/analyst_revisions_v2, instead of silently mutating research/acer in place. Use a semantic schema identifier such as arv2-canonical-event-v1, independent of marketing version numbers. The minimum row contract is:

- source snapshot ID and exact manifest hash;
- page hash, filename, row offset, and raw-row hash;
- provider event ID and immutable event-version ID;
- revision sequence, supersedes ID, revision kind, and original/corrected/withdrawn/tombstone state;
- effective time, provider-publication time, available time, and ingestion time;
- availability evidence and quality enum;
- stable firm/institution, analyst, issuer, security, and share-class IDs;
- historical ticker validity interval;
- raw and normalized ratings;
- ontology version, validity interval, and source evidence;
- canonical refusal reason;
- producing commit and schema/config hashes.

An as_of=t materialization must retain the version known at t. A later correction cannot rewrite history. Absence from Snapshot B must not become a deletion until the captures are proven comparable and provider deletion semantics are established.

**Acceptance tests**

Current ACER contract-v2 rows must be rejected by the ARV2 loader. Cover original to correction to withdrawal, late correction, equal timestamps, same-day reconciliation, missing provider ID, snapshot-deletion ambiguity, current-ticker reuse, share-class changes, firm rename, and point-in-time replay immediately before and after each availability boundary.

### AR-P2-005 — Legacy analyst outcome paths remain runnable

**Where**

- scripts/run_analyst_target_significance_check.py:27-52
- scripts/run_execution_timing_revalidation.py:53-118
- assistant/research_findings.json:22-35, 46-50
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:74-106

**Problem**

These rejected-family scripts fetch mutable yfinance data and reveal outcomes without a V2 preregistration, immutable dataset/config/code identity, permanent look ID, or shared-holdout latch. A casual rerun can create an uncounted look and contaminate the new program.

**Fix**

- Quarantine entry points under a legacy/reproduction namespace or make default invocation refuse before network/outcome access.
- Require an owner-authorized immutable reproduction/look ID and a frozen local dataset.
- Forbid network acquisition during a historical reproduction.
- Label any authorized historical reproduction non-new, non-V2, and unable to update active findings.
- Add an import firewall so research/analyst_revisions_v2 cannot import legacy analyst signal/data modules.

**Acceptance tests**

Default call, missing registered look ID, or network-backed reproduction refuses before outcome access. Exact historical reproduction remains isolated and cannot update active evidence. The V2 transitive import closure rejects legacy modules.

### AR-P2-006 — ETF effective-contributor formula is invalid near zero

**Where**

- Governing PDF, physical page 38, sections 18.3-18.4, equations 18.3-18.5
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:31-34

**Verified counterexample**

The PDF defines p_i as absolute contribution divided by total absolute contribution plus epsilon, then N_eff as one divided by the sum of squared p_i. Because epsilon makes the p values sum to less than one, they are not probabilities. One contribution of 1e-12 with epsilon 1e-6 yields N_eff near 1e12 instead of 1. At exactly zero contribution, N_eff divides by zero.

**Normative correction**

    a_i = abs(weight_i * signal_i)
    total = sum(a_i)
    if total <= frozen_numerical_zero:
        score = 0
        n_eff = 0
        reliability = 0
    else:
        p_i = a_i / total
        n_eff = 1 / sum(p_i ** 2)

Do not add epsilon to a probability normalization. Validate finite nonnegative allowed weights and clamp only after proving the analytical bound. Because the source PDF is immutable, record this as an owner-approved normative erratum/decision register; do not silently edit the PDF.

**Golden tests**

Zero contribution, one tiny contributor, one ordinary contributor, k equal contributors producing N_eff=k, one dominant contributor approaching one, and nonfinite/negative holdings refusal.

### AR-P2-007 — Event count is not independent evidence

**Where**

- PDF pages 10, 12, 29, and 33; sections 2.2, 3.1.4 H4, 13.2-13.3, 15.1
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:26-30

**Problem**

The narrative says multiple institutions should matter more than one institution repeating itself and that many analysts reacting to one earnings release are not independent news. The formula computes N_eff over events, dedupes only institution/security/day, and does not use common_event_id in canonical reliability. Five equal events from one institution on five days therefore look like five contributors; fifteen institutions clustered on one earnings release can look like fifteen independent news items.

**Fix**

Freeze the independent-contributor unit before outcomes:

1. reconcile institution/security/session records and corrections;
2. aggregate live contributions by stable institution before institution breadth;
3. cluster common catalysts and prevent one cluster from multiplying independent-news reliability;
4. retain raw event intensity as a separate diagnostic, not reliability;
5. define how overlapping institution and catalyst clusters combine.

**Golden tests**

Five events/one firm gives institution N_eff=1; five firms/equal independent evidence gives 5; fifteen firms/one common catalyst does not become fifteen independent items; cover mixed clusters, one dominant institution, and same-day corrections.

### AR-P2-008 — Soft quality conflicts with hard validity

**Where**

- PDF pages 16-17, 20, 33, and 54; sections 5.1-5.3, 7.3, 15.3, 27.1
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:46-49, 61-68

**Problem**

The blueprint says unknown/inconsistent timing, ambiguous rating ontology, and contaminated entity mappings are excluded or NO-GO. It also places timestamp, rating-map, and entity-map quality inside qdata from zero to one. That permits invalid rows to contribute at 0.1 or 0.2 and potentially contaminate sector medians before shrinkage.

**Fix**

Split the contract into binary admissibility and post-admission measurement quality. Timing, ontology, identity/security mapping, revision state, and point-in-time availability are hard gates with named refusals. Only noncritical measurement-quality diagnostics may enter a continuous reliability term after validity passes. Rename qdata to make this distinction explicit.

**Acceptance test**

Every ambiguous entity/rating/timestamp row becomes a refusal and never enters stock, sector, ETF, coverage, or reliability cross-sections.

### AR-P2-009 — Date-only event timing differs by one session

**Where**

- PDF pages 16-17, section 5.2
- research/acer/normalize.py:19-38, 276-284
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:38-39, 61

**Problem**

V1 uses available_date=max(action_date, last_updated UTC date), followed by the next session strictly after that date. The literal V2 table says next trading-day open plus one conservative day. A Tuesday date-only event is therefore Wednesday-open under V1 and Thursday-open under the literal V2 rule.

**Fix**

ARV2-0 must choose and state exact session arithmetic. Store an aware available_at plus evidence/quality, and derive eligible_session once in a shared exchange-calendar component. Do not reuse V1 available_date implicitly.

**Acceptance tests**

Tuesday, Friday, holiday eve, half-day, DST boundary, exact premarket, exact open, intraday, after-close, date-only, inconsistent clock, and later correction. Include a dangerous-direction test proving date-only cannot enter one session early.

### AR-P2-010 — Sparse and zero-MAD normalization is undefined

**Where**

- PDF page 33, equation 15.2
- PDF pages 40-41, equation 19.6
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:28-30, 68, 85

**Problem**

Analyst signals are naturally zero-inflated. Dividing by 1.4826 times MAD plus epsilon turns a single tiny nonmedian observation in a zero-MAD group into an arbitrary extreme, then clipping hides the degeneracy. The population, structural-zero meaning, minimum active names, peer fallback, and whether winsorization means training quantiles or fixed score clipping are not defined.

**Fix**

In the ARV2 decision register:

- define the point-in-time universe and distinguish no event, valid zero, missing, and invalid;
- set minimum total and active-event names per group;
- choose a frozen zero-MAD/sparse fallback such as pooled shrinkage, rank transform, or named refusal;
- choose either training-only quantile winsorization or fixed score clipping and name it correctly;
- use only point-in-time classifications/holdings;
- never use epsilon as a variance estimate.

**Golden tests**

All-zero group, one active among zeros, one/two-name sector, no-event versus invalid, peer ties, sector reclassification, zero MAD, and training-only clip bounds.

### AR-P2-011 — ETF mapping percentage does not prove holdings completeness

**Where**

- PDF page 18, section 6.2
- PDF pages 38-41, sections 18-19
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:31-34, 46-49, 70, 86

**Problem**

Mapped supplied weight divided by supplied weight can report 100 percent even when the source feed omitted 20 percent of the fund. The contract does not reconcile declared total/NAV, cash, derivatives, shorts, duplicate securities/share classes, negative/nonfinite weights, stale snapshots, no-event constituents, or point-in-time peer categories. Coverage C can become negative or exceed one and turn shrinkage into amplification.

**Fix**

Build a typed PIT holdings snapshot contract that:

- reconciles supplied positions against declared total/NAV and explicit cash/derivative treatment;
- identifies permanent security/share class and deduplicates;
- restricts canonical V2 to validated long-equity weights unless another instrument contract is approved;
- includes explicit unmapped positions in the denominator;
- bounds coverage between zero and one within a frozen tolerance;
- versions effective/available timestamps, holdings lag, category, and peer data;
- distinguishes missing snapshot, stale snapshot, unmapped position, and valid constituent with no analyst event.

**Acceptance tests**

Omitted 20 percent, total weight 0.8/1.2, duplicate security, negative/NaN/Infinity weight, cash, derivative, unmapped 1.01 percent, stale/missing snapshot, late peer-category change, and historical ticker reuse.

### AR-P2-012 — Cost equation mixes units

**Where**

- PDF page 50, section 24.1, equation 24.1
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:69

**Problem**

Turnover times commission/spread is a portfolio-return cost, while an unweighted sum of square-root participation terms is neither dollars nor portfolio-return units. Splitting an equivalent trade can change the cost mechanically.

**Fix**

Freeze all terms in dollars or all in portfolio-return units. One coherent return form is:

    sum_j abs(delta_dollars_j) *
        (commission_rate_j + half_spread_j
         + impact_coefficient_j * sqrt(abs(delta_dollars_j) / ADV_dollars_j))
        / NAV

Define one-way/two-way turnover, per-side convention, auction/open spread, PIT ADV lookback and availability, minimum fees, participation caps, missing-ADV refusal, and forced illiquid/delisting exits.

**Golden tests**

Hand-calculated single trade, economically equivalent split trade, zero trade, buy/sell symmetry, 0/5/10/20 bps scenarios, missing ADV, participation cap, and forced terminal exit.

### AR-P2-013 — Portfolio hysteresis conflicts with a hard five-name cap

**Where**

- PDF pages 42-43, sections 20.2-20.4
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:40-42

**Problem**

Five incumbents can remain above exit rank 70 while two entrants exceed entry rank 90. Retaining seven violates the cap; dropping incumbents violates hysteresis; blocking stronger entrants makes the entry threshold incomplete. Tie-breaking, eviction, constraint order, cap redistribution, residual cash, overlap clusters, and look-through sector exposures are also undefined.

**Fix**

Specify one deterministic state machine: forced exits, retained eligibility, entrant ordering, eviction rule, total-order tie break, constraint sequence, infeasibility behavior, cap redistribution, and residual cash. Compute look-through constraints from lagged PIT holdings. Underfill safely instead of relaxing a cap.

**Golden tests**

Five retained plus entrants, exact-rank ties, infeasible sector/cluster caps, fewer than five candidates, missing classification, stale holdings, inverse-vol cap, and residual cash.

### AR-P2-014 — Reliability is not calibrated confidence

**Where**

- PDF page 51, section 25.1, equation 25.1
- CLAUDE.md:216-218

**Problem and fix**

ConfidenceAnalyst is a heuristic product of reliability, quality, and event diversity. It is evidence quality, not prospectively calibrated confidence. Rename it analyst_reliability or evidence_quality everywhere. Reserve confidence for a prospectively calibrated quantity that clears a frozen calibration gate.

**Acceptance test**

No pre-calibration output schema, UI, or report contains a confidence field or claim.

### AR-P2-015 — Provider-history statement conflicts with measured data

**Where**

- PDF page 14, section 4.1
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:60

**Measured evidence**

Snapshot A includes 5 accepted events in 2011, 24,296 in 2012, and 28,609 in 2013, while the PDF says history begins in 2013.

**Fix**

Obtain and pin provider coverage/backfill semantics before these rows influence ontology or warm-up. Report coverage and vocabulary by era. Either admit early rows under a documented contract or quarantine them. Keep normative strategy design separate from measured provider facts so source precedence does not force a known-false observation.

### AR-P2-016 — Milestone order violates the stock-first stopping rule

**Where**

- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:82-90
- docs/THREE_STRATEGY_PROJECT_DIRECTION.md:87-104
- docs/ACTION_PLAN_2026-08-20.md:450-463

**Problem**

The shared workflow and original ACER ladder require the stock-level test before ETF construction can continue. The ARV2 table schedules ARV2-4 ETF reverse index/aggregation before ARV2-5 stock-first event study. That spends the expensive topology effort and exposes extra design choices before the decisive stop/go result.

**Fix**

Amend the owner-approved coordination docs so the executable sequence is:

1. freeze contracts;
2. build ratings/ontology;
3. build PIT identity and outcome prerequisites;
4. implement stock score and synthetic/golden tests;
5. register and run the stock-only event study;
6. stop on a valid null;
7. only after a pass, build and test ETF topology;
8. run ETF walk-forward research;
9. implement QC parity;
10. perform the separately defined final evaluation.

Structural provider capability audits may precede the stock test, but full ETF signal construction may not. Add an active-document test that asserts milestone order, not merely presence of milestone names.

### AR-P2-017 — The preregistration and holdout contract is not executable

**Where**

- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:72, 82-90
- docs/THREE_STRATEGY_PROJECT_DIRECTION.md:153-171
- research/acer/capability.py and existing generic research utilities

**Problem**

ARV2-0 says every ambiguous choice will be fixed, but no immutable machine-readable cell registry currently freezes them. ARV2-8 says independent final holdout, while the shared direction says all lanes must leave one common final period untouched for a single combined evaluation. The phrase is ambiguous enough to permit a lane to spend the shared holdout. The generic five-dimension look counter is not sufficient for this strategy's topology, timing, horizon, schedule, weighting, holdings-lag, coverage, common-event, cost, and extension family.

**Required preregistration**

Create a reviewed, content-addressed specification under a new lane-owned path such as research/analyst_revisions_v2/specs/arv2_round0.json plus a strict loader. Before any outcome import it must freeze:

- shared final cutoff/reserved period and an explicit prohibition on lane access;
- contaminated legacy periods and which data may be discovery/validation only;
- one primary rating-only hypothesis and signs; target/estimate/news channels are separate future families;
- exact availability and label construction from eligible open to h-session exit open, including splits, dividends, delistings, and no missing-exit drops;
- purged/grouped walk-forward splits by decision date/common event with embargo at least the outcome horizon;
- independent sample unit, clustering, HAC/bootstrap block rules, and minimum independent dates;
- exact control set, including momentum, earnings/guidance/immediate jump where mandated, size, liquidity, volatility, sector, and the treatment of missing controls;
- exact universe, structural-zero semantics, group fallbacks, clipping/residualization, thresholds, and hyperparameters;
- primary stock topology and the single predeclared ETF topology comparison hierarchy;
- identical observation rules for stock/industry/ETF and every baseline;
- all cost and holdings-lag parameters;
- complete multiplicity family and permanent cell/look IDs;
- one-shot lane validation periods distinct from the untouched shared integration holdout;
- three-lane family correction and the rule that a valid null closes the family.

Outcome-loading code must require a reviewed spec hash, a registered unspent look ID, a frozen dataset/code identity, and a shared-holdout exclusion proof.

**Dangerous-direction tests**

Attempt outcome access with a missing spec, edited spec, unregistered/spent look, shared-holdout date, unpurged split, block shorter than horizon, omitted control, unregistered topology, or changed cost. Every case must refuse before returning a price or outcome statistic.

### AR-P3-001 — Issuer diagnostic accepts weak dataset-shaped input

**Where**

- research/acer/identity.py:325-382
- scripts/report_acer_identity.py:78-90
- tests/test_acer_identity.py:309-341

The report function accepts a dataset-ID prefix, version, snapshot name/hash, and count without authenticating the full dataset ID/content/events/refusals hashes. Change it to accept only a validated typed identity or load one through the strict loader. Persist exact contract version and hashes. Test forged prefix, missing content hash, wrong full ID, unsupported version, and count-only input.

### AR-P3-002 — Direct-import tests miss transitive authority leaks

**Where**

- research/acer/__init__.py:14-15
- tests/test_acer_normalization.py:585-632

The current reachable dependency graph is safe, but tests inspect only imports written directly in research/acer. Add a transitive local-import closure and a fixture where ACER imports a safe-looking facade that imports backtest, execution, network, or outcome code. Preserve the direct AST check as a fast diagnostic.

### AR-P3-003 — URL redaction is incomplete

**Where**

- scripts/audit_benzinga_ratings.py:112-114, 179
- tests/test_benzinga_ratings_audit.py:130-136

APIKEY, Api_Key, and access_token variants remain visible while apiKey is redacted. Current requests use a bearer header, so no current leak was found. Parse URLs structurally, case-fold decoded parameter names, redact a frozen credential-name set or allow only approved query fields, and sanitize exception text. Add mixed-case, percent-encoded, repeated-key, fragment, and exception tests.

### AR-P3-004 — Legacy target code admits nonfinite and unknown semantics

**Where**

- data/price_target_data.py:47-98
- signals/analyst_target.py:77-97
- tests/test_price_target_data.py:24-117

Two positive infinities can survive trimming and yield infinite consensus; a NaN close can produce a NaN upward signal; an unknown method silently means mean; timezone information is stripped rather than verified. If retained for advisory display, require finite positive values, an explicit mean/median enum, strict schema, and verified timezone/session semantics. Keep it outside V2.

### AR-P3-005 — Bootstrap block can be shorter than the label horizon

**Where**

- ml/cross_sectional.py:284-313
- tests/test_ml_cross_sectional.py:171-190

The docstring advises but does not enforce block length at least the overlapping outcome horizon. The ARV2 wrapper must take horizon_sessions and refuse block_length below it. Add the dangerous 20-session outcome/1-day block test.

### AR-P3-006 — Documentation tests do not pin the full meaning

**Where**

- tests/test_active_document_consistency.py:1425-1440
- docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md:59-72
- docs/SESSION_HANDOFF.md

The consistency test requires 768 in active documents but pins lower bound/not allowlist only in the archived measurement. It also cannot distinguish immutable normative PDF rules from later measured provider facts. Require every active summary to say 768 is a lower bound, never an allowlist; prohibit current-ticker joins; and make the precedence rule explicitly separate normative design from observed availability/history.

### AR-P3-007 — Active routing and factual history are stale

**Where**

- docs/operations/MANDATE.md:117-125
- README.md:365-405
- docs/operations/OPERATIONAL_FACTS.md:841-858
- docs/research/alpha-result.md

The mandate still says individual-stock signal hunting is off the roadmap, while the owner-directed three-lane program requires stock-first validation. README and Operational Facts say no QuantConnect live call has ever been made even though the durable run ledger records many cloud runs. Amend the active documents to distinguish no execution authority from historical research calls and to acknowledge the owner-directed stock-first lanes. Add consistency tests against the run ledger and direction document.

## 6. Research implementation blueprint

### 6.1 Package and artifact boundaries

Do not relabel current research/acer artifacts as V2. Preserve them as immutable legacy evidence and build a new lane-owned namespace:

    research/analyst_revisions_v2/
        contracts.py
        snapshot.py
        events.py
        ontology.py
        availability.py
        identity.py
        stock_signal.py
        inference.py
        holdings.py
        etf_signal.py
        portfolio.py
        costs.py
        outcome_gate.py
        specs/

Tests should mirror that boundary under tests/analyst_revisions_v2. No module before outcome_gate may import prices/outcomes, backtest engines, execution, broker, or network clients. Provider capture remains a separate audited adapter.

### 6.2 Required fix order

1. Owner-approved V2 erratum and machine-readable ARV2-0 decision register.
2. Typed snapshot completeness and exactly-once normalization contracts.
3. Snapshot B/provider amendment-deletion study; no inferred tombstones before semantics are known.
4. PIT firm, analyst, issuer, security, share-class, ticker, sector, price/corporate-action, and delisting contracts.
5. Rating ontology with time-valid normalized firm scales and fail-closed refusals.
6. Stock signal, institution/common-event reliability, availability, sparse-group behavior, and golden equations—with no outcome imports.
7. Reviewed immutable look registration and stock-only event study.
8. Stop on a valid null. If it passes, then build PIT ETF holdings, coverage, aggregation, and portfolio state machine.
9. ETF walk-forward evaluation under frozen costs and multiplicity.
10. QC implementation only after research acceptance, followed by deterministic parity.
11. One separately authorized integration evaluation on the untouched shared holdout.

### 6.3 Research definition of done

The analyst strategy is not complete merely because code runs. Completion requires:

- every source row has exactly one authenticated terminal disposition;
- point-in-time replay is version-correct under corrections and withdrawals;
- all formulas have hand-computed golden tests and dangerous-direction mutations;
- invalid identity/timing/ontology never becomes fractional evidence;
- stock evidence passes its preregistered gate before ETF construction;
- no lane consumes the shared final holdout;
- the permanent look ledger accounts for every observed cell and rejected/refused run;
- inference uses independent dates/common events, purging/embargo, horizon-aware blocks/HAC, and the complete multiplicity family;
- transaction costs, terminal returns, holdings lag, underfill, and capacity are dimensionally correct and frozen;
- independent review reproduces dataset identity, material counts, mutation failures, and the exact accepted commit;
- no result creates paper or live trading authority without a separate owner promotion decision.

---

# Part II — Remaining Project

## 7. System finding ledger

| ID | Priority | Finding | Status |
|---|---|---|---|
| SYS-P1-001 | P1 | Boolean JSON values can weaken authoritative numeric policy limits | Open |
| SYS-P1-002 | P1 | Execution is authorized against an unproven, incoherent, or foreign-account portfolio | Open |
| SYS-P1-003 | P1 | Kill switch/cancel-all can miss an order already past validation | Open |
| SYS-P1-004 | P1 | Normal submit responses lack one strict broker-order identity/schema boundary | Open |
| SYS-P1-005 | P1 | Identity-anomaly parking and global halt are split across transactions | Open |
| SYS-P1-006 | P1 | Malformed open orders are skipped while evidence remains marked available | Open |
| SYS-P2-001 | P2 | Risk checks use rounded floats despite exact broker numerics | Open |
| SYS-P2-002 | P2 | Fill quantity/price exactness is lost in the durable ledger | Open |
| SYS-P2-003 | P2 | Duplicate event IDs can project conflicting unjournaled payloads | Open |
| SYS-P2-004 | P2 | Unknown broker status is mislabeled broker accepted | Open |
| SYS-P2-005 | P2 | Negative portfolio states can be reported compliant | Open |
| SYS-P2-006 | P2 | Earnings blackout blocks legitimate risk-reducing sells | Open |
| SYS-P2-007 | P2 | Invalid/future order timestamps disable stale cancellation | Open |
| SYS-P2-008 | P2 | Future pre-broker claims can be reported healthy | Open |
| SYS-P2-009 | P2 | Market-data health accepts partial/malformed/mixed-staleness batches | Open |
| SYS-P2-010 | P2 | Backtests accept time-reversing and return-manufacturing parameters | Open |
| SYS-P2-011 | P2 | Watchdog can monitor a different policy from scheduled execution | Open |
| SYS-P2-012 | P2 | Database schema verification ignores semantic constraints | Open |
| SYS-P2-013 | P2 | ML storage permits outcomes before a session horizon matures | Open |
| SYS-P3-001 | P3 | Reconciler timing controls are not uniformly finite/range validated | Open |
| SYS-P3-002 | P3 | Budget reporting silently drops malformed fill evidence | Open |
| SYS-P3-003 | P3 | Authorization TTL is weakly typed and replay consumption is unsynchronized | Open |

## 8. Detailed P1 execution and policy findings

### SYS-P1-001 — Boolean JSON values weaken numeric policy limits

**Where**

- assistant/policy.py:130-181, 268-322
- assistant/execution_kernel/validate.py:560-585
- tests/test_policy.py:141-178

**Verified failure**

Python bool is a numeric subclass. TradingPolicy.validate applies finiteness and range comparisons without first excluding bool. JSON true can therefore become 100 percent when a fractional cap is multiplied by 100; false passed through policy_with_updated_flags can become a zero cash reserve. Basket, leveraged-ETF, spread, and cash-reserve examples genuinely weaken policy rather than merely fail closed.

**Why P1**

A malformed but syntactically valid policy can validate, receive a legitimate fingerprint, and authorize materially more exposure than the owner intended.

**How and where to fix**

1. Add one strict real-number parser in assistant/policy.py that rejects bool before conversion, accepts only the supported numeric representation, enforces finiteness, and applies a field-specific inclusive/exclusive range.
2. Use it for every percentage, notional, duration, spread, slippage, count, and reserve field, including update helpers.
3. Reject JSON NaN/Infinity at parse time in addition to object-level validation.
4. Ensure fingerprinting occurs only after strict validation and canonical numeric normalization.
5. Inspect other authoritative configuration dataclasses for the same bool-as-number pattern.

**Regression and mutation tests**

Parameterize True and False over every numeric field through direct validation, JSON load, and policy updater. Add an end-to-end policy-to-execution-kernel test proving no bool becomes 0, 1, or 100. Reverse the bool rejection and require the test set to fail.

### SYS-P1-002 — Execution lacks one account-bound coherent portfolio

**Where**

- assistant/execution_service.py:600-609
- assistant/execution_kernel/validate.py:268-302, 416-425
- assistant/portfolio_snapshot.py:194-228
- execution/alpaca_broker.py:96-98, 208-230, submit paths near 672 and 738
- risk/execution_gate.py:340-416

**Verified failures**

- Execution validates a caller-supplied portfolio but never requires source=alpaca, account_mode=paper, or a nonempty account ID matching the preflight broker account.
- Snapshot capture reads account, open orders, and positions sequentially without a coherence proof, then computes equity from early cash plus later positions and ignores broker equity.
- A fill between reads can combine 100 dollars old cash with a later 50-dollar position and report 150 dollars equity although broker equity is 100.
- Broker operations create clients from mutable environment credentials at several stages. Credentials can rotate from account A to account B between snapshot, preflight, and submit.
- ExecutionAuthorization binds intent but not account ID, mode, or snapshot lineage.

**Required architecture**

1. Caller snapshots become preview-only. After the proposal is atomically claimed, execution must acquire its own account-scoped snapshot.
2. Introduce a broker session/client whose account identity is established once and reused through final submission.
3. Use a bounded seqlock-style collection:

       account A
       open orders A
       positions
       open orders B
       account B

   Require stable account ID/mode, cash, buying power, position quantities, and order identities/material sizes. Retry a small fixed number; otherwise refuse.
4. Treat broker equity_decimal as authoritative and reconcile the component sum within a strict tolerance. Never silently replace it with asynchronously sampled cash plus positions.
5. Require a complete Alpaca paper snapshot and exact numerics.
6. Bind account ID, paper mode, snapshot identity, and policy fingerprint into ExecutionAuthorization.
7. The same account-scoped client must perform the final submit and echo the bound account.

**Tests**

- Manual/live/foreign account snapshot refuses before submit.
- Fill during capture causes retry and then refusal if unstable.
- Account changes mid-capture or credentials rotate after validation: zero submission.
- Component equity disagrees with broker equity: refusal.
- Stable matching paper account: positive control.

### SYS-P1-003 — Kill-switch dispatch race

**Where**

- assistant/execution_service.py:584-609, 791-800
- assistant/order_reconciler.py:458-464
- execution broker submit paths

**Race**

T1 validates while the switch is off and pauses before submit. T2 activates the durable switch, sees zero open orders, and returns from cancel-all. T1 resumes and submits beneath an active switch. Another uncoordinated last-moment read narrows but cannot close this race.

**Fix**

Implement a crash-recoverable, cross-process dispatch fence:

1. Execution claims proposal and acquires the fence.
2. Under the fence it rereads environment and durable kill/reconciliation switches, revalidates account binding and authorization, records a dispatch attempt, submits, and releases.
3. Cancel-all sets the switch first, acquires the same fence so in-flight dispatch drains, repeatedly queries/cancels until the open-order set is stable, records results, and releases.
4. Queued submissions acquire later and refuse.
5. Reconciliation-halt activation uses the same fence.
6. Emergency cancellation must remain possible even when normal attribution fields are malformed.

SQLite can coordinate a lease/attempt row if the process model is multi-process; a process-local lock is insufficient.

**Deterministic barrier tests**

- Cancel-all cannot return before an already-fenced dispatch is seen and cancellation requested.
- Late environment switch refuses before submit.
- Reconciliation halt fences concurrent dispatch.
- Process crash while holding the lease is recoverable without allowing blind submit.
- After cancel-all returns, no queued dispatch proceeds.

### SYS-P1-004 — Broker response is not strictly identity-validated

**Where**

- assistant/execution_service.py:791-811
- assistant/execution_kernel/submit.py:188-217
- execution/alpaca_broker.py:157-205
- assistant/execution_kernel/outcomes.py:73-124
- assistant/order_lifecycle.py:293-320

**Verified gaps**

The normal submit return is journaled without comparing it to the exact approved intent. Missing order ID becomes the string None. Reconciliation checks omit exact root client_order_id, TIF, recognized status, and fill invariants. Limit identity uses float tolerance. Raw filled can terminalize without positive exact quantity/price, while unknown zero-fill status falls through to accepted.

**Fix**

Create one strict validate_broker_order boundary used by:

- normal submit return;
- root idempotency lookup;
- reconciliation polling;
- open-order snapshots;
- stream events and replacements.

It must require:

- nonempty valid broker order ID;
- exact expected root client-order ID, with separately proven replacement-chain lineage;
- matching bound account;
- canonical ticker/side/type;
- TIF exactly day for the current contract;
- exact Decimal requested quantity and canonical tick price;
- recognized closed status vocabulary;
- aware timestamps;
- fill invariants: zero for unfilled, zero less than partial less than requested, and filled quantity equal to requested plus finite positive average price for filled.

Validate before any positive success projection. A post-contact mismatch is ambiguous: retain reservation, park submission_unknown, reconcile under the expected key, and atomically halt/alert. Do not call it submission_failed.

**Tests**

Wrong/missing client ID, missing order ID, wrong account/TIF/type/side/ticker/quantity, one-tick limit mismatch, unknown status, filled without exact quantity/price, and root lookup under another client key all refuse and halt. Include a valid replacement chain positive test.

### SYS-P1-005 — Anomaly state and global containment are not atomic

**Where**

- assistant/execution_kernel/outcomes.py:166-176, 197-208
- assistant/execution_kernel/reconcile.py:127-139, 159-172
- assistant/order_reconciler.py:98-109, 206-216
- assistant/storage.py:4370-4430

**Failure**

Each path first commits proposal submission_unknown and then separately activates the global reconciliation halt. A crash between commits leaves an acknowledged broker identity anomaly without a kill switch; unrelated submissions can continue.

**Fix**

Add AssistantStore.park_reconciliation_anomaly_and_halt using one BEGIN IMMEDIATE transaction. It must:

- conditionally project the proposal to submission_unknown with error and reconciliation time;
- set the persistent kill switch;
- upsert the critical operational alert;
- retain reservation and duplicate slot;
- write the halt even if a concurrent terminal transition prevents proposal projection.

All mismatch callers must use only this method. Coordinate its completion with the dispatch fence in SYS-P1-003.

**Fault-injection tests**

Crash after each SQL statement, reopen the database, and prove there is never a committed anomaly without halt and alert. Test concurrent terminal update, rollback of all rows on failure, and idempotent retry.

### SYS-P1-006 — Malformed open orders make an incomplete book look complete

**Where**

- execution/alpaca_broker.py:157-205
- assistant/portfolio_snapshot.py:196-204
- assistant/execution_kernel/validate.py:480-490
- assistant/execution_kernel/revalidate.py:158-200

**Failure**

Open-order normalization permits missing ticker, unknown side/type, missing quantity/notional, and nonfinite numerics as None. The endpoint list still sets open_orders_available=true. Duplicate and pending-exposure checks then skip the malformed row, permitting a new buy based on an incomplete broker book.

**Fix**

Define a strict active-order schema: nonempty order ID/ticker, recognized active status, known side/type/TIF, finite positive exact quantity or notional, and valid fill range. One invalid risk-relevant row makes open-order evidence unavailable and blocks new submission. Pending exposure must use exact Decimal companions.

Keep emergency cancellation separate: minimally enumerate raw rows and cancel every valid order ID even when attribution is malformed. Strict normal validation must not obstruct risk reduction.

**Tests**

Missing ID/ticker/side/type/TIF/size, NaN/Infinity, unknown status, and invalid fill range each cause zero submission and explicit unavailable evidence. Cancel-all must still cancel a malformed-but-identifiable order.

## 9. Detailed P2 system findings

### SYS-P2-001 — Rounded float risk math at exact cap boundaries

**Where**

- assistant/portfolio_snapshot.py:133-160
- risk/execution_gate.py:701-749, 899-1089
- assistant/execution_kernel/revalidate.py:175-219

Exact fields exist, but the gate reads rounded float cash/equity/buying power and rounded market values. A position worth 49.994 can display 49.99; adding 0.01 appears to reach exactly 50.00 and pass a 50 percent cap although exact exposure is 50.004. Multiple rows accumulate the error.

Use exact snapshot properties and position.exact_field throughout authoritative arithmetic. Require exact values on Alpaca execution snapshots; display values may never drive a decision. Validate exact/display consistency. Test sub-cent boundary, accumulated rounding, disagreement, fractional pending orders, and quote exactness.

### SYS-P2-002 — Exact fills are irreversibly rounded

**Where**

- assistant/storage.py:429-445, 3777-3798, 6111-6218
- execution/alpaca_broker.py:585-593

SQLite REAL stores fill quantity/price and stream events emit floats. Authoritative fill reconstruction ignores decimal text that may exist in polling payloads. Fractional lots, cost basis, P&L, tax, and execution-quality evidence cannot reproduce broker digits.

Add authoritative text-decimal columns for cumulative and incremental quantity/price, preserve provider decimal text at every boundary, and read exact text for all ledger/lot consumers. Keep REAL only for compatibility/display. Mark legacy REAL-only rows rounded/unrecoverable. Migrate additively and backfill only when exact source bytes exist. Test adversarial decimals, restart round-trip, stream partial plus poll cumulative remainder, and legacy disclosure.

### SYS-P2-003 — Duplicate event ID can split journal and projection

**Where**

- assistant/storage.py:3737-3885
- assistant/order_lifecycle.py:323-343
- execution/alpaca_broker.py:585-594

On event-ID collision, storage compares only order/proposal binding. INSERT does nothing, but projection continues using the new caller payload. The append-only journal may retain partial/4 while proposal/order state becomes filled/10.

Store a canonical immutable event-content hash over every projection-driving field. Exact replay is idempotent. Same ID with any changed status, quantity, price, time, or normalized payload must roll back with projections unchanged and atomically alert/halt when execution-relevant. Repair from stored bytes, never replay caller bytes. Scope identity by broker/account/order if provider IDs are not global. Test exact replay, every changed field, concurrent collision, unchanged projections, and legacy self-heal.

### SYS-P2-004 — Unknown status is positive acceptance

**Where**

- assistant/order_lifecycle.py:293-320
- assistant/readiness.py:26-32

A new/corrupt provider status with zero fill falls through to broker_accepted, which readiness does not treat as a critical unresolved outcome. Map unknown/blank status to submission_unknown or a dedicated critical state. Retain reservation and duplicate slot, open an alert/halt, and make readiness false. The strict status vocabulary belongs in SYS-P1-004's central validator. Test new enum, blank, malformed type, and case/whitespace variants.

### SYS-P2-005 — Negative portfolio can appear compliant

**Where**

- assistant/portfolio_snapshot.py:65-127
- assistant/risk_copilot.py:505-551
- assistant/context_builder.py:77-88
- risk/execution_gate.py:752-788

The builder checks finiteness but accepts negative shares/prices/market values. One-sided exposure comparisons can return no policy violations, while execution correctly refuses the same state.

Create a canonical no-short/no-margin snapshot contract: reject negative shares, nonpositive prices for nonzero holdings, negative/inconsistent market value, and unsupported negative cash/buying power; decide and document zero-share handling. Validate direct dataclass instances as well as builder/broker paths. Reporting must become unavailable/degraded on malformed state, never compliant. Add parity tests proving anything execution rejects for position integrity cannot receive a clean risk report.

### SYS-P2-006 — Earnings safeguard obstructs risk reduction

**Where**

- risk/execution_gate.py:1267-1278, 1328-1353, 1428-1432
- tests/test_personal_assistant.py:954-1000
- CLAUDE.md:169-171
- docs/ACTION_PLAN_2026-08-20.md:589-590

The earnings blackout applies to both sides and an existing test expects a generated risk-reduction sell to be blocked. This violates the binding rule that a conservative safeguard cannot obstruct a legitimate risk-reducing sale.

Make earnings blackout exposure-increasing only. In the current long-only model it is buy-only. Before allowing a sell, prove a valid current long and quantity no greater than holdings; oversell/short-opening remains blocked. Test generated reduction, owner trim, buy block, oversell refusal, and mixed hard violations.

### SYS-P2-007 — Bad order timestamps silently preserve stale orders

**Where**

- assistant/order_reconciler.py:291-331, 725-769

Missing/unparseable timestamps return no cancellation, naive timestamps become UTC, and future timestamps have negative age and appear young. Reconciliation can still record success.

Return a structured timestamp/cancellation disposition. Require aware time, allow only a small frozen future-skew tolerance, and treat missing/malformed/naive/materially-future time as integrity failure with durable alert and readiness failure. Once authoritative order ID is known, cancellation is risk-reducing and should be attempted or moved to an explicit operator recovery state. Test recent, stale, missing, malformed, naive, small skew, and material future cases including recorded reconciliation error counts.

### SYS-P2-008 — Future pre-broker claim appears healthy

**Where**

- assistant/readiness.py:48-55, 141-210

A future updated_at yields negative age and is neither stale nor unreadable, so readiness can be true while the uniqueness slot stays wedged. Reject naive time; classify materially future claims separately; block readiness and surface ID/status/time/signed age. Do not auto-reclaim from ambiguous clock evidence. Test future, naive, malformed, exact-now, recent, stale, and tolerance boundary.

### SYS-P2-009 — Market-data success is not data usability

**Where**

- data/market_data.py:59-109
- data/price_source.py:114-169
- assistant/data_integrity.py:68-127, 181-209
- tests/test_data_integrity.py:144-155

Any nonempty frame can count as returned. Missing columns, nonfinite/nonpositive or impossible OHLC, invalid index, partial universe, and a fresh ticker beside a stale ticker can record success; maximum session masks the stale sibling.

Create one central provider-output validator before success is persisted:

- canonical ticker;
- unique ascending exchange-session index;
- required fields;
- finite positive OHLC with high/low consistency;
- valid nonnegative volume;
- at least one usable row.

Persist transport success, ticker usability, requested-universe completeness, and per-ticker freshness separately. Partial results may be usable but must be degraded/alertable; use worst required-symbol freshness. Test every malformed bar direction, invalid index/order/duplicates, partial universe, and mixed staleness while preserving valid siblings.

### SYS-P2-010 — Backtest APIs permit impossible economics

**Where**

- backtest/engine.py:72-204, 579-620
- backtest/portfolio_simulator.py:95-307
- strategies/leverage_rotation.py:42-142
- strategies/trend_vol_rotation.py:59-205
- strategies/vol_target_rotation.py:70-211
- strategies/kelly_rotation.py:123-265
- strategies/decline_grid.py:124-373
- stricter sibling: market_analytics.py:162-186

Negative hold_days can exit before entry; negative benchmark horizon shifts backward; negative slippage/cost/tax manufactures return; NaN propagates; zero rebalance period divides by zero; invalid weights introduce hidden shorts/leverage; nonpositive prices reach sizing.

Add a shared research/backtest input contract at every public entry point: positive integer horizon excluding bool, explicit same-day exception, finite nonnegative bounded costs, positive capital, positive integer cadence/counts, long-only bounded weights whose sum is within tolerance, positive finite prices, and aligned unique monotonic sessions. Test negative/zero/bool/float horizons, NaN/Infinity/negative costs, invalid weights, zero cadence, nonpositive prices, and prove exit never precedes entry.

### SYS-P2-011 — Watchdog policy differs from execution policy

**Where**

- scripts/run_operations_watchdog.py:46-68
- assistant/policy.py:30-83
- scripts/run_personal_assistant.py:196-208
- scripts/install_windows_operational_tasks.ps1:141-179
- docs/ACTION_PLAN_2026-08-20.md:595-597

Watchdog supplies an explicit default path, bypassing the canonical explicit to environment to personal to default resolution used by scheduled execution. It can certify a different set of limits.

Default watchdog --policy to none and call resolve_policy_path. Have the installer resolve or accept one explicit policy and pass it to every operational task. Record path and fingerprint in heartbeats; task verification must compare all fingerprints. Test precedence, broken path, WhatIf/install parity, and one-fingerprint parity across cycle, monitor, observation, and watchdog.

### SYS-P2-012 — Schema verification ignores the constraints that protect integrity

**Where**

- assistant/storage.py:404-445, 6654-6805
- tests/test_storage_schema_verification.py:229-262

The verifier represents tables only as column-name sets. A table rebuilt without primary key, inline unique, not-null, default, type affinity, foreign key, or check can still pass; implicit autoindexes are excluded.

Compare structured PRAGMA table_xinfo, PK ordinal, affinity/type, not-null, default expression, foreign_key_list, index_list/index_xinfo including uniqueness/origin, plus canonical table SQL for check, STRICT, and WITHOUT ROWID. Keep named index/trigger comparisons. Mutation-test removal of each constraint, especially trade_proposals.idempotency_key uniqueness.

### SYS-P2-013 — Session horizon can mature on a weekend

**Where**

- ml/contracts.py:491-507
- assistant/storage.py:2529-2547, 2821-2857
- correct normal path: ml/shadow.py:135-179, 237-273

A Friday horizon-one record can declare Saturday availability because generic/storage validation uses calendar days, then attach an outcome before Monday's session close. Normal shadow code computes sessions correctly, but the durable boundary trusts direct callers.

Move exchange-session resolution to a neutral shared calendar module. Persist target_session and independently derive it in storage from as_of_session plus horizon_sessions; require availability no earlier than exchange close and matured_at no earlier than canonical availability. Use additive nullable migration; legacy rows lacking proof cannot accept outcomes. Test weekends, holidays, half-days, malicious direct storage calls, delayed availability, and legacy rows.

## 10. Detailed P3 system findings

### SYS-P3-001 — Reconciler timing parameters accept invalid numbers

**Where**

- assistant/order_reconciler.py:301-326, 608-636, 788-790

max_order_age_minutes is not validated; interval checks let NaN pass. Negative age can cancel every order, while NaN may disable cancellation or break waiting. Validate every timing input as finite and within explicit positive/nonnegative bounds before broker contact/thread/state mutation; require aware now. Test negative, NaN, and Infinity for every argument.

### SYS-P3-002 — Budget reporting drops malformed fill rows

**Where**

- assistant/storage.py:4187-4265

Malformed event_at or fill quantity/price is skipped, understating filled notional without an integrity result. Reservations remain authoritative, so this is P3. Reject malformed evidence at ingestion; reporting must return integrity_errors and degrade readiness. Test malformed/naive/future time and NaN/Infinity/negative quantity/price while proving reservation enforcement stays conservative.

### SYS-P3-003 — Authorization TTL/replay defense is weak

**Where**

- risk/execution_gate.py:419-559

TTL accepts bool/float/negative/unbounded values. Single-use verification performs check then set without synchronization; two threads could theoretically pass. The atomic proposal claim protects the current primary path, limiting impact.

Require a small bounded integer TTL excluding bool, preferably an internal constant. Guard prune/check/consume with one lock or persistent atomic consume primitive. Test all invalid TTL types/ranges and a two-thread barrier proving exactly one verification succeeds.

## 11. System remediation dependency order

This ordering minimizes the chance that one safety repair is invalidated by another. Use one bounded implementation branch per coherent milestone and require Claude's independent review of the exact pushed commits under the current owner workflow.

### SYS-FIX-0 — Containment and tests first

- Disable new non-risk-reducing paper dispatch through an owner-approved operational action; preserve cancel and legitimate risk-reducing sell paths.
- Write deterministic failing tests for all six P1 findings before production changes.
- Pin exact policy, account, database, and broker fake fixtures.
- Do not roll the evidence epoch merely to run unit tests.

### SYS-FIX-1 — Strict primitives

- Strict numeric/policy parser, excluding bool and nonfinite values.
- Canonical Decimal parser and exact order/fill fields.
- One strict broker-order/open-order validator and recognized status vocabulary.
- Account-scoped broker session identity.

### SYS-FIX-2 — Account snapshot and authorization

- Execution-owned coherent snapshot.
- Broker equity reconciliation.
- Authorization bound to account/mode/snapshot/policy.
- Same-client preflight and submit.

### SYS-FIX-3 — Dispatch containment

- Cross-process dispatch fence/lease.
- Kill-switch and cancel-all drain semantics.
- Atomic anomaly parking, halt, and alert.
- Malformed open-order fail-closed behavior with independent emergency cancellation.

### SYS-FIX-4 — Durable exactness and integrity

- Text-decimal fill migration.
- Duplicate-event content hash and stored-event replay.
- Semantic SQLite schema verifier.
- Unknown status/readiness behavior.
- Temporal-integrity contracts.

### SYS-FIX-5 — Supporting-system correctness

- Canonical portfolio snapshot and report parity.
- Risk-reducing earnings exception.
- Market-data semantic health.
- Shared backtest configuration validators.
- Watchdog policy parity.
- Session-based ML maturity.

### SYS-FIX-6 — Independent proof

For each P1:

- focused red/green test;
- dangerous-direction mutation;
- concurrent barrier/fault-injection test where applicable;
- restart/recovery test for durable state;
- full suite and compileall;
- exact commit-by-commit review;
- paper-only fault drill with a fake broker;
- explicit proof of zero live authority and no policy relaxation.

No live deployment discussion begins until the P1 ledger is closed and the existing promotion checklist independently passes.

## 12. Cross-cutting implementation rules

### 12.1 One concept, one authoritative boundary

- Numeric decisions use Decimal/text exact values; floats are presentation only.
- Exchange-session time is resolved once by a shared calendar contract.
- Broker order identity/status/fill validation occurs in one validator used by every transport path.
- Account identity is bound once and carried through authorization and submit.
- Persisted evidence is strict, typed, exact-keyed, content-addressed, and semantically revalidated on load.

### 12.2 Fail closed without blocking risk reduction

Unknown account/order/data/time/state blocks new exposure. It must not block cancel-all or a proven risk-reducing sale. Separate attribution/normal validation from the minimal evidence needed to reduce risk.

### 12.3 No silent coercion

Reject bool-as-number, unknown enums, unverified timezone assumptions, unknown schema keys, nonfinite values, and malformed persisted rows. Do not convert them to zero, mean, UTC, accepted, unavailable-with-success, or a skipped row.

### 12.4 No result-driven specification

Every V2 formula fallback, topology, control, threshold, universe, cost, and evaluation cell is frozen before outcomes. A valid null stops the canonical family. ETF aggregation cannot rescue a null stock signal.

## 13. Known or explicit future work not counted as defects

The following are important gates but were not misrepresented as completed code:

- no Analyst Revisions V2 stock signal, outcome study, ETF reverse index/score, portfolio, or QC algorithm exists;
- the corrected V2 canonical event artifact is intentionally not materialized;
- PIT security master, sector history, prices/corporate actions, terminal returns, ETF holdings, eligibility, and peer data are not yet acquired/accepted;
- Snapshot B amendment/deletion/restatement semantics and provider processing rights remain unresolved;
- physical project separation, allocation scatter, duplicated risk-cap arithmetic, and ML promotion are documented architecture/roadmap debt;
- the accepted same-day-open realism limitation is distinct from SYS-P2-010's invalid parameters;
- no predictive analyst edge is currently confirmed.

Do not migrate the superseded V1 event artifact into V2. Rebuild V2 from authenticated raw evidence under the new contract.

## 14. Commit-by-commit disposition

The coordination/documentation range was reviewed from 6156ef9 through 79d3732, plus merge 62b716f. These commits do not implement the V2 strategy or change execution code.

| Commit | Disposition | Reason |
|---|---|---|
| c9dcdb6 | **Rejected as implementation authorization; retained as planning baseline** | It honestly establishes the three lanes, but the analyst milestone order/holdout wording and unresolved blueprint contracts in AR-P2-006 through AR-P2-017 prevent implementation-ready acceptance. |
| d00c0e0 | **Accepted after correction** | Main three-strategy direction is sound after amendments in c88ac4f/a6cc4fb. |
| c88ac4f | **Accepted after correction** | Review amendments added isolation/shared-holdout protections; a null-result/coordination defect was corrected by a6cc4fb. |
| a6cc4fb | **Accepted** | Corrects reviewed coordination gates and preserves the stock-first/null-stop logic. |
| bcd2e79 | **Accepted as historical review record** | Records the then-current counter-review; later workflow change is explicitly historical. |
| f4dbd95 | **Accepted after finalization** | Handoff state was completed/corrected by later commits. |
| 80e76e7 | **Accepted** | Records clean detached validation and final direction state. |
| 9b2643a | **Accepted** | Removes the Codex counter-review step in accordance with the later owner decision. |
| 79d3732 | **Accepted** | Adds isolated counter-review validation evidence; no production change. |
| 62b716f | **Accepted** | Merge tree is byte-identical to 79d3732 and contains no additional conflict-resolution change. |

This commit disposition does not close the open issue ledger. It distinguishes accurate coordination history from authorization to implement an under-specified strategy.

## 15. Validation evidence

### Analyst-focused verification

- 135 focused tests passed in 3.07 seconds:
  - tests/test_acer_normalization.py
  - tests/test_acer_identity.py
  - tests/test_acer_capability.py
  - tests/test_benzinga_ratings_audit.py
  - tests/test_analyst.py
  - tests/test_analyst_target.py
- Read-only Snapshot A dry run:
  - 587,046 raw rows;
  - 584,916 accepted events;
  - 2,130 refusals;
  - 29,187 events conservatively deferred beyond action date;
  - 9,677 tickers;
  - 507 firms.
- Refusals reproduced: 2,008 missing rating, 46 inconsistent transition, 39 update-before-action, and 37 missing firm.
- The governing PDF SHA-256 matched its active record.
- All 64 PDF pages were text-extracted and visually reviewed.

### Full project verification

- Independent full suite at c9dcdb6: **4,571 passed, 25 known warnings in 1,697.13 seconds**.
- The warnings were existing websockets.legacy and joblib/NumPy deprecations.
- The production code audited is byte-identical to the original 9b2643a snapshot.
- Static secret scan found placeholders but no concrete committed credential.
- No broker, provider, QuantConnect, or real-outcome call was made by this review.

### Reproductions performed

- Empty/hash-valid and string-boolean snapshot manifests accepted.
- Underfilled normalized outputs accepted under a valid source hash.
- Safety-shaped unknown identity keys accepted.
- URL credential redaction missed case/alias variants.
- Legacy nonfinite target/close behavior reproduced.
- ETF N_eff near-zero counterexample calculated.
- Bool policy cap/reserve weakening reproduced.
- Mid-capture portfolio incoherence reproduced with a fake broker.
- Duplicate-event journal/projection divergence and malformed-order skip were traced through their transaction/projection paths.

## 16. Acceptance checklist for closing this review

This review may be marked corrected only when:

1. every P1 has a merged correction, focused regression, mutation proof, concurrency/fault proof, and independent exact-commit review;
2. ARV2 has an owner-approved normative erratum and content-addressed executable ARV2-0 spec;
3. snapshot, normalization, dataset, and row loaders prove semantic completeness, exactly-once coverage, strict schema, and code/config lineage;
4. corrections/withdrawals and point-in-time replay pass Snapshot B tests;
5. milestone order is stock study before ETF construction and lane code cannot access the shared final holdout;
6. all strategy formulas and fallbacks pass golden/dangerous-direction tests;
7. legacy analyst outcome entry points refuse unregistered calls;
8. all P2/P3 dispositions are either fixed and verified or explicitly owner-accepted with rationale and a durable follow-up gate;
9. the complete suite, compileall, diff check, schema migrations, restart tests, and static secret scan pass on the final exact commit;
10. the relevant implementation/review records and session handoff are updated only through the owner-authorized workflow;
11. no shared checkout is used for concurrent implementation/review;
12. no outcome, provider, paper deployment, epoch roll, or live promotion is inferred from code completion.

## 17. Recommended owner decisions before implementation

The owner should explicitly decide:

- whether new paper buys are paused until the six P1 findings close;
- the exact V2 date-only timing rule;
- institution/common-event independent-evidence unit;
- sparse/zero-MAD fallback;
- normative ETF N_eff erratum;
- holdings instrument scope and completeness source;
- deterministic hysteresis/cap state machine;
- exact confounder/control set;
- lane validation periods versus the untouched shared integration holdout;
- provider authority for Snapshot B and processing/transfer rights;
- the ARV2 schema/package name and whether V1 remains permanently read-only.

Until those decisions are frozen, implementation should stop at synthetic contract work and must not observe real outcomes.
