# Remediation Ledger — Analyst Revisions V2 and Full Project

**Prepared:** 2026-08-26
**Implementation role:** Codex
**Source audit:** [REVIEW_2026-08-26_ANALYST_REVISIONS_AND_FULL_PROJECT.md](REVIEW_2026-08-26_ANALYST_REVISIONS_AND_FULL_PROJECT.md)
**Implementation branch:** `codex/full-review-p1-remediation-20260826`
**Disposition:** implementation corrections assembled; acceptance is intentionally withheld
**Trading/research authority:** none

## 1. Purpose, status vocabulary, and non-authority statement

This document is the durable HOW/WHERE remediation companion to the original
audit. It does not replace, shorten, or delete the original findings. Every
original finding remains traceable below, and adversarial review findings found
during remediation receive separate stable IDs. The original audit remains the
record of what was wrong; this ledger records the correction boundary and the
evidence an independent reviewer must reproduce.

Every item uses the same deliberately narrow implementation status:

> **Implemented — pending required independent review/counter-review.**

That phrase means code and regression coverage have been assembled on the
implementation branch. It does **not** mean the finding is independently
closed, the milestone is complete, a strategy is valid, or an operational path
is approved. Final disposition requires the owner-mandated sequence: review of
the exact pushed implementation snapshot, correction of any confirmed review
findings, Codex counter-review of the exact reviewed snapshot, final exact-tree
validation, and the associated records/handoff.

No P0 was found in the original audit or the adversarial remediation review.
No strategy outcome was imported or observed. No permanent real-data research
look was consumed. No provider, licensed-data, QuantConnect, quality-control,
broker, paper-account, or live-account operation was performed. No deployment,
scheduler change, evidence-epoch roll, policy relaxation, or live promotion was
performed or authorized. Synthetic and local fixture tests prove software
behavior only; they do not prove market edge or readiness.

The current fail-closed state has distinct gates that must not be conflated:
the reviewed-spec registry is empty; the permanent-look declaration is
`zero_access` because no external append-only spend authority exists; and the
canonical checked-in research-source authority declares exact zero access and
has no positive production-registration path. The ETF cross-section/nonempty-
portfolio boundary also refuses unconditionally because its universe/rank/tie/
inverse-volatility derivation is not owner-frozen. A synthetic fixture can test
refusal behavior, but it cannot register production bytes or lift any gate.

## 2. Coverage summary

| Area | Original P1 | Follow-up P1 | Final P1 | Original P2 | Follow-up P2 | Final P2 | Original P3 | Follow-up P3 | Final P3 | P0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Research / Analyst Revisions V2 | 0 | 14 | 2 | 17 | 11 | 0 | 7 | 2 | 0 | 0 |
| Remaining project | 6 | 5 | 19 | 13 | 4 | 4 | 3 | 2 | 0 | 0 |
| **Total** | **6** | **19** | **21** | **30** | **15** | **4** | **10** | **4** | **0** | **0** |

The 46 original findings, 38 first-follow-up findings, and 25 final-adversarial
findings are all mapped below. The aggregate is explicit: **P0=0, P1=46,
P2=49, P3=14, total=109**. Follow-up IDs use `AR-FU-*` and `SYS-FU-*`; final
adversarial IDs use `AR-FINAL-*` and `SYS-FINAL-*`. Both are additive to, not
replacements for, the original audit IDs.

---

# Part I — Research Layer and Analyst Revisions V2

## 3. Research coverage map

