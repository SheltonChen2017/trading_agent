# Analyst Revisions ETF Strategy V2 — implementation and session record

Status: **ARV2 CONTRACT/SAFETY REMEDIATION IMPLEMENTED; PENDING REQUIRED
CLAUDE REVIEW AND CODEX COUNTER-REVIEW. NO V2 SIGNAL OR OUTCOME TEST, ETF
RESEARCH PORTFOLIO, QC ALGORITHM, OR DEPLOYMENT HAS BEEN RUN.**

Branch: `codex/strategy-analyst-revisions-v2`

Governing owner source:
`ANALYST_REVISIONS_ETF_STRATEGY_BLUEPRINT_V2_EN.pdf`, 64 pages, 271,570
bytes, SHA-256
`eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193`.
The PDF identifies itself as v2.0 dated 2026-08-22 and replaces the former
analyst-consensus plan.

Codex is the primary implementer. Claude is the independent reviewer, and
Codex counter-reviews Claude's exact reviewed push before combining that
disposition with the next authorized bounded milestone. Both agents work
serially on the same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

## 1. Canonical strategy contract

The first executable family is the PDF's rating-only V2, not a free-form
blend:

- identify genuine upgrades and downgrades using each firm's own ordered
  rating vocabulary normalized to `[-1, +1]`;
- deduplicate to institution-stock-day, use a 20-trading-day half-life, sum
  decayed events, robustly z-score within sector, and shrink by
  `N_eff / (N_eff + 3)` times measured data quality;
- discover candidate ETFs from signaled stocks, then aggregate stock scores
  using point-in-time holdings and coverage normalization;
- apply ETF reliability
  `sqrt(coverage) * min(1, sqrt(N_eff / 5))` and rank ETFs relative to peers;
- treat novelty, price-target revisions, EPS revisions, breadth, and analyst
  quality as separate diagnostics or preregistered extensions. They must not
  be silently multiplied into the canonical rating score;
- trade no earlier than the next open after public availability; a date-only
  event receives the PDF's conservative one-day delay;
- use hysteresis (enter rank 90, exit rank 70), hold at most five ETFs, cap an
  ETF at 20%, sector exposure at 40%, overlap clusters at 30%, and leave cash
  residuals when necessary; and
- use no leverage in the canonical program. Leveraged or inverse overlays are
  outside V2 until the unlevered research and risk gates pass.

Every row must retain event time, effective time, available time, ingestion
time, source identity, immutable version, and revision lineage. Current-ticker
joins are prohibited. ETF candidate weight mapping must reach at least 99% or
fail closed.

## 2. Current ACER foundation versus V2

The old ACER V1 documents are archived. The existing code and datasets are
not discarded; they are assessed below as infrastructure, not as V2
completion.

| Area | Current repository state | V2 requirement / gap | Disposition |
|---|---|---|---|
| Vendor capture | Legacy ACER byte-hash validation exists. | V2 requires semantic completeness, exact partition/page coverage, immutable source locators, amendment/deletion behavior, and transfer rights for QC. | Use only through the separate typed V2 verifier; legacy tuples are not publishable V2 evidence. |
| Event normalization | `research/acer/` produces a canonical event table with named refusals. Reviewed snapshot: 587,046 raw rows, 584,916 accepted events, 2,130 refusals (99.64% retained), roughly Dec-2011 through Aug-2026. | Add V2 institution-stock-day dedupe, event taxonomy, corrected/withdrawn-event lineage, and explicit availability rules. | Extend; do not rewrite raw history. |
| Time semantics | Date-level conservative availability exists. | V2 needs trustworthy `effective_time` and `available_time`, next-open cohorting, and explicit date-only delay. Intraday history may be incomplete. | Blocking audit. |
| Firm identity | Firm name and Benzinga firm/analyst identifiers are present in source rows. | Build durable firm identity and a firm-specific ordered-rating ontology; reject ambiguous vocabularies. | Not implemented. |
| Rating scale | No production rating scale exists. Old V1 proposed a global five-level map but it was never adopted. | V2 requires firm-specific normalized ordered scales in `[-1,+1]`. | Replace proposal; implement only after tests. |
| Signal formula | No production ACER signal exists. Old V1 proposed two encodings, 21/63/126 half-lives, coverage-neutral means, and a six-cell family. | Canonical V2 is genuine changes, 20-session half-life, decayed event sum, sector robust z-score, reliability shrinkage. | Entirely new work. |
| Consensus/novelty | No historical active-rating state engine. | Reconstruct contributor-excluded consensus with 90/180/365-day rating expiry; keep novelty diagnostic separate. | Not implemented. |
| Targets/EPS | Raw current/previous targets exist; no vetted target signal. No analyst EPS-revision history is established. | Targets and EPS are diagnostic/extension channels and need their own PIT availability, units, splits/currency, and multiplicity budget. | Deferred from canonical. |
| Issuer identity | A name/ticker diagnostic found 768 deterministic interleavings; it is explicitly a lower bound, not an allowlist. | Durable PIT security master across ticker reuse, share classes, mergers, delistings, and corporate actions. | Blocking. |
| Sector model | SIC may be locally available; no accepted PIT V2 sector taxonomy. | Robust sector standardization with a frozen, point-in-time taxonomy and sparse-sector fallback. | Not implemented. |
| Prices/outcomes | No event has been joined to price or return. The EDGAR/yfinance path lacks decision-grade delisting/terminal returns; Databento remains unmeasured. | Split/dividend-adjusted PIT total returns including delistings, next-open execution, 20-day primary horizon, and 0/5/10/20 bps cost grid. | Blocking; no look consumed. |
| ETF topology | ACER V1 deliberately deferred ETF contract; no reverse constituent index or ETF score exists. | Stock-first discovery, PIT holdings, >=99% mapped candidate weight, ETF eligibility, coverage normalization, reliability, peer ranking. | Not implemented. |
| Portfolio/QC | No ACER portfolio or QC algorithm exists. | Hysteresis, caps, overlap clusters, cash, scheduling, custom immutable signal ingest, and execution tests. | Not implemented. |
| Research design | Legacy residualized-IC/bootstrap utilities exist; old preregistration remained incomplete. | Re-preregister V2 rounds 0-8, stock/industry/ETF topology comparison, 5y/2y/1y walk-forward, 20-day primary horizon, multiplicity and permanent look ledger. | New freeze required before outcomes. |

