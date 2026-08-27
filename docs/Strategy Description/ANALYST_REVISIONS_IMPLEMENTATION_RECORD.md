# Analyst Revisions ETF Strategy V2 — implementation and session record

Status: **ARV2 CONTRACT/SAFETY CANDIDATE ASSEMBLED BUT UNACCEPTED; PENDING
CLAUDE REVIEW OF THE EXACT PUSHED SNAPSHOT AND CODEX COUNTER-REVIEW OF CLAUDE'S
EXACT REVIEWED PUSH. NO AUTHENTICATED PRODUCTION EVENT EXISTS. NO V2
SIGNAL/SCORE, CROSS-SECTION, NONEMPTY PORTFOLIO, OUTCOME TEST, QC RESULT, OR
DEPLOYMENT EXISTS.**

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
`docs/SESSION_HANDOFF.md` outside an explicit owner-directed common
reconciliation; this record is the lane's status and handoff.

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

| Area | Current repository state | Remaining production/evidence gate | Disposition |
|---|---|---|---|
| Snapshot and source authority | V2 has strict complete and diagnostic snapshot types, exact partition/page/raw-inventory reconciliation, immutable locator/hash checks, and clean producing-lineage bindings. The canonical checked-in research-source authority is an exact `zero_access` declaration with no positive entries and cannot be rebound at runtime. | A separately governed, append-only production-source authority must admit an exact real artifact after source entitlement, semantics, completeness, retention, and exact vendor permission/rights for transfer to QuantConnect/QC processing are independently established. | Safety primitive implemented; production source access refuses; pending review/counter-review. |
| Event normalization | V2 has typed canonical-event/refusal/result contracts, exactly-one disposition, correction/supersession lineage, build-recipe identity, post-construction revalidation, and immutable dataset publication checks. Legacy `research/acer/` rows remain legacy evidence. | No deterministic provider-specific raw-to-canonical V2 normalizer exists. Accepted production rows therefore remain prohibited; only exhaustive refusal results can be formed. | Contract implemented; accepted-event boundary deliberately zero-access. |
| Time semantics | Exchange-session availability rules, strict UTC instants, next-open handling, and the conservative date-only delay are implemented as deterministic contracts. | Provider clock semantics and actual timestamp completeness have not been authenticated for a production V2 snapshot. | Safety rule implemented; no production event admitted. |
| Firm identity and rating ontology | Permanent firm/analyst identities, ontology evidence, genuine-change admission, and verified-policy bindings are represented by strict contracts. | No production firm-specific ordered vocabulary, reviewed policy artifact, or authenticated identity mapping exists. | Schema/admission layer implemented; production catalog empty. |
| Canonical stock formula | Deterministic primitives cover genuine changes, 20-session decay, independent breadth, robust sector normalization, reliability shrinkage, and explicit invalid/sparse states. | No authenticated production events, sector classifications, or score artifact exist. | Formula safety primitives implemented; no production signal or score. |
| Consensus, novelty, targets, and EPS | Canonical-versus-diagnostic separation is contract-pinned; legacy target/timing runners are quarantined from V2 and from new outcome access. | No production historical active-rating state, novelty series, or decision-grade target/EPS extension has been built or authorized. | Deferred diagnostics/extensions; they cannot alter the canonical score. |
| Provider-history boundary | Measured pre-2013 source rows have a named quarantine rule and cannot be laundered through a later partition; normative strategy design remains separate from observed provider history. | Provider coverage, backfill, correction, and deletion semantics remain unauthenticated for V2 production use. | Refusal rule implemented; factual provider audit still required. |
| Issuer/security identity | V2 contracts require permanent issuer/security/share-class identities and historical ticker validity. A legacy name/ticker diagnostic found 768 deterministic interleavings; it is a lower bound, not an allowlist, and current-ticker joins are prohibited. | No accepted PIT security master covering ticker reuse, share classes, mergers, delistings, and corporate actions exists. | Identity admission implemented; real mapping remains blocked. |
| Sector/classification | Strict PIT classification evidence, freshness, content identity, and reauthentication boundaries exist. | The production classification source catalog is empty; no accepted PIT V2 taxonomy exists. | Consumer safety implemented; production classification access refuses. |
| Prices, outcomes, and costs | Strict terminal-event and transaction-cost contracts enforce decimal arithmetic, one net security change, explicit ADV, and source reauthentication. No event has been joined to a later price or return; Databento remains unmeasured. | Production cost/ADV/terminal-return catalogs are empty; owner-frozen outcome inputs and authorized permanent-look infrastructure do not exist. | Cost safety primitives implemented; no outcome I/O and zero looks. |
| ETF holdings/topology | PIT holdings, declared-versus-summed weight reconciliation, stale/incomplete refusal, fixed lag, 99% coverage, eligibility, and stock-score lineage primitives exist. | No authenticated production holdings or stock-score artifact exists, so no production reverse index, ETF score, or peer topology exists. | Consumer safety implemented; production topology remains zero-access. |
| Cross-section and portfolio | Deterministic rank/hysteresis/tie/eviction/cap/overlap/cash allocator primitives and verified policy bindings exist. | No reviewed simultaneous rank/volatility derivation or authenticated rank/classification/cost source exists. The public boundary therefore refuses every nonempty portfolio and can return only the safe empty/all-cash result. | Dormant safety algorithm implemented; no research portfolio or QC result. |
| Preregistration and outcome gate | A strict draft-spec loader, semantic validator, reviewed-source checks, immutable lineage bindings, one-use period rules, and fail-closed outcome permit boundary exist. | Required owner decisions remain open; the independently reviewed exact-spec registry is empty; no independent review anchor or external cross-machine append-only permanent-look authority exists. | Validation/gating primitives implemented; every outcome authorization refuses. |
| Architecture and legacy quarantine | The V2 package is registered as a research entry point, guarded against reverse imports from legacy ACER, and keeps the legacy outcome runners non-new/non-V2 with no network fallback. | Independent review and Codex counter-review of the exact candidate are still required. | Candidate assembled, not accepted. |