| ID | Priority | Correction boundary | Primary regression evidence |
|---|---:|---|---|
| AR-P2-001 | P2 | Strict typed V2 snapshot verifier and non-publishable diagnostic type | `tests/analyst_revisions_v2/test_snapshot_and_normalization.py` |
| AR-P2-002 | P2 | Exactly-one normalization disposition plus commit/config/package lineage | `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py` |
| AR-P2-003 | P2 | Exact-key, canonical JSON/JSONL, typed artifact loader | `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py`, `tests/test_acer_normalization.py` |
| AR-P2-004 | P2 | Lane-owned canonical event/revision contract and PIT replay | `tests/analyst_revisions_v2/test_snapshot_and_normalization.py` |
| AR-P2-005 | P2 | Legacy runner quarantine and transitive import firewall | `tests/test_analyst_revisions_v2_legacy_quarantine.py`, `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py` |
| AR-P2-006 | P2 | Zero-safe effective-contributor formula without epsilon normalization | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-007 | P2 | Institution/catalyst-level independent breadth | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-008 | P2 | Hard admissibility before reliability | `tests/test_analyst_revisions_v2_contracts.py`, `tests/analyst_revisions_v2/test_snapshot_and_normalization.py` |
| AR-P2-009 | P2 | Exchange-calendar availability contract, including conservative date-only delay | `tests/analyst_revisions_v2/test_snapshot_and_normalization.py`, `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-010 | P2 | Structural-zero/invalid distinction and sparse-group refusal | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-011 | P2 | Authenticated complete holdings book and derived coverage/lag evidence | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-012 | P2 | Dimensionally coherent NAV-return cost model | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-013 | P2 | Deterministic state machine and simultaneous constrained allocation | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-P2-014 | P2 | Reliability terminology; no uncalibrated confidence claim | `tests/test_analyst_revisions_v2_contracts.py`, active-document checks |
| AR-P2-015 | P2 | Explicit provider-era classification and hard pre-2013 quarantine | Analyst snapshot/dataset/contract tests |
| AR-P2-016 | P2 | Stock-first milestone order pinned in active records/tests | `tests/test_active_document_consistency.py` |
| AR-P2-017 | P2 | Externally reviewed preregistration plus zero-access outcome boundary pending external spend authority | `tests/test_analyst_revisions_v2_preregistration.py` |
| AR-P3-001 | P3 | Issuer diagnostic requires typed validated dataset identity | `tests/test_acer_identity.py` |
| AR-P3-002 | P3 | Transitive local-import closure, including dynamic/parent-package paths | Analyst firewall and project-separation tests |
| AR-P3-003 | P3 | Structural, case-insensitive credential redaction | `tests/test_benzinga_ratings_audit.py` |
| AR-P3-004 | P3 | Strict finite target/close and explicit aggregation semantics | `tests/test_price_target_data.py`, `tests/test_analyst_target.py` |
| AR-P3-005 | P3 | Horizon-aware bootstrap wrapper | `tests/test_analyst_revisions_v2_statistics.py` |
| AR-P3-006 | P3 | Active-document precedence/lower-bound/current-ticker guards | `tests/test_active_document_consistency.py` |
| AR-P3-007 | P3 | Stock-first/QC-history factual documentation corrections | `tests/test_active_document_consistency.py` |
| AR-FU-P1-001 | P1 | Private reviewed-spec authority anchored to independent Git review | `tests/test_analyst_revisions_v2_preregistration.py` |
| AR-FU-P1-002 | P1 | Semantic validation of every frozen cell and contaminated-period exclusion | `tests/test_analyst_revisions_v2_preregistration.py` |
| AR-FU-P1-003 | P1 | Local-ledger authority removed; zero-access until external append-only spend authority exists | `tests/test_analyst_revisions_v2_preregistration.py` |
| AR-FU-P1-004 | P1 | Canonical `arv2_ds_<sha256>` dataset identity accepted and bound | `tests/test_analyst_revisions_v2_preregistration.py` |
| AR-FU-P1-005 | P1 | Pre-2013 rows cannot be accepted or year-laundered | Analyst snapshot/dataset tests |
| AR-FU-P1-006 | P1 | Loader-only `VerifiedSnapshot` with out-of-band identity and full byte revalidation | `tests/analyst_revisions_v2/test_snapshot_and_normalization.py` |
| AR-FU-P1-007 | P1 | Loader-only `NormalizedDataset`; accepted/refused disposition and refusal applicability revalidated | Analyst snapshot/normalization/dataset tests |
| AR-FU-P1-008 | P1 | Missing/invalid stock observations refuse; only explicit structural zero contributes zero | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P1-009 | P1 | Formula, holdings, rank-threshold, allocation, and cost rules derive from one authenticated reviewed policy | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P1-010 | P1 | Reviewed-policy identity held outside the value; clone/mutate/self-rehash and fixture-only positive bypass refuse | Analyst preregistration/contract tests |
| AR-FU-P1-011 | P1 | Loader-authenticated score artifact binds policy, normalized dataset lineage, derivation, decision, epoch, and exact typed score set | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P1-012 | P1 | Arbitrary rank bytes and every nonempty portfolio remain zero-access until a reviewed complete rank/volatility derivation exists | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P1-013 | P1 | Terminal exception proves and exactly liquidates an authenticated positive long position | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P1-014 | P1 | Portfolio consumption recursively revalidates every nested authority object | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-001 | P2 | Holdings source/content hash, complete denominator, derived lag, frozen thresholds | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-002 | P2 | Simultaneous proportional cap scaling | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-003 | P2 | Authenticated classification evidence bound to ETF/holdings/decision | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-004 | P2 | Typed PIT terminal-exit evidence and conservative missing-ADV treatment | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-005 | P2 | INVALID observations hard-refuse the group | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-006 | P2 | Canonical checked-in zero-access source authority makes self-attested holdings/stock-score/classification/cost/PIT bytes non-authoritative | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-007 | P2 | Mixed-time nonempty cross-sections remain zero-access pending one reviewed simultaneous-context derivation | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-008 | P2 | Exact sector mass and non-dilutable overlap-cluster membership | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-009 | P2 | Holdings effective/decision lag is derived on canonical NYSE sessions | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-010 | P2 | Every cost and terminal row binds the requested decision, epoch, policy, and source context | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P2-011 | P2 | Fixed Decimal context and canonical ordering across score, allocation, and cost calculations | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P3-001 | P3 | Canonical holdings identity and unmapped-category refusal | `tests/test_analyst_revisions_v2_contracts.py` |
| AR-FU-P3-002 | P3 | Missing legacy artifact maps to named quarantine exception | `tests/test_analyst_revisions_v2_legacy_quarantine.py` |
| AR-FINAL-P1-001 | P1 | Canonical checked-in zero-access source authority; no runtime production re-registration | Analyst contracts and source-authority mutation tests |
| AR-FINAL-P1-002 | P1 | Accepted rows prohibited until a deterministic provider-specific raw-to-canonical normalizer exists | Analyst snapshot/normalization/dataset tests |

## 4. Original P2 research findings

### AR-P2-001 — Snapshot verification authenticated bytes, not semantic completeness

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the legacy verifier treated a hash-valid manifest as proof of
  completeness, coerced truthy values, and returned the same publishable shape
  for complete and incomplete captures.
- **HOW and WHERE:** `research/analyst_revisions_v2/snapshot.py` now defines
  `VerifiedPage`, `VerifiedPartition`, `VerifiedSourceRow`, `VerifiedSnapshot`,
  and the deliberately non-publishable `IncompleteDiagnosticSnapshot`.
  `load_snapshot`/`load_verified_snapshot` require canonical UTF-8 JSON, exact
  keys and booleans, nonempty contiguous partitions, ordered unique pages,
  in-partition rows, exact counts/hashes, complete file inventory, and stable
  source-row locators. Publication in
  `research/analyst_revisions_v2/dataset.py` accepts only the verified type.
- **Safety invariant:** a diagnostic, partial, empty, mispartitioned, or
  unreferenced capture cannot become canonical V2 evidence merely by carrying
  internally consistent hashes.
- **Regression evidence:** snapshot tests cover string booleans, zero-row
  captures, gaps/duplicates, page/count/hash drift, unreferenced files,
  noncanonical JSON, and diagnostic-type publication refusal.
- **Residual owner/data decision:** no real provider capture was verified or
  published; Snapshot B comparability and provider amendment/deletion semantics
  remain data-contract gates.

### AR-P2-002 — Dataset identity lacked exactly-once coverage and producing lineage

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** identity could be rebuilt from loose accepted/refused lists
  without proving one terminal disposition per source row or binding the
  producing code/configuration.
- **HOW and WHERE:** `research/analyst_revisions_v2/normalization.py` defines
  `NormalizationProvenance`, `NormalizationResult`, and
  `compute_build_recipe_sha256`; it binds every event/refusal to an authenticated
  `SourceRowLocator` and rejects dropped, duplicate, extra, or overlapping
  dispositions. `research/analyst_revisions_v2/dataset.py` captures a clean Git
  commit, package-source SHA-256, schema/config/build-recipe hashes, snapshot
  identity, and counts in `NormalizedDatasetManifest`. The legacy ACER loader in
  `research/acer/dataset.py` was also narrowed to typed validated identity.
- **Safety invariant:** every authenticated source row has exactly one terminal
  fate, and any change in source, schema, configuration, build recipe, package
  source, or producing commit changes/refuses the dataset identity.
- **Regression evidence:** tests mutate row coverage, provenance, config,
  package source, dirty/ignored source, and Git commit lineage and expect refusal.
- **Residual owner/data decision:** the clean-lineage machinery is fixture-tested;
  no licensed real artifact or evidence epoch was created.

### AR-P2-003 — Frozen loader was not a strict persisted-evidence boundary

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** unknown safety-shaped manifest fields and unparsed JSONL rows
  could survive byte-hash checks and be returned to callers.
- **HOW and WHERE:** canonical primitives in
  `research/analyst_revisions_v2/canonical.py` reject duplicate keys, nonfinite
  JSON, noncanonical bytes, path traversal, unknown fields, malformed IDs, and
  ambiguous timestamps. `publish_normalized_dataset` writes canonical sorted
  JSONL into a new immutable directory; `load_normalized_dataset` hashes before
  parsing, enforces exact schemas/order/uniqueness/disjointness, reconstructs
  typed frozen records, and rejects unreferenced files. `load_validated_identity`
  in `research/acer/dataset.py` closes the legacy dictionary-shaped boundary.
- **Safety invariant:** persisted bytes are not trusted because their filenames
  or partial hashes look right; the loader re-establishes the entire frozen
  semantic contract before returning authority-shaped evidence.
- **Regression evidence:** unknown keys, malformed/canonicality drift,
  nonfinite JSON, duplicate IDs, out-of-order rows, tampered files, unsupported
  versions, and unreferenced files all have refusal tests.
- **Residual owner/data decision:** old ACER artifacts remain legacy foundation
  evidence and are not silently reinterpreted as V2.

### AR-P2-004 — V1/V2 ambiguity and missing correction lineage

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the V1 marketing/version label could be mistaken for Analyst
  Strategy V2, and a current-state row could not represent revisions,
  withdrawals, permanent identities, or as-known-at-time replay.
- **HOW and WHERE:** the separate
  `research/analyst_revisions_v2/` package owns V2. In `contracts.py`,
  `CanonicalSourceEvent`, `RevisionKind`, `EventState`, availability/rating
  enums, `validate_revision_lineage`, and `materialize_events_as_of` bind raw
  locator/hash, provider and immutable event-version IDs, revision sequence,
  supersession, state, four time concepts, stable institution/analyst/issuer/
  security/share-class identities, historical ticker validity, ontology,
  mapping evidence, and producing lineage. Snapshot absence never synthesizes
  a tombstone.
- **Safety invariant:** later corrections/withdrawals do not rewrite what was
  known earlier, and a legacy ACER row cannot enter the V2 typed loader.
- **Regression evidence:** original→correction→withdrawal, late/equal-time
  revision, absent-row ambiguity, ticker reuse, share classes, firm rename,
  field loss, unknown fields, and impossible chains are tested.
- **Residual owner/data decision:** actual provider amendment/deletion behavior
  and processing/transfer rights still require evidence and owner acceptance.

### AR-P2-005 — Rejected legacy analyst outcome paths remained runnable

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** two convenience scripts could fetch mutable outcomes without a
  V2 spec, immutable lineage, registered look, or holdout latch.
- **HOW and WHERE:** `research/analyst_revisions_v2/legacy_reproduction.py`
  exposes `quarantine_legacy_runner` and a strict immutable reproduction
  registry. `scripts/run_analyst_target_significance_check.py` and
  `scripts/run_execution_timing_revalidation.py` call the quarantine before any
  fetch/outcome read. `import_firewall.py` computes the transitive local import
  closure and rejects legacy analyst targets, outcome, broker, network, and
  authority modules from V2.
- **Safety invariant:** a default/unregistered/missing/network-backed legacy run
  refuses before reading an outcome and cannot update active V2 evidence.
- **Regression evidence:** default runners are monkeypatched to prove fetch is
  never reached; unregistered/missing artifacts raise the named quarantine
  error; safe-looking transitive/dynamic import bypasses refuse.
- **Residual owner/data decision:** the reproduction registry remains a
  quarantine mechanism, not authority to rerun historical results.

### AR-P2-006 — ETF effective-contributor formula failed at and near zero

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** epsilon was placed in the probability denominator, so weights
  did not sum to one and zero/tiny mass could yield infinite or enormous breadth.
- **HOW and WHERE:** `effective_contributors` in
  `research/analyst_revisions_v2/formulas.py` validates finite Decimal
  contributions, returns zero score/breadth/reliability at the frozen numerical
  zero boundary, and otherwise computes the algebraically equivalent
  inverse-Herfindahl ratio `total^2 / sum(value^2)` with canonical stable Decimal
  sums and analytical `[1, contributor_count]` bounds.
- **Safety invariant:** one contributor has breadth one regardless of magnitude,
  `k` equal contributors have breadth `k`, and zero evidence cannot manufacture
  reliability.
- **Regression evidence:** zero, tiny singleton, ordinary singleton, equal and
  dominant contributors, and invalid numerics are golden-tested.
- **Residual owner/data decision:** the immutable source PDF is not edited; the
  correction must remain recorded as a normative erratum in the associated
  strategy record after the review chain.

### AR-P2-007 — Raw event count was treated as independent evidence

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** deduplication at institution/security/day still let repeated
  institutions and one common catalyst multiply apparent breadth.
- **HOW and WHERE:** `IndependentContribution`, `EvidenceBreadth`, and
  `independent_evidence_breadth` in `formulas.py` aggregate by stable institution
  and common-event cluster; raw intensity remains distinct from independent
  reliability.
- **Safety invariant:** correlated repetitions can affect a diagnostic but
  cannot masquerade as additional independent news.
- **Regression evidence:** five events from one firm, five independent firms,
  fifteen firms around one catalyst, mixed clusters, and dominant contributors
  are covered.
- **Residual owner/data decision:** real common-event identifiers and clustering
  quality have not been audited; they remain prerequisite data evidence.

### AR-P2-008 — Soft quality could admit hard-invalid rows

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** timing, ontology, and identity validity were multiplied into a
  fractional quality score instead of being prerequisites.
- **HOW and WHERE:** strict enums/contracts in `contracts.py`, named refusals in
  `normalization.py`, and `SignalObservation`/`ObservationState` plus
  `analyst_reliability` in `formulas.py` separate binary admissibility from
  post-admission evidence quality.
- **Safety invariant:** ambiguous timing, mapping, ontology, or revision state
  never enters stock/sector/ETF cross-sections or reliability arithmetic.
- **Regression evidence:** malformed timing/mapping/enum rows and INVALID
  observations are rejected before normalization and aggregation.
- **Residual owner/data decision:** actual ontology/mapping sources are absent;
  code cannot convert missing evidence into admissibility.

### AR-P2-009 — Date-only event timing differed by one session

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** V1 selected the next session after the date while the V2
  blueprint literally required the next-session open plus one conservative day.
- **HOW and WHERE:** `derive_event_availability` and `prove_timing_order` in
  `availability.py` use neutral exchange-calendar functions from
  `data/exchange_calendar.py`. Exact timestamp evidence uses the first open
  strictly after publication; date-only evidence waits two exchange sessions.
  Timing and eligibility are stored as aware instants/session labels.
- **Safety invariant:** ambiguous/date-only evidence can be late but never one
  session early; holidays, half-days, weekends, and DST use the exchange
  calendar rather than calendar arithmetic.
- **Regression evidence:** Tuesday, Friday, holiday, half-day, exact open,
  intraday/after-close, and inconsistent clock cases are covered.
- **Residual owner/data decision:** this implements the literal conservative V2
  reading; any later owner amendment requires a new reviewed spec/evidence epoch.

### AR-P2-010 — Sparse and zero-MAD normalization was undefined

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** epsilon was acting as fake scale in zero-inflated groups, and
  missing, invalid, no-event, and structural-zero observations were conflated.
- **HOW and WHERE:** `ObservationState`, `SignalObservation`,
  `RobustNormalization`, and `robust_group_normalize` in `formulas.py` encode
  structural zero separately, enforce minimum total/active observations, use
  valid point-in-time groups, and return a named unavailable/refusal state for
  sparse or zero-MAD evidence rather than dividing by epsilon.
- **Safety invariant:** sparse degeneracy cannot become an extreme clipped score;
  invalid rows never disappear into a neutral zero.
- **Regression evidence:** all-zero, one-active, small group, ties, structural
  zero versus invalid, and zero-MAD cases are tested.
- **Residual owner/data decision:** any alternative pooled/rank fallback is a new
  preregistered design choice, not a runtime convenience.

### AR-P2-011 — Mapping percentage did not prove a complete holdings book

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** coverage used only supplied rows, so an omitted slice of a fund
  could still report 100% mapped; lag, denominator, duplicate identity, and
  non-equity treatment were caller assertions.
- **HOW and WHERE:** `Holding`, `HoldingsSnapshot`, and
  `build_verified_holdings_snapshot` in `holdings.py` authenticate source bytes/
  digest, canonical permanent identities, complete declared long-equity book,
  unique positions, total weight within a frozen 0.1% tolerance, explicit
  instrument/mapping state, effective/available instants, and content SHA-256.
  `verify_holdings_evidence` derives the complete candidate set, session lag,
  fixed 99% mapped threshold, coverage, and eligibility. `weighted_stock_score`
  accepts only that typed evidence.
- **Safety invariant:** omitted/unmapped/stale positions stay in the denominator;
  callers cannot relax book completeness, lag, or coverage at aggregation time.
- **Regression evidence:** unregistered/unsorted source and unreconciled-book
  cases refuse; unmapped weight remains in the denominator; omitting a candidate
  position refuses; content mutation is detected; and not-yet-available, stale,
  and NYSE-session-boundary cases are distinct.
- **Residual owner/data decision:** a real PIT holdings vendor, NAV/declared-total
  semantics, licensing, and historical completeness have not been accepted.

### AR-P2-012 — Cost equation mixed incompatible units

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a portfolio-return turnover term was added to unweighted
  per-trade impact terms, making split trades change economics mechanically.
- **HOW and WHERE:** `TradeCostInput`, `CostResult`, and
  `portfolio_transaction_cost` in `costs.py` compute all components in dollars
  and divide once by positive NAV. Exact Decimal notional weights commission,
  half-spread, and square-root participation impact; missing/nonpositive ADV
  fails closed unless authenticated terminal evidence invokes conservative
  full-notional cost.
- **Safety invariant:** units remain coherent, buy/sell treatment is symmetric,
  and splitting an economically identical trade does not manufacture lower
  cost.
- **Regression evidence:** hand calculation, split invariance, zero trade,
  symmetry, basis-point scenarios, participation limit, missing ADV, and forced
  terminal exit are covered.
- **Residual owner/data decision:** the reviewed policy fixes the allowed cost
  scenario grid and participation/fee limits; actual commission, spread, impact,
  and ADV values must come from a future independently governed PIT cost source.
  Synthetic tests are not empirical calibration.

### AR-P2-013 — Portfolio hysteresis conflicted with the five-name cap

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** no total order resolved forced exits, retained incumbents,
  stronger entrants, ties, coupled constraints, and residual cash.
- **HOW and WHERE:** caller-constructible `PortfolioRules` is disabled;
  `VerifiedAnalystPolicy`, `PortfolioCandidate`, `PortfolioDecision`,
  `construct_portfolio`, and `_allocate` in `portfolio.py` encode forced
  invalid/stale exits, deterministic rank/identity ordering, incumbent tie
  preference, stronger-entrant eviction, an unbreakable reviewed holdings cap,
  and proportional inverse-volatility water filling. Reviewed ETF/sector/overlap
  caps scale the simultaneous proposal, never sequentially privilege list order;
  infeasible capacity remains cash with named underfill. These are outcome-free
  primitives only: the public cross-section authority now refuses every nonempty
  portfolio until the stock-first/rank milestone is independently reviewed.
- **Safety invariant:** a cap is never relaxed to stay invested and input order
  cannot decide capital allocation.
- **Regression evidence:** the terminal public-boundary regression proves
  arbitrary ranks and every nonempty portfolio remain zero-access, so the
  dormant hysteresis/allocation primitive cannot affect a result in this
  milestone.
- **Residual owner/data decision:** no portfolio outcome or real holdings topology
  was run. Before a later reviewed cross-section authority makes the primitive
  reachable, direct exact-tie, stronger-entrant, forced-exit, coupled-cap,
  permutation, and residual-cash tests must be restored on that exact final API.

### AR-P2-014 — Heuristic evidence quality was called confidence

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a heuristic product of reliability/quality/diversity was named
  as if it were prospectively calibrated probability confidence.
- **HOW and WHERE:** the V2 public function is `analyst_reliability` in
  `formulas.py`; contracts and associated documentation use reliability/evidence
  quality. No pre-calibration V2 output grants a `confidence` interpretation.
- **Safety invariant:** presentation vocabulary cannot imply calibration or
  trading authority that has never been measured.
- **Regression evidence:** contract/document tests inspect the V2 surface and
  terminology.
- **Residual owner/data decision:** `confidence` remains prohibited until a
  separately frozen prospective calibration gate passes.

### AR-P2-015 — Measured pre-2013 rows conflicted with provider-history claims

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** documentation treated 2013 as a start date even though the
  measured snapshot contains earlier rows of unknown backfill semantics.
- **HOW and WHERE:** `ProviderEra`, `ProviderEraDecision`, and
  `classify_provider_era` in `provider_history.py` distinguish observed pre-2013
  rows from admissible-era rows. `normalization.py` requires the named refusal
  `provider_backfill_semantics_unverified_pre_2013`; publication verifies the
  effective-year partition and prevents relabeling an early row into a later
  partition. Active records separate normative design from observed facts.
- **Safety invariant:** existence is reported honestly, but unknown early-history
  semantics cannot influence ontology, warm-up, or outcomes.
- **Regression evidence:** pre-2013 acceptance, wrong refusal, year laundering,
  wrong partition, and improper later-era refusal are tested.
- **Residual owner/data decision:** only provider evidence can resolve the
  backfill semantics; until then quarantine is permanent and fail-closed.

### AR-P2-016 — Milestone order violated the stock-first stopping rule

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the lane record scheduled ETF topology before the decisive
  stock-level stop/go study.
- **HOW and WHERE:** `docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md`
  and the concise sequencing reference in `docs/ACTION_PLAN_2026-08-20.md` now
  place frozen contracts, immutable inputs, and stock-score software before the
  one-shot stock study; ETF topology follows only a valid stock pass.
  `test_analyst_v2_milestones_enforce_stock_first_before_etf_topology` in
  `tests/test_active_document_consistency.py` pins order, not mere name presence.
- **Safety invariant:** expensive topology choices and ETF aggregation cannot
  rescue or tune around a valid null stock hypothesis.
- **Regression evidence:** the active-document guard fails if ETF topology moves
  before stock-first evidence or the null-stop rule disappears.
- **Residual owner/data decision:** the stock study remains unauthorized because
  there is no externally reviewed executable spec or accepted real dataset.

### AR-P2-017 — Preregistration and holdout boundary was not executable

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** prose did not authenticate a complete specification, prove
  independent review, exclude contaminated/shared periods, or durably consume a
  one-shot look.
- **HOW and WHERE:** `preregistration.py` defines all required cells,
  `DraftPreregistration`, privately constructed `ReviewedPreregistration`,
  `OutcomeAccessRequest`, privately constructed `OutcomeAccessPermit`, strict
  semantic validation, an external committed review registry, Git ancestry/
  clean-tree checks, and the checked-in zero-access declaration in
  `specs/permanent_look_authority.json`. The draft is deliberately
  non-executable and `specs/reviewed_spec_registry.json` is empty.
  `run_authorized_outcome_slice` is the sole bounded outcome-return boundary: it
  reauthenticates the reviewed spec, exact snapshot/dataset, clean package code,
  cost cell, topology, dates, horizon, embargo, block, controls, and holdout
  exclusion before requesting a spend receipt. Because no externally pinned,
  cross-machine append-only spend authority exists, the request fails before an
  outcome loader can run.
- **Safety invariant:** no local file, edited/self-reviewed spec, incomplete or
  unregistered request, contaminated period, or holdout-touching slice can
  return outcome bytes; absent external spend authority means zero access, not a
  resettable local approximation.
- **Regression evidence:** missing/edited/self-blessed specs, forged types,
  semantic cell mutations, wrong dataset/code/cost/topology, omitted controls,
  short embargo/block, holdout overlap, local-ledger deletion/substitution,
  repository-authority substitution, permit reuse/wrong slice, and callback
  invocation all refuse. The integration test proves the outcome callback is
  never reached even after all currently authenticable local inputs pass.
- **Residual owner/data decision:** an independent reviewer must create and
  commit a reviewed artifact/registry anchor after owner decisions are frozen.
  Until then the registry intentionally grants zero outcome access.

## 5. Original P3 research findings

### AR-P3-001 — Issuer diagnostic accepted weak dataset-shaped dictionaries

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a caller could supply a plausible ID prefix/count/hash subset
  without authenticating the actual dataset and row lineage.
- **HOW and WHERE:** `build_diagnostic_report` in `research/acer/identity.py`
  requires `ValidatedDatasetIdentity` from
  `research/acer/dataset.load_validated_identity`, verifies that the identity
  covers the complete event set, and persists full contract/content lineage.
  `scripts/report_acer_identity.py` loads the typed boundary.
- **Safety invariant:** a report cannot elevate a dictionary-shaped assertion to
  issuer-identity evidence.
- **Regression evidence:** forged prefix, missing/wrong content, unsupported
  version, count-only input, and incomplete event coverage refuse.
- **Residual owner/data decision:** name/ticker diagnostics remain insufficient
  for permanent PIT security identity and are documented as such.

### AR-P3-002 — Direct-import tests missed transitive authority leaks

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** inspecting only import statements directly inside ACER/V2
  missed a safe-looking local facade that imported outcome or execution code.
- **HOW and WHERE:** `validate_transitive_import_closure` in
  `research/analyst_revisions_v2/import_firewall.py` resolves reachable local
  modules, package initializers, relative imports, and dynamic-import syntax and
  rejects forbidden outcome/network/broker/execution/backtest paths. Project
  separation manifest/tests classify the new neutral modules and research
  entrypoint.
- **Safety invariant:** research-input code cannot acquire authority or outcome
  access indirectly through another repository module.
- **Regression evidence:** facade, parent initializer, relative, and dynamic
  import bypass fixtures fail; the actual V2 closure passes.
- **Residual owner/data decision:** the closure must be rerun whenever local
  package dependencies change.

### AR-P3-003 — Provider URL credential redaction was incomplete

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** redaction matched one spelling/case and exception strings could
  reintroduce credential query values.
- **HOW and WHERE:** `_strip_key` and `_sanitize_exception_text` in
  `scripts/audit_benzinga_ratings.py` parse URL components, decode and case-fold
  query names, redact the credential-name family, preserve safe repeated fields,
  and sanitize exception text before persistence/display.
- **Safety invariant:** mixed-case, alias, encoded, repeated, fragment, or
  exception-shaped URL material cannot disclose a credential value.
- **Regression evidence:** parameterized mixed-case/alias URLs, repeated safe
  keys, and exception-text cases are covered.
- **Residual owner/data decision:** no credential or provider call was used in
  remediation; tests use placeholders only.

### AR-P3-004 — Legacy target code admitted nonfinite values and unknown semantics

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** infinities/NaN could survive calculation, unknown aggregation
  silently became mean, and timezone/session meaning was guessed.
- **HOW and WHERE:** `data/price_target_data.py` adds
  `PriceTargetContractError`, `ConsensusMethod`, strict provider-history schema,
  finite positive targets, exact analyst-count/window rules, and exchange-session
  effective-time validation. `signals/analyst_target.py` rejects nonfinite/
  nonpositive close and invalid thresholds rather than emitting NaN signals.
- **Safety invariant:** malformed legacy advisory data produces no plausible
  analyst signal and remains outside the V2 import closure.
- **Regression evidence:** NaN/Infinity/nonpositive values, unknown method,
  schema drift, half-day/after-close timing, naive timestamps, invalid close,
  and invalid threshold tests exist.
- **Residual owner/data decision:** this only hardens a legacy advisory surface;
  it is not the canonical V2 stock signal.

### AR-P3-005 — Bootstrap block could be shorter than the outcome horizon

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the generic utility documented but did not enforce the
  dependence-length constraint required by overlapping analyst labels.
- **HOW and WHERE:** `run_horizon_aware_block_bootstrap` in
  `research/analyst_revisions_v2/statistics.py` requires exact positive integers
  excluding bool and refuses `block_length_sessions < horizon_sessions` before
  delegating to any statistic.
- **Safety invariant:** the V2 inference path cannot claim a one-session
  bootstrap for a 20-session overlapping outcome.
- **Regression evidence:** 20-versus-1 refusal, exact-boundary delegation, bad
  types/ranges, and import-boundary tests are present.
- **Residual owner/data decision:** real block length, clustering, and power are
  preregistration cells and have not been selected from outcomes.

### AR-P3-006 — Documentation guards did not pin the full semantics

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** tests looked for isolated tokens without requiring that 768 was
  a lower bound rather than an allowlist, forbidding current-ticker joins, or
  separating normative design from observed provider facts.
- **HOW and WHERE:** active analyst records now state the lower-bound/not-
  allowlist meaning, prohibition on current-ticker joins, and normative-versus-
  observed precedence. `tests/test_active_document_consistency.py` asserts these
  propositions across every active analyst summary.
- **Safety invariant:** documentation cannot turn absence of observed identity
  risk into proof of safety or overwrite an immutable normative rule with a
  current vendor observation.
- **Regression evidence:** consistency tests fail when any required phrase or
  precedence relationship is removed.
- **Residual owner/data decision:** the tests protect written claims; they do not
  create the missing security-master evidence.

### AR-P3-007 — Active routing and QuantConnect history were stale

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the mandate said stock-signal work was off-roadmap and active
  facts denied historical QuantConnect research calls despite the durable ledger.
- **HOW and WHERE:** `docs/operations/MANDATE.md`, `README.md`, and
  `docs/operations/OPERATIONAL_FACTS.md` distinguish owner-directed stock-first
  research from execution authority and distinguish historical cloud research
  calls from current authorization. Active consistency tests bind those facts to
  the three-strategy direction and run history.
- **Safety invariant:** acknowledging research history never implies QC execution
  or broker authority, while the roadmap no longer contradicts its stock-first
  lanes.
- **Regression evidence:** active-document tests reject both a stock-first denial
  and a false claim that historical QC calls never occurred.
- **Residual owner/data decision:** no new QC job was run; vendor-to-QC processing
  rights and later QC milestones remain gated.

## 6. Adversarial follow-up research findings

### AR-FU-P1-001 — Reviewed preregistration was forgeable/mutable and lacked an external review anchor

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a frozen dataclass or embedded `reviewed_by` string is still
  caller-constructible; nested cells remained mutable and a producing commit
  could bless its own spec.
- **HOW and WHERE:** `ReviewedPreregistration` is `init=False` and privately
  constructed with an unexported authority token; cells are detached and
  recursively frozen. `_review_anchor`, `_assert_review_authority`, and the
  committed `specs/reviewed_spec_registry.json` require exact canonical artifact
  SHA-256, tracked/clean spec and registry files in one repository, an independent
  review commit that is an ancestor of the current commit, and inclusion of the
  producing commit in the reviewed history.
- **Safety invariant:** self-asserted metadata, post-load mutation, a dirty file,
  or a self-blessed/unrelated commit cannot acquire outcome authority.
- **Regression evidence:** direct construction, nested mutation, edited artifact,
  self-blessed review, dirty registry/spec, and broken ancestry refuse.
- **Residual owner/data decision:** the production reviewed registry remains
  empty until an independent reviewer commits a real anchor.

### AR-FU-P1-002 — Required cells were presence-only and allowed contaminated validation overlap

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a non-null cell did not prove the cell's internal dates,
  controls, topology, labels, purging, costs, universe, or cross-cell relations.
- **HOW and WHERE:** `_validate_semantics` in `preregistration.py` validates every
  required cell's exact nested schema and cross-cell relationships: exchange
  sessions, contaminated/validation/shared-holdout ordering, label/embargo/block
  lengths, corporate actions/terminal returns, universe/structural zeros,
  normalization, stock topology, controls, parity, costs, holdings lag/coverage,
  multiplicity, one-shot periods, and valid-null closure.
- **Safety invariant:** a syntactically complete but semantically contaminated or
  internally contradictory document cannot authorize outcome access.
- **Regression evidence:** a parameterized test mutates every required semantic
  family and proves refusal before spending the look.
- **Residual owner/data decision:** passing semantic validation still requires
  independent substantive review of the choices; it is not scientific approval.

### AR-FU-P1-003 — Permanent looks relied on resettable local state

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** an `unspent` field or even an atomic local SQLite database is
  not permanent authority: deleting, restoring, copying, or substituting the
  file can reset the budget across computers. The earlier local permit also did
  not bind every approved slice/control field.
- **HOW and WHERE:** local SQLite spending was removed from
  `preregistration.py`. `specs/permanent_look_authority.json` declares the only
  truthful current state, `zero_access`. `OutcomeAccessPermit` is init-disabled
  and binds the complete request (dates, horizon, embargo, block, controls,
  topology, cost, dataset, code), reviewed artifact/review commit, family, and
  external receipt identity. `authorize_outcome_access` and permit assertion
  fail closed; `run_authorized_outcome_slice` reauthenticates all actual inputs
  and cannot invoke its outcome loader without a future externally pinned
  append-only receipt.
- **Safety invariant:** deleting or substituting any local database cannot grant
  or reset a look. Until a cross-machine append-only authority can atomically
  spend and reauthenticate a full-request receipt, zero callers win.
- **Regression evidence:** local-ledger creation/deletion/substitution,
  concurrent callers, repository-authority substitution, forged permits,
  wrong-slice reuse, init-disabled permit replacement, and a fully bound runner
  all refuse before outcome bytes are read.
- **Residual owner/data decision:** the owner must select, independently review,
  and operationally govern an external append-only authority, including atomic
  spend, backup, transfer, access control, and incident recovery. Software does
  not pretend that a local database satisfies this gate.

### AR-FU-P1-004 — Outcome gate rejected the canonical V2 dataset identity

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the gate accepted only a generic raw hash form while dataset
  publication emits the namespaced `arv2_ds_<64-hex>` identifier.
- **HOW and WHERE:** `_dataset_id` in `preregistration.py` validates the canonical
  prefix plus exact SHA-256 suffix and is used consistently for spec look
  registration and `OutcomeAccessRequest` binding.
- **Safety invariant:** the gate neither rejects the real canonical artifact nor
  accepts an unnamespaced/short/malformed lookalike.
- **Regression evidence:** canonical ID positive control and wrong prefix/length/
  character cases are covered.
- **Residual owner/data decision:** no real canonical dataset currently exists;
  the fix aligns contracts only.

### AR-FU-P1-005 — Pre-2013 quarantine was advisory rather than enforced

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a prose warning did not stop normalization/publication from
  admitting an early row, substituting another refusal, or labeling it as 2013.
- **HOW and WHERE:** `classify_provider_era` is called by the V2 normalization
  boundary; pre-2013 source rows require exactly
  `provider_backfill_semantics_unverified_pre_2013`. Dataset publication checks
  locator/effective year against partition year and rejects any pre-2013 event or
  any later row carrying the early-era refusal.
- **Safety invariant:** early rows remain observable as measured facts but cannot
  become canonical events or be laundered across a partition boundary.
- **Regression evidence:** 2011/2012 acceptance, wrong/no refusal, year relabeling,
  and 2013-boundary cases are covered.
- **Residual owner/data decision:** quarantine can be lifted only by a new
  provider-semantics decision and lineage change, never by data abundance.

### AR-FU-P1-006 — `VerifiedSnapshot` authority could be cloned or redirected after verification

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** `frozen=True` and a private-looking token do not create
  provenance. `copy`, `dataclasses.replace`, `object.__new__`, or copied token
  state could manufacture a second value, while a consumer that checked only
  scalar hashes could miss replaced manifest/page bytes or a redirected source
  root.
- **HOW and WHERE:** `VerifiedSnapshot` in `snapshot.py` is now `init=False` and
  has no copyable authority field. `_verified_snapshot` records the exact object
  identity, absolute loader root, and a deep fingerprint of every scalar,
  partition, page, locator, and raw row in the private weak-reference
  `_SNAPSHOT_AUTHORITIES` registry. Public
  `revalidate_verified_snapshot` requires that original identity, compares the
  live object with the held-out fingerprint, reloads the bound manifest and all
  page files, reparses their rows, and compares the complete reloaded fingerprint.
  Snapshot locator access, normalization/build-recipe construction, publication,
  and dataset loading call this revalidator rather than trusting a frozen shell.
- **Safety invariant:** neither cloning an authentic object nor preserving its
  visible hashes can mint snapshot authority; post-load mutation, deletion,
  page substitution, row substitution, count drift, or root redirection refuses
  before the snapshot can contribute to a result.
- **Regression evidence:**
  `test_verified_snapshot_cannot_be_replaced_or_token_cloned` and
  `test_every_snapshot_consumer_reloads_bound_manifest_and_pages` exercise
  `dataclasses.replace`/`object.__new__` forgery and on-disk manifest/page drift,
  in addition to the existing completeness and canonical-byte mutations.
- **Residual owner/data decision:** this authenticates one local artifact against
  its loader-observed bytes; it does not establish provider ownership,
  acquisition rights, completeness, or Snapshot B comparability.

### AR-FU-P1-007 — Dataset shells, accepted events, and refusal labels could erase raw rows

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a frozen `NormalizedDataset` remained replaceable: a caller
  could preserve a plausible manifest while removing records. Separately, a
  caller-selected refusal type/digest could turn an otherwise admissible source
  row into a named refusal, and an accepted event could bypass an objectively
  required refusal.
- **HOW and WHERE:** `NormalizedDataset` in `dataset.py` is `init=False`; the
  private weak-reference `_DATASET_AUTHORITIES` registry binds its exact loader
  identity, artifact root, and full manifest/snapshot/event/refusal fingerprint.
  `revalidate_normalized_dataset` revalidates the nested snapshot, reloads and
  hashes the canonical manifest and JSONL files, reconstructs typed records,
  reruns counts/content/result bindings, and compares every field. Publication
  first calls `revalidate_normalization_result`, so a replaced result cannot be
  written. In `normalization.py`, `NormalizationRefusal` is factory-only;
  `evidence_sha256` binds its exact raw-row locator and typed reason, while
  `_applicable_refusal_reason` derives the one applicable reason from the
  authenticated raw row under fixed precedence. `NormalizationResult` rejects
  an event when the row requires refusal and rejects a refusal when no supported
  reason applies.
- **Safety invariant:** every authenticated raw row has exactly one justified
  terminal disposition. Copy/replace forgery, accepted-event laundering,
  invented refusal type, arbitrary digest, and post-load record erasure all
  refuse at every publication/consumption boundary.
- **Regression evidence:**
  `test_refusal_digest_and_type_cannot_be_fabricated_to_erase_a_row`,
  `test_normalized_dataset_is_loader_only_and_revalidates_all_content`, and
  `test_publication_revalidates_result_instead_of_trusting_frozen_shell` cover
  the dangerous directions, alongside dropped/duplicate/extra disposition,
  canonical JSONL, and pre-2013 exact-refusal cases.
- **Residual owner/data decision:** only refusal reasons objectively derivable
  from the current strict raw-row contract are admissible. Provider-specific
  semantics or identity judgments need independently accepted source evidence;
  they cannot be invented by widening this enum.

### AR-FU-P1-008 — Missing stock signals could become investable zeros

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** accepting loose numeric mappings or using a missing-key default
  of zero confounds an observed neutral/structural state with unavailable or
  corrupt evidence. That failure direction can preserve ETF eligibility by
  silently deleting adverse uncertainty.
- **HOW and WHERE:** `SignalObservation` in `formulas.py` has four disjoint typed
  states: `SIGNAL`, `STRUCTURAL_ZERO`, `MISSING`, and `INVALID`. In
  `holdings.py`, the authenticated stock-score artifact must exactly cover every
  mapped holdings security with a matching `SignalObservation`; missing and
  invalid observations hard-refuse artifact loading/ETF scoring, while only an
  explicit `STRUCTURAL_ZERO` becomes numeric zero. Signal values must be finite,
  nonzero, and within the authenticated policy clip.
  `robust_group_normalize` likewise refuses an invalid group and does not admit
  missing rows into its usable cross-section.
- **Safety invariant:** absence, parse failure, or contamination never becomes
  a neutral stock signal. A numeric zero exists only when the upstream contract
  explicitly proves the preregistered structural-zero state.
- **Regression evidence:**
  `test_weighted_score_requires_loader_authenticated_exact_score_artifact` and
  `test_stock_score_artifact_refuses_missing_extra_duplicate_and_invalid_rows`
  remove a mapped security, add/duplicate a security, substitute an untyped
  mapping, supply `MISSING`/`INVALID`, and exceed the clip; all refuse. The
  normalization contract test separately proves invalid-group refusal and
  structural-zero behavior.
- **Residual owner/data decision:** typed state semantics do not by themselves
  authenticate where a signal value came from; the loader-authenticated
  stock-score authority is tracked separately in AR-FU-P1-011.

### AR-FU-P1-009 — Callers could relax policy, ranking thresholds, caps, and cost assumptions

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** individually caller-supplied half-life, clip, minimum breadth,
  holdings lag/coverage, entry/exit rank, maximum holdings, ETF/sector/cluster
  caps, cost grid, participation, and fee values let a call site silently create
  an easier strategy than the reviewed family.
- **HOW and WHERE:** `derive_verified_analyst_policy` in `formulas.py` is the one
  policy-derivation boundary. It consumes a reauthenticated
  `ReviewedPreregistration`, extracts the primary stock topology plus holdings,
  portfolio, and cost cells, and constructs `VerifiedAnalystPolicy` only when
  every canonical ARV2 value matches. `require_verified_analyst_policy` is called
  by normalization, holdings, score, portfolio, and cost consumers. The old
  `PortfolioRules` constructor always refuses; portfolio thresholds and coupled
  caps come from the policy, and the cost call accepts only a scenario in the
  reviewed grid while all other coefficients come from authenticated PIT cost
  evidence.
- **Safety invariant:** a caller may request one preregistered cost scenario but
  cannot lower a threshold, extend staleness, raise a cap, alter rank hysteresis,
  or substitute cheaper assumptions without changing reviewed policy identity
  and being refused.
- **Regression evidence:**
  `test_policy_authority_refuses_caller_authored_rules_or_unreviewed_input`
  rejects caller-authored rules and an unreviewed input and asserts exact policy
  fields; formula, holdings, and cost tests exercise fixed thresholds, scenario
  grid, and participation. Portfolio rule/cap substitution cannot become an
  alternate positive path because every nonempty cross-section is zero-access.
- **Residual owner/data decision:** the fixed values are faithfully enforced,
  not scientifically validated. Changing them requires a new independently
  reviewed preregistration/evidence epoch rather than an API override.

### AR-FU-P1-010 — A policy clone could mutate, self-rehash, and bypass real reviewed-policy derivation

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** an init-disabled or frozen dataclass with an internal digest is
  still self-attesting if a caller can copy its token, mutate a field, and
  recompute the same public hash algorithm. Earlier positive tests also created
  policy-shaped values directly, so they could stay green while the real
  reviewed-spec loader/anchor path was broken.
- **HOW and WHERE:** `_register_policy_authority` holds exact
  `VerifiedAnalystPolicy` object identity and its original evidence digest in a
  private weak-reference registry outside the value. Only
  `derive_verified_analyst_policy(require_reviewed_preregistration(...))`
  registers an object. `require_verified_analyst_policy` requires that exact
  identity, recomputes the digest, and compares every fixed field; the private
  `_create_verified_analyst_policy` helper alone creates no accepted authority.
  `require_reviewed_preregistration` itself rechecks the loader-held fingerprint,
  canonical artifact/registry bytes, clean Git state, and independent review
  ancestry. Contract-test positive setup now creates and loads an actually
  anchored temporary reviewed specification before deriving policy.
- **Safety invariant:** `copy`, `dataclasses.replace`, `object.__setattr__`, token
  copying, and self-rehashing cannot create a second authoritative policy or
  weaken the original; positive tests exercise the public reviewed-authority
  chain rather than a privileged constructor shortcut.
- **Regression evidence:** the policy-authority test mutates a copied ETF cap,
  recomputes its internal digest, and proves the clone remains unregistered.
  Preregistration tests independently mutate/copy reviewed values and their
  nested cells and prove registry/spec/ancestry reauthentication fails closed.
- **Residual owner/data decision:** the temporary Git anchor is synthetic test
  infrastructure. The checked-in reviewed registry remains empty until an
  independent reviewer creates a real reviewed specification anchor.

### AR-FU-P1-011 — ETF aggregation accepted caller-authored stock scores

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** an exact mapping of typed `SignalObservation` values fixed
  missing/zero semantics but not authority: callers could still create any
  in-clip values and thereby choose the ETF score. A digest computed over those
  values would remain self-attestation unless the score artifact also carried
  authenticated dataset, derivation, policy, and time lineage.
- **HOW and WHERE:** `ResearchSourceKind.STOCK_SCORE` and the canonical checked-in
  zero-access source declaration extend the common refusal seam. In `holdings.py`,
  `StockScoreDatasetIdentity` binds canonical dataset ID, normalization result,
  snapshot/manifest, normalizer config/code, build recipe, producing commit/tree,
  evidence epoch, and event/refusal hashes;
  `StockScoreDerivationIdentity` binds derivation ID/config/code and producing
  commit/tree. The strict stock-score parser validates canonical bytes and the
  dormant factory contract requires a dataset ID authorized by the reviewed
  policy, derived/available/decision ordering, and complete valid in-clip rows;
  the public authority boundary nevertheless refuses every source because no
  positive production registration path exists.
  `require_verified_stock_score_evidence` rechecks that identity, external
  digest, policy, and every reparsed field. `weighted_stock_score` now accepts
  only that evidence and requires exact mapped-security coverage plus equality
  with holdings policy, decision instant, and evidence epoch.
- **Safety invariant:** a caller-authored mapping, copied evidence shell,
  substituted bytes, foreign dataset/policy/decision/epoch, missing/extra row, or
  convenient in-clip scalar cannot enter ETF scoring. The checked-in authority's
  exact access set is empty, so no real score artifact currently has authority.
- **Regression evidence:**
  `test_weighted_score_requires_loader_authenticated_exact_score_artifact`,
  `test_stock_score_artifact_refuses_missing_extra_duplicate_and_invalid_rows`,
  and
  `test_stock_score_authority_refuses_clone_mutation_substitution_and_foreign_context`
  cover the naked-map, clone, mutation, source substitution, policy, dataset,
  decision, epoch, completeness, state, ordering, and clip failure directions.
- **Residual owner/data decision:** the source authority and reviewed registry
  intentionally authorize nothing, and no real score derivation was run. A future external
  authority must prove that the embedded normalized-dataset and derivation
  identities correspond to the actual immutable artifacts and clean code; hash
  registration alone is not scientific validation or provider QC.

### AR-FU-P1-012 — Portfolio ranks were arbitrary caller-supplied numbers

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** accepting `peer_rank` and inverse volatility on each portfolio
  candidate let a caller promote one ETF, omit competitors, or mix ranks from
  different universes and times while still satisfying entry/exit thresholds.
  Authenticating a file containing those arbitrary ranks would prove file
  identity, not the complete score-to-rank, tie, universe, and inverse-volatility
  derivation.
- **HOW and WHERE:** the public
  `build_verified_cross_section_evidence` and
  `require_verified_cross_section_evidence` boundaries in `portfolio.py`
  deliberately raise the named `_CROSS_SECTION_ZERO_ACCESS_REASON` for every
  input, even if a private parser fixture has a matching digest.
  Consequently `PortfolioCandidate` cannot acquire a verified cross-section and
  `construct_portfolio` cannot construct any nonempty portfolio; the only public
  result before the stock-first/rank rule is reviewed is 100% cash for an empty
  candidate set. `VerifiedCrossSectionEvidence` and its parser remain
  non-authoritative internal contract scaffolding, not an alternate rank loader.
- **Safety invariant:** no bounded, signed, registered, or otherwise plausible
  rank byte can become portfolio authority until a reviewed specification fixes
  the complete universe, score-to-rank/tie rule, simultaneous PIT context, and
  inverse-volatility derivation. Unsupported ETF topology cannot rescue or tune
  around the stock-first study.
- **Regression evidence:**
  `test_cross_section_and_nonempty_portfolio_are_zero_access_until_rank_rule_is_frozen`
  supplies a synthetic arbitrary-rank parser fixture and proves both its loader and a
  nonempty candidate refuse; the empty all-cash result is the only positive
  control.
- **Residual owner/data decision:** a future owner decision and independent
  review must freeze the rank/universe/volatility derivation after a valid
  stock-level pass. That later milestone must add actual complete-cross-section
  reauthentication and dangerous-direction tests before lifting this zero-access
  boundary.

### AR-FU-P1-013 — A terminal cost exception could create or enlarge a short position

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** treating any negative trade as a forced exit proved direction
  but not the held long quantity. A sell larger than the position could pass the
  missing-ADV exception and create new short exposure; a positive trade could
  also be mislabeled risk-reducing.
- **HOW and WHERE:** registered terminal source bytes in `costs.py` now bind a
  canonical `position_snapshot_id` and positive
  `current_long_position_dollars` in `VerifiedTerminalExitEvidence`.
  `TradeCostInput` accepts terminal evidence only for the same security,
  decision, and evidence epoch and requires `delta_dollars` to equal exactly the
  negated authenticated long position. `portfolio_transaction_cost` reparses
  terminal and trade-cost source bytes before applying the conservative
  missing-ADV path.
- **Safety invariant:** the exceptional path can close exactly one proved long
  position; it cannot buy, partially masquerade as a forced liquidation, sell
  beyond the position, or establish/increase a short.
- **Regression evidence:**
  `test_forced_terminal_exit_requires_registered_matching_pit_evidence` rejects
  a positive trade, an oversize `-101` sale against a `100` long, absent terminal
  evidence, mixed epoch/decision, and unregistered source; exact `-100`
  liquidation is the synthetic positive control and receives full-notional cost
  when ADV is missing.
- **Residual owner/data decision:** no real position snapshot or terminal-event
  source has authority. Execution remains outside this research package; this
  cost exception is not an order instruction.

### AR-FU-P1-014 — Top-level consumers did not revalidate nested evidence

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** validating a nested snapshot/source only when an outer value
  was first constructed left a time-of-check/time-of-use gap:
  `object.__setattr__`, copied inner objects, or substituted source bytes could
  mutate a later argument while the top-level shell still looked valid.
- **HOW and WHERE:** terminal consumers now call the relevant public revalidator
  again. Dataset loading/revalidation calls `revalidate_verified_snapshot`;
  publication rebuilds `NormalizationResult`; `weighted_stock_score` calls both
  `require_verified_holdings_evidence` (which reparses the holdings snapshot) and
  `require_verified_stock_score_evidence` (which checks held-out object identity
  and reparses registered score bytes); cost aggregation revalidates every
  `VerifiedTradeCostEvidence` and nested terminal artifact. Classification
  evidence likewise reparses registered source bytes. The nonempty portfolio
  boundary is additionally zero-access, so an outer candidate cannot be used to
  bypass the still-unreviewed cross-section authority.
- **Safety invariant:** authority must still be valid at the terminal consumer;
  a valid outer dataclass cannot shield a mutated, substituted, foreign, or
  deleted inner artifact.
- **Regression evidence:** snapshot/dataset replace and on-disk mutation tests,
  the stock-score clone/mutation/substitution test, holdings content-mutation
  test, cost/ADV source mutation test, and terminal source/context test exercise
  nested post-construction failures. The nonempty-portfolio zero-access test
  proves a candidate shell cannot provide an alternate route.
- **Residual owner/data decision:** the same recursive-consumer rule must be
  preserved and positively mutation-tested when a future reviewed rank/
  cross-section loader is implemented; no such authority or outcome access was
  implemented here.

### AR-FU-P2-001 — Holdings content, lag, denominator, and tolerance were caller-asserted

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a caller could choose a convenient candidate subset, lag limit,
  denominator, or completeness tolerance and still obtain a score.
- **HOW and WHERE:** `build_verified_holdings_snapshot` derives immutable content
  identity from authenticated source hash and complete holdings fields;
  `verify_holdings_evidence` fixes `MAXIMUM_HOLDINGS_LAG_SESSIONS` and
  `MINIMUM_MAPPED_CANDIDATE_COVERAGE`, derives lag from effective/decision
  sessions, and materializes all long-equity position IDs. Both
  `PortfolioCandidate` and `weighted_stock_score` require/revalidate the private
  typed evidence.
- **Safety invariant:** topology/eligibility inputs cannot be weakened at the
  final scoring or portfolio call site.
- **Regression evidence:** incomplete candidate enumeration, unmapped
  denominator, source/content mutation, wrong effective-session label,
  not-yet-available evidence, and exchange-session staleness refuse; policy clone
  tests prevent threshold/lag substitution.
- **Residual owner/data decision:** provider completeness and source bytes remain
  an acquisition/structural-audit gate.

### AR-FU-P2-002 — Sequential cap application biased inverse-volatility allocation

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** mutating sector/cluster usage candidate-by-candidate allowed the
  first iteration item to consume a shared cap and made allocation order-dependent.
- **HOW and WHERE:** `_allocate` in `portfolio.py` computes one simultaneous
  inverse-volatility proposal, derives the minimum ETF/sector/cluster scaling
  factor across the whole active set, applies additions together, removes only
  names blocked by now-binding constraints, and repeats. Remaining infeasible
  capital stays cash.
- **Safety invariant:** coupled constraints cannot privilege list order or be
  relaxed to force full investment.
- **Regression evidence:** the final terminal regression proves every nonempty
  portfolio remains zero-access, so the dormant allocator cannot expose its
  ordering behavior in this milestone.
- **Residual owner/data decision:** production caps remain reviewed-policy values
  and were not outcome-tuned. The future rank/topology milestone must restore
  direct reordered-candidate, shared-cap, simultaneous-binding, residual-cash,
  and exact-bound tests before making `_allocate` reachable.

### AR-FU-P2-003 — Portfolio validity and classifications were naked booleans/assertions

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a caller could label an ETF valid or supply convenient sector/
  overlap tuples without authenticated PIT source evidence.
- **HOW and WHERE:** `VerifiedClassificationEvidence`,
  `build_verified_classification_evidence`, and
  `require_verified_classification_evidence` in `portfolio.py` parse strict
  canonical JSON bytes, verify source SHA-256, and bind the exact ETF security,
  holdings content SHA-256, UTC decision instant, sector exposures, overlap
  clusters, and evidence SHA-256. `PortfolioCandidate` cross-checks classification
  evidence against private verified holdings evidence.
- **Safety invariant:** relabeling, source mutation, foreign ETF/snapshot, or a
  different decision time invalidates the candidate before construction.
- **Regression evidence:** the classification dilution test exercises strict
  registered canonical bytes and exact exposure semantics; the nonempty-
  portfolio zero-access test proves classification evidence cannot independently
  unlock selection.
- **Residual owner/data decision:** a real PIT classification source has not been
  accepted or loaded. Before a later cross-section authority makes candidates
  reachable, direct digest/byte mutation, ETF/holdings/decision/epoch mismatch,
  and post-construction nested revalidation tests must be retained on the exact
  candidate API.

### AR-FU-P2-004 — Forced-terminal cost exception was contradictory and forgeable

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a boolean exception could bypass missing ADV while the normal
  contract claimed missing ADV must refuse, without proving a delisting/terminal
  event was knowable at the decision time.
- **HOW and WHERE:** `TerminalEventKind`, `VerifiedTerminalExitEvidence`,
  `verify_terminal_exit_evidence`, and `require_terminal_exit_evidence` in
  `costs.py` bind registered canonical source/event/position-snapshot IDs,
  positive current-long notional, PIT effective/availability/decision times,
  evidence epoch, and source SHA-256 in an init-disabled typed value. Every
  consumer reparses the registered source bytes. Only that evidence activates
  the conservative missing-ADV path, which charges full notional rather than
  zero or a cheap default.
- **Safety invariant:** illiquidity evidence cannot be waived by a caller flag,
  and forced risk removal does not acquire an unrealistically free execution.
- **Regression evidence:** the forced-terminal test rejects a positive trade,
  oversize short-creating liquidation, absent terminal evidence, mixed
  decision/epoch, and unregistered source; exact synthetic liquidation proves
  conservative full-notional pricing for missing ADV.
- **Residual owner/data decision:** terminal data source and conservative cost
  parameter require real PIT evidence before use.

### AR-FU-P2-005 — INVALID observations were silently erased

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** filtering invalid observations before group calculation made a
  contaminated group look like a smaller clean sample.
- **HOW and WHERE:** `robust_group_normalize` explicitly inspects
  `ObservationState`; any INVALID member returns/refuses an invalid group rather
  than dropping the row. Structural zero, no-event, missing, and invalid remain
  distinct states.
- **Safety invariant:** removing evidence cannot convert contamination into
  eligibility.
- **Regression evidence:** mixed valid/invalid group tests prove refusal and
  distinguish structural zeros.
- **Residual owner/data decision:** upstream named refusal counts must remain in
  later evidence reports; no outcome report exists yet.

### AR-FU-P2-006 — Source and PIT provenance were self-attested and rebindable

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** hashing caller-supplied bytes proves only that later bytes match
  earlier bytes. It does not prove who produced them, when the information was
  actually observed/ingested, whether a provider later amended/deleted it, or
  whether the caller invented convenient effective/available timestamps.
- **HOW and WHERE:** `ResearchSourceKind`,
  `_require_zero_access_source_authority`, and
  `require_registered_source_bytes` in `formulas.py` form the common source
  authority seam. The loader re-reads
  `specs/research_source_authority.json` and accepts only its exact canonical
  zero-access schema/ID/mode/empty entries; `require_registered_source_bytes`
  then refuses every kind and every byte string. Strict parsers in `holdings.py`,
  `portfolio.py`, and `costs.py` remain testable without becoming authority, and
  no runtime registration API or positive production registry exists.
- **Safety invariant:** self-hashing or rebinding source IDs/timestamps cannot
  create production authority. Until a separately governed authority admits a
  real artifact, all production source-dependent scoring, ranking, portfolio,
  terminal, and cost paths are intentionally zero-access.
- **Regression evidence:** holdings, stock-score, and cost tests prove every
  production source refuses; stock-score tests cover clone/byte substitution;
  terminal tests prove absent/foreign source refusal; classification tests bind
  exact parsed bytes; and the cross-section test proves strict parsing itself
  cannot lift the independent rank zero-access gate. Synthetic parser-positive
  controls are not provider evidence or production registration.
- **Residual owner/data decision:** a future independently reviewed, committed or
  signed provider/ingestion authority must bind provider contract, immutable
  artifact digest, observed/ingested availability evidence, evidence epoch,
  amendment/deletion handling, and access/transfer rights. Source-authored PIT
  clocks alone are not provenance, and the checked-in zero-access declaration
  must not be replaced merely to make tests or research run.

### AR-FU-P2-007 — Portfolio candidates could mix different-time cross-sections

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** individually plausible candidates can form an impossible
  portfolio if ranks, inverse volatilities, holdings, or classifications come
  from different decision instants, evidence epochs, policies, or candidate
  universes. Per-candidate validation did not establish one simultaneous
  comparison set.
- **HOW and WHERE:** because the reviewed specification does not yet freeze a
  complete simultaneous rank/volatility derivation, `portfolio.py` does not mint
  `VerifiedCrossSectionEvidence` at all. Both its builder and consumer raise the
  named cross-section zero-access refusal, and every nonempty
  `PortfolioCandidate`/`construct_portfolio` path therefore stops before reading
  ranks. The dormant strict parser describes the required single
  `effective_at`, `available_at`, `decision_at`, `evidence_epoch_id`,
  `policy_sha256`, and complete candidate tuple but does not grant authority.
- **Safety invariant:** one portfolio decision is a single PIT cross-section,
  not a collage of the most favorable observations from different clocks,
  vintages, universes, or policies. Until that simultaneity can be positively
  derived and reauthenticated, zero nonempty candidates is safer than a partial
  per-candidate approximation.
- **Regression evidence:** the cross-section/nonempty-portfolio zero-access test
  proves even a synthetically registered, well-formed rank source cannot be
  consumed and that only an empty all-cash portfolio returns.
- **Residual owner/data decision:** after a valid stock-first pass, a new reviewed
  topology milestone must define and test the complete simultaneous context and
  the real price/volatility, holdings, classification, and score availability
  authority described in AR-FU-P2-006. This remediation did not implement it.

### AR-FU-P2-008 — Sector and overlap-cluster fractions could dilute shared caps

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a caller could label a wholly exposed ETF as a small fractional
  cluster member, or provide sector fractions summing below one, reducing the
  usage charged to a binding shared cap while leaving the ETF economically
  exposed.
- **HOW and WHERE:** `_validated_exposures` in `portfolio.py` requires canonical
  typed exposure rows with unique group IDs. Sector fractions must sum exactly
  to one under the fixed Analyst Decimal context. Every asserted overlap-cluster
  membership must equal exactly one, so membership is conservative and cannot
  be fractionalized. `_allocate_in_context` then charges those full look-through
  exposures in its simultaneous ETF/sector/cluster water-filling calculation;
  infeasible residual remains cash.
- **Safety invariant:** exposure classification cannot create cap headroom by
  leaving sector mass unclassified or diluting overlap membership. Coupled caps
  are charged against the complete authenticated classification.
- **Regression evidence:** `test_overlap_cluster_membership_cannot_be_diluted`
  rejects `0.5` cluster membership and a sector total of `0.999999`. The
  cross-section zero-access test proves no nonempty allocation can consume even
  valid-looking classifications before the later reviewed topology milestone.
- **Residual owner/data decision:** exact sector and overlap classification
  contents remain future PIT provider evidence. The conservative membership
  rule is enforced software behavior, not proof that the taxonomy is correct.

### AR-FU-P2-009 — Holdings lag used UTC dates instead of NYSE sessions

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** subtracting UTC calendar dates can make an after-close New York
  snapshot look one day newer or older and counts weekends/holidays incorrectly.
  A caller-supplied effective-session label could also disagree with the actual
  session begun by the timestamp.
- **HOW and WHERE:** `_effective_session_for_instant` in `holdings.py` requires
  the source's `effective_session` to be the latest NYSE session whose open has
  occurred by `effective_at`. `_decision_session` requires `decision_at` to equal
  the canonical NYSE session open. `_derived_lag_sessions` counts the inclusive
  exchange-calendar sequence between those sessions, and
  `mapped_candidate_coverage` compares the derived lag with the authenticated
  policy ceiling rather than a caller value.
- **Safety invariant:** weekends, holidays, UTC midnight, and after-close clock
  boundaries cannot relabel a stale holding as current or create an extra usable
  session.
- **Regression evidence:** `test_holdings_use_nyse_sessions_not_utc_calendar_dates`
  covers a `00:30Z` boundary and rejects the wrong next-day label;
  `test_holdings_availability_and_staleness_are_distinct_refusals` proves
  exchange-session staleness and not-yet-available evidence remain separate.
- **Residual owner/data decision:** source availability and exchange-calendar
  rules still need provider-contract review; no real holdings artifact was
  evaluated.

### AR-FU-P2-010 — Cost evidence was under-bound to decision time and evidence epoch

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** valid-looking ADV/spread/impact rows from different decisions
  or epochs could be combined, while opposing rows for one security could net
  away turnover. A terminal exception could also come from another position
  context.
- **HOW and WHERE:** `VerifiedTradeCostEvidence` in `costs.py` binds canonical
  source bytes to security, policy digest, effective/available/decision times,
  evidence epoch, commission, half-spread, impact, and ADV.
  `portfolio_transaction_cost` now requires explicit `decision_at` and
  `evidence_epoch_id`; every row is reparsed and must match that requested
  context and the common context of every other row. Split rows for one security
  require identical source assumptions, and opposing nonzero directions refuse
  instead of netting. Terminal evidence must match the same security, decision,
  epoch, and exact long-position liquidation.
- **Safety invariant:** a cost decision cannot cherry-pick stale or foreign
  liquidity assumptions, mix evidence epochs, erase turnover through buy/sell
  netting, or attach a terminal waiver from another context.
- **Regression evidence:**
  `test_cost_rows_cannot_erase_turnover_by_opposing_or_mixed_context_rows`
  covers opposing rows and mixed epochs; the split-invariance test proves honest
  same-direction splits match one trade; cost-source and terminal tests mutate
  source content, policy, decision, epoch, and position context.
- **Residual owner/data decision:** the checked-in source authority grants zero
  access to trade-cost/ADV and terminal artifacts. Real model calibration, source quality, and conservative
  parameter review remain blocked by AR-FU-P2-006.

### AR-FU-P2-011 — Input order and ambient Decimal context changed authoritative numerics

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** Python's process-global Decimal precision and insertion-order
  summation can produce different rounded results for the same mathematical
  multiset, especially under cancellation or high dynamic range. Fixed context
  without canonical summation order addressed only half the defect; cost changes
  can alter portfolio-return/participation conclusions, so this is P2 rather
  than a presentation-only P3.
- **HOW and WHERE:** `ANALYST_DECIMAL_PRECISION`, the private fixed context, and
  `analyst_decimal_context` in `formulas.py` isolate authoritative arithmetic
  from ambient settings. `_stable_decimal_sum` sorts values by absolute value
  and value before addition; `effective_contributors` uses it for mass and
  squares, while `independent_evidence_breadth` groups contributions into lists,
  processes stable institution/catalyst keys, and stable-sums each group.
  Holdings source rows and stock-score rows require canonical ordering, and ETF
  aggregation iterates canonical position IDs. In `costs.py`, split deltas are
  retained rather than accumulated in arrival order, stable-summed per security,
  and total costs are accumulated by sorted security ID. Portfolio ranking and
  allocation use exact Decimal values/canonical identity order; the nonempty
  public portfolio boundary remains zero-access independently of these
  primitives.
- **Safety invariant:** changing the caller's Decimal context or permuting an
  economically identical input multiset cannot change evidence breadth, ETF
  score, cost, turnover, or any later threshold/cap decision.
- **Regression evidence:**
  `test_effective_contributors_has_no_epsilon_or_ambient_context_pathology` and
  `test_independent_breadth_does_not_multiply_repeats_or_common_catalyst`
  enumerate high-dynamic-range permutations under a low ambient precision;
  `test_cost_aggregation_is_permutation_invariant_under_high_dynamic_range`
  permutes split and cross-security cost rows. Holdings/score tests also repeat
  calculation under a changed ambient context.
- **Residual owner/data decision:** precision and ordering are deterministic
  software rules, not evidence that any signal/cost model is empirically valid.
  A later reviewed numerical-policy change must roll identity/evidence epoch and
  reproduce the permutation suite.

### AR-FU-P3-001 — Holding identity tolerated whitespace and unmapped category leakage

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** whitespace variants could create distinct apparent IDs, and an
  unmapped row could still carry a peer category that looked authoritative.
- **HOW and WHERE:** `Holding.__post_init__` in `holdings.py` requires canonical
  nonempty position/permanent security/share-class IDs, strict instrument/mapping
  enums, and exact Decimal weights. `MappingState.UNMAPPED` requires no security
  or peer-category assertion; mapped long equity requires both appropriate
  identity and category evidence.
- **Safety invariant:** presentation whitespace and an unmapped label cannot
  split/deduplicate identities or enter peer topology.
- **Regression evidence:** padded IDs, duplicate canonical IDs, and unmapped
  category/security mutations refuse.
- **Residual owner/data decision:** canonical identity contents still depend on
  the future PIT security master.

### AR-FU-P3-002 — Missing legacy reproduction path leaked `FileNotFoundError`

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** operating-system exceptions escaped the quarantine abstraction,
  making callers distinguish/load paths before receiving the intended refusal.
- **HOW and WHERE:** `quarantine_legacy_runner` in `legacy_reproduction.py`
  catches the narrow filesystem `OSError` family and raises
  `LegacyReproductionBlocked` with a named non-authoritative refusal.
- **Safety invariant:** missing/unreadable legacy data remains a deliberate
  quarantine outcome and cannot fall through to network acquisition.
- **Regression evidence:** registered-but-missing artifact tests assert exception
  identity and prove no fetch occurs.
- **Residual owner/data decision:** none beyond the standing rule that legacy
  reproduction cannot update active V2 evidence.

## 6A. Final adversarial research findings

### AR-FINAL-P1-001 — Production research-source authority was runtime-rebindable

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a process-local registration seam could assign authority to
  caller-supplied bytes after startup. Hash equality inside that mutable registry
  therefore proved only self-consistency, not independent, immutable approval of
  a production source.
- **HOW and WHERE:** `research/analyst_revisions_v2/formulas.py` removes the
  positive production registry and makes `require_registered_source_bytes`
  re-read `specs/research_source_authority.json` through
  `_require_zero_access_source_authority`. The checked-in artifact must be the
  exact canonical schema, authority ID, `authority_mode="zero_access"`, and
  empty-entry declaration; every source kind and every supplied byte string is
  refused. Holdings, stock-score, classification, cost, terminal, and
  cross-section consumers in `holdings.py`, `portfolio.py`, and `costs.py`
  retain their strict parsers but cannot turn parsed fixture bytes into
  production authority.
- **Safety invariant:** no supported production interface can create, replace,
  or broaden production source authority. This is a capability boundary, not a
  defense against hostile arbitrary code that can rewrite the module itself.
  Until a separately governed immutable authority is designed, reviewed, and
  owner-approved, the exact production access set is empty.
- **Regression evidence:**
  `test_checked_in_source_authority_is_canonical_zero_access_and_not_rebindable`
  exercises every `ResearchSourceKind`, mutation of the declaration, attempted
  module rebinding, and synthetic bytes; all dangerous directions refuse.
  Parser-positive tests remain private software-contract tests and explicitly do
  not grant source authority.
- **Residual owner/data gate:** the owner must later approve an independently
  administered, append-only production-source authority and the provider
  contracts, licensing, immutable artifacts, access controls, and incident
  process behind it. This correction performs no provider access, registers no
  real hashes, consumes no outcome, and grants no research or trading authority.

### AR-FINAL-P1-002 — Accepted rows bypassed provider-specific raw derivation

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** exactly-once row accounting authenticated that an accepted
  event pointed at a raw row, but it did not prove that every canonical field was
  deterministically derived from that provider's raw schema. A caller could
  author economically meaningful canonical values and bind them to an unrelated
  authenticated locator.
- **HOW and WHERE:** `NormalizationResult.__post_init__` and
  `revalidate_normalization_result` in
  `research/analyst_revisions_v2/normalization.py` now enforce
  `ACCEPTED_EVENT_ZERO_ACCESS_REASON`: `events` must be empty until a reviewed,
  deterministic provider-specific raw-to-canonical normalizer exists. Exhaustive
  refusal-only results remain permitted when every `VerifiedSourceRow` has one
  justified terminal refusal. `result_sha256` reconstructs and revalidates the
  complete object before hashing, so post-construction mutation or an
  `object.__new__` shell cannot obtain authority. Publication and loading in
  `research/analyst_revisions_v2/dataset.py` cross-check the same invariant.
- **Safety invariant:** no accepted canonical event exists unless its complete
  semantic derivation from authenticated raw bytes is encoded and independently
  reviewed; locator/hash binding alone is insufficient. Today the accepted-event
  production set is exactly empty.
- **Regression evidence:**
  `test_arbitrary_canonical_event_fields_are_zero_access_without_raw_derivation`
  and the snapshot/normalization/dataset mutation suite reject arbitrary accepted
  fields, post-construction mutation, forged shells, pre-2013 laundering, and
  digest recomputation, while accepting an exhaustive canonically ordered
  refusal-only dataset as the fail-closed control.
- **Residual owner/data gate:** a later provider adapter must freeze the observed
  provider schema, field-level mappings, correction/withdrawal semantics,
  timestamp derivation, identity mappings, refusal taxonomy, and golden raw-byte
  fixtures before any accepted row is possible. No real row, score, portfolio,
  outcome, or strategy conclusion was authorized by this remediation.

---

# Part II — Remaining Project

## 7. System coverage map

| ID | Priority | Correction boundary | Primary regression evidence |
|---|---:|---|---|
| SYS-P1-001 | P1 | Strict non-boolean finite policy numerics | `tests/test_policy.py` |
| SYS-P1-002 | P1 | One immutable account-scoped broker session and coherent exact snapshot | `tests/test_coherent_broker_snapshot.py`, `tests/test_execution_authorization_binding.py` |
| SYS-P1-003 | P1 | Shared cross-process dispatch/runtime-state fence and drain | Dispatch/cancel-all fence tests |
| SYS-P1-004 | P1 | Central strict broker-order contract used before projection | Broker-order/replacement/execution tests |
| SYS-P1-005 | P1 | Atomic proposal park + halt + critical alert | Broker-event/reconciliation tests |
| SYS-P1-006 | P1 | One malformed active order invalidates normal risk evidence; emergency cancel still works | Broker-order and cancel-all tests |
| SYS-P2-001 | P2 | Exact Decimal snapshot/risk arithmetic | `tests/test_risk_gate_precision_and_authorization.py`, risk-copilot tests |
| SYS-P2-002 | P2 | Provider decimal text retained through event/fill ledger | `tests/test_broker_event_ledger_integrity.py` |
| SYS-P2-003 | P2 | Canonical event-content hash and atomic collision containment | `tests/test_broker_event_ledger_integrity.py` |
| SYS-P2-004 | P2 | Unknown broker status becomes submission-unknown + halt | Broker lifecycle/readiness tests |
| SYS-P2-005 | P2 | Canonical long-only portfolio integrity shared by reports and execution | `tests/test_assistant_risk_copilot.py` |
| SYS-P2-006 | P2 | Earnings blackout is exposure-increasing only | `tests/test_personal_assistant.py` |
| SYS-P2-007 | P2 | Structured strict order-time disposition and recovery | Reconciler timing/replacement tests |
| SYS-P2-008 | P2 | Future/naive/malformed claim time blocks readiness without auto-reclaim | `tests/test_stranded_claim_recovery.py` |
| SYS-P2-009 | P2 | Central semantic bar validation and per-symbol health | Market-data/data-integrity tests |
| SYS-P2-010 | P2 | Shared strict research/backtest input contracts | `tests/test_research_backtest_input_contracts.py` and strategy tests |
| SYS-P2-011 | P2 | One resolved policy path/fingerprint across scheduled surfaces | `tests/test_operational_policy_identity.py`, CLI tests |
| SYS-P2-012 | P2 | Semantic SQLite schema comparison | `tests/test_storage_schema_verification.py` |
| SYS-P2-013 | P2 | Neutral exchange-session target/availability validation | ML contract/shadow tests |
| SYS-P3-001 | P3 | Finite bounded reconciler timing controls | `tests/test_reconciler_timing_integrity.py` |
| SYS-P3-002 | P3 | Malformed fill evidence is reported and blocks readiness | Broker-event/readiness tests |
| SYS-P3-003 | P3 | Strict bounded authorization TTL and atomic in-process consume | Authorization tests |
| SYS-FU-P1-001 | P1 | Runtime-global emergency stop shared across operator databases | Dispatch/cancel-all tests |
| SYS-FU-P1-002 | P1 | Fence failure degrades but cannot abort emergency cancellation | `tests/test_cancel_all_dispatch_fence.py` |
| SYS-FU-P1-003 | P1 | Malformed persistent stop fails closed | Execution/readiness tests |
| SYS-FU-P1-004 | P1 | Broker-session mode is immutable after client capture | `tests/test_coherent_broker_snapshot.py` |
| SYS-FU-P1-005 | P1 | Final recapture binds policy-driving valuations | `tests/test_coherent_broker_snapshot.py` |
| SYS-FU-P2-001 | P2 | Anomaly recurrence preserves/reopens halt and alert | Reconciliation anomaly tests |
| SYS-FU-P2-002 | P2 | Unexpected managed triggers rejected; event insert read back exactly once | Schema/event-ledger tests |
| SYS-FU-P2-003 | P2 | Fallback event identity uses normalized UTC time | Broker-event ledger tests |
| SYS-FU-P2-004 | P2 | Root observations bind to durable broker order ID | Reconciliation/replacement tests |
| SYS-FU-P3-001 | P3 | Readiness includes non-authoritative fill-ledger integrity | Readiness/event-ledger tests |
| SYS-FU-P3-002 | P3 | Strict broker submit boundary requires expected policy fingerprint | Broker-session tests |
| SYS-FINAL-P1-001 | P1 | Final binding covers every policy-driving quote, including pending market buys | Broker snapshot/authorization tests |
| SYS-FINAL-P1-002 | P1 | Sealed session and complete SDK/client identity | Broker session identity tests |
| SYS-FINAL-P1-003 | P1 | Authorization and dispatch permits cannot survive a process fork | Risk authorization/fork tests |
| SYS-FINAL-P1-004 | P1 | Runtime-stop activation/clear is incident-bound and race-safe | Dispatch-fence activation/clear tests |
| SYS-FINAL-P1-005 | P1 | Every broker-adapter submit path requires a one-use dispatch permit | Broker direct-adapter tests |
| SYS-FINAL-P1-006 | P1 | Database integrity anomalies activate runtime-global containment | Storage integrity/containment tests |
| SYS-FINAL-P1-007 | P1 | Runtime stop retains concurrent incident causes | Dispatch-fence incident tests |
| SYS-FINAL-P1-008 | P1 | Malformed emergency siblings cannot hide later raw order IDs | Emergency cancel-all tests |
| SYS-FINAL-P1-009 | P1 | Incomplete open scans do not skip older durable attempts | Reconciler emergency-attempt tests |
| SYS-FINAL-P1-010 | P1 | Persisted broker events are versioned and reauthenticated before reuse | Broker-event ledger tests |
| SYS-FINAL-P1-011 | P1 | Containment survives alert-persistence failure | Storage containment fault tests |
| SYS-FINAL-P1-012 | P1 | Journal fallback preserves the first retained incident | Storage journal-fallback tests |
| SYS-FINAL-P1-013 | P1 | Runtime-global attempt ledger rejects collision, tamper, and replay | Dispatch-attempt ledger tests |
| SYS-FINAL-P1-014 | P1 | One broker order ID cannot bind multiple proposals | Broker-order binding tests |
| SYS-FINAL-P1-015 | P1 | Foreign account/mode attempts make emergency scans incomplete | Reconciler emergency-scope tests |
| SYS-FINAL-P1-016 | P1 | Cancel-all proves its exact runtime/local stop before stability claims | Cancel-all stop-proof tests |
| SYS-FINAL-P1-017 | P1 | Append-only containment conflicts cannot overwrite root cause | Storage append-only fault tests |
| SYS-FINAL-P1-018 | P1 | Integrity scans include foreign-key, page, and order-binding invariants | Storage integrity tests |
| SYS-FINAL-P1-019 | P1 | Transient runtime publication failure latches execution fail-closed | Runtime publication fault tests |
| SYS-FINAL-P2-001 | P2 | Runtime namespace is fixed rather than caller-configurable | Dispatch namespace tests |
| SYS-FINAL-P2-002 | P2 | Readiness reports and blocks on runtime-global stops | Readiness/runtime-stop tests |
| SYS-FINAL-P2-003 | P2 | Reverse architecture guard prevents non-lane code importing Analyst V2 | Architecture boundary tests |
| SYS-FINAL-P2-004 | P2 | Active workflow documents pin review plus Codex counter-review | `tests/test_active_document_consistency.py` |

## 8. Original P1 execution and policy findings

### SYS-P1-001 — Boolean JSON values weakened numeric policy limits

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** Python treats `bool` as an integer, so generic finiteness/range
  comparisons allowed `true`/`false` to become authoritative 1/0 values and
  acquire a valid policy fingerprint.
- **HOW and WHERE:** `_finite_real` and `_reject_non_finite_json_constant` in
  `assistant/policy.py` reject bool before numeric conversion, reject JSON
  NaN/Infinity at parse time, and are used by every percentage/notional/duration/
  spread/slippage/count/reserve field and policy update helper. Validation
  precedes `compute_policy_fingerprint`.
- **Safety invariant:** no syntactically valid JSON boolean or nonfinite token can
  relax an exposure, reserve, order, spread, or timing limit.
- **Regression evidence:** `tests/test_policy.py` parameterizes both booleans
  through direct dataclass validation, JSON load, and update helpers, and covers
  nonstandard JSON constants and count typing.
- **Residual owner/operational decision:** no policy file was changed or deployed;
  the owner must independently review the exact implementation before any
  operational use.

### SYS-P1-002 — Execution lacked one account-bound coherent portfolio

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** execution accepted caller snapshots, combined sequential broker
  reads without coherence proof, ignored broker equity, recreated clients from
  mutable environment settings, and authorized an intent without binding account,
  mode, snapshot, or policy.
- **HOW and WHERE:** `AlpacaBrokerSession` in `execution/alpaca_broker.py` captures
  credentials/paper mode/client/process owner once and reuses them for reads,
  preflight, recapture, lookup, cancellation, stream, and submit.
  `build_portfolio_snapshot_from_alpaca` and its strict helpers in
  `assistant/portfolio_snapshot.py` use bounded account→orders→positions→orders→
  account capture, exact Decimal companions, stable identities/material state,
  authoritative broker equity reconciliation, content SHA-256, and expiry.
  `ExecutionValidationContext`/`ExecutionAuthorization` in
  `risk/execution_gate.py` bind account ID/mode, snapshot ID/time, and policy
  fingerprint. `assistant/execution_service.py` captures execution-owned evidence
  only after claim and submits through the same session.
- **Safety invariant:** a manual/live/foreign/stale/incoherent snapshot or rotated
  credential/account cannot authorize or consume a paper dispatch.
- **Regression evidence:** stable positive capture; fills, balances, positions,
  orders, account identity, credentials/mode, policy, snapshot, and component-
  equity mutations; live/manual/foreign cases; restart/process ownership; and
  authorization binding are covered.
- **Residual owner/operational decision:** broker behavior is fake/fixture-tested;
  no real Alpaca read or paper submission was performed.

### SYS-P1-003 — Kill-switch dispatch race

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** switch activation/cancel-all and submit used independent checks,
  allowing a validated worker to submit after emergency cancellation returned.
- **HOW and WHERE:** `execution_dispatch_fence` and `runtime_state_fence` in
  `assistant/dispatch_fence.py` combine process-local reentrancy with a stable OS
  file lock and fork reset. The execution service acquires the fence around final
  kill/halt reread, account/snapshot/policy revalidation, durable attempt record,
  broker contact, and release. `cancel_all_open_orders` first publishes the
  emergency stop, acquires the same fence where available, reads durable attempts,
  repeatedly discovers/cancels until stable, and only then returns. Reconciliation
  halt activation is coordinated with the same runtime fence.
- **Safety invariant:** cancel-all cannot report a clean drain while a pre-existing
  fenced dispatch remains unseen, and queued dispatches observe the stop and
  refuse.
- **Regression evidence:** deterministic thread/process barriers, cross-database
  dispatch, child-after-fork, owner crash, delayed broker indexing, late attempt,
  rescan stability, cancellation retries, and queued refusal are covered.
- **Residual owner/operational decision:** no real broker fault drill or scheduler
  deployment was performed; independent review must examine Windows locking and
  crash semantics on the exact pushed tree.

### SYS-P1-004 — Broker response was not strictly identity-validated

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** submit, lookup, polling, streaming, and replacement paths each
  accepted different incomplete shapes; missing identity/status/fill evidence
  could receive a positive projection.
- **HOW and WHERE:** `execution/broker_contract.py` now owns canonical strict
  broker account/order/active-book validation and recognized status/fill
  invariants. `assistant/execution_kernel/broker_evidence.py` binds a proposal's
  durable account/mode/snapshot/policy context and calls the central validator.
  Normal submit return, root-key lookup, reconciliation, stream updates,
  replacements, and active-order snapshots validate exact nonempty IDs, root
  client ID or proven chain, account, ticker/side/type/TIF, Decimal quantity/tick
  price, aware time, known status, and fill ranges before projection. Post-contact
  mismatch parks ambiguous state and contains globally.
- **Safety invariant:** malformed/mismatched broker evidence never becomes
  accepted/filled/failed and never releases its reservation as a rejection.
- **Regression evidence:** missing/sentinel IDs, padded identities, wrong account/
  client/ticker/side/type/TIF/quantity/price, unknown status, impossible fills,
  timestamps, malformed active rows, and valid multi-hop replacements are tested.
- **Residual owner/operational decision:** the provider's complete production
  status vocabulary still requires ongoing controlled maintenance; an unknown
  future value intentionally fails closed.

### SYS-P1-005 — Anomaly state and global containment were not atomic

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** proposal parking and kill-switch/alert writes committed in
  separate transactions, leaving a crash window where unrelated submissions
  could continue after a known broker identity anomaly.
- **HOW and WHERE:** `AssistantStore.park_reconciliation_anomaly_and_halt` in
  `assistant/storage.py` uses one `BEGIN IMMEDIATE` transaction to conditionally
  project `submission_unknown`, retain reservation/duplicate slot, persist the
  kill switch, and upsert a critical operational alert. The halt/alert commits
  even if a concurrent terminal transition prevents proposal projection. All
  mismatch paths in execution outcome, manual reconciliation, stream/poll
  reconciliation, and order lifecycle call this boundary.
- **Safety invariant:** no committed broker identity anomaly can exist without a
  committed persistent halt and discoverable critical alert.
- **Regression evidence:** SQL fault injection, transaction rollback, concurrent
  terminal update, repeated/idempotent anomaly, event collision, and reopen/
  restart assertions cover the atomic boundary.
- **Residual owner/operational decision:** no actual alert delivery or operator
  response was exercised; this is durable local containment only.

### SYS-P1-006 — Malformed open orders made an incomplete book look complete

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** normalization converted missing/invalid active-order fields to
  `None`, but callers still marked the endpoint available and skipped those rows
  in duplicate/exposure checks.
- **HOW and WHERE:** the central active-order validator in
  `execution/broker_contract.py` requires usable ID/ticker, known active status,
  side/type/TIF, exact positive quantity or notional, valid fill range, and
  consistent exact/display companions; one bad risk-relevant row invalidates the
  whole normal book. `assistant/portfolio_snapshot.py` and execution validation
  propagate unavailable evidence. Emergency helpers `_emergency_order_mapping`
  and `_emergency_order_id` in `assistant/order_reconciler.py` remain deliberately
  minimal so every syntactically valid order ID can still be canceled even if
  attribution is malformed.
- **Safety invariant:** incomplete open-order evidence blocks new/increasing
  exposure but never blocks risk-reducing emergency cancellation.
- **Regression evidence:** every missing/unknown/nonfinite/invalid active field
  blocks normal submission; malformed-but-identifiable rows are still canceled.
- **Residual owner/operational decision:** no real account-wide cancel was issued.

## 9. Original P2 system findings

### SYS-P2-001 — Rounded float risk math at exact cap boundaries

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** authoritative checks consumed rounded display floats even when
  exact Decimal evidence existed, allowing sub-cent and aggregate boundary drift.
- **HOW and WHERE:** strict exact fields are required/validated in
  `assistant/portfolio_snapshot.py`; `risk/execution_gate.py` parses Decimal
  intent, quotes, positions, cash/equity/buying power, pending orders, basket and
  total exposure without binary floating-point decision arithmetic. Display/
  exact companions must agree. Risk-copilot reporting uses the same exact
  snapshot integrity.
- **Safety invariant:** presentation rounding can neither create cap headroom nor
  conceal an over-cap portfolio.
- **Regression evidence:** sub-cent position, accumulated rounding, mismatched
  companions, exact boundary, fractional pending order, quote, basket, and total
  exposure tests exist.
- **Residual owner/operational decision:** no owner limit was changed; this only
  makes enforcement reproduce the configured limits exactly.

### SYS-P2-002 — Exact fills were irreversibly rounded

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** broker decimal digits became SQLite REAL/float at stream and
  journal boundaries, preventing exact later reconstruction.
- **HOW and WHERE:** additive schema columns in `assistant/storage.py` retain
  cumulative and incremental quantity/price as canonical decimal text plus
  `numeric_evidence_status`; event/fill consumers prefer text. Alpaca order/trade
  update normalization preserves provider decimal companions. Legacy REAL-only
  rows are explicitly `legacy_rounded_unrecoverable`; they are not falsely
  backfilled as exact.
- **Safety invariant:** new provider digits survive restart byte-for-byte, while
  legacy uncertainty remains visible and cannot silently gain precision.
- **Regression evidence:** adversarial decimals, restart round-trip, partial
  stream plus cumulative poll, exact reconstruction, recoverable text, and legacy
  disclosure are covered.
- **Residual owner/operational decision:** old rounded digits cannot be recovered
  without original source evidence; that limitation is permanent.

### SYS-P2-003 — Duplicate event ID could split journal and projection

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** `INSERT OR IGNORE` compared only binding, then projected the new
  caller payload even when the stored event ID referred to different content.
- **HOW and WHERE:** `AssistantStore.project_broker_order_event` canonicalizes all
  projection-driving event fields and stores `event_content_json`, SHA-256,
  version, account/order scope, and exact numeric evidence in one transaction.
  Exact replay is idempotent and reprojects only stored bytes. A changed payload
  under the same ID rolls back projection and atomically halts/alerts.
- **Safety invariant:** one event identity has exactly one immutable meaning;
  journal and proposal/order/fill projection cannot diverge.
- **Regression evidence:** exact replay; each changed field; account-scope
  collision; concurrent collision; faulted alert write rollback; unchanged
  projection; and legacy self-heal are covered.
- **Residual owner/operational decision:** provider event-ID global scope remains
  conservatively supplemented with broker/account/order binding.

### SYS-P2-004 — Unknown status was treated as positive acceptance

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** lifecycle mapping used a positive default for any unrecognized
  zero-fill status.
- **HOW and WHERE:** `proposal_status_for_order` in
  `assistant/order_lifecycle.py` returns `submission_unknown` for every unknown/
  blank value. `journal_broker_order_update` detects status outside the central
  vocabulary and calls atomic anomaly parking/halt/alert before projection.
  Readiness treats the unresolved state as critical and reservations remain held.
- **Safety invariant:** novel/corrupt provider state cannot mean accepted,
  terminal, absent, or budget-releasable without reviewed semantics.
- **Regression evidence:** new enum, blank, malformed type, case/whitespace, and
  readiness/halt paths are tested.
- **Residual owner/operational decision:** adding a provider status requires an
  explicit contract/test change; runtime learning is prohibited.

### SYS-P2-005 — Negative portfolio could appear compliant

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** report builders checked finiteness but not the no-short/no-margin
  economics that the execution gate enforced.
- **HOW and WHERE:** `validate_long_only_portfolio_snapshot` in
  `assistant/portfolio_snapshot.py` rejects negative shares/market values/cash/
  buying power, nonpositive price for nonzero holdings, inconsistent exact/display
  values, duplicates, and position-equity mismatch. Builder, direct dataclass,
  context, risk-copilot, and execution paths all use it; reports degrade rather
  than returning compliant.
- **Safety invariant:** a state refused by execution integrity cannot receive a
  clean advisory risk report.
- **Regression evidence:** negative/inconsistent fields through builder and
  directly constructed snapshots plus report/gate parity are tested.
- **Residual owner/operational decision:** canonical model remains long-only; any
  future short/margin support requires a separate contract.

### SYS-P2-006 — Earnings safeguard obstructed legitimate risk reduction

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the earnings blackout applied symmetrically to buys and sells,
  even though a proved held-quantity sell reduces risk.
- **HOW and WHERE:** `_check_earnings_blackout` and phase/side applicability in
  `risk/execution_gate.py` make the blackout exposure-increasing only. Sell
  allowance still requires a valid current long and quantity no greater than
  exact holdings; oversell/short-opening and unrelated hard violations remain
  blocked.
- **Safety invariant:** conservative information safeguards cannot trap existing
  exposure, but the exception cannot open a short or bypass another control.
- **Regression evidence:** generated reduction, owner trim, buy blackout,
  unavailable earnings, oversell, and mixed hard-violation tests exist.
- **Residual owner/operational decision:** this is a rule-correctness change, not
  permission to submit any sell.

### SYS-P2-007 — Bad order timestamps silently preserved stale orders

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** missing/malformed values implied no cancellation, naive time was
  assumed UTC, and future time looked young while reconciliation still succeeded.
- **HOW and WHERE:** `timestamp_disposition` in
  `assistant/temporal_integrity.py` and `_order_timestamp_disposition` in
  `assistant/order_reconciler.py` classify healthy/stale/missing/malformed/naive/
  small-skew/material-future evidence with signed age and frozen tolerance.
  `_cancel_if_stale` records a structured disposition; once a valid authoritative
  order ID exists, malformed timing enters explicit operator recovery/alert
  rather than a false healthy reconciliation.
- **Safety invariant:** ambiguous clock evidence never certifies a stale order as
  healthy, and risk-reducing cancellation remains attempted/visible where safe.
- **Regression evidence:** recent/stale/boundary, missing, malformed, naive,
  offset, small/future skew, replacement authority, implicit-now ordering, and
  recovery counts are tested.
- **Residual owner/operational decision:** operator recovery remains necessary
  when broker time evidence is irreparably ambiguous.

### SYS-P2-008 — Future pre-broker claim appeared healthy

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** negative age passed both stale and unreadable checks and could
  leave a uniqueness slot wedged while readiness stayed true.
- **HOW and WHERE:** `_claim_timestamp_disposition` and
  `transaction_readiness` in `assistant/readiness.py` use strict aware time,
  signed age, and the shared future-skew bound. Malformed/naive/material-future
  claims block readiness with proposal/status/time/reason. Manual recovery in
  `assistant/execution_service.py` validates the timestamp and conditional
  unchanged-state boundary; ambiguous time is never auto-reclaimed.
- **Safety invariant:** unknown clock direction blocks readiness but cannot be
  used as proof that no broker contact occurred.
- **Regression evidence:** future/naive/malformed/exact-now/recent/stale/tolerance,
  timestamp-change race, offset normalization, and manual recovery tests exist.
- **Residual owner/operational decision:** clock repair/operator inspection is
  required for ambiguous durable rows.

### SYS-P2-009 — Market-data success did not imply usable data

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** any nonempty provider frame was recorded as success, and maximum
  freshness hid stale/missing siblings.
- **HOW and WHERE:** `data/market_data.py` and `data/price_source.py` centrally
  validate canonical ticker, required schema, unique ascending exchange-session
  index, finite positive OHLC, high/low consistency, nonnegative valid volume,
  and at least one usable row before success. `assistant/data_integrity.py`
  separates transport success, per-ticker usability, requested-universe
  completeness, and per-ticker/worst-required freshness; partial valid siblings
  remain available but the batch is degraded and alertable.
- **Safety invariant:** transport availability cannot certify malformed bars or
  hide a stale/missing required symbol.
- **Regression evidence:** missing columns, NaN/Infinity/nonpositive/impossible
  OHLC, bad volume/index/order/duplicates, partial universe, mixed freshness, and
  valid-sibling preservation are tested.
- **Residual owner/operational decision:** no external provider call or production
  health record was made; provider-specific structural audits remain separate.

### SYS-P2-010 — Backtest APIs permitted impossible economics

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** public backtest/strategy entry points accepted negative/bool/
  nonfinite horizons/costs, invalid cadence/weights/prices, and misaligned sessions.
- **HOW and WHERE:** `data/research_input_contracts.py` owns positive/nonnegative
  integer checks excluding bool, explicit horizon/same-day rules, bounded finite
  rates and combined costs, positive capital/prices, long-only weight sums, and
  unique monotonic aligned session indexes/windows. `backtest/engine.py`,
  `backtest/portfolio_simulator.py`, and decline/Kelly/leverage/trend-vol/
  vol-target strategies call these at public boundaries.
- **Safety invariant:** a simulation cannot manufacture return through negative
  cost, exit before entry, implicit short/leverage, invalid price, or zero cadence.
- **Regression evidence:** negative/zero/bool/float horizons and cadence,
  NaN/Infinity/negative rates, overcombined costs, invalid weights, misalignment,
  nonpositive prices, and exit ordering are covered.
- **Residual owner/operational decision:** valid inputs do not make a backtest
  evidence of edge; outcome/selection controls remain separate.

### SYS-P2-011 — Watchdog policy differed from execution policy

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** watchdog supplied its own explicit default instead of using the
  canonical explicit→environment→personal→default resolution, so scheduled
  surfaces could certify different limits.
- **HOW and WHERE:** `scripts/run_operations_watchdog.py` defaults policy input to
  none and calls `assistant.policy.resolve_policy_path`.
  `scripts/install_windows_operational_tasks.ps1` resolves/accepts one policy and
  passes it to every task; `scripts/run_personal_assistant.py` records resolved
  path/fingerprint; `scripts/verify_windows_evidence_tasks.ps1` compares the
  installed triggers and fingerprints across cycle, monitor, observation, and
  watchdog.
- **Safety invariant:** operational health cannot be green for a different policy
  than the execution process would enforce.
- **Regression evidence:** precedence, missing/broken path, CLI resolution,
  installer `WhatIf`, trigger verification, and cross-surface fingerprint parity
  are covered.
- **Residual owner/operational decision:** no Windows task was installed, changed,
  or executed during remediation.

### SYS-P2-012 — Schema verification ignored integrity constraints

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the verifier compared table column-name sets and named objects,
  allowing loss of PK/unique/not-null/default/type/FK/check/generated semantics.
- **HOW and WHERE:** structured schema types and `_table_schema`,
  `_schema_objects`, `_table_sql_constraints`, `_all_indexes`, and
  `_compare_schema_objects` in `assistant/storage.py` compare `table_xinfo`, PK
  order, affinity/declared type, null/default/generated state, foreign keys,
  implicit/named index uniqueness/origin/columns, trigger/index SQL, and canonical
  table SQL constraints including CHECK/STRICT/WITHOUT ROWID semantics. Read-only
  verification does not create or migrate the target.
- **Safety invariant:** a same-named but semantically weakened database cannot be
  reported compatible.
- **Regression evidence:** mutation tests remove every constraint family,
  idempotency-key uniqueness, implicit unique identity, FK, generated column,
  CHECK, index, and trigger while preserving operator-local unrelated tables.
- **Residual owner/operational decision:** current code cannot non-destructively
  restore every legacy semantic weakening; such databases remain failed for
  operator repair.

### SYS-P2-013 — Session horizon could mature on a weekend

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** generic/storage validation used calendar-day offsets and trusted
  caller-supplied availability even though normal shadow code used sessions.
- **HOW and WHERE:** neutral `data/exchange_calendar.py` derives target sessions,
  exchange opens/closes, and canonical availability. `PredictionRecord` in
  `ml/contracts.py` validates target session and no-earlier-than-close
  availability. Shadow storage in `assistant/storage.py` independently derives
  and persists target session, requires matured time no earlier than canonical/
  delayed availability, and refuses outcome attachment to migrated legacy rows
  lacking session proof. `ml/shadow.py`/`shadow_runtime.py` use the same contract.
- **Safety invariant:** direct storage callers cannot mature a Friday horizon-one
  prediction on Saturday or before Monday's close.
- **Regression evidence:** weekend, holiday/session derivation, early/wrong target,
  delayed availability, malicious direct storage call, and legacy-row refusal are
  covered.
- **Residual owner/operational decision:** this preserves observational ML only;
  it grants no model or execution authority.

## 10. Original P3 system findings

### SYS-P3-001 — Reconciler timing controls were weakly typed/ranged

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** NaN/Infinity/negative values could disable waits, cancel every
  order, or enter broker/thread work before failure.
- **HOW and WHERE:** `bounded_timing_number` and `bounded_positive_int` in
  `assistant/temporal_integrity.py`, plus the reconciler's narrow wrapper,
  validate exact allowed types, finiteness, positive/nonnegative bounds, and aware
  `now` before broker contact, thread creation, or durable mutation.
- **Safety invariant:** invalid timing configuration has zero operational side
  effects and cannot invert cancellation semantics.
- **Regression evidence:** every public reconciler timing argument is
  parameterized with bool, negative, zero where prohibited, NaN, and infinities.
- **Residual owner/operational decision:** frozen maximums remain policy constants;
  changing them requires reviewed configuration work.

### SYS-P3-002 — Budget reporting silently dropped malformed fill rows

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** parse failures were skipped, understating filled notional
  without exposing evidence degradation.
- **HOW and WHERE:** exact fill ingestion rejects malformed pairs; legacy/corrupt
  rows read by `AssistantStore.get_execution_budget_usage` produce sorted
  `integrity_errors`, `legacy_unrecoverable_event_ids`, and an evidence status
  while reservations remain conservative. `transaction_readiness` consumes the
  integrity result rather than treating a numeric subtotal as complete.
- **Safety invariant:** malformed fill evidence can reduce readiness but can never
  reduce authoritative reservation enforcement or look like zero spend.
- **Regression evidence:** malformed/naive/future time, NaN/Infinity/nonpositive/
  incomplete quantity-price pairs, corrupt exact text, and legacy REAL-only rows
  are covered.
- **Residual owner/operational decision:** corrupt/legacy rows require operator
  investigation and cannot be promoted to exact evidence.

### SYS-P3-003 — Authorization TTL/replay defense was weak

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** TTL accepted bool/float/negative/unbounded values, and
  in-process check-then-set replay consumption lacked one synchronization boundary.
- **HOW and WHERE:** `_validated_authorization_ttl` in
  `risk/execution_gate.py` requires a bounded exact integer excluding bool;
  authorization proofs bind expiry/context. A single lock guards prune/check/
  consume of token proofs, while the durable proposal claim remains the primary
  cross-process exactly-one dispatch control.
- **Safety invariant:** one authorization cannot be replayed by concurrent
  threads, extended through type coercion, or detached from signed execution
  context.
- **Regression evidence:** invalid TTL types/ranges, object/proof mutation,
  expiry, independent tokens, and a two-thread barrier proving exactly one verify
  succeeds are covered.
- **Residual owner/operational decision:** this in-memory token registry is not a
  substitute for the durable claim/fence and is documented accordingly.

## 11. Adversarial follow-up system findings

### SYS-FU-P1-001 — Emergency stop was split across independent operator databases

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a persistent kill switch stored inside database A was invisible
  to a dispatch using database B, even though both processes targeted the same
  broker runtime/account.
- **HOW and WHERE:** `runtime_emergency_stop_path`,
  `activate_runtime_emergency_stop`, `get_runtime_emergency_stop`, and
  `clear_runtime_emergency_stop` in `assistant/dispatch_fence.py` store one
  canonical runtime-global, generation-bound, atomically written stop record next
  to the shared fence rather than inside an arbitrary operator database. Execution
  final pre-contact checks read both local persistent state and the shared runtime
  stop. Cancel-all publishes the shared stop before draining. State writes are
  serialized by `runtime_state_fence` and reject symlink/path/schema/generation
  ambiguity.
- **Safety invariant:** two processes using different database files cannot
  disagree that an account-wide emergency stop is active; local corruption or
  absence cannot downgrade a valid shared stop.
- **Regression evidence:** cross-database process barriers prove an in-flight
  dispatch is drained/canceled and a queued dispatch refuses; generation binding,
  clear semantics, malformed/corrupt runtime JSON, and shared attempt visibility
  are covered.
- **Residual owner/operational decision:** the canonical runtime directory is
  machine-local; its permissions, backup/transfer exclusion, and multi-host
  topology require an operations review before any deployment.

### SYS-FU-P1-002 — Dispatch-fence acquisition failure aborted emergency cancellation

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the same fence that coordinates normal safety could fail to
  open/acquire, and the exception stopped cancel-all before it contacted the
  broker, converting a containment degradation into no risk reduction.
- **HOW and WHERE:** `_enter_best_effort_emergency_fence` in
  `assistant/order_reconciler.py` attempts runtime-state and execution fences but
  returns a structured degradation instead of raising. `cancel_all_open_orders`
  still publishes every stop it can, freezes one account-scoped broker session,
  enumerates/cancels valid IDs, invokes account-wide cancellation coverage, and
  rescans. `_record_cancel_all_incomplete` atomically activates reconciliation
  halt where possible and upserts a critical `emergency_cancel_all:incomplete`
  alert with the fence/local-stop failure.
- **Safety invariant:** coordination failure can prevent a clean success claim but
  cannot prevent best-effort risk-reducing cancellation.
- **Regression evidence:** injected fence failure and local kill-switch write
  failure prove broker cancellation still occurs, the result is explicitly
  incomplete, and a critical durable alert is recorded; persistent cancel
  failure also never reports stable.
- **Residual owner/operational decision:** operators must treat `incomplete` as an
  incident requiring manual broker verification; no real cancellation was run.

### SYS-FU-P1-003 — Malformed persistent stop was interpreted as off

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** dictionary `.get("active")`/truthiness semantics let malformed
  type/shape/timestamp state bypass a safety switch or produce inconsistent
  readiness/dispatch behavior.
- **HOW and WHERE:** `AssistantStore.set_kill_switch` requires an exact bool and
  string reason. Persistent and runtime readers validate exact mapping shape,
  boolean identity, nonempty/aware change time, generation, and canonical fields.
  `_runtime_emergency_stop_active` in `assistant/execution_service.py` catches no
  malformed state as false: validation failure forces the final pre-contact path
  to `kill_switch_active=True`. `transaction_readiness` reports malformed state
  as blocked with its integrity reason.
- **Safety invariant:** unknown/corrupt stop state is equivalent to an active stop
  for new exposure, never an inactive default.
- **Regression evidence:** malformed local values/types and corrupt/truncated/
  wrong-schema runtime state block before broker contact; strict writer tests
  reject bool-like values.
- **Residual owner/operational decision:** corrupt state requires operator repair;
  automatic clearing is prohibited.

### SYS-FU-P1-004 — `AlpacaBrokerSession` mode could be mutated after client capture

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the session exposed a writable public mode attribute even
  though the underlying client/credentials had already been captured for paper
  or live, so a live client could be relabeled as paper before validation.
- **HOW and WHERE:** `AlpacaBrokerSession` in `execution/alpaca_broker.py` stores
  mode privately as `_paper`, exposes read-only `paper`/`account_mode` properties,
  includes mode in immutable session/account/snapshot evidence, and reuses it for
  URLs, stream, preflight, final authorization verification, and submit. No setter
  or caller-supplied post-construction relabel path exists.
- **Safety invariant:** the mode authorized is the mode used to construct the
  client and contact the broker; assignment cannot turn a live client into
  paper-labelled evidence.
- **Regression evidence:** mutation/assignment against a live-captured fake
  refuses and no order is submitted; frozen credential/mode reuse is asserted
  across lookup and submit.
- **Residual owner/operational decision:** live mode remains independently gated
  by explicit confirmation/account ID and was not exercised.

### SYS-FU-P1-005 — Final broker recapture omitted policy-driving valuations

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the pre-submit fingerprint covered identity/order quantities but
  omitted broker equity and position current-price/market-value fields used by
  exposure and reserve policy. The market could move after authorization without
  invalidating the snapshot.
- **HOW and WHERE:** `AlpacaBrokerSession._execution_snapshot_state_fingerprint`
  includes exact account cash/buying power/equity and each position's exact
  quantity, current price, and market value plus the active-order material
  fingerprint. `_assert_execution_snapshot_unchanged` performs a fresh coherent
  capture immediately before token verification/contact and compares that full
  state; mismatch requires fresh validation.
- **Safety invariant:** every broker field that drove the authorization remains
  identical at final dispatch, not merely account/order identity.
- **Regression evidence:** current-price, market-value, equity, cash/buying-power,
  position, and open-order mutations all produce zero submit; stable recapture is
  the positive control.
- **Residual owner/operational decision:** this intentionally favors refusal under
  ordinary market movement; any future tolerance policy would be a separately
  reviewed authorization design.

### SYS-FU-P2-001 — Repeated anomaly handling could leave a proposal reconciling without an open alert

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** idempotent/conditional anomaly code treated an already-seen
  anomaly or changed proposal status as a no-op and could rely on an alert that
  had been closed or a local proposal projection that no longer applied.
- **HOW and WHERE:** `AssistantStore.park_reconciliation_anomaly_and_halt` and
  `activate_reconciliation_halt` in `assistant/storage.py` treat the persistent
  halt and critical alert as unconditional containment facts inside the same
  transaction, while proposal projection remains conditional/monotonic. The
  stable anomaly fingerprint upsert reopens/refreshes the alert on every recurrence
  and retains diagnostic details; outcome, manual, stream, poll, status, and event
  collision paths call this single boundary. Recovery/error handlers route a
  failed reconciliation back to `submission_unknown` or the anomaly boundary
  instead of stranding `reconciling` silently.
- **Safety invariant:** every currently observed unresolved broker anomaly has an
  active durable halt and open critical alert even if the proposal raced,
  recurred, or a prior alert was acknowledged/closed.
- **Regression evidence:** repeat-after-alert-close, already-terminal/racing
  proposal, exception during reconciliation, idempotent replay, and reopen/restart
  cases assert proposal monotonicity plus halt/alert presence.
- **Residual owner/operational decision:** only an explicit operator resolution
  procedure may clear the halt/alert; remediation does not perform that action.

### SYS-FU-P2-002 — Schema verification allowed extra managed triggers and event insertion was not proven

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** checking only required trigger/index names allowed an additional
  trigger on an execution-managed table to suppress or mutate a write, and a
  successful SQL call was treated as proof that exactly one immutable event row
  existed.
- **HOW and WHERE:** `_schema_objects`/`_compare_schema_objects` in
  `assistant/storage.py` distinguish operator-local unrelated objects from the
  closed set of triggers/indexes attached to managed execution tables and reject
  extras there. `project_broker_order_event` uses a non-ignoring insert for a new
  identity, checks affected-row count, reads back the single row within the same
  transaction, and compares its complete binding/content hash/canonical bytes
  before projection; trigger/schema drift rolls back.
- **Safety invariant:** unreviewed database behavior cannot silently suppress,
  rewrite, duplicate, or reinterpret an execution journal event.
- **Regression evidence:** extra BEFORE/AFTER/INSTEAD-style managed trigger,
  suppress/replace trigger, wrong rowcount/readback, duplicate identity, and
  unrelated operator table/object cases are mutation-tested.
- **Residual owner/operational decision:** a database with managed-object drift
  remains failed for deliberate operator repair; automatic destructive rebuild is
  not attempted.

### SYS-FU-P2-003 — Fallback broker event ID hashed an unnormalized timestamp

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** equivalent ISO instants (`Z`, `+00:00`, or another offset) could
  hash to different fallback event IDs even though projection normalized the
  stored `event_at`, defeating deterministic deduplication.
- **HOW and WHERE:** `normalized_event_at` in
  `assistant/order_lifecycle.py` parses an aware instant, converts it to canonical
  UTC ISO text, and rejects malformed/naive/future values before identity
  construction. `broker_event_id` receives/hashes that normalized text along with
  normalized status and canonical exact numeric material. Provider-supplied event
  IDs remain bound by the immutable content hash/scope checks.
- **Safety invariant:** one physical broker event has one fallback identity
  regardless of equivalent timezone spelling, while genuinely different instants
  remain distinct.
- **Regression evidence:** `Z`, UTC offset, and equivalent non-UTC offset forms
  deduplicate; different instants, naive/malformed/future values, and exact replay
  cases are covered.
- **Residual owner/operational decision:** fallback IDs remain a deterministic
  substitute only where the provider gives no stable event ID.

### SYS-FU-P2-004 — Later root observations were not bound to the durable broker order ID

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** reconciliation under the correct root client-order key could
  later accept a different broker order ID without proving an explicit replacement
  chain, allowing identity to drift across polls/streams.
- **HOW and WHERE:** the first strictly validated root observation is persisted as
  durable root broker-order identity in the proposal/order journal. Subsequent
  root-key lookup, submit recovery, manual reconciliation, poll, and stream paths
  in `assistant/execution_kernel/broker_evidence.py`,
  `assistant/execution_kernel/outcomes.py`, `assistant/order_reconciler.py`, and
  `assistant/order_lifecycle.py` require that ID exactly. A different ID is valid
  only through the central replacement resolver's explicit `replaces`/
  `replaced_by` lineage back to the durable root; otherwise the proposal is parked
  and globally contained.
- **Safety invariant:** a client-order key does not authorize arbitrary later
  broker identity, and replacement adoption is explicit, bounded, and auditable.
- **Regression evidence:** same-key/different-root ID, later matching order after
  earlier mismatch, wrong predecessor, cycle/depth/missing link, valid one/multi-
  hop replacement, and restart lookup cases are covered.
- **Residual owner/operational decision:** an anomalous broker identity requires
  operator/broker investigation; automatic identity reassignment is forbidden.

### SYS-FU-P3-001 — Readiness ignored non-authoritative fill-ledger integrity

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** reservations remained conservative, so malformed historical
  fill rows did not weaken the enforcement subtotal, but readiness could still
  report healthy while reporting/reconciliation evidence was corrupt.
- **HOW and WHERE:** `AssistantStore.get_execution_budget_usage` returns explicit
  `evidence_status`, `integrity_errors`, and legacy-unrecoverable IDs from exact
  ledger verification. `transaction_readiness` in `assistant/readiness.py`
  includes a dedicated fill-ledger-integrity check; any corruption makes overall
  readiness false while preserving reservations and distinguishing disclosed
  legacy rounding from new corruption.
- **Safety invariant:** non-authoritative accounting corruption cannot be hidden
  behind conservative enforcement or a green readiness report.
- **Regression evidence:** corrupted exact text/time/pair, legacy-only evidence,
  clean provider-exact ledger, and reservation-conservatism cases assert both
  readiness and budget behavior.
- **Residual owner/operational decision:** legacy rounded rows remain a disclosed
  limitation; the owner must decide whether they require an operational block or
  bounded historical exception after review.

### SYS-FU-P3-002 — Strict broker submit API made policy fingerprint optional

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** `submit_market_order`/`submit_limit_order` defaulted
  `expected_policy_fingerprint` to `None`; a direct caller could provide an
  otherwise bound authorization without explicitly carrying the expected active
  policy identity into the last broker boundary.
- **HOW and WHERE:** both strict session submit methods in
  `execution/alpaca_broker.py` require a canonical 64-hex expected policy
  fingerprint before broker reads/contact and pass it to
  `verify_execution_authorization`. The execution service always supplies the
  fingerprint derived from the exact active policy and captured context. Legacy
  module-level broker facades still cannot submit without a valid bound
  authorization/session snapshot.
- **Safety invariant:** the final broker boundary independently proves the same
  policy identity used to validate/authorize the intent; omission cannot become a
  wildcard match.
- **Regression evidence:** missing/`None`/malformed/wrong fingerprint refuses with
  zero broker contact, while the exact bound fingerprint is the positive control
  for both market and limit paths.
- **Residual owner/operational decision:** no real submit occurred; API signature
  compatibility must be assessed during independent review, with safety taking
  precedence over permissive legacy calling.

## 11A. Final adversarial system findings

### SYS-FINAL-P1-001 — Final authorization did not bind every policy-driving quote

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** snapshot recapture bound account, positions, and open orders,
  but pending market-buy notional could still depend on a quote whose value or
  timestamp was not re-established at the final broker boundary.
- **HOW and WHERE:** `_ExecutionSnapshotRegistration`,
  `get_execution_validation_quote`, `_assert_all_execution_quotes_unchanged`,
  and the market/limit submit methods in `execution/alpaca_broker.py` maintain an
  immutable per-snapshot quote registry. `assistant/execution_kernel/validate.py`
  obtains policy-driving quotes through that snapshot-bound broker. Final submit
  re-fetches every registered quote, requires identical bid/ask material, and
  reapplies the same freshness and future-skew limits before contact.
- **Safety invariant:** every quote used to authorize current or pending exposure
  is tied to the exact snapshot and remains identical and temporally admissible
  at dispatch; an unbound, stale, future, missing, or changed quote yields zero
  submit.
- **Regression evidence:** broker snapshot/authorization tests mutate pending-
  market-buy prices and timestamps, inject stale/future quotes, omit registrations,
  and alter bid/ask after validation; all dangerous cases refuse before submit,
  with an unchanged fresh quote as the positive control.
- **Residual owner/operational gate:** real quote-provider latency and failure
  drills remain required. No tolerance, live contact, account access, or trading
  authority is introduced.

### SYS-FINAL-P1-002 — Broker session and SDK identity remained mutable or incomplete

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** protecting only paper/live mode and account ID left other
  connection identity mutable, and an SDK client check that omitted credential,
  sandbox, authentication, or endpoint material could validate one context while
  a different context performed the request.
- **HOW and WHERE:** `AlpacaBrokerSession` in `execution/alpaca_broker.py` is a
  sealed, non-subclassable, non-copyable, process-owned object with guarded
  `__setattr__`. Its private slots freeze key, secret, mode, account ID, client
  objects, canonical trading/data endpoints, OAuth/basic-auth flags, and process
  owner. `_assert_sdk_client_identity` checks the complete SDK/client identity,
  and every read/contact path reasserts session ownership and immutable endpoint
  slots rather than mutable module constants.
- **Safety invariant:** the account, mode, credentials, authentication mode,
  endpoint, clients, and process that generated evidence are the same immutable
  context that performs final dispatch.
- **Regression evidence:** session tests attempt attribute mutation, subclassing,
  copy/pickle, fork reuse, endpoint-constant mutation, client base-URL mutation,
  key/secret mismatch, sandbox mismatch, and authentication-mode mismatch; all
  refuse, while one unchanged session completes only the synthetic positive path.
- **Residual owner/operational gate:** credential rotation, endpoint failover,
  paper/live fault drills, and live confirmation remain separate reviewed
  operations. No credential was used or stored by this remediation.

### SYS-FINAL-P1-003 — Execution authority could replay after process fork

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** inherited process memory could carry an authorization secret,
  token registry, lock, or dispatch permit into a child; a token consumed in one
  process was not necessarily consumed in the other.
- **HOW and WHERE:** the after-fork reset in `risk/execution_gate.py` rotates the
  process-local authorization secret and replaces the consumed-token registry
  and lock. `_reset_after_fork` in `assistant/dispatch_fence.py` replaces fence
  and one-use permit state. Authorizations, broker sessions, and
  `ExecutionDispatchPermit` records all bind their creating process and are
  rechecked immediately before contact.
- **Safety invariant:** neither a validated execution authorization nor a
  dispatch permit is transferable across a fork, and parent/child consumption
  state cannot diverge into two valid submits.
- **Regression evidence:** fork-specific risk/dispatch tests mint before fork and
  attempt use in both processes, including inherited-lock/registry mutation;
  child reuse refuses and the parent remains one-use. Platforms without fork are
  explicitly skipped rather than reported as proof.
- **Residual owner/operational gate:** spawn/service-manager crash-restart drills
  remain required on the deployment platform. This is containment code, not
  permission to start an execution service.

### SYS-FINAL-P1-004 — Runtime-stop activation and clear had a stale-read race

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** activation, observation, and clearing could occur across
  separate lock windows; a clearer could act on stale state or remove a newer
  concurrent cause that happened to share an earlier global stop generation.
- **HOW and WHERE:** `activate_runtime_emergency_stop`,
  `get_runtime_emergency_stop`, `clear_runtime_emergency_stop`, and
  `runtime_state_fence` in `assistant/dispatch_fence.py` use a canonical incident
  set under the runtime-state fence. Clear requires the exact open `incident_id`,
  reason, origin database, and observed activation identity and removes only that
  incident. Storage recovery helpers re-read and re-prove the exact incident
  under the global dispatch fence; if it disappeared, they republish it before
  any local clear.
- **Safety invariant:** a stale observer cannot clear a concurrent or changed
  containment cause, and execution cannot resume between local and runtime stop
  transitions without proving the named incident remains contained.
- **Regression evidence:** dispatch-fence tests interleave activation, stale
  clear, same-ID/different-content reuse, concurrent causes, and removal between
  read and fence acquisition; stale/different clears refuse or republish the
  exact incident.
- **Residual owner/operational gate:** operators still need a reviewed incident-
  resolution and multi-process drill. The remediation clears no actual stop.

### SYS-FINAL-P1-005 — Direct broker-adapter paths bypassed the service dispatch fence

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** validating an authorization inside the normal execution service
  did not prevent another in-process caller from invoking a broker adapter submit
  directly after bypassing the service's final fence checks.
- **HOW and WHERE:** `_mint_execution_service_dispatch_permit`,
  `execution_dispatch_permit_fence`, and
  `consume_execution_dispatch_permit` in `assistant/dispatch_fence.py` create a
  private, opaque, process-bound, one-use permit tied to database, proposal,
  idempotency key, broker-session identity, account/mode, policy, snapshot,
  runtime-stop generation, and fence ownership. The broker adapter separately
  revalidates and consumes the bound execution authorization immediately before
  permit consumption. `assistant/execution_service.py` is the sole production minter.
  Both strict submit methods and module facades in `execution/alpaca_broker.py`
  require and consume that permit while the dispatch fence remains held; obsolete
  private POST helpers were removed/inlined inside those fenced methods.
- **Safety invariant:** no route to `/v2/orders` or an SDK order submit can make
  broker contact without the exact one-use permit and the still-held global
  dispatch fence.
- **Regression evidence:** direct-adapter tests call session and module submit
  methods with missing, forged, reconstructed, mismatched, reused, post-fork,
  and out-of-fence permits and monkeypatch every broker-contact seam; contact
  remains zero. Exact service-issued permit is the bounded positive control.
- **Residual owner/operational gate:** independent review must repeat lexical and
  dynamic submit-path enumeration when the adapter changes. No real order or
  endpoint contact occurred.

### SYS-FINAL-P1-006 — Database anomalies were contained only inside one database

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a corrupt operator database could set its own kill state while
  another database in the same runtime continued dispatching, even though broker
  account exposure is shared outside those database boundaries.
- **HOW and WHERE:** `_activate_detected_broker_integrity_incident`,
  `park_reconciliation_anomaly_and_halt`, and the integrity paths in
  `assistant/storage.py` derive a stable incident ID, publish it through
  `activate_runtime_emergency_stop`, persist the database-local halt and critical
  alert, and use `_drain_and_retry_runtime_incident` to prove or republish the
  exact runtime incident under the dispatch fence. Dispatch checks the canonical
  runtime state in addition to local state.
- **Safety invariant:** any database capable of detecting execution-evidence
  corruption stops new/increasing exposure across every operator database in the
  runtime; containment is not scoped to the damaged file.
- **Regression evidence:** storage/dispatch integration tests corrupt event,
  schema, page, foreign-key, and binding evidence in one database and attempt a
  dispatch from another; the global stop blocks it, including restart and
  repeated-detection cases.
- **Residual owner/operational gate:** repair and incident-clear procedures remain
  manual and independently reviewed. The code does not infer that a stopped or
  repaired database is operationally trustworthy.

### SYS-FINAL-P1-007 — A single runtime-stop record lost concurrent causes

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** representing the runtime stop as one mutable reason meant a
  later incident could overwrite an earlier one, or resolving one cause could
  incorrectly release the runtime while another remained unresolved.
- **HOW and WHERE:** runtime-state schema and validators in
  `assistant/dispatch_fence.py` store canonical `open_incidents`, each with
  immutable incident ID, reason, origin database, and activation time.
  `activate_runtime_emergency_stop` adds idempotently but rejects content reuse;
  `clear_runtime_emergency_stop` removes only the named, exactly matched cause and
  derives the aggregate reason/generation from the remaining set.
- **Safety invariant:** runtime dispatch stays stopped until every independently
  identified incident is explicitly and correctly cleared; one cause cannot
  overwrite or clear another.
- **Regression evidence:** concurrent-incident tests activate causes from
  multiple databases, repeat exact activation, attempt same-ID content mutation,
  clear in both orders, and restart between operations; the stop remains active
  while any cause survives.
- **Residual owner/operational gate:** the owner must define who may resolve each
  incident class and how that approval is audited. No incident is auto-resolved.

### SYS-FINAL-P1-008 — One malformed emergency sibling hid later raw order IDs

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** normalizing an emergency open-order sequence as one batch meant
  a malformed or repeated sibling could abort enumeration before later usable raw
  broker order IDs were discovered and cancelled.
- **HOW and WHERE:** `_emergency_order_mapping`, `_emergency_order_id`, and
  `cancel_all_open_orders` in `assistant/order_reconciler.py` process emergency
  siblings independently. Strict normalized IDs are preferred; when normalization
  fails, bounded raw-object/mapping extraction attempts a canonical string/UUID
  ID, records the malformed sibling and incomplete scan, continues through the
  sequence, and merges every unique usable raw ID into the cancellation set.
  `AlpacaBrokerSession.get_open_order_ids_for_emergency` supplies the parallel
  fail-degraded adapter view.
- **Safety invariant:** malformed evidence can prevent a claim that the book is
  complete, but it cannot conceal a later usable order ID or prevent best-effort
  risk-reducing cancellation.
- **Regression evidence:** emergency tests place malformed, exception-raising,
  duplicated, padded, and valid raw-ID siblings in different orders and prove all
  canonical usable IDs are attempted exactly once while completeness remains
  false.
- **Residual owner/operational gate:** unresolved malformed broker objects require
  operator/provider investigation; a cancellation attempt is not proof of broker
  cancellation or book stability.

### SYS-FINAL-P1-009 — An incomplete open scan skipped older durable attempts

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** emergency logic could treat current open-order enumeration as
  the candidate universe even after admitting it was incomplete, omitting older
  durable dispatch attempts whose broker state was still unresolved.
- **HOW and WHERE:** `cancel_all_open_orders` in
  `assistant/order_reconciler.py` always merges
  `list_runtime_dispatch_attempts` with normalized/raw open-order IDs. It scans
  durable attempts independent of open-book completeness, validates account and
  mode scope, resolves proposal/order bindings where possible, and keeps unknown
  or unconfirmable attempts in the unresolved set across rounds and restarts.
- **Safety invariant:** an incomplete live scan broadens emergency uncertainty;
  it never narrows the durable set of potentially live orders that must be
  cancelled or explicitly left unresolved.
- **Regression evidence:** reconciler tests combine malformed/throwing open scans
  with older durable attempts absent from the live response, restart the store,
  and prove each usable durable order ID is attempted while `book_stable` remains
  false for unresolved evidence.
- **Residual owner/operational gate:** broker/provider confirmation and an
  operator-reviewed drain remain necessary before stability or restart is
  asserted. No simulated cancel result grants that confirmation.

### SYS-FINAL-P1-010 — Persisted broker events could be reblessed after downgrade

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a migration or read path could recompute missing integrity
  metadata from current row contents, allowing previously persisted broker-event
  bytes to be modified or downgraded and then treated as newly authenticated.
- **HOW and WHERE:** `_migrate_broker_event_integrity`,
  `_broker_event_integrity_error`, `_assert_broker_event_integrity`, and
  `list_broker_order_events` in `assistant/storage.py` use a versioned canonical
  event schema/content hash. The one-time legacy backfill is allowed only when
  the complete metadata column family was absent; once any integrity metadata
  exists, reads and migrations verify it and never rewrite/rebless mismatches.
  Projection reauthenticates canonical bytes, scope, binding, and version before
  use.
- **Safety invariant:** after the integrity boundary exists, no modified,
  downgraded, partly migrated, or version-confused event can acquire fresh
  authority by recomputing metadata from itself.
- **Regression evidence:** event-ledger migration tests mutate content/version/
  hash/scope before and after legacy migration, create partially present metadata,
  and reopen the database; every dangerous direction is contained rather than
  backfilled, while a pristine all-columns-absent legacy fixture migrates once.
- **Residual owner/operational gate:** real legacy databases require backup,
  offline rehearsal, and independent migration review. The remediation neither
  repairs corrupted history nor declares it trustworthy.

### SYS-FINAL-P1-011 — Alert persistence failure could defeat containment

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** if local halt, proposal park, alert, and runtime publication
  were treated as one all-or-nothing success, failure to write the diagnostic
  alert could roll back or bypass the safety-critical stop.
- **HOW and WHERE:** containment paths in `assistant/storage.py`, including
  `_activate_detected_broker_integrity_incident` and
  `park_reconciliation_anomaly_and_halt`, publish the runtime incident and retain
  a process fail-closed latch independently of diagnostic success. The durable
  local transaction still attempts monotonic proposal state, local halt, and
  critical alert atomically; on alert/storage failure,
  `_drain_and_retry_runtime_incident` re-proves or republishes the exact runtime
  cause and surfaces the persistence error without releasing dispatch.
- **Safety invariant:** observability failure may reduce diagnostics but cannot
  authorize new/increasing exposure or erase the original containment cause.
- **Regression evidence:** storage fault-injection tests fail alert insert/upsert,
  transaction commit, runtime publication, and retry in combinations; another
  database still observes the runtime stop or process latch, and the original
  error remains reported.
- **Residual owner/operational gate:** alert-delivery channels and degraded-
  containment runbooks require operational drills. A process latch is deliberately
  non-clearable in-process and requires controlled restart after durable repair.

### SYS-FINAL-P1-012 — Journal fallback could overwrite the retained root incident

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** fallback error handling could catch a secondary journal or
  containment exception and write a new generic failure over the first broker
  anomaly, destroying the evidence needed to understand and resolve the stop.
- **HOW and WHERE:** broker-event projection and fallback paths in
  `assistant/storage.py` preserve the first canonical incident ID/reason and use
  append-only, stable-fingerprint updates. Expected journal/containment conflicts
  are normalized to `JournalTransactionConflictError` and routed through the
  same retained-root containment seam; fallback diagnostics are appended or
  associated without replacing the root incident.
- **Safety invariant:** secondary failure handling cannot change the identity,
  reason, or origin of the first safety-critical incident and cannot weaken its
  runtime/local stop.
- **Regression evidence:** broker-event/storage tests inject a root collision and
  then fail alert, journal, append-only trigger, and retry paths; the original
  incident remains open and byte-identical while secondary errors are reported.
- **Residual owner/operational gate:** retained incident evidence still requires
  human diagnosis and protected backup/export. The code does not adjudicate the
  broker truth or clear the stop.

### SYS-FINAL-P1-013 — Dispatch-attempt identity allowed collision, tamper, or replay

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** database-local or permissively parsed attempt records could let
  two databases reuse an attempt identity, mutate its binding, replay a terminal
  attempt, or smuggle padded identifiers that compared differently at later
  boundaries.
- **HOW and WHERE:** `_validated_runtime_dispatch_attempt`,
  `_runtime_dispatch_attempt_identity`, `record_runtime_dispatch_attempt`, and
  `list_runtime_dispatch_attempts` in `assistant/dispatch_fence.py` maintain a
  canonical runtime-global append/state-transition ledger. Exact schema,
  canonical IDs (including untrimmed-equality rejection), digests, account/mode,
  proposal/order bindings, timestamps, state transitions, and content identity
  are revalidated under `runtime_state_fence`; collision/tamper/replay invokes
  `_contain_runtime_dispatch_attempt_integrity`.
- **Safety invariant:** one attempt identity has one immutable cross-database
  meaning and one monotonic lifecycle; malformed, colliding, changed, or replayed
  attempts stop runtime dispatch.
- **Regression evidence:** attempt-ledger tests exercise padded IDs, unknown keys,
  same-ID/different-content records, cross-database collision, terminal replay,
  backward transition, file tamper, crash/restart, and concurrent writers; each
  dangerous case activates/retains containment.
- **Residual owner/operational gate:** attempt-ledger backup, permissions, disk-
  failure, and multi-host coordination remain deployment gates. No durable record
  proves a broker outcome by itself.

### SYS-FINAL-P1-014 — One broker order ID could bind multiple proposals

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** event identity checks protected one event/proposal scope but did
  not globally prevent the same broker order ID from appearing under two
  proposals, allowing fills/status to project onto inconsistent local intents.
- **HOW and WHERE:** the primary-key-backed broker-order lookup and
  `BrokerOrderBindingConflictError` in `assistant/storage.py` enforce one durable
  proposal per canonical broker order ID. `project_broker_order_event` validates
  the binding before projection; a cross-proposal conflict rolls back projection,
  parks the affected proposal where possible, preserves the root diagnostic,
  activates local and runtime-global containment, and opens/refreshes a critical
  alert.
- **Safety invariant:** a broker order identity cannot authorize or update more
  than one proposal; ambiguity stops all new/increasing exposure rather than
  choosing a winner.
- **Regression evidence:** broker-order/event-ledger tests bind the same ID to two
  proposals through insert, replay, replacement, migration, and concurrent paths;
  no second projection commits and global/local halt plus retained alert are
  asserted.
- **Residual owner/operational gate:** the broker and operator must determine the
  true intent/order relationship. Automatic reassignment or merge remains
  forbidden.

### SYS-FINAL-P1-015 — Foreign account or mode attempts disappeared from emergency completeness

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** filtering runtime attempts to the active account/mode could make
  an unexpected foreign-scope attempt vanish from the emergency report and allow
  a false claim that all relevant orders were resolved.
- **HOW and WHERE:** `cancel_all_open_orders` in
  `assistant/order_reconciler.py` validates every durable attempt's account and
  mode against the active account-scoped broker. A mismatch is retained as an
  explicit foreign-scope unresolved record, marks the scan incomplete, activates
  containment, and prevents `book_stable`; it is not silently cancelled through
  the wrong session or filtered away.
- **Safety invariant:** foreign-scope execution evidence always widens uncertainty
  and blocks stability. The system neither ignores it nor uses current credentials
  to act on an unproven account/mode.
- **Regression evidence:** emergency-scope tests mix local, foreign-account,
  foreign-mode, malformed-scope, and otherwise usable attempts; local IDs remain
  cancellable, every foreign item is reported unresolved, and stability/readiness
  remain false across restart.
- **Residual owner/operational gate:** an operator with correctly authorized
  credentials must investigate the foreign scope separately. The remediation
  performs no cross-account access or cancellation.

### SYS-FINAL-P1-016 — Cancel-all claimed an active stop without proving publication

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** reporting a requested stop or relying on an earlier activation
  call was not proof that the exact runtime and local incident remained active
  after races, write failures, or a concurrent clear.
- **HOW and WHERE:** `cancel_all_open_orders` in
  `assistant/order_reconciler.py` reports requested, observed-active, and
  confirmed stop state separately. Under the global dispatch fence it re-reads
  the exact runtime incident ID/reason/origin and local stop, republishes a missing
  runtime incident when possible, and treats read/proof exceptions as
  `active=None`. `book_stable` requires confirmed runtime stop, confirmed local
  stop, a complete drain, and no unresolved orders; a request or best-effort
  activation alone never satisfies it.
- **Safety invariant:** emergency output cannot claim stable containment unless
  the exact stop is durably observed at the protected boundary; unknown proof is
  fail-closed, not truthy.
- **Regression evidence:** cancel-all tests remove/change the incident between
  activation and verification, fail runtime/local reads and writes, race a clear,
  and return empty broker books; requested remains distinguishable from active,
  `active=None` is preserved, and stability remains false without full proof.
- **Residual owner/operational gate:** broker-side cancellation confirmation and
  operator review remain required; even a confirmed local/runtime stop does not
  prove the external order book is empty.

### SYS-FINAL-P1-017 — Append-only containment exceptions fell into root-overwrite fallback

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** SQLite append-only triggers correctly rejected a forbidden
  journal mutation, but their driver-specific exception escaped the recognized
  conflict family and entered generic fallback logic that could replace the root
  anomaly or lose containment context.
- **HOW and WHERE:** append-only writes and broker-event transaction handling in
  `assistant/storage.py` catch the narrow SQLite trigger/integrity exception at
  the transaction boundary, normalize it to `JournalTransactionConflictError`,
  roll back the forbidden mutation, and route it through the stable incident,
  alert, local-halt, and runtime-containment path. The original incident remains
  the root; the append-only conflict is retained as secondary evidence.
- **Safety invariant:** enforcing immutability cannot itself weaken containment or
  authorize an overwrite; a rejected journal mutation leaves both history and
  the first incident intact.
- **Regression evidence:** storage fault tests fire append-only triggers during
  normal projection, anomaly parking, alert fallback, and nested failure paths;
  they assert the forbidden update never commits, the canonical exception is
  surfaced, and the original runtime incident remains open.
- **Residual owner/operational gate:** trigger activation indicates database or
  code drift requiring deliberate repair and backup. Automatic trigger removal
  or journal rewriting is not authorized.

### SYS-FINAL-P1-018 — Integrity scans missed foreign-key, page, and order-binding corruption

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** a nominal SQLite integrity result and schema comparison did not
  cover foreign-key violations, all page-level results, or semantic one-order/
  one-proposal bindings; some non-`ok` results were reported without invoking the
  common containment boundary.
- **HOW and WHERE:** `_integrity_results` and `database_integrity_check` in
  `assistant/storage.py` consume all rows from `PRAGMA integrity_check` and
  `PRAGMA foreign_key_check`, verify managed schema objects/event content, and
  scan broker-order bindings for duplicates or inconsistent roots. Every non-
  `ok` result—not only a selected message—flows through
  `_activate_detected_broker_integrity_incident`, which establishes the stable
  local/runtime incident and alert.
- **Safety invariant:** any detected physical, relational, schema, journal, or
  order-binding corruption makes readiness false and stops new/increasing
  exposure across the runtime.
- **Regression evidence:** storage integrity tests inject multiple page messages,
  FK violations, extra/missing managed objects, event corruption, and duplicate/
  conflicting order bindings, including combinations where the first result is
  benign; every non-`ok` item is returned and containment is asserted.
- **Residual owner/operational gate:** offline SQLite diagnostics, backup restore,
  and independent evidence reconciliation are required before repair/clear. Code
  detection is not proof that the database can be safely salvaged.

### SYS-FINAL-P1-019 — Transient runtime-stop publication failure allowed another database to resume

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** if runtime publication failed transiently after a local anomaly,
  the detecting process could raise while another database observed no global
  stop and continued dispatching.
- **HOW and WHERE:** `_latch_runtime_emergency_stop_failure` in
  `assistant/dispatch_fence.py` installs a process fail-closed latch on runtime-
  state fence, read, validation, or publication failure. Runtime stop readers and
  permit/dispatch-fence acquisition honor the latch. `_contain_runtime_dispatch_attempt_integrity`
  and `_drain_and_retry_runtime_incident` in `assistant/storage.py` re-read the
  exact incident under the global fence, republish if absent, and latch on every
  inability to prove it before propagating the original error.
- **Safety invariant:** inability to durably publish or verify global containment
  is itself a global stop for that process; no database serviced by it can resume
  on an unknown runtime state.
- **Regression evidence:** fault-injection tests fail initial publication, fence
  acquisition, atomic replace, subsequent read, and republish; dispatch from a
  second database remains blocked by the latch, which cannot be cleared inside
  the compromised process.
- **Residual owner/operational gate:** multi-host containment still needs an
  independently designed shared authority; this runtime mechanism is host-local.
  Recovery requires controlled process restart after durable-state diagnosis.

### SYS-FINAL-P2-001 — Runtime namespace was configurable or split by caller context

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** deriving runtime fence/stop/attempt files from database paths or
  mutable environment configuration let two processes choose different
  namespaces and each believe it held the global execution boundary.
- **HOW and WHERE:** `_canonical_runtime_root`, `dispatch_fence_path`,
  `runtime_emergency_stop_path`, `runtime_state_fence_path`, and
  `runtime_dispatch_attempts_path` in `assistant/dispatch_fence.py` use a fixed
  per-user application-data root: the Windows known-folder API or a literal,
  ownership-checked POSIX location. Database input is retained only for API
  compatibility/origin metadata and cannot select the synchronization namespace;
  environment overrides and caller-relative roots cannot select it; on POSIX,
  symlink or ownership ambiguity at the fixed literal fallback refuses.
- **Safety invariant:** all local operator databases and processes for the same
  user converge on one runtime fence, stop state, and attempt ledger; callers
  cannot opt out through configuration.
- **Regression evidence:** namespace tests vary database locations, current
  directory, environment variables, separators, and process boundaries and
  assert identical canonical paths; unavailable/unsafe known folders fail closed.
- **Residual owner/operational gate:** multi-user, container, roaming-profile,
  network-filesystem, and multi-host deployment topologies require a new reviewed
  coordination design before use.

### SYS-FINAL-P2-002 — Readiness ignored the runtime-global emergency stop

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** readiness checked local database kill state and integrity but
  could report healthy while another database had activated the runtime-global
  stop or runtime state was unreadable.
- **HOW and WHERE:** `transaction_readiness` in `assistant/readiness.py` calls
  `get_runtime_emergency_stop`, emits a dedicated runtime-stop check with open
  incident identities, and makes overall readiness false for active, malformed,
  unreadable, or latched state. This check is independent of the local kill-
  switch and database-integrity checks so their differing scope stays visible.
- **Safety invariant:** readiness cannot be green while runtime dispatch is
  stopped or its state is unknown, regardless of the selected database's local
  health.
- **Regression evidence:** readiness tests activate incidents from another
  database, retain multiple causes, corrupt/remove runtime state, inject read
  failures/latches, and clear only one cause; every non-proven-clear state is red.
- **Residual owner/operational gate:** readiness remains a diagnostic, not restart
  authority. Operators must resolve and explicitly clear every incident through
  the reviewed workflow.

### SYS-FINAL-P2-003 — Architecture checks guarded Analyst V2 only in one direction

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** the Analyst package import firewall prevented V2 from importing
  outcome/execution/legacy authority, but no reverse guard stopped production,
  other strategy lanes, or shared modules from importing Analyst V2 internals and
  turning incomplete research objects into de facto shared authority.
- **HOW and WHERE:** the architecture/project-separation tests enumerate the
  repository's transitive local import graph in both directions. They permit only
  the declared Analyst V2 research/test/document surfaces and reject imports of
  `research.analyst_revisions_v2` from execution, risk, assistant, data, ML,
  shared strategy code, Insider Buying, Short Interest, and production entrypoint
  manifests. Dynamic imports and parent-package aliases are included.
- **Safety invariant:** incomplete Analyst V2 research remains lane-owned and
  non-production; no other layer can silently consume it as a signal, policy,
  portfolio, outcome, or execution authority.
- **Regression evidence:** architecture mutation tests insert direct, transitive,
  dynamic, and parent-package imports on both sides and require the guard to turn
  red; the existing explicit research-only surface is the positive control.
- **Residual owner/operational gate:** any future shared contract must be proposed
  as a narrow reviewed interface with a versioned migration, not by weakening the
  guard. No strategy result or cross-lane authority is created.

### SYS-FINAL-P2-004 — Active documents encoded a superseded review workflow

**Implementation status:** Implemented — pending required independent review/counter-review.

- **Root cause:** active direction, workflow, handoff, agent, and action-plan text
  disagreed on separate review branches versus the later owner-directed serialized
  same-lane workflow and omitted the required Codex counter-review, making a
  code-correct snapshot operationally ambiguous.
- **HOW and WHERE:** `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`,
  `docs/Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md`,
  `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`, `AGENTS.md`,
  `docs/ACTION_PLAN_2026-08-20.md`, and `docs/SESSION_HANDOFF.md` are reconciled to
  the later owner decision: for these three strategy lanes work is serialized on
  the long-lived lane branch, Claude independently reviews the exact pushed Codex
  snapshot, and Codex counter-reviews the exact reviewed snapshot before final
  acceptance. `tests/test_active_document_consistency.py` pins the exception and
  its precedence.
- **Safety invariant:** no lane milestone can be represented as accepted without
  exact-snapshot independent review, correction disposition, Codex counter-review,
  final validation, and updated lane/root records, while shared remediation does
  not import Analyst-only authority into the other lanes.
- **Regression evidence:** active-document consistency tests fail when review is
  moved to a separate lane branch, counter-review is omitted, obsolete sequencing
  returns, or required stock-first/no-outcome/no-authority language drifts.
- **Residual owner/operational gate:** documentation alignment does not itself
  complete review, counter-review, branch synchronization, provider work, outcome
  access, or deployment. Exact remote heads and final validation evidence remain
  pending until recorded in the handoff.

## 12. Implementation dependency and review order

The corrections should be reviewed in this order because later guarantees rely
on earlier boundaries. A green later-layer test is not a substitute for reviewing
its prerequisites.

1. **Strict primitives and fixed runtime namespace:** policy numerics, canonical
   JSON/Decimal/time/session parsing, typed evidence, the non-configurable
   per-user Windows known-folder root or ownership-checked POSIX runtime root,
   and fork-reset process state.
2. **Sealed execution identity and complete valuation context:** immutable
   account/mode/credential/authentication/endpoint SDK identity, coherent exact
   snapshot, every policy-driving quote (including pending market buys), and
   final freshness/future-skew recapture.
3. **Unbypassable dispatch authorization:** policy/account/mode/snapshot token
   binding, fork invalidation, one-use service-minted dispatch permits held
   through every SDK/HTTP submit, and the canonical runtime-global attempt
   ledger's collision/tamper/replay rules.
4. **Multi-incident containment:** incident-bound activation/clear, runtime-global
   propagation from every database anomaly, concurrent-cause retention, alert-
   failure independence, republish-under-fence behavior, and the process
   fail-closed latch when runtime publication or proof fails.
5. **Emergency cancellation and drain:** independent raw sibling enumeration,
   durable attempts even after incomplete open scans, explicit foreign-scope
   unresolved evidence, canonical order IDs, and separate requested/active/
   confirmed stop claims before `book_stable`.
6. **Durable journal and database integrity:** exact Decimal/event bytes,
   versioned read reauthentication without downgrade/reblessing, immutable first
   incident across fallback, normalized append-only conflicts, one order ID per
   proposal, and full page/foreign-key/schema/binding containment.
7. **Recovery, readiness, and supporting correctness:** unknown-state behavior,
   temporal recovery, local and runtime-stop readiness, portfolio/risk parity,
   earnings risk reduction, market-data usability, backtest contracts,
   operational policy parity, and ML exchange-session maturity.
8. **Research evidence identity:** strict snapshot, exactly-once refusal coverage,
   loader-only/out-of-band snapshot and dataset authority, V2 event/revision
   contract, immutable dataset, import/legacy quarantine, and the final accepted-
   event zero-access barrier until provider-specific raw derivation exists.
9. **Analyst source authority and formulas/topology:** first prove the canonical
   checked-in source authority is exact zero-access and has no positive runtime
   registration seam; then review policy identity, validity states, breadth,
   nested revalidation, and deterministic arithmetic as non-authoritative
   primitives. Review cross-section/nonempty-portfolio refusal separately:
   rank/universe/volatility derivation is not frozen, and no source can be
   registered by the current production boundary.
10. **Preregistration and acceptance workflow last:** external review anchor,
    semantic frozen cells, full-request outcome boundary, and externally pinned
    append-only permanent-look spending, followed by exact-pushed-snapshot Claude
    review, correction disposition, Codex counter-review, final validation, and
    lane/root records. Checked-in source/look authorities and the reviewed-spec
    registry authorize nothing throughout this review.

For each group, the independent reviewer should inspect the uncorrected finding,
the correction diff, and the dangerous-direction test; temporarily break the
key guard where practical and confirm the test turns red; restore it; then run
focused and full validation on the exact committed/pushed tree. Codex then
counter-reviews the reviewer corrections and final tree. No group should be
marked accepted solely because another group's integration test passes.

## 13. Required final validation evidence

The implementation work has produced green development runs, including a final
Analyst contract-module run of **24 passed in 6.57s** after the last score-state
guard, an adjacent Analyst V2 contracts/statistics/preregistration/quarantine/
firewall run of **138 passed in 136.83s** after the substantive authority,
rank-containment, and deterministic-aggregation changes, and an earlier broad
remediation baseline of **541 passed, 1 skipped, 2 warnings**. The one source
change after the 138-test run was covered by the later 24-test rerun. All are
still intermediate development evidence, not independent acceptance or an
exact-final-tree full run; they must not be copied into the final handoff as if
they covered later documentation/integration edits. Targeted syntax compilation
of `formulas.py`, `holdings.py`, `portfolio.py`, `costs.py`, and the contract
test file was also green, but it does not replace the required repository-wide
compile command below.

Before the implementation snapshot is handed to the independent reviewer, the
implementer must record results from the exact final committed tree for:

| Validation | Required evidence |
|---|---|
| Research/Analyst focused | All ACER and `analyst_revisions_v2` snapshot, normalization, dataset, preregistration, formulas, holdings, portfolio, costs, statistics, legacy quarantine, documentation, and import-firewall tests; exact pass/skip/warning count and duration |
| P1 execution focused | Policy, coherent broker snapshot, authorization binding, broker order contract, dispatch/cancel-all fence, atomic anomaly, replacement chain, execution characterization, and broker-event ledger tests |
| P2/P3 system focused | Temporal/recovery/readiness, schema, exact fill, portfolio/risk, earnings, market data, backtest input, operations policy, and ML session-maturity tests |
| Architecture boundaries | Direct and transitive ML/LLM/authority/outcome/import boundaries plus project-separation entrypoint/manifest tests |
| Full suite | `python -m pytest -q` with exact pass/skip/failure/warning count and duration |
| Compilation | `python -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py` |
| Repository checks | `git diff --check`, narrow secret-shape scan, exact branch/HEAD, and a clean `git status --short --branch` |
| Independent review | Exact pushed implementation head, ordered commit dispositions, P0–P3 ledger, reviewer correction commits, mutation evidence, and reviewer reruns |
| Counter-review | Exact reviewed head, disposition of every reviewer correction, final reruns, and handoff/associated-record commits |

The final validation record must replace intermediate counts with the exact final
tree results. Any edit after a run invalidates the affected result and requires a
rerun.

## 14. Remaining owner/data/operations gates that code did not close

The following are deliberately still blocked even if every test passes:

- external independent review and Codex counter-review of the exact pushed
  remediation snapshot;
- an owner-approved, externally reviewed Analyst V2 specification and committed
  registry anchor; the checked-in registry currently authorizes nothing;
- accepted provider contracts, processing/transfer rights, Snapshot B amendment/
  deletion semantics, and immutable real artifacts;
- PIT security master, prices/corporate actions/delistings, ETF holdings/NAV,
  classifications, stock-score, terminal-event, ADV/spread, controls, and
  outcome evidence, plus an independently governed positive source authority;
- an externally pinned append-only permanent-look authority with atomic
  exactly-once spend, full-request receipts, independent administration,
  backup/transfer/access-control/incident procedures, and cross-machine
  reauthentication before any authorized outcome access; the checked-in
  `zero_access` registry is not that authority;
- the actual normalized-dataset-to-stock-score computation/derivation artifact,
  the stock-first one-shot study, a valid pass/null disposition, and the hard
  rule that a valid null closes the canonical family;
- after a valid stock pass only, an owner-frozen and independently reviewed
  complete ETF universe, score-to-rank/tie and inverse-volatility derivation,
  cross-section authority, ETF topology, portfolio outcome evaluation,
  untouched cross-lane final holdout, three-lane selection correction, and later
  QuantConnect parity;
- broker/provider/QC fault drills, paper deployment, scheduler installation,
  evidence-epoch roll, alert-delivery verification, or operational policy change;
- any live-integration design, funded-account access, capital allocation, or
  autonomous execution authority.

The safe present interpretation is therefore narrow: the remediation branch is
a candidate software correction set awaiting the repository's full review chain.
It is not a completed Analyst strategy, a validated trading backbone, or an
authorization to observe outcomes or operate an account.

## 15. Reviewer closeout checklist

An independent reviewer must not close this ledger until all of the following are
true on one exact pushed snapshot:

1. all 109 IDs above receive an explicit independent disposition;
2. every original finding is cross-checked against the source audit and retained;
3. every follow-up finding is reproduced or otherwise concretely verified;
4. all P1 fixes receive concurrency/crash/fault/restart evidence where applicable;
5. research identity, preregistration, and no-outcome boundaries are mutation-
   tested, including empty reviewed registry behavior;
6. failure directions block new/increasing exposure without blocking legitimate
   risk-reducing cancellation or a proved long-position reduction;
7. database migrations are tested fresh and pre-migration, and verification is
   read-only when requested;
8. exact final focused/full/compile/diff/status results are recorded;
9. no synthetic fixture is described as market evidence and no intermediate test
   count is described as final acceptance;
10. the associated Analyst/operations/review records and root session handoff name
    the exact implementation/review/counter-review commits and remote state;
11. shared changes are synchronized to the three owner-named strategy branches
    without copying Analyst-lane code into the Insider Buying or Short Interest
    lane namespaces; and
12. no provider, outcome, QC, broker, deployment, scheduler, paper, or live action
    is inferred from software completion.