No real-outcome research look has been performed for V2. The migration of the
existing event dataset into a V2 schema is the first bounded engineering task;
it must preserve the immutable original rather than mutating it in place.

## 3. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| ARV2-0 | Freeze schemas, ontology rules, event availability, identifiers, data quality, test family, cost model, and look budget. | Every ambiguous choice is fixed in a reviewed, content-addressed spec; no outcome code can run before that gate. |
| ARV2-1 | Audit/extend immutable ratings ingest and build firm-rating ontology with fail-closed refusals. | Synthetic and sampled structural tests; exact lineage and dedupe invariants. |
| ARV2-2 | Build PIT issuer/security master and outcome prerequisites. | Ticker reuse/share-class/delisting mutations fail; coverage and ambiguity reported. |
| ARV2-3 | Implement the canonical stock score and separate diagnostic channels. | Golden equations, sparse-sector behavior, no outcome imports, no leakage. |
| ARV2-4 | Register and run the one-shot stock-first structural/event study under the frozen budget. | Permanent look logged; a valid null closes the canonical family; the shared final holdout remains untouched. |
| ARV2-5 | Only after an ARV2-4 pass, build the PIT ETF reverse index, eligibility, mapping, and ETF aggregation. | >=99% mapped candidate weight; stale/dynamic/transitive bypasses fail. |
| ARV2-6 | Walk-forward ETF research with fixed costs and baselines. | OOS gate, robustness, capacity, turnover, overlap, and null handling. |
| ARV2-7 | Implement QC algorithm using immutable custom/precomputed signals. | Deterministic parity, scheduling, sizing, cash/cap/failure tests; still research-only. |
| ARV2-8 | Produce the lane dossier without opening the shared integration holdout. | Independent lane review complete; integration/final evaluation remains a separately owner-scheduled main-line milestone. |

ETF topology construction is deliberately downstream of the stock-first stop/go
test. A structural provider-capability audit may occur earlier, but no ETF
signal topology may be tuned or completed before ARV2-4 passes.

## 3A. Normative V2 errata and executable safety boundary (2026-08-26)

The immutable PDF remains the owner source; the following corrections are a
versioned implementation decision register for places where its equations or
prose are incomplete or internally inconsistent. They do not rewrite ACER V1
or claim a research result.

- **Package boundary:** all new contracts live in
  `research/analyst_revisions_v2/`. `research/acer/` remains legacy capture
  evidence and is never relabeled as V2.
- **Snapshot and dataset identity:** publishable data must be a typed complete
  snapshot with exact schema, booleans, requested bounds, contiguous
  partitions/pages, count reconciliation, raw-page inventory, and hashes.
  Every raw source locator receives exactly one accepted event or refusal.
  The derived identity binds the clean producing commit, schema/normalizer,
  configuration, provider contract, evidence epoch, and build recipe. A
  diagnostic incomplete snapshot has a distinct non-publishable type.
- **Canonical events:** V2 uses semantic schema
  `arv2-canonical-event-v1`, with immutable raw locator/hash, provider event
  and version IDs, revision/supersession/correction state, four timing
  instants, permanent firm/analyst/issuer/security/share-class identity,
  historical ticker validity, rating ontology evidence, and producing
  lineage. A later correction never rewrites what was known earlier.
- **Timing:** an exact public instant becomes eligible at the first exchange
  open strictly after that instant. A date-only row becomes eligible only at
  the second exchange-session open strictly after its date. Ambiguous or
  inconsistent clocks are refusals, not fractional quality discounts.
