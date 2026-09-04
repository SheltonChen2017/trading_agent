# Analyst Revisions ETF Strategy V2 — implementation and session record

Status: **ARV2-1 ACCEPTED. ARV2-2 PIT IDENTITY/OUTCOME-PREREQUISITE CANDIDATE
ACCEPTED AFTER CLAUDE REVIEW AND CODEX COUNTER-REVIEW CORRECTION. ARV2-3
OUTCOME-FREE STRUCTURAL STOCK-SCORE CANDIDATE ACCEPTED AFTER INDEPENDENT
CLAUDE REVIEW AND CODEX COUNTER-REVIEW CORRECTION. THE OWNER-DIRECTED QC-FIRST
OUTCOME-FREE PLAN (ARV2-3Q) IS ACCEPTED AFTER INDEPENDENT CLAUDE REVIEW AND
CODEX COUNTER-REVIEW CORRECTION. ARV2-4A OUTCOME-FREE STRUCTURAL PREREQUISITES
ARE ACCEPTED AT CODEX COUNTER-REVIEW AFTER INDEPENDENT CLAUDE REVIEW. THE
COUNTER-REVIEW CORRECTIONS AND THE PROJECT-WIDE MAIN SYNCHRONIZATION ARE
ACCEPTED AFTER INDEPENDENT CLAUDE REVIEW AND CODEX COUNTER-REVIEW CORRECTION
(SECTIONS 7-8). THE OWNER-AUTHORIZED OUTCOME-FREE, CONTENT-ADDRESSED
FOLD-MANIFEST-ONLY STRUCTURAL CANDIDATE (ARV2-4B) IS ACCEPTED AFTER
INDEPENDENT CLAUDE REVIEW AND CODEX COUNTER-REVIEW CORRECTION (SECTIONS
9-11). A COMPLETE INDEPENDENT WHOLE-LANE RE-REVIEW (SECTION 13) ACCEPTED
THE CUMULATIVE TREE AFTER CORRECTING THREE P2 FAIL-OPEN/CONSISTENCY
DEFECTS. CODEX COUNTER-REVIEW ACCEPTS BOTH CLAUDE COMMITS AFTER ADDITIONAL
MATERIAL SAFETY AND RECORD CORRECTIONS (SECTION 14). THE OWNER APPROVED THE
FULL 39-ALIAS LEGACY COMPARATOR AND CORRECTED MATCHED-ROW RULES. THE
OUTCOME-FREE, CONTENT-ADDRESSED ARV2-4C STRUCTURAL CANDIDATE IS ACCEPTED
AFTER INDEPENDENT CLAUDE REVIEW AND ONE TEST-COVERAGE CORRECTION (SECTIONS
15-16). CODEX COUNTER-REVIEW ACCEPTS BOTH CLAUDE COMMITS AFTER ONE
RECORD-ONLY DAG-WORDING CORRECTION (SECTION 17). THE OWNER APPROVED THE
RECOMMENDED ARV2-4D-A POWER POLICY. THE OUTCOME-FREE, CONTENT-ADDRESSED
CALIBRATION-PROTOCOL CANDIDATE IS ACCEPTED AFTER INDEPENDENT CLAUDE REVIEW
AND CODEX COUNTER-REVIEW CORRECTION (SECTIONS 18-20); ITS NUMERIC
CALIBRATION RECEIPT AND EVERY OUTCOME-BEARING ACTION REMAIN SEPARATELY
GATED. THE OWNER-DIRECTED FOUR-FAMILY MULTIPLICITY RE-FREEZE (ARV2-3Q-F)
IS ACCEPTED AFTER INDEPENDENT CLAUDE REVIEW, FOUR P3 HARDENING CORRECTIONS,
AND CODEX COUNTER-REVIEW RECORD CORRECTIONS (SECTIONS 21-23). IT MAKES THE
EFFECTIVE ANALYST ALLOCATION `1/80`, REFUSES FALLBACK TO THE
SUPERSEDED-UNSPENT `1/60`, AND GRANTS NO DATA, OUTCOME, QC, DEPLOYMENT, OR
TRADING AUTHORITY.
THE OWNER LATER AUTHORIZED ONLY THE BOUNDED, OUTCOME-FREE ARV2-4D-B1
CALIBRATION-INPUT MANIFEST-SCHEMA MILESTONE. ITS CONTENT-ADDRESSED SCHEMA AND
IN-MEMORY SYNTHETIC-FIXTURE VALIDATOR ARE IMPLEMENTED AS A CANDIDATE PENDING
INDEPENDENT CLAUDE REVIEW AND CODEX COUNTER-REVIEW (SECTION 24). ARV2-4D-B1
CANNOT LOAD A PRODUCTION MANIFEST OR INPUT, COMPUTE A CALIBRATION, ISSUE A
NUMERIC RECEIPT, ACCESS OUTCOMES OR QC, DEPLOY, OR TRADE. THE FULL
ARV2-4D-B MILESTONE REMAINS SEPARATELY GATED.
THE ARV2-4 EVALUATION AND EVERY
DATA, OUTCOME,
UPLOAD, COMPILE, QC-RUN, PAPER, OR FUNDED ACTION REMAIN BLOCKED BY THE
RECORDED SOURCE, RIGHTS, REVIEW, RUN-IDENTITY, AND ONE-USE AUTHORITY GATES.
NO AUTHENTICATED PRODUCTION EVENT EXISTS. NO V2 SIGNAL/SCORE/CROSS-SECTION
WITH PRODUCTION OR EXECUTABLE AUTHORITY, NONEMPTY PORTFOLIO, OUTCOME TEST,
QC RESULT, OR DEPLOYMENT EXISTS.**

Branch: `codex/strategy-analyst-revisions-v2`

Owner lane scope, 2026-08-29: this branch is exclusively for Analyst
Revisions V2 strategy code, tests, documentation, and its eventual
QuantConnect test path. Trading App and Streamlit UI work are out of scope
unless the owner explicitly changes this direction. Owner clarification,
2026-08-29: successful completion of all prior research, review, validation,
and deployment gates may eventually lead to live trading through QuantConnect;
that destination grants no present QC-job, deployment, or trading authority.

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
| Snapshot and source authority | V2 snapshot manifest v2 now binds the exact capture instant as well as complete/diagnostic type, partition/page/raw inventory, locator/hash, and clean producing lineage. Capture chronology cannot postdate verification and is part of every downstream manifest identity. The checked-in research-source authority remains an exact immutable `zero_access` declaration with no positive entries. | A separately governed, append-only production-source authority must admit an exact real artifact after source entitlement, semantics, completeness, retention, and exact vendor permission/rights for transfer to QuantConnect/QC processing are independently established. | ARV2-1 structural ingest accepted; production source access still refuses. |
| Event normalization | In addition to the zero-access canonical-event/refusal/result contracts, V2 now has a content-addressed Massive/Benzinga provider contract, exact documented field/action parsing, one source-derived ingest disposition per raw row, duplicate-ID refusal, immutable raw-hash version IDs, two-snapshot correction/addition/disappearance lineage, and an exhaustive structural binding of accepted rows to PIT permanent identity or a named refusal. The firm/identity join retains the exact ARV2-1 rational mapping. Legacy `research/acer/` rows remain legacy evidence. | The production source, security-master, and firm-ontology registries are empty. The older zero-access `CanonicalSourceEvent` representation is not yet a publishable rational firm-score event, and no real event has passed production registration. | ARV2-1 accepted; ARV2-2 structural identity candidate implemented; accepted production events remain prohibited. |
| Time semantics | Exchange-session availability rules, strict UTC instants, next-open handling, and the conservative date-only delay are implemented as deterministic contracts. | Provider clock semantics and actual timestamp completeness have not been authenticated for a production V2 snapshot. | Safety rule implemented; no production event admitted. |
| Firm identity and rating ontology | A loader-authenticated, content-addressed mapping now requires firm ID/name, half-open valid date range, exact raw label, complete ordered rank/scale size, company/sector/absolute scope, mapping quality, reviewer, source evidence, and ontology version. It implements the blueprint score as an exact rational number, refuses unreviewed labels and periods, inventories observed labels without ordering them, admits only direction-consistent upgrades/downgrades, and keeps initiations, target-only actions, and terminations out of the rating-change channel. The committed production registry remains empty, and positive registration now also refuses until a separate non-self-referential approval receipt exists. | No production firm-specific ordered vocabulary, reviewed policy artifact, authenticated permanent firm/analyst identity mapping, or external registration-approval authority exists. No label is inferred from the public sample or legacy ACER map; documented `assumes` remains quarantined pending semantic review. | ARV2-1 accepted; production ontology access refuses. |
| Canonical stock formula | ARV2-3 adds exact 20-session exponential decay without a hard cutoff, NYSE-session age derived inside the assembler, institution-stock-session dedupe, rational rating deltas, stable raw summation, absolute-mass institution/catalyst breadth, activity-aware sector median/MAD normalization with the frozen 1.4826 scale and symmetric ±4 clip, and the stock-specific `N_eff / (N_eff + 3) * q_data` reliability. ARV2-4A adds an authenticated structural stock-evaluation contract and fixture-only same-date robust control transform, training-only Decimal QR fit, and unchanged validation/test application with exact contract/fold/policy/refusal lineage, reauthenticated NYSE-open decision clocks, and process-local builder identity/digest authentication that refuses copied, reconstructed, or relabeled cross-sections. ARV2-4B adds the exact content-addressed six-fold NYSE walk-forward child manifest without wiring it into fit/apply. ARV2-4C adds the owner-approved, exact 39-alias naive global comparator, matched-row/coverage/bootstrap contract, and acyclic stock-contract successor while preserving the reviewed fold bytes and the predecessor's single-arm refusal rules. ARV2-4D-A adds the owner-approved, outcome-free power-calibration policy and authenticated provisional planning arithmetic without any calibration receipt. | No authenticated production events, controls, institution/common-event mappings, PIT sector classifications, measured quality, reviewed/executable fold integration, numeric power receipt, outcomes, or production score artifact exists. ARV2-4C and corrected ARV2-4D-A are accepted after independent review and Codex counter-review; every action capability remains false. | ARV2-3 and ARV2-3Q accepted; corrected ARV2-4A, ARV2-4B, ARV2-4C, and ARV2-4D-A accepted after independent review and Codex counter-review; no executable score exists. |
| Consensus, novelty, targets, and EPS | Canonical-versus-diagnostic separation is contract-pinned; legacy target/timing runners are quarantined from V2 and from new outcome access. | No production historical active-rating state, novelty series, or decision-grade target/EPS extension has been built or authorized. | Deferred diagnostics/extensions; they cannot alter the canonical score. |
| Provider-history boundary | Measured pre-2013 source rows retain the exact dominant quarantine even when another defect is present and cannot be laundered through a later partition. Chronologically captured snapshots compare stable IDs/raw hashes as unchanged, added, corrected, or missing-from-later-without-invented-withdrawal. | Provider coverage, backfill, correction, and deletion semantics remain unauthenticated for V2 production use; no current licensed snapshot was accessed in this milestone. | Structural lineage implemented; factual provider audit still requires exact owner authorization. |
| Issuer/security identity | A canonical, content-addressed, loader-reauthenticated PIT master now separates issuers, securities, share classes, vendor/standard identifiers, listings, and lineage. It binds base and interval-closure availability, redacts future endpoints, resolves historical tickers by event date/cutoff, preserves ticker reuse and share classes, represents symbol/listing changes, mergers and delistings, refuses ambiguity/ineligibility/late evidence, and reports exhaustive integer coverage. The legacy name/ticker diagnostic's 768 deterministic interleavings remain a lower bound, not an allowlist; current-ticker joins are prohibited. | The committed production security-master registry is empty. No real source, rights/entitlement evidence, production vintage/correction builder, accepted mapping, or external registration-approval authority exists; structural fixtures cannot self-promote. | ARV2-2 structural identity work accepted; production identity access refuses. |
| Sector/classification | Strict PIT classification evidence, freshness, content identity, and reauthentication boundaries exist. | The production classification source catalog is empty; no accepted PIT V2 taxonomy exists. | Consumer safety implemented; production classification access refuses. |
| Prices, outcomes, and costs | Strict terminal-event and transaction-cost contracts enforce decimal arithmetic, one net security change, explicit ADV, and source reauthentication. ARV2-2 now derives a revalidatable, fail-closed inventory of in-range merger/delisting terminal-return requirements and never silently omits an unavailable terminal name. No event has been joined to a later price or return; Databento remains unmeasured. | Production split/dividend, cost/ADV, and terminal-return catalogs are empty; owner-frozen outcome inputs and authorized permanent-look infrastructure do not exist. | Outcome prerequisites implemented structurally; no outcome I/O and zero looks. |
| ETF holdings/topology | PIT holdings, declared-versus-summed weight reconciliation, stale/incomplete refusal, fixed lag, 99% coverage, eligibility, and stock-score lineage primitives exist. | No authenticated production holdings or stock-score artifact exists, so no production reverse index, ETF score, or peer topology exists. | Consumer safety implemented; production topology remains zero-access. |
| Cross-section and portfolio | Deterministic rank/hysteresis/tie/eviction/cap/overlap/cash allocator primitives and verified policy bindings exist. | No reviewed simultaneous rank/volatility derivation or authenticated rank/classification/cost source exists. The public boundary therefore refuses every nonempty portfolio and can return only the safe empty/all-cash result. | Dormant safety algorithm implemented; no research portfolio or QC result. |
| Preregistration and outcome gate | A strict draft-spec loader, semantic validator, reviewed-source checks, immutable lineage bindings, one-use period rules, and fail-closed outcome permit boundary exist. The retired 2026-09-01 through 2027-08-31 period refuses as superseded unspent. Exact loaders authenticate the accepted QC-first parent and corrected ARV2-4A/4B/4C/4D-A structural descendants while every side-effect capability remains literal false. ARV2-3Q-F adds an authenticated four-family multiplicity overlay with no fallback to the old `1/60` allocation. The owner-authorized ARV2-4D-B1 candidate adds only a content-addressed calibration-input manifest schema and an in-memory canonical synthetic-metadata validator; it implements no production manifest loader, input read, calibration, or receipt. | Later executable-spec integration remains required. The reviewed-spec registry and ARV2-4D-B numeric receipt are empty; no production manifest, source/input access, nuisance-computation authority, source/run binding, external review anchor, upload/compile/launch authority, evaluation authority, paper look, or deployment authority exists. Every future outcome-bearing composition must authenticate separately reviewed multiplicity and power-protocol leaves. | Old prospective candidate retired with zero looks; ARV2-3Q and corrected ARV2-4A/4B/4C/4D-A accepted; ARV2-3Q-F accepted after independent review and Codex counter-review; ARV2-4D-B1 is an implementation candidate pending both reviews; every outcome/QC authorization refuses. |
| Architecture and legacy quarantine | The V2 package is registered as a research entry point, guarded against reverse imports from legacy ACER, and keeps legacy outcome runners non-new/non-V2 with no network fallback. ARV2-3, the accepted QC-first parent, corrected ARV2-4A/4B/4C/4D-A modules, ARV2-3Q-F, and the ARV2-4D-B1 candidate are in the exact 34-module transitive import firewall and reach neither outcomes, execution, QC transport, nor legacy ACER. Structural evidence remains fixture-only and every consumer reauthenticates nested immutable lineage. | Production source, ontology, security-master, institution, common-event, classification, quality, outcome, look, QC, and execution authorities remain absent or zero-access. | ARV2-3Q and corrected ARV2-4A/4B/4C/4D-A accepted; ARV2-3Q-F accepted after independent review and Codex counter-review; ARV2-4D-B1 is a zero-authority candidate pending review. |

The production source, firm-ontology, security-master, classification, cost,
and rank catalogs remain empty. The canonical source authority permits no
positive production source; accepted
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
| ARV2-3Q | Freeze the outcome-free control, stock-event-study, QC-first, multiplicity, paper-confirmation, and funded-pilot separation contract. | Content-addressed candidate independently reviewed; old period proved superseded unspent; zero data/outcome/QC/deployment authority. |
| ARV2-3Q-F | Apply the owner-directed four-lane selection-family re-freeze as an additive outcome-free overlay without rewriting accepted ancestors. | Exact `1/20` family and four permanent `1/80` maxima, unused/withdrawn slots expire without transfer or denominator change, old `1/60` authenticated only as superseded-unspent, absence/clone/substitution refuses, every action capability false, and independent Claude review plus Codex counter-review required. |
| ARV2-4A | Materialize the content-addressed stock historical-evaluation structure and fixture-only mandatory-control transform/fit/apply boundary without sources or outcomes. | Exact parent/PDF binding, training-only fold/policy lineage, named row refusals and coverage, immutable report inventory, all external bindings null, all action capabilities false, independent Claude review and Codex counter-review required. |
| ARV2-4B | Freeze the exact outcome-free stock walk-forward fold manifest as an acyclic child of the reviewed QC-first plan and stock-evaluation history definition. | Six rolling 5/2/1 folds, exact 1/5/20/60-session purge and embargo boundaries, NYSE-axis and parent-artifact hashes, partial-2026 exclusion and common-event refusals; all external bindings null and all action capabilities false; independent Claude review and Codex counter-review required. |
| ARV2-4C | Freeze the owner-approved 39-alias naive global comparator and the corrected matched-row comparison as an outcome-free successor of the reviewed stock/fold authorities. | Exact 39 mapped and 15 measured-refusal aliases, symmetric paired-only zero-range handling, five 19/20 structural coverage ledgers pooled and per fold, complete-session deterministic bootstrap, unchanged predecessor/fold bytes, complete acyclic lineage, all action capabilities false, independent Claude review and Codex counter-review required. |
| ARV2-4D-A | Freeze the owner-approved minimum meaningful effect, target power, calibration window, HAC/component arithmetic, fixed-capacity disposition, and disclosure boundary without reading calibration inputs. | Content-addressed protocol with exact Decimal constants/order, complete 483-session pre-test axis, lag-20 missing-gap-preserving HAC, q05 component floor, 1,388-session fixed capacity, authenticated provisional helper, all receipt/action bindings null or false; independent Claude review and Codex counter-review required. |
| ARV2-4D-B1 | Freeze the outcome-free calibration-input manifest schema and validate only caller-supplied canonical synthetic metadata in memory. | Content-addressed schema bound only to accepted ARV2-4D-A; exact 483-session axis, evidence-epoch cutoff, input-role/count censuses, rights and closed lineage contracts; every external authority null and every action capability false; independent Claude review and Codex counter-review required before any production-input work. |
| ARV2-4D-B | Under separate exact calibration-input authority, compute and bind the numeric power receipt and required date/component floors in a new stock successor without changing reviewed ancestors. | Reviewed input-manifest schema/rights/lineage, authenticated nuisance-only calibration, closed numeric receipt, no research result, no outcome-informed rescue, and independent review/counter-review before any ARV2-4 run. |
| ARV2-4 | Materialize the full V2 historical-evaluation schema, implement the frozen stock control adjustment, bind the exact QC run and power plans, and run the one-shot historical stock event study in QC Cloud. | Immutable development-evaluation receipt logged with no confirmatory alpha; a screen failure or valid null closes the canonical family, while a pass unlocks ARV2-5 only. |
| ARV2-5 | Only after an ARV2-4 pass, build the PIT ETF reverse index, eligibility, mapping, and ETF aggregation. | >=99% mapped candidate weight; stale/dynamic/transitive bypasses fail. |
| ARV2-6 | Freeze the ETF-specific residualization, estimand, power, and cost contracts, then run the one-shot walk-forward ETF historical backtest in QC Cloud. | Immutable development-evaluation receipt logged with no confirmatory alpha; OOS/robustness/capacity/turnover/overlap screen; failure closes the family. |
| ARV2-7 | Implement the QC paper algorithm using immutable custom/precomputed signals. | Deterministic research/backtest/paper parity, scheduling, sizing, cash/cap/failure tests; no deployment authority. |
| ARV2-8 | Produce the paper-ready lane dossier and freeze the exact future evidence epoch before observation. | Independent review complete; exact future dates and shared-holdout treatment owner-frozen; paper deployment separately authorized. |
| ARV2-9 | Run 252 NYSE sessions in QC Paper Trading as the blind prospective confirmation vehicle. | The sole Analyst prospective look is irrevocably committed on its first accepted observation and reaches one terminal state; efficacy remains sealed until a valid final unseal, and invalid/underfilled closure cannot reuse alpha or create a replacement look. |
| ARV2-10 | Optionally consider a small funded QC canary after a successful paper confirmation. | New exact owner live-risk authority, account/risk/run bindings, review, kill switch, reconciliation, and no leverage/shorts/options; no paper authority converts. |

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

The former machine-readable round-0 inventory remains at
`research/analyst_revisions_v2/specs/arv2_round0.draft.json` as the exact
content-addressed predecessor
`arv2-round0-candidate-8d13a0a4577df322` / SHA-256
`8d13a0a4577df3223c96c4c11722457e059b4ade63f578ab860ce7364494e847`.
Owner direction on 2026-08-30 superseded its planned-unbound
2026-09-01 through 2027-08-31 look before any dataset/code binding, review
registration, outcome access, or spend. It therefore consumed **zero looks**.
The legacy v1 loader remains usable only for migration/structural validation:
the old look identity and exact period refuse, its only replacement identity is
explicitly `migration-only`, and its public outcome-authority entry point
always refuses. It cannot authorize ARV2-4, be relabeled prospective, or be
backfilled. A separate complete V2 historical-evaluation schema is required.

The active outcome-free hash-bound amendment, not a complete successor spec, is
`research/analyst_revisions_v2/specs/arv2_qc_first.draft.json`, authenticated by
`research/analyst_revisions_v2/qc_first_plan.py` as
`arv2-qc-first-plan-36e455e72b8750fe` / SHA-256
`36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc`.
Its authority is exactly
`planning_only_no_data_no_outcome_no_qc_action_no_deployment`; its public
upload, historical-launch, paper-deployment, and funded-live capabilities are
all constant false.

ARV2-4A's corrected checked-in child is
`research/analyst_revisions_v2/specs/arv2_stock_historical.structural.json`,
authenticated by `stock_evaluation_contract.py` as
`arv2-stock-historical-c5ff2a6a0dcf341e` / SHA-256
`c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b`.
The original reviewed candidate
`arv2-stock-historical-dcc30556b6fb582b` is superseded by the section 4S
counter-review corrections; it was never bound to data, outcomes, or QC.
The corrected child's internal `pending_independent_review` status is an
immutable candidate-lifecycle label, not the current handoff state. That exact
hash has since completed independent Claude review and Codex counter-review;
future content-addressed successors must carry their own review lifecycle.
It binds the strategy PDF and corrected QC-first parent, uses strict canonical
UTF-8 bytes and content-derived section identities, and contains no results.
Every external source, comparator, fold-manifest, power, registry, economic,
liquidity, dataset, code, QC-plan, or evaluation-receipt binding is null; source,
outcome, upload, compile, launch, disposition, paper, funded, and order
capabilities are all false.

The amendment freezes the stock control/event-study constraints and makes every
remaining executable definition an explicit null hash rather than choosing it
after outcomes. ARV2-4A now implements the structural control transform and
fixture-only fit/apply boundary: coefficients fit only active stock rows in each
training fold after same-date accepted-row transforms, then apply unchanged to
validation/test; structural zeros remain exact zero. The detailed production
control-source definition, fold manifest, global map/matched comparison, power,
reporting registries, economic gate, and liquidity bindings remain null, so
stock execution is constant false. ETF residualization is a
different contract deliberately deferred to ARV2-6 and may not reuse stock
coefficients. Mandatory controls cover the PDF's full momentum, peer momentum,
earnings/guidance proximity, immediate event jump, beta/volatility,
value/growth/size, liquidity/turnover, holdings concentration, analyst coverage,
event-intensity, and event-diversity families. Immediate event jump is
outcome-regression-only and missing active-event intraday evidence refuses.

ARV2-4C leaves that predecessor and the reviewed fold manifest byte-for-byte
unchanged. Its three new canonical artifacts are the global map
`arv2-global-rating-map-aaf5830c3c3fb403` / SHA-256
`aaf5830c3c3fb403b0e84f5ad22d1f20fa3f91df41cf3bd64f33695875d2e3d9`,
the matched comparison
`arv2-global-matched-b94a3457b848c4dc` / SHA-256
`b94a3457b848c4dc1f6dee77ef366002362573431eb9cc2fc3b8f530ec7f89c9`,
and the stock successor
`arv2-stock-historical-successor-a9a2210b8f6582bc` / SHA-256
`a9a2210b8f6582bc3ce9e533ce33e9b51ffc0a0b3203b62ad21d9d373ce06f95`.
They authenticate the PDF, QC-first amendment and its exact superseded base,
the predecessor stock contract, and the unchanged fold manifest in a complete
acyclic graph. Every source, outcome, QC, result, deployment, and order
capability remains false.

The stock development screen reports 1/5/20/60-session date-level Spearman IC
summaries and Fama-MacBeth coefficients, with 20 sessions primary, bullish and
bearish effects separate, horizon-specific embargo/block/HAC distances measured
on the actual NYSE-session axis, 19,999 centered block resamples, and the PDF's
predeclared earnings cohorts. A deterministic bipartite common-event graph puts
each outcome in exactly one component; cross-date components refuse before fold
assignment, so neither folds nor date blocks split them. PRIMARY, SECONDARY, and
EXPLORATORY outputs are labeled; secondary FDR and deflated-Sharpe reports are
non-rescuing and their exact hypothesis/trial registries must be hashed before a
run. The exact primary cost gate is 10 bps **per side**. Liquidity impact is a
non-promoting diagnostic until its coefficient, dollar-NAV grid, and ADV
convention are separately frozen. ARV2-4D-A freezes the content-addressed
power-calibration method, and ARV2-4D-B1 now freezes only the outcome-free
calibration-input manifest schema. The production manifest, authenticated
inputs, numeric ARV2-4D-B receipt, and bound floors remain null and are hard
pre-launch gates rather than post-result choices.

The historical stock and ETF QC runs are immutable **development evaluations**,
not permanent looks and not prospective confirmation; each failure closes the
family, while a pass unlocks only the next bounded stage. The fixed history
cutoff is 2026-08-28, with last mature decision sessions 2026-08-27,
2026-08-21, 2026-07-31, and 2026-06-03 for horizons 1, 5, 20, and 60. Later
decisions are named immature refusals and cannot be filled with later data.

Only the future QC Paper confirmation consumes formal alpha: one Analyst-lane
look at `1/80` under the effective four-lane correction. The predecessor
`1/60` allocation is superseded-unspent and nonrevivable. The look's dates,
estimand, power-plan hash, and evidence epoch are deliberately null and
non-backfillable until
ARV2-4/5/6/7/8 pass and the exact future 252-session target is frozen before
observation. The sole look becomes irrevocably non-reusable on its first accepted
observation and ends spent/unsealed, invalid/uninspected, or underfilled/
uninspected; the latter two close the family without replacement. Efficacy stays
sealed until one atomic final unseal, while monitoring is limited to named
operational/safety metrics. Timely event, corporate-action, security-master,
and fixed-lag holdings facts may only append under a monotone hash-chained frozen
feed/mapping contract; retroactive corrections/backfills/reordering, mapping-
method changes, or any provider/right/schema/ontology/code/configuration/
execution/runtime change invalidates the epoch. A small funded pilot is an
optional later stage only after successful paper confirmation and a separate
exact live-risk decision; paper authority never converts into funded authority.

A future complete V2 executable spec must still be committed and clean, match an entry in
the separate committed review registry, bind its exact independently reviewed
Git blob and review ancestry, and pass semantic validation of every mandatory
cell. Outcome authorization must then reauthenticate that source and obtain an
immutable evaluation receipt for historical screens and, separately, an atomic
spend receipt from an independently pinned cross-machine append-only authority
for the final paper look. No local file or SQLite database can grant or reset
either authority. The reviewed-spec registry and external integrations remain
absent; every authorization attempt refuses before an outcome loader can run.
No credential, provider row, price, return, outcome, QC job, or deployment was
accessed; no look was consumed.

Source precedence is explicit: normative strategy design governs the intended
formula, while observed provider availability/history governs factual data
claims. Neither category is permitted to overwrite the other.

## 4. Exact next step

ARV2-4C is accepted after Claude's independent review in section 16 and Codex
counter-review in section 17. The owner then approved the recommended
ARV2-4D-A policy. Section 18 implements the bounded, outcome-free,
content-addressed candidate: a 10-basis-point arithmetic gross H20 SPY-excess
effect per +1 bullish adjusted-score unit, nominal 80% power at two-sided 5%
size for that one primary coefficient, the first fold's 483-session H20
validation axis for nuisance calibration, exact lag-20 HAC and q05 component
rules, and a fixed 1,388-session capacity decision. It does not claim power for
the net sleeve, paired IC, three-gate family, exact bootstrap, or the lane as a
whole. Claude accepted it in section 19; section 20 accepts Claude's review
after correcting the lane-specific implementation and evidence defects found
in that review commit.

The full input-bearing ARV2-4D-B milestone was not authorized by the
ARV2-4D-A approval and remains unauthorized. It still requires an
independently reviewed production input manifest, exact input identities and
access, processing/storage rights, complete lineage, permitted nuisance-only
computation, a closed numeric receipt, and a separately reviewed successor
binding.

Section 21 implements the owner's separately authorized 2026-08-30
four-family multiplicity amendment as the outcome-free ARV2-3Q-F candidate.
It is an authenticated child overlay of the immutable QC-first plan and an
independent parallel leaf alongside the separately authenticated power
protocol. It preserves accepted bytes, tombstones the unspent `1/60` Analyst
allocation, and makes the effective permanent allocation `1/80` inside the
fixed four-lane `1/20` family. Neither parallel leaf is an ancestor or
descendant of the other. Every future outcome-bearing successor must
authenticate both independently reviewed leaves.

Claude reviewed ARV2-3Q-F in section 22, and section 23 accepts both Claude
commits after correcting their record. Section 23.5 correctly records the
owner-authority stop as it existed then and remains unchanged as historical
evidence. Later owner direction on 2026-09-03 authorized only the bounded,
schema-only ARV2-4D-B1 synthetic-fixture milestone. Section 24 implements that
candidate without editing, re-pinning, or re-parenting ARV2-4D-A, ARV2-3Q-F,
the fold manifest, or any other accepted ancestor.

No credential, Massive/Benzinga key, provider or licensed row, price, return,
outcome, or QC resource was needed or used. Every production-input,
nuisance-computation, numeric-receipt, outcome, QC upload/compile/launch,
paper, funded, deployment, and trading action retains its separate exact
authority gate. ARV2-4 must not run while its receipt, source/rights, review,
run-identity, and one-use authorities are absent.

## 4A. Independent Claude review, corrections, and Codex counter-review, 2026-08-27

**Range reviewed:** `a4f58e6^..5a5c7ab`, 21 commits, every one disposed.
**Claude disposition: accepted after correction.** 0 P0, 0 P1, 3 P2, 6 P3.
**Codex counter-review disposition:** both pushed Claude commits accepted; the
inherited uncommitted correction set was accepted after correction. Codex
found 0 P0, 0 P1, 2 P2, and 1 P3 in that proposed correction set.
**Zero research looks.** No provider, credential, licensed row, broker,
operator-database, QuantConnect or scheduler access occurred.

### 4A.1 Scope change recorded during the review

The owner-specified range ended at `d8d0ad6`. While the review was running the
lane advanced to `5a5c7ab` and this checkout was fast-forwarded by a
`pull --ff-only` (reflog verified; clean fast-forward, no history rewritten).
Per `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` §1 the range was
**extended deliberately rather than allowed to drift**. The extension is safe
to combine with the earlier work because `research/analyst_revisions_v2/`,
`data/exchange_calendar.py`, `assistant/temporal_integrity.py`,
`execution/broker_contract.py` and `assistant/dispatch_fence.py` are
byte-identical between the two commits, so every probe and mutation performed
against `d8d0ad6` still holds at the review head.

### 4A.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `a4f58e6` | Accepted | Counter-review restoration; 61/61 active-document checks, guard mutation-tested. |
| `5d99ae4` | Accepted | Bool-as-number policy weakening closed at the parser boundary. |
| `6b3b734` | Accepted | Cross-process dispatch fence introduced. |
| `4c671d3` | Accepted | Execution authorization bound to broker context. |
| `26b14ff` | Accepted | Park + kill switch + alert made one `BEGIN IMMEDIATE`; halt written even when a terminal transition wins the row. |
| `7a79109` | Accepted | Cancel-all drain fenced. |
| `a7c423b` | Accepted after correction | Fork hardening correct; its regression test could not run on Windows (CLR-007). |
| `6b9ef21` | Accepted | Coherent account-scoped snapshot; execution discards the caller preview and captures its own. |
| `31c7144` | Accepted | Closes the broker open-order indexing race. |
| `00954b2` | Accepted after correction | Large shared hardening commit; source of CLR-002, CLR-004, CLR-005. |
| `49fe8e8` | Accepted after correction | ARV2 fail-closed authority layer; source of CLR-009. |
| `1a6f6cb` | Accepted | Registers the ARV2 research entry point and boundary. |
| `5fb451c` | Accepted (governance verified) | Edits otherwise-frozen coordination files under an explicit bounded owner exception; see §4A.5. |
| `130af4c` | Accepted | Lane-record boundary statement. |
| `7029acb` | Accepted | Corrects candidate status to "assembled but unaccepted". |
| `68ae4b4` | Accepted after correction | Shared regression closure; source of CLR-001. |
| `653a9c0` | Accepted | ARV2 decimal/structural-zero hardening. |
| `d8d0ad6` | Accepted | Lane-record ledger row. |
| `a8f9071` | Accepted | Correct fix: `total_equity` aggregated already-rounded display values while `total_equity_exact` aggregated exact ones, so a multi-position portfolio could drift cents apart and fail its own display/exact integrity contract. Rounds the exact aggregate once. |
| `c167574` | Accepted | Lane-record ledger row. |
| `5a5c7ab` | Accepted | Lane-record ledger row. |

None rejected. No commit was reviewed only as part of a combined diff.

### 4A.3 Material claims reproduced independently

The record's central claim is that the ARV2 layer is fail-closed with zero
looks. It was re-derived with an adversarial probe written outside the
repository, not accepted from the record:

| Probe | Result |
|---|---|
| `require_registered_source_bytes`, all six source kinds | all refuse |
| `run_authorized_outcome_slice` with an instrumented loader | refused; **`outcome_loader` never executed** |
| `authorize_outcome_access` | cannot mint a permit under any input |
| Forged `OutcomeAccessPermit` carrying the real module token | refused |
| Forged, internally self-consistent `VerifiedAnalystPolicy` (valid evidence hash + real token) | refused — out-of-band weakref authority defeats it |
| `load_reviewed_preregistration` on the draft | refused (registry empty) |
| Legacy analyst runner | refused before any network or outcome access |
| Cross-section evidence / `PortfolioRules` | both refuse; no non-empty portfolio constructible |

The four committed authority artifacts were read directly and are genuinely
empty (`entries: []`, `authority_mode: "zero_access"`).

**Blueprint errata verified by golden values.** `N_eff`: zero mass → `0`; a
single `1e-30` contributor → `0` (no epsilon blow-up); one → `1`; four equal →
`4`; `[1000,1,1]` → `1.004002`. Independence: five events from **one** firm →
`1` (raw intensity 5 kept separately); five firms → `5`; fifteen firms on one
catalyst → `1`.

**Timing boundaries verified exhaustively**, including the dangerous direction:
exactly at the 09:30 open → next session; 1 µs before/after → same/next
session; intraday and after-close → next session; Friday/Saturday → Monday;
Jul 3 half day and Dec 24 → Jul 5 and Dec 26; date-only → the **second**
session strictly after; naive, malformed and non-string clocks all refuse;
four-clock monotonicity refuses each inversion. DST handled (13:30Z summer vs
14:30Z winter open).

**Import boundary is transitively enforced.** The package's own closure
validator reaches 21 modules and **zero** rooted in `assistant`, `execution`,
`risk`, `backtest`, `ml`, `signals`, `strategies` or `scripts`.

**Mutation testing.** Five ARV2 safety invariants were reverted one at a time
in a throwaway worktree pinned at `d8d0ad6`; each turned the suite red
(baseline 169 passed): date-only delay 2→1 session (6 failed), accepted-event
zero-access latch removed (16 failed), `N_eff` epsilon reintroduced (1),
independence `min`→`max` (1), next-open `>`→`>=` (1).

### 4A.4 Issue ledger

| ID | Pri | Status | Location | Issue and impact | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|
| CLR-001 | P3 | **Corrected** | `tests/test_ml_evidence_operations.py` | A new test fed `sys.executable` to an installer that refuses Microsoft Store app-execution aliases by contract, so it failed on any machine whose `python` is the Store alias — the default on the owner's host — while passing elsewhere. | CLAUDE.md §10 requires the full suite to pass on the exact final tree; a test whose outcome depends on interpreter provenance makes that gate unreproducible and reports a permanent false failure. | Skips when the interpreter is not a real executable, matching how sibling tests skip off-Windows. | Red under the Store alias before, skipped after, and **still passes under a real interpreter**, so the skip is not vacuous. |
| CLR-002 | P2 | **Corrected after counter-review** | `assistant/portfolio_ledger.py` | SYS-P2-002's exact-decimal chain stopped at `list_fills`: the durable journal re-read the rounded float and ignored `qty_decimal`/`price_decimal`, so a fractional fill was re-rounded before becoming book cost and realized P&L. The first proposed correction also made an exact fill fail on its second identical sync because duplicate validation still rebuilt the header from the float companions. | Money paths must not round-trip through binary float, and an immutable operator journal must remain retry-safe across the upgrade. | `_exact_fill_decimal` prefers provider text. One shared header builder now drives insertion and duplicate validation; retries accept either the current exact header or the immutable legacy float-derived header, while a changed exact companion still conflicts. | Public-boundary tests prove exact sync twice (insert then duplicate), legacy row followed by exact companions, and changed exact digits in the dangerous direction. **Deliberately bounded:** `assistant/tax_lots.py` remains float throughout and requires a separate conversion milestone. `numeric_evidence_status` was not added to immutable metadata because that needs an additive migration. |
| CLR-003 | P2 | **Open - attempted correction rejected by Codex** | `assistant/dispatch_fence.py`, `assistant/order_reconciler.py` | A busy final broker-contact fence can outlast the ordinary timeout, but the proposed 180 s replacement was not a proven upper bound and delayed all best-effort cancellation of already-open orders. | Emergency cancellation must reduce risk promptly without claiming a guessed broker-call bound as a correctness proof. | Reverted the 180 s constant, API threading, and constant-only test. The existing bounded failure remains loud (`book_stable=False` plus a durable critical incomplete-containment incident). A real fix requires independently bounded broker operations and a stop-request/cancellation design that does not synchronously wait several minutes before contacting the broker. | Static call-path reproduction showed waits of roughly 420 s under a stuck holder (180 + 30 + 30 + 180) before the cancellation body. Final preflight can perform repeated account/order/position/asset/quote calls, most through SDK clients without the claimed local 30 s timeout, so `3 × 30 s` was false. Existing fail-loud cancellation tests remain green. |
| CLR-004 | P2 | **Corrected** | `assistant/portfolio_snapshot.py` | The non-strict snapshot builder set `open_orders_available=True` over unvalidated broker rows, so a malformed order was silently skipped by the duplicate and pending-exposure checks while the book appeared complete. | Advisory and preflight surfaces presented an incomplete order book as complete, and operators read preflight as "this would be approved". | A successful call is now treated as transport success only; the book is validated through the same strict contract, and any invalid risk-relevant row makes the evidence unavailable. | Red/green mutation-verified with a positive control proving a healthy book stays available. Execution was never exposed: it does `del caller_preview` and captures its own strict snapshot. |
| CLR-005 | P3 | **Closed — owner decision, no code change** | `risk/execution_gate.py` | The remediation widens what trips the global kill switch, and the kill switch blocks **all** orders including legitimate risk-reducing sells. | CLAUDE.md §5 says a conservative safeguard must not obstruct a risk-reducing sell. | **Owner decision 2026-08-27: leave the kill switch absolute and document the deviation.** It is the master emergency stop, not an ordinary safeguard; admitting orders while it is active is the one direction that can let an order reach the broker during an incident. Risk can still be reduced because emergency cancel-all and `cancel_assistant_order` never consult it. | Recorded as an accepted documented deviation. Any future carve-out must be a separate owner-authorized milestone proving no new exposure can be opened. |
| CLR-006 | P3 | **Corrected** | `ml/earnings_gap.py` | A hardcoded 16:00 ET close survived the shared-calendar consolidation, so on roughly nine early-close sessions a year a 14:30 ET release was classified `intraday` instead of `after_close`, misaligning its event window. Dead `_NYSE`/`mcal` objects made the module look calendar-aware. | Event-time misalignment in a research path, plus a second drifting definition of "market close". | Classification now uses the exchange calendar's real close for the release's own session, with the fixed hour kept only as the fallback for a date that is not a trading session. Dead calendar objects removed. | Red/green mutation-verified. Normal sessions keep the exact 16:00 boundary, so ordinary sessions cannot be silently reclassified. |
| CLR-007 | P3 | **Corrected** | `tests/test_dispatch_fence.py` | The fork-inheritance regression test — the entire point of `a7c423b` — is `skipif(not hasattr(os, "fork"))`, so the hardening never executed on Windows, the owner's only supported platform. | The hardening was unverified on the platform that actually runs it; a regression would be invisible here. | Added a platform-neutral test that calls the fork-child reset directly and proves it discards inherited handles, depth and permits and rebuilds the guards. The POSIX test is retained. | Red/green mutation-verified: neutering the reset fails it. |
| CLR-008 | P3 | **Corrected** | `tests/test_atomic_reconciliation_anomaly.py` | Crash fault injection was simulated with aborting triggers and patched exceptions asserted against the same live store; no process kill and no database reopen, so durability across a real crash rested on SQLite's guarantee alone. | The audit asked for a crash mid-transaction followed by a database reopen; the repo already had a genuine `os._exit` technique that had simply not been applied here. | Added a test that really terminates a child interpreter with `os._exit` between the proposal park and the commit — skipping every `except`/`finally` and the fallback kill-switch write — then reopens the database and asserts there is never a committed anomaly without its halt and alert. | Mutation-verified against the exact pre-remediation failure mode: splitting the transaction so the park commits before the halt makes it fail. |
| CLR-009 | P3 | **Corrected after counter-review test hardening** | `research/analyst_revisions_v2/formulas.py`, `holdings.py`; `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py` | Five out-of-band authority registries, but only three guarded by a lock; `_POLICY_AUTHORITIES` and `_STOCK_SCORE_AUTHORITIES` were bare dicts. The first source test only proved matching lock declarations existed; deleting the actual `with` guard still passed. | The out-of-band registry is the mechanism that defeats forged authority objects, so both production discipline and regression sensitivity must be uniform. | Both registries use `threading.RLock()` and guarded register/get/weakref-forget paths. The AST audit pins all five registries, validates an actual `threading.RLock()` declaration, and requires every non-declaration registry access to have its own lock as a lexical `with` ancestor. | Four synthetic dangerous-direction mutations (unguarded get, set, pop, and wrong lock) are rejected; a matching-lock positive control passes. No exploit was constructed, and the live production code was independently confirmed guarded. |

Resolved and open items are both retained; nothing was deleted after fixing.

### 4A.5 Governance verification

**Frozen-file edits are covered.** `5fb451c` edits the workflow, direction and
review-process documents under an explicit, bounded, self-describing one-time
common-remediation exception that names its scope and expiry and states that
synchronization is not acceptance and grants no credential, provider, outcome,
QC, broker or deployment authority. The same text is present on `main`, merged
by the owner, corroborating that it is owner-directed rather than
self-authorized.

**Cross-lane isolation held.** Verified against the live remotes:
`research/analyst_revisions_v2/` contains **30 files on this lane and 0 on both
`codex/strategy-insider-buying` and `codex/strategy-short-interest`**.

**Synchronized commits are patch-identical to the merged main work.** All
seventeen were compared to their `main`-side sources by stable patch ID and
every pair matches, including `a8f9071` against `1ed0602`
(`cbc98a73962e1592d9242dd31fbbd16278432dd0`). This lane introduced no divergent
variant of a shared safety fix.

**Corrections stayed on this one lane branch.** No side branch was created. The
frozen list is the coordination documents plus `requirements.txt`,
`config.py`, CI/tooling configuration and shared test or classification
manifests; general shared implementation code is not frozen, and this lane
already carries shared execution fixes from the remediation synchronization.

### 4A.6 Remaining gates

Unchanged by this review: owner decisions on the ARV2-0 open cells, a reviewed
spec anchor, governed source admission, and an external cross-machine
append-only permanent-look authority must all close before any production
normalization, price/outcome join, real score, ETF construction, non-empty
portfolio or QuantConnect run. ARV2-4 remains the stock-first stop/go gate
ahead of any ETF topology work. The required Codex counter-review is recorded
below; its accepted-after-correction disposition does not resolve those gates.

### 4A.7 Codex counter-review dispositions and findings

| Reviewed item | Disposition | Independent basis |
|---|---|---|
| `48a8b08` | **Accepted** | The CLR-001 Store-alias skip is restricted to an interpreter the installer refuses by contract; the same test remains executable under the real project interpreter. The review range and 21 commit dispositions were rechecked. |
| `bd3393d` | **Accepted** | It records the completed Claude validation and required same-branch handoff without changing product behavior. Its separate review report was consolidated into this branch-specific record under the owner's documentation instruction; Git history retains the original. |
| Inherited, uncommitted Claude correction set | **Accepted after correction** | CLR-002, CLR-004, CLR-006, CLR-007, CLR-008, and the CLR-009 production locks were accepted. Codex corrected CLR-002 retry compatibility and CLR-009 test sensitivity, and rejected/reverted the unsafe CLR-003 timeout attempt. CLR-005 remains the recorded owner decision with no code change. |

| Counter-review ID | Pri | Status | Finding and disposition |
|---|---|---|---|
| ARV2CR-001 | P2 | **Corrected** | Exact fill insertion used provider digits while duplicate validation used float companions, so the second identical sync raised `LedgerError`; exact-only validation would also strand legacy journals. Centralized the header and accepted exact-current or legacy immutable identity. |
| ARV2CR-002 | P2 | **Correction rejected; CLR-003 remains open** | The proposed 180 s emergency wait was an unsupported bound and could postpone broker cancellation for roughly seven minutes. Reverted it and retained the bounded, loud-incomplete behavior pending a structural owner-authorized safety milestone. |
| ARV2CR-003 | P3 | **Corrected** | The registry test checked only declaration strings and passed after removing real guards. Replaced it with an exact-inventory AST guard audit plus four red-direction mutations and a positive control. |

Focused final-tree validation for every reviewed surface: **334 passed, 1
skipped, 1 known dependency warning in 351.68 s**. The three new exact-fill
and six lock-audit tests also passed alone (**9 passed in 10.65 s**).
Complete fixture-only final-tree validation: **5,448 passed, 2 skipped, 0
failed, 25 known dependency warnings in 10,766.38 s (2h59m26s)**.
Forced `compileall` over application, research, and test modules exited 0;
the post-record active-document gate passed **63 tests**; `git diff --check`
was clean.
No provider, credential, licensed row, outcome, broker, operator database,
QuantConnect, scheduler, or order access occurred; **0 research looks** and no
permanent look identifier was consumed.

The review chain closes as accepted after correction, but the next milestone
is blocked before implementation and before push by the explicit workflow
rule. ARV2-0 still has eight `owner_decision_required` cells:
`shared_holdout`, `contaminated_legacy_periods`, `corporate_action_contract`,
`universe_contract`, `normalization_contract`, `stock_topology`,
`multiplicity_family`, and `lane_validation_period`. The reviewed-spec
registry is empty, and both source and permanent-look authorities remain
`zero_access`. ARV2-1 must not begin.

**Later owner direction, 2026-08-27:** after the local counter-review commit
was reported with the ARV2-0 blocker, the owner explicitly directed Codex to
push it. This authorizes one counter-review-only push despite the normal
combined-push stop rule. It does not resolve any ARV2-0 cell, authorize a next
milestone, open source or outcome authority, consume a look, or permit ARV2-1.

## 4B. ARV2-0 owner-decision freeze candidate, 2026-08-28

The owner authorized implementation of Codex's recommendations wherever a
direct choice had not been supplied, with the objective of balancing profit
potential and risk control. This authorizes the bounded ARV2-0 policy/fixture
milestone and its push on this lane. It does not self-review the candidate,
admit a provider artifact, open an outcome, consume a look, or authorize
ARV2-1.

### 4B.1 Action taken for each formerly open owner decision

| Decision cell | Action taken | Risk/profit rationale |
|---|---|---|
| `shared_holdout` | Freeze the lane cutoff at 2027-08-31 and reserve 2027-09-01 through 2029-08-31 as the shared final holdout, prohibited to this lane. | A two-year untouched common period is long enough to expose regime dependence while preserving earlier history for development. |
| `contaminated_legacy_periods` | Classify the exact legacy analyst outcome-inspection interval 2019-07-16 through 2026-07-23 as `discovery_only`, never untouched confirmation evidence. | Keeps useful engineering knowledge without laundering prior outcome exposure into statistical evidence. V2 remains a separate package and implementation, informed by ACER reviews rather than copied from ACER. |
| `corporate_action_contract` | Require PIT split handling on the effective session, ex-date cash dividends in total return, mandatory terminal delisting return, and named refusal when terminal return is absent. Leave source ID/hash null pending audit. | Prevents survivorship and corporate-action distortions; refusing incomplete terminal outcomes is safer than silently dropping likely difficult names. |
| `universe_contract` | Freeze US-incorporated ordinary common stocks on XASE/XNAS/XNYS, include delisted names, keep share classes separate with a PIT issuer link, prohibit current-ticker joins, and exclude ADRs, BDCs, closed-end funds, ETFs, foreign ordinaries, partnerships, preferreds, REITs, rights, trusts, units, and warrants. Leave security-master ID/hash null pending audit. | Produces a more economically comparable stock universe while retaining failed/delisted securities and refusing ambiguous identity. |
| `normalization_contract` | Freeze PIT eligible cross-sections, sector median/MAD normalization, no market fallback (`sector -> refuse`), at least 20 usable and 5 active names, structural zero only for valid no-event state, clip at the cell's frozen bound, mandatory control residualization, and named refusal for degenerate groups. | Robust normalization preserves signal in ordinary conditions but refuses sparse or structurally incomparable cross-sections instead of inventing confidence. |
| `stock_topology` | Freeze one primary stock cell, `arv2-stock-primary-20d`: rating changes only, upgrades positive/downgrades negative, 20-session half-life, zero threshold, clip 4, mandatory controls. | One economically motivated primary cell maximizes interpretability and avoids post-result parameter shopping; stock evidence must pass before industry/ETF aggregation. |
| `multiplicity_family` | Freeze family `arv2-rating-only-v1`, alpha 0.05, Bonferroni over every registered cell/look, one permanent cell, and one permanent look `arv2-look-stock-primary-001`; a valid null closes the family and the three-lane correction remains 3. | One honest chance limits false discovery while preserving power for the canonical hypothesis. |
| `lane_validation_period` | Freeze one prospective look from 2026-09-01 through 2027-08-31. The look is only `planned_unbound`; dataset/code identities remain null. | A full year samples changing market conditions and starts after the policy freeze, but cannot run until source, code, review, and spend authorities are real. |

The owner's additional period instruction is frozen in a new
`historical_evaluation_contract`: use every eligible audited session from
2013-01-02 through 2026-08-31; separately report objective boom, stress, and
ordinary states using prior-close information; and separately report named
COVID-crash, 2022 rate-shock, and AI-boom episodes. The all-period
walk-forward result is the only formal selection result. Regime results are
descriptive and cannot rescue failure. Pre-2013 history, including 2008, may
be added only after the selected source proves PIT coverage and semantics.

### 4B.2 Data/subscription action list

The owner reports that Massive-Benzinga and QuantConnect credentials and
subscriptions exist on this computer. No credential or account was accessed
in ARV2-0, because possession of a credential does not prove a dataset
entitlement, history, PIT semantics, terminal-return coverage, or processing
rights. Purchase nothing solely from this inventory; first perform the later
owner-authorized read-only, zero-outcome entitlement audit.

1. Treat the existing Massive-Benzinga Analyst Ratings expansion as the
   candidate canonical event source; re-audit its exact entitlement, history,
   corrections/vintages, stable IDs, and purchase-specific right to process an
   allowed raw/normalized/derived representation in QC Cloud.
2. Audit the QC account for US Equities daily history, US Equity Security
   Master, and US Fundamental Data. Together they are candidates for prices,
   splits/dividends/symbol changes, PIT identities, original-reported
   fundamentals, shares, market cap, sector, size, value, momentum,
   volatility, and liquidity. A generic QC subscription or API token is not
   proof of these entitlements or semantics.
3. Confirm whether the Massive account separately includes **Benzinga
   Corporate Guidance** and **Benzinga Earnings**. If not, these are the first
   likely incremental purchases for the mandatory earnings/guidance control;
   buy only after a schema/history/identifier/license audit shows QC
   fundamentals cannot close the same PIT control.
4. Select a genuine terminal-delisting-return source. CRSP `DLRET` remains the
   preferred research-grade candidate. QC's documented delisting event and
   last tradable price do not by themselves prove an after-delisting return;
   an equivalent cheaper source is acceptable only after it proves complete
   coverage and semantics.
5. Defer ETF constituent/holdings entitlement purchases until the stock-first
   gate passes. They are not needed for ARV2-0 through the decisive stock
   validation and should not dilute the current data budget.

### 4B.3 Implementation and validation boundary

The loader now authenticates the candidate's content hash, canonical cell
order, all owner semantics, the cost-cell hash, and the exact planned look.
It exposes zero unresolved owner decisions separately from eight pending
external/review bindings. Unreviewed source or dataset/code bindings refuse;
the existing `reviewed_frozen` loader, Git review registry, and zero-access
permanent-look authority are unchanged. Focused preregistration validation is
recorded in the push row after the final tree is tested. No provider or
outcome access occurred; **0 research looks**.

## 4C. Independent Claude review of the counter-review and ARV2-0 freeze, 2026-08-28

**Range reviewed:** `bd3393d..b912459`, three commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, 0 P2, 2 P3 (both
corrected by this review). **Zero research looks.** No provider, credential,
licensed row, price, return, outcome, broker, operator-database, QuantConnect
or scheduler access occurred.

### 4C.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `7f493d1` | Accepted | Counter-review of the inherited correction set. Verified byte-level that my six corrections entered unmodified (`portfolio_snapshot.py`, `ml/earnings_gap.py`, the CLR-009 locks, and four test modules). Codex's two modifications are genuine improvements: ARV2CR-001 accepts the legacy float-derived journal header alongside the exact header, preventing the `LedgerError`-on-resync my version would have raised against every journal written before exact digits were consumed, without weakening conflict detection; ARV2CR-003 replaces my define-only lock test with an AST audit of every registry access site, pins the five-file inventory, and self-tests the audit both ways. **The rejection of my CLR-003 fix is confirmed correct**: I independently traced the fenced pre-submit body to `TradingClient` SDK calls carrying no local timeout, so my `3 × 30 s` premise was factually wrong, and the 180 s wait would stack to roughly 420 s of pure waiting before any cancellation under a stuck holder — trading prompt risk reduction for an unproven completeness bound. CLR-003 stays open pending a structural design. |
| `c83782d` | Accepted | Documentation-only record of the owner's explicit `push` instruction as a narrow exception to the stop-before-push consequence; scope stated accurately. |
| `b912459` | Accepted after correction | The ARV2-0 owner-decision freeze. Content verified against the loader, not the prose (§4C.2). Correction: two guard-test sensitivity gaps (§4C.3). |

### 4C.2 Independent verification of the freeze

- The candidate loader was executed directly: status
  `owner_decisions_frozen_pending_external_bindings_and_review`, zero
  unresolved owner decisions, exactly the eight declared pending external
  bindings, one `planned_unbound` look; `load_reviewed_preregistration`
  refuses the same artifact.
- **Nine re-hashed weakening attempts all refused on semantic pins**, proving
  the pins hold independently of the content hash: `etf_cap` 0.20→0.50,
  `leverage` true, validation end moved into the shared holdout, embargo
  20→5, alpha 0.05→0.5, a second smuggled stock cell, look state
  `planned_unbound`→`registered_unspent`, status→`reviewed_frozen`, and
  deletion of the contaminated-period inventory.
- The full zero-access probe re-ran unchanged at this head: all six research
  source kinds refuse, the outcome loader never executes, forged permits and
  a self-consistent forged policy are rejected, the legacy runners refuse,
  and no non-empty portfolio is constructible.
- Internal consistency of the frozen dates verified: lane one-shot validation
  2026-09-01→2027-08-31 is **prospective**, ends exactly at the shared cutoff,
  precedes the reserved holdout 2027-09-01→2029-08-31, does not overlap the
  discovery-only contaminated interval 2019-07-16→2026-07-23, and historical
  development (2013-01-02→2026-08-31) ends before prospective validation
  begins. Embargo and bootstrap block both equal the 20-session horizon
  floor.
- No frozen shared file was touched anywhere in the range (verified by name
  against the Action Plan, Session Handoff, coordination documents,
  `requirements.txt`, `config.py`, and `AGENTS.md`).

### 4C.3 Findings

| ID | Pri | Status | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R2-001 | P3 | **Corrected** | `tests/test_analyst_revisions_v2_preregistration.py` | The candidate-binding test bundled a source violation and a look violation in one fixture, so deleting the look `dataset_id`/`code_identity` guard from the loader left the whole suite green — the companion source violation carried the test. Demonstrated by mutation: removing the guard, 35/35 still passed. | Added single-violation parametrized cases: look `dataset_id` alone, look `code_identity` alone, corporate `source_id` alone, universe `security_master_sha256` alone, plus embargo and leverage single-violation cases, each correctly re-hashed so only semantics can refuse. | Re-ran the mutation: 2 cases fail; restored tree green. |
| ARV2R2-002 | P3 | **Corrected** | same file | Nothing covered the `alpha` 0.05 pin: removing it from the loader left the suite green, after which a correctly re-hashed candidate carrying `alpha: "0.5"` loads — a twentyfold multiplicity-budget weakening laundered through a valid hash. | Single-violation case tampering `alpha` to `0.5` with a correct re-hash, expecting the exact refusal. | Re-ran the mutation: the alpha case fails; restored tree green. |

Both are test-sensitivity findings: the production guards themselves were
present and working (my tamper probe refused both weakenings before any test
existed for them).

### 4C.4 Validation

- As-received head `b912459`: full suite **5,453 passed, 3 skipped, 0 failed,
  25 known dependency warnings in 2,174.92 s**, independently reproducing the
  freeze row's exact claim.
- Focused battery over every file the range touched: **469 passed, 1
  skipped**; preregistration file after the new tests: **42 passed**.
- Full suite re-run on the exact final code tree containing the new
  regression tests, with the result recorded in this push's commit message;
  `compileall` over every package exit 0; `git diff --check` clean.

### 4C.5 Next step

Codex counter-reviews this exact pushed head — the two test corrections and
this record — before accepting ARV2-0 or combining that disposition with the
next authorized bounded milestone. The reviewed spec anchor, audited
corporate-action/security-master sources, dataset and code identities,
vendor-to-QC processing rights, and the external append-only permanent-look
authority all remain required before ARV2-1 or any outcome access; CLR-003
remains open in shared execution code.

## 4D. Codex counter-review of Claude's ARV2-0 review, 2026-08-28

**Range counter-reviewed:** `b912459..1507777`, one commit. **Disposition:
ACCEPTED.** No correction was required. 0 new P0, 0 P1, 0 P2, and 0 P3
findings. This closes the ARV2-0 implementation/review/counter-review chain as
accepted after Claude's two test corrections. **Zero research looks.** No
provider, credential, licensed row, price, return, outcome, broker,
operator-database, QuantConnect, scheduler, or order access occurred.

### 4D.1 Commit disposition

| Commit | Disposition | Independent basis |
|---|---|---|
| `1507777` | **Accepted** | The commit changes only the preregistration guard tests and this lane record. Its seven single-violation cases isolate look dataset/code identity, corporate source, universe source, embargo, leverage, and alpha pins without weakening production code. The recorded dispositions for `7f493d1`, `c83782d`, and `b912459` agree with the independently rechecked diffs and the prior counter-review evidence. |

### 4D.2 Reproduction and dangerous-direction checks

- The exact preregistration file passed **42 tests** at `1507777`.
- In a detached throwaway worktree pinned to the reviewed commit, removing
  both look `dataset_id` and `code_identity` semantic guards made exactly the
  two new look cases fail: **2 failed, 5 passed, 35 deselected**.
- After restoring that guard, removing the alpha `0.05` semantic pin made
  exactly the new alpha case fail: **1 failed, 6 passed, 35 deselected**.
- The throwaway worktree was removed after restoration. The reviewed lane
  tree remained unchanged and clean.

The two Claude findings ARV2R2-001 and ARV2R2-002 are therefore accepted as
real test-sensitivity corrections. They are load-bearing in the dangerous
direction and introduce no product behavior. The owner's current instruction
authorizes the next bounded structural milestone on this branch, but does not
open credentials, licensed provider rows, outcomes, QuantConnect jobs, or any
execution surface.

## 4E. ARV2-1 immutable ratings ingest and firm ontology candidate, 2026-08-28

**Disposition:** implementation candidate complete; independent Claude review
and Codex counter-review remain required. The production source and ontology
catalogs remain empty and zero-access. This milestone used the owner blueprint,
the Massive/Benzinga public documentation checked on 2026-08-28, synthetic
fixtures, and an anonymized fixture with the documented response shape. It did
not read the machine-local licensed Snapshot A rows or any credential. **Zero
research looks.**

### 4E.1 Implemented scope

- `research/analyst_revisions_v2/snapshot.py` advances the unpublished V2
  manifest from v1 to v2 and content-binds `captured_at`; complete and
  incomplete artifacts both refuse a capture instant after verification.
  No admitted V2 production artifact exists, so no production artifact was
  migrated or relabeled.
- `research/analyst_revisions_v2/ratings_ingest.py` pins the current public
  Massive/Benzinga endpoint, field inventory, action taxonomy, unsupported
  `assumes` quarantine, target-only rule, conservative clock rule, pre-2013
  quarantine, and correction/deletion semantics into provider-contract SHA-256
  `2e7aa5584765ea5b3cdb40d8895cb852dbb62b43172de42adfb1d58bc0a12dbc`.
  Every authenticated row receives exactly one accepted structural record or
  source-bound named refusal. Duplicate stable IDs refuse every post-2013
  occurrence; raw hashes become immutable version IDs; ordered complete
  snapshots distinguish unchanged, added, corrected, and missing-later rows,
  with the last state explicitly not treated as a withdrawal.
- `research/analyst_revisions_v2/firm_ontology.py` loads only canonical,
  reviewed, nonempty, content-addressed firm maps. Each mapping binds firm ID
  and name, validity interval, exact raw label, ordered rank and scale size,
  relative/absolute scope, mapping quality, reviewer, source evidence, and
  version. Scales require every rank and nonoverlapping firm intervals. The
  blueprint formula is represented as an exact `Fraction`, so three-level
  scores are `-1, 0, 1` and five-level scores are
  `-1, -1/2, 0, 1/2, 1` without float rounding.
- Observed firm/label/date/count inventory is deliberately unordered; it
  cannot promote a generic vocabulary into authority. Exact reviewed spelling
  is required, so `Buy` does not authorize `buy`, and ambiguous labels such as
  `Positive` refuse unless separately reviewed. Upgrades and downgrades must
  agree with the mapped direction. Initiations never receive a fictitious
  neutral prior, while target-only and termination rows stay outside the
  rating-change channel.
- The one-contribution-per-institution/security/trading-day contract consumes
  permanent identities, never tickers. Identical economics collapse to one
  contribution while retaining all linked event IDs; conflicting same-day
  economics return a named refusal. ARV2-2 must authenticate those permanent
  identities before this pure contract can receive production candidates.

### 4E.2 Tests and dangerous-direction evidence

- New provider/ontology/dedupe file plus capture-time and authority-inventory
  guards: **40 passed in 5.75 s** on the final implementation.
- Complete exact working tree: **5,501 passed, 3 skipped, 0 failed, 25 known
  dependency warnings in 2,922.06 s (48m42s)**.
- `compileall` over application, research, scripts, and tests exited 0;
  `git diff --check` is clean. The lane-document gate is rerun after this
  record update and its exact result is recorded in the push row.
- Dangerous-direction mutation: replacing exact ontology-label matching with
  automatic case folding made the dedicated unreviewed-alias test fail
  (**1 failed**); restoring exact matching returned the focused tree to green.
- The existing authority-registry inventory test initially failed when the
  ontology authority was added, proving the inventory detects an undeclared
  registry. Adding `_ONTOLOGY_AUTHORITIES` to the pinned lock audit restored
  the complete Analyst V2 suite.

### 4E.3 Implementation findings and dispositions

| ID | Pri | Status | Finding and disposition |
|---|---|---|---|
| ARV2I-001 | P2 | **Corrected** | The first ontology draft matched labels case-insensitively, which would have admitted an unreviewed alias. Matching is now exact; reviewed aliases must be explicit rows at the same rank. Reverse mutation is red. |
| ARV2I-002 | P2 | **Corrected** | The first single-event normalization entry point accepted a freely constructed `BenzingaRatingRecord`. It now accepts an event ID only through a fully reauthenticated `BenzingaIngestAudit`; forged audit content is refused, and exhaustive ontology results have a public source/ontology revalidator. |
| ARV2I-003 | P3 | **Corrected** | The first structural parser required a current rating for target-only rows, collapsing the blueprint's separate channel. Target-only and coverage-termination records may omit a current rating and cannot produce a rating-change contribution. |
| ARV2I-004 | P3 | **Corrected** | The new ontology authority was absent from the exact lock-registry inventory, and the complete Analyst V2 suite failed. The inventory now pins the sixth registry and verifies every access uses its own `RLock`. |

There are no unresolved P0-P3 findings in this implementation. The public
provider contract is a structural specification, not evidence that the current
account entitlement, purchased terms, history, clocks, corrections, deletion
behavior, or QC-processing rights have been authenticated. No checked-in
production ontology is created: ordering a real firm's labels remains a manual,
versioned review task after exact source access is separately authorized.

### 4E.4 Remaining gate and next step

Claude reviews the counter-review commit and the separate ARV2-1 code/record
commit on this same lane. Codex then counter-reviews every Claude commit. If
accepted, the next bounded engineering milestone is ARV2-2 PIT issuer/security
identity; a current Massive entitlement/licence/snapshot audit remains a
separately authorized zero-outcome source action. The source authority,
reviewed production ontology, canonical rational event publication, outcomes,
permanent-look authority, QuantConnect, and execution all remain closed.

## 4F. Independent Claude review of the ARV2-0 counter-review and ARV2-1 candidate, 2026-08-28

**Range reviewed:** `1507777..6f23244`, two commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, 0 P2, 2 P3 (one
corrected by this review, one open by design with a named closure point).
**Zero research looks.** No provider, credential, licensed row, price, return,
outcome, broker, operator-database, QuantConnect or scheduler access occurred.

### 4F.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `31c313e` | Accepted | Codex counter-review of my ARV2-0 corrections; record-only. Its reproduction evidence (42 tests at `1507777`; the two mutations isolated to exactly the new cases) matches what I observed when writing those tests. This closes the ARV2-0 chain as accepted. |
| `6f23244` | Accepted after correction | The ARV2-1 ratings-ingest and firm-ontology candidate. Both modules read in full and verified independently (§4F.2); correction: one untested guard branch (§4F.3). |

### 4F.2 Independent verification of ARV2-1

- **No network or credential surface exists.** Both new modules import only
  the canonical/evidence/ontology/snapshot layers; the transitive import
  firewall was executed directly and reaches 23 modules with zero
  execution-capable or network roots, now including `ratings_ingest` and
  `firm_ontology`. The ingest consumes only an already-verified local V2
  snapshot; no code in the package can perform a capture.
- **The provider contract hash was recomputed independently** and matches
  both the module constant and the §4E claim
  (`2e7aa558…a12dbc`). A snapshot must carry this exact contract ID and hash
  or the audit refuses.
- **Blueprint scale goldens reproduced by hand:** three-level scales map to
  exactly −1, 0, 1 and the five-level formula is the exact `Fraction`
  blueprint equation; lowercase `buy` refuses as `unreviewed_rating_label`;
  a date before the firm's scale refuses as `no_active_firm_scale`; a rank
  gap, overlapping validity intervals, and `status: draft` all refuse at
  load.
- **Exactly-once discipline holds:** the audit enforces one terminal
  disposition per source row with canonical sorting; every occurrence of a
  duplicate provider ID is refused (`DUPLICATE_PROVIDER_EVENT_ID` vs
  `CONFLICTING_PROVIDER_EVENT_VERSION` by raw-hash), with the pre-2013
  quarantine kept dominant.
- **Dedupe goldens reproduced:** identical same-day economics collapse to one
  contribution retaining both linked event IDs; conflicting economics return
  the named refusal; duplicate canonical IDs and zero-change candidates
  refuse; the contract takes permanent identities only — no ticker path
  exists.
- **Chronology semantics verified:** snapshot manifest v2 content-binds
  `captured_at` (never later than `verified_at`); lineage comparison requires
  strictly increasing capture instants and identical year bounds; a row
  missing from a later snapshot is typed
  `missing_from_later_snapshot_not_withdrawal`.
- **Mutation matrix (detached scratch worktree pinned at `6f23244`, so the
  concurrently running full suite could not be contaminated):** exact-label
  matching → casefold: red; dedupe conflict → silent first-wins: red;
  lineage chronology removed: red; duplicate provider IDs accepted: red;
  upgrade-side direction gate removed: **survived** → ARV2R3-001 below.

### 4F.3 Findings

| ID | Pri | Status | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R3-001 | P3 | **Corrected** | `tests/analyst_revisions_v2/test_ratings_ingest_and_ontology.py` | Only the downgrade branch of the action-direction gate was tested; deleting the upgrade branch (`upgrades` whose reviewed mapping is non-positive) left all 38 tests green. Same single-violation-per-guard class as ARV2R2-001. | Added a regression with one case per gap: an `upgrades` action whose reviewed order moves the score down, and an `upgrades` between two reviewed aliases at the same rank — a zero change only the reviewed order can expose, since the raw labels differ and structural ingest accepts the row. | Mutation re-run in the scratch worktree: the upgrade-branch deletion now fails the new test; restored tree green (39 passed). |
| ARV2R3-002 | P3 | **Open by design — closure point named** | `research/analyst_revisions_v2/firm_ontology.py` | Authority asymmetry: every other evidence category is anchored by a committed zero-access registry, but a firm ontology becomes loader-authenticated authority from any local file whose content says `status: "reviewed"`. | None applied — deliberately. The structural milestone needs positive ontology loading for synthetic fixtures, and no production path is reachable: accepted canonical events remain latched off, all six research source kinds refuse, and the canonical event contract will bind `rating_ontology_evidence_sha256` through the reviewed-spec chain. Hard-gating now would be a speculative framework change. | To close when the production ontology catalog milestone lands: a committed ontology registry analogous to `reviewed_spec_registry.json`, consulted before an ontology can bind production events. Recorded so the asymmetry cannot silently persist into ARV2-2+. |

### 4F.4 Validation

- Focused ARV2 battery at the review head: **229 passed** (368 s); the
  ingest/ontology file after the new regression: **39 passed**.
- Full suite on the exact final tree recorded in this push's commit message;
  `compileall` exit 0; `git diff --check` clean; no frozen shared file
  touched anywhere in the range.

### 4F.5 Next step

Codex counter-reviews this exact pushed head before accepting ARV2-1 or
combining that disposition with the next authorized bounded milestone
(ARV2-2, the PIT issuer/security master). The ontology-registry closure point
in ARV2R3-002 belongs to that later production-catalog work. All external
bindings, the reviewed spec anchor, and the permanent-look authority remain
zero-access.

## 4G. Codex counter-review of Claude ARV2-1 review, 2026-08-29

**Exact commit reviewed:** `31a2b64125f2dde7809d565ab31651b5b5d95094`
against parent `6f23244ccbbab410e62373cf0373225cdcf70056`.
**Disposition: ACCEPTED.** 0 P0, 0 P1, 0 P2, 0 new P3. **Zero research
looks.** No provider, credential, licensed row, price, return, outcome, broker,
operator-database, QuantConnect, scheduler, or order access occurred.

### 4G.1 Commit disposition and independent evidence

| Commit | Disposition | Basis |
|---|---|---|
| `31a2b64` | Accepted | The exact one-commit remote range is clean and changes only the ARV2-1 guard test and this lane record. The new regression isolates both unsafe upgrade cases: a reviewed downward move labeled `upgrades` and two distinct reviewed aliases whose mapped change is zero. Removing the upgrade-side guard makes the new test fail; weakening `<= 0` to `< 0` also makes it fail. The restored focused file is green. |

- Independently re-read the production branch and confirmed that the guard
  rejects `upgrades` whenever the exact ontology-derived change is nonpositive;
  Claude did not weaken production behavior.
- Independently re-ran the complete ingest/ontology file: **39 passed**. A
  separate zero-access/import battery was **14 passed**; the static transitive
  closure reached 23 modules with no forbidden root, and the provider-contract
  hash recomputed exactly as
  `2e7aa5584765ea5b3cdb40d8895cb852dbb62b43172de42adfb1d58bc0a12dbc`.
- `ARV2R3-001` is therefore accepted as corrected and mutation-sensitive.
  `ARV2R3-002` is accepted as a real, safely deferred P3: arbitrary structural
  ontology fixtures still cannot reach production publication, and ARV2-2 is
  the named closure point for an empty committed production registry.
- `git diff --check` is clean and the exact branch head matched the fetched
  remote before ARV2-2 work began.

### 4G.2 Next step

Proceed in this same round and worktree with the bounded ARV2-2 structural
candidate: permanent issuer/security/share-class identity, point-in-time
historical ticker resolution, exhaustive mapping/refusal coverage, and
delisting/merger terminal-outcome prerequisites. Production identity and
ontology catalogs remain empty; outcomes, permanent looks, QC, and execution
remain prohibited.

## 4H. ARV2-2 PIT issuer/security identity candidate, 2026-08-29

**Disposition: CANDIDATE COMPLETE, NOT ACCEPTED.** Independent Claude review
of the exact pushed snapshot and Codex counter-review of Claude's exact review
commit remain mandatory. No provider, credential, licensed row, price, return,
outcome, broker, operator-database, QuantConnect, scheduler, or order access
occurred. **Zero research looks and no permanent look consumed.**

### 4H.1 Implemented scope

- Added immutable, content-addressed issuer, security, share-class, standard
  and vendor identifier, listing-interval, and lineage records. Base facts and
  interval closures carry separate availability instants; future closures are
  redacted rather than leaked through resolved records or evidence identity.
- Added historical-ticker resolution by event date and knowledge cutoff. It
  preserves ticker reuse, multiple share classes, symbol and listing changes,
  mergers, and delistings; never rewrites an event to a current ticker or
  successor; and refuses ambiguous, late, ineligible, or terminated mappings.
- Added exhaustive Benzinga-event identity auditing with exact integer
  coverage, one permanent mapping or named refusal per accepted source event,
  exact-rational firm/identity joins, and public-result revalidation. The audit
  indexes one authenticated master rather than reparsing and rescanning it for
  every event.
- Added a fail-closed inventory of merger/delisting terminal-return
  requirements. An in-range terminal event that is unavailable at the
  knowledge cutoff is a named refusal, never a silently omitted requirement;
  no price or outcome is loaded.
- Added fixed, Git-anchored production registries for firm ontologies and
  security masters. Both committed registries are empty. Structural fixture
  loaders remain usable, but production entry points require an exact reviewed
  commit, registered path and hash, clean tracked file, matching reviewed Git
  blob, non-symlink path, and retained-payload recheck. This closes historical
  finding `ARV2R3-002` without admitting any production artifact.

### 4H.2 Review findings corrected before handoff

| Finding | Priority | Final disposition |
|---|---:|---|
| `ARV2I2-001` | P2 | Corrected: future interval endpoints were initially visible before their closure evidence was available. All interval closures now have explicit availability and are redacted until known. |
| `ARV2I2-002` | P2 | Corrected: delayed symbol/terminal evidence and ticker reuse could expose or bypass a predecessor closure. Resolution and lineage reasoning now fail closed at the exact knowledge cutoff. |
| `ARV2I2-003` | P2 | Corrected: an unavailable in-range terminal event could be omitted from the requirement inventory. The builder now emits a named refusal. |
| `ARV2I2-004` | P2 | Corrected: the first audit path reparsed and linearly scanned the complete master per event. The final path authenticates once and uses indexed candidates. |
| `ARV2I2-005` | P2 | Corrected: a same-ticker exchange/MIC transfer lacked an explicit lineage type. `listing_change` now represents it without pretending it is a symbol change. |
| `ARV2I2-006` | P3 | Corrected: production registry checks needed pre-resolution symlink refusal, retained-byte TOCTOU checks, and a positive reviewed-Git path. All three are regression-tested. |
| `ARV2I2-007` | P3 | Corrected: permanent identifier reuse, listing-country filtering, and related guard sensitivity were tightened and mutation-tested. |

Three independent audits accepted the corrected candidate with **0 unresolved
P0-P3 findings**. The contract audit found no remaining P0-P2 mismatch with
the PDF or ARV2-2 exit gate. The code audit independently ran **114 passed, 1
host-capability symlink skip, 0 failed in 42.11 s**. The mutation audit killed
**13/13** targeted weakenings covering ambiguity, current-ticker/date loss,
component and terminal availability, post-delisting mapping, successor rewrite,
share-class collapse, future closure visibility, ticker reuse, resolver source
reauthentication, production-gate bypass, registry symlinks, and reviewed-blob
substitution.

### 4H.3 Validation and remaining gates

- Final focused security-master/import-authority battery: **40 passed, 1
  host-capability symlink skip, 0 failed in 2.19 s**.
- Complete Analyst Revisions V2 battery: **268 passed, 1 host-capability
  symlink skip, 0 failed in 69.63 s**.
- Complete repository: **5,541 passed, 3 skipped, 0 failed, 26 known
  dependency warnings in 1,140.84 s (19m00s)**.
- Independent compileall completed successfully; **63/63 active-document
  assertions passed** in the final direct module runner. Final diff/status
  gates are run immediately before commit and push.

The production master, ontology, source-rights evidence, vintage/correction
builder, split/dividend source, and terminal-return source remain absent. No
real mapping or outcome may run. After Claude reviews this exact candidate and
Codex counter-reviews that review, the next bounded milestone is ARV2-3, the
canonical stock score and strictly separate diagnostic channels; it does not
start in this push.

## 4I. Independent Claude review of the ARV2-1 counter-review and ARV2-2 candidate, 2026-08-29

**Range reviewed:** `31a2b64..56d6fe0`, two commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, **1 P2**, 3 P3 — all
corrected — plus one documented, deliberately unfixed observation.
**Zero research looks.** No provider, credential, licensed row, price, return,
outcome, broker, operator-database, QuantConnect, scheduler or order access
occurred.

**Owner instruction applied (2026-08-29):** this lane exists solely for Analyst
Revisions strategy development, its QuantConnect test path, and eventual live
trading through QuantConnect only after every prior research, review,
validation, and deployment gate is complete. Trading App and Streamlit UI are
outside this lane. Issues outside that purpose are documented, not fixed. Every
correction below is inside `research/analyst_revisions_v2/`, its committed
artifacts, or its tests, and each unblocks a gate this lane depends on.

### 4I.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `0fb7998` | Accepted | Codex counter-review of my ARV2-1 review; record-only, 0 findings. Its independent evidence (39 ingest/ontology tests, 23-module closure, recomputed provider-contract hash) matches what I observed writing those tests, and it correctly carried `ARV2R3-002`'s closure into ARV2-2 as the named next step. |
| `56d6fe0` | Accepted after correction | The ARV2-2 PIT identity candidate. Both new modules and the 2,143-line security master read in full; strong design, one platform-breaking defect and three unpinned guards (section 4I.3). |

### 4I.2 Independent verification of ARV2-2

- **`ARV2R3-002` is genuinely closed.** `production_registry.py` is a shared,
  Git-anchored gate reusing the reviewed-blob pattern from the preregistration
  anchor. Both new registries are committed **empty**, so structural fixtures
  still load while nothing can bind production. The positive path is **not
  vacuous**: its test builds a real Git repository, registers an artifact,
  proves the gate accepts it, then substitutes the artifact with a matching
  re-hashed entry and proves rejection against the reviewed blob.
- **Point-in-time discipline holds in the dangerous direction.** Interval
  closures carry their own availability instant, so a delisting or symbol
  change stays invisible until its evidence was publishable; ticker reuse
  yields `AMBIGUOUS_ACTIVE_TICKER_MAPPING` rather than first-wins; resolution
  never consults a successor or a current ticker.
- **Load-time validation is exhaustive**: permanent-ID uniqueness (CIK, vendor
  IDs, share class), nested validity containment, non-overlapping listings and
  ticker/exchange pairs, lineage availability ordering, terminal-event
  consistency, and listing-transition abutment.
- **Refusals are counted, never dropped**: coverage arithmetic requires
  `mapped + refused == total` with per-reason counts that sum and sort
  canonically.
- **Mutation matrix (detached scratch worktree at `56d6fe0`)**, deliberately
  aimed at guards the implementation's 13/13 list did not name:
  issuer-country, listing-exchange and security-type eligibility all **bit**;
  combined-join identity-refusal precedence **bit**;
  listing-closure-needs-lineage, coverage arithmetic and coverage refusal-sum
  **survived** (see 4I.3).

### 4I.3 Findings

| ID | Pri | Status | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R4-001 | **P2** | **Corrected** | `research/analyst_revisions_v2/specs/` | The committed zero-access artifacts are content-addressed and their loaders demand canonical JSON with exactly one LF, but the repository has **no `.gitattributes`** and this host has `core.autocrlf=true`. Every artifact therefore checked out as CRLF and `require_canonical_json_bytes` rejected them. Consequences: the production-gate test **failed on the owner's own platform** while the other machine did not reproduce it; `_require_zero_access_source_authority` died at parse instead of verifying the declaration it exists to prove, so that safety property was silently unverified here; and a legitimately registered artifact could **never** be accepted on Windows, which would have blocked the first real ontology or security-master registration. Fail-closed throughout, hence P2 rather than P1. | Added a lane-scoped `research/analyst_revisions_v2/specs/.gitattributes` marking `*.json` as `-text` so these bytes are never translated in either direction, and renormalized the working tree. Lane-owned; no shared or frozen file touched. | The Git blobs were already canonical LF, proving the defect is checkout-only. After the fix the failing test passes and the source authority resolves to its exact `zero_access` ID. Two new regressions pin the property rather than the mechanism: every committed artifact is CRLF-free, the five canonical-required artifacts parse, and both zero-access declarations return their exact IDs — a refusal alone cannot distinguish a real declaration from an unreadable file. Mutation: re-CRLF-ing the artifacts turns all three tests red; restoring turns them green. Reproduced independently in a fresh detached worktree, so it is not an artifact of this working copy. |
| ARV2R4-002 | P3 | **Corrected** | `security_master.py` load validation | The guard requiring every listing closure to be explained by transition or terminal lineage had no regression: disabling it left the entire file green. An unexplained closure is precisely how a delisting hides as a quiet gap and drops the hardest names from the identity layer. | Added a load-time regression asserting the named refusal. | Mutation red/green verified. |
| ARV2R4-003 | P3 | **Corrected** | `SecurityIdentityCoverage` | Neither coverage invariant was pinned: removing the `mapped + refused == total` check or the refusal-sum check left the file green, although the dataclass is public. | Added a regression covering both invariants directly. | Both mutations red/green verified. |
| ARV2R4-004 | P3 | **Corrected** | `security_master.py` eligibility constants | `ELIGIBLE_LISTING_EXCHANGES`, `ELIGIBLE_ISSUER_COUNTRY` and the `SecurityType` vocabulary restate the ARV2-0 frozen `universe_contract`, and the existing test hardcoded the vocabulary instead of deriving it. They agree today, but nothing bound them, so amending the frozen owner decision would silently leave the identity gate enforcing the old universe — and that gate decides which securities can ever reach the QC test. | Added a test deriving venues, incorporation and the full instrument vocabulary from the committed frozen spec and asserting the code constants match, including an explicit `united_states` to `US` representation pin. | Mutation: dropping `XASE` from the code constant while the spec is unchanged turns it red; restoring turns it green. |
| ARV2R4-005 | P3 | **Documented, deliberately not fixed** | `security_master.py` successor-cycle detector | The cycle detector survived mutation, but it is **unreachable**, not merely untested. The successor-activity guard requires each successor to be active on its predecessor's terminal date: for A to B at d1 and B to A at d2 the constraints force `d1 < d2` and `d2 < d1` simultaneously, and the same telescoping precludes longer cycles. | None. A test would have to construct an input the earlier guards already reject, and deleting the detector would remove harmless defense-in-depth. | Recorded so a future refactor that relaxes the activity guard knows this detector is the remaining backstop. |

### 4I.4 Validation

- As-received `56d6fe0` on this Windows host: **5,539 passed, 1 failed, 4
  skipped, 25 warnings in 1,782.71 s**. The single failure is ARV2R4-001. The
  skip count reconciles: the other machine reports 3 because its interpreter
  is real, while this host adds the `CLR-001` interpreter skip introduced in
  an earlier round precisely so a Store-alias interpreter degrades to a skip
  rather than a failure.
- Focused ARV2 batteries after the corrections: security master **41 passed,
  1 host-capability symlink skip**; dataset/import firewall **39 passed**.
- Full suite on the exact final tree recorded in this push's commit message;
  `compileall` exit 0; `git diff --check` clean; no frozen shared file
  touched.

### 4I.5 Cross-lane note (not acted on)

The missing `.gitattributes` is a repository-wide condition. This review fixed
it only inside this lane's own `specs/` directory, because a root-level
`.gitattributes` is shared tooling configuration that would bind the Insider
Buying and Short Interest lanes at merge time. Those lanes may hold the same
latent defect wherever they add content-addressed artifacts read as canonical
bytes. That is an owner-coordinated common-baseline decision, not a lane
change, and is recorded here rather than acted on.

### 4I.6 Next step

Codex counter-reviews this exact pushed head before accepting ARV2-2 or
starting the next bounded milestone. The production master, ontology,
source-rights evidence, vintage/correction builder, split/dividend source and
terminal-return source all remain absent, and every production authority
remains zero-access.

## 4J. Codex counter-review of Claude commit `f592334`, 2026-08-29

**Commit reviewed:** `f5923345b572fb5844277cc5426c047610ad1fbe`
against parent `56d6fe0eff32d00b1692b3b17a3838649eeba56b`.
**Disposition: ACCEPTED AFTER CORRECTION.** Quality 7/10. 0 P0, 0 P1,
**1 P2 and 1 P3, both corrected.** Zero research looks. No provider,
credential, licensed row, price, return, outcome, broker, operator database,
QuantConnect job, scheduler, order, Trading App, or Streamlit access occurred.

Claude's three new security-master guard regressions are sound. The listing
closure, coverage arithmetic/refusal totals, and frozen-universe bindings were
independently reproduced. `ARV2R4-005` is also correct: the successor-cycle
detector is unreachable under the stronger predecessor/successor activity
constraints and remains harmless defense in depth.

| ID | Pri | Status | Location | Counter-review finding and correction |
|---|---|---|---|---|
| ARV2CR5-001 | **P2** | **Corrected** | `research/analyst_revisions_v2/specs/`, registry schemas/loaders | Claude added the correct `-text` rule, but an ordinary fast-forward of this pre-existing Windows worktree did not rewrite unchanged JSON blobs. The new canonical-byte test and the positive source-authority test therefore both failed, and `_require_zero_access_source_authority()` still stopped at a CRLF parse error rather than verifying the zero-access declaration. Bumped exactly the three artifacts consumed through `require_canonical_json_bytes` — firm-ontology registry, research-source authority, and security-master registry — plus their loader constants to schema v2. Those real blob changes force existing worktrees to refresh the files under `-text`; all three now contain zero CRLF bytes and validate canonically. No authority entry was added and production access remains zero. |
| ARV2CR5-002 | P3 | **Corrected** | `test_dataset_and_import_firewall.py`, `.gitattributes` comments | Claude's test called every JSON artifact content-addressed and listed five as byte-canonical. Only the three registries above use the exact-byte loader; permanent-look and reviewed-spec registries parse tolerantly/compare canonicalized semantics. Narrowed the assertion and comments to the real contract while retaining both positive zero-access checks. |

The owner clarified during this counter-review that eventual live trading
through QuantConnect is a correct long-term destination after all prior work is
complete. It is therefore not a review finding. The clarification changes no
current authority: this round performs neither a QC job nor any live action.

An ordinary fast-forward at `f592334` reproduced **78 passed, 2 failed, 1
skipped** in Claude's focused firewall/security selection; both failures were
the incomplete EOL migration above. After correction, the exact two failed
guards pass directly, all three byte-canonical registries are LF-only, and the
broader 87-node focused selection reaches 100% with the one host-capability
symlink skip. On this Windows host the pytest process can linger after node
completion, so the exact final-tree counts are deferred to the combined
ARV2-3 validation before the one push. `git diff --check` is clean.

The next bounded milestone is ARV2-3: an outcome-free, structurally testable
canonical stock-score candidate and strictly separate diagnostics. Production
source, ontology, security, sector, common-event, quality, score, outcome, and
QC authorities remain empty or absent. No provider credentials are needed or
authorized for that structural implementation.

## 4K. ARV2-3 structural stock-score candidate, 2026-08-29

**Implementation disposition: COMPLETE AS AN UNREVIEWED, STRUCTURAL-ONLY
CANDIDATE.** It is not a production score, executable strategy, outcome test,
QC result, deployment artifact, or trading authorization. Claude must review
the exact pushed snapshot and Codex must counter-review every resulting Claude
commit before ARV2-3 can be accepted. Zero research looks were used.

### 4K.1 Implemented scope

- Added the stock-specific formula primitives from the PDF: exact exponential
  decay with the frozen 20-NYSE-session half-life and no hard lookback cutoff;
  `N_eff / (N_eff + 3) * q_data`; and activity-aware robust normalization that
  distinguishes a valid no-event zero from an event-active exact cancellation.
- Added a content-addressed structural stock-score evidence bundle and
  pre-control candidate. The builder revalidates the original verified
  snapshot, ingest audit, reviewed firm ontology, permanent security identity
  audit, combined ARV2-2 result, policy, and master rather than trusting a
  caller-assembled shell.
- Derives the decision open and every event age internally from the NYSE
  calendar; exact-open source updates follow the existing conservative
  date-only delay, while rows updated after snapshot capture refuse globally.
  One shared session index and decay-by-age cache preserve exact arithmetic
  without rebuilding a multi-year exchange schedule for every event.
- Derives the complete eligible common-stock universe from the authenticated
  ARV2-2 master. The master intentionally retains its reviewed inclusive PIT
  cutoff, while new ARV2-3 institution/classification/common-event/quality
  evidence must be known strictly before the decision open. Tests pin both
  sides of that deliberate boundary.
- Excludes only the four identity refusals that prove a row is outside the
  frozen universe (issuer country, listing country, exchange, security type).
  Ambiguous/late identity and ontology failures still block the cross-section;
  accepted historical events outside the decision universe are sliced before
  structural evidence lookup.
- Deduplicates institution-security-eligible-session observations, computes
  exact rational rating change times decay, sums deterministically, derives
  institution and common-catalyst effective breadth from absolute contribution
  mass, then takes the conservative minimum.
- Normalizes the complete sector cross-section with median and
  `1.4826 * MAD`, requires at least 20 total and five event-active names,
  refuses zero MAD without epsilon or market fallback, clips symmetrically at
  ±4, and applies measured stock reliability only after normalization.
- Converts missing, late, conflicting, or as-known ambiguous structural
  evidence into canonical named refusals. Any refusal clears every score and
  sector-normalization record, so no partial artifact can escape.
- Keeps diagnostics separate from the canonical candidate. Diagnostics first
  rebuild/revalidate the candidate; refusing candidates cannot emit apparently
  available rows. Upgrade/downgrade counts, directional breadth, institutions,
  and distinct common events are structural diagnostics. Unique permanent
  analysts, consensus novelty, target revisions, EPS revisions, and analyst
  quality remain explicitly unavailable rather than inferred.
- Leaves the PDF's mandatory cross-sectional control residualization in the
  named state
  `blocked_unspecified_mandatory_controls_cross_sectional`. The frozen sources
  do not specify estimator, intercept, scaling, collinearity, or operation
  order, so this milestone does not invent an executable final score.

### 4K.2 Pre-commit review findings and dispositions

Three independent read-only audits covered code/trust boundaries, numerical
equivalence to the PDF, and dangerous-direction test sensitivity. Their final
stable-tree dispositions are clean: **0 unresolved P0-P3**.

| ID | Pri | Status | Finding and correction |
|---|---|---|---|
| ARV2I3-001 | P2 | **Corrected** | Initial institution/classification interval use did not bind closure availability, so a future-known endpoint could leak into the decision slice. Added paired base/closure availability, strict new-evidence visibility, reviewed-master cutoff parity, and future/known closure regressions. |
| ARV2I3-002 | P2 | **Corrected** | A proven ADR/REIT/country/exchange exclusion in the exhaustive ARV2-2 identity result could poison the entire valid universe, while an accepted event outside the current universe could enter contributions or trigger missing-evidence refusals. Exempted exactly the four proven universe exclusions and sliced all non-universe events before feature construction; ambiguity and ontology failures remain blocking. |
| ARV2I3-003 | P2 | **Corrected** | Diagnostics initially trusted a frozen candidate shell, could label partial/refusing evidence available, depended on ambient Decimal precision, and represented PDF event diversity as a ratio. Diagnostics now require full source revalidation, reject refusing candidates, use the fixed Decimal context, count distinct common events, mark unauthenticated permanent-analyst breadth unavailable, and enforce unique rows/exact deferred channels. |
| ARV2I3-004 | P2 | **Corrected** | Legitimate nonoverlapping final intervals can overlap as known when a predecessor closure arrives late. Sector/institution multiplicity raised an unstructured exception rather than producing a durable candidate. Added named, hashed ambiguity refusals and bitemporal regressions; refusing sectors still emit no partial scores. |
| ARV2I3-005 | P3 | **Corrected** | Golden/mutation sensitivity did not initially pin mixed rating magnitudes, NYSE versus calendar age, no hard cutoff, absolute-mass breadth under cancellation, the 1.4826 MAD scale, both clip tails, multi-sector no-fallback behavior, positive dedupe, zero-evidence reliability, evidence binding, strict timing boundaries, or empty/global-refusal calendar short circuits. The final 55-node focused file pins each dangerous direction. |
| ARV2I3-006 | P3 | **Corrected** | Per-event session aging rebuilt the NYSE schedule across the history span. Replaced it with one verified session-index map per build and an exact decay-by-age cache; independent comparison matched 2,173 session ages including age zero. |

No unrelated Trading App/Streamlit issue was changed. One unrelated
host/tooling observation, **ARV2ENV-001**, remains document-only: under this
sandbox the pytest 9.1.1 cache provider stalled in `tempfile.mkdtemp` while
trying to create its repository cache after otherwise-green assertions.
Disabling only that non-semantic cache plugin produced the clean final exit;
no repository source or pytest configuration was changed. The earlier
cross-lane `.gitattributes` coordination note also remains document-only as
recorded in 4I.5.

### 4K.3 Validation, authority boundary, and next gate

- Stable focused stock-score file: **55 passed in 44.35 s**. Independent final
  code review reached the preceding 53-node tree with no failure, then the
  test audit directly verified both empty paths before their regressions were
  added; the numerical delta audit passed 9 selected tests and matched 2,173
  session ages exactly.
- Complete Analyst Revisions V2 battery: **328 passed, 1 host-capability
  symlink skip in 106.54 s (1m46s)** on the final code tree.
- Transitive import closure reaches 26 local modules, includes
  `research.analyst_revisions_v2.stock_signal`, and reaches neither
  `execution` nor `research.acer`.
- Exact repository code tree: **5,601 passed, 3 skipped, 0 failed, 26 known
  warnings in 1,307.06 s (21m47s)**. Changed-file `py_compile` passes under the
  alternate repository-owned cache; `git diff --check` is clean. The final
  record-only active-document rerun, with only the unrelated cache provider
  disabled after ARV2ENV-001, exited cleanly: **63 passed in 1.17 s**.

Only synthetic/anonymized documented-shape fixtures were used. No provider or
QC credential, licensed row, price, return, outcome, broker, operator database,
QuantConnect job, scheduler, order, Trading App, or Streamlit access occurred;
**0 research looks and no permanent look identifier consumed.** Eventual live
trading through QuantConnect remains the valid post-gate destination stated by
the owner, but this candidate grants no present QC, deployment, or trading
authority.

The next action is the one combined push followed by Claude's independent
review. ARV2-4 must not start merely because ARV2-3 code exists: it still needs
accepted production evidence bindings, exact vendor-to-QC processing rights,
the external append-only permanent-look authority, and explicit authorization
for the one-shot outcome use.

## 4L. Independent Claude review of the ARV2-2 counter-review and the ARV2-3 candidate, 2026-08-29

**Range reviewed:** `f592334..8701880`, two commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, **1 P2**, 3 P3 - all
corrected - plus one documented, deliberately unfixed observation.
**Zero research looks.** No provider, credential, licensed row, price, return,
outcome, broker, operator-database, QuantConnect, scheduler or order access
occurred.

Owner scope instruction applied: this lane is for Analyst Revisions V2 strategy
work only. Every correction below is a test inside `tests/analyst_revisions_v2/`;
**no production module was modified**, and no Trading App, Streamlit, or shared
execution file was touched.

### 4L.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `a597ac3` | Accepted after correction | Codex's ARV2-2 counter-review. Its narrowing of the byte-canonical set to three artifacts is **correct** - I traced every `require_canonical_json_bytes` call site and confirmed `permanent_look_authority.json` and `reviewed_spec_registry.json` are parsed tolerantly through `_json_object` and compared after semantic canonicalization, and that `spec_hash` is taken over `_canonical_payload(raw)` rather than over file bytes. The schema-v2 blob bump is a sound migration device. The defect is that it was applied to three of the seven artifacts the `-text` rule governs (ARV2R5-001). |
| `8701880` | Accepted after correction | The ARV2-3 structural stock-score candidate. `stock_signal.py` (1,779 lines) read in full, plus the `formulas.py` diff. Strong and genuinely conservative work; five tested properties survived reverse mutation and are now pinned under ARV2R5-002/003/004. |

### 4L.2 Independent verification of ARV2-3

- **Golden equations reproduced by a different formulation.** I recomputed the
  decay as `context.power(Decimal("0.5"), age/20)` at 60 digits rather than the
  implementation's `divmod` plus `exp(-r/H * ln 2)`. The two agree to better
  than 1e-40 across ages 0, 1, 7, 10, 19, 20, 21, 40, 63, 100, 251, 1000 and
  3400; are exactly 1, 0.5 and 0.25 at ages 0, 20 and 40; and are strictly
  decreasing throughout. `N_eff/(N_eff+3) * q_data` matches six hand cases
  exactly. Sector median, MAD, the 1.4826 scale and the symmetric clip match an
  exact-`Fraction` hand computation to better than 1e-45.
- **The import boundary holds and was not widened.** The transitive closure is
  26 modules, contains `research.analyst_revisions_v2.stock_signal`, and
  reaches no `execution`, `ml`, `risk`, `assistant`, network, or
  `research.acer` module. The only allowed exception remains the pre-existing
  `dataset -> subprocess`.
- **No partial artifact can escape, twice over.** `_candidate` clears scores and
  sector normalizations whenever any refusal exists, and the frozen dataclass
  independently rejects a record carrying both. Event-scope refusals propagate
  into `invalid_security_ids`, then into a sector refusal, then into the global
  `if not refusals` gate.
- **Mutation matrix in a detached scratch worktree at `8701880`:** 14 reverse
  mutations aimed deliberately at guards the implementation's own ARV2I3-005
  list does not claim to pin. Seven bit: `final_executable_available`, the
  strict before-open evidence cutoff, the late-data-quality boundary, the
  1.4826 MAD scale, the diagnostics refusing-candidate guard, the
  structural-zero versus active distinction, and the candidate
  source-derivation check. Seven survived; five were pinned under
  ARV2R5-002/003/004 and two are documented in ARV2R5-005.

### 4L.3 Findings

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R5-001 | **P2** | **Corrected after Codex counter-review** | `research/analyst_revisions_v2/specs/`, `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py` | ARV2CR5-001's migration is **incomplete in the exact worktree it was written for**. `*.json -text` governs all seven artifacts, but only the three whose blobs were bumped to schema v2 were rewritten on checkout. Measured on this host: `arv2_round0.draft.json`, `legacy_reproduction_registry.json`, `permanent_look_authority.json` and `reviewed_spec_registry.json` were **CRLF in the lane worktree while their committed blobs are LF**, and `git status` reported the tree **clean** because the stat cache predates the `-text` rule. Two consequences follow. Any operation that refreshes that cache reveals four permanently modified files, and staging them would commit CRLF bytes into content-addressed artifacts. More importantly, `_review_anchor` requires `git status --porcelain` over the spec and the review registry to be **empty**, so in that state the first genuine reviewed-spec registration - the gate ARV2-4 depends on - refuses. Fail-closed throughout, hence P2 rather than P1. This also corrects my own 4I.3 claim that the working tree had been renormalized: that did not hold for this checkout. | Restored the all-artifact CRLF assertion that ARV2CR5-002 dropped when it narrowed the canonical set, keeping Codex's correct three-artifact byte-canonical contract intact, and repaired the four stale working files from their existing LF blobs; **no committed content changed**. The as-pushed failure message named a broad delete/checkout remediation; ARV2CR6-001 replaces it with narrow, non-destructive guidance. | The restored guard fails on the unrepaired lane worktree, naming `arv2_round0.draft.json`, and passes after the repair. Re-CRLF-ing an artifact turns it red again and restoring turns it green. A byte-level table of blob versus lane checkout versus fresh checkout was recorded during review. Codex additionally pins the effective `text: unset` attribute for all seven artifacts. |
| ARV2R5-002 | P3 | **Corrected** | `formulas.py` `rating_decay_weight` | The docstring promises the primitive "never truncates old or tiny-but-nonzero contributions" and `test_exponential_decay_has_no_hidden_hard_lookback_cutoff` is named for that property, but it probes **age 120 only**. The frozen history runs 2013-01-02 to 2026-08-31, roughly 3,400 sessions, so a cutoff introduced anywhere beyond 120 would silently drop the oldest events from every raw sum with the suite still green. | Added a regression pinning ages 251, 400, 1000, 2000 and 3400: strictly positive, strictly decreasing, and equal to the independent power formulation. | Inserting `if age_sessions > 250: return Decimal("0")` survives the original file and is **red** against the new one; restored green. |
| ARV2R5-003 | P3 | **Corrected** | `stock_signal.py` upstream-refusal filter | `PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS` is pinned as a constant, but no test exercised an identity-stage refusal **outside** that set, so the filter could stop consulting the constant entirely and stay green. `test_ontology_or_ambiguous_identity_refusal_still_blocks_cross_section` exercises only the ontology half: its fixture uses an unknown firm, which refuses at the `firm_ontology` stage. Widening the exemption to every identity-stage refusal would let an ambiguous or late issuer mapping - an unknown security, not a proven-ineligible one - publish scores, which is a fail-open direction. | Added a regression using an unmapped ticker, which produces a genuine identity-stage refusal outside the exempt set, and asserts the cross-section still refuses with `UPSTREAM_IDENTITY_OR_ONTOLOGY_REFUSAL` and emits no scores. | Dropping `and item.reason in PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS` is **red** against the new test and green restored. |
| ARV2R5-004 | P3 | **Corrected** | `StructuralStockScoreCandidate` frozen contract | Three record-level guards were unpinned because the builder already prevents the states they reject: the no-partial-artifact invariant, the `residualization_state` pin, and the structural-only `authority` pin. The last two carry this milestone's central safety claim - that it cannot become executable or acquire production authority - and all three are reachable by direct construction, which is exactly how a later consumer or fixture would assemble a candidate. | Added one regression that rejects a weakened authority, a weakened residualization state, and a refusing candidate carrying scores, and positively asserts `final_executable_available is False`. | Each of the three guards was mutated independently: all three **red** against the new test, all green restored. |
| ARV2R5-005 | P3 | **Documented, deliberately not fixed** | `stock_signal.py` sector refusal and `_stable_sum` | Two further mutations survived. Removing the `SECTOR_CONTAINS_INVALID_SECURITY` refusal changes only the refusal detail, because the underlying event or security refusal already forces the same empty result; and replacing magnitude-ordered summation with plain `sum` cannot be distinguished by fixtures at 50-digit precision. | None. Both are redundancy or determinism properties whose safety outcome is unchanged, and pinning the summation order would assert an implementation detail rather than a contract. | Recorded so a later refactor knows these two are unpinned by design rather than by oversight. |

### 4L.4 Validation

- Focused `test_stock_signal.py` as received: **55 passed in 28.39 s**, exactly
  reproducing the implementation's claim. After the three new regressions:
  **58 passed in 35.40 s**.
- Focused `test_dataset_and_import_firewall.py` on the final tree:
  **39 passed in 35.86 s**.
- Complete repository suite, exact **as-received** tree `8701880` in a
  detached scratch worktree: **5601 passed, 3 skipped, 25 warnings in 1068.06s (0:17:48)**.
- Complete repository suite, exact **final** tree including these review
  corrections: **5604 passed, 3 skipped, 25 warnings in 1068.48s (0:17:48)**.
- `compileall` exit 0; `git diff --check` clean; active-document gate
  **63 passed**; no frozen or shared file touched.
- Interpreter note: this review ran on **Python 3.12.13**, the only interpreter
  present in the repository virtual environment on this host, while the
  implementation row cites its own environment. Counts are therefore comparable
  by node identity rather than by interpreter version.
- Environment note **ARV2ENV-002**, mine rather than the implementation's: an
  initial full-suite run under a deep `--basetemp` produced 41 failures and 98
  errors, every one of them `Git lineage command failed: ... Filename too
  long`. That is the Windows path-length limit reached by the temporary Git
  repositories these tests construct, not a defect; a short `--basetemp` such
  as `C:/t/bt` reproduces clean results. Recorded so the next agent does not
  rediscover it.

### 4L.5 Next step

Codex's counter-review is recorded in section 4M. No blob refresh is warranted:
all seven committed artifacts and working files are LF, and rewriting the four
semantic-canonical artifacts merely for churn could disturb the owner-frozen
candidate identity. The effective `text: unset` rule is instead pinned by a
regression.

Mandatory-control residualization and the primary event-study analysis
contract are owner-decision gates that must be frozen and independently
reviewed before any ARV2-4 outcome/look access; they cannot be selected after
results. The reviewed spec anchor, audited production inputs,
vendor-to-QuantConnect processing rights, prospective interval, and external
append-only permanent-look authority also remain open. Every production
authority remains zero-access.

## 4M. Codex counter-review of Claude's ARV2-3 review, 2026-08-30

**Range reviewed:** `8701880..12157dd`, exactly two Claude commits.
**Disposition:** `6e8edab` **accepted after correction**; `12157dd`
**accepted after correction**. Counter-review ledger: **0 P0, 0 P1, 3 P2,
4 P3; all corrected.** The ARV2-3 review chain is closed. **Zero research
looks.** No credential, provider row, licensed artifact, price, return,
outcome, broker, operator database, QuantConnect job, scheduler, order, UI, or
Streamlit access occurred.

### 4M.1 Findings and corrections

| ID | Pri | Status | Reviewed commit | Issue and impact | Correction |
|---|---|---|---|---|---|
| ARV2CR6-001 | **P2** | **Corrected** | `6e8edab`, `12157dd` | The EOL assertion recommended deleting every spec JSON and checking out the whole directory, and the record called that safe. Following it could destroy untracked artifacts and intended unstaged edits, violating the repository's preservation rule. | Removed the broad command. The diagnostic now requires preserving intended edits and restoring only the named file's confirmed line-ending drift. Section 4L.3 no longer calls the original remediation safe. |
| ARV2CR6-002 | P3 | **Corrected** | `6e8edab` | The long-horizon decay test used absolute tolerance `1e-40`; at age 3400 the expected weight is about `6.68e-52`, so a value billions of times too large could pass. | Replaced the vacuous absolute comparison with a 60-digit-context relative-error bound below `1e-48`. |
| ARV2CR6-003 | P3 | **Corrected** | `6e8edab` | The direct-construction invariant pinned partial `scores` but not the other forbidden operand, `sector_normalizations`. | Added the symmetric refusing-candidate replacement and error assertion. |
| ARV2CR6-004 | P3 | **Corrected** | `6e8edab` | The all-artifact EOL regression did not pin the governing `*.json -text` rule and its docstring overstated the exact-byte loader set. Already-LF files would stay green if `.gitattributes` were weakened. | Asserted effective `text: unset` for every discovered spec artifact and distinguished the seven clean-tree artifacts from the three exact-byte loader consumers. |
| ARV2CR6-005 | **P2** | **Corrected** | `12157dd` | Canonical section 2 and section 4 still described ARV2-3 as pending Claude review and instructed Codex to repeat the already-completed push/review stage. | Updated the status and stock-formula disposition, closed the ARV2-3 review chain, and rewrote section 4 as the current owner/gate handoff. |
| ARV2CR6-006 | **P2** | **Corrected** | `12157dd` | Section 4L.5 treated mandatory-control residualization before ARV2-4 as an optional timing question. The PDF requires Round 1 executable returns after controls and signal survival after momentum/earnings/peer controls; selecting the estimator after the one-shot result would invalidate the look. | Made both the executable control contract and primary event-study analysis contract explicit pre-outcome owner-decision and independent-review gates, with the unresolved semantics enumerated in section 4. |
| ARV2CR6-007 | P3 | **Corrected** | `12157dd` | The narrative said seven mutations survived but only four were corrected and two documented. ARV2R5-002 pins one, ARV2R5-003 one, and ARV2R5-004 three: five corrected plus two documented. | Corrected sections 4L.1/4L.2. The historical append-only Claude ledger row is retained verbatim; this row supplies its correction. |

### 4M.2 Independent verification and stop disposition

- The exact review range is `6e8edab`, then `12157dd`; the first changes only
  two Analyst V2 test files and the second only this lane record.
- Before Codex corrections, focused stock-signal and dataset/import-firewall
  files independently reproduced **58 passed** and **39 passed**. All seven
  spec files had zero CRLF bytes and exact worktree-to-blob identity; the
  effective attribute was `text: unset` for each.
- Final corrected-tree validation is recorded in the session ledger below.
- The PDF's residual-score equation requires training-only coefficient
  estimation; Round 1 requires realistic executable returns after controls;
  its mandatory-control chapter names the control families; and the Signal
  Gate requires survival after momentum, earnings, peer, overlap, and
  holdings-lag controls. Those requirements establish the pre-look gate; they
  do not choose the still-unfrozen executable semantics.
- ARV2-4 is blocked before implementation and before push under the serialized
  lane workflow. This counter-review is committed locally only. No next
  milestone, provider/entitlement audit, outcome access, or QC work was begun.

## 4N. Owner QC-first sequence and ARV2-3Q planning candidate, 2026-08-30

**Owner decision:** run historical backtests in QuantConnect before beginning a
new untouched prospective year; after successful historical screens, complete
the intervening ETF/QC milestones and use QC Paper Trading for the prospective
confirmation. A small funded QC canary may be considered only after successful
paper confirmation under a separate live-risk gate. This is sequencing, not
current run or trading authority.

**Implemented:** a strict, content-addressed, outcome-free QC-first amendment
and loader; an explicit legacy-v1 outcome tombstone; a stock-only training-fold
control contract; a date-level stock event-study contract; separate historical
development evaluations and future paper confirmation; exact historical cutoff
and horizon maturity dates; and constant-false upload/run/deployment/live
capabilities. `stock_signal.py` now names the owner-frozen control boundary but
does not implement or publish a residualized score.

**Pre-commit review findings corrected:**

- ARV2Q-001 (P1): the first draft reused the legacy prospective v1 permit for a
  historical evaluation. The old ID and period now remain superseded unspent,
  v1 has only a migration-only structural identity, public v1 outcome access
  always refuses, and ARV2-4 requires a separate full V2 evaluation schema.
- ARV2Q-002 (P2): historical tests were initially described as permanent looks.
  They are now immutable development screens with no confirmatory alpha; only
  the future blinded paper look receives `1/60`.
- ARV2Q-003 (P2): the initial control/event-study draft conflated stock and ETF
  fits, left common-event multi-membership and actual-session inference
  ambiguous, under-specified horizon/IC/classification reporting, and allowed
  later power/capacity choices. Stock and ETF contracts are split; common-event
  components, fold/HAC/block constraints, exact Spearman IC/Fama-MacBeth
  outputs, PRIMARY/SECONDARY/EXPLORATORY labels, FDR/deflated-Sharpe reporting,
  10-bps-per-side primary costs, pre-run definition/manifest/power/economic/
  reporting hashes, and separately bound diagnostic capacity choices now fail
  closed. None of the actual null hashes may execute.
- ARV2Q-004 (P2): paper blindness and evidence epochs were incomplete. Efficacy
  output sealing, the safety-monitor whitelist, monotone hash-chained ordinary
  appends, exact committed/terminal look accounting, rights/counter-review
  prerequisites, no replacement or blind extension, and invalidation for
  retroactive data/provider/ontology/code/configuration/execution/runtime changes
  are now frozen.
- ARV2Q-005 (P2): mutable policy globals and Python Boolean/integer equality
  or a mutable root-key allowlist could weaken a correctly rehashed artifact.
  Recursive immutable templates, an immutable root schema, and type-aware exact
  comparison now refuse those attacks.
- ARV2Q-006 (P2): the amendment trusted the predecessor's embedded hash, flattened
  source/upload/compile/launch authorities into a circular list, and left funded
  gates as prose. The loader now recomputes the exact retired predecessor hash;
  historical authority is a strict phased state machine with separately null
  bindings; and the funded policy machine-binds paper success, reviews, rights,
  exact QC/risk/account artifacts, kill-switch and reconciliation receipts while
  retaining zero live/order authority.

**Boundary:** the power-plan, run-plan, data/source/right, reviewed-spec,
external evaluation/look authority, QC project/compile, paper epoch, and funded
risk bindings remain null or absent. This milestone used synthetic structure
only: zero provider rows, outcomes, evaluations, permanent looks, QC jobs,
deployments, broker actions, or orders.

## 4O. Independent Claude review of the ARV2-3 counter-review and the ARV2-3Q QC-first candidate, 2026-08-30

**Range reviewed:** `12157dd..f724bf9`, two commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, **2 P2**, 8 P3
corrected; 5 P3 documented and deliberately not fixed; 1 reported defect
closed as a **false alarm** after independent reproduction.
**Zero research looks, zero development evaluations.** No provider,
credential, licensed row, price, return, outcome, broker, operator-database,
QuantConnect job, upload, scheduler, order, UI or Streamlit access occurred.

Owner scope instruction applied: every correction is inside
`research/analyst_revisions_v2/` or `tests/analyst_revisions_v2/` and its
sibling preregistration test. No frozen or shared file was touched. Unlike the
previous round this review does modify one production module, `qc_first_plan.py`,
by twelve lines; the justification is in ARV2R6-003.

### 4O.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `9309de3` | Accepted after correction | Codex's counter-review of my ARV2-3 review. I verified it **strictly strengthened** every guard it touched: no assertion was deleted, no tolerance loosened, no match narrowed. ARV2CR6-002 is a genuine sensitivity increase - the old absolute `1e-40` bound was vacuous at age 3400, where the true weight is about `6.68e-52`, so a value many orders of magnitude wrong would have passed; the replacement relative bound catches it. ARV2CR6-001's narrowing of my remediation wording is correct and I accept the criticism: my original message told the reader to delete every spec JSON, which could destroy untracked or intended-unstaged work. Corrected here only by ARV2R6-005. |
| `f724bf9` | Accepted after correction | The ARV2-3Q QC-first planning candidate: a 1,235-line loader, an 847-line content-addressed spec, a new test file, and outcome-gate changes. The safety architecture is sound - I reproduced the identity binding, the retired-look tombstone and the constant-false capabilities first-hand - but two guards carrying its own stated authority boundary had no test at all (ARV2R6-001/002). |

### 4O.2 Independent verification

Reproduced first-hand rather than accepted from the record:

- **Plan identity.** `plan_hash` is SHA-256 over the parsed payload with
  `plan_id` and `plan_hash` set to null, serialised `sort_keys=True`,
  `separators=(",",":")`, `ensure_ascii=False`; `plan_id` is
  `arv2-qc-first-plan-` plus the first 16 hex characters. I recomputed
  `9574bf824e9b9735...e706e7` exactly. Note the binding is over canonical
  content, not file bytes - the raw file SHA-256 is `bf74c9c6...` - so a
  differently serialised file with identical meaning authenticates. That is
  acceptable because every root section additionally passes recursive
  type-aware comparison against in-module frozen templates.
- **The retired look is genuinely unreachable.** The committed
  `arv2_round0.draft.json` now refuses through its own loader
  (`look identity was superseded unspent and cannot be revived`), the
  predecessor is authenticated by recomputed hash with its tombstone (id,
  period, state) pinned, and `authorize_outcome_access` raises on every path.
- **Constant-false capabilities.** `upload_available`,
  `historical_launch_available`, `paper_deployment_available` and
  `funded_live_available` are literal `return False` properties with no
  data-dependent path.
- **Calendar arithmetic.** Independently recomputed from
  `data.exchange_calendar`: 2026-08-28 is an NYSE session, and the last mature
  decision sessions for horizons 1/5/20/60 are exactly 2026-08-27, 2026-08-21,
  2026-07-31 and 2026-06-03 as frozen. `0.05/3` is carried as the exact
  rational `1/60`.
- **Freeze compliance.** Neither commit touches the Action Plan, root Session
  Handoff, direction record, shared workflow, data-source register,
  `requirements.txt`, `config.py` or another lane.
- **Full suite as received at `f724bf9`: 5,626 passed, 3 skipped, 0 failed**,
  which reproduces the implementation ledger row exactly.

### 4O.3 Findings

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R6-001 | **P2** | **Corrected** | `preregistration.py` `SUPERSEDED_VALIDATION_PERIODS` (guard) / `tests/test_analyst_revisions_v2_preregistration.py` (no test) | The superseded-period refusal is half of the ARV2Q-001 P1 remediation the record claims - "the old look identity and exact period refuse" - and it had **no regression test**. Emptying `SUPERSEDED_VALIDATION_PERIODS` to `frozenset()` left all 43 tests green. Every existing fixture that renames the look also moves the start date to 2026-09-02, so no test ever reaches the period guard. Reachability confirmed: a correctly re-hashed candidate carrying the migration-only look id but the untouched 2026-09-01..2027-08-31 window is refused today by this guard alone. A silent regression would let the retired prospective window be re-registered under a fresh look id, corrupting the lane's look and alpha accounting. | Added the missing single-violation case to the existing one-violation-per-case battery: the migration-only candidate with the retired period restored must refuse with `superseded unspent by the owner QC-first sequence`. | Emptying the constant is **red** against the new case and green restored. |
| ARV2R6-002 | **P2** | **Corrected** | `qc_first_plan.py` authority/schema/status pins / `tests/analyst_revisions_v2/test_qc_first_plan.py` | The loader's pin of the plan authority string to `planning_only_no_data_no_outcome_no_qc_action_no_deployment` - the record's own authority-boundary marker - had **no test**: deleting that line passed all 21 tests, as did deleting the sibling `schema` and `status` pins. Reachability confirmed: a copy of the draft declaring `authority="full_qc_action_and_deployment_authority"` with a correctly recomputed `plan_hash`/`plan_id` is refused **only** by that line; with it removed the forged plan authenticates as a valid `QcFirstStudyPlan`. Any later composition layer that reads `plan.authority` would then be reading an attacker-chosen string. | Added three cases to the dangerous-change battery covering the authority, schema and status pins. | Each pin deleted independently is **red** against its new case and green restored. |
| ARV2R6-003 | P3 | **Corrected** | `qc_first_plan.py` JSON parse sites | The module advertises a no-binary-float contract and passes `parse_float=_reject_float`, but `json.loads` routes the bare `NaN`, `Infinity` and `-Infinity` tokens through `parse_constant`, which was not overridden. I confirmed all three tokens parse into Python floats without the refusal firing. **Not currently exploitable**: I injected NaN at all 151 top-level contract fields with correct re-hashing and the recursive frozen-template comparison refused every one. It is a hole in a stated contract on a module explicitly designed to grow as null hashes are filled, so it is worth closing now rather than after a field escapes exact comparison. | Added `_reject_constant` and wired `parse_constant` at both parse sites - the only production change in this review. | Removing `parse_constant` is **red** against the extended float test and green restored; the 151-point injection sweep is recorded above. |
| ARV2R6-004 | P3 | **Corrected** | `qc_first_plan.py` `_require_exact`, `_object`, plan-identity check | Four further defences claimed by ARV2Q-005/006 were unpinned: relaxing type-aware comparison to plain `!=` (so `True` passes as `1`), allowing unknown keys inside nested contracts, deleting the `plan_id` content-derivation check, and removing `object_pairs_hook` so a duplicated JSON key silently keeps the last value. Each mutation passed the whole suite. | Added a type-exactness case, a nested-unknown-field case, a standalone `plan_id` derivation test, and a duplicate-JSON-key test. | All four mutations **red** against the new tests and green restored. |
| ARV2R6-005 | P3 | **Corrected** | `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py` docstring | The docstring `9309de3` wrote says "All seven artifacts", but `f724bf9` added an eighth spec artifact in the very next commit. The test itself globs the directory and was unaffected. | Reworded to describe the set rather than count it. | Documentation only; the surrounding assertions are unchanged and still pass. |
| ARV2R6-006 | P3 | **Corrected** | `tests/test_analyst_revisions_v2_preregistration.py` | `f724bf9` deleted the only success-path assertions for `load_draft_preregistration`, so every remaining draft-loader test expected a refusal and nothing demonstrated the migration/structural-validation capability the record says is retained. A loader that began refusing everything would have passed. | Added one positive test asserting the returned draft's planned look, empty unresolved decisions and pending external bindings, and that the reviewed loader still refuses it. | Making the loader raise unconditionally is **red** against the new test and green restored. |
| ARV2R6-007 | P3 | **Closed - false alarm** | `tests/analyst_revisions_v2/test_dataset_and_import_firewall.py` check-attr guard | A reported survivor claimed the new `git check-attr` assertion is vacuous because renaming `specs/.gitattributes` away leaves it green. Reproduced and **refuted**: `git check-attr` also consults the index, so a worktree-only rename proves nothing about the guard. Against the threat the guard actually exists for - the rule being removed from the commit - I staged the deletion and the attribute became `text: unspecified` and the test failed. No code change; recorded so the same mis-specified mutation is not retried. | None. | `git rm --cached` plus worktree removal turns the guard red; worktree-only rename does not. |

### 4O.4 Documented, deliberately not fixed

| ID | Pri | Observation |
|---|---|---|
| ARV2R6-008 | P3 | **The "strict phased state machine" exists only as declarative data.** `authority_phase_order`, `phase_rule`, `authority_bindings`, `look_state_machine` and the funded-pilot gates are frozen JSON that no function in this milestone reads or enforces; the record's "machine-gated future paper/funded states" overstates what code does today. Harmless while every capability is constant false and no executor exists, but the enforcement must be written before any phase can be claimed satisfied. Recorded rather than fixed because implementing an executor is ARV2-4 scope, not review scope. |
| ARV2R6-009 | P3 | **The maturity invariant is not revalidated by the loader.** The loader checks the cutoff and the four decision dates are NYSE sessions and that `history_start < cutoff`, but never recomputes that the h-th session after each decision falls at or before the cutoff. I verified the four committed dates are correct today; a coordinated wrong edit would not be caught. |
| ARV2R6-010 | P3 | **Loader symlink/TOCTOU hardening is weaker than the sibling registry.** `load_qc_first_study_plan` and `_verify_superseded_base` use a bare `read_bytes()` with no symlink refusal, strict resolve, or retained-payload re-read, whereas `production_registry.py` was hardened for exactly that under ARV2I2-006. No production path admits this artifact yet, so the gap is latent. |
| ARV2R6-011 | P3 | **`owner_frozen` provenance is broader than the recorded owner decision.** The plan status is `owner_frozen_outcome_free_pending_independent_review_and_external_bindings` and the record calls it the "owner-frozen QC-first plan", but section 4N records the owner decision as sequencing - run historical backtests in QC before a prospective year. The detailed statistical contract (19,999 resamples, 10 bps per side, cohort definitions, HAC distances) was authored by the implementer, not chosen by the owner. In a lane whose whole discipline is provenance, "owner-frozen" should name only the cells the owner actually decided. Flagged for the owner rather than silently relabelled. |
| ARV2R6-012 | P3 | **The industry tier is orphaned.** The amendment inherits the owner-frozen `topology_comparison_hierarchy` cell whose value is `["stock","industry","etf"]`, but its own `gatekeeping_order` and the rewritten ARV2-4..10 ladder go stock then ETF with no industry stage. Either the inherited cell is superseded and should say so, or a stage is missing. |

### 4O.5 Correction to a claimed count

The `f724bf9` ledger row states the complete Analyst V2 battery is
"352 passed, 1 host symlink skip". On the exact pinned tree I measure
**347 passed, 1
host-capability symlink skip** on the corrected tree for
`tests/analyst_revisions_v2` plus the contracts and preregistration files -
equivalently **338** before my nine new nodes. The 352 figure is not
reproducible under that selection; the likeliest explanation is a wider file
selection rather than a failure, and nothing in my run failed. The ledger is append-only, so the row stands; this
paragraph is its correction, in the same way ARV2CR6-007 corrected my earlier
mutation arithmetic.

### 4O.6 Validation

- Full suite, exact **as-received** tree `f724bf9` in a pinned detached
  worktree: **5,626 passed, 3 skipped, 25 warnings**, reproducing the
  implementation claim exactly.
- Full suite, exact **final** tree including these corrections:
  **5,635 passed, 3 skipped, 0 failed, 25 warnings in 1,054.82 s (17m35s)**.
  The delta of exactly nine nodes over the as-received run is the nine
  regressions added here, so no pre-existing node changed state.
- Focused after correction: QC-first plan **28 passed**; preregistration
  **45 passed**; dataset/import firewall **39 passed**.
- Ten reverse mutations across both correction batches: every one **red**
  against its new test and **green** restored.
- `compileall` exit 0; `git diff --check` clean; active-document gate
  **63 passed**. Python 3.12.13.

### 4O.7 Next step

Codex counter-reviews this exact pushed head before accepting ARV2-3Q or
starting any ARV2-4 work. Three items deserve its attention and an owner
decision rather than an implementer choice: the `owner_frozen` provenance
label (ARV2R6-011), the orphaned industry tier (ARV2R6-012), and whether the
declarative authority state machine (ARV2R6-008) must become executable code
before any phase is claimed satisfied.

ARV2-4 remains blocked. The reviewed spec anchor, audited production inputs,
vendor-to-QuantConnect processing rights, external append-only evaluation and
look authorities, and explicit owner run authority are all still absent, and
every production authority remains zero-access.

## 4P. Codex counter-review of Claude commits `39104f6` and `f2c15d8`, 2026-08-30

**Range reviewed:** `f724bf9..f2c15d8`, two commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, 3 P2 and 6 P3
corrected; 0 unresolved P0-P3. **Zero research looks and zero development
evaluations.** No credential, provider row, licensed artifact, price, return,
outcome, QuantConnect upload/compile/job, deployment, broker, scheduler, or
order was accessed.

| Commit | Disposition | Basis |
|---|---|---|
| `39104f6` | Accepted after correction | Claude's parser and authority-guard corrections were directionally correct. Codex retained them, extended duplicate-key refusal to both preregistration parse sites, and added missing predecessor duplicate/non-finite regressions. |
| `f2c15d8` | Accepted after correction | Claude's review record correctly identified several real gaps, but its canonical handoff, finding count, global comparator, topology, provenance, phase-enforcement, maturity, and file-authentication details required correction before ARV2-3Q could be accepted. |

### 4P.1 Findings and corrections

| ID | Pri | Status | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2CR7-001 | P3 | Corrected | `preregistration.py`; preregistration tests | Duplicate-key refusal covered the QC-first parser but not both legacy draft parse sites; predecessor duplicate/non-finite cases were unpinned. | Added one strict duplicate hook to both sites and exact regressions for duplicate keys and non-finite predecessor data. | Counter-review-only battery green; reverse parser cases refuse. |
| ARV2CR7-002 | **P2** | Corrected | Canonical status, section 4, section 4O | The record still said Codex counter-review was pending and treated all ARV2-4 implementation as blocked, even though the next outcome-free structural prerequisite was not authority-gated. | Accepted ARV2-3Q after correction, separated ARV2-4A structural work from the real-data/QC evaluation, and corrected the exact next step. | Canonical status and handoff now agree with the code gates. |
| ARV2CR7-003 | **P2** | Corrected | `qc_first_plan.py`; QC-first artifact/tests | Firm-specific normalization had no decisive, scale-invariant, matched-row comparison against the global-map baseline. | Added the paired 20-session Spearman-IC non-inferiority gate on identical walk-forward test rows; failure is non-rescuing and closes the family. | Definition, hash, weakening tests, and parent identity recomputation pass. |
| ARV2CR7-004 | **P2** | Corrected | `qc_first_plan.py`; QC-first artifact/tests | The frozen stock-to-ETF sequence orphaned the PDF's industry tier and omitted decisive direct-stock variants and holdings-lag sensitivity. | Restored the stock -> industry -> ETF topology, direct equal/inverse-volatility/score-weight stock variants, and H0/H1/H5 holdings-lag checks. | Exact topology and weakening regressions pass. |
| ARV2CR7-005 | P3 | Corrected | QC-first status/provenance | `owner_frozen` overstated what the owner had personally selected. | Replaced it with implementation-frozen, outcome-free candidate terminology and recorded the owner sequencing source separately. | Exact schema/status/provenance pins pass. |
| ARV2CR7-006 | P3 | Corrected | QC-first authority phases | Phase order was declarative only, while the record implied executable enforcement. | Added structural phase-binding validation while keeping evidence and action capabilities literal false; no phase can self-authorize. | Forged/missing bindings and action-capability mutations refuse. |
| ARV2CR7-007 | P3 | Corrected | QC-first horizon maturity | Frozen maturity dates were compared as strings but not recomputed from the NYSE calendar. | Recomputed every horizon against the cutoff during authentication. | Calendar mutation tests refuse. |
| ARV2CR7-008 | P3 | Corrected | QC-first artifact loading | A file could be read through a symlink or change between authentication steps. | Required regular non-symlink paths, stable double reads, and post-authentication byte revalidation. | Symlink and time-of-check/time-of-use mutations refuse. |
| ARV2CR7-009 | P3 | Corrected | Section 4O issue ledger | The claimed `8 P3 corrected` count did not reconcile with the four listed corrected P3 IDs, and several open observations were presented as owner decisions when the PDF already resolved them. | Preserved the historical text, corrected it append-only here, and classified implementation corrections versus genuinely gated external actions. | This section contains the complete reconciled disposition. |

### 4P.2 Validation and next step

- Counter-review-only tests: **119 passed in 70.15 s**.
- The corrected parent is
  `arv2-qc-first-plan-36e455e72b8750fe` / SHA-256
  `36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc`.
- All action capabilities remain false; all external source, result, QC,
  deployment, and order authority remains absent.

ARV2-3Q is accepted after correction. The next bounded milestone is ARV2-4A,
the outcome-free structural prerequisite described in section 4. It requires
no credentials and grants no authority to bind provider rows, outcomes, QC,
paper deployment, funded deployment, or orders.

## 4Q. ARV2-4A outcome-free structural evaluation prerequisite, 2026-08-30

**Milestone disposition: IMPLEMENTED CANDIDATE PENDING CLAUDE REVIEW.** This is
not ARV2-4 completion and performs no historical evaluation. It consumed zero
provider rows, outcomes, QC actions, development evaluations, or permanent
looks.

### 4Q.1 Implemented scope

- Added canonical child contract
  `arv2-stock-historical-dcc30556b6fb582b` / SHA-256
  `dcc30556b6fb582b249d6fa2945e4e23161035502a014ba645c521c743251629`,
  binding the exact strategy PDF and corrected QC-first parent. The loader
  refuses duplicate keys, binary floats/non-finite values, noncanonical UTF-8
  bytes, BOM/CRLF/whitespace variants, symlink traversal, unstable reads,
  source mutation, direct construction, copied authority, and nested mutation.
- Materialized the PDF/parent stock structure for 1/5/20/60 open-to-open SPY
  excess returns, bullish-primary/bearish-secondary Fama-MacBeth analysis,
  date-level Spearman IC, exact common-event connected components, actual-NYSE
  HAC distance, 19,999 centered complete-session block resamples, the three
  conjunctive primary gates, the full report/Appendix-C plot inventory, and the
  stock -> industry -> ETF downstream hierarchy. These remain definitions only.
- Implemented pure fixture-only pre-open controls: exact Decimal inputs; a
  frozen 50-digit HALF_EVEN context; accepted-row median/MAD scaling; named
  missing, wrong-session, late, and unseen-industry refusals; a 20-row and 95%
  per-date floor; structural-zero preservation; and exact coverage denominators.
- Implemented content-derived fixture fold boundaries with exact horizon-sized
  NYSE purge/embargo gaps for 1/5/20/60, candidate-policy lineage, training-only
  Decimal modified-Gram-Schmidt QR with a relative rank threshold, immutable
  coefficients/columns/industry levels, and validation/test-only application.
  Nested models, folds, cross-sections, rows, refusals, and batch partition
  intervals are revalidated before use.
- Added an immutable report-plan surface that can enumerate outputs but cannot
  receive outcome rows, results, a disposition, promotion, QC, deployment, or
  order authority.

### 4Q.2 Review findings corrected during implementation

The implementation was audited in parallel for code integrity and statistical
fidelity. All P0-P2 findings were corrected before handoff: exact parent primary
IDs, test-fold-only global comparison, common-event weighting/refusal semantics,
IC/Fama-MacBeth HAC and bootstrap contracts, weighted immediate-event jump,
power fields, loader provenance/canonical bytes, exact fold gaps, candidate
policy lineage, nested-mutation reauthentication, row/date coverage, rank-stable
QR, frozen Decimal rounding/exponents, batch partition containment, and a
held-out residual golden proving frozen prediction subtraction with no
validation refit. Final independent dispositions were **0 P0, 0 P1, 0 P2**.

### 4Q.3 Validation and remaining gates

- ARV2-4A focused tests: **27 passed in 5.57 s**.
- Combined counter-review plus ARV2-4A selection: **146 passed in 70.76 s**.
- Independent code audit: **109 passed**, with no remaining P0-P2.
- Canonical loader check: no module/artifact section drift, no section-hash
  drift, content-derived child identity exact.
- Complete Analyst V2 battery: **396 passed, 1 host symlink skip in 106.67 s**.
- Exact repository tree: **5,669 passed, 3 skipped, 0 failed, 25 known
  dependency warnings in 893.21 s (14m53s)**.
- Changed-module compile, active-document, diff, and final status gates are
  rerun after this final record update and before commit/push.

Every child external binding is null and every action capability is false.
Source-specific stale-control semantics, audited production controls, the
global map and matched-row contract, fold manifest, power calibration,
secondary/trial registries, economic execution definition, liquidity/capacity
binding, dataset/code/QC identities, review anchors, results, and evaluation
receipt remain absent. Therefore no provider, outcome, QC, paper, funded, or
order action is reachable. Claude reviews this candidate next; Codex then
counter-reviews before any later bounded milestone.

## 4R. Independent Claude review of ARV2-3, ARV2-3Q and ARV2-4A, 2026-08-30

**Range reviewed:** `f592334..c334571`, ten commits, each disposed below.
**Disposition: ACCEPTED.** 0 P0, 0 P1, 0 P2, 0 P3. **No correction was
required** — the first round in this lane where I found nothing to fix. Two
observations are recorded in 4R.4 because they matter to future refactors and
to lane coordination, not because either is a defect.
**Zero research looks.** No provider, credential, licensed row, price, return,
outcome, broker, operator-database, QuantConnect, scheduler or order access
occurred, and none was possible: every capability probed is constant false.

**Reviewing session:** this is the Fable 5 session on the work identity
(`sheltonchen@microsoft.com`), the same session that produced §4I. Sections
§4L and §4O were produced by a different Claude session; see ARV2R7-002.

### 4R.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `a597ac3` | Accepted | Codex counter-review of my ARV2-2 corrections. It kept my `.gitattributes` fix and **improved it**: bumping the artifact schema v1→v2 forces a tracked blob change, which is what actually renormalizes a pre-existing worktree — adding the attribute alone does not. |
| `8701880` | Accepted | ARV2-3 structural stock scoring. Canonical formula goldens are pinned exactly (d=0→1, d=20→0.5, d=40→0.25) and the stock reliability constant is deliberately distinct from the ETF one. |
| `6e8edab` | Accepted | Restores the universal CRLF assertion I had written and adds a `git check-attr text` check, so the guard now pins the mechanism as well as the property — stronger than my original. |
| `12157dd` | Accepted as prior-review record | Independent Claude review of ARV2-3 by another session. Its material claims were re-derived here rather than accepted. |
| `9309de3` | Accepted | Codex counter-review of that review. |
| `f724bf9` | Accepted | ARV2-3Q QC-first resequencing. The most consequential commit in the range; verified in detail in 4R.2. |
| `39104f6` | Accepted | Pins ARV2-3Q authority guards and closes a non-finite parse hole. |
| `f2c15d8` | Accepted as prior-review record | Independent Claude review of ARV2-3Q by another session; claims re-derived here. |
| `e53ba26` | Accepted | Codex counter-review of that review; it changed the QC-first artifact, and the record's active identity statement was correctly updated to the new `arv2-qc-first-plan-36e455e72b8750fe`. |
| `c334571` | Accepted | ARV2-4A outcome-free prerequisites: stock controls and the stock evaluation contract. |

### 4R.2 The QC-first resequencing, verified rather than accepted

This amendment supersedes the ARV2-0 frozen look and introduces a path toward
QC paper trading and an optional funded canary, so it received the most
scrutiny.

- **The superseded look cost nothing.** The retired look remains
  `planned_unbound` with null `dataset_id` and null `code_identity` — the same
  state I verified myself when reviewing ARV2-0 — and the v1 loader now
  actively refuses it with `look identity was superseded unspent and cannot be
  revived`. Retiring an unbound, unspent look consumes zero alpha.
- **The multiplicity model is coherent and honest.** Family alpha is 1/20; the
  single prospective look carries 1/60, which is the three-lane Bonferroni
  correction applied to one lane look. Historical QC work is explicitly
  labelled `selection_and_engineering_only_no_confirmatory_alpha_claim`, so
  iteration during development cannot masquerade as confirmation.
  `unused_alpha_reallocation` is prohibited, and both a historical screen
  failure and a prospective valid null close the family.
- **Stock-first survives the resequencing.** The frozen `gatekeeping_order` is
  stock historical → industry/ETF topology construction → combined historical
  → ETF paper prospective. ETF residualization is explicitly a different
  contract deferred to ARV2-6 and may not reuse stock coefficients.
- **The obvious critique is pre-empted.** Moving confirmation to 252 paper
  sessions invites an underpowered-confirmation objection, since a 20-session
  horizon yields only about a dozen independent periods. The plan states
  `duration_role: target_only_not_a_power_claim`, requires a pre-observation
  power plan naming `required_eligible_sessions_and_independent_clusters` and
  `minimum_economic_effect` (its hash is still null, so execution is blocked),
  spends alpha only at atomic final unseal, and retires an insufficient look
  **uninspected** with no replacement or alpha reuse. That is the correct
  treatment of an underpowered look: do not peek at it.

### 4R.3 Adversarial verification performed

- **Fail-closed latches, probed directly.** All six research source kinds
  refuse; the outcome loader never executes; both zero-access declarations
  resolve to their exact IDs (a refusal alone cannot distinguish a real
  declaration from an unreadable file). The QC-first plan's upload,
  historical-launch, paper-deployment and funded-live capabilities are all
  `False`, are properties that cannot be force-set, and **stayed false when I
  claimed every authority phase complete with full bindings** —
  `grants_action_authority` and `evidence_authentication_performed` are
  likewise constant false. Out-of-order phase prefixes, premature phase
  outputs, and tampered `plan_status` / `planning_authority` all refuse.
- **Import boundary**: transitive closure reaches 29 modules with zero
  execution-capable or network roots, including all four new modules.
- **Mutation matrix (detached scratch worktree at `c334571`).** Killed:
  `funded_live_available → True` (2 failed); phase-prefix order check removed
  (1 failed); `outcome_access_available → True` (13 failed);
  `control_definition` dropped from the frozen-section exact-match set (25
  failed); `STOCK_RELIABILITY_N0` 3 → 5, the stock/ETF constant confusion (4
  failed). Two mutations survived and are explained in ARV2R7-001.

### 4R.4 Observations (no correction required)

| ID | Kind | Observation |
|---|---|---|
| ARV2R7-001 | Unreachable redundancy, verified | Two guards inside `stock_controls._require_contract` — the `control_definition` equality check and the `external_bindings` all-null check — survived mutation. They are **unreachable, not untested**: I demonstrated empirically that a correctly re-hashed contract carrying either violation is refused at load (`control_definition.active_residual_clip changed from the frozen…`, `external_bindings.review_commit changed from the frozen…`), and `require_loaded_stock_evaluation_contract` independently reauthenticates loader provenance. Writing a regression would require constructing a state the loader already rejects. Recorded so a future refactor that relaxes the loader's exact-match knows these inner checks become the remaining backstop. This is the same architectural pattern as `ARV2R4-005`. |
| ARV2R7-002 | Lane coordination | Two different Claude sessions are now reviewing this lane: the Opus 5 session on the personal Git identity produced §4L and §4O, while this Fable 5 session on the work identity produced §4I and this section. Commit trailers distinguish them cleanly (`Co-Authored-By: Claude Opus 5` versus `Claude Fable 5`), and the counter-review commits carry no Claude trailer, so the implement → review → counter-review loop is intact and no record is misattributed. The parallel workflow nevertheless specifies **one dedicated Claude review session per lane**, and two sessions risk duplicated or divergent review records. This is an owner coordination decision, not a defect, and is raised rather than acted on. |

### 4R.5 Validation

- Full suite on the exact as-received tree `c334571`: **5,668 passed, 4
  skipped, 0 failed, 25 known dependency warnings in 2,227.73 s**. The four
  skips are this host's two pre-existing skips, the `CLR-001` interpreter
  skip, and the host-capability symlink skip.
- This review changes **no code and no test** — only this record — so the
  as-received run above is also the final-tree code validation. The
  active-document gate is rerun immediately before commit.
- Focused batteries during review: ARV2 directory **292 passed, 1 skipped**;
  QC-first plan **34 passed**; stock evaluation/controls **27 passed**; stock
  signal **58 passed**.
- `git diff --check` clean; no frozen shared file touched; no production
  module modified.

### 4R.6 Next step

This historical instruction was completed by the section 4S counter-review.
ARV2-4 remains blocked by the recorded source, rights, review, run-identity
and one-use authority gates; every executable definition hash is still null,
so stock execution, upload, QC launch, paper deployment and funded live all
remain constant false.

## 4S. Codex counter-review of Claude commit `37dc424`, 2026-08-30

**Commit reviewed:** `37dc424fee28fd71fbd23951e267c6997088a889`
against parent `c33457109f71f65a3e30c0d4c71984055d633304`.
**Disposition: ACCEPTED AFTER CORRECTION.** Review ledger: 0 P0, 0 P1,
5 P2, and 5 P3; all corrected. Claude changed only this lane record, but its
clean disposition triggered a cumulative recheck of the accepted lane tree.
That recheck found one inherited ARV2-2 production-admission defect, one
material ARV2-4A decision-clock defect, one material ARV2-4A cross-section
lineage defect, and three ARV2-4A contract/reporting defects that the review had
missed. **Zero research looks and zero development evaluations.** No credential,
provider row, licensed artifact, price, return,
outcome, QC upload/compile/job, deployment, broker, operator database,
scheduler, order, UI, or Streamlit surface was accessed.

Quality assessment: Claude's record-only review is **6/10** because its core
zero-authority findings were sound but its handoff/dispositions were stale and
its cumulative review missed both the inherited production-admission defect
and the two ARV2-4A temporal/lineage defects. The corrected ARV2-4A structural
tree is **8/10**: narrow, deterministic, and strongly fail-closed, while all
production sources, executable definitions, external authorities, and the QC
run remain deliberately absent.

### 4S.1 Commit disposition and reconciled prior range

| Commit | Correct cumulative disposition | Basis |
|---|---|---|
| `a597ac3` | Accepted after correction | Historical ARV2R5-001, later CRLF-worktree corrections, and inherited production-registration correction ARV2CR8-005 remain part of its disposition. |
| `8701880` | Accepted after correction | Historical ARV2R5-002 through ARV2R5-004 corrections remain part of its disposition. |
| `6e8edab` | Accepted after correction | Section 4M records the counter-review corrections to its tests and guidance. |
| `12157dd` | Accepted after correction | Section 4M corrects its canonical handoff and review arithmetic. |
| `9309de3` | Accepted after correction | Section 4O records the later guard and parser corrections. |
| `f724bf9` | Accepted after correction | Section 4O records the later authority, parser, and positive-path corrections. |
| `39104f6` | Accepted after correction | Section 4P retains and extends its parser/authority corrections. |
| `f2c15d8` | Accepted after correction | Section 4P corrects its handoff, topology, provenance, and phase claims. |
| `e53ba26` | Accepted | Its ARV2-3Q counter-review corrections remain valid; no later defect is assigned to this commit. |
| `c334571` | Accepted after correction | ARV2-4A is accepted after ARV2CR8-006 through ARV2CR8-010 below. |
| `37dc424` | Accepted after correction | Its independent verification is retained; ARV2CR8-001 through ARV2CR8-004 correct its record. |

Section 4R's plain `Accepted` labels describe that reviewer's absence of new
findings; they do not erase the resolved findings already retained in sections
4L through 4P. The two section 4R observations now have unique IDs
`ARV2R7-001` and `ARV2R7-002`. The append-only 2026-08-30 Claude ledger row
retains the original colliding `ARV2R5-001/002` text; those two references
resolve to `ARV2R7-001/002` after this collision correction.

### 4S.2 Counter-review issue ledger

| ID | Pri | Status | Location | Issue and impact | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|
| ARV2CR8-001 | P2 | Corrected | Canonical status, section 2, section 4 | The branch-local handoff still said ARV2-4A awaited Claude review and instructed repeating the already completed `c334571` push. | The lane record replaces the frozen root handoff; stale next-action text can make a later machine repeat a completed stage or infer the wrong gate. | Marked corrected ARV2-4A accepted at counter-review, updated the current-state table and exact next step, and preserved every external/QC block. | Canonical status, section 2, and section 4 agree; section 4R.6 is retained as the completed historical instruction and superseded by section 4S. |
| ARV2CR8-002 | P2 | Corrected | Section 4R.1 | Plain `Accepted` labels and a zero-finding summary erased prior accepted-after-correction dispositions in the same ten-commit range. | The required review ledger must retain resolved defects and dispose each commit both individually and cumulatively. | Added the reconciled table in section 4S.1 without rewriting the historical push-ledger row. | Rechecked the earlier authoritative tables in sections 4L, 4M, 4O, and 4P against all ten commits. |
| ARV2CR8-003 | P3 | Corrected | Section 4R.4 | Observation IDs `ARV2R5-001/002` collided with unrelated existing P2/P3 findings. | Stable IDs must be unambiguous for later correction and audit references. | Renamed the two section 4R observations and cross-references to `ARV2R7-001/002`. | Exact-ID search now has one definition for each new observation while the historical R5 findings remain intact. |
| ARV2CR8-004 | P3 | Corrected | Section 4R handoff | The required honest 1-10 quality assessment was absent. | The review/handoff process explicitly requires a quality rating alongside acceptance. | Recorded separate 6/10 review-record and 8/10 corrected-tree ratings above. | This section states both the rating and its concrete basis. |
| ARV2CR8-005 | P2 | Corrected | `production_registry.py`; security-master registry test | A registry entry added after its named `review_commit` could admit the reviewed structural artifact; the positive test implemented exactly that sequence. The artifact blob was reviewed, but the later registry entry was not. | A caller-authored reviewed-by string and ancestor commit cannot grant production authority. Embedding a commit's own hash in the registry entry is circular, so the current scheme lacks a non-self-referential registration approval. | Retained artifact/blob/clean-tree/TOCTOU checks but made every positive registration fail closed until a separately pinned approval receipt exists. | The former positive path now expects `approval authority is absent`; later artifact substitution still fails against the reviewed blob. Current committed registries remain empty. |
| ARV2CR8-006 | P2 | Corrected | `stock_controls.py`; stock-evaluation tests | `PreopenControlCrossSection` parsed but did not reauthenticate that `decision_at` was the exact NYSE open for `decision_session`; a directly reconstructed artifact bypassed the builder-only check. | A false decision clock can admit post-open controls into a pre-open artifact and create lookahead when the fixture boundary later becomes persistent. | Moved the exact session-open equality into the frozen artifact invariant used by fit and apply. | Before correction, a direct probe printed `FORGED_CLOCK_ACCEPTED`; the new `dataclasses.replace` regression refuses the same timestamp. |
| ARV2CR8-007 | P3 | Corrected | `PreopenControlCrossSection`, fit/apply | Cross-sections did not bind the stock-evaluation spec and could be relabeled under a later contract generation. | Persisted structural evidence must retain exact contract lineage rather than acquire the consumer's current hash during fit. | Added `spec_hash` to the cross-section identity and required exact contract equality in training and application. | Rehashed cross-sections with a different valid SHA-256 refuse in both fit and apply regressions. |
| ARV2CR8-008 | P3 | Corrected | Stock-evaluation contract and application | The contract said every unseen industry refuses while implementation deliberately preserved structural-zero rows before the industry check. | Contract and executable structural behavior must agree before the run schema is built. | Clarified the frozen rule as `refuse_active_row_structural_zero_remains_exact_zero`, retaining the safer no-invented-signal behavior. | The repository contract test pins the exact rule; active unseen industries refuse and structural-zero rows remain exact zero. |
| ARV2CR8-009 | P3 | Corrected | Stock IC report definition | The same statistic was called `positive_date_share` in per-horizon inventories and `positive_share` in the general inventory. | Two names would create ambiguous report fields and lineage during ARV2-4 schema implementation. | Normalized the general inventory to `positive_date_share`. | Contract tests require the canonical name and prohibit the obsolete alias. |
| ARV2CR8-010 | P2 | Corrected | `stock_controls.py`; stock-evaluation and import-firewall tests | A copied cross-section could relabel both `decision_session` and `decision_at` to another valid NYSE open while retaining the original candidate/evidence hashes; fit then used the forged wrapper date for fold membership. | Exact-open validation alone does not prove that the wrapper session belongs to the builder-authenticated candidate/evidence, allowing future controls to be relabeled into training. | Made cross-sections process-local builder-authenticated objects under a locked weak-reference identity registry whose pinned digest is recomputed before fit/apply. Persistence and reconstruction remain unsupported until a separately reviewed loader exists. | The original direct probe printed `FORGED_SESSION_ACCEPTED`; regressions now refuse an identical copy, paired session/open relabel, wrong-spec copy, and low-level mutation of an otherwise registered object. Authentic builder outputs still fit/apply, and the authority-registry lock inventory pins the new registry. |

### 4S.3 Independent verification and remaining authority

- `37dc424` changes only this lane record; its nominal review range contains
  exactly ten commits.
- Source/spec/test corrections are committed locally as
  `33d40f1e1e0ffb9ddd26627324375d7b4eb7f7a2`; this lane-record commit follows.
  Neither commit is pushed under the current owner-decision gate.
- All six research source kinds still refuse; both zero-access declarations
  positively resolve to their exact identities; the retired outcome boundary
  refuses before its instrumented loader executes.
- QC-first upload, historical launch, paper deployment, funded live,
  evidence-authentication, and action-authority properties remain literal
  false even after every structural phase is claimed complete with bindings.
- The transitive Analyst import closure remains outcome-, network-, QC-, and
  execution-free. The two section 4R inner-guard mutations remain unreachable
  under the outer authenticated loader and are not defects.
- Corrected stock child identity:
  `arv2-stock-historical-c5ff2a6a0dcf341e` / SHA-256
  `c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b`.
- Focused pre-correction review battery: **146 passed**. The first corrected
  registry/control selection was **31 passed, 39 deselected**; after the
  cross-section identity correction, the final focused source/test/lock
  battery was **70 passed, 1 skipped in 22.78 s**.
- Exact final code/test tree on Python 3.13.14: **5,670 passed, 3 skipped,
  25 known dependency warnings in 2,228.09 s (37m08s)**. Repository compileall
  exited 0. The lane active-document gate is **63 passed**; final diff and
  branch/status checks are clean apart from Git's informational LF-to-CRLF
  checkout warnings.

ARV2-4 remains blocked. No current milestone authorizes a provider/account
audit, licensed row, normalization, upload, compile, outcome, QC job,
evaluation reservation, paper deployment, funded deployment, or order. No
ARV2-4B exists in the governing ladder. The recommended next outcome-free
candidate is a fold-manifest-only structural binding, but owner authorization
must name that bounded work before it begins. Under the serialized workflow,
this counter-review correction series is committed locally and the lane stops
before the next milestone and before push unless the owner authorizes one of
those next actions.

The owner subsequently authorized only the counter-review-only push by the
explicit instruction `push` on 2026-08-31. Section 4 and the final ledger row
supersede the push-stop condition above; ARV2-4 and every other authority gate
remain unchanged.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | V2 source reviewed; legacy/current gap measured; no implementation. | PDF text and all 64 rendered pages inspected; no outcome access; 0 looks. | V2 is a replacement, not a parameter patch. | Claude reviews the documentation baseline; implementation waits for owner instruction. |
| 2026-08-27 | Codex implementation | `a4f58e6` -> `653a9c0` (code snapshot; this lane-record commit follows) | Owner-authorized one-time common remediation synchronization | Synchronized the bounded shared-remediation series through `7029acb`, then identical final shared patch `68ae4b4` (source `6770db3`, stable patch ID `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`) and Analyst-only decimal/structural-zero hardening `653a9c0` (source `66168ed`). No other strategy implementation entered this lane. | Exact lane tree: 5,434 passed, 2 skipped, 25 dependency-deprecation warnings in 39m14s; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean; worktree clean. No provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or live scheduler access; **0 research looks**. | Independent final audits found no remaining P0-P3 issue in the synchronized diff. Synchronization is not acceptance; candidate remains zero-access and unaccepted. | Push this exact lane-recorded snapshot; Claude reviews every pushed commit on this lane, then Codex counter-reviews every Claude commit before any next milestone. |
| 2026-08-27 | Codex implementation | `d8d0ad6` -> `a8f9071` (code snapshot; this lane-record commit follows) | Owner-authorized shared portfolio-equity correction | Cherry-picked source fix `1ed0602` into `assistant/portfolio_snapshot.py` and `tests/test_assistant_risk_copilot.py`. The builder now aggregates exact Decimal cash and position values before rounding the single total-equity display, preventing legitimate fractional-share portfolios from failing the strict display/exact integrity check. The validator, policy limits, broker contracts, strategy code, and research gates were not weakened or changed. | Focused portfolio/risk/coherent-snapshot suite: 112 passed, 0 failed, 1 dependency warning in 20.25s; compileall exit 0; `git diff --check` clean. Source correction previously passed the complete 5,442-test suite and a reverse mutation that reproduced display `100.01` versus exact `100`. No provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | `SYS-FU-P1-006` reproduced: per-position display rounding accumulated into a competing equity total and prevented UI load. Corrected without adding tolerance; pending Claude review and Codex counter-review. | Validate and push the exact recorded lane snapshot. Claude then reviews both new commits on this lane before any later milestone. |
| 2026-08-27 | Codex validation | `c167574` -> `c167574` (exact isolated tested snapshot; this validation-record commit follows) | Portfolio-equity correction final validation | Revalidated the complete Analyst Revisions V2 lane after its code and required lane-record commits in a detached isolated worktree pinned to `c167574`; no product file changed during the run. | Complete exact-tree suite: **5,435 passed, 2 skipped, 0 failed, 25 dependency warnings in 2,017.42s (33m37s)**. The earlier focused 112-test suite, 63-test active-document suite, compileall, and diff checks were also green. Fixture-only; no provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | No new P0-P3 finding. `SYS-FU-P1-006` remains implemented but unaccepted pending the required review chain; all Analyst source/outcome gates remain zero-access. | Commit this validation record and push the complete three-commit lane range; Claude reviews every new commit before any later milestone. |
| 2026-08-27 | Claude review | `5a5c7ab` -> `48a8b08` (this lane-record commit follows) | Independent review of the owner-authorized remediation synchronization | Reviewed all 21 commits in `a4f58e6^..5a5c7ab` with an explicit disposition each; none rejected. The owner-specified range ended at `d8d0ad6`, but the lane advanced to `5a5c7ab` during the review (clean `pull --ff-only`, reflog verified), so scope was deliberately extended rather than allowed to drift; `research/analyst_revisions_v2/`, `data/exchange_calendar.py`, `assistant/temporal_integrity.py`, `execution/broker_contract.py` and `assistant/dispatch_fence.py` are byte-identical across that extension. Corrected CLR-001 in `tests/test_ml_evidence_operations.py`; added `docs/Archive/Review/REVIEW_2026-08-27_ARV2_LANE_REMEDIATION_SYNC.md`. No production file was changed. | Exact committed tree `48a8b08`: **5,434 passed, 0 failed, 3 skipped, 25 known warnings in 1,403s**; compileall exit 0; `git diff --check` clean. As received at `d8d0ad6`: 5,433 passed, 1 failed, 2 skipped (that failure was CLR-001, interpreter-provenance dependent, now corrected). Independently reproduced rather than accepted: the outcome loader never executes, all six research source kinds refuse, forged permit and self-consistent forged policy objects are rejected, the ETF `N_eff` and institution/catalyst independence errata return their hand-computed values, every event-timing boundary including exactly-at-open is correct, and the transitive import closure reaches 21 modules with zero execution-capable roots. Five safety invariants were mutation-tested in a pinned throwaway worktree and each turned the suite red (6, 16, 1, 1 and 1 failures). 17/17 synchronized commits are patch-identical to their `main` sources. Data sources: none; no provider, credential, licensed row, broker, operator-database, QuantConnect or scheduler access. **0 research looks; no permanent look identifier consumed.** | 0 P0, 0 P1, 3 P2, 6 P3. CLR-001 corrected and verified red/green across two interpreters. One proposed P1 (cancel-all fence timeout) was downgraded to P2 after confirming it records a durable critical incident instead of reporting success. CLR-002/003/004 are shared-execution items with mitigations, not lane regressions; six files flagged by deeper sweeps were confirmed untouched by this range and are pre-existing. The ARV2 lane-owned research layer yielded no defects; CLR-009 is a self-found locking-consistency note with no demonstrable exploit. Disposition: **accepted after correction**; synchronization remains not acceptance. | Codex counter-reviews this exact pushed head including the CLR-001 correction, and disposes CLR-002 through CLR-009 - several belong to the shared remediation owner rather than this lane. Owner decisions, a reviewed spec anchor, governed source admission and an external append-only permanent-look authority all remain open before any production normalization, outcome join, ETF construction or QC run. |
| 2026-08-27 | Codex counter-review | `bd3393d` -> this commit | Counter-review both pushed Claude commits and complete the inherited correction set on this one lane | Stayed on `codex/strategy-analyst-revisions-v2` in the dedicated worktree. Accepted `48a8b08` and `bd3393d`; independently reviewed every inherited correction. Retained CLR-002/004/006/007/008 and CLR-009 production locking, fixed exact-fill retry/legacy compatibility and lock-test sensitivity, and rejected/reverted the unsupported CLR-003 180 s delay. Consolidated the separate report into this required branch-specific record and removed the duplicate live copy. | Focused final-tree suite: **334 passed, 1 skipped, 1 known dependency warning in 351.68 s**; isolated new regressions: **9 passed in 10.65 s**. Exact full-tree result and compile/diff evidence are recorded before commit. No provider, credential, licensed row, outcome, broker, operator database, QuantConnect, scheduler, or order access; **0 research looks**. | 0 P0, 0 P1, 2 P2, 1 P3 in the proposed correction set: ARV2CR-001 and ARV2CR-003 corrected; ARV2CR-002 caused the attempted fix to be reverted and CLR-003 to remain explicitly open. The existing candidate is accepted after correction. | ARV2-0 is the next milestone but is blocked by eight owner decisions plus empty reviewed-spec/source/look authorities. Per the same-branch workflow, stop before ARV2-1 and before push; commit the counter-review locally and request owner direction. |
| 2026-08-27 | Codex push authorization | `7f493d1` -> this record commit | Owner-directed counter-review-only push | After Codex reported the ARV2-0 owner-decision blocker and the normal stop-before-push consequence, the owner explicitly instructed: `push`. This is recorded as a narrow exception for the completed counter-review series only; no next-milestone implementation was added. | Documentation-only update after the exact counter-review validation above; final active-document gate and diff check rerun before commit. No provider, credential, licensed row, outcome, broker, operator database, QuantConnect, scheduler, or order access; **0 research looks**. | No new P0-P3 finding. CLR-003 remains open; all eight ARV2-0 owner-decision cells and all zero-access authorities remain unchanged. | Push the exact two-commit local range once. Remain stopped before ARV2-1 pending the recorded owner decisions and authority gates. |
| 2026-08-28 | Codex implementation | `c83782d` -> this commit | ARV2-0 owner-decision freeze candidate | Resolved all eight owner-decision cells under the owner's risk/profit direction; added the all-history plus objective/named-regime evaluation contract; made the candidate content-addressed; split frozen source policy from still-null external evidence; froze one stock-primary cell and one planned, unbound permanent look. Extended universe and normalization schemas to encode the exact owner choices rather than vague fallback text. No branch was created or switched. | Final exact worktree: **5,453 passed, 3 skipped, 0 failed, 25 known dependency warnings in 1,974.84s (32m54s)**; final focused preregistration file **35 passed**; repository compileall exit 0; final active-document and diff/status gates recorded immediately before commit. No credential, provider row, licensed artifact, price, return, outcome, broker, operator database, QuantConnect job, scheduler, or order access; **0 research looks and no permanent look consumed**. | 0 new P0-P3 findings. One broad-suite failure was only a stale expected error-message substring after the multiplicity guard was strengthened; the diagnostic was corrected and the exact full tree passed. Candidate remains unreviewed and zero-access. | Push this one bounded commit to the existing lane. Claude independently reviews the exact pushed snapshot and pushes its disposition/corrections on this branch. Codex then counter-reviews every Claude commit before ARV2-1 or any source audit/outcome work. |
| 2026-08-28 | Claude review | `b912459` -> this commit | Independent review of the counter-review push and the ARV2-0 owner-decision freeze | Reviewed all three commits in `bd3393d..b912459` with an explicit disposition each (section 4C): counter-review `7f493d1` accepted, including independent confirmation that rejecting my CLR-003 attempt was correct; push record `c83782d` accepted; freeze `b912459` accepted after correction. Verified my six inherited corrections entered byte-identical and that Codex's two modifications (journal retry compatibility, AST lock audit) are genuine improvements. Ran the candidate loader directly; nine correctly re-hashed weakening attempts all refused on semantic pins; the reviewed-spec path refuses the candidate; the complete zero-access probe is unchanged. Corrected two guard-test sensitivity gaps (ARV2R2-001/002) with seven single-violation regression cases in `tests/test_analyst_revisions_v2_preregistration.py`; no production file changed. Stayed on this one lane branch; single combined push. | As-received `b912459`: full suite **5,453 passed, 3 skipped, 0 failed, 25 known warnings in 2,174.92s**, exactly reproducing the freeze row's claim. Final code tree with the new tests: full-suite result in this push's commit message; focused battery 469 passed, 1 skipped; preregistration file 42 passed; both mutations now turn the new tests red and the restored tree is green; compileall exit 0; `git diff --check` clean. No provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect or scheduler access. **0 research looks.** | 0 P0, 0 P1, 0 P2, 2 P3 - both corrected and mutation-verified. The production guards were never absent (the tamper probe refused both weakenings); the gaps were test sensitivity only. CLR-003 remains open in shared execution code with the loud incomplete-containment behavior as the interim. | Codex counter-reviews this exact pushed head before accepting ARV2-0 or combining that disposition with the next authorized bounded milestone. ARV2-1, source admission, review anchoring and any outcome authority remain gated as recorded in sections 3A/4/4B. |
| 2026-08-28 | Codex counter-review and implementation | `1507777` -> this commit (`31c313e` is the separate counter-review record) | Accept Claude ARV2-0 corrections; implement ARV2-1 structural ingest/ontology candidate | Accepted Claude's one review commit after focused and reverse-mutation reproduction, then added capture chronology, the content-addressed Massive/Benzinga structural contract, exhaustive ingest/refusal and snapshot-version lineage, loader-authenticated firm-specific exact rational scales, non-inferential vocabulary inventory, source-audit-bound firm normalization, and permanent-identity daily dedupe. Stayed in the dedicated worktree and branch; no other strategy or frozen shared document changed. | Exact full tree: **5,501 passed, 3 skipped, 0 failed, 25 known warnings in 2,922.06 s (48m42s)**; final focused ARV2-1/capture/authority battery **40 passed in 5.75 s**; lane-document gate **63 passed**; compileall exit 0; exact-label reverse mutation **1 failed** and restored green; final diff/status gates run before commit/push. Public documentation and synthetic/anonymized documented-shape fixtures only. No credential, licensed row, price, return, outcome, broker, operator database, QuantConnect job, scheduler, or order access; **0 research looks and no permanent look consumed**. | Claude `1507777`: accepted, 0 new P0-P3. ARV2-1 self-review: ARV2I-001/002 P2 and ARV2I-003/004 P3 corrected; no unresolved P0-P3. Production source, reviewed ontology, permanent identities, rational canonical publication, outcome/look, QC, and execution authorities remain closed. | Commit the ARV2-1 code and this record separately from `31c313e`, verify the exact two-commit range, and push once. Claude independently reviews both commits on this same branch; Codex counter-reviews before ARV2-2. |
| 2026-08-28 | Claude review | `6f23244` -> this commit | Independent review of the ARV2-0 counter-review and the ARV2-1 ratings-ingest/ontology candidate | Reviewed both commits in `1507777..6f23244` with an explicit disposition each (section 4F): counter-review `31c313e` accepted, ARV2-1 `6f23244` accepted after correction. Read both new modules in full. Independently recomputed the provider-contract hash (matches the module and the 4E claim), reproduced the blueprint scale goldens as exact Fractions, verified exactly-once dispositions, duplicate-ID refusals, chronology-bound lineage with missing-not-withdrawal semantics, and the identity-only dedupe contract. Executed the transitive import firewall directly: 23 modules reached, zero network or execution-capable roots. Ran a five-guard mutation matrix in a detached scratch worktree so the concurrent full-suite run could not be contaminated: four guards bit, one survived and became ARV2R3-001, corrected with an upgrade-branch direction regression (including the zero-change-via-reviewed-alias case) and re-mutation-verified red/green. ARV2R3-002 records the ontology authority-registry asymmetry as open by design with its closure point named. No production file changed. Stayed on this one lane branch; single combined push. | As-received `6f23244` full suite and final-tree full suite results recorded in this push's commit message; focused ARV2 battery **229 passed in 368s**; ingest/ontology file **39 passed** after the new regression; active-document gate **63 passed**; compileall exit 0; `git diff --check` clean. No provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect or scheduler access. **0 research looks.** | 0 P0, 0 P1, 0 P2, 2 P3: ARV2R3-001 corrected and mutation-verified; ARV2R3-002 open by design pending the production ontology catalog. The upgrade-side gate was present and working in production code; the gap was test sensitivity only, the same single-violation-per-guard class as ARV2R2-001. | Codex counter-reviews this exact pushed head before accepting ARV2-1 or starting ARV2-2 (PIT issuer/security master). External source bindings, the reviewed spec anchor, the ontology production catalog and the permanent-look authority all remain zero-access. |
| 2026-08-29 | Codex counter-review and implementation | `31a2b64` -> this commit (`0fb7998` is the separate counter-review record) | Accept Claude's ARV2-1 review; implement the ARV2-2 structural PIT identity and outcome-prerequisite candidate | Accepted Claude's exact review commit after independent reading, focused tests, and two reverse mutations. Added loader-reauthenticated permanent issuer/security/share-class identity, PIT identifier/listing intervals with closure availability, historical-ticker resolution, symbol/listing/merger/delisting lineage, exhaustive mapping/refusal coverage, exact firm/identity joins, terminal-return requirement inventory, and empty Git-anchored production ontology/security-master registries. Recorded the owner's 2026-08-29 restriction of this lane to ARV2 strategy/QC work, excluding Trading App/Streamlit work. Stayed in this dedicated worktree and branch; no shared/frozen document changed. | Final focused battery **40 passed, 1 skipped in 2.19 s**; complete Analyst V2 battery **268 passed, 1 skipped in 69.63 s**; exact full tree **5,541 passed, 3 skipped, 0 failed, 26 known dependency warnings in 1,140.84 s (19m00s)**; independent code audit **114 passed, 1 skipped in 42.11 s**; **13/13** dangerous mutations killed; independent compileall passed; **63/63 active-document assertions passed**; final diff/status gates run before commit/push. Fixtures only. No credential, provider row, licensed artifact, price, return, outcome, broker, operator database, QC job, scheduler, or order access; **0 research looks and no permanent look consumed**. | Claude `31a2b64`: accepted, 0 new P0-P3. ARV2-2 self/independent review: ARV2I2-001 through ARV2I2-007 corrected; 0 unresolved P0-P3. `ARV2R3-002` is closed by an empty production ontology registry. All real source, identity, ontology, outcome, look, QC, and execution authorities remain closed. | Commit ARV2-2 separately from `0fb7998`, verify the exact two-commit range, and push once. Claude independently reviews both commits on this same branch; Codex counter-reviews before ARV2-3. |
| 2026-08-29 | Claude review | `56d6fe0` -> this commit | Independent review of the ARV2-1 counter-review and the ARV2-2 PIT identity candidate | Reviewed both commits in `31a2b64..56d6fe0` with an explicit disposition each (section 4I): `0fb7998` accepted, `56d6fe0` accepted after correction. Read `security_master.py` (2,143 lines), `production_registry.py` and the `firm_ontology.py` production gate in full. Confirmed `ARV2R3-002` is genuinely closed and that its positive registry path is not vacuous. Applied the owner's 2026-08-29 lane-purpose instruction: every correction is inside `research/analyst_revisions_v2/`, its committed artifacts or its tests; the one out-of-purpose observation is documented, not fixed. Corrected ARV2R4-001 (P2) by adding a lane-scoped `specs/.gitattributes`; corrected ARV2R4-002/003/004 with guard regressions. No production module was modified. Stayed on this one lane branch; single combined push. | As-received `56d6fe0` on this Windows host: **5,539 passed, 1 failed, 4 skipped, 25 warnings in 1,782.71s** - the failure is ARV2R4-001, and the skip count reconciles against the other machine's 3 via the earlier `CLR-001` interpreter skip. Final-tree full-suite result is in this push's commit message. Focused: security master **41 passed, 1 symlink skip**; dataset/import firewall **39 passed**; active-document gate **63 passed**. Mutation matrix in a detached scratch worktree at `56d6fe0`: eligibility (country/exchange/type) and combined-join precedence bit; listing-closure lineage, coverage arithmetic and coverage refusal-sum survived and are now pinned; every new test verified red/green. compileall exit 0; `git diff --check` clean. No provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect or scheduler access. **0 research looks.** | 0 P0, 0 P1, 1 P2, 3 P3 corrected, 1 P3 documented. ARV2R4-001 is the notable one: with no `.gitattributes` and `core.autocrlf=true`, every committed zero-access artifact checked out as CRLF, so the production-gate test failed on the owner's own platform, the source-authority declaration was never actually verified here, and a legitimately registered artifact could never have been accepted on Windows. Fail-closed throughout, hence P2. ARV2R4-005 records that the successor-cycle detector is unreachable rather than untested, with the algebraic reason. | Codex counter-reviews this exact pushed head before accepting ARV2-2 or starting the next bounded milestone. A root-level `.gitattributes` for the other two lanes is flagged in 4I.5 as an owner-coordinated common-baseline decision, deliberately not made here. All production authorities remain zero-access. |
| 2026-08-29 | Codex counter-review | `f592334` -> this commit | Accept Claude's ARV2-2 review after correcting its existing-worktree migration | Reviewed Claude's exact one-commit push and independently accepted its security-master guard tests. Reproduced that `.gitattributes` alone leaves unchanged CRLF files in a normally fast-forwarded Windows worktree, narrowed the exact-byte contract to its three real consumers, and gave those empty registries a schema-v2 blob migration. The owner clarified that eventual live trading through QC is a valid post-gate destination, while UI remains out of scope and no current QC/live authority exists. Stayed on this branch/worktree and touched only ARV2 code, artifacts, tests, and this lane record. | As received: **78 passed, 2 failed, 1 skipped** in the focused selection; the two EOL/authority failures were isolated directly. Corrected selection: all 87 nodes reached 100% with one host symlink skip; exact critical guards pass directly; three canonical registries are LF-only; `git diff --check` clean. The exact combined final-tree suite follows with ARV2-3 before the one push. No credential, provider row, licensed artifact, outcome, QC job, broker, operator database, scheduler, order, UI, or Streamlit access; **0 research looks**. | `f592334` accepted after correction: ARV2CR5-001 P2 and ARV2CR5-002 P3 corrected; no unresolved P0-P3. The clarified eventual-QC-live destination is not a finding. Unrelated findings remain document-only by owner instruction. | Commit this counter-review separately, then implement the single bounded ARV2-3 structural stock-score milestone. Validate both commits and push the combined range once for Claude's next review. |
| 2026-08-29 | Codex implementation | `f592334` -> this commit (`a597ac3` is the separate counter-review commit) | ARV2-3 structural canonical stock-score candidate and isolated diagnostics | Implemented exact stock decay/reliability, source-derived NYSE ages, dedupe/raw aggregation, absolute-mass institution/catalyst breadth, activity-aware sector MAD normalization, strict structural evidence timing/refusals, ARV2-2 universe/source-chain revalidation, and separately revalidated diagnostics. The fixture-only candidate remains blocked at unspecified mandatory control residualization and can never become executable from this milestone. Preserved reviewed inclusive security-master PIT semantics while requiring new ARV2-3 evidence strictly before the decision open. Added one shared session-age index/decay cache. Stayed in the dedicated worktree and touched only Analyst V2 code, tests, and this lane record. | Focused stock-score file **55 passed in 44.35 s**; complete Analyst V2 battery **328 passed, 1 host symlink skip in 106.54 s**; exact repository code tree **5,601 passed, 3 skipped, 0 failed, 26 known warnings in 1,307.06 s**; active-document **63 passed in 1.17 s after the final record row with only the non-semantic cache provider disabled for ARV2ENV-001**; changed-file `py_compile`, transitive 26-module outcome/QC firewall, and `git diff --check` pass. Three independent audits ended clean; session-age equivalence matched 2,173 ages. Synthetic fixtures only. No provider/QC credential, licensed row, price, return, outcome, broker, operator database, QC job, scheduler, order, UI, or Streamlit access; **0 research looks and no permanent look consumed**. | ARV2I3-001 through ARV2I3-004 P2 and ARV2I3-005/006 P3 corrected; 0 unresolved P0-P3. No unrelated issue was changed; ARV2ENV-001 is documented without a repository change. ARV2-3 remains unaccepted, structural-only, non-executable, and zero-authority. | Commit ARV2-3 and this required record separately from `a597ac3`, verify the exact two-commit local range and clean worktree, then push once. Claude independently reviews every pushed commit on this same branch; Codex counter-reviews before ARV2-4 or any source/outcome/QC step. |
| 2026-08-29 | Claude review | `8701880` -> this commit | Independent review of the ARV2-2 counter-review and the ARV2-3 structural stock-score candidate | Reviewed both commits in `f592334..8701880` with an explicit disposition each (section 4L): `a597ac3` accepted after correction, `8701880` accepted after correction. Read `stock_signal.py` (1,779 lines) in full plus the `formulas.py` diff. Reproduced the decay, reliability and MAD goldens by independent formulations, and confirmed the 26-module transitive closure reaches no execution, ML, network or legacy-ACER module. Ran a 14-mutation matrix in a detached scratch worktree aimed at guards the implementation's own list does not claim to pin: 7 killed, 7 survived, 4 corrected and 2 documented. Applied the owner's lane-scope rule: every correction is a test in `tests/analyst_revisions_v2/`; no production module changed. Stayed on this one lane branch; single combined push. | As received `8701880`: **5601 passed, 3 skipped, 25 warnings in 1068.06s (0:17:48)**. Final tree with the new regressions: **5604 passed, 3 skipped, 25 warnings in 1068.48s (0:17:48)**. Focused: stock signal 55 as received then **58 passed**; dataset/import firewall **39 passed**; active-document **63 passed**. Every new guard verified red under reverse mutation and green restored. Python 3.12.13. Fixtures only; no provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect, scheduler or order access; **0 research looks and no permanent look consumed.** | 0 P0, 0 P1, 1 P2, 3 P3 corrected, 1 P3 documented. ARV2R5-001 (P2): ARV2CR5-001's schema-v2 migration refreshed three of the seven artifacts `*.json -text` governs, so four spec artifacts sat CRLF against LF blobs in this lane checkout while `git status` reported clean via the stat cache; that state makes `_review_anchor`'s committed-and-clean precondition refuse the first reviewed-spec registration and risks committing CRLF into content-addressed artifacts. Working files repaired from their existing LF blobs with no committed content change. ARV2R5-002/003/004 pin the no-hard-cutoff decay beyond age 120, the identity-refusal exemption set's actual use, and the frozen candidate authority/residualization/no-partial guards. ARV2R5-005 records two deliberately unpinned redundancy properties. | Codex counter-reviews this exact pushed head before accepting ARV2-3 or starting ARV2-4. Whether the remaining four spec artifacts should receive a blob-level refresh, and whether the blocked mandatory-control residualization needs an owner decision before ARV2-4, are named in 4L.5. All production source, ontology, identity, outcome, look and QC authorities remain zero-access. |
| 2026-08-30 | Codex counter-review | `12157dd` -> this commit | Accept Claude's ARV2-3 review after correcting its tests and canonical handoff | Counter-reviewed both Claude commits `6e8edab` and `12157dd` under the repository workflow and the strategy PDF. Accepted each after correction. Replaced unsafe EOL remediation, strengthened the long-decay and partial-artifact regressions, pinned the effective Git EOL rule, corrected the stale handoff and mutation arithmetic, and made the mandatory-control/event-study decision a hard pre-look gate. Stayed in the dedicated branch/worktree and touched only two Analyst V2 test files plus this lane record; no production module changed. | Corrected focused files: **58 passed in 36.71 s** and **39 passed in 43.52 s**; complete Analyst V2 battery **331 passed, 1 host symlink skip in 104.79 s**; exact repository code tree **5,604 passed, 3 skipped, 25 known warnings in 923.36 s (15m23s)**; final active-document gate **63 passed**; compileall exit 0; final diff/status gates run before local commit. No credential, provider row, licensed artifact, price, return, outcome, broker, operator database, QC job, scheduler, order, UI, or Streamlit access; **0 research looks and no permanent look consumed**. | `6e8edab` and `12157dd` accepted after correction. ARV2CR6-001/005/006 are P2; ARV2CR6-002/003/004/007 are P3; all corrected, 0 unresolved P0-P3. ARV2-3 is accepted but remains structural, non-executable, and zero-production-authority. ARV2-4 remains blocked by the decisions and authorities in section 4. | Commit this counter-review locally only and stop before ARV2-4 and before push. Owner must first freeze the executable mandatory-control and primary event-study contracts; later source/rights/review/time/look/QC gates remain separately required. Do not request pasted credentials. |
| 2026-08-30 | Codex implementation | `9309de3` -> this commit | ARV2-3Q owner-frozen QC-first planning candidate | Implemented content-addressed amendment `arv2-qc-first-plan-9574bf824e9b9735`, authenticated its exact retired predecessor, permanently disabled the legacy-v1 outcome path, separated historical development screens from the sole future paper look, froze stock/event-study constraints and explicit null pre-run definition hashes, staged source/upload/compile/evaluation authorities, and machine-gated future paper/funded states. Stayed on the one Analyst lane branch/worktree; no UI or unrelated strategy work. | Exact repository tree **5,626 passed, 3 skipped, 0 failed, 25 known warnings in 1,091.35 s (18m11s)**; complete Analyst V2 battery **352 passed, 1 host symlink skip in 96.25 s**; final plan/document gate rerun after the hash settled; compileall and final diff/status gates run before commit. Three independent audits ended with 0 unresolved P0-P3. Synthetic/outcome-free planning only: no credential, licensed row, price, return, outcome, QC upload/compile/job, deployment, broker, scheduler, or order; **0 development evaluations and 0 permanent looks consumed**. | ARV2Q-001 P1 and ARV2Q-002 through ARV2Q-006 P2 corrected; all later statistical, authority, state-accounting, reporting, test-sensitivity, and documentation findings corrected. The amendment is unreviewed and planning-only; all action capabilities remain false. | Commit ARV2-3Q separately from `9309de3`, verify the exact two-commit local range, and push once. Claude independently reviews both commits on this same branch. Codex counter-reviews before materializing the full V2 evaluation schema or performing any provider/outcome/QC action. |
| 2026-08-30 | Claude review | `f724bf9` -> this commit | Independent review of the ARV2-3 counter-review and the ARV2-3Q QC-first planning candidate | Reviewed both commits in `12157dd..f724bf9` with an explicit disposition each (section 4O): `9309de3` accepted after correction, `f724bf9` accepted after correction. Reproduced the plan identity recipe, the retired-look tombstone refusal, the four constant-false capabilities and the four horizon maturity dates first-hand. Pinned two untested authority-boundary guards, closed a stated no-binary-float hole, and restored deleted positive-path coverage. Stayed on this one lane branch; single push. | As received `f724bf9`: **5,626 passed, 3 skipped**, reproducing the implementation claim exactly. Final tree: **5,635 passed, 3 skipped, 0 failed in 1,054.82 s** - a delta of exactly the nine new nodes. Focused: QC-first plan **28 passed**, preregistration **45 passed**, dataset/import firewall **39 passed**, Analyst V2 battery **347 passed, 1 skipped**, active-document **63 passed**. Ten reverse mutations all red then green. compileall exit 0; `git diff --check` clean; Python 3.12.13. Synthetic fixtures only; no credential, provider row, licensed artifact, price, return, outcome, QC job, upload, deployment, broker, scheduler or order access; **0 research looks and 0 development evaluations consumed.** | 0 P0, 0 P1, 2 P2, 8 P3 corrected; 5 P3 documented; 1 false alarm closed. ARV2R6-001 and ARV2R6-002 are the P2s: the superseded-period refusal and the plan authority/schema/status pins each worked but had no test, so either could be deleted with the suite green - a forged plan asserting action authority authenticates once the authority pin is gone. ARV2R6-003 closes the NaN/Infinity `parse_constant` hole (verified unexploitable at all 151 contract fields). ARV2R6-007 closed as a false alarm after reproduction. ARV2R6-008/011/012 raise owner-decision items: the phased state machine is declarative data no code enforces, the `owner_frozen` label is broader than the recorded sequencing decision, and the inherited industry tier has no stage in the new ladder. | Codex counter-reviews this exact pushed head before accepting ARV2-3Q or starting ARV2-4. ARV2-4 remains blocked on the reviewed spec anchor, audited production inputs, vendor-to-QC processing rights, external evaluation/look authorities and explicit owner run authority. |
| 2026-08-30 | Codex counter-review | `f724bf9` -> this commit | Accept Claude's ARV2-3Q review after correction | Counter-reviewed Claude commits `39104f6` and `f2c15d8` under the PDF and repository workflow. Retained the valid parser/guard work; completed duplicate/non-finite coverage; corrected stale canonical status, global-map and industry-topology gaps, provenance, structural phase validation, horizon maturity, path/TOCTOU authentication, and the review-ledger mismatch. Stayed on this branch/worktree and touched only Analyst V2 code, artifacts, tests, and this record. | Counter-review-only battery **119 passed in 70.15 s**. No credential, licensed row, price, return, outcome, QC upload/compile/job, deployment, broker, scheduler, or order; **0 research looks and 0 development evaluations**. | `39104f6` and `f2c15d8` accepted after correction; ARV2CR7-001 through ARV2CR7-009 corrected; 0 unresolved P0-P3. | Commit this counter-review separately, then implement exactly ARV2-4A outcome-free structural prerequisites. Validate both and make one combined push for Claude's next review. |
| 2026-08-30 | Codex implementation | `e53ba26` -> this commit | ARV2-4A outcome-free structural evaluation prerequisite | Added the canonical child stock-evaluation contract, exact PDF/parent analysis and reporting structure, strict canonical/provenance loader, fixture-only same-date control transforms, training-only Decimal QR, exact per-horizon fold gaps, policy/fold/model lineage, named refusals/coverage, held-out application goldens, and a result-free report plan. Stayed on the dedicated Analyst branch/worktree; no UI, Streamlit, another strategy, shared/frozen project document, source, or executor work. | Focused ARV2-4A **27 passed**; combined counter-review/ARV2-4A **146 passed**; complete Analyst V2 **396 passed, 1 host skip**; exact repository tree **5,669 passed, 3 skipped, 0 failed, 25 known warnings in 893.21 s**; two independent audits end at 0 P0-P2. Compile, document, diff, status, and exact commit-range gates rerun before the one push. No credential, provider row, licensed artifact, price, return, outcome, QC upload/compile/job, deployment, broker, scheduler, or order; **0 research looks and 0 development evaluations**. | All implementation-audit P0-P2 findings corrected; none unresolved. Source/global-map/fold/power/economic/registry/result/QC/deployment bindings remain null and capabilities false. ARV2-4A is a structural candidate, not an evaluation. | Commit separately from `e53ba26`, validate the exact combined tree, then push exactly once. Claude independently reviews both commits; Codex counter-reviews before any next milestone. |
| 2026-08-30 | Claude review | `c334571` -> this commit | Independent review of ARV2-3, ARV2-3Q and ARV2-4A | Reviewed all ten commits in `f592334..c334571` with an explicit disposition each (section 4R). **Accepted with no correction required** - the first round in this lane where I found nothing to fix; no code or test was changed, only this record. Read `stock_signal.py`, `qc_first_plan.py`, `stock_controls.py` and `stock_evaluation_contract.py`, and verified the QC-first resequencing in detail: the superseded ARV2-0 look was genuinely unbound and unspent and its loader now refuses revival, the multiplicity model applies 1/60 to the single prospective look under three-lane Bonferroni, historical QC work is explicitly non-confirmatory, stock-first survives in the frozen gatekeeping order, and the underpowered-paper-confirmation critique is pre-empted by `target_only_not_a_power_claim` plus a mandatory pre-observation power plan and uninspected retirement of an insufficient look. | As-received `c334571`: **5,668 passed, 4 skipped, 0 failed, 25 known warnings in 2,227.73s**; because this review changes no code, that run is also the final-tree code validation. Focused: ARV2 directory 292 passed/1 skipped; QC-first 34 passed; evaluation+controls 27 passed; stock signal 58 passed; active-document gate rerun before commit. Adversarial probe: all six source kinds refuse, outcome loader never fires, both zero-access declarations verify positively, QC-first capabilities stay constant false even with every authority phase claimed complete and fully bound, out-of-order/premature/tampered plans refuse, import closure 29 modules with zero forbidden roots. Mutation matrix killed 5 of 7; the 2 survivors are proven unreachable. `git diff --check` clean. No provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect or scheduler access. **0 research looks.** | 0 P0, 0 P1, 0 P2, 0 P3. Two observations recorded, neither a defect: ARV2R5-001 shows two `stock_controls._require_contract` guards are unreachable rather than untested, demonstrated by showing the loader refuses both violations at load, so no fabricated regression was added; ARV2R5-002 notes that two different Claude sessions are now reviewing this lane (Opus 5 produced 4L/4O, this Fable 5 session produced 4I and 4R), which commit trailers distinguish cleanly, but the workflow specifies one dedicated Claude review session per lane. | Codex counter-reviews this exact pushed head. ARV2-4 remains blocked by the source, rights, review, run-identity and one-use authority gates; every executable definition hash is null, so stock execution, upload, QC launch, paper deployment and funded live are all constant false. The two-reviewer coordination question in ARV2R5-002 is for the owner. |
| 2026-08-31 | Codex counter-review push authorization | `37dc424` -> `3aedfff` (counter-review series; this authorization-record commit follows) | Accept Claude's review after correction; owner-authorized counter-review-only push | Counter-reviewed Claude commit `37dc424` commit-by-commit and cumulatively, corrected the inherited production-registration authority gap and ARV2-4A clock, contract-lineage, fold-lineage, and reporting defects, added dangerous-direction regressions, reconciled the historical review ledger, and committed code/tests as `33d40f1` plus the counter-review record as `3aedfff`. After Codex reported that no next bounded milestone or push was authorized, the owner explicitly instructed `push`; this row records that narrow exception only. | Exact corrected code/test tree on Python 3.13.14: **5,670 passed, 3 skipped, 0 failed, 25 known dependency warnings in 2,228.09 s (37m08s)**; final focused battery **70 passed, 1 skipped**; active-document gate **63 passed**; compileall exit 0; final diff/status and remote-head gates clean. No credential, provider row, licensed artifact, price, return, outcome, QC upload/compile/job, deployment, broker, operator database, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | 0 P0, 0 P1, 5 P2, 5 P3; ARV2CR8-001 through ARV2CR8-010 all corrected. Three independent final audits found no remaining P0-P3 issue. The corrected ARV2-4A hash remains pending the next independent review; every production/QC/action capability remains false. | Commit this authorization record and push the exact three-commit range once. Claude independently reviews the pushed correction series on this same branch. Do not start ARV2-4 or the recommended fold-manifest-only candidate without separate owner authorization. |
| 2026-08-31 | Codex main-sync integration and push authorization | `c16f7f4` -> `43224495` (reviewed integration and local-application records; this authorization record follows) | Resolve project-wide `main` conflicts without weakening Analyst ownership | Integrated exact `origin/main@1a5264e` through reviewed merge `4ef736b`, preserved lane-owned ARV2 work and compatible regression unions, corrected `ARV2-MRG-001`, and fast-forwarded the clean long-lived local lane. After Codex reported the exact clean local head and that nothing had been pushed, the owner explicitly instructed `push`; this row records that authorization for this completed integration only. | Exact resolved tree: **5,953 passed, 3 skipped, 0 failed, 26 warnings**; Analyst-focused **408 passed, 1 skipped**; reconciliation-focused **103 passed**; active-document gate after local application **67 passed**; compileall and applicable diff/status gates passed. No provider, outcome, QC, broker, deployment, order, or trading access; **0 research looks**. | `ARV2-MRG-001` P2 corrected; no open P0-P3 in the reviewed integration. ARV2-4 and all source/outcome/action gates remain blocked. | Commit this authorization record, re-fetch and require the recorded remote tips to remain exact ancestors, then push this one long-lived lane once. Independent review of the exact pushed snapshot follows before any later milestone. |
| 2026-08-31 | Codex corrective post-push main sync | `7a7757a2` -> this merge | Remove the remaining PR conflict after `main` advanced | After the atomic lane push, `main` advanced from `1a5264e6` to `19ae3f9f` by merging the Insider, Short Interest, and Target Price PRs. The owner reported that one conflict remained. A four-lane merge simulation found only this Analyst lane conflicted, in shared `tests/test_ml_evidence_operations.py`; the exact stronger `main` blob was selected because it supersedes the lane's older skip-only Store-alias workaround. This corrective merge completes the previously authorized conflict-free PR outcome; it grants no new milestone or action authority. | Conflict file **57 passed**. Pre-commit full tree reached **6,789 passed, 13 skipped** with one expected commit-state failure: a Target Price exact-byte test reads `HEAD`, where newly staged merge files cannot exist until the merge commit is created. The exact committed-tree rerun follows this record. No provider, outcome, QC, broker, deployment, order, or trading access; **0 research looks**. | No new P0-P3 code finding. Main's resolver preserves a real virtual-environment launcher, resolves only an invalid Store alias to the running process image, and directly tests zero-byte and reparse-only refusals. | Commit this merge, rerun the complete exact committed tree and document gates, re-fetch, then push the corrective Analyst update once if green. Independent review of the new exact pushed head remains required. |
| 2026-08-31 | Owner corrective-push authorization | `d9b05eb6` -> `64ccf252` (tested merge plus validation record; this authorization record follows) | Publish the conflict-free Analyst follow-up | After Codex reported the exact local and remote heads, complete-suite evidence, clean worktree, and conflict-free merge simulation, the owner explicitly instructed `push`. This authorizes one corrective push to the existing Analyst lane only. | Exact committed tree **6,790 passed, 13 skipped, 0 failed**; conflict file **57 passed**; active-document gate **69 passed**; compileall, diff, ancestry, clean-status, and merge-tree gates passed. No provider, outcome, QC, broker, deployment, order, or trading access; **0 research looks**. | No open P0-P3 finding in the corrective merge. ARV2-4 remains blocked. | Commit this authorization record, re-fetch and require exact `main@19ae3f9f` and remote Analyst head `7a7757a2`, then push once. Independent review of the exact pushed snapshot follows. |
| 2026-08-31 | Claude review | `cf136e25` -> this commit | Independent review of the ARV2-4A counter-review corrections and the project-wide main synchronization | Reviewed all eleven commits in `37dc424f..cf136e25` with an explicit disposition each (section 7). Verified by bytes that the analyst research tree is identical from pre-merge lane head `c16f7f40` to final `cf136e25`, that the single corrective-merge conflict resolved to exact main blob `be5ad791`, and that every earlier review regression survives. Mutation-verified three section 4S guards red/green; the fourth survivor is unreachable defense-in-depth (ARV2R8-001), documented not forced. No code or test change was required; this record is the only change. | Exact final tree `cf136e25`: **6790 passed, 13 skipped, 25 warnings in 1455.60s (0:24:15)**. Strict analyst battery **382 passed, 1 skipped in 128.61 s** (section 6.3's 408 is a wider selection); active-document **69 passed**; `git diff --check` clean. Python 3.12.13. No provider, credential, licensed row, price, return, outcome, QC job, upload, deployment, broker, scheduler or order access; **0 research looks and 0 development evaluations.** | 0 P0, 0 P1, 0 P2, 0 corrected; 3 P3 observations documented (ARV2R8-001 unreachable fit-level spec binding, ARV2R8-002 shared-scope dropped ledger tests, ARV2R8-003 two-session review coordination). Cumulative dispositions of the pre-`37dc424` commits remain as recorded in sections 4L-4S. | Codex counter-reviews this exact pushed head. The next bounded milestone (fold-manifest structural binding) requires owner authorization before it begins; ARV2-4 and every data/outcome/QC/paper/funded authority remain blocked. |
| 2026-08-31 | Codex counter-review | `c09d8e4c` -> this commit | Accept Claude's synchronization review after record correction | Re-derived every material merge/isolation claim and accepted the reviewed strategy tree unchanged. Corrected the literal 196-versus-11 range overclaim, three stale canonical handoff rows, the missing quality score, and the exact-tree validation attribution (section 8). The owner's current instruction separately authorizes only the next outcome-free fold-manifest structural milestone. | Corrected active-document gate **69 passed in 5.69 s**; Git ancestry corridor **11**, ordinary two-dot set **196**; diff check clean. No credential, provider row, licensed artifact, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | `c09d8e4c` accepted after correction: 0 P0, 0 P1, 2 P2 and 2 P3 corrected; none unresolved. Review artifact 5/10; underlying integrated structural tree 8/10. | Commit this counter-review record separately, then implement exactly the authorized content-addressed fold-manifest-only structural milestone. Validate both stages and make one combined push for Claude's next review. |
| 2026-08-31 | Codex implementation | `c09d8e4c` -> this record (`a961230a` counter-review; `a6887004` ARV2-4B candidate) | ARV2-4B content-addressed stock fold manifest | Added the exact six-fold 2020-2025 NYSE walk-forward child manifest, four horizon-specific purge/embargo boundaries per fold, immutable authenticated loader authority, exact parent-byte and semantic lineage, partial-2026 exclusion, and cross-date/cross-boundary common-event refusals. The parent stock contract remains unchanged and unbound, every external binding is null, and every data/outcome/QC/result/deployment/order capability remains false. | Focused manifest/registry **36 passed in 13.31 s**; complete Analyst V2 **432 passed, 1 skipped in 1,163.86 s**; repository remainder **6,824 passed, 13 skipped, 1 precisely deselected, 25 warnings in 3,539.17 s** after the deselected out-of-scope Target Price assertion was reproduced directly as **1 failed in 0.68 s**; compileall exit 0; active-document gate **69 passed in 1.20 s** before final record stabilization. Synthetic and structural inputs only; no credential, provider row, licensed artifact, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | ARV2FMI-001/002/003 P2 and ARV2FMI-004/005 P3 corrected; two independent audits found no remaining ARV2 P0-P3. ARV2-UNRELATED-001 is a reproducible P3 stale Target Price error-message assertion, documented and not fixed. Candidate quality 8/10. | Commit this record, re-run the exact document/diff/status gates, re-fetch and require the remote not to have moved, then make exactly one combined push. Claude independently reviews both commits and this record before any ARV2-4 or external-authority step. |
| 2026-08-31 | Claude review | `12b9e61c` -> this commit | Independent review of the section-8 counter-review and the ARV2-4B fold-manifest candidate | Reviewed all three commits in `c09d8e4c..12b9e61c` with an explicit disposition each (section 10). Accepted every section-8 finding against my own section 7 after reproducing the 11/196 counts. Independently recomputed the manifest identity, the 3,435-session axis and hash, all fourteen year-first fold anchors, the horizon-20 purge/embargo construction, and both parent byte pins; probed all six constant-false capabilities, the 30-module import closure, and the lock-inventory coverage. Six reverse mutations: four bit, one corrected (ARV2R9-001), one documented unreachable (ARV2R9-002). One test-only correction; no production module changed. | As received `12b9e61c`: **6825 passed, 13 skipped, 25 warnings in 1451.51s (0:24:11)**, zero failures - ARV2-UNRELATED-001 did not reproduce on this host. Final tree: fold-manifest file **36 passed**; strict analyst battery **418 passed, 1 skipped**; active-document **69 passed**; compileall exit 0; `git diff --check` clean. Python 3.12.13. No provider, credential, licensed row, outcome, QC, upload, deployment, broker, scheduler or order access; **0 research looks and 0 development evaluations.** | 0 P0, 0 P1, 0 P2, 1 P3 corrected, 1 P3 documented. ARV2R9-001: the ARV2FMI-001 in-load revalidation trio had no revert-detecting regression - deleting all three lines left the suite green; a monkeypatched parent loader that mutates its file after returning now pins both parents red/green. ARV2R9-002: the non-circularity clause is unreachable today behind the parent byte pin and becomes load-bearing at the future successor - that review must add the regression. Candidate quality 9/10; counter-review record 8/10. | Codex counter-reviews this exact pushed head. The next bounded milestone requires explicit owner authorization; ARV2-4 execution and every data/outcome/QC/paper/funded authority remain blocked. |
| 2026-08-31 | Codex counter-review | `ba4b3bc9` -> this commit | Accept Claude's ARV2-4B review after correction; stop at the next owner-definition gate | Counter-reviewed both Claude commits in `12b9e61c..ba4b3bc9` commit-by-commit and cumulatively. Completed the claimed final three-file revalidation regression, removed the mid-test fixture-wide undo, normalized a related authenticated-parent disappearance race into the Analyst domain error, and reconciled every canonical current-state passage. Stayed on the dedicated Analyst branch/worktree; no other strategy, UI, Streamlit, source, outcome, or executor work. | Focused corrected loader regressions **39 passed in 10.11 s**; complete `tests/analyst_revisions_v2` **332 passed, 1 skipped in 102.77 s**; active-document gate **69 passed in 0.99 s**; changed-path compileall exit 0; `git diff --check` clean. No credential, provider row, licensed artifact, price, return, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | `0052df9` and `ba4b3bc9` accepted after correction: 0 P0, 0 P1, 1 P2, and 3 P3; ARV2CR10-001 through ARV2CR10-004 corrected. Claude review artifact 7/10; underlying ARV2-4B candidate 9/10. | Commit this counter-review locally and stop before both the next milestone and push. Owner chooses and approves either the exact global-map/matched-row definition (recommended first) or the exact power-plan definition. No credentials are needed. |
| 2026-09-01 | Codex advisory counter-review | `9f8377cf` -> this record commit | Counter-review Claude's proposal-only ARV2-4C advisory | Verified all eight supplied findings against the PDF, exact frozen stock contract, fold-manifest lineage, formulas, tests, and retained archived V1 evidence. Accepted the advisory after correction: retained the successor, exact bootstrap, per-arm derivation, staged coverage, semantic-disclosure, and diagnostic requirements; rejected a fold-manifest re-pin, a blanket zero-MAD-to-zero override, and any claim that an uncommitted per-string V1 count table is already available as V2 evidence. No ARV2-4C artifact or implementation was created. | Record-only validation is reported in section 12.6. No provider row, licensed artifact, price, return, outcome, QC, broker, deployment, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | Claude's eight findings: four confirmed, four partially correct after scope/evidence correction. Counter-review found 4 P2 and 1 P3 defects/omissions in the advisory itself; all are corrected in the recorded disposition, with no product change. Advisory quality **6/10**. | Commit locally and stop before push. After owner-authorized publication of an exact clean snapshot, Claude performs the requested full-module review. ARV2-4C remains unapproved and unimplemented. |
| 2026-09-01 | Codex counter-review | `67ae5c11` -> `06f08b56` + `a371724a` (code corrections; this record commit follows) | Counter-review Claude's complete whole-lane review; no next milestone | Counter-reviewed `d72c8057` and `67ae5c11` independently and cumulatively. Accepted Claude's ingest, numerical, stable-sum, timing, and fit/apply corrections, then closed the residual Git attestation/ancestry and import-firewall/facade fail-opens, completed the five-field ingest-boundary tests, and corrected the whole-lane review record. A final adversarial pass then closed computed-name calendar-facade access and pinned commit-graph disabling on the ancestry query. Stayed in the dedicated Analyst worktree and branch. | Exact corrected tree: `tests/analyst_revisions_v2` **420 passed, 1 skipped in 139.59 s**; root preregistration **46 passed in 39.67 s**; dataset/firewall **116 passed in 83.38 s**; ratings/ontology **49 passed**; active-document gate **69 passed**; compileall exit 0; `git diff --check` clean. No credential, provider row, licensed artifact, price, return, outcome, QC upload/compile/job, broker, deployment, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | 0 P0, 0 P1, 6 P2, and 6 P3; `ARV2CR11-001` through `ARV2CR11-012` corrected. Both Claude commits accepted after correction. Final current-tree audit and validation found no remaining P0-P2. | Commit this lane record locally and stop before both ARV2-4C implementation and push. The owner must explicitly approve the recommended full 39-alias comparator or choose the 16-label core; no credentials are needed for that decision. |
| 2026-09-01 | Codex implementation | `4c686a55` -> this record commit | Owner-approved ARV2-4C full-39 global comparator and corrected matched-row structural candidate | Implemented three content-addressed outcome-free artifacts plus an authenticated loader/resolver/hash-counter boundary. Preserved predecessor and fold bytes, added the complete seven-source acyclic ancestry, exact 39-map/15-refusal policy, symmetric paired-only zero-range handling, five pooled/per-fold 19/20 coverage ledgers, staged post-join underfill, deterministic complete-session bootstrap, and full-path scale-invariance/adversarial tests. | Focused candidate **152 passed, 1 host skip**; complete Analyst suite **571 passed, 2 host skips in 132.60 s**; complete repository **7,068 passed, 14 skipped, 3 standing out-of-lane failures, 26 warnings in 1,254.63 s**; compileall exit 0; exact artifact render equality and diff checks green. The three failures are `ARV2-UNRELATED-001` plus the two `ARV2WL-D11` sleeve-report cases and were documented, not fixed. No credential, provider row, licensed artifact, price, return, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | `ARV2I4C-001` through `ARV2I4C-004` P2 and `ARV2I4C-005` through `ARV2I4C-007` P3 corrected. Three final independent read-only audits accepted with no remaining P0-P3. | Commit implementation and record, revalidate exact final tree, re-fetch and stop if remote moved, then make exactly one combined push. Claude independently reviews the complete pushed range on this branch; Codex counter-reviews before the power-plan milestone. |
| 2026-09-01 | Codex counter-review | `db2d8011` -> this local record commit | Accept Claude's ARV2-4C review after one documentation correction; identify the exact power-policy gate | Accepted Claude's test-only predecessor-refusal regression and independently verified the exercised guard. Corrected section 16's linear-looking DAG shorthand to a topological node order with exact parent sets; no production code changed. Derived the next safe milestone boundary from the PDF and frozen parent contracts without choosing financial/statistical numbers. | New regression **1 passed** independently; final ARV2-4C plus active-document battery **220 passed, 1 host skip in 20.29 s**; `git diff --check` clean apart from informational Windows line-ending notice. No credential, provider row, licensed artifact, price, return, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | `abcb34f3` accepted; `db2d8011` accepted after `ARV2CR12-001` P3 record correction. No P0-P2. ARV2R10-D01/D02 remain accurately documented. | Keep this counter-review local and unpushed until the owner approves the exact power-policy inputs; then implement one bounded outcome-free power milestone, validate both stages, and make the single combined push. |
| 2026-09-02 | Codex implementation | `db2d8011` -> `ac6f06e4` (counter-review `317ebe03`; record commits follow) | Owner-approved ARV2-4D-A outcome-free power-calibration protocol | Retained and committed the section-17 counter-review, then froze the exact 10-bps/+1 bullish H20 effect, nominal 80%/two-sided 5% planning policy, 483-session pre-test calibration axis, lag-20 HAC and q05 component arithmetic, 1,388-session fixed capacity, closed disclosure contract, nine-node lineage, authenticated loader, and non-authoritative provisional helper. No input manifest, numeric receipt, successor binding, or action authority was created. | Protocol **94 passed, 1 host symlink skip**; protocol plus import firewall **210 passed, 1 skip in 118.28 s**; complete Analyst suite **666 passed, 3 skips in 167.60 s**; exact committed repository **7,162 passed, 15 skipped, 4 standing out-of-lane failures, 26 warnings in 1,321.04 s**. The failures are `ARV2-UNRELATED-001` and three date-relative Trading App sleeve-report assertions in the standing `ARV2WL-D11` family; documented, not fixed. Renderer/raw artifact SHA and diff checks are exact. No credential, provider row, licensed artifact, price, return, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | `ARV2I4DA-001` through `ARV2I4DA-007` P2 and `ARV2I4DA-008` through `ARV2I4DA-010` P3 corrected. Three independent final read-only audits accepted with no remaining P0-P3. | Revalidate the final record-only change, re-fetch and stop if the remote moved, then make exactly one combined push. Claude reviews `db2d8011..new_head`; Codex counter-reviews before any separately authorized ARV2-4D-B work. |
| 2026-09-02 | Claude review and deferred-finding resolution | `35b3833` -> this commit | Independent review of ARV2-4D-A plus resolution of the section-13 deferred findings | Reviewed all four commits in `db2d801..35b3833` with an explicit disposition each (section 19); ARV2-4D-A accepted with no correction required. Verified rather than accepted: both recorded identities reproduce exactly (protocol ID `arv2-stock-power-calibration-protocol-0ba6b7d745783796`, artifact SHA-256 `ff16117a...f4a13`), all nine action capabilities are literal false, the loader cannot be called without the complete six-artifact reviewed ancestry, and the import firewall still reports zero forbidden roots. Separately resolved the whole-lane deferred findings: corrected `ARV2WL-D01`, `-D02`, `-D03`, `-D05`, `-D07`, `-D08`; documented `-D04`, `-D06`, `-D09`, `-D10` with the reason each must not be fixed on this branch; `-D11` remains out of lane per the owner scope rule. Added `tests/analyst_revisions_v2/test_dormant_etf_portfolio_arithmetic.py`. No committed artifact was re-serialised and no frozen shared file was touched. | New dormant-arithmetic file **14 passed**; active-document gate **69 passed**; focused ARV2 batteries green; full-tree suite result recorded in this push's commit message; compileall exit 0; `git diff --check` clean. Mutation evidence: ignoring the ETF cap in water filling (3 failed), dropping the cost impact term (1), ignoring the coverage denominator (2), dropping the weight from the weighted score (1), disabling the firm-normalization census (1), and removing the snapshot sidecar refusal (1) all turn the new tests red; restoring turns them green. No provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect or scheduler access. **0 research looks.** | 0 P0, 0 P1, 0 P2, 0 P3 against the reviewed range. Two self-corrections are recorded rather than hidden: the first `ARV2WL-D03` test did not discriminate its own fix, and investigation showed the fail-open is unreachable because `mapped` is rounded during accumulation, so the test now pins the real boundary property and the change is labelled hardening; and the first `ARV2WL-D05` comment claimed the hard caps were re-checked exactly when they are re-checked with tolerance, so it now states what the code enforces. `ARV2WL-D10` was attempted and correctly abandoned after finding that the tightened byte check would reject a reviewed hash-pinned artifact whose root keys are unsorted. | Codex counter-reviews this exact pushed head. ARV2-4D-B stays unauthorised pending a separately reviewed input-manifest schema and calibration-input authority. The four deliberately unfixed findings are owner or ARV2-5 decisions, and the two-reviewer ownership question in `ARV2R5-002` is still open. |
| 2026-09-02 | Codex counter-review and implementation | `10ce9196` -> this validation commit (`7b804e7` counter-review; `89f385c` ARV2-3Q-F candidate) | Accept Claude's ARV2-4D-A/deferred-finding review after correction; implement the owner-directed four-family multiplicity overlay | Counter-reviewed Claude's sole commit commit-by-commit and cumulatively, corrected its exact-coverage, allocator, authority, census, test-sensitivity, and record defects, then implemented the additive four-lane `1/20` family overlay with a permanent `1/80` Analyst maximum, expiring/nontransferable slots, authenticated supersession of the old unspent `1/60`, immutable QC ancestry, and no fallback or action authority. No accepted ancestor or out-of-lane code was changed. | Counter-review battery **217 passed, 1 skip**; ARV2-3Q-F plus firewall **212 passed, 5 skips**; complete Analyst V2 **782 passed, 8 skips**; exact committed repository **7,279 passed, 20 skipped, 3 standing `ARV2WL-D11` out-of-lane failures, 25 warnings in 3,008.37 s**; active-document **69 passed**; compileall and diff checks clean. No provider, credential, licensed row, price, return, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | Counter-review: 0 P0, 0 P1, 3 P2 and 6 P3, all corrected (`ARV2CR13-001..009`). ARV2-3Q-F self-review: 0 P0, 0 P1, 1 P2 and 4 P3, all corrected (`ARV2QF-001..005`). Three independent final audits found no remaining P0-P3. The three unrelated Trading App failures were documented and not fixed. | Commit this exact validation record, fetch only the lane remote and require it still equals `10ce9196`, then push the complete local range exactly once. Claude independently reviews every pushed commit; Codex counter-reviews before any later milestone. ARV2-4D-B and every data/outcome/QC/deployment/trading action remain unauthorized. |
| 2026-09-02 | Claude independent review | `d2aefe6f` -> `64edf355` (corrections) + this record commit | Independently review Codex counter-review `7b804e7b`, the ARV2-3Q-F four-family multiplicity candidate `89f385cd`, and its validation record `d2aefe6f` | Disposed all three commits individually and cumulatively; reproduced the semantic SHA-256 `54ab0bb6...`, artifact SHA-256 `2e9f390e...`, exact `1/20` / `1/80` rationals, expiry-without-transfer semantics, byte-unchanged `1/60` and ARV2-4D-A artifacts, no-fallback authority, constant-false capabilities, null bindings, and the additive acyclic leaf first-hand; confirmed `7b804e7b` only strengthens (the 52-digit coverage fail-open reproduced against `10ce9196`). Corrected four P3 hardening/test-sensitivity findings in the overlay module and its battery only (`ARV2R12-001..004`); documented five in-lane P3 observations (`ARV2R12-D01..D05`) and the standing out-of-lane `ARV2WL-D11` failures without fixing them. | As-received `d2aefe6f`: focused **280 passed, 5 skips**; complete repository **7,279 passed, 20 skipped, 3 standing `ARV2WL-D11` out-of-lane failures, 25 warnings**. Final tree `64edf355`: overlay **116 passed, 5 skips**; overlay plus firewall **232 passed, 5 skips**; complete Analyst V2 **894 passed, 8 skips**; complete repository **3 failed, 7299 passed, 20 skipped, 25 warnings in 1572.05s (0:26:12)** (same three out-of-lane failures); active-document **69 passed in 1.70s**; seven reverse mutations red then green; compileall and diff checks clean. No provider, credential, licensed row, price, return, outcome, QC action, deployment, broker, scheduler, order, UI, or Streamlit access; **0 research looks and 0 development evaluations**. | 0 P0, 0 P1, 0 P2, 4 P3 corrected, 5 P3 documented; Codex counter-review `7b804e7b` accepted, `89f385cd` accepted after correction, `d2aefe6f` accepted. | Commit this record, fetch only the lane remote and require it still equals `d2aefe6f`, then push exactly once. Codex counter-reviews every Claude commit. ARV2-4D-B and every data/outcome/QC/deployment/trading action remain unauthorized. |

| 2026-09-03 | Codex counter-review | `c83218c7` -> this local record commit (not pushed) | Accept Claude's ARV2-3Q-F review after record correction; stop at the owner-authority gate | Counter-reviewed `64edf355` and `c83218c7` commit-by-commit and cumulatively. Accepted Claude's 15-line semantic hardening and 20 new regressions; corrected the current alpha/status and DAG prose, and completed the parser-observation scope. No production code, test, artifact, authority, out-of-lane, or next-milestone change was made. | Focused overlay plus import-firewall battery **232 passed, 5 host symlink skips in 277.10 s**; overlay file **116 passed, 5 skips**; complete Analyst V2 battery **909 passed, 8 skips in 805.23 s**; exact full tree **3 failed, 7,299 passed, 20 skipped, 25 warnings in 3,428.89 s**, with only the standing out-of-lane `ARV2WL-D11` failures; active-document consistency **69 passed**; compileall and diff checks clean. No credential, provider/licensed row, price, return, outcome, QC resource, deployment, broker, scheduler, or order access; **0 research looks and 0 development evaluations**. | `64edf355` accepted; `c83218c7` accepted after correction: 0 P0, 0 P1, 2 P2 and 2 P3 (`ARV2CR14-001..004`), all corrected or fully documented in the lane record. `ARV2WL-D11` remains documented, out of lane, and unfixed. | Commit this counter-review record locally and do not push. No subsequent milestone is authorized. ARV2-4D-B and every data/outcome/QC/deployment/trading action remain blocked pending the exact owner authorities in section 23.5. |
| 2026-09-03 | Codex implementation | `6baa13d2` -> this candidate commit | Owner-authorized ARV2-4D-B1 outcome-free calibration-input manifest schema | Pushed the completed counter-review first, then implemented only the later-authorized schema and caller-supplied synthetic-fixture validator. The content-addressed contract closes the 483-session axis, evidence epoch/cutoff, two input roles and censuses, rights, source/transformation/terminal lineage, hashes, and counts. It adds no production input loader, calibration, receipt, outcome, QC, deployment, or trading path; accepted 4D-A and 3Q-F artifacts are byte-identical. | B1 **252 passed, 2 skips**; B1 plus firewall **368 passed, 2 skips in 345.17 s**; complete Analyst and repository runs reached 79% and 9%, respectively, with zero failures before the owner's immediate-finalization instruction; compileall, exact identity/renderer reproduction, ancestor byte checks, and diff check pass. No restricted access; **0 research looks and 0 development evaluations**. | Two P2 and two P3 findings (`ARV2I4DB1-001..004`) corrected before freeze; final audit found 0 remaining P0-P3. | Commit once, fetch only the lane remote and require `6baa13d2`, then push once. Claude independently reviews this exact snapshot; full ARV2-4D-B remains gated. |
| 2026-09-03 | Claude review | `42faec1` -> this commit | Independent review of the ARV2-4D-B1 calibration-input manifest schema candidate | Reviewed the single commit in `6baa13d..42faec1` with an explicit disposition (section 25); accepted with no correction, so this push is record-only and the candidate tree is unchanged. Verified rather than accepted: artifact 15,136 bytes at `e642d065...`, semantic hash `4032405d...` and schema ID recomputed from bytes, renderer output byte-identical; the 483-session axis, its SHA-256, the 2020-01-30 cutoff and 2020-01-31 first excluded session all reproduced from `data.exchange_calendar` and the h20 fold block; first nine lineage nodes identical to ARV2-4D-A; ARV2-4D-A and ARV2-3Q-F byte pins unchanged; 34-module firewall with zero forbidden roots; 14 capabilities, 14 bindings and 11 fixture authorities all false or null. Eighteen adversarial fixtures behaved correctly. The parent-bytes question is closed: a semantically identical, differently serialised ARV2-4D-A artifact is refused by the protocol loader's canonical-render check, so the semantic hash pins the parent bytes transitively. | B1 battery **252 passed, 2 skipped** in 87.9 s, reproducing section 24. Complete repository suite **3 failed, 7,550 passed, 23 skipped in 47:06**, the three being the out-of-lane `ARV2WL-D11` sleeve-report trio, completing the runs Codex stopped at 79% and 9%. Mutation matrix in a detached scratch worktree: six of seven guard removals turn the battery red; the seventh (`if not source_roots`) survives because it is unreachable by construction, documented rather than papered over with a test. Active-document gate green; compileall exit 0; `git diff --check` clean. No provider, credential, licensed row, price, return, outcome, broker, operator-database, QuantConnect, scheduler or order access. **0 research looks, 0 development evaluations.** | 0 P0, 0 P1, 0 P2, 0 P3. Two observations carried to ARV2-4D-B2 without priority: the capture instant has no upper bound and `post_cutoff_corrections_included` is an unverifiable self-declaration at schema level, which is correct for an outcome-free schema but will need vintage evidence in a production manifest; and the unreachable guard should stay as defense in depth. `ARV2WL-D11` remains the only repository failure and is out of lane. | Codex counter-reviews this exact pushed head. ARV2-4D-B2 and full ARV2-4D-B remain unauthorised; `ARV2R5-002` two-reviewer ownership still open. |

## 6. Project-wide `main` synchronization conflict review, 2026-08-31

This review froze the pushed Analyst lane at
`c16f7f40c844cc70c387c3270c03a01209a5015b` and `origin/main` at
`1a5264e6b1de3caf5477477d1312a762b2d42419`.  The merge was resolved only in
a detached disposable clone and recorded by local merge commit
`4ef736b`; the live long-lived branch, its worktree, and its remote ref were
not moved.  Applying or pushing this artifact requires a fresh exact-tip check
and separate owner direction.

### 6.1 Commit-by-commit disposition

| Commit | Disposition | Basis |
|---|---|---|
| `e53ba26` | Accepted | ARV2-3Q counter-review corrections remain fail-closed and consistent. |
| `c334571` | Accepted after correction | ARV2-4A defects ARV2CR8-006 through ARV2CR8-010 were corrected by `33d40f1`. |
| `37dc424` | Accepted after correction | Its independent verification remains useful; ARV2CR8-001 through ARV2CR8-004 were corrected. |
| `33d40f1` | Accepted | Correctly closes registration self-promotion, decision-clock and lineage relabeling, and report-contract gaps. |
| `3aedfff` | Accepted | Accurate documentation-only counter-review ledger. |
| `c16f7f4` | Accepted | Accurately records the narrow push authorization without granting later authority. |

The earlier `a4f58e6..f2c15d8` history retains the dispositions already recorded
above.  No new open P0-P3 finding remains in the reviewed pushed delta.

### 6.2 Conflict choices and finding

All 37 textual conflicts were resolved without weakening either side's owned
contract.  Shared safety and execution production files use the exact newer
`main` versions.  Analyst-owned source, specifications, fixtures, and closest
tests use the exact lane versions.  Four manual test unions retain
non-superseded coverage for real-process crash durability, malformed
read-only open-order books, fork-child reset behavior, and Store-alias
installer-preview skipping.  Three older lane-only portfolio-ledger tests were
not retained because two asserted behavior incompatible with `main`'s newer
exact-money/provenance contract and the remaining behavior is covered by the
stronger shared suite.

`ARV2-MRG-001` (P2) was found and corrected during integration: a wholesale
lane choice for this record omitted `main`'s exact active-document requirement
that a valid null closes the canonical family.  The reconciled ARV2-4 gate now
states that a screen failure or valid null closes the canonical family, while
only a pass unlocks ARV2-5.  No executable strategy behavior was changed by
that documentation correction.

### 6.3 Verification and authority

- Analyst-focused: **408 passed, 1 skipped**.
- Reconciliation-focused: **103 passed**.
- Active-document consistency after the gate union: **67 passed**.
- Exact final resolved tree: **5,953 passed, 3 skipped, 0 failed, 26 warnings**
  in 993.96 seconds; repository `compileall` exited 0.
- Non-PDF staged `git diff --check` passed.  The standard check reports only
  whitespace-like bytes in the exact `main`-owned target-price PDF; its blob
  equals the second parent and was not rewritten.
- The initial long-temporary-path failures were Windows path-length artifacts;
  the identical selection passed with a short temporary base.

No provider, credential, licensed row, price, return, outcome, QuantConnect
upload/compile/job, deployment, broker, operator database, scheduler, order,
UI, or trading authority was used or granted.  ARV2-4 remains blocked, and
this merge-resolution record does not authorize a later milestone.

### 6.4 Local application, 2026-08-31

After the owner directed Codex to begin the reconciliation work, Codex
re-fetched all remotes, verified that the live worktree was clean and still at
exact recorded lane head `c16f7f40c844cc70c387c3270c03a01209a5015b`,
verified the complete-history bundle, and fast-forwarded this long-lived local
branch to reviewed bundle tip
`d9de03d3ecfb745b3267ac96025847e373de52de`.  The tested merge commit
`4ef736be060bf4311b718a2778d230d0fa45a594` is therefore now in this local
branch's ancestry.  No commit was rewritten and no remote ref was moved.

This application changes the earlier artifact-only state; it does not change
the conflict choices, test evidence, review disposition, or authority gates
above.  The branch remains local-only and must not be pushed without separate
owner authorization and a fresh exact remote-tip check.

### 6.5 Corrective synchronization after `main` advanced, 2026-08-31

Immediately after the three resolved lane heads were pushed, `main` advanced
from `1a5264e6b1de3caf5477477d1312a762b2d42419` to
`19ae3f9f` by merging the Insider Buying, Short Interest, and Target Price
PRs. The owner then reported one remaining conflict. Read-only merge-tree
reproduction showed Insider, Short Interest, and Target Price merge cleanly;
only Analyst Revisions conflicted, solely in
`tests/test_ml_evidence_operations.py`.

The earlier Analyst resolution had retained a small Store-alias detection
helper that skipped the installer-preview test. New `main` contains the
strictly stronger shared contract: it keeps a real virtual-environment
launcher, resolves only an invalid Store execution alias to the running
process image, and adds direct zero-byte and reparse-point refusal coverage.
The conflict was therefore resolved to exact `main` blob
`be5ad79182c89f502eb90b7f6e0b49396c8f967e`; no Analyst-owned production,
specification, fixture, or test path was replaced.

The exact conflict file passed **57 tests**. The first complete-suite run on
the staged, not-yet-committed merge reached **6,789 passed and 13 skipped**;
its only failure was
`test_policy_code_is_checked_out_as_exact_bytes`, whose deliberate
`git show HEAD:<new-target-price-path>` check cannot see files until the merge
commit exists. This is a commit-state validation gate rather than a product
failure. The complete suite must be rerun on the exact merge commit before the
corrective push. No provider, outcome, QuantConnect, broker, deployment,
order, or trading authority was accessed or granted, and ARV2-4 remains
blocked.

### 6.6 Exact committed-tree validation and corrective handoff

The corrective merge is committed as
`d9b05eb6c5911cd78c7f608b795d417e8878f3a1`, with parents exact prior pushed
Analyst head `7a7757a299adf2a7c5a85c989a75e8f0440043bc` and exact advanced
`main@19ae3f9f97e088c2e418c4a488bbbaa07303da48`. The previously failing
Target Price exact-byte guard passed directly on this committed state.

The exact committed repository tree then passed **6,790 tests with 13 skips,
0 failures, and 26 dependency/runtime warnings in 1,362.48 seconds
(22m42s)**. The conflict file remained independently green at **57 passed**.
Repository compileall passed with bytecode redirected to a dedicated temporary
cache because this sandbox cannot write existing worktree `__pycache__`
directories. Changed-file diff checking, unmerged-path checking, ancestry, and
worktree status are clean.

No new P0-P3 finding remains. This documentation-only handoff commit follows
the fully tested merge. A fresh fetch must still show `19ae3f9f` and prior
Analyst head `7a7757a2` as ancestors before the one corrective push. The exact
new pushed snapshot then requires independent review; all research, source,
outcome, QuantConnect, deployment, broker, order, and trading gates remain
unchanged.

### 6.7 Explicit authorization for the corrective push

After the corrective merge and validation record produced clean local head
`64ccf25243487d48a96c2879e03867a0c958026f`, Codex reported that the remote
remained at `7a7757a299adf2a7c5a85c989a75e8f0440043bc`, `main` remained at
`19ae3f9f97e088c2e418c4a488bbbaa07303da48`, the complete suite was green,
and the PR merge simulation was conflict-free. The owner then explicitly
instructed `push`. This authorizes one corrective remote update of the
existing Analyst lane after one final exact-tip and clean-worktree check. It
does not authorize a new milestone or any provider, outcome, QuantConnect,
deployment, broker, order, or trading action.

## 7. Independent Claude review of the ARV2-4A counter-review and the main synchronization, 2026-08-31

**Ancestry corridor reviewed:**
`git rev-list --ancestry-path --reverse 37dc424f..cf136e25` returns the eleven
commits disposed below. The full two-dot set difference contains 196 commits:
185 off-corridor commits entered as already-main ancestry through the two
merge commits and are not claimed as individually reviewed in this lane.
Their lane-relevant merge result, conflict resolution, and Analyst-tree
isolation are reviewed below. **Claude disposition: ACCEPTED.** 0 P0, 0 P1,
0 P2; **Claude required no code correction.** Codex later corrected two P2
and two P3 record defects in section 8 without changing the reviewed strategy
code.
Three P3 observations are documented in 7.4; none is a defect in the reviewed
range. **Zero research looks and zero development evaluations.** No provider,
credential, licensed row, price, return, outcome, broker, operator-database,
QuantConnect, upload, scheduler, order, UI or Streamlit access occurred.

**Reviewing session:** the same Claude session (personal Git identity) that
produced sections 4L and 4O, addressing the coordination point in ARV2R7-002
by identifying itself explicitly. Sections 4I and 4R were produced by the
work-identity session. The commits `e53ba26`, `c334571` and `37dc424` inside
the wider ledger history were reviewed by section 4R and counter-reviewed by
section 4S; this review spot-verified their material claims rather than
re-reviewing them, and its own range begins after `37dc424`.

### 7.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `33d40f1e` | Accepted | The section 4S code corrections. Verified strengthening throughout: `require_production_registry_entry` now ends in an unconditional fail-closed raise so a checked-in registry entry cannot self-promote (ARV2CR8-005); the exact NYSE-open equality moved into the frozen cross-section invariant (ARV2CR8-006); and the process-local weak-reference identity registry mirrors the established `_POLICY_AUTHORITIES` pattern - RLock, id-reuse-safe purge callback, digest re-pin - so a `dataclasses.replace` copy carries the token but lands unregistered and refuses, and a low-level mutation of a registered object breaks its pinned digest (ARV2CR8-010). The new registry is covered by the authority-lock inventory test. Mutation-verified: removing the open-equality check, skipping the registry authentication, and reverting the approval raise each turn the new tests red; restored green. |
| `3aedfffc` | Accepted | Record-only section 4S ledger. Its cumulative-disposition reconciliation of section 4R (ARV2CR8-002) is correct, and its ARV2CR8-003 ID-collision repair leaves exactly one definition per observation. Touches only this lane record. |
| `c16f7f40` | Accepted | Records the narrow owner push authorization without granting later authority. Record-only. |
| `4ef736be` | Accepted | First main merge. Independently verified: the analyst research tree (`research/analyst_revisions_v2/`, `tests/analyst_revisions_v2/`, both sibling test files) is **byte-identical** from pre-merge lane head `c16f7f40` to final `cf136e25` - an empty diff - so no conflict choice touched lane-owned strategy code. |
| `d9de03d3` | Accepted | Section 6 conflict-review record, including the self-found and corrected `ARV2-MRG-001`. Record-only. |
| `43224495` | Accepted | Local-application record (fast-forward of the reviewed bundle; no rewrite). Record-only. |
| `7a7757a2` | Accepted | Owner push-authorization record. Record-only. |
| `d9b05eb6` | Accepted | Second (corrective) main merge after `main` advanced. Its single conflict file `tests/test_ml_evidence_operations.py` resolves to exactly `main`'s blob `be5ad791...`, verified by blob-hash equality at both `19ae3f9f` and `cf136e25`, matching the section 6.5 claim. |
| `64ccf252` | Accepted | Validation record for the corrective merge. Record-only. |
| `ef1a5251` | Accepted | Owner corrective-push authorization record. Record-only. |
| `cf136e25` | Accepted | The PR #321 merge by the owner. The lane branch, its remote, and `main` now share this head. |

### 7.2 Independent verification

- **Lane isolation across both merges, proved by bytes.** `git diff c16f7f40
  cf136e25` over the analyst research and test tree is empty. Every one of
  this lane's review regressions - the superseded-period case, the
  authority/schema/status pins, the plan-id derivation, duplicate-key
  refusal, the no-hard-cutoff decay pin - is present at the final tree.
- **The one merge conflict resolved to the stronger side.** The final
  `tests/test_ml_evidence_operations.py` blob equals `main`'s, which carries
  the real virtual-environment launcher and reparse-point coverage rather
  than the lane's smaller Store-alias helper.
- **Fail-closed production registration re-verified.** The former positive
  registration test now expects `approval authority is absent`, and later
  artifact substitution still fails against the reviewed blob. Reverting the
  unconditional raise turns the renamed test red.
- **Historical validation of the pre-review code tree `cf136e25`:** full suite
  **6790 passed, 13 skipped, 25 warnings in 1455.60s (0:24:15)** in a pinned detached worktree. The growth from section 6.3's 5,953 reflects the four merged lanes' suites now sharing one tree, and the extra skips are other lanes' host-capability skips; nothing failed. Strict analyst battery (analyst directory plus the
  contracts and preregistration files): **382 passed, 1 host symlink skip in
  128.61 s** - section 6.3's 408 uses a wider reconciliation selection, the
  same selection-variance class recorded in 4O.5. The **69-pass**
  active-document result applies to the record bytes committed at
  `cf136e25`, not the later section-7 bytes in `c09d8e4c`; the counter-review
  validation for the corrected record is reported separately. `git diff
  --check` was clean; no frozen shared file was touched.

### 7.3 Mutation matrix

Four reverse mutations against the section 4S guards in a detached scratch
worktree at `cf136e25`: open-equality removal, registry-authentication skip,
and approval-raise revert each **bit**; the fit-level `spec_hash` binding
survived and became observation ARV2R8-001 below rather than a correction.

### 7.4 Observations (documented, deliberately not corrected)

| ID | Kind | Observation |
|---|---|---|
| ARV2R8-001 | Unreachable redundancy, verified | The fit/apply check `item.spec_hash != contract.spec_hash` (ARV2CR8-007) survived mutation, and analysis shows it is **unreachable through authentic objects today**, not merely untested: the contract loader's exact frozen-template match makes a second valid `spec_hash` unconstructible in-process (any content change refuses at load; a byte-identical copy has the same hash), and a tampered registered cross-section breaks its pinned registry digest before the comparison runs. This is the same defense-in-depth pattern as ARV2R7-001 and ARV2R4-005. It becomes the load-bearing guard the moment a future milestone introduces contract versioning or a reviewed persistence loader - that refactor must add the regression this review deliberately did not force. |
| ARV2R8-002 | Shared-scope, out of lane | Section 6.2 records three lane-only portfolio-ledger test functions not retained through the merge because they asserted behavior incompatible with `main`'s newer exact-money/provenance contract. No test *file* was deleted (verified: the lane-to-final diff has no deletions), and the justification names the stronger shared coverage. Portfolio-ledger behavior is Trading-App scope, so under the owner's lane rule this is documented for the shared-remediation owners rather than re-litigated here. |
| ARV2R8-003 | Session coordination | Three review sections in this lane now come from two Claude sessions (4I/4R work identity; 4L/4O/this section personal identity). Attribution stays clean through Git identity and the explicit session statements each section now carries, but ARV2R7-002's point stands: the parallel workflow names one review session per lane, and consolidation is an owner decision. |

### 7.5 Next step

Codex counter-reviews this exact pushed head. The recommended next bounded
milestone remains the fold-manifest-only structural binding named in section
4S, which requires owner authorization before it begins. ARV2-4 stays blocked
on the recorded source, rights, review, run-identity and one-use authority
gates; every executable definition hash is still null, and upload, historical
launch, paper deployment and funded live remain constant false.

## 8. Codex counter-review of Claude commit `c09d8e4c`, 2026-08-31

**Disposition: ACCEPTED AFTER CORRECTION.** Review-artifact quality: **5/10**
because the substantive verification was strong but the literal commit-range
claim, canonical handoff state, required quality assessment, and exact-tree
validation attribution needed correction. Underlying integrated structural
tree quality: **8/10** because its authenticated, outcome-free boundaries and
tests are strong, while production sources and executable definitions remain
intentionally absent. Claude's commit changed only this lane record. It
introduced no source, outcome, QC, network, deployment, or trading path.

| ID | Severity | Status | Finding | Correction and verification |
|---|---:|---|---|---|
| ARV2CR9-001 | P2 | Corrected | Section 7 called `37dc424f..cf136e25` an eleven-commit range even though ordinary two-dot enumeration contains 196 commits. This overstated commit-by-commit coverage and made the binding review ledger non-reproducible. | Section 7 now names the exact eleven-commit ancestry corridor and explicitly excludes the 185 imported-main off-corridor commits from its individual-review claim while retaining review of both merge results, the one conflict, and Analyst-tree isolation. `git rev-list --ancestry-path --count` returns 11; ordinary `git rev-list --count` returns 196. |
| ARV2CR9-002 | P2 | Corrected | Three canonical current-state rows still said corrected ARV2-4A was pending independent review after section 7 had completed that review. A later machine could repeat a completed stage or infer the wrong gate. | The stock-formula, preregistration, and architecture rows now agree with sections 7-8: corrected ARV2-4A is accepted after independent review and Codex counter-review correction. Every executable authority remains blocked. |
| ARV2CR9-003 | P3 | Corrected | Section 7 omitted the mandatory honest 1-10 quality assessment. | Section 8 records separate, reasoned ratings for the review artifact and underlying structural tree. |
| ARV2CR9-004 | P3 | Corrected | Section 7 called the `cf136e25` validation an exact-final-tree result even though the new record bytes were committed only at `c09d8e4c`, and the active-document gate reads this file. | Section 7.2's result is treated as historical validation of the pre-review code tree. This counter-review and the milestone record separately report validation of their exact final document trees. |

Independent evidence also confirmed that `c16f7f40..cf136e25` is empty over
the Analyst research and test paths; `tests/test_ml_evidence_operations.py`
has blob `be5ad79182c89f502eb90b7f6e0b49396c8f967e` at both `19ae3f9f` and
`cf136e25`; and `c09d8e4c` modifies only this record. Claude observation
ARV2R8-001 is valid unreachable defense-in-depth, ARV2R8-002 remains
document-only and out of this lane, and ARV2R8-003 is nonblocking because the
reviewing session is explicitly attributed.

The owner's instruction on this round supplies the separate authorization
required by section 7.5 for exactly the next outcome-free,
content-addressed fold-manifest-only structural milestone. It does not grant
provider, licensed-row, outcome, QC upload/compile/job, paper deployment,
funded deployment, broker, scheduler, order, or trading authority. No
credential or API key is needed for that structural work. ARV2-4 remains
blocked.

## 9. ARV2-4B content-addressed stock fold manifest, 2026-08-31

**Disposition: CANDIDATE COMPLETE, NOT ACCEPTED.** The owner authorized this
single outcome-free structural milestone in the instruction that opened this
round. The checked-in child is
`arv2-stock-folds-1002155dbe8e3e87` / SHA-256
`1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611`.
It consumed no provider row, licensed artifact, price, return, outcome, QC
upload/compile/job, broker, deployment, scheduler, order, credential, or API
key: **zero research looks and zero development evaluations**.

### 9.1 Frozen structural contract

The lineage is deliberately one-way and non-circular:

`strategy PDF -> QC-first plan -> stock-evaluation spec/history -> fold manifest`.

The manifest binds the exact PDF hash; QC-first plan ID, semantic hash, and
artifact-byte SHA-256; stock-spec ID, semantic hash, artifact-byte SHA-256,
and history-section SHA-256; and evaluation ID. The parent stock spec retains
its null `fold_manifest_sha256`. A later full ARV2-4 successor may bind this
manifest only after independent review and Codex counter-review; this child
cannot edit its parent into a content-hash cycle.

Its calendar contract binds **3,435** ordered NYSE sessions from 2013-01-02
through the fixed 2026-08-28 outcome cutoff, SHA-256
`b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3dc848cfb86ab88d732`.
Six rolling 5-year train / 2-year validation / 1-year test folds are frozen:

| Test year | Nominal train `[start,end)` | Nominal validation `[start,end)` | Nominal test `[start,end)` |
|---:|---|---|---|
| 2020 | `[2013-01-02,2018-01-02)` | `[2018-01-02,2020-01-02)` | `[2020-01-02,2021-01-04)` |
| 2021 | `[2014-01-02,2019-01-02)` | `[2019-01-02,2021-01-04)` | `[2021-01-04,2022-01-03)` |
| 2022 | `[2015-01-02,2020-01-02)` | `[2020-01-02,2022-01-03)` | `[2022-01-03,2023-01-03)` |
| 2023 | `[2016-01-04,2021-01-04)` | `[2021-01-04,2023-01-03)` | `[2023-01-03,2024-01-02)` |
| 2024 | `[2017-01-03,2022-01-03)` | `[2022-01-03,2024-01-02)` | `[2024-01-02,2025-01-02)` |
| 2025 | `[2018-01-02,2023-01-03)` | `[2023-01-03,2025-01-02)` | `[2025-01-02,2026-01-02)` |

Each fold contains independently content-hashed 1/5/20/60-session boundaries.
Purge is the half-open interval from nominal train end to effective validation
start; embargo is the half-open interval from nominal validation end to
effective test start. Each contains exactly the named number of NYSE sessions
and revalidates through `StructuralFoldBoundary`. Partial 2026 is locked out
with no blind extension. Cross-date common-event components are refused before
fold assignment, and cross-boundary components are refused in full from all
adjacent samples. No component inventory exists without data.

The loader requires one sorted-key UTF-8/LF byte form, exact content-derived
manifest/section/fold/boundary hashes, stable non-symlink files, final
TOCTOU revalidation, immutable deep-frozen values, and a process-local locked
weak-reference authority registry. Every external binding is null and every
source/outcome/QC/result/deployment/order capability is literal false. It
does not connect these folds to fixture-only fit/apply or create any execution
surface.

### 9.2 Implementation review ledger

| ID | Severity | Status | Finding | Correction and verification |
|---|---:|---|---|---|
| ARV2FMI-001 | P2 | Corrected | The first draft did not revalidate both parent files after their nested loaders returned, leaving an in-load byte-change window. | Added independent stable reads plus final QC-plan, stock-parent, and manifest revalidation. Direct audit races that mutate either parent after its loader returns now refuse with the named parent error. |
| ARV2FMI-002 | P2 | Corrected | Pretty reserialization preserved parsed insertion order, so a reordered-object byte stream could load under the same semantic manifest identity. | Made sorted keys part of the sole accepted manifest byte form, regenerated the artifact, and added a dangerous-direction key-order regression. |
| ARV2FMI-003 | P2 | Corrected | The QC-first parent semantic hash ignores harmless JSON whitespace; after an initial valid load, changed QC bytes could therefore reauthenticate under the same parsed plan identity. | Bound exact QC-plan and stock-spec artifact SHA-256 values in the manifest, retained their original authenticated bytes in loader authority, and refuse both initial and post-load parent-byte changes. |
| ARV2FMI-004 | P3 | Corrected | Parent loader exceptions escaped the fold-manifest API instead of its domain error. | Wrapped QC-first and stock-evaluation authentication failures as `StockFoldManifestError`; exact initial/post-load parent mutation regressions pin the boundary. |
| ARV2FMI-005 | P3 | Corrected | Strict UTF-8 JSON containing an escaped lone surrogate leaked `UnicodeEncodeError` during canonical reserialization. | Canonical rendering now translates all type/value/Unicode failures into `StockFoldManifestError`; the escaped-surrogate regression passes. |
| ARV2-UNRELATED-001 | P3, out of scope | Documented, not fixed | The repository-wide run reaches a pre-existing Target Price test whose expected diagnostic substring is stale: `tests/target_price_revisions/test_preregistration.py::test_self_declared_review_and_registry_substitution_refuse` expects `Git repository`, while the fail-closed implementation now reports `reviewed spec and registry must be committed and clean`. The safety refusal still occurs. | Reproduced directly as **1 failed in 0.68 s** and then deselected exactly for the remaining-inventory run. Per the owner lane restriction, no Target Price code or test was changed. |

Two independent implementation audits end with **zero remaining P0-P3**.
Review-artifact and code quality are **8/10**: the child is narrow,
content-addressed, reproducible, strongly fail-closed, and adversarially
tested, while it is intentionally not yet independently accepted, parent-bound
for execution, or connected to any data/result authority.

### 9.3 Validation and next step

The final focused manifest plus authority-registry battery is **36 passed in
13.31 s**. It regenerates all six folds and 24 horizon boundaries from the
NYSE calendar; recomputes the calendar, section, fold, boundary, and outer
hashes; rejects 17 correctly rehashed semantic weakenings; and covers strict
JSON, BOM/whitespace/key order/surrogate, symlink, loader identity, mutation,
initial/post-load parent tampering, in-load TOCTOU, import closure, and registry
locking. The complete Analyst V2 battery is **432 passed, 1 skipped in
1,163.86 s (19m23s)**. Compileall over the Analyst package and tests exits 0.
The active-document gate passes all **69** assertions before and after final
record stabilization.

The unfiltered 6,838-test repository run exposed one failure at collected item
437 and was stopped to obtain a focused traceback. The exact node reproduces
alone as **1 failed in 0.68 s**: the out-of-scope Target Price assertion in
ARV2-UNRELATED-001 expects an obsolete diagnostic substring while the
production guard still refuses safely. With only that exact node deselected,
the complete remaining inventory is **6,824 passed, 13 skipped, 1 deselected,
25 known dependency warnings in 3,539.17 s (58m59s)**. No Target Price file was
changed. Thus every repository test except the one separately reproduced and
documented out-of-scope assertion passes on the candidate code tree.

The exact next step is independent Claude review of the combined
counter-review plus ARV2-4B push, followed by Codex counter-review. ARV2-4
remains blocked on authenticated source/rights, complete reviewed executable
definitions, run identity, one-use evaluation authority, and separate exact
QC-job authorization. This milestone grants none of those authorities and
does not require the owner to provide credentials now.

## 10. Independent Claude review of the section-8 counter-review and the ARV2-4B fold manifest, 2026-08-31

**Range reviewed:** `c09d8e4c..12b9e61c`, three commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, 0 P2, **1 P3
corrected**, 1 P3 documented. **Zero research looks and zero development
evaluations.** No provider, credential, licensed row, price, return, outcome,
broker, operator-database, QuantConnect, upload, scheduler, order, UI or
Streamlit access occurred.

**Reviewing session:** the personal-identity session that produced sections
4L, 4O and 7. **Quality ratings (ARV2CR9-003 applied):** ARV2-4B candidate
**9/10** - the strongest loader in the lane so far, with one sensitivity gap
on a correction its own ledger called verified; section-8 counter-review
record **8/10** - all four of its findings against my section 7 are fair and
correctly corrected.

### 10.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `a961230a` | Accepted | Codex's counter-review of my section 7. I accept all four findings against my own review: the 11-versus-196 range statement was genuinely imprecise (I reproduced `git rev-list --ancestry-path --count` = 11 and the two-dot count = 196 exactly as corrected); the three stale current-state rows, the omitted quality rating, and the validation-attribution point are all correct. Record-only. |
| `a6887004` | Accepted after correction | The ARV2-4B fold-manifest candidate. Exceptional design: the module derives the entire expected document from the NYSE calendar at import and the loader compares the artifact against that derivation, so the committed bytes cannot drift from calendar truth; non-circularity is enforced in code (the loader refuses if the parent's `fold_manifest_sha256` ever becomes non-null); `parse_constant`, duplicate keys, BOM, byte-canonical form, symlink/stat-identity double reads, and a reload-and-compare reauthentication are all present from the first commit. One test-sensitivity gap corrected below (ARV2R9-001). |
| `12b9e61c` | Accepted | Validation/handoff record. Its honest disclosure of the out-of-lane Target Price failure (ARV2-UNRELATED-001) with exact reproduction is the correct treatment under the owner's lane-scope rule. Record-only. |

### 10.2 Independent verification

Reproduced first-hand rather than accepted from the record:

- **Identity and calendar arithmetic, all exact.** Recomputed
  `arv2-stock-folds-1002155dbe8e3e87` from the id/hash-nulled canonical
  payload; the 3,435-session axis 2013-01-02..2026-08-28 and its SHA-256;
  all fourteen year-first NYSE sessions used as fold anchors (2016-01-04,
  2017-01-03, 2021-01-04, 2022-01-03, 2023-01-03 and the rest); and the
  purge/embargo construction - for the 2020 fold at horizon 20, the effective
  validation start is exactly the 20th session after nominal train end and
  the purge interval contains exactly 20 sessions, both recomputed from
  `data.exchange_calendar` directly.
- **Both parent byte pins verified** against the committed
  `arv2_qc_first.draft.json` and `arv2_stock_historical.structural.json`, and
  the milestone commit touches neither parent - the stock spec's
  `fold_manifest_sha256` remains null, so the lineage stays acyclic.
- **Authority surface probed.** All six capability properties return `False`;
  the capabilities map is all-false and external bindings all-null on the
  loaded object; `dataclasses.replace` cannot even construct a copy
  (`init=False`); a `copy.copy` fails loader-authority reauthentication; the
  transitive import closure is 30 modules including `fold_manifest`, with no
  execution, ML, network or legacy-ACER root; the new
  `_FOLD_MANIFEST_AUTHORITIES` registry is covered by the lock-inventory
  test.
- **Mutation matrix, six reverse mutations:** expected-document match,
  `parse_constant`, byte-canonical form, and the QC-parent byte pin all
  **bit**. The post-load revalidation trio survived and became ARV2R9-001;
  the non-circularity clause survived and is documented as ARV2R9-002.

### 10.3 Findings

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R9-001 | P3 | **Corrected** | `fold_manifest.py` final `_revalidate` trio / `tests/analyst_revisions_v2/test_fold_manifest.py` | ARV2FMI-001's correction - final re-reads of both parents and the manifest after the nested loaders return - had **no revert-detecting regression**: deleting all three `_revalidate` lines left the test file green. The window is real and deterministically reachable: a parent rewritten immediately after its own loader returns is caught only by that trio. The existing TOCTOU tests cover the double-read window inside `_read_stable_regular` and post-load mutation via `require_loaded_stock_fold_manifest`, but not this in-load window - the exact gap ARV2FMI-001 exists to close. | Added a regression that wraps each parent loader to mutate its file immediately after returning, expecting the named `changed after authentication` refusal for both parents. Test-only; no production module changed. | Deleting the `_revalidate` trio turns the new test **red**; restored **green**. |
| ARV2R9-002 | P3 | **Documented, deliberately not fixed** | `fold_manifest.py` parent-lineage check | The non-circularity clause (refuse when the parent's `fold_manifest_sha256` is non-null) also survived mutation, and it is **unreachable today**, not merely untested: a parent artifact carrying a filled binding fails the `PARENT_STOCK_SPEC_ARTIFACT_SHA256` byte pin and the parent loader's own frozen-template match before this clause runs. It becomes the load-bearing guard at exactly the moment a future ARV2-4 successor updates those constants to bind this manifest - that successor's review must add the regression this one cannot construct. Same class as ARV2R7-001 and ARV2R8-001. | None. | Reachability analysis recorded here; both earlier refusals reproduced during the mutation run. |

**ARV2-UNRELATED-001 did not reproduce here:** my unfiltered as-received run
passed with zero failures, and the named Target Price test passes directly in
both a pinned detached worktree and the lane worktree on this host (Python
3.12.13). Codex reproduced the failure on its own environment (Python
3.13.14), so the stale-assertion behavior is environment-dependent rather
than universal. Either way it is another lane's test; per the owner's
lane-scope rule it stays documented for the Target Price lane, now with the
added datum that the failure does not occur on every host.

### 10.4 Validation

- Full suite, exact **as-received** tree `12b9e61c` in a pinned detached
  worktree: **6825 passed, 13 skipped, 25 warnings in 1451.51s (0:24:11)** - zero failures; the out-of-lane ARV2-UNRELATED-001 Target Price assertion did not reproduce on this host (see 10.3).
- Focused fold-manifest file on the final tree: **36 passed in 11.17 s**
  (35 as received plus the new regression). Strict analyst battery: **418
  passed, 1 skipped in 142.25 s**. Active-document gate: **69 passed**.
  Changed-path `compileall` exit 0; `git diff --check` clean; no frozen
  shared file touched; the only change is one test file.
- The new regression and its reverse mutation verified red/green in a
  detached scratch worktree.

### 10.5 Next step

Codex counter-reviews this exact pushed head. The next bounded milestone
after that requires explicit owner authorization; the natural candidates
named by the gate ledger are the global-map/matched-row comparison binding or
the power-plan definition, both still outcome-free. ARV2-4 execution remains
blocked on the recorded source, rights, review, run-identity and one-use
authority gates; every external binding in the fold manifest is null and
every action capability is literal false.

## 11. Codex counter-review of Claude commits `0052df9` and `ba4b3bc9`, 2026-08-31

The clean dedicated worktree fast-forwarded from pushed Codex head `12b9e61c`
to Claude head `ba4b3bc9`. Codex reviewed both new commits under `CLAUDE.md`,
`AGENTS.md`, the two standing review-process documents, the strategy PDF, and
this lane record. No credential, provider, licensed row, outcome, QuantConnect,
broker, deployment, scheduler, or order capability was accessed.

### 11.1 Commit dispositions

| Commit | Disposition | Counter-review basis |
|---|---|---|
| `0052df9969b8f38b96f48f7c314342ba8c125996` | **Accepted after correction** | The two parent-mutation cases genuinely pinned their corresponding final byte revalidations, but the claimed three-file coverage omitted the manifest and the shared `monkeypatch.undo()` removed repository-wide autouse isolation. The corrected parameterized regression uses a fresh fixture instance for each of QC parent, stock parent, and manifest. |
| `ba4b3bc9eb5d2ff492dd5162aa05474655d7dc70` | **Accepted after correction** | The independent calculations, fold geometry, authority checks, and ARV2-4B 9/10 quality assessment reproduce. Its current-state handoff and ARV2R9-001 verification claim required reconciliation with the completed review and the exact test coverage. |

The Claude review artifact rates **7/10** because its production assessment was
strong but its only correction overclaimed regression coverage and weakened
test isolation. The underlying ARV2-4B structural candidate remains **9/10**:
its fold geometry, content identity, zero-access boundary, and fail-closed
behavior remain intact after correction.

### 11.2 Counter-review issue ledger

| ID | Pri | Status | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|
| ARV2CR10-001 | P2 | **Corrected** | The canonical stock-formula, preregistration, architecture, lifecycle, and exact-next-step passages still described already-completed ARV2-4A/4B reviews as pending. A later machine could repeat a completed stage or infer the wrong gate. | Reconciled every current-state passage with sections 7-11 and recorded the real next owner-definition gate without changing immutable artifact bytes. | Active-document gate and direct stale-phrase search on the corrected record. |
| ARV2CR10-002 | P3 | **Corrected** | Claude's regression and section 10 claimed to pin the final QC-parent, stock-parent, and manifest revalidation trio, but mutated only the two parents. Bypassing only manifest revalidation left all 36 fold tests green. | Replaced the two-stage test with three isolated parameter cases that mutate QC parent, stock parent, or manifest inside the nested-load window. | Correct production gives three named domain refusals; selectively bypassing each corresponding revalidation turns its case red. |
| ARV2CR10-003 | P3 | **Corrected** | The test called fixture-wide `monkeypatch.undo()` midway, which also removed the autouse execution-runtime isolation patches before the second case. No executor path ran, but the test violated repository isolation. | Parameterization gives each case a fresh fixture lifecycle and removes manual undo entirely. | Source inspection and the complete Analyst battery. |
| ARV2CR10-004 | P3 | **Corrected** | A QC parent disappearing immediately after its authenticated nested load failed closed but leaked raw `FileNotFoundError` from a final strict path resolution instead of `StockEvaluationContractError`. | Normalized that narrow disappearance race to `QC-first parent changed or disappeared` and added a deterministic regression. | Focused corrected loader regressions and complete Analyst battery pass. |

Totals: **0 P0, 0 P1, 1 P2, 3 P3; all corrected, none unresolved.**
The future non-circular parent-binding guard remains deliberately unreachable
behind the exact current parent byte pins, as ARV2R9-002 records; its first
successor must add a reachable regression when those pins change.

### 11.3 Validation and authority boundary

- Focused fold-manifest file plus the parent-disappearance regression: **39
  passed in 10.11 s**.
- Complete `tests/analyst_revisions_v2` directory: **332 passed, 1 skipped in
  102.77 s**.
- Active-document gate: **69 passed in 0.99 s**. Changed-path `compileall` exit
  0; `git diff --check` clean; only the four intended Analyst files changed.
- Structural fixtures only; **0 research looks and 0 development evaluations**.
  Every source/outcome/QC/deployment/order capability remains false.

### 11.4 Owner decision and stop point

The loop cannot safely call either remaining definition a completed milestone
without an owner policy choice. The recommended next milestone is the
global-map/matched-row binding because the blueprint makes that comparison a
stock signal gate, but the blueprint does not define the exact global rating
vocabulary or numeric scores. The alternative power-plan milestone likewise
requires exact effect-size, power, coverage, component, and underfill choices.

Codex therefore commits this counter-review locally and stops before the next
milestone and before push. The owner must choose one path and approve its exact
substantive definition; a null scaffold is not completion. Neither choice needs
QC credentials or a Massive/Benzinga API key. All later data, rights, outcome,
QC job, paper, funded, and trading gates remain separate.

## 12. Codex counter-review of Claude's ARV2-4C proposal advisory, 2026-09-01

Claude reviewed the owner-visible `ARV2-4C-GLOBAL-v1` proposal rather than a
commit. The supplied review summary identifies lane head `ba4b3bc9`, reports no
repository change, and disposes the proposal **ACCEPT AFTER CORRECTION** with
six P2 and two P3 findings. Codex independently checked every finding against
the visually inspected relevant PDF sections, the exact frozen JSON and Python
contracts, the fold-manifest loader, stock formulas and tests, and the retained
archived V1 proposal/review evidence. No provider or outcome source was opened.

**Counter-review disposition: ACCEPTED AFTER CORRECTION.** The advisory found
several real underspecifications, but four of its corrections were incomplete
or unsafe as written. The proposal remains unapproved and unimplemented.

### 12.1 Claude finding dispositions

| Finding | Counter-review disposition | Basis and required correction |
|---|---|---|
| `ARV2P-001` P2 | **Partially correct** | The paired constant-arm convention cannot override the frozen single-arm `constant_score` refusal, and the paired bootstrap axis needs an explicit successor contract. However, the existing fold manifest must not be re-pinned: the recorded DAG is PDF -> QC plan -> stock spec v1 -> reviewed fold manifest. Stock spec v2 may bind its predecessor and that existing child. Re-parenting the child to v2 while v2 binds it would create a cycle. `ARV2R9-002` becomes reachable only if the fold loader's parent pins change; the v2 loader instead needs its own acyclic-ancestry regression. Common valid differences and an uncompressed complete-session resampling axis are compatible once stated separately. |
| `ARV2P-002` P2 | **Partially correct** | Preserve the already frozen exact zero margin. Call the rule a **zero-margin no-worse-with-confidence gate, operationally equivalent to a one-sided superiority boundary in nondegenerate samples**. It is not literally strict superiority because the registered `>= 0` comparisons permit exact equality. The margin cannot be relaxed after outcomes. |
| `ARV2P-003` P2 | **Partially correct** | The full owner proposal enumerated all 38 quarantined strings; only the abbreviated Claude-review message used “remaining aliases.” The retained archive verifies only aggregates: 584,916 V1 events, a 54-string union, and 99.567% top-19 current-label coverage. No committed per-string count table exists, and that all-event/current-label statistic is not the V2 denominator for firm-admitted directional endpoint pairs. The map must enumerate every string and disposition, but exact V2 counts require a separately authorized, content-addressed, outcome-free source census. They must not be invented or imported as already available authority. |
| `ARV2P-004` P2 | **Confirmed** | Freeze each fold's complete ordered test-session axis; all noncircular 20-session starts; draws per fold; final-block truncation; missing markers; equal-occurrence mean over available centered differences with sampling multiplicity; an empty-resample locked refusal with no redraw; Type-7 quantile; and a dependency-independent hash-counter sampler including rejection sampling rather than an unspecified PRNG/modulo conversion. |
| `ARV2P-005` P2 | **Partially correct** | Mapped delta, decayed mass, raw score, institution/catalyst breadth, conservative `N_eff`, reliability, sector normalization, fit coefficients, and residuals are per-arm; identities, activity evidence, `q_data`, ages, controls, folds, and outcomes are shared. A collapse-zero event stays active but has zero mass and cannot increase `N_eff`. The proposed blanket zero-MAD-sector override is rejected: MAD can be zero for a nonconstant vector such as `0,0,1`. Only an exact zero-range arm (`min == max`) may totalize to paired-only zero scores. Zero MAD with nonzero range remains a joint refusal charged to coverage; shared-control zero MAD still refuses. |
| `ARV2P-006` P2 | **Confirmed after staging clarification** | Pre-outcome event, active-row, component, and score-capable-date coverage may use no outcome availability, value, or dispersion. Post-join validity separately requires exact outcome identity, at least 20 identical rows, the paired constant-score rule, and `max(50, bound power-plan required dates/components)`. Outcome mismatch is `INVALID_DATA`; honest post-join underfill is `INCONCLUSIVE_locked_no_extension`; an adequate-sample gate failure is `FAIL_closes_family`. No outcome-informed map, fold, period, seed, or retry change is permitted. |
| `ARV2P-007` P3 | **Partially correct** | The PDF explicitly names `sector perform` as ambiguous, so it may differ deliberately from `market perform`, but the owner-visible basis must be stated; `in-line` likewise remains a conservative refusal unless separately approved. Printable-ASCII-only handling and exact refusal of `equal weight` were already deterministic in the full proposal. Dividing legacy tiers by two is a positive affine range alignment and is Spearman-inert for fixed membership/ties; the successor must document and regression-test that property through the full homogeneous path. |
| `ARV2P-008` P3 | **Confirmed** | Bind non-rescuing counts and exact denominators for tier-collapse events, per-arm totalized-zero dates, both-arm constant refusals, unmapped/quarantined pairs, and empty bootstrap replicates. The seed record must transitively or directly bind the successor stock spec, map, matched-row contract, fold manifest, evaluation ID, and sampler version. |

### 12.2 Counter-review findings against the advisory

| ID | Pri | Status | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|
| `ARV2CRP-001` | P2 | **Corrected in disposition** | Claude required a fold-manifest re-pin and said `ARV2R9-002` automatically becomes reachable. Re-parenting a content-addressed child to the successor that binds it risks the exact hash cycle ARV2-4B prevents. | Preserve the reviewed child unchanged. Stock spec v2 binds both stock spec v1 and the existing fold manifest; add a v2 acyclic-ancestry regression. Retain `ARV2R9-002` for an actual future fold-loader parent change. | Lane-record lineage at section 9.1 and direct inspection of `fold_manifest.py`'s exact old-parent pins and null-parent guard. |
| `ARV2CRP-002` | P2 | **Corrected in disposition** | The advisory called a 54-string per-label count census “already reviewed,” but the repository retains only aggregate V1 claims and the 39 mapped/15 refused vocabulary. Treating unavailable per-string counts as bound V2 evidence would weaken provenance and could smuggle licensed legacy measurements into a new authority artifact. | Separate exact policy dispositions from measurements. Record the aggregate archive only as historical risk context; require separate source authority and a content-addressed V2 pre-outcome census before claiming counts or paired coverage. | Repository-wide searches find the aggregate review evidence and vocabulary but no committed per-string count table or reproducible census artifact. |
| `ARV2CRP-003` | P2 | **Corrected in disposition** | “Zero MAD -> all-zero z” is unsafe because MAD zero does not imply a constant signal. It can erase genuine minority variation and bias the global arm downward. | Totalize only exact zero range. Preserve fail-closed zero-MAD handling when range is nonzero, with symmetric paired refusal and coverage charge. | Hand example `0,0,1`; production formula returns `zero_mad` whenever MAD is zero, and the existing regression pins refusal without epsilon or market fallback. |
| `ARV2CRP-004` | P2 | **Open owner-design issue; blocks freeze** | The advisory did not challenge the central selection risk in the proposed 16-label core map. It quarantines 23 aliases that the archived 39-label coarse baseline mapped. Joint exclusion can censor exactly the firm-idiosyncratic cases the firm ontology is intended to improve; a 95% volume gate does not eliminate composition bias. | The revised proposal must make an explicit owner choice between faithfully reproducing the full 39-alias legacy global comparator and using a new conservative-core comparator. Codex recommends the full legacy comparator, clearly labeled a naive benchmark policy rather than firm semantics, plus label/pair/fold composition diagnostics. No choice is inferred here. | Mechanical comparison of the full proposal's 16 allowed labels with the archived 39 mapped aliases; PDF section 7.3 retains the original global map as the comparison baseline. |
| `ARV2CRP-005` | P3 | **Corrected in disposition** | The advisory overstated two labels: common valid dates and complete-session blocks are not inherently contradictory, and a zero-margin inclusive lower-bound gate is not literally strict superiority in the degenerate equality case. | Separate estimand dates from the resampling axis and use exact zero-margin terminology without reopening the frozen margin. | Direct comparison of the parent strings and the registered inclusive inequalities. |

Totals against the advisory: **0 P0, 0 P1, 4 P2, 1 P3**. Four are
corrected in this counter-review record; `ARV2CRP-004` remains a substantive
owner-design blocker. The advisory rates **6/10**: it correctly stopped an
underdefined freeze and found the most important bootstrap/coverage seams, but
its lineage cascade, zero-MAD remedy, census provenance, and comparator-sample
selection analysis were not reliable enough to implement directly.

### 12.3 Revised statistical and coverage conclusions

The existing single-arm IC inventory keeps its current refusal rule. The
successor may add only this paired estimand:

- fewer than 20 identical rows or a constant shared outcome: joint refusal;
- neither score constant: ordinary average-rank Spearman for both arms;
- exactly one score constant: that arm's paired association is exact zero and
  the other arm receives ordinary Spearman;
- both scores constant: joint `both_arms_constant_score` refusal;
- no pairwise imputation or one-arm row removal.

The zero is a registered paired association, not a valid single-arm Spearman
observation. At the sector-score stage, exact zero range may analogously emit
paired-only active zero scores; nonconstant zero-MAD vectors still refuse.

Bootstrap centering uses the observed equal-valid-date mean
`D = mean(IC_firm,t - IC_global,t)`. Resampling operates on each fold's full
NYSE test-session axis, preserves missing/refused markers, uses noncircular
20-session blocks wholly inside the fold, and takes the equal-occurrence mean
of available centered differences after sampling. Missing positions add
neither zero nor denominator. An empty replicate is a locked refusal, never a
redraw. The Type-7 95th percentile defines `LCB95 = D - q95`; passing still
requires `D >= 0` and `LCB95 >= 0`. A canonical hash-counter sampler must pin
digest inputs, fixed-width indices, rejection counter, unbiased start-index
conversion, and the sampler domain/version.

Coverage has two non-interchangeable stages. Outcome-free readiness measures
events, active rows, components/member incidence, and pre-outcome candidate
dates using authenticated signal inputs only. It gates whether an outcome run
may launch. After the single authenticated outcome join, exact identity parity
is mandatory and the valid-date/component floor becomes
`max(current frozen floor, bound power-plan floor)`. Post-join underfill cannot
be repaired by a mapping, fold, period, seed, or retry change.

### 12.4 Vocabulary and evidence conclusion

The retained archive establishes a 54-string V1 union and a proposed
case-insensitive/whitespace-collapsed 39-mapped/15-refused global table. Its
99.567% figure covers the top 19 **current-rating strings over all V1 events**;
it does not measure V2 firm-admitted upgrade/downgrade endpoint-pair coverage,
fold coverage, identity coverage, or direction consistency. The new global
resolver's canonicalization is itself a policy and must state collision groups.

The original 16-label proposal is deterministic, but it is not demonstrated
to be the least biased comparator. Before approval, the owner must explicitly
choose whether the benchmark reproduces all 39 legacy aliases or uses the
narrow core despite its selective-exclusion risk. Codex recommends the full
39-alias baseline for the comparison only, with ambiguous labels marked as
naive benchmark policy rather than production firm semantics. Future exact V2
counts and the 19/20 paired-coverage decision require separately authorized
source-only evidence; no counts are inferred here.

### 12.5 Authority and next step

No map, matched-row contract, successor stock spec, fold-manifest modification,
bootstrap implementation, source census, or outcome result was created. The
owner's requested complete Claude module review now precedes a revised ARV2-4C
approval. That review must use the exact pushed same-lane snapshot and must not
implement ARV2-4C, access credentials/provider rows/outcomes, run QC, or begin
paper/funded execution. After its push, Codex counter-reviews every Claude
commit. Only then should the corrected global-map proposal return for owner
approval.

### 12.6 Validation

This was a record-only counter-review; no production or test code changed. The
final active-document gate passed **all 69 tests**, and `git diff
--check` was clean. Runner discovery first confirmed that this lane checkout
has no local virtual environment, the bundled document Python has no `pytest`,
and the default sandbox temp root was inaccessible; those preflight attempts
executed no product assertions. The successful run used the repository's
existing sibling-worktree virtual environment with an explicit writable
base-temp directory. No broader code suite or compile step was warranted for
unchanged code. No research look or development evaluation was consumed.

## 13. Complete independent whole-lane re-review, 2026-09-01

**Scope:** the entire Analyst Revisions V2 lane, superseding the milestone-only
reviews in sections 4L-12. Every prior acceptance, count, hash, and recorded
correction was treated as a claim to verify, not evidence to trust.

**Review base / head:** lane parallel baseline
`c9dcdb647914acbfcefce187a138f52fcdad0c68` (parent
`6156ef9b92737c9b390a96d286b0fbde4ff4b19c`) through the exact fetched pushed
head `e4d7f4396e9d8fe7b601339f53f587bed1d63d6a`
(`origin/codex/strategy-analyst-revisions-v2`). The remote did not move during
the review. The two commits after the last milestone review, `9f8377cf`
(Codex counter-review of ARV2-4B) and `e4d7f439` (Codex advisory
counter-review of the ARV2-4C proposal), are now part of the reviewed
snapshot.

**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, **3 P2 corrected**,
4 P3 corrected, and **11 findings documented and deliberately not fixed
(3 P2, 8 P3; `ARV2WL-D11` is out of lane)**. **Zero research looks and zero
development evaluations.** No provider,
credential, licensed row, price, return, outcome, broker, operator-database,
QuantConnect, upload, scheduler, order, UI or Streamlit access occurred at any
point in the review, and none was reachable: every production authority is
empty or zero-access and every action capability is literal false.

**Lane quality rating: 8.5/10.** The fail-closed architecture is genuinely
strong - content-addressed everything, out-of-band weakref authority
registries, exact Decimal/Fraction arithmetic, exhaustive refusal taxonomies,
and a real transitive import firewall. Points off for three latent
fail-open/consistency defects that had passed nine prior review rounds
(a whole-census ingest crash, an unenforced "read-only" git boundary, and an
evadable dynamic-import walker), and for a large block of dormant ETF/portfolio
arithmetic that is verified-correct but has no behavioral regression net for
the day its zero-access gate is lifted.

### 13.1 Method

Six independent audit lenses read every file under
`research/analyst_revisions_v2/` and `tests/analyst_revisions_v2/` line by
line, plus the shared-boundary dependencies, and executed forge, GC-id-reuse,
NaN, timing, and arithmetic probes against the exact committed bytes. I
personally re-derived every authority hash, the PDF hash, the full
PDF-to-code deviation table, and each material finding before correcting it,
and mutation-verified six behavior-changing or test-gap corrections red then
green. `ARV2WL-005` was an intentionally behavior-equivalent consolidation:
reverting the delegation restores the identical inline stable-sort/sum rule,
so it was verified by direct equivalence inspection and the 58-test
stock-signal file, not by a red behavioral mutation. The PDF SHA-256 is
`eae7b995...c616193` and matches the governing record. The 271,570-byte file
contains **64 physical pages**: one unnumbered cover, six roman-numbered
front-matter pages (`i` through `vi`), and 57 Arabic-numbered strategy-body
pages (`1` through `57`); all physical pages were included in the review.

### 13.2 Commit-disposition table

The lane history from the baseline to the review head contains **51 commits
that touch Analyst V2 implementation, specification, test, or lane-record
paths** (the ordinary two-dot count to `main` is larger only because the two
`main`-sync merges import unrelated commits; those are excluded here as
imported, not lane work). Four commits are **exact patch-id duplicates** of
earlier lane commits, re-applied during the 2026-08-26/27 shared-remediation
synchronization; each is confirmed byte-identical via `git patch-id --stable`.
The reviewed disposition of every commit is **accepted or accepted-after-
correction**; the per-milestone corrections are recorded in sections 4L-12 and
the three additional lane-wide corrections below apply to the cumulative tree.

| Commit range | Milestone | Disposition | Where reviewed |
|---|---|---|---|
| `e13baa1`, `ee17967`, `905c781` + patch-id twins `49fe8e8`/`130af4c`/`7029acb` | Fail-closed authority layer + remediation sync (duplicate pair) | Accepted | 4A-4B; twins verified patch-identical |
| `66168ed` + twin `653a9c0`, `d8d0ad6`, `c167574`, `5a5c7ab`, `bd3393d`, `7f493d1`, `c83782d` | Decimal-contract hardening, portfolio-rounding sync, remediation review/counter-review | Accepted | 4A-4B; twin patch-identical |
| `b912459`, `1507777`, `31c313e` | ARV2-0 owner-decision freeze + review/counter-review | Accepted | 4C-4D |
| `6f23244`, `31a2b64`, `0fb7998` | ARV2-1 ingest/ontology + review/counter-review | Accepted | 4E-4G |
| `56d6fe0`, `f592334`, `a597ac3` | ARV2-2 PIT identity + review/counter-review | Accepted after correction | 4H-4J |
| `8701880`, `6e8edab`, `12157dd`, `9309de3` | ARV2-3 stock scoring + review/counter-review | Accepted after correction | 4K-4M |
| `f724bf9`, `39104f6`, `f2c15d8`, `e53ba26` | ARV2-3Q QC-first + review/counter-review | Accepted after correction | 4N-4P, 8 |
| `c334571`, `37dc424`, `33d40f1`, `3aedfff`, `c16f7f4` | ARV2-4A prerequisites + review/counter-review/records | Accepted after correction | 4Q-4S |
| `4ef736b`, `d9de03d`, `43224495`, `7a7757a`, `d9b05eb`, `64ccf25`, `ef1a525` | Two `main`-sync merges + conflict-review records | Accepted | 6, 7 |
| `c09d8e4`, `a961230` | ARV2-4A/sync review + counter-review | Accepted | 7, 8 |
| `a6887004`, `12b9e61`, `0052df9`, `ba4b3bc9`, `9f8377cf` | ARV2-4B fold manifest + review/counter-review | Accepted after correction | 9-11; 13.4 below |
| `e4d7f439` | ARV2-4C proposal advisory counter-review | Accepted | 12; record-only |

### 13.3 Authority chain, recomputed independently

Every hash in the chain PDF -> QC-first plan -> stock-evaluation spec ->
fold manifest was recomputed from the committed bytes without using the
production serializer as the oracle, and every one matched:

- QC-first plan `arv2-qc-first-plan-36e455e72b8750fe` - content hash and
  content-derived id both exact.
- Stock-evaluation spec `arv2-stock-historical-c5ff2a6a0dcf341e` - content
  hash exact; its `history_definition` section hash exact; its
  `fold_manifest_sha256` is **null**, so the lineage is acyclic.
- Fold manifest `arv2-stock-folds-1002155dbe8e3e87` - content hash exact; both
  parent artifact-byte pins (`8339238d...`, `34d1e715...`) match the committed
  parent bytes.
- Round-0 predecessor `arv2-round0-candidate-8d13a0a4577df322` - exact.
- All committed registries (`firm_ontology`, `security_master`,
  `research_source_authority`, and the rest) are **LF-only and empty**; every
  external binding is null and every capability literal false. Forge probes
  (pickle, subclass, `object.__new__`, deepcopy, caller-supplied hash,
  in-place mutation, GC id-reuse over 200k attempts) were all refused, and
  every authority-registry access sits under its `RLock`.

### 13.4 The ARV2-4B counter-review (`9f8377cf`), independently verified

`9f8377cf` was not covered by any prior section. It **strengthened** every
guard it touched: it normalized a raw `OSError` on QC-plan disappearance into
the typed `StockEvaluationContractError` refusal, and it rewrote my
`0052df9` in-load TOCTOU regression from two mutation targets to a three-way
parametrization (QC parent, stock parent, and now the manifest itself). I
confirmed from the code that each parametrized case remains caught
**exclusively** by its corresponding final `_revalidate` line, so the
strengthened test is still fully sensitive to deleting that trio. No guard or
test was weakened. Accepted.

### 13.5 Corrections (this review)

All seven are inside `research/analyst_revisions_v2/` or its tests; no other
lane, shared execution/assistant/risk path, or frozen document was touched.

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2WL-001 | **P2** | **Corrected** | `ratings_ingest.py` `_parse_source_row` | The per-row provider-field length screen used 2048 (8192 for `notes`) while `BenzingaRatingRecord.__post_init__` re-checks the same text at the canonical 256-char bound. A firm/analyst/rating/target value of 257-2048 characters therefore passed per-row screening and then raised a `CanonicalEvidenceError` during record construction **outside** the `_RowRefusal` handler, halting the entire snapshot census - one malformed provider row denies the whole ingest. This violates the lane's own "exactly one accepted row or named refusal per source row" contract. Fail-closed (no leak), hence P2 not P1. | Bounded the five affected parse sites (`firm`, `analyst`, `rating`, `previous_rating`, `price_target_action`) at 256 to match the record contract, so an over-long value becomes one `INVALID_PROVIDER_FIELD` refusal. | Added `overlong_firm`/`overlong_rating` cases to the one-named-refusal-per-defect battery; both **red** on the unbounded screen (whole-audit crash), green after. |
| ARV2WL-002 | **P2** | **Corrected** | `dataset.py` `read_git_text`/`read_git_bytes` | The helpers' docstrings claim "read-only Git query" but nothing enforced it: caller-controlled `arguments` flowed straight into `subprocess.run(["git","-C",root,*arguments])`, so a caller could reach mutating subcommands (`push`, `update-ref`) or inject configuration/executables via `-c alias.x=!cmd` or `--exec-path`. Every current in-repo caller uses fixed read-only subcommands, so this is a latent boundary-not-enforced-by-code defect, exactly the "comments claiming guarantees not enforced by code" hazard CLAUDE.md forbids. | Added a six-member read-only subcommand allowlist (`cat-file`, `ls-files`, `merge-base`, `rev-parse`, `show`, `status`) enforced at both runners; the first token must be an allowlisted subcommand, which also blocks global-option injection because Git parses those only before the subcommand. | New regression drives `push`/`update-ref`/`-c alias`/`gc`/empty; all **red** before (they ran), refused after. Every existing git-dependent battery (security master, preregistration, dataset) still green. |
| ARV2WL-003 | **P2** | **Corrected** | `import_firewall.py` dynamic-import walker | The transitive-closure walker detected only the two friendly dynamic-import spellings (`importlib.import_module`, bare `__import__`). It was evadable six ways proven by execution: `builtins.__import__(...)`, a rebound `il = importlib`, `getattr(importlib,'import_module')(...)`, `getattr`-result assigned to a variable, and the builtins equivalents. A future execution-capable module could reach `execution`/`requests`/`socket` through any of these while the closure reported clean - a false green on the very evasion the walker's docstring claims to stop. No current module uses any dynamic import, so latent. | Hardened the walker: track `builtins` aliases and `__import__` attribute access; detect `getattr(<importlib|builtins>, "import_module"|"__import__")` both as a direct call and when its result is assigned to a variable; and follow simple rebinding of the import machinery to a local name. | Added all six evasion forms to `test_dynamic_imports_cannot_bypass_the_firewall`; all **red** before the fix, all refused after; reverting the walker reddens four. The 30-module closure is unchanged and still reaches no execution/ML/network/legacy-ACER root. |
| ARV2WL-004 | P3 | **Corrected** | `formulas.py` `NUMERICAL_ZERO` | The single 1e-18 use site (the inverse-Herfindahl 0/0 guard in `effective_contributors`) had its boundary untested; the nearest test probed only 1e-12, so the threshold could be widened anywhere below that - a genuine hidden epsilon - with the suite green. | Pinned the exact inclusive boundary: at 1e-18 -> 0, just above -> counts, and the gate is on the summed mass not per-value. | New regression passes; matches my own probe. |
| ARV2WL-005 | P3 | **Corrected** | `stock_signal.py` `_stable_sum` | A verbatim second copy of `formulas._stable_decimal_sum` (the authoritative permutation-invariance rule for raw-score summation); two copies can drift (CLAUDE.md consolidation rule). | Delegated `_stable_sum` to the formulas module. | Full stock-signal file (58 tests) green after consolidation. |
| ARV2WL-006 | P3 | **Corrected** | `test_stock_evaluation_and_controls.py` | The ambient-Decimal-context regression covered `build_preopen_control_cross_section` only; a future edit dropping a `localcontext` inside `_solve_ols` or the frozen application would not have been caught. | Added a regression running the full fit + apply pipeline under hostile low/high-precision ambient contexts and asserting identical model and batch hashes. | Passes; inputs are built once under the normal context so only the production path runs under the hostile contexts. |
| ARV2WL-007 | P3 | **Corrected** | `availability.py` timing guards / `test_analyst_revisions_v2_contracts.py` | Two safety-critical PIT guards were untested: `derive_event_availability`'s "provide exactly one of public_at or public_date" mutual-exclusivity (no test anywhere) and two of the three `prove_timing_order` ordering branches (only `effective>published` was covered). | Added regressions for both-clocks/neither-clock refusal and for the `published>available` and `available>ingested` branches. | All three new cases green; each targets a previously uncovered guard. |

### 13.6 Documented, deliberately not fixed

| ID | Pri | Location | Observation and why not fixed here |
|---|---|---|---|
| ARV2WL-D01 | **P2** | `holdings.py`, `costs.py`, `portfolio.py` | **Dormant ETF/portfolio arithmetic has essentially no behavioral test coverage.** `portfolio_transaction_cost`, `mapped_candidate_coverage`, the `weighted_stock_score` success path, `_allocate` (the 20/40/30 caps and water-filling), and `construct_portfolio`'s hysteresis/eviction are all verified correct by independent execution against hand arithmetic, but only their zero-access refusals and low-level parsers are tested in-tree. When the ARV2-5 milestone lifts the zero-access gate (a one-file registry change), this arithmetic goes live with no regression net. Not fixed here because a clean behavioral test requires source-registry-bypass infrastructure that does not exist and would effectively pre-build the ARV2-5 harness - broadening this review. **The ARV2-5 milestone must build that harness and add coverage before any nonempty portfolio can be produced.** |
| ARV2WL-D02 | **P2** | `docs/Archive/Review/REMEDIATION_2026-08-26_ANALYST_AND_FULL_PROJECT.md:822,925` | The archived remediation record's "Regression evidence" names exactly three tests: `test_weighted_score_requires_loader_authenticated_exact_score_artifact`, `test_stock_score_artifact_refuses_missing_extra_duplicate_and_invalid_rows`, and `test_stock_score_authority_refuses_clone_mutation_substitution_and_foreign_context`. A `git grep` across every local ref restricted to `tests/` found zero test-file hits for all three; their retained appearances are documentation only. Partial parser-level analogues exist, but the named weighted-score-level regressions do not. The archived report remains frozen history, so this is an owner-visible record-integrity gap rather than an in-place archive rewrite. |
| ARV2WL-D03 | P3 | `holdings.py:703` | The 99% mapped-coverage gate divides `mapped/denominator` (rounding at precision 50) before `coverage >= threshold` rather than comparing exactly. With ~50-significant-digit weights (which `_source_decimal` admits) this fails open by up to ~1e-50. Unreachable with realistic weights and behind the zero-access gate. The exact fix for ARV2-5 is to decide eligibility on `Fraction(mapped)` vs `Fraction(threshold)*Fraction(denominator)`; documented rather than applied unregressed to dormant code. |
| ARV2WL-D04 | P3 | `portfolio.py:928-968` | An evicted incumbent or a coverage-refused entrant is dropped from the decision with no `ForcedExit`/underfill record, so downstream research must diff `previous_holdings` to reconstruct implied exits. Conflicts with the "record refusals and underfill" discipline; a decision-artifact design point for ARV2-5. |
| ARV2WL-D05 | P3 | `portfolio.py:716` | `_allocate` uses a local `1e-18` tolerance that also grants a permissive `weight <= cap + 1e-18` slack on the hard caps. Negligible (1e-18 of NAV) but is not a named policy constant and could drift from the policy hash; fold into a named constant at ARV2-5. |
| ARV2WL-D06 | P2 | `import_firewall.py` | Beyond the dynamic-import evasions closed in ARV2WL-003, the Analyst firewall is a **denylist**: `os.system`, `eval`/`exec` reassignment, and stdlib modules such as `ctypes` are not caught, whereas the Target Price lane's sibling firewall is an allowlist that catches all of them. Closing the import-machinery half was in scope; converting the whole firewall to the allowlist model is a lane-architecture change (it would alter the closure computation) that should be an owner-scheduled consolidation, ideally adopting the Target Price implementation to remove the two-implementation drift. |
| ARV2WL-D07 | P3 | `ratings_ingest.py:1009` | `FirmRatingNormalizationResult.__post_init__` does not verify `events + refusals == source census` (its `source_audit_sha256` is format-checked only), unlike its sibling result types. The only in-repo consumer revalidates first, so latent; add the census invariant when the ontology production catalog is populated. |
| ARV2WL-D08 | P3 | `snapshot.py:504` | `load_snapshot` reconciles only the `pages/` inventory; unauthenticated sidecar files elsewhere in the snapshot root are admitted into a `VerifiedSnapshot`. No data flows from them today; tighten to an exact-root inventory like `load_normalized_dataset` when production capture is authorized. |
| ARV2WL-D09 | P3 | `stock_signal.py:1247-1275,1302-1307`, refusal scopes | **Partially withdrawn by Codex counter-review.** The initiation/out-of-universe portion was a false alarm: the frozen topology is explicitly rating-changes-only, keeps initiations, target-only actions, and terminations outside that channel, and defines structural zero over admitted PIT rating-change contributions. Skipping those rows is therefore correct. The retained non-blocking observation is that per-security missing/late/ambiguous sector-classification failures use `RefusalScope.GLOBAL` with a security ID, while data-quality failures use `RefusalScope.SECURITY` and then sector fallout. Because the classification path intentionally refuses the whole cross-section, this is diagnostic-scope consistency only, not an admission or score-correctness defect. |
| ARV2WL-D11 | P3, out of lane | `tests/test_sleeve_report.py:246` | Two three-sleeve-engine (Trading App) tests fail on today's date (2026-09-01): a fixture lot's `days_to_long_term` computes to 0, breaking `assert 0 < days_to_long_term <= 30`. A time-relative fixture with no fixed clock; imports nothing in the Analyst lane and fails identically with this review's changes stashed. Documented per the owner lane-scope rule; belongs to whoever owns the three-sleeve engine. |
| ARV2WL-D10 | P3 | `stock_evaluation_contract.py:839`, `data/exchange_calendar.py` | The standalone contract loader's canonical-bytes check omits `sort_keys`, so a root-key-reordered file shares one `spec_id` with different bytes (mitigated in the composed path by the manifest's byte pin); and `exchange_calendar.py` has no dedicated behavioral test (DST/half-day opens are pinned only indirectly). Shared/consumer-safety items for a future coordinated change, not lane-blocking. |

### 13.7 Point-in-time, leakage, and refusal-accounting verdict

Verified sound across all lenses and my own probes: the exact-open rule is
strictly-after (an event published at 09:30 ET is eligible only next session,
tested at the exact instant); date-only evidence takes the second session
strictly after, tested across weekends and holidays; the two evidence forms
are mutually exclusive (now regression-pinned, ARV2WL-007); `session_open_instant`
is DST-correct (14:30Z EST vs 13:30Z EDT verified at both 2021 transitions);
pre-2013 rows are quarantined with an exact named refusal that cannot be
laundered through a later partition; ticker reuse and cross-exchange ambiguity
refuse rather than first-wins; no current-ticker or successor joins exist;
future interval-closure knowledge is redacted; and terminal-return
requirements raise rather than silently omit. The firm normalization formula
is exactly `2*(rank-1)/(K-1)-1` in `Fraction` arithmetic (verified for K=2,3,5
including endpoints); the decay, `N_eff/(N_eff+3)*q_data` reliability, the
1.4826 MAD scale, the `sqrt(C)*min(1,sqrt(N_eff/5))` ETF factor, and the
conservative-minimum breadth all match hand computation, with `q_data` applied
exactly once. The event taxonomy is closed - non-change actions can never
carry a rating change and initiations receive no invented neutral prior. The
global map is **not implemented** at this head (only null-hash slots in the
stock spec and the ARV2-4C proposal reviewed in section 12); I did not invent
or implement it.

### 13.8 Milestone definition-of-done assessment

- **ARV2-0** (owner-decision freeze): satisfied - all eight cells frozen,
  content-addressed, reviewed.
- **ARV2-1** (ingest + firm ontology): satisfied for its structural scope;
  production ontology registry committed empty by design.
- **ARV2-2** (PIT security identity): satisfied; production security-master
  registry empty; ARV2WL-D07 is a latent hardening for when it is populated.
- **ARV2-3 / ARV2-3Q** (stock score + QC-first resequencing): satisfied as
  outcome-free structural candidates; residualization deliberately blocked.
- **ARV2-4A** (evaluation prerequisites): satisfied structurally; the control
  fit/apply path is sound and now more fully ambient-context-pinned.
- **ARV2-4B** (fold manifest): satisfied; acyclic, content-addressed,
  strongly fail-closed.
- **ARV2-4C** (global map): **proposal only, unimplemented and unapproved**
  (section 12). Later milestones (ETF reverse index, ETF aggregation,
  walk-forward, QC parity, paper) remain structural or unbuilt.

No milestone claims market edge; every "evidence" is fixture behavior only;
the sole prospective paper look is unspent; the retired historical look
refuses as superseded-unspent.

### 13.9 Validation

- Focused, all changed subsystems on the final tree (ratings ingest, dataset/
  firewall, stock evaluation/controls, stock signal, contracts):
  **219 passed in 93.70 s**.
- Complete repository suite on the exact final tree: **2 failed, 6838 passed, 13 skipped, 25 warnings in 1197.08s (0:19:57)** in a pinned base-temp. The only failures are the two out-of-lane
  `tests/test_sleeve_report.py` cases in ARV2WL-D11 below; every Analyst
  test passes. Both fail identically with my changes stashed, confirming
  they are pre-existing and unrelated to this review.
- Six mutation-sensitive corrections were verified red then green.
  `ARV2WL-005` was equivalence-inspected and passed all 58 stock-signal tests;
  the broader "all seven red then green" statement in the correction commit
  message is superseded by this record correction.
- `compileall` over the Analyst package and tests exit 0; `git diff --check`
  clean; Python 3.12.13. No frozen or shared document touched; the only changes
  are four Analyst production modules and four Analyst test files.

### 13.10 Next step

Codex counter-reviews this exact pushed head. The dormant-coverage gap
(ARV2WL-D01), the denylist-to-allowlist firewall consolidation (ARV2WL-D06),
and the archived-record integrity gap (ARV2WL-D02) are the three items most
worth an owner decision; the remaining documented items are hardening notes
tied to the milestone that first activates each path. ARV2-4C stays
unapproved pending the corrected proposal (section 12). ARV2-4 execution
remains blocked on the recorded source, rights, review, run-identity and
one-use authority gates; every production authority is empty or zero-access
and every action capability is literal false.

## 14. Codex counter-review of Claude commits `d72c8057` and `67ae5c11`, 2026-09-01

Codex counter-reviewed both pushed Claude commits separately and on their
cumulative tree. Claude's five-field ingest bounds, numerical-zero tests,
stable-sum consolidation, ambient-context coverage, and timing regressions are
sound. Its Git and import-firewall corrections materially improved the lane
but did not enforce the guarantees claimed by the review. Codex reproduced
the residual fail-opens before correcting them in `06f08b56` and `a371724a`;
no finding was accepted from prose alone.

### 14.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `d72c8057` | **Accepted after correction** | The ingest, formula, stock-signal, fit/apply, and timing changes are correct. Its subcommand-only Git allowlist and incremental dynamic-import walker remained bypassable; `06f08b56` and `a371724a` close those boundaries and complete their tests. |
| `67ae5c11` | **Accepted after correction** | The whole-lane review is useful and its main technical findings are sound. Section 13 required exact count, pagination, mutation-evidence, archived-test-name, and initiation/refusal-scope corrections. |

No commit is rejected. The cumulative whole-lane candidate remains accepted
after the corrections below; this disposition grants no source, outcome, QC,
deployment, order, or trading authority.

### 14.2 Counter-review findings and corrections

| ID | Pri | Status | Commit | Location | Finding, correction, and proof |
|---|---|---|---|---|---|
| `ARV2CR11-001` | **P2** | **Corrected** | `d72c8057` | `dataset.py` Git query boundary | Checking only the first Git subcommand still admitted side-effecting options and helpers, re-iterated caller-controlled arguments after validation, honored replacement/config/filter state, assumed 40-character objects, trusted index flags and the stat cache, and treated `ident`-normalized but behaviorally different source as clean. The boundary now accepts only five exact inert query grammars, executes the validated tuple, strips inherited Git controls, disables replacement/lazy-fetch/helper/cache surfaces, carries only validated checkout conversion settings, supports SHA-1/SHA-256, refuses executable filters and nonstandard index flags, and independently inventories and batch-hashes regular tracked files while refusing `ident`. Real-repository regressions cover every named form, including a globally configured CRLF checkout. |
| `ARV2CR11-002` | **P2** | **Corrected** | `d72c8057` | `dataset.py` ancestry proof | `--no-replace-objects` does not disable legacy `.git/info/grafts`; a graft made two unrelated roots pass `merge-base --is-ancestor` while status remained clean. Ancestry now resolves Git's exact graft path and refuses any graft metadata both before and after the query; commit-graph acceleration is disabled. The regression first proves raw Git accepts the forged parent and then proves the Analyst helper refuses it. |
| `ARV2CR11-003` | **P2** | **Corrected** | `d72c8057` | `import_firewall.py` | Claude's denylist-oriented walker still admitted executable builtins/evaluation paths, constant/default/pattern aliases, capability re-exports, unlisted standard-library capabilities, and repository-local `.pyw` or ABI-tagged extension shadows. The authoritative public boundary is now a fixed positive allowlist with exact 30-module closure, importer-specific capabilities, sensitive literal/reflection refusal, alias/rebinding checks, and reviewed-source-only local resolution. Mutation-sensitive probes cover the demonstrated executable forms; the guard remains explicitly a static dependency boundary, not an OS sandbox. |
| `ARV2CR11-004` | **P2** | **Corrected** | `d72c8057` | `import_firewall.py`, `data.exchange_calendar` boundary | An Analyst module could import `pd` from the approved calendar facade and reach pandas I/O without a direct forbidden import. Calendar consumers may now import only the exact six reviewed calendar exports; `pd`, `mcal`, wildcard, attribute, and dynamic facade access refuse. The actual closure and all current calendar consumers remain green. |
| `ARV2CR11-005` | P3 | **Corrected** | `d72c8057` | `test_ratings_ingest_and_ontology.py` | Claude correctly bounded all five provider fields but regression-tested only `firm` and `rating`. Exact 256-character acceptance and 257-character named refusal are now pinned independently for `firm`, `analyst`, `rating`, `previous_rating`, and `price_target_action`. |
| `ARV2CR11-006` | P3 | **Corrected** | `67ae5c11` | Section 13 summary | Section 13 reported 10 documented findings as 2 P2/8 P3, while D01-D11 contain 11: 3 P2 and 8 P3. The totals now reconcile and identify D11 as out of lane. |
| `ARV2CR11-007` | P3 | **Corrected** | `67ae5c11` | Section 13.1 | “57 pages” conflated body numbering with file pagination. The source has 64 physical pages: cover, six roman front-matter pages, and 57 Arabic body pages. |
| `ARV2CR11-008` | P3 | **Corrected** | `d72c8057`, `67ae5c11` | Commit prose; sections 13.1/13.9 | All seven corrections were described as mutation-red/green. Stable-sum delegation is behavior-equivalent, so reverting it cannot redden a behavioral test. The record now distinguishes six red/green corrections from one equivalence-inspected consolidation. |
| `ARV2CR11-009` | P3 | **Corrected** | `67ae5c11` | `ARV2WL-D02` | Two of three allegedly absent archived test names were abbreviated, preventing exact reproduction. All three are now enumerated with the test-path/all-local-ref search scope. |
| `ARV2CR11-010` | P3 | **Corrected** | `67ae5c11` | `ARV2WL-D09` | The initiation/out-of-universe observation conflicted with the frozen rating-change-only topology and was a false alarm. That portion is withdrawn; only the non-blocking classification refusal-scope consistency note remains. |
| `ARV2CR11-011` | **P2** | **Corrected** | `d72c8057`; first counter-review pass | `import_firewall.py`, `data.exchange_calendar` boundary | The first correction refused named unsafe exports but still allowed a computed `getattr(calendar_alias, "p" + chr(100))` to reach the facade's pandas binding. The firewall now tracks exact calendar-facade imports and direct aliases and refuses every dynamic `getattr` on that facade regardless of how the key is constructed. Two computed-key regressions pin direct and propagated aliases. |
| `ARV2CR11-012` | **P2** | **Corrected** | `d72c8057`; first counter-review pass | `dataset.py` ancestry proof | The first correction placed `core.commitGraph=false` on the index audit but not in the shared options used by `merge-base --is-ancestor`, contradicting its own ancestry guarantee. The option now applies to every validated read-only Git query, and a captured-command regression pins it on the actual ancestry call. |

Totals against the two Claude commits and their cumulative correction chain:
**0 P0, 0 P1, 6 P2, and 6 P3**, all corrected.

`ARV2WL-D06` is therefore closed by `ARV2CR11-003`. The other documented
items retain their section 13.6 dispositions; no unrelated strategy, Trading
App, or Streamlit defect was changed.

### 14.3 Validation and authority boundary

- `tests/analyst_revisions_v2`: **420 passed, 1 skipped in 139.59 s**.
- Root Analyst preregistration file: **46 passed in 39.67 s**.
- Dataset/import-firewall file: **116 passed in 83.38 s**;
  ratings/ontology file: **49 passed**.
- Active-document consistency gate: **69 passed**.
- Changed-scope `compileall` exited 0 and `git diff --check` was clean.
- The final current-tree audit and validation found no remaining P0-P2 issue.
- Structural fixtures only: **0 research looks and 0 development
  evaluations**. No credential, licensed provider row, price, return,
  outcome, QuantConnect upload/compile/job, broker, deployment, scheduler,
  order, UI, or Streamlit surface was accessed.

### 14.4 Owner decision and stop point

This counter-review does not resolve `ARV2CRP-004`. The owner selected the
global-benchmark path before the power-plan path but explicitly reserved
approval of the exact map and matched-row rules. The later recommendation to
use the **full 39-alias legacy comparator** rather than the proposed
**16-label core comparator** has not been approved. A generic instruction to
continue the normal loop does not choose between those materially different
comparator populations.

Accordingly, ARV2-4C implementation remains unauthorized. The next bounded
action is the corrected, content-addressed ARV2-4C proposal for the owner's
explicit full-39-versus-core-16 choice and approval of its exact matched-row,
coverage, bootstrap, per-arm reliability, post-join underfill, and
acyclic-successor rules. No credential, provider row, outcome, QuantConnect
job, deployment, or trading authority is needed or granted for that proposal.
This counter-review is committed locally and stops before both ARV2-4C
implementation and push.

## 15. Owner-approved ARV2-4C structural candidate, 2026-09-01

The owner explicitly approved the **full 39-alias legacy comparator** and the
corrected matched-row rules after the section 14 stop. Codex implemented
exactly that bounded, outcome-free milestone in the existing Analyst worktree
and branch. No provider row, credential, licensed artifact, price, return,
outcome, QuantConnect action, deployment, broker, scheduler, or order was
used. The candidate is pending independent Claude review and subsequent Codex
counter-review; implementation is not acceptance and grants no action
authority.

### 15.1 Content-addressed authority set

| Artifact | Content identity | Artifact SHA-256 | Role |
|---|---|---|---|
| `arv2_global_rating_map.structural.json` | `arv2-global-rating-map-aaf5830c3c3fb403` / `aaf5830c3c3fb403b0e84f5ad22d1f20fa3f91df41cf3bd64f33695875d2e3d9` | `630cc822fa83d7aba15920cfb8f37863f6d6fffa262e26ac96074e8526391f4e` | Exact naive global rating map and refusal inventory. |
| `arv2_global_matched_comparison.structural.json` | `arv2-global-matched-b94a3457b848c4dc` / `b94a3457b848c4dc1f6dee77ef366002362573431eb9cc2fc3b8f530ec7f89c9` | `40b164e3e2944053eaaaaf1a651e34dfb335a4cbc8aeca2ee3f67ecdc9e8dffa` | Paired rows, per-arm derivations, coverage, diagnostics, numerical rules, deterministic bootstrap, and zero-margin gate. |
| `arv2_stock_historical_successor.structural.json` | `arv2-stock-historical-successor-a9a2210b8f6582bc` / `a9a2210b8f6582bc3ce9e533ce33e9b51ffc0a0b3203b62ad21d9d373ce06f95` | `51718ee5ae278d1254e8efb01b2acdd9c6cbe51741dd72d5b5969c3b48576647` | Successor that retains the predecessor's single-arm rules and binds the approved paired-only amendments. |

`global_benchmark_contract.py` renders and authenticates all three artifacts,
their content-derived IDs/hashes, and seven exact authority sources: the map,
matched contract, successor, predecessor stock contract, unchanged fold
manifest, QC-first plan, and superseded QC-plan base. It rejects noncanonical
JSON, duplicate keys, floats/non-finite values, BOM/CRLF changes, links,
unstable reads, post-read replacement, source mutation, forged objects,
equality-spoofed fields, and incomplete or cyclic lineage. The successor adds
no parent pin to the reviewed fold manifest and does not edit or reparent it.

### 15.2 Approved 39-alias comparator

The map is exact, printable-ASCII-only, and closed. Canonicalization lowercases
ASCII and trims/collapses literal U+0020 spaces only; it performs no Unicode,
punctuation, or semantic rewrite. Unknown labels refuse. Exact mapped levels
and aligned scores are:

| Level / score | Exact aliases |
|---|---|
| 5 / `+1` | `strong buy`, `conviction buy`, `top pick`, `action list buy` |
| 4 / `+1/2` | `buy`, `outperform`, `overweight`, `market outperform`, `sector outperform`, `positive`, `accumulate`, `add`, `speculative buy`, `long-term buy`, `outperformer`, `above average` |
| 3 / `0` | `neutral`, `hold`, `equal-weight`, `market perform`, `sector perform`, `in-line`, `sector weight`, `perform`, `peer perform`, `market weight`, `average` |
| 2 / `-1/2` | `underweight`, `underperform`, `sector underperform`, `market underperform`, `reduce`, `negative`, `underperformer`, `below average`, `trim`, `cautious` |
| 1 / `-1` | `sell`, `strong sell` |

The 15 measured exact refusals are `developing`, `equalweight`, `fair value`,
`gradually accumulate`, `hold neutral`, `mixed`, `not rated`, `performer`,
`sector overweight`, `sector performer`, `sector underweight`, `speculative
hold`, `tender`, `trading buy`, and `trading sell`. Thus `equal-weight` maps,
while `equalweight` is a measured refusal and `equal weight` is an unknown
future label. Halving the legacy range is a positive affine transformation:
the full contribution-to-final-score regression proves rank and tie invariance
through decay, absolute-mass breadth, conservative `N_eff`, sector MAD
normalization, reliability, and final score.

The archived V1 document is policy provenance only. No archived or licensed
event count is promoted into V2 evidence. An admitted directional event whose
mapped global endpoints have the expected sign remains active; an exact-zero
global delta is the named active `global_tier_collapse_zero`; an opposite-sign
global delta is a joint `global_direction_conflict` refusal. The latter stays
in the structural coverage denominator and cannot make the comparator easier
through uncharged censoring.

### 15.3 Corrected paired comparison

The predecessor single-arm IC inventory still refuses fewer than 20 rows, a
constant score, or a constant outcome. Only the paired firm-versus-global gate
uses the successor rule on identical rows and one shared outcome:

- fewer than 20 identical rows or a constant shared outcome jointly refuses;
- neither arm constant uses ordinary average-rank Spearman for both arms;
- exactly one constant arm receives an exact paired-only association of zero,
  while the other arm uses ordinary Spearman;
- both arms constant jointly refuse with `both_arms_constant_score`; and
- no imputation or one-arm row deletion is permitted. A paired totalized zero
  is never admitted to a single-arm IC inventory.

Event identity, activity evidence, `q_data`, NYSE-session ages/decay kernel,
eligible census, graph, controls/folds, and later shared outcome are common.
Mapped delta, contribution/absolute mass, raw score, institution/common-event
breadth, conservative `N_eff`, sector normalization, reliability,
coefficients, and residuals are derived separately per arm. A collapse event
remains ACTIVE with zero score/breadth mass and cannot increase `N_eff`; a
security-date containing only collapse events remains an ACTIVE zero row with
zero reliability through the paired fit census.

For either arm, an exact zero-range paired sector may totalize standardized
scores to zero while preserving ACTIVE versus STRUCTURAL_ZERO state. A
nonzero-range zero-MAD sector jointly refuses; shared-control zero MAD retains
the parent refusal. There is no epsilon or market fallback. The numerical
contract forbids binary floats, requires finite input, exact rational
midranks, stable Decimal summation, precision 50 / `ROUND_HALF_EVEN`, exact
Python Decimal exponent/clamp/trap settings, and exact-zero comparisons.

Five outcome-free structural ledgers must each pass exact 19/20 cross
multiplication both pooled and independently in every nonempty fold: endpoint
pair mapping plus direction admissibility, active security-date rows, common
event components, component-member incidence, and score-capable dates. A zero
denominator is invalid. After the single later authorized outcome join, the
valid-date and connected-component floors are each the stronger of 50 and the
content-addressed power-plan requirement. Honest underfill is
`INCONCLUSIVE_locked_no_extension`; identity corruption is `INVALID_DATA`;
adequate-sample failure closes the family. None permits alias, fold, period,
seed, or retry rescue.

The bootstrap samples each fold's complete uncompressed horizon-20 NYSE test
session axis with noncircular 20-session blocks, all starts `0..N_f-20`,
`ceil(N_f/20)` draws, concatenation and fold-length truncation. Missing dates
add neither value nor denominator; multiplicity remains; the replicate is the
equal-occurrence pooled mean. A zero-available replicate locks underfill with
no redraw. The dependency-independent SHA-256 hash-counter sampler has fixed
seed fields, uint64 ordinals, unbiased rejection conversion, `B=19,999`, and
the exact Type-7 95th percentile. The primary gate is the frozen zero-margin
no-worse-with-confidence rule: after every readiness gate, pass requires both
`D >= 0` and `LCB95 >= 0`; exact equality passes.

### 15.4 Implementation counter-audit

Three independent read-only audit threads reviewed policy/statistics, code,
and adversarial tests while Codex implemented the candidate. All final
dispositions are **ACCEPT**, with no remaining P0-P3 finding. Material issues
found and corrected before freeze were:

| ID | Pri | Status | Correction |
|---|---|---|---|
| `ARV2I4C-001` | P2 | Corrected | Opposite-sign mapped transitions now remain in the endpoint/direction coverage denominator, preventing uncharged comparator censoring. |
| `ARV2I4C-002` | P2 | Corrected | Resolver mappings are reconstructed from trusted exact primitive fields; caller-controlled equality/score objects cannot forge a delta. |
| `ARV2I4C-003` | P2 | Corrected | Loader-authority fingerprints validate exact runtime types and use trusted type-tagged immutable values, closing equality-spoofed hashes and nested entry mutation. |
| `ARV2I4C-004` | P2 | Corrected | The complete acyclic graph and successor now include the exact superseded QC-plan base and every material parent edge. |
| `ARV2I4C-005` | P3 | Corrected | Malformed lineage and QC-plan ancestry failures normalize to the ARV2-4C domain error; the cycle guard remains directly reachable. |
| `ARV2I4C-006` | P3 | Corrected | Load-time and post-load mutation checks cover all seven sources, including unstable double reads and the superseded base. |
| `ARV2I4C-007` | P3 | Corrected | Decimal exponent/context/flag/trap behavior, caller-nonoverrideable coverage/sampler bounds, and the complete homogeneous half-scale signal path are regression-pinned. |

### 15.5 Validation, remaining gates, and next step

- Exact ARV2-4C/final-path focus: **152 passed, 1 host symlink skip**.
- Complete `tests/analyst_revisions_v2`: **571 passed, 2 host symlink skips in
  132.60 s**.
- Complete repository: **7,068 passed, 14 skipped, 3 failed, 26 warnings in
  1,254.63 s (20m54s)**. The failures are exactly the standing out-of-lane
  `ARV2-UNRELATED-001` Target Price error-message assertion and the two
  date-relative Trading App sleeve-report assertions in `ARV2WL-D11`; no
  Analyst test failed. They are documented and were not fixed under the
  owner's lane boundary.
- Import-firewall closure remains exact and outcome-free; the only new
  standard-library capability is arithmetic-only `math` for reduced-rational
  validation.
- Changed-scope `compileall` exited 0 with its cache redirected outside this
  worktree; `git diff --check` is clean apart from non-error Windows line-ending
  notices.
- Structural fixtures only: **0 research looks and 0 development
  evaluations**.

The next action is one combined push of the section 14 counter-review series
and this ARV2-4C candidate for Claude's independent review on this same
branch. Codex then counter-reviews every Claude commit. Only after acceptance
may the next bounded outcome-free power-plan milestone begin. Production
sources/rights, outcomes, QuantConnect upload/compile/run, result disposition,
paper/funded deployment, and orders each remain separately gated and false.

## 16. Independent Claude review of the whole-lane counter-review and the ARV2-4C milestone, 2026-09-01

**Range reviewed:** `67ae5c11..aa6d1d00`, five commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, 0 P2, **1 P3
corrected**, 2 P3 documented. **Zero research looks and zero development
evaluations.** No provider, credential, licensed row, price, return, outcome,
broker, operator-database, QuantConnect, upload, scheduler, order, UI or
Streamlit access occurred, and none was reachable: every production authority
is empty or zero-access and every action capability is literal false.

**Quality: ARV2-4C candidate 9.5/10** - the most disciplined artifact in the
lane; a faithful, complete implementation of the corrected proposal with a
textbook-correct unbiased bootstrap and an acyclic successor that touches no
reviewed byte. **Codex's whole-lane counter-review (section 14) 9/10** - it
found real residual fail-opens my prior fixes left and corrected three genuine
accuracy errors in my section 13.

### 16.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `06f08b56` | Accepted | Codex's counter-review hardening of the Git boundary and import firewall. Independently audited line by line against the base: it **only strengthens** - no guard removed or loosened, my ARV2WL-001/002/003 fixes preserved. 19/19 mutating/injection git argv rejected (`-c`, `--exec-path`, `-C` escape, push/update-ref/gc/fetch, pathspec magic) with all six real caller shapes accepted; the firewall is now an import allowlist plus a reflection denylist that catches all six dynamic-import evasions plus `os.system`/`eval`/`exec`/`ctypes`. Closes my own ARV2WL-D06 recommendation. |
| `a371724a` | Accepted | Codex's follow-up closing two self-found gaps from its first pass: a computed-key `getattr` on the calendar facade reaching `pd`, and `core.commitGraph=false` not applied to the ancestry call. Both correct and regression-pinned. |
| `4c686a55` | Accepted | Section 14, Codex's counter-review of my whole-lane commits `d72c8057`/`67ae5c11`. Its findings are fair and I verified the material one myself: my section 13 undercounted the documented findings (10 -> 11; 2 -> 3 P2, because D06 is P2), overstated "all seven mutation red/green" (the stable-sum consolidation is behavior-equivalent), and cited 57 body pages versus 64 physical. All three are genuine; ARV2CR11-001/002 (the `.git/info/grafts` ancestry forge and subcommand-only allowlist gaps) are real residual fail-opens my fixes left. Record-only. |
| `63bd04b0` | Accepted after correction | The ARV2-4C global comparator milestone: `global_benchmark_contract.py` (1,807 lines) plus three content-addressed artifacts. One P3 test-coverage gap corrected (ARV2R10-001). |
| `aa6d1d00` | Accepted | The milestone record (sections 15). Its claims match my independent verification. Record-only. |

### 16.2 Independent verification of ARV2-4C

Every item on the owner's verification list was reproduced first-hand from the
committed bytes:

- **Rating map:** exactly 39 mapped aliases across five levels (4+12+11+10+2),
  exact reduced-rational operational scores +1, +1/2, 0, -1/2, -1 =
  `(legacy_level-3)/2`; exactly 15 measured refusals matching the archived
  vocabulary; **zero map/refusal collision**; every label canonical ASCII
  lowercase, trimmed, single-spaced; non-ASCII refuses; unknown labels refuse
  with no default. Map hash `aaf5830c...` recomputed exact.
- **Event semantics:** an exact-zero global delta becomes an **active**
  `global_tier_collapse_zero` (not structural zero, not dropped); expected-sign
  transitions stay active contributions; opposite-sign conflicts **jointly
  refuse and are charged to structural coverage** (`opposite_sign_is_
  denominator_only`), not silently dropped.
- **Predecessor single-arm refusal unchanged:** the loader pins the parent's
  IC `date_refusal` to `fewer_than_20_rows_or_constant_score_or_constant_
  outcome`, and the paired rule is explicitly additive
  (`firm_specific_vs_global_paired_gate_only`).
- **Paired rules:** <20 identical rows, constant shared outcome, and both arms
  constant all jointly refuse; exactly one constant arm gives that arm exact
  IC=0 and the other ordinary Spearman; exact one-to-one row parity;
  imputation and one-arm removal both forbidden.
- **Sector totalization (the key ARV2CRP-003 correction):** only an
  **exact-zero range** (`min==max`) totalizes to paired-only all-zero
  standardized scores preserving ACTIVE vs STRUCTURAL_ZERO; a **nonzero-range
  zero-MAD** sector **refuses** and is charged to coverage; shared-control
  zero-MAD refuses; no epsilon/market fallback.
- **Per-arm derivation:** mapped delta, decayed mass, raw score, breadth,
  conservative `N_eff`, sector normalization, reliability, coefficients and
  residuals are per arm; identities, activity, `q_data`, ages, controls, folds
  and outcomes are shared; a collapse-zero event stays active with zero mass
  and cannot raise `N_eff`.
- **Coverage:** five 19/20 ledgers (endpoint-pair, active-row, component,
  member-incidence, date), each required both pooled and independently in
  every nonempty fold, by exact integer cross-multiplication, with a zero
  denominator as underfill and no outcome dependence.
- **Post-join:** identity mismatch -> INVALID_DATA; honest shortfall ->
  INCONCLUSIVE locked, no extension; adequate-sample failure -> FAIL closes the
  family; any outcome-informed map/fold/period/seed/retry change forbidden.
- **Bootstrap:** complete-session noncircular 20-session moving blocks
  contained in each fold (the 2020 fold's 233 sessions give exactly 214
  allowed starts), Type-7 quantile computed as `0.9*x[18999]+0.1*x[19000]`,
  fixed 19,999 resamples, and a **dependency-independent unbiased SHA-256
  hash-counter sampler** whose rejection band `reject u >= 2^256-(2^256 mod m)`
  eliminates modulo bias, with fail-closed overflow.
- **Half-scale invariance:** two regressions pin that dividing legacy tiers by
  two is Spearman-inert through the full contribution-to-final-score path
  (ranks and ties preserved).
- **Lineage:** the successor stock spec binds an eight-node DAG whose
  topological node order is PDF, qc_base, qc_plan, stock_v1, fold_manifest,
  global_map, matched_contract, stock_v2. The exact branching parents are:
  qc_base <- PDF; qc_plan <- {PDF, qc_base}; stock_v1 <- {PDF, qc_plan};
  fold_manifest <- {PDF, qc_plan, stock_v1}; global_map <- {PDF};
  matched_contract <- {PDF, stock_v1, fold_manifest, global_map}; and stock_v2
  <- {PDF, qc_plan, stock_v1, fold_manifest, global_map, matched_contract}.
  I confirmed by topological check it is **acyclic** and the successor is a
  leaf. The fold manifest, predecessor
  stock spec, and `fold_manifest.py` are **byte-identical** to the base -
  no edit, re-pin, or reparent - and the fold manifest's parents remain
  `{pdf, qc_plan, stock_v1}`, never the successor. All three new-artifact
  hashes (map, matched, successor) recomputed exact.
- **Authority surface:** loading the contract through its six-artifact loader,
  all six capability accessors return `False`; `copy.copy`, `object.__new__`,
  and pickle all fail reauthentication; the transitive closure is 31 modules
  with no execution/ML/network/legacy-ACER root.

### 16.3 Findings

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R10-001 | P3 | **Corrected** | `global_benchmark_contract.py:1448` / `tests/analyst_revisions_v2/test_global_benchmark_contract.py` | The loader pins the predecessor's single-arm IC `date_refusal` string so a future edit that weakened the single-arm rule (dropping the constant-score/constant-outcome clause the paired rule builds on) would be caught - but no regression exercised that specific guard. The neighbouring null-slot battery covers the child-slot guards, not the refusal string. The guard fires (verified by a weakened-parent probe); it was simply unpinned. | Added a monkeypatch regression that returns a parent with `date_refusal="fewer_than_20_rows_only"` and asserts the loader refuses with `single-arm IC refusal changed`, mirroring the existing null-slot test pattern. Test-only; no production module changed. | Removing the guard reddens the new test; restored green. |

### 16.4 Documented, not fixed

| ID | Pri | Location | Observation |
|---|---|---|---|
| ARV2R10-D01 | P3 | `global_benchmark_contract.py` numerical contract | The Decimal numerical contract (prec 50, HALF_EVEN, fresh-context-per-calculation, exact-zero comparison) is present only as frozen specification text; the module imports no `decimal` and performs no Decimal arithmetic, because the Spearman/bootstrap statistic consumes outcomes and is correctly deferred. Its ambient-context-isolation guarantee is therefore a **future obligation** on the milestone that builds the statistic, not something this outcome-free module can honor or that can be pinned today. Recorded so that implementer creates a fresh local context per calculation rather than inheriting `getcontext()`. |
| ARV2R10-D02 | P3 | `import_firewall.py:692-714` | Codex's allowlist firewall catches every dynamic-import evasion, `os.system`, `eval`/`exec` reassignment, `ctypes`, and string-concatenated dunder names, but a `getattr(obj, <fully-runtime-string>)` where the attribute name is a genuine runtime value (a function parameter, or `chr(115)+'ystem'`) is not flagged - the documented boundary of a static guard. Exploitation would require **both** a dangerous object root (os/subprocess/importlib/builtins, all already blocked at import/name level) **and** a fully-computed name, so it is not reachable today. The module docstring already disclaims this; no change recommended, recorded for completeness. |

### 16.5 Validation

- ARV2-4C focused file `test_global_benchmark_contract.py` on the final tree:
  **151 passed, 1 host symlink skip** (150 as received plus the new
  ARV2R10-001 regression); the item-9 half-scale invariance regression in
  `test_stock_signal.py` passes.
- Git-boundary/firewall and ratings batteries: **165 passed**; my prior
  ARV2WL-001/002/003 fixes confirmed present and strengthened.
- Complete repository suite, exact as-received tree `aa6d1d00`: **3 failed, 7068 passed, 14 skipped, 25 warnings in 1714.03s (0:28:34)** in a pinned base-temp. All three failures are in `tests/test_sleeve_report.py` (Trading App three-sleeve engine, out of lane) and reproduce on the pristine base; **zero Analyst tests failed**. Composition differs from the record's host - three sleeve-report cases here versus one Target Price plus two sleeve there - which is the known date/interpreter sensitivity of those standing out-of-lane assertions (ARV2WL-D11, ARV2-UNRELATED-001), not a regression.
- The ARV2R10-001 regression mutation-verified red then green.
- `compileall` over the Analyst package exit 0; `git diff --check` clean;
  Python 3.12.13. No frozen or shared document touched; the only change is one
  Analyst test file.

### 16.6 Next step

Codex counter-reviews this exact pushed head. The next milestone is the
power-plan definition, which is a separate owner-authorized step and must not
begin by inference; ARV2R10-D01's Decimal-context obligation lands on the
milestone that builds the outcome-bearing statistic. ARV2-4 execution remains
blocked on the recorded source, rights, review, run-identity and one-use
authority gates; every production authority is empty or zero-access and every
action capability is literal false. No credential, provider, outcome, QC,
deployment, or trading access is authorized.

## 17. Codex counter-review of Claude commits `abcb34f3` and `db2d8011`, 2026-09-01

The clean dedicated worktree synchronized exactly at pushed Claude head
`db2d8011554411263fb11f2c9a60154166ce5bed`. Codex reviewed both new commits
under `CLAUDE.md`, `AGENTS.md`, the two standing review-process documents, the
strategy PDF, the exact ARV2-4C authorities, and this record. No provider,
credential, licensed row, price, return, outcome, QuantConnect, deployment,
broker, scheduler, or order capability was accessed.

### 17.1 Commit dispositions

| Commit | Disposition | Counter-review basis |
|---|---|---|
| `abcb34f349d71679e8df495997f6f4d313b18f2d` | **Accepted** | The monkeypatch returns the exact authenticated predecessor identity with only the single-arm IC refusal weakened, reaches the real additive-rule guard, and asserts the named domain refusal. It closes the claimed P3 sensitivity gap without changing production behavior. |
| `db2d8011554411263fb11f2c9a60154166ce5bed` | **Accepted after documentation correction** | The review's technical findings, artifact calculations, correction scope, and authority statements reproduce. Its only defect was the section 16.2 arrow shorthand, which could be read as edges in a linear chain although the committed DAG is branching. |

Cumulatively, `aa6d1d00..db2d8011` is **accepted after correction**. There is
no production-code defect and no P0-P2 finding.

### 17.2 Counter-review finding

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| `ARV2CR12-001` | P3 | **Corrected** | Section 16.2 lineage bullet | The notation `PDF -> qc_base -> qc_plan -> stock_v1 -> fold_manifest -> global_map -> matched_contract -> stock_v2` looked like a linear edge chain. That is not the committed graph: `global_map` is a child only of the PDF, and the matched contract has four parents. A later reader could infer a nonexistent re-parenting even though the artifact and loader are correct. | Relabeled the sequence as a topological node order and listed every exact parent set. No artifact, loader, or production byte changed. | Direct comparison with `_successor_document().acyclic_lineage` and the canonical successor JSON; focused loader test and document validation. |

Claude's `ARV2R10-D01` remains a valid future obligation: the milestone that
first implements outcome-bearing Spearman/bootstrap arithmetic must use a
fresh frozen Decimal context. `ARV2R10-D02` remains an unreachable static-
analysis limit and does not justify broadening the firewall now.

### 17.3 Validation and authority boundary

- The new predecessor-refusal regression passed independently: **1 passed**.
- Complete focused ARV2-4C file: **151 passed, 1 host symlink skip**. Active-
  document gate: **69 passed**. Combined: **220 passed, 1 skipped in 20.29 s**.
- The correction changes this lane record only. No reviewed artifact,
  production module, fold manifest, shared project document, UI, Streamlit,
  or other strategy file changes.
- Structural/code evidence only: **0 research looks and 0 development
  evaluations**.

### 17.4 Exact blocker before the power milestone

The owner's instruction authorizes power-plan work, but the source and frozen
parents contain no numeric minimum meaningful effect, target power, or
independent variance/dependence calibration. Choosing those values would set
how small an edge the historical screen claims it can detect; under the
repository rule that an assistant must not invent financial numbers or a
convenient universal sample threshold, that remains an owner decision.

The recommended bounded sequence is:

1. **ARV2-4D-A:** freeze an outcome-free, content-addressed calibration
   protocol, including the owner-approved effect and target power, exact
   non-evaluation calibration window/source, horizon-20 complete-session HAC
   arithmetic, component rule, infeasibility disposition, and all-null action
   authority.
2. **ARV2-4D-B:** only after separate authority for the calibration inputs,
   create the numeric content-addressed power receipt and bind its required
   valid-date/component floors through a new stock successor. Never edit or
   re-pin the reviewed ARV2-4C artifacts or fold manifest.

No credentials are needed for ARV2-4D-A. Any return-based calibration is a
separate outcome/data action; it must not begin from this authorization.

## 18. ARV2-4D-A owner-approved power-calibration protocol, 2026-09-02

The owner approved the recommended ARV2-4D-A power policy. Codex implemented
exactly that bounded, outcome-free policy after committing section 17's
counter-review as `317ebe03`. The implementation commit is `ac6f06e4`. It
does not inspect calibration rows or returns, calculate a research result,
create a numeric receipt, launch QuantConnect, or authorize any subsequent
stage.

### 18.1 Content-addressed policy and scope

The canonical artifact is
`research/analyst_revisions_v2/specs/arv2_stock_power_calibration_protocol.structural.json`,
authenticated by `power_calibration_protocol.py` as:

- protocol ID
  `arv2-stock-power-calibration-protocol-0ba6b7d745783796`;
- content SHA-256
  `0ba6b7d7457837967b5b8b7966cc22c2ddd00f4dbf4a7269b9aaa562baac757f`;
- exact artifact SHA-256
  `ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13`;
  and
- authority
  `calibration_method_only_no_input_data_outcome_receipt_qc_or_deployment_authority`.

The minimum meaningful effect is exactly 10 basis points (`1/1000`) of
20-session open-to-open arithmetic gross SPY-excess return per +1 unit of the
primary bullish control-adjusted score. The target is nominal asymptotic 80%
power at two-sided 5% size for the single
`bullish_20_session_fama_macbeth` coefficient. This is deliberately not a
power claim for the economic net sleeve, paired IC comparison, conjunctive
three-gate family, exact 19,999-replicate bootstrap, or the Analyst lane as a
whole. Neither the effect nor target may be weakened or reinterpreted after
outcomes.

The nuisance-only calibration source is the first fold's H20 validation
period: the complete 483-session XNYS axis `[2018-01-31, 2020-01-02)`, axis
SHA-256 `22d38c7178f6863d4d9f5284eba9216b0f8499848b1188781316d1169b13a051`.
Its last included decision session is 2019-12-31, whose H20 outcome matures
2020-01-30 before the first test session on 2020-01-31. Purge, embargo, and
interior-axis checks are derived from the authenticated unchanged fold
manifest rather than copied as unchecked dates.

The protocol freezes a fresh 50-digit `ROUND_HALF_EVEN` Decimal context;
exact z constants for 0.975 and 0.80; squared sum
`7.8488797343490889511625145685327253191071246220413`; and exact evaluation
order. The lag-20 HAC operates on date-level beta values at their full session
positions, never compresses or zero-fills missing dates, uses denominator
`N`, Bartlett weights `(21-l)/21`, and requires a positive finite long-run
variance with at least one valid pair at every lag. Stable summation begins at
exact zero after sorting by `(abs(value), signed value)`; the transient mean
uses the same fresh context.

The component calibration uses all point-in-time eligible rows in the
firm-specific primary H20 Fama-MacBeth design after non-outcome refusals and
before the outcome join or global matching, with structural-neutral zeros
retained and no score/sign filter. The lower-fifth component floor is the
non-interpolated 25th smallest of all 483 exact session/count pairs, including
honest zeros. Required dates are
`max(50, ceil(Omega * factor / (1/1000)^2))`; required components are
`max(50, required_dates * q05)`. A requirement at or below the fixed 1,388
H20 test-session capacity is only
`FEASIBLE_FIXED_DESIGN_pending_authenticated_receipt`; a requirement above it
is `UNDERPOWERED_FIXED_DESIGN_no_launch`, with no extension or rescue.

### 18.2 Authentication, lineage, and deferred receipt

The loader accepts one canonical JSON byte form, derives and verifies its
identity, refuses links and unstable/non-regular reads, authenticates the
complete ARV2-4C parent, and revalidates both child and parent across nested
authentication. Reauthentication uses an immutable type-tagged fingerprint,
a locked weak-reference authority registry, and rejects copies,
reconstruction, pickle, scalar/collection substitution, and equality-spoofed
objects.

The unchanged eight-node ARV2-4C graph is extended by one
`power_protocol` leaf. That leaf directly records every bound material parent:
the PDF, QC-first plan, stock v1, fold manifest, global map, matched contract,
and stock v2. No reviewed ARV2-4C artifact, predecessor stock spec, fold
manifest, or loader byte was edited, re-pinned, or re-parented.

`derive_provisional_power_requirement` is arithmetic-only. It accepts an exact
positive finite caller-supplied Decimal long-run variance and all 483 exact
session/count pairs, then returns a non-constructible provisional value whose
authority, receipt, and power-plan bindings are literal false/null. It does
not read a file, outcome, provider, credential, or QC resource, and its
feasible label does not authorize a launch.

ARV2-4D-B remains deliberately absent. Its exact input-manifest schema is
deferred to separate review; only identities, hashes, rights, lineage,
session keys, and counts may be admitted before any calibration. The future
numeric receipt has a closed permitted-output allowlist, while returns,
date-level betas, their mean/sign, intermediate HAC terms, p-values,
performance statistics, gate results, and all other computed values are
forbidden from persistence. Every current input, receipt, power-plan, outcome,
QC, result, deployment, and order binding remains null or false.

### 18.3 Implementation counter-audit

Three independent read-only audit threads examined the statistical contract,
implementation boundary, and adversarial tests. All final dispositions are
**ACCEPT**, with no remaining P0-P3 finding. Issues found during construction
and corrected before this record were:

| ID | Pri | Status | Correction |
|---|---|---|---|
| `ARV2I4DA-001` | P2 | Corrected | Standardized the future component-census hash/count fields across the source and deferred-receipt contracts. |
| `ARV2I4DA-002` | P2 | Corrected | Made provisional results non-directly-constructible and exposed authority/receipt bindings only as constant false/null properties. |
| `ARV2I4DA-003` | P2 | Corrected | Pinned the exact firm-arm, pre-outcome, no-score/sign-filter component population and made the absolute date floor drive the pooled component floor. |
| `ARV2I4DA-004` | P2 | Corrected | Closed the persistable numeric-output allowlist and explicitly prohibited every other computed or intermediate statistic. |
| `ARV2I4DA-005` | P2 | Corrected | Froze exact `<= 1388` versus `> 1388` dispositions without clamping, extension, or an authorizing feasible label. |
| `ARV2I4DA-006` | P2 | Corrected | Added a final child-byte revalidation after nested parent reauthentication, closing a deterministic post-load TOCTOU window. |
| `ARV2I4DA-007` | P2 | Corrected | Added the directly bound global map to the power leaf's exact lineage and regenerated the content identity. |
| `ARV2I4DA-008` | P3 | Corrected | Fully pinned stable summation, fresh-context mean/evaluation order, exact session/count pairs, and purge/maturity/calendar behavior. |
| `ARV2I4DA-009` | P3 | Corrected | Removed a false claim that the future input-manifest schema was already closed and deferred its exact fields to separately reviewed ARV2-4D-B. |
| `ARV2I4DA-010` | P3 | Corrected | Added literal identity/constants/output pins, hostile-context tests, exact 1,388/1,389 boundary values, floor-to-component propagation, and load/require mutation regressions. |

### 18.4 Validation, authority boundary, and next step

- Canonical protocol file: **94 passed, 1 host symlink skip**.
- Protocol plus import-firewall/authority-registry battery: **210 passed, 1
  skip in 118.28 s**.
- Complete `tests/analyst_revisions_v2`: **666 passed, 3 host skips in
  167.60 s**.
- Complete repository on the exact committed code tree: **7,162 passed, 15
  skipped, 4 standing out-of-lane failures, 26 warnings in 1,321.04 s
  (22m01s)**. The failures are the previously documented Target Price stale
  diagnostic assertion `ARV2-UNRELATED-001` and three date-relative Trading
  App sleeve-report assertions in the `ARV2WL-D11` family. No Analyst test
  failed, and the unrelated tests/code were not changed.
- The renderer equals the checked-in bytes; the exact artifact hash above and
  all ARV2-4C ancestor artifact hashes reproduce. `git diff --check` is clean.
- Three final independent audits returned **ACCEPT** with no remaining P0-P3.
- Structural/code evidence only: **0 research looks and 0 development
  evaluations**.

The exact next action is one combined push of the already committed section-17
counter-review, ARV2-4D-A implementation, and this record for Claude's
independent review. Codex then counter-reviews every Claude commit. ARV2-4D-B
must not begin without separate exact owner authority for its reviewed input
schema and calibration inputs/rights. No credentials are needed now. ARV2-4
and every provider, outcome, QC, paper, funded, deployment, and trading action
remain blocked.

## 19. Independent Claude review of ARV2-4D-A and resolution of the whole-lane deferred findings, 2026-09-02

**Range reviewed:** `db2d801..35b3833`, four commits, each disposed below.
**Disposition: ACCEPTED.** 0 P0, 0 P1, 0 P2, 0 P3 against the reviewed range.
Separately, this session was asked to resolve the findings section 13 recorded
as documented-but-unfixed. Six are now corrected, four are documented with the
reason they must not be fixed here, and one is out of lane.
**Zero research looks.** No provider, credential, licensed row, price, return,
outcome, broker, operator-database, QuantConnect, scheduler or order access
occurred.

**Reviewing session:** the Fable 5 session on the work identity, which also
produced sections 4I, 4R and 7. Sections 4L, 4O, 10, 13 and 16 were produced
by the Opus 5 session; see `ARV2R5-002` on lane review ownership.

### 19.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `317ebe0` | Accepted | Codex counter-review of the ARV2-4C corrections; record-only. |
| `ac6f06e` | Accepted | The ARV2-4D-A power-calibration protocol. Verified in 19.2. |
| `6e7d2ce` | Accepted | Milestone record for the above. |
| `35b3833` | Accepted | Final validation record. |

### 19.2 ARV2-4D-A verified rather than accepted

- **Both recorded identities reproduce exactly.** Loading the artifact yields
  protocol ID `arv2-stock-power-calibration-protocol-0ba6b7d745783796`, and the
  file's SHA-256 is `ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13`
  — both identical to the values recorded in section 18.
- **All nine action capabilities are literal false**: calibration-input access,
  source access, outcome access, authoritative receipt, power-plan binding, QC
  action, result disposition, deployment and orders.
- **The loader demands the complete reviewed ancestry.** It cannot be called
  without the global rating map, matched-comparison contract, stock successor
  spec, parent stock spec, fold manifest and QC-first plan. A protocol divorced
  from its lineage does not load at all.
- **No data or network surface.** Imports are stdlib plus
  `data.exchange_calendar` plus in-lane modules; the transitive import firewall
  still reports zero forbidden roots.
- **The scope disclaimer is honest.** The 10bp effect and 80% target are
  claimed for exactly one coefficient and explicitly disclaimed for the net
  sleeve, paired IC, three-gate family, bootstrap and the lane as a whole, with
  the numeric receipt deferred to ARV2-4D-B under separate authority.

### 19.3 Deferred whole-lane findings: corrected

| ID | Was | Correction | Verification |
|---|---|---|---|
| ARV2WL-D01 | P2 | **Substantially closed.** Added `tests/analyst_revisions_v2/test_dormant_etf_portfolio_arithmetic.py` (14 tests) covering the allocator's water filling and 20/40/30 caps, `mapped_candidate_coverage`, the `weighted_stock_score` success path, and `portfolio_transaction_cost`. The zero-access gate is bypassed only locally inside that file; its refusals keep their own tests and no committed artifact or authority is altered. | Four mutations killed: ignoring the ETF cap in water filling (3 failed), dropping the impact term from cost (1), ignoring the coverage denominator (2), dropping the weight from the weighted score (1). Cost splitting is pinned as non-reducing. |
| ARV2WL-D02 | P2 | **Closed.** The three tests the archived remediation record named now exist under exactly those names: `test_weighted_score_requires_loader_authenticated_exact_score_artifact`, `test_stock_score_artifact_refuses_missing_extra_duplicate_and_invalid_rows`, and `test_stock_score_authority_refuses_clone_mutation_substitution_and_foreign_context`. | They pass, and they exercise real behaviour (authority, census, post-authentication mutation) rather than restating the names. |
| ARV2WL-D03 | P3 | **Hardened, with an honest scope correction.** Coverage eligibility now compares `Fraction(mapped)` against `Fraction(threshold) * Fraction(denominator)` instead of a rounded quotient. | I first wrote a test asserting this fixed a reachable fail-open; mutation showed the test did not discriminate, and investigation showed why: `mapped` is accumulated under the same 50-digit context, so a higher-precision weight is already rounded before the comparison sees it. The fail-open is therefore **unreachable through this path**, and the change is hardening only. The test now pins the real property — exact decision at the threshold boundary — rather than claiming a fix it does not deliver. |
| ARV2WL-D05 | P3 | **Closed.** The bare `1e-18` is now `ALLOCATION_CONVERGENCE_TOLERANCE`. | Its comment initially claimed the hard caps were re-checked *exactly*; they are re-checked as `weight > cap + tolerance`. The comment now states what the code enforces — a bounded overshoot of at most 1e-18 of NAV — rather than a guarantee it does not provide. |
| ARV2WL-D07 | P3 | **Closed.** `FirmRatingNormalizationResult` now carries an optional `source_census` and refuses when dispositions do not cover it exactly; `normalize_firm_rating_audit` populates it from the audit, so the invariant is live rather than dormant. | Mutation: disabling the census check fails the new regression; restoring passes. |
| ARV2WL-D08 | P3 | **Closed.** `load_snapshot` now reconciles the entire snapshot root, not only `pages/`: any file that is neither the manifest nor a referenced page is refused as an unauthenticated sidecar. | Mutation: removing the refusal fails the new regression, which covers both a root-level and a nested sidecar; restoring passes. |

### 19.4 Deferred whole-lane findings: documented, deliberately not fixed

| ID | Reason it is not fixed here |
|---|---|
| ARV2WL-D04 | Recording a `ForcedExit`/underfill row for an evicted incumbent changes the shape of the `PortfolioDecision` research artifact. That is the ARV2-5 decision-artifact design point the finding itself names, not a defect to patch unilaterally. |
| ARV2WL-D06 | Converting the firewall from denylist to allowlist alters the closure computation and is explicitly an owner-scheduled lane-architecture consolidation, ideally adopting the Target Price implementation to remove the second implementation. Out of scope for a review pass. |
| ARV2WL-D09 | The retained half is a refusal-scope labelling inconsistency. Changing `RefusalScope` values would alter frozen refusal semantics that downstream contracts pin by hash. |
| ARV2WL-D10 | **Attempted, abandoned, and re-specified.** Adding `sort_keys=True` to the standalone loader's canonical-bytes check is the fix the finding proposes, but it is the wrong fix and I verified why before applying it. The disorder is not confined to the root: `arv2_stock_historical.structural.json` contains **29 unsorted dicts** nested throughout, so sorting re-serialises the whole artifact, changing its bytes, `spec_hash` and `spec_id`, and cascading into every descendant that pins that ancestry (fold manifest, successor spec, matched-comparison contract, calibration protocol). That is a multi-artifact re-pin needing owner authorisation and fresh review anchors, for a formatting property. The root order is also a deliberate human header (`schema, status, authority, spec_id, spec_hash, ...`); alphabetising it would lead with `analysis_definition` and read worse. **The correct fix needs no artifact change at all:** pin the artifact's raw SHA-256 and compare `sha256(payload)` against it, which is the mechanism this codebase already uses — `fold_manifest.py:59` pins `PARENT_STOCK_SPEC_ARTIFACT_SHA256 = 34d1e715...`, verified here to equal the artifact's actual digest. The composed path is therefore **already closed**; the gap is only the standalone loader, which re-derives bytes instead of comparing them to a pin. A raw-byte pin also catches strictly more than `sort_keys` would: nested reordering, whitespace, and any other byte difference. Import direction cooperates (`fold_manifest` imports from `stock_evaluation_contract`), so the constant belongs in `stock_evaluation_contract` with `fold_manifest` importing it, which also removes today's duplicated literal. Known cost: the module and its artifact must then be re-pinned together, already the accepted pattern here (four such constants in `fold_manifest` alone). Left unapplied in this push because it modifies a reviewed contract loader and belongs in its own scoped correction with its own red/green mutation, not folded into this batch. |
| ARV2WL-D11 | Out of lane by the owner scope rule, and now **three** failures rather than two as the date advanced to 2026-09-02: `test_default_gain_review_is_fifty_percent_and_long_term_gated`, `test_every_lot_row_carries_the_tax_mechanism_fields` and `test_report_carries_no_action_shaped_field`. **The cause is more specific than the original "time-relative fixture" note.** The fixture pins a clock (`_NOW = 2026-08-07`) and builds each lot at `_NOW - timedelta(days=days_ago)`, but `evaluate_sleeves(...)` is called with no clock argument, so the report under test reads the real wall clock instead. A lot built with `days_ago=340` is therefore acquired 2025-09-01 and crossed one year on 2026-09-01, which is why the count grew from two failures on 2026-09-01 to three on 2026-09-02: the assertions `term_if_sold_now == "short"` and `0 < days_to_long_term <= 30` are only true inside a roughly 26-day window after the pinned `_NOW`. The fix belongs to the three-sleeve engine owner and is to thread the pinned clock into the call under test rather than to widen the assertions. **Proven to pre-exist this work rather than assumed:** with every change in this push stashed, the pristine tree at `35b3833` fails the identical three, and `tests/test_sleeve_report.py` imports nothing from the Analyst lane. Documented under rule 1; not fixed on this branch. |

### 19.5 Validation

- Focused ARV2 batteries after the corrections, plus the new
  `test_dormant_etf_portfolio_arithmetic.py` at **14 passed**.
- Full suite on the exact final tree recorded in this push's commit message.
- `compileall` exit 0; `git diff --check` clean; no frozen shared file touched;
  no committed artifact re-serialised; every production authority still empty
  and every action capability still literal false.

### 19.6 Next step

Codex counter-reviews this exact pushed head. ARV2-4D-B remains unauthorised
by the ARV2-4D-A approval and still requires a separately reviewed
input-manifest schema and exact calibration-input authority before any numeric
receipt exists. The four deliberately unfixed findings in 19.4 remain owner or
ARV2-5 decisions.

## 20. Codex counter-review of Claude commit `10ce9196`, 2026-09-02

**Exact snapshot received and reviewed:**
`10ce9196a33d1a60a597d2f30134315153882138`, whose parent is
`35b38331e68ef464f9de2fa20014682958f52a1e`. The local and fetched remote
lane tips matched and the worktree was clean before review. This was the only
new commit. Its ARV2-4D-A disposition is accepted: both recorded identities,
closed capabilities, complete parent authentication, scope disclaimer, and
absence of data/outcome/QC authority were reproduced. Its snapshot-root and
cost-arithmetic corrections are also accepted. The commit as a whole is
**accepted after correction** for the findings below.

### 20.1 Counter-review findings and exact dispositions

| ID | Pri | Disposition | Finding and correction |
|---|---|---|---|
| `ARV2CR13-001` | P2 | **Corrected** | The new coverage comparison converted already context-rounded Decimal aggregates to `Fraction`. A valid 52-digit mapped/unmapped pair whose exact coverage is below 99% therefore still rounded to `0.99 / 1` and passed. `mapped_candidate_coverage` now sums each accepted row as an exact `Fraction` before any 50-digit diagnostic arithmetic; the rounded Decimal coverage remains diagnostic only. |
| `ARV2CR13-002` | P2 | **Corrected** | `ARV2WL-D01` was closed by a water-filling test that did not require a second redistribution round; an unconditional break after the first binding round survived. The test now requires the two remaining names to reach 20% each and exact 40% cash. A locally authority-bypassed structural test also covers entry hysteresis, strictly stronger-entrant eviction, and incumbent precedence on an exact cutoff tie. |
| `ARV2CR13-003` | P2 | **Corrected** | `ARV2WL-D02` was called closed although the named authority test exercised only post-authentication mutation. The restored battery now covers a copied authenticated value, mutation, substituted source bytes, foreign policy, unauthorized dataset, foreign epoch, foreign decision clock, and an untyped naked mapping; its row-validation battery now covers missing/invalid states, clipping, and canonical order as well as missing/extra/duplicate/zero rows. |
| `ARV2CR13-004` | P3 | **Corrected** | `source_census` was optional, so callers could still construct a normalization result without the claimed exhaustive census. It is now required, always type/count checked, and populated by the sole production builder. The comment and record distinguish this local invariant from the actual source-derived authority supplied by revalidation against the authenticated audit. |
| `ARV2CR13-005` | P3 | **Corrected/qualified** | Naming `ALLOCATION_CONVERGENCE_TOLERANCE` did not bind it into `VerifiedAnalystPolicy` or the policy hash, so section 19 overstated `ARV2WL-D05` as closed. The exact `1e-18` value is now independently literal-pinned, and the code states honestly that policy-lineage binding or an exact-zero proof remains an ARV2-5 decision. |
| `ARV2CR13-006` | P3 | **Corrected** | The recorded denominator mutation could not have produced two failures because every added coverage fixture had denominator exactly one. A tolerance-valid overweight book now proves the denominator load-bearing: mapped `0.9909` over exact denominator `1.001` is below 99% and refuses. |
| `ARV2CR13-007` | P3 | **Record correction** | Section 19 lists `ARV2WL-D06` as unfixed even though section 14 and the current allowlist implementation show it was already closed by `ARV2CR11-003`. No new firewall production change is needed; the section-19 classification is superseded by this row. |
| `ARV2CR13-008` | P3 | **Record correction** | The current header and sections 2/4 still said ARV2-4D-A awaited review, and section 19 cited `ARV2R5-002` for the two-reviewer coordination observation. Current-state passages now record accepted-after-correction status; the historical reviewer-coordination ID is `ARV2R7-002`. The coordination question remains open and is not a source/statistical/action gate. |
| `ARV2CR13-009` | P3 | **Corrected** | One boundary-test docstring still described the superseded rounded-aggregate implementation and called the now-reproduced defect unreachable; another named closure omitted the naked-map refusal. Both claims and the missing guard are corrected. |

No P0 or P1 was found. The standing `ARV2WL-D11` Trading App date-relative
test failures remain outside this lane and were not changed. `ARV2WL-D04`,
`ARV2WL-D09`, and `ARV2WL-D10` retain the exact deferred dispositions in
section 19.4. `ARV2WL-D06` is already closed as corrected above.

### 20.2 Independent evidence

- As received, the exact changed-area battery was **213 passed, 1 host
  symlink skip in 198.50 s**.
- On Claude's implementation, the 52-digit coverage and required-census
  regressions were both red (**2 failed**); both passed after correction.
- Breaking after the allocator's first binding round made the strengthened
  redistribution regression red (**1 failed**), and restoring the loop made
  it green.
- Ignoring the coverage denominator made the new overweight-book regression
  red (**1 failed**), and restoring exact division made it green.
- The final counter-review battery is **217 passed, 1 host symlink skip in
  198.43 s**. `git diff --check` and broader cumulative validation are rerun
  after the next bounded milestone and recorded before the single push.
- No credential, provider or licensed row, price, return, outcome, QuantConnect
  action, broker, operator database, scheduler, deployment, or order was
  accessed. **Zero research looks and zero development evaluations.**

### 20.3 Next authorized bounded step

ARV2-4D-B remains unauthorized. The owner-directed 2026-08-30 four-family
multiplicity correction is the next safe data-free milestone. Introduced here
as branch-local label **ARV2-3Q-F**, it must be an additive authenticated child
of the immutable QC-first plan and an independent parallel leaf alongside the
separately authenticated power-protocol leaf: four exact permanent lane slots
share two-sided FWER `1/20`, Analyst receives at most `1/80`, unused or withdrawn
slots expire without transfer, redistribution, or denominator recomputation,
and all within-lane confirmatory allocations sum to no more than `1/80`. The
old `1/60` bytes remain unchanged as an authenticated superseded-unspent
ancestor. ARV2-4D-A's separate non-confirmatory `1/20` development
power-planning size remains unchanged. No outcome or action authority follows.

## 21. ARV2-3Q-F four-family multiplicity candidate, 2026-09-02

**Disposition:** implemented and self-reviewed as an outcome-free structural
candidate; pending Claude's independent review and Codex counter-review.
ARV2-4D-B remains unauthorized, and no later milestone is inferred from this
work.

### 21.1 Frozen policy and exact identity

The owner-directed selection family has exactly four permanent lane slots:
`analyst-revisions-v2`, `insider-buying`, `short-interest`, and
`target-price-revisions`. Their total two-sided family-wise alpha is exactly
`1/20`; each permanent lane maximum is exactly `1/80`. Unused or withdrawn
slots expire. Transfer, redistribution, and denominator recomputation are
prohibited. All Analyst confirmatory allocations must sum to at most `1/80`;
the sole currently planned, still-unbound Analyst look is allocated exactly
`1/80`.

The previously accepted three-lane `1/60` bytes remain unchanged and are
authenticated only as a superseded-unspent, nonrevivable predecessor. Missing,
copied, reconstructed, mutated, substituted, or foreign overlay objects refuse;
there is no fallback to `1/60`. ARV2-4D-A's separate non-confirmatory `1/20`
development planning size is unchanged and does not consume confirmatory
alpha.

The canonical candidate identities are:

- overlay ID:
  `arv2-four-family-multiplicity-54ab0bb69fb6fa16`;
- semantic SHA-256:
  `54ab0bb69fb6fa162ca3ba6764864b230136c68c017f1e6b669034dda75b806e`;
- exact artifact-byte SHA-256:
  `2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648`.

### 21.2 Additive lineage and authority boundary

No accepted ancestor was changed. The overlay is an additive child of the
strategy PDF, superseded QC base, and accepted QC-first plan. It is a separate
parallel leaf from the ARV2-4D-A power protocol: the power protocol is not in
this artifact's parent set, and this artifact does not claim to authenticate
their relationship. A future outcome-bearing composition must authenticate
both independently reviewed leaves.

The loader stable-double-reads and exact-byte-pins the overlay, QC-first plan,
superseded QC base, and zero-access look authority; validates their semantic
state and exact acyclic parent set; retains all four payloads in a private
weak-reference authority registry guarded by its own lock; and revalidates all
four before exposing any positive alpha value. The canonical JSON boundary
refuses alternate byte forms, duplicate keys, binary floating point,
non-finite constants, invalid UTF-8, and link traversal.

All 12 source, outcome, look, QC, result, deployment, and order capabilities
are literal `false`. All 14 external bindings are `null`. Repository evidence
records zero authorized/accepted observations, but explicitly does not claim
proof of unobserved external activity because no external zero-observation
receipt exists. No source, outcome, QC, deployment, or trading permission is
created.

### 21.3 Implementation self-review findings

| ID | Pri | Disposition | Finding and correction |
|---|---|---|---|
| `ARV2QF-001` | P2 | **Corrected** | The first loader draft authenticated the transitive superseded QC base only inside the nested parent loader and did not retain or revalidate its bytes under the overlay authority. The final loader binds its exact ID, semantic hash, raw SHA-256, path, and payload; revalidates it before publication and on every authority use; and has substitution, in-load mutation, and post-load mutation regressions. |
| `ARV2QF-002` | P3 | **Corrected** | The first zero-look wording could be read as proof of all external inactivity. The artifact now limits the assertion to repository gate state, records the exact evidence provenance, and leaves the external zero-observation receipt null. |
| `ARV2QF-003` | P3 | **Corrected** | Early parser tests used malformed fragments and the capability/binding checks derived their expected inventories from the artifact under test, so they could miss a coordinated weakening. The final tests mutate an otherwise valid artifact and carry independent literal inventories for all 12 capabilities and 14 bindings. |
| `ARV2QF-004` | P3 | **Corrected** | The first battery did not independently cover every positive getter, valid-type fingerprint mutations, parent/ancestor links, byte-versus-stat stable-read branches, the within-lane ceiling guard, or all post-load parent mutations. Dedicated regressions now cover each boundary; deleting superseded-base post-load revalidation makes the exact guard test red. |
| `ARV2QF-005` | P3 | **Record/artifact correction** | Initial wording incorrectly called the overlay a sibling of the QC-first plan and then overclaimed a bound sibling relationship to the power protocol. The final DAG makes the overlay a child of the immutable QC-first plan, excludes the power protocol from its parent set, and leaves their relationship for separately authenticated future composition. |

There are no unresolved P0-P3 findings in this milestone scope. The standing
out-of-lane `ARV2WL-D11` Trading App failures remain documented and were not
fixed. No unrelated production file or project-wide document was changed.

### 21.4 Validation completed before the implementation commit

- Canonical renderer equality, semantic ID/hash recomputation, and raw SHA-256
  reproduction pass for the exact checked-in artifact.
- ARV2-3Q-F file: **96 passed, 5 host symlink skips**.
- ARV2-3Q-F plus import-firewall/authority-registry battery: **212 passed, 5
  host symlink skips in 269.30 s**.
- Complete `tests/analyst_revisions_v2`: **782 passed, 8 host skips in
  608.13 s**.
- Complete repository on exact committed code tree `89f385c`: **7,279 passed,
  20 skipped, 3 standing out-of-lane failures, 25 warnings in 3,008.37 s
  (50m08s)**. The failures are the three date-relative Trading App assertions
  already proved and documented as `ARV2WL-D11`:
  `test_default_gain_review_is_fifty_percent_and_long_term_gated`,
  `test_every_lot_row_carries_the_tax_mechanism_fields`, and
  `test_report_carries_no_action_shaped_field`. No Analyst test failed, and no
  Trading App code or test was changed.
- Active-document consistency on the stabilized section 21: **69 passed in
  30.67 s**.
- Reverse mutation: deleting only the post-load superseded-base revalidation
  makes the exact four-artifact regression fail; restoring it passes.
- Package/test `compileall` exits 0 and `git diff --check` is clean apart from
  informational Windows line-ending notices.
- Three independent read-only audits examined production/artifact integrity,
  test sensitivity, and the milestone/authority gate. All three return
  **ACCEPT after correction with 0 remaining P0-P3** on the stabilized tree.

No credential, provider or licensed row, price, return, outcome, QuantConnect
resource, broker, operator database, scheduler, deployment, or order was
accessed. **Zero research looks and zero development evaluations.** The exact
final static/document gates and this repository-wide result are preserved in
a validation-only follow-up commit before the single push.

### 21.5 Next gate

Claude independently reviews the exact pushed counter-review and ARV2-3Q-F
commits. Codex then counter-reviews every Claude commit. ARV2-4D-B still needs
a separately reviewed input-manifest schema plus exact calibration-input,
rights, lineage, and nuisance-only computation authority. No data, outcome,
QC, paper, funded, deployment, or trading action may occur from this candidate.

## 22. Independent Claude review of Codex counter-review `7b804e7b` and the ARV2-3Q-F candidate, 2026-09-02

**Range reviewed:** `10ce9196..d2aefe6f`, three commits, each disposed below.
**Disposition: ACCEPTED AFTER CORRECTION.** 0 P0, 0 P1, 0 P2, **4 P3
corrected** (`ARV2R12-001..004`), 5 P3 documented. The declared policy,
identities, lineage, and authority surface were all reproduced first-hand and
match the owner's verification list exactly; every correction is a
defence-in-depth or test-sensitivity hardening of the overlay module and its
battery, and the artifact bytes and all three identities are unchanged.
**Zero research looks and zero development evaluations.** No provider,
credential, licensed row, price, return, outcome, broker, operator-database,
QuantConnect, upload, scheduler, order, UI or Streamlit access occurred, and
none was reachable: every production authority is empty or zero-access and
every action capability is literal false.

**Quality: ARV2-3Q-F candidate 9/10** - a faithful, fail-closed encoding of
the owner's four-lane decision with exact rationals, an additive acyclic leaf,
and a loader that survived every forge, crafted-byte, TOCTOU and junction probe
executed against it; the deductions are for semantic guards that were shadowed
by the byte pin and therefore untested. **Codex's counter-review `7b804e7b`
9.5/10** - it found a genuine residual fail-open in this reviewer's prior
coverage fix (a 52-digit book strictly below 99% was still eligible because
the aggregates were already context-rounded), reproduced here by executing the
`10ce9196` implementation, and every other correction strictly strengthened.

### 22.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `7b804e7b` | Accepted | Codex's counter-review of Claude commit `10ce9196`. Audited line by line against its base: it **only strengthens**. `mapped_candidate_coverage` now sums row weights as exact `Fraction` **before** any 50-digit Decimal arithmetic, so the eligibility decision no longer sees context-rounded aggregates (ARV2CR13-001, a genuine residual fail-open in the prior fix that this review missed); `FirmRatingNormalizationResult.source_census` is now required, integer-checked and count-checked (ARV2CR13-004); the water-filling test now demands a genuine second redistribution round (mid/low both reach exactly 0.20 with exact 0.40 cash) instead of the weaker "equal and under cap" assertion; the stock-score authority test now separately exercises clone, fresh-artifact mutation, source substitution, foreign policy and foreign dataset; the tolerance is regression-pinned at `1e-18` and its comment now states honestly that it is not yet bound into the policy hash (ARV2-5 decision). All 15 removed test lines were replaced by strictly stronger assertions; no guard was loosened and no public signature outside the lane changed. |
| `89f385cd` | Accepted after correction | The ARV2-3Q-F four-family multiplicity overlay: `four_family_multiplicity.py` (780 lines), the content-addressed structural artifact, a 30-test battery, and the firewall closure/allowlist registration of the new module and its private authority registry. Independent verification in 22.2. |
| `d2aefe6f` | Accepted | Record-only (section 21.4/21.5 and the final ledger row, 12 insertions, 3 deletions). Its validation claims match my independent reproduction below. |

### 22.2 Independent verification of ARV2-3Q-F

Every item on the owner's verification list was reproduced first-hand from the
committed bytes, not from the record:

- **Identity:** the artifact-byte SHA-256 is exactly
  `2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648`; the
  semantic SHA-256 recomputed with the module's recipe (null `overlay_id` and
  `overlay_hash`, `sort_keys`, `(",", ":")`, `ensure_ascii=False`,
  `allow_nan=False`, UTF-8) is exactly
  `54ab0bb69fb6fa162ca3ba6764864b230136c68c017f1e6b669034dda75b806e`, and the
  ID is its 16-hex prefix under `arv2-four-family-multiplicity-`. The
  checked-in bytes equal `render_expected_four_family_multiplicity_overlay()`
  byte for byte, and the pretty renderer round-trips the parsed document to the
  identical bytes.
- **Policy values:** the loader, fed the real overlay, `permanent_look_authority.json`
  and `arv2_qc_first.draft.json`, returns `shared_family_alpha = 1/20`,
  `analyst_confirmatory_alpha_ceiling = 1/80`,
  `analyst_prospective_look_alpha = 1/80` as exact `Fraction`s. The artifact
  stores every alpha as a reduced `{numerator, denominator}` rational and
  `_fraction` refuses unreduced, zero, negative, float or extra-key forms;
  `_validate_arithmetic` requires `4 * (1/80) == 1/20`, the Analyst allocation
  sum `<= 1/80`, equal to the declared `allocation_sum`, and the allocation
  inventory equal to the permanent look inventory. The whole document is also
  pinned to the module constant by `_require_exact`, so a single-field edit
  refuses twice.
- **Expiry, no transfer:** `slot_reallocation` is `transferable=false`,
  `unused=EXPIRES`, `withdrawn=EXPIRES`, `redistribution=PROHIBITED`,
  `denominator_recomputation=PROHIBITED`; the per-lane maximum is a constant
  `1/80` with no lane-count-dependent recomputation anywhere in the module, and
  the fixed four-lane inventory is pinned by ID and count.
- **Supersession without fallback:** `arv2_qc_first.draft.json` and every other
  pre-existing spec artifact are byte-identical across the range (`git diff
  --stat 10ce9196 d2aefe6f -- specs/` shows only the new overlay file). The
  loader authenticates the old plan through its own loader and then
  `_validate_parent_state` requires the superseded `1/60`, three-lane factor,
  Bonferroni label, the single look ID, null period/epoch/power-plan fields,
  `deployment_authorized=false`, and `confirmatory_alpha_spent=false` on both
  historical stages; any other state refuses. `require_loaded_four_family_
  multiplicity_overlay(None)` and every unauthenticated object refuse with no
  `1/60` path: the three positive getters exist only on the authenticated
  overlay and return constants.
- **ARV2-4D-A unchanged:** `arv2_stock_power_calibration_protocol.structural.json`
  (SHA-256 `ff16117a…`) was last touched at `ac6f06e4`, before this range; its
  `two_sided_size = 1/20` planning field is untouched, the overlay excludes the
  power protocol from its parent set and records
  `development_evaluations_consume_confirmatory_alpha=false`.
- **Capabilities and bindings:** all 12 artifact capabilities are literal
  `false`, all 14 external bindings `null`, and the seven runtime accessors
  (`grants_action_authority` plus six `*_available`) are constant `False` with
  no data-dependent path.
- **Authority surface:** `copy.copy` refuses at the weak-reference registry,
  `copy.deepcopy` and `pickle` refuse on the frozen mapping proxy, and
  `require_…` rejects subclasses by exact type and stale IDs by identity plus
  fingerprint; every authority use re-reads all four pinned files.
- **Lineage:** with child-to-parent edges, the PDF has no parent, the QC base
  names the PDF, the QC-first plan names the PDF and QC base, and the overlay
  names all three as parents and remains a leaf. No reviewed node or edge
  changed, and the overlay does not re-pin the fold manifest, stock specs, or
  4D-A leaf.
- **Firewall:** the new module is registered in the transitive closure and its
  `_FOUR_FAMILY_MULTIPLICITY_AUTHORITIES` registry in the private-state
  inventory; no execution, ML, network or legacy root is reachable.

### 22.3 Findings

| ID | Pri | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ARV2R12-001 | P3 | **Corrected** | `four_family_multiplicity.py` `_validate_arithmetic` | The Analyst `within_lane_confirmatory_alpha_ceiling` was never bound to the shared `permanent_maximum_per_lane`, and `look_budget` was never bound to the look inventory. With the exact-literal match bypassed (the pattern the existing over-ceiling regression uses), a `1/79` ceiling with a `1/79` allocation and a `look_budget` of 2 were accepted. On the checked-in tree both are refused twice (artifact SHA pin, `_require_exact`); the guard becomes load-bearing exactly when a reviewed successor relaxes the literal match under the artifact's own "bind or subdivide this allocation, never add alpha" policy. | Added `ceiling != lane_alpha` and `look_budget != len(permanent_look_ids)` refusals with a comment naming the failure direction; two bypass-exact regressions. The real artifact still loads and no identity changes. | Removing each guard reddens its regression (1/1); restored green. |
| ARV2R12-002 | P3 | **Corrected** | `tests/analyst_revisions_v2/test_four_family_multiplicity.py` | The alpha-constant closure, `_validate_parent_state` (the superseded-unspent `1/60` tombstone) and `_validate_zero_look_authority` had no independent test sensitivity: neutralising each left the 96-test battery green, because the parent and look-authority byte pins shadow them. Two independent lens audits measured this; one rated the tombstone gap P2 because that check is the only guard the moment the parent constants are re-pinned to a re-frozen plan. Section 21.3 `ARV2QF-004`'s "load-bearing" wording was accurate only for the within-lane ceiling line. | Added a self-consistent `1/10` family / `1/40` lane refusal; five weakened-parent stubs (spent stock stage, revived `1/40` alpha, started paper period, deployment authorised, two-lane factor) delivered through a patched nested loader, all refusing `parent state cannot be authenticated`; and a re-pinned positive look authority refusing on the semantic guard alone. | Neutralising the three guards reddens 1 / 5 / 1 regressions; restored green. |
| ARV2R12-003 | P3 | **Corrected** | `tests/analyst_revisions_v2/test_four_family_multiplicity.py` | Link refusal had zero executed coverage on the supported Windows host: all five symlink tests skip for lack of privilege (`WinError 1314`) and there was no junction case, although `_is_link_like` handles junctions and refuses them when exercised directly. | Added junction-based regressions via `_winapi.CreateJunction` (no privilege required) for a junctioned ancestor directory and for each supplied path individually; they skip outside Windows. | Removing the parent-chain link check reddens all 4; restored green. The 5 symlink skips remain and are now backed by executed junction coverage. |
| ARV2R12-004 | P3 | **Corrected** | `tests/analyst_revisions_v2/test_four_family_multiplicity.py` | The seven action accessors are literal `return False`, but nothing pinned that: rewriting one to read the artifact's `capabilities` survived because the data is also false. | AST regression asserting each accessor body is exactly one literal `return False`. | Making `orders_available` data-dependent reddens it; restored green. |

### 22.4 Documented, not fixed

| ID | Pri | Location | Observation |
|---|---|---|---|
| ARV2R12-D01 | P3 | `holdings.py:715-726` | `CoverageResult.coverage` is still the 50-digit-rounded Decimal quotient, so a 52-digit book strictly below 99% now reports `coverage == minimum_coverage == 0.99` beside `eligible=False`. It fails closed and `require_verified_holdings_evidence` recomputes eligibility rather than deriving it from `coverage`; the only risk is a future presenter reading the rounded diagnostic as the decision. ARV2-5 may carry the exact rational or mark the field as rounded. Not introduced by `7b804e7b`; made observable by its correct fix. |
| ARV2R12-D02 | P3 | `four_family_multiplicity.py` `_parse_artifact`, `_validate_zero_look_authority` | Both JSON boundaries wrap only Unicode and JSON decode errors. With the relevant byte pin bypassed in memory, a 5,000-digit integer raises the raw interpreter digit-limit `ValueError` and extreme nesting raises `RecursionError`. Both fail closed, and their SHA pins refuse first in production; typed-error tidiness only. Codex reproduced the same scope extension against the zero-look parser in section 23. |
| ARV2R12-D03 | P3 | `four_family_multiplicity.py` | Several layers (overlay artifact SHA pin, content-identity check, the type-plus-sentinel check and dead-weak-reference check in `require_…`) have no individual mutation sensitivity because a stronger neighbouring layer shadows each. This is deliberate defence in depth and is recorded so the redundancy stays a conscious choice. |
| ARV2R12-D04 | P3 | `four_family_multiplicity.py:560-567, 693` | `overlay.definition` is readable without calling `require_…`, and the nested QC-first loader receives the caller's unresolved path rather than the resolved one. Both are harmless today (no consumer exists; post-nested byte revalidation and content-hash equality close the window); the composing milestone should state the "call `require_` first" convention. |
| ARV2R12-D05 | P3 | future paper-ready freeze | The prospective look's power plan must be computed at two-sided `1/80` (`effective_power_plan_alpha_field`); the ARV2-4D-A `z_0.975` planning at `1/20` does not transfer. The overlay already encodes this; noted so the ARV2-8 freeze does not assume it. |

**Out-of-lane, documented and not fixed:** the three standing `ARV2WL-D11`
Trading App sleeve-report assertions (`tests/test_sleeve_report.py`) remain
the only repository failures; no Trading App code or test was touched.

### 22.5 Validation

- Semantic identity, artifact identity, renderer equality, loader
  acceptance, policy getters, capability accessors, and forge refusals were
  reproduced first-hand from the committed bytes (section 22.2).
- As-received focused batteries on the exact pushed tree `d2aefe6f` (overlay,
  dormant arithmetic, ratings ingest, dataset/firewall): **280 passed, 5 host
  symlink skips**.
- Complete repository suite on the exact as-received tree `d2aefe6f`: **7,279
  passed, 20 skipped, 3 failed, 25 warnings in 1,487.80 s** in a pinned
  base-temp; the three failures are the standing out-of-lane `ARV2WL-D11`
  Trading App sleeve-report assertions, identical to section 21.4. Every
  Analyst test passed as received.
- Corrected overlay file on the final tree: **116 passed, 5 host symlink
  skips** (96 as received plus 20 `ARV2R12` regressions); overlay plus
  dataset/import-firewall battery **232 passed, 5 skips**.
- Complete Analyst V2 battery (`tests/analyst_revisions_v2`, contracts,
  preregistration) on the final tree `64edf355`: **894 passed, 8 host skips
  in 286.97 s**.
- Complete repository suite on the exact final code tree `64edf355`: **3 failed, 7299 passed, 20 skipped, 25 warnings in 1572.05s (0:26:12)** in a pinned base-temp; the only failures are the same three standing out-of-lane `ARV2WL-D11` Trading App sleeve-report assertions, and every Analyst test passes.
- Active-document consistency on the stabilised section 22:
  **69 passed in 1.70s**
- Reverse mutation on the final tree: removing the ceiling binding, the
  look-budget binding, the alpha-constant check, the parent tombstone check,
  the zero-look semantic guard, the parent-chain link check, and one literal
  accessor reddens 1 / 1 / 1 / 5 / 1 / 4 / 1 regressions respectively; the
  module was restored byte-exact after each and the battery is green.
- `compileall` over the Analyst package and tests exits 0; `git diff --check`
  clean; staged blobs verified LF; Python 3.12.13. The only production change
  is fifteen added lines in `four_family_multiplicity.py`; the artifact bytes,
  every spec artifact, and every frozen or shared document are untouched.
- Independent lens audits (loader/forge, policy semantics, counter-review
  corrections) were run read-only with pinned base-temps and left the
  worktree clean; every finding above was verified by this reviewer before
  disposition. **Zero research looks and zero development evaluations.**

### 22.6 Next step

Codex counter-reviews this exact pushed head. ARV2-4D-B remains unauthorized
and needs a separately reviewed input-manifest schema plus exact
calibration-input, rights, lineage, and nuisance-only computation authority.
The four-family overlay is a candidate pending Codex counter-review; a future
outcome-bearing composition must authenticate both the overlay and the 4D-A
leaf independently. No credential, provider, outcome, QC, paper, funded,
deployment, or trading access is authorized, and none was used here.

## 23. Codex counter-review of Claude commits `64edf355` and `c83218c7`, 2026-09-03

**Exact pushed snapshot received:**
`c83218c7583c9cbfc7840f02324a431ab00a33ad`, whose parent is correction
commit `64edf355cc5afce4df770100ef2772d024dc3649` and whose review base is
`d2aefe6f7212ae632c64aa4aa82c19f047d08617`. The dedicated worktree was
clean, the local branch was fast-forwarded without switching, and the fetched
remote and local tips matched before review.

**Disposition:** `64edf355` is accepted. `c83218c7` is accepted after the
record corrections below. The cumulative ARV2-3Q-F candidate is accepted
after correction. No production code, test, artifact, or authority change is
required by this counter-review.

### 23.1 Commit-by-commit disposition

| Commit | Disposition | Basis |
|---|---|---|
| `64edf355` | **Accepted** | The 15-line production addition correctly binds the Analyst ceiling to the shared permanent `1/80` slot and requires an exact-integer look budget equal to the permanent-look inventory. The 20 new regressions isolate the two arithmetic guards, alpha constants, superseded-parent tombstone, zero-look semantics, four executable Windows junction paths, and all seven literal-false accessors. No existing test was weakened; the overlay artifact and all identities are unchanged. |
| `c83218c7` | **Accepted after record correction** | Section 22 correctly disposes all three prior Codex commits and reproduces the artifact, policy, authority, test, and zero-look evidence. Four current-state/wording defects are corrected in sections 2, 3, 4, and 22 and retained in the ledger below. |

### 23.2 Counter-review findings

| ID | Pri | Disposition | Finding and correction |
|---|---|---|---|
| `ARV2CR14-001` | P2 | **Corrected** | The current canonical contract still described the future Analyst paper look as `1/60` under the superseded three-lane correction. That contradicted the now-effective four-lane `1/80` maximum and could cause a later paper freeze to overallocate confirmatory alpha. The current contract summary now says `1/80` and explicitly tombstones the predecessor `1/60` as superseded-unspent and nonrevivable. No historical ancestor or artifact was changed. |
| `ARV2CR14-002` | P2 | **Corrected** | The section-2 current-state rows and exact-next-step handoff still said ARV2-3Q-F awaited Claude review after section 22 completed it. They now record completion of Claude review and this Codex counter-review while preserving the absence of every source, outcome, QC, deployment, and trading authority. Historical section-21/22 sequencing text and the immutable artifact lifecycle label remain historical rather than being rewritten. |
| `ARV2CR14-003` | P3 | **Corrected** | Section 22 described `PDF -> qc_base -> qc_first_plan -> overlay` as child-to-parent even though those arrows read parent-to-child and omitted direct parent edges. It now states the exact parent set for every node under the artifact's declared child-to-parent edge direction. |
| `ARV2CR14-004` | P3 | **Corrected/documented; no code change** | `ARV2R12-D02` scoped the raw `ValueError`/`RecursionError` normalization gap only to `_parse_artifact`. A direct 5,000-digit probe shows `_validate_zero_look_authority` has the same typed-error tidiness gap. The row now covers both. Each path remains fail-closed and is reached only after its exact SHA pin is deliberately bypassed, so no loader correction is warranted in this round. |

No P0 or P1 was found. The two P2s are current-record contradictions, not
production behavior defects. The only code correction in the received range
remains Claude's valid 15-line hardening.

### 23.3 Retained documented observations and lane boundary

`ARV2R12-D01`, `ARV2R12-D03`, `ARV2R12-D04`, and `ARV2R12-D05` retain their
section-22 dispositions. `ARV2R12-D02` remains in-lane, fail-closed, and
deliberately documented rather than fixed; only its scope is completed here.

The three `tests/test_sleeve_report.py` date-relative failures remain the
standing out-of-lane `ARV2WL-D11` Trading App issue. They are documented with
their existing evidence and recommended owning fix in section 19.4. This
counter-review does not alter Trading App code or tests. No unrelated finding
is silently repaired on the Analyst branch.

### 23.4 Independent evidence and validation

- The exact correction diff is 15 production lines plus tests; artifact raw
  SHA-256 `2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648`
  and semantic SHA-256
  `54ab0bb69fb6fa162ca3ba6764864b230136c68c017f1e6b669034dda75b806e`
  reproduce unchanged.
- Focused overlay plus import-firewall battery: **232 passed, 5 host symlink
  skips in 277.10 s**. The new junction cases execute rather than skip on this
  Windows host.
- Direct no-I/O parser probe: both `_parse_artifact` and
  `_validate_zero_look_authority` raise the raw interpreter digit-limit
  `ValueError` for a 5,000-digit JSON integer, confirming the documented scope
  extension without reading an external artifact.
- Three independent read-only audits found no production or test defect in
  `64edf355`; the record/gate audit independently reproduced **116 passed, 5
  skips** for the overlay file and **69 passed** for active-document
  consistency and identified the four record findings above.
- Complete Analyst V2 battery (directory plus contracts, legacy quarantine,
  preregistration, and statistics): **909 passed, 8 host skips in 805.23 s
  (13m25s)**.
- Exact repository tree: **7,299 passed, 20 skipped, 3 standing
  `ARV2WL-D11` out-of-lane failures, and 25 warnings in 3,428.89 s
  (57m08s)**. The failures are exactly
  `test_default_gain_review_is_fifty_percent_and_long_term_gated`,
  `test_every_lot_row_carries_the_tax_mechanism_fields`, and
  `test_report_carries_no_action_shaped_field`; no Analyst test failed.
- Compilation exits zero. Active-document consistency is **69 passed** after
  the final record edit; final diff, staged-content, branch, and status gates
  are run before the local commit.

No credential, provider or licensed row, price, return, outcome, QuantConnect
resource, broker, operator database, scheduler, deployment, or order was
accessed. **Zero research looks and zero development evaluations.**

### 23.5 Exact next gate

No subsequent implementation milestone is authorized. ARV2-4D-B still needs
separate owner authority for a reviewed calibration input-manifest schema,
exact input identities and access, processing/storage rights, lineage, and the
permitted nuisance-only computation. Outcome access, QC upload/compile/launch,
backtesting, paper/funded deployment, and trading remain separately blocked.

Under the same-lane workflow, this owner-decision blocker stops the round
before ARV2-4D-B and before a push. Commit this counter-review record locally;
the owner may then authorize a counter-review-only push or define and authorize
the exact ARV2-4D-B input-manifest milestone for a later combined round.

## 24. Owner-authorized ARV2-4D-B1 schema-only candidate, 2026-09-03

### 24.1 Later authorization and bounded scope

Section 23.5 is preserved unchanged and was correct when written. The
counter-review record was committed as `6baa13d2` and pushed before this work.
The owner then explicitly authorized only ARV2-4D-B1: an outcome-free
calibration-input manifest schema using synthetic fixtures. That later
direction supersedes the section-23 stop only for this bounded candidate; it
does not authorize full ARV2-4D-B.

The candidate adds the content-addressed structural artifact, its authenticated
immutable loader and in-memory synthetic-fixture validator, a dedicated test
battery, and exact import-firewall/authority-registry inventory entries. It
does not load a production manifest or input artifact, compute nuisance
statistics, issue a numeric receipt, bind a stock successor, access outcomes
or QuantConnect, deploy, or trade.

### 24.2 Frozen candidate contract and identity

- Schema ID:
  `arv2-stock-power-calibration-input-schema-4032405d1773236e`.
- Semantic SHA-256:
  `4032405d1773236e61938a88c6ec77e62bbbd71ff8e24eb615565023c07f8e24`.
- Exact-artifact SHA-256:
  `e642d06531b6ca024c3ee438ee88a113eef1483f2f6fca9d0e120afcfc5ed2f1`.
- Canonical artifact size: **15,136 bytes**.

The schema is an additive leaf whose sole direct parent is the accepted
ARV2-4D-A power protocol. ARV2-3Q-F remains an independent parallel leaf; the
first future outcome-bearing composition must authenticate both. Synthetic
fixtures must carry the exact 483 ordered sessions, the ordered
`date_level_beta_series` and `component_count_census` roles, complete beta
state and exact nonnegative component-count censuses, closed declared counts,
canonical identities/hashes, and strict sorted UTF-8 JSON.

The eight-field evidence-epoch binding contains synthetic epoch/artifact IDs,
semantic and raw hashes, a canonical UTC capture instant, the exact
`2020-01-30` calibration-information cutoff, the `2020-01-31` first excluded
session, and literal-false post-cutoff corrections. Every lineage node binds
that epoch. Lineage roles are closed to source, transformation, and the two
terminal input roles; every terminal has ancestry, every source root is
rights-bound for each descendant role, every node is reachable, and terminal
nodes cannot parent another node.

Synthetic rights metadata grants no legal, access, processing, transfer, or
storage authority. All 14 schema external bindings and 11 fixture external
authorities are null; all 14 capabilities are exact false. Production mode is
recognized only to refuse.

### 24.3 Findings corrected before candidate freeze

| ID | Pri | Disposition | Finding and correction |
|---|---|---|---|
| `ARV2I4DB1-001` | P2 | **Corrected** | The first validator accepted a fully rehashed two-terminal lineage with no source ancestor. The final contract requires closed roles, at least one distinct rights-bound source root, nonempty terminal ancestry, transformation-only intermediates, complete reachability, and terminal leaf status. The exact former exploit now refuses. |
| `ARV2I4DB1-002` | P2 | **Corrected** | A free epoch label did not content-bind vintage/cutoff semantics. It was replaced by the exact eight-field evidence-epoch binding; malformed IDs/hashes/time, cutoff drift, post-cutoff correction claims, and node-epoch drift refuse. |
| `ARV2I4DB1-003` | P3 | **Corrected** | A source root could have empty rights or rights for the wrong descendant role. Each ancestral source root must now carry a known binding applicable to that exact terminal role; empty, unknown, and one-sided mutations refuse. |
| `ARV2I4DB1-004` | P3 | **Corrected** | The initial battery lacked individual sensitivity for the above boundaries and malformed hash/Git/scope fields. Dedicated one-violation regressions now cover them. The acyclicity call remains defense in depth behind parent-before-child and exact-DAG validation. |

No P0 or P1 was found. A final independent audit found no remaining P0-P3.
Claude review and subsequent Codex counter-review remain required.

### 24.4 Validation and scope evidence

- B1 file: **252 passed, 2 host symlink-privilege skips**; the Windows junction
  case executed and passed.
- B1 plus full Analyst import firewall: **368 passed, 2 skipped in 345.17 s**.
- The complete Analyst V2 run reached **79% with zero failures/errors** before
  the owner requested immediate finalization; the complete repository run
  reached **9% with zero failures/errors** before the same stop. These partial
  runs are not represented as completed suites.
- Renderer bytes, semantic identity, and raw identity reproduce exactly.
  ARV2-4D-A remains byte-identical at
  `ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13`;
  ARV2-3Q-F remains byte-identical at
  `2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648`.
- The transitive import firewall covers exactly **34 modules**. Compileall and
  `git diff --check` exit zero.

No credential, provider/licensed row, source input, price, return, outcome,
QuantConnect resource, broker, deployment surface, scheduler, or order was
accessed. **Zero research looks and zero development evaluations.** The
standing out-of-lane `ARV2WL-D11` Trading App issue remains documented and was
not changed.

### 24.5 Next gate

ARV2-4D-B1 is an implementation candidate, not production authority. Claude
must review the exact pushed snapshot, after which Codex counter-reviews every
Claude commit. Full ARV2-4D-B remains blocked on an independently reviewed
production manifest, exact input identities/access and rights, authenticated
nuisance-only computation, a numeric receipt, successor binding, and separate
outcome/QC/deployment/trading authorities. No B1 schema, synthetic fixture,
rights metadata, hash, lineage, or summary can self-promote into those gates.

## 25. Independent Claude review of ARV2-4D-B1, 2026-09-03

**Range reviewed:** `6baa13d..42faec1`, one candidate commit.
**Disposition: ACCEPTED.** 0 P0, 0 P1, 0 P2, 0 P3. No correction was
required, so this push is record-only; the candidate tree at `42faec1` is
unchanged.
**Zero research looks and zero development evaluations.** No provider,
credential, licensed row, price, return, outcome, broker, operator-database,
QuantConnect, scheduler, deployment or order access occurred. Codex reported
its complete Analyst and repository runs were stopped at 79% and 9%; both were
completed here (25.6).

**Reviewing session:** the Fable 5 session on the work identity (also
sections 4I, 4R, 7 and 19). The other Claude session's ownership question in
`ARV2R5-002` remains open.

### 25.1 Commit disposition

| Commit | Disposition | Basis |
|---|---|---|
| `42faec1` | Accepted | Schema module, frozen artifact, 56-function battery (252 cases), firewall inventory entry, section 24. Verified in 25.2 to 25.4. |

### 25.2 Verified rather than accepted

Every identity and structural claim in section 24 was recomputed from bytes,
not read from the record:

- **Frozen identity reproduces exactly.** Artifact 15,136 bytes, SHA-256
  `e642d06531b6ca024c3ee438ee88a113eef1483f2f6fca9d0e120afcfc5ed2f1`;
  recomputed semantic hash `4032405d1773236e...` and derived schema ID match;
  the module's renderer output is byte-identical to the checked-in file; LF
  only, no BOM; `specs/.gitattributes` `-text` applies to the new file.
- **The 483-session axis is real, not asserted.** `data.exchange_calendar`
  yields exactly 483 XNYS sessions from 2018-01-31 through 2019-12-31
  inclusive, and the canonical SHA-256 of that list equals
  `CALIBRATION_AXIS_SHA256`. The 20th session after 2019-12-31 is
  2020-01-30 (the cutoff) and the first session strictly after it is
  2020-01-31 (first excluded). The `arv2-wf-test-2020-h20` fold block in the
  fold manifest carries the same boundaries and structural hash
  `9dcaa09e...`.
- **Parent and parallel leaf unchanged.** The first nine lineage nodes are
  identical to the ARV2-4D-A artifact's; B1 is the tenth, parented only on
  `power_protocol`. ARV2-4D-A is byte-identical at `ff16117a...` and
  ARV2-3Q-F at `2e9f390e...`; no reviewed artifact was edited, re-pinned or
  re-parented.
- **Closed authority surface.** 14 schema capabilities and 14 external
  bindings, 11 fixture external authorities, 9 schema and 5 summary action
  accessors: all literal false or null. The summary type cannot be
  constructed directly. The module's only file access is the stable two-read
  authentication of its own artifact; it has no environment, network,
  process or write surface.
- **Import firewall** closes at exactly 34 modules with zero forbidden roots.

### 25.3 Adversarial probes beyond the battery

Eighteen hand-built fixtures behaved correctly: pre-cutoff capture instant
(`2020-01-30T23:59:59.999999Z`) refused and the exact boundary
(`2020-01-31T00:00:00.000000Z`) accepted; `+00:00` offset, missing
microseconds and an unreal `2020-02-30` refused; a fourth beta state, a
boolean component count, extra root and nested keys, production mode, an
asserted external authority, a `0`-for-`False` capability, a Saturday axis
key and a swapped axis pair all refused; rights covering one role, a root
with empty rights, and a second source root whose rights cover only the
component role while feeding the beta terminal all refused with the intended
reason. A valid fixture yields a frozen summary that refuses attribute
assignment.

**Parent-bytes question closed.** B1's loader checks the parent's semantic
hash, not its artifact bytes, so I tested whether a semantically identical but
differently serialised ARV2-4D-A artifact could be substituted. It cannot:
the protocol loader's own canonical-render check refuses it, and because that
render is sorted and deterministic, the semantic hash pins the bytes
transitively. This is the property the standalone stock-spec loader lacks
(`ARV2WL-D10`); it holds here. An identical-bytes clone at another path loads,
confirming the pin is on content rather than location.

### 25.4 Mutation matrix on the four corrected findings

Run in a detached scratch worktree at `42faec1`; the lane tree was never
modified.

| Guard removed | Battery result |
|---|---|
| `ARV2I4DB1-003` root rights need not cover the terminal role | 1 failed |
| `ARV2I4DB1-002` capture-instant not-before bound | 1 failed |
| `ARV2I4DB1-001` orphan lineage nodes allowed | 1 failed |
| `ARV2I4DB1-001` terminal may parent another node | 1 failed |
| lineage-node evidence-epoch drift allowed | 1 failed |
| production mode accepted | 1 failed |
| `ARV2I4DB1-001` `if not source_roots` refusal | **252 passed (survived)** |

The survivor is unreachable by construction rather than untested: the node
list must be nonempty, the first ordered node cannot have parents because
parents must precede children, and any parentless node must already be a
rights-bound `source_artifact` or the loop refuses. The exact former exploit
(a two-terminal lineage with no source ancestor) is refused by those earlier
guards, so the correction stands; the line is defense in depth. No test was
fabricated to cover a branch that cannot execute.

### 25.5 Observations carried forward, not findings

- The evidence-epoch capture instant has a lower bound but no upper bound, and
  `post_cutoff_corrections_included: false` is a self-declaration the schema
  cannot verify. That is correct for a schema-only, outcome-free milestone
  and is declared as syntactic-only in the artifact, but the production
  ARV2-4D-B2 manifest will need vintage evidence for that claim rather than a
  flag.
- The single survivor above should stay as written; converting it to a test
  would assert an impossible state.
- The standing out-of-lane `ARV2WL-D11` Trading App failures are unchanged
  and are the only failures in the completed repository run (25.6).

### 25.6 Validation on the exact candidate tree

- B1 battery alone: **252 passed, 2 host symlink-privilege skips** in 87.9 s,
  reproducing section 24 exactly.
- Complete repository suite: **3 failed, 7,550 passed, 23 skipped, 25 warnings in 2,826.65 s (47:06)**. The three failures are `tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated`, `::test_every_lot_row_carries_the_tax_mechanism_fields` and `::test_report_carries_no_action_shaped_field`, the standing out-of-lane `ARV2WL-D11` clock-threading defect diagnosed in section 19.4; nothing in this range touches that file and it imports nothing from this lane. Every Analyst V2 test passed.
- Active-document consistency gate passes after this section was added;
  `compileall` exit 0; `git diff --check` clean; no frozen shared file
  touched; no committed artifact re-serialised.

### 25.7 Next gate

Codex counter-reviews this exact pushed head. ARV2-4D-B2 and the full
ARV2-4D-B remain unauthorised: no production manifest loader, input access,
rights authentication, nuisance computation, numeric receipt, successor
binding, outcome, QC, deployment or trading action exists or is implied by
this acceptance.

## 26. Owner-directed cross-lane bug-fix integration applied (2026-09-04)

The owner directed the dedicated Review lane session to fix, on the
`main`-derived branch `Feature-bug-fix-integration-2026-09-04`, the shared
trading-application / test-infrastructure / repository-tooling issues that this
record and the sibling lane records had documented but, under the lane scope
rule, deliberately not fixed, and to apply the identical commits to every lane
branch so no lane carries a divergent copy of a shared file. This lane received
them as cherry-picks; no lane-owned file changed.

| Integration-branch commit | Cherry-pick on this lane | Content |
|---|---|---|
| `7f99f303d0b6f5a2a65aa5b5b49f9c52256716d8` | `bbf228c452cb83c53bec9ceb85d913cc693fc7d8` | sleeve-report clock seam, runtime-stop leak redirect + conftest guard, shared EOL attributes, Briefing smoke isolation, characterization test rename |
| `3114a1530f0afa400eb200e79ff218c174657e69` | `d71f249b5f18d7bdfba7f3b68963ec557be8bc4e` | notification cycle evaluates at its own clock; guard decoder bound at import |
| docs commit | `d1cbf82a1c610bdd4dc12636a947603bf650350d` | `docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md` (fix table, full disposition ledger, owner decisions) plus the four-lane README, the direction status paragraph, and the workflow exception paragraph |
| `6ef66eed77f9b24ea3df8aa538f42de0c871c824` (F-8, owner direction, same day) | `7e38b93fa8aed0e753b377ee636117e174b4b0bb` | `tests/target_price_revisions/test_preregistration.py::test_self_declared_review_and_registry_substitution_refuse` made deterministic across harness layouts (Analyst `ARV2-UNRELATED-001` / Short-interest `SI-OOL-003`); the loader is unchanged |
| integration record update | `90f2cd06f35132535f866d5c2723cf2cc2ea2d4e` | F-8 recorded in `docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md` (fix table, ledger rows, validation) |

Items of this record closed by the application: ARV2WL-D11 (F-1); the repository-wide root `.gitattributes` gap noted in section 4I.5 (F-4). `ARV2-UNRELATED-001` is not a stale message: it depends on where pytest's `tmp_path` lives and is routed to the Target-price lane, which owns that test. Every other
out-of-lane item this record carries was examined; its disposition and reason
are in the integration record's section 5, and the items needing an owner
decision are listed in its section 6.

This application is not acceptance of any lane milestone and grants no
provider, outcome, look, QuantConnect, broker, operator-database, deployment,
paper, live, or trading authority. The lane's same-branch review loop resumes
from this head. Validation on this lane's resulting head: focused set (sleeve report/notifications, leak guard, EOL attributes, crash-test redirect, Briefing smoke, reservation characterizations, active-document consistency): 174 passed in 24.22s.

**Follow-up, same day (F-8).** After the integration record showed that
`ARV2-UNRELATED-001` / `SI-OOL-003` were not a stale message but a
harness-layout dependency — `_repository_root` walks up from the spec, so a
spec written straight into pytest's `tmp_path` reaches the "not inside a Git
repository" refusal under an external base temp and the "committed and clean"
refusal under a repository-local `--basetemp` — the owner directed that the
Target-price test be fixed as well. The test now asserts the exact refusal its
own location must reach (`_bare_tmp_path_refusal` mirrors the loader's
discovery order) and adds two layout-independent assertions that exercise the
other branches explicitly (a self-declared review in a foreign repository →
`share one repository`; an uncommitted one inside the anchored repository →
`committed and clean`). `research/target_price_revisions/preregistration.py`
is unchanged; this is a test-determinism correction and grants no authority. Validation on this head: Target-price preregistration test file plus active-document consistency: 152 passed, 2 skipped in 26.50s.