The production source/classification/cost/rank catalogs remain empty. The
canonical source authority permits no positive production source; accepted
normalization and nonempty-portfolio boundaries both refuse. Accordingly there
is no authenticated production event, score, cross-section, nonempty portfolio,
outcome, or QC result. No real-outcome research look has been performed for V2,
and this implementation consumed **zero looks**.

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
- **Production admission:** the canonical checked-in research-source authority
  is an exact immutable `zero_access` declaration with no positive entries and
  no runtime registration seam. Every source-dependent production consumer
  refuses. Normalization likewise prohibits accepted rows until a deterministic
  provider-specific raw-to-canonical normalizer is implemented and reviewed;
  current exhaustive builds may contain refusals only. The production
  source/classification/cost/rank catalogs remain empty.
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

## 4. Exact next step

The next step is acceptance of the existing contract/safety candidate, not a
new research milestone:

1. place the shared and Analyst-only remediation commits on
   `codex/strategy-analyst-revisions-v2`, validate the exact candidate, append
   its exact push row below, and push it without opening any data or outcome
   authority;
2. Claude independently reviews that exact pushed snapshot commit by commit
   and pushes the complete disposition and any corrections to the same lane;
3. Codex counter-reviews Claude's exact reviewed push, including dangerous-
   direction regression evidence, before the candidate can be accepted; and
4. only after that review chain closes may the Action Plan authorize another
   bounded milestone. Owner decisions, a reviewed spec anchor, governed source
   admission, and external append-only permanent-look authority must still be
   closed before any production normalization, price/outcome join, real score,
   ETF construction, nonempty portfolio, QC run, or QuantConnect launch.

Until those steps are recorded, the candidate remains unaccepted and all
production research and outcome boundaries remain zero-access.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | V2 source reviewed; legacy/current gap measured; no implementation. | PDF text and all 64 rendered pages inspected; no outcome access; 0 looks. | V2 is a replacement, not a parameter patch. | Claude reviews the documentation baseline; implementation waits for owner instruction. |
| 2026-08-27 | Codex implementation | `a4f58e6` -> `653a9c0` (code snapshot; this lane-record commit follows) | Owner-authorized one-time common remediation synchronization | Synchronized the bounded shared-remediation series through `7029acb`, then identical final shared patch `68ae4b4` (source `6770db3`, stable patch ID `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`) and Analyst-only decimal/structural-zero hardening `653a9c0` (source `66168ed`). No other strategy implementation entered this lane. | Exact lane tree: 5,434 passed, 2 skipped, 25 dependency-deprecation warnings in 39m14s; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean; worktree clean. No provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or live scheduler access; **0 research looks**. | Independent final audits found no remaining P0-P3 issue in the synchronized diff. Synchronization is not acceptance; candidate remains zero-access and unaccepted. | Push this exact lane-recorded snapshot; Claude reviews every pushed commit on this lane, then Codex counter-reviews every Claude commit before any next milestone. |