- **Validity versus quality:** timing, ontology, entity/security mapping,
  revision state, and PIT availability are binary admission gates. Only
  noncritical measurement diagnostics may enter `analyst_reliability` after
  admission. The word `confidence` is reserved for a prospectively calibrated
  quantity.
- **Breadth:** contribution probabilities contain no epsilon. Zero mass gives
  score/breadth/reliability zero. Events are aggregated by stable institution
  and common catalyst; canonical independent breadth is the conservative
  minimum of their effective counts. Raw event count is diagnostic intensity,
  not independent evidence.
- **Normalization:** no event is a structural zero; missing and invalid are
  different states. Sparse and zero-MAD groups return named refusals. Fixed
  score clipping is not called winsorization, and epsilon is never used as an
  invented variance estimate.
- **Holdings and classifications:** the content-addressed PIT holdings book
  reconciles declared and independently summed weight including explicit
  cash/derivatives, rejects duplicate or noncanonical permanent identities,
  shorts, stale/incomplete snapshots, and includes every long-equity position
  (including unmapped weight) in the coverage denominator. The portfolio and
  stock-score paths accept only reauthenticated holdings evidence with the
  fixed one-session lag and 99% threshold. ETF peer classifications likewise
  come from canonical hashed source bytes and bind ETF, holdings content, and
  decision time; a caller-supplied category label has no authority.
- **Costs:** commission, half-spread, and square-root impact are calculated in
  dollars per net security target change, then divided once by NAV. Split rows
  cannot lower impact or multiply minimum fees. Missing ADV refuses except for
  a separately labeled forced terminal exit.
- **Portfolio:** forced exits precede eligibility; incumbents use rank 70 and
  entrants rank 90; descending rank, incumbent-on-exact-tie, then permanent ID
  is the total order. A strictly stronger entrant may evict the weakest
  incumbent. The hard five-name, 20% ETF, 40% look-through sector, and 30%
  overlap-cluster caps are never relaxed; inverse-volatility redistribution
  stops at constraints and leaves residual cash.
- **Provider history:** Snapshot A factually contains 5 accepted 2011 events,
  24,296 in 2012, and 28,609 in 2013. Every pre-2013 source row is quarantined
  with the exact named refusal
  `provider_backfill_semantics_unverified_pre_2013` until provider
  coverage/backfill semantics are reviewed; a later row cannot use that
  refusal. Partition year must equal event effective year, so a caller cannot
  launder an early event through a later partition. The PDF's 2013 design
  statement is not used to erase measured bytes.
- **Legacy outcome runners:** the rejected target/timing runners are
  quarantined before data fetch. They require a permanent owner registry ID
  and exact frozen local artifact, remain non-new/non-V2, have no network
  fallback, and cannot update active findings.

The machine-readable round-0 inventory is
`research/analyst_revisions_v2/specs/arv2_round0.draft.json`. It is deliberately
`blocked_owner_decisions`, not outcome-executable: the common final holdout,
contaminated periods, corporate-action source, exact universe, normalization
fallback, primary stock cell IDs, multiplicity IDs, and lane validation dates
still require owner decisions. The strict loader returns a distinct draft
type. A future executable spec must be committed and clean, match an entry in
the separate committed review registry, bind its exact independently reviewed
Git blob and review ancestry, and pass semantic validation of every mandatory
cell. Outcome authorization must then reauthenticate that source and obtain an
atomic spend receipt from an independently pinned, cross-machine append-only
permanent-look authority before any outcome I/O. No local file or SQLite
database can grant or reset that authority. The request must also bind frozen
data/code/cost identity, the one-shot period, a purged split, horizon-sized
embargo/bootstrap block, every mandatory control, stock-primary topology, and
proof that it ends before the shared holdout. Both the reviewed-spec registry
and external spend-authority integration are presently absent: the committed
authority artifact declares exact `zero_access`, every authorization attempt
refuses before the outcome loader can execute, and the legacy machine-local
ledger path has no authority. No outcome was loaded and no look was consumed
by this work.

Source precedence is explicit: normative strategy design governs the intended
formula, while observed provider availability/history governs factual data
claims. Neither category is permitted to overwrite the other.

## 4. First implementation scope

The first Codex implementation session should implement **tests and schema
only for ARV2-0/ARV2-1**:

1. pin the V2 raw/canonical fields and availability ordering;
2. prove institution-stock-day deduplication and corrected-event lineage;
3. build a versioned, data-derived firm-rating vocabulary inventory without
   assigning outcome-informed scores;
4. add dangerous-direction tests for global-map fallback, current-ticker
   joins, date-only same-day trading, and silent unknown-rating coercion; and
5. update this record before the first push.

Do not add a price join, calculate forward returns, tune a rating order from
returns, construct ETFs, or launch QuantConnect in this milestone.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | V2 source reviewed; legacy/current gap measured; no implementation. | PDF text and all 64 rendered pages inspected; no outcome access; 0 looks. | V2 is a replacement, not a parameter patch. | Claude reviews the documentation baseline; implementation waits for owner instruction. |
