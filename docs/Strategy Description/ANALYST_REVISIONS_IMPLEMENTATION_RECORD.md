# Analyst Revisions ETF Strategy V2 — implementation and session record

Status: **ARV2-1 ACCEPTED. ARV2-2 PIT IDENTITY/OUTCOME-PREREQUISITE CANDIDATE
ACCEPTED AFTER CLAUDE REVIEW AND CODEX COUNTER-REVIEW CORRECTION. ARV2-3 IS
NEXT. NO AUTHENTICATED PRODUCTION EVENT EXISTS. NO V2 SIGNAL/SCORE,
CROSS-SECTION, NONEMPTY PORTFOLIO, OUTCOME TEST, QC RESULT, OR DEPLOYMENT
EXISTS.**

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
| Snapshot and source authority | V2 snapshot manifest v2 now binds the exact capture instant as well as complete/diagnostic type, partition/page/raw inventory, locator/hash, and clean producing lineage. Capture chronology cannot postdate verification and is part of every downstream manifest identity. The checked-in research-source authority remains an exact immutable `zero_access` declaration with no positive entries. | A separately governed, append-only production-source authority must admit an exact real artifact after source entitlement, semantics, completeness, retention, and exact vendor permission/rights for transfer to QuantConnect/QC processing are independently established. | Structural ingest implemented as an unreviewed candidate; production source access still refuses. |
| Event normalization | In addition to the zero-access canonical-event/refusal/result contracts, V2 now has a content-addressed Massive/Benzinga provider contract, exact documented field/action parsing, one source-derived ingest disposition per raw row, duplicate-ID refusal, immutable raw-hash version IDs, two-snapshot correction/addition/disappearance lineage, and an exhaustive structural binding of accepted rows to PIT permanent identity or a named refusal. The firm/identity join retains the exact ARV2-1 rational mapping. Legacy `research/acer/` rows remain legacy evidence. | The production source, security-master, and firm-ontology registries are empty. The older zero-access `CanonicalSourceEvent` representation is not yet a publishable rational firm-score event, and no real event has passed production registration. | ARV2-1 accepted; ARV2-2 structural identity candidate implemented; accepted production events remain prohibited. |
| Time semantics | Exchange-session availability rules, strict UTC instants, next-open handling, and the conservative date-only delay are implemented as deterministic contracts. | Provider clock semantics and actual timestamp completeness have not been authenticated for a production V2 snapshot. | Safety rule implemented; no production event admitted. |
| Firm identity and rating ontology | A loader-authenticated, content-addressed mapping now requires firm ID/name, half-open valid date range, exact raw label, complete ordered rank/scale size, company/sector/absolute scope, mapping quality, reviewer, source evidence, and ontology version. It implements the blueprint score as an exact rational number, refuses unreviewed labels and periods, inventories observed labels without ordering them, admits only direction-consistent upgrades/downgrades, and keeps initiations, target-only actions, and terminations out of the rating-change channel. A separate fixed Git-anchored production registry now prevents a structural fixture from self-promoting. | The committed production ontology registry is empty. No production firm-specific ordered vocabulary, reviewed policy artifact, or authenticated permanent firm/analyst identity mapping exists. No label is inferred from the public sample or legacy ACER map; documented `assumes` remains quarantined pending semantic review. | ARV2-1 accepted; production ontology access refuses. |
| Canonical stock formula | Deterministic primitives cover genuine changes, independent breadth, robust sector normalization, the ETF-specific reliability calculation, and explicit invalid/sparse states. The frozen 20-session half-life was policy-only through ARV2-2; no stock-specific decay/reliability assembler had yet been implemented. | No authenticated production events, sector classifications, measured stock-level data quality, or score artifact exist. | Formula safety primitives implemented; no production signal or score. |
| Consensus, novelty, targets, and EPS | Canonical-versus-diagnostic separation is contract-pinned; legacy target/timing runners are quarantined from V2 and from new outcome access. | No production historical active-rating state, novelty series, or decision-grade target/EPS extension has been built or authorized. | Deferred diagnostics/extensions; they cannot alter the canonical score. |
| Provider-history boundary | Measured pre-2013 source rows retain the exact dominant quarantine even when another defect is present and cannot be laundered through a later partition. Chronologically captured snapshots compare stable IDs/raw hashes as unchanged, added, corrected, or missing-from-later-without-invented-withdrawal. | Provider coverage, backfill, correction, and deletion semantics remain unauthenticated for V2 production use; no current licensed snapshot was accessed in this milestone. | Structural lineage implemented; factual provider audit still requires exact owner authorization. |
| Issuer/security identity | A canonical, content-addressed, loader-reauthenticated PIT master now separates issuers, securities, share classes, vendor/standard identifiers, listings, and lineage. It binds base and interval-closure availability, redacts future endpoints, resolves historical tickers by event date/cutoff, preserves ticker reuse and share classes, represents symbol/listing changes, mergers and delistings, refuses ambiguity/ineligibility/late evidence, and reports exhaustive integer coverage. The legacy name/ticker diagnostic's 768 deterministic interleavings remain a lower bound, not an allowlist; current-ticker joins are prohibited. | The committed production security-master registry is empty. No real source, rights/entitlement evidence, production vintage/correction builder, or accepted mapping exists; structural fixtures cannot self-promote. | ARV2-2 structural identity candidate implemented; production identity access refuses. |
| Sector/classification | Strict PIT classification evidence, freshness, content identity, and reauthentication boundaries exist. | The production classification source catalog is empty; no accepted PIT V2 taxonomy exists. | Consumer safety implemented; production classification access refuses. |
| Prices, outcomes, and costs | Strict terminal-event and transaction-cost contracts enforce decimal arithmetic, one net security change, explicit ADV, and source reauthentication. ARV2-2 now derives a revalidatable, fail-closed inventory of in-range merger/delisting terminal-return requirements and never silently omits an unavailable terminal name. No event has been joined to a later price or return; Databento remains unmeasured. | Production split/dividend, cost/ADV, and terminal-return catalogs are empty; owner-frozen outcome inputs and authorized permanent-look infrastructure do not exist. | Outcome prerequisites implemented structurally; no outcome I/O and zero looks. |
| ETF holdings/topology | PIT holdings, declared-versus-summed weight reconciliation, stale/incomplete refusal, fixed lag, 99% coverage, eligibility, and stock-score lineage primitives exist. | No authenticated production holdings or stock-score artifact exists, so no production reverse index, ETF score, or peer topology exists. | Consumer safety implemented; production topology remains zero-access. |
| Cross-section and portfolio | Deterministic rank/hysteresis/tie/eviction/cap/overlap/cash allocator primitives and verified policy bindings exist. | No reviewed simultaneous rank/volatility derivation or authenticated rank/classification/cost source exists. The public boundary therefore refuses every nonempty portfolio and can return only the safe empty/all-cash result. | Dormant safety algorithm implemented; no research portfolio or QC result. |
| Preregistration and outcome gate | A strict draft-spec loader, semantic validator, reviewed-source checks, immutable lineage bindings, one-use period rules, and fail-closed outcome permit boundary exist. | Required owner decisions remain open; the independently reviewed exact-spec registry is empty; no independent review anchor or external cross-machine append-only permanent-look authority exists. | Validation/gating primitives implemented; every outcome authorization refuses. |
| Architecture and legacy quarantine | The V2 package is registered as a research entry point, guarded against reverse imports from legacy ACER, and keeps the legacy outcome runners non-new/non-V2 with no network fallback. The authority-lock inventory now covers the PIT master loader. | ARV2-3 must preserve the transitive no-outcome/no-QC import closure and all empty production authorities. | ARV2-2 accepted after review and counter-review correction. |

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
`owner_decisions_frozen_pending_external_bindings_and_review`, not
outcome-executable. Owner direction on 2026-08-28 adopted the recommended
risk-balanced choices for all eight formerly open cells. The exact candidate
is content-addressed as
`arv2-round0-candidate-8d13a0a4577df322` / SHA-256
`8d13a0a4577df3223c96c4c11722457e059b4ade63f578ab860ce7364494e847`.
The loader now distinguishes a decided policy from evidence that does not yet
exist: corporate-action and security-master policies are frozen while their
source IDs and hashes remain explicitly null; the single permanent look ID is
frozen while its dataset and code identities remain explicitly null. Any
attempt to populate those fields in the unreviewed candidate refuses.

The candidate also freezes the requested history design: all eligible audited
history from 2013-01-02 through 2026-08-31, point-in-time ordinary/boom/stress
classification, and named COVID, 2022 rate-shock, and 2023-2026 AI-boom
diagnostics. Only the all-period walk-forward result may select the strategy;
regime and named-episode outputs are descriptive, non-rescuing diagnostics.
Earlier history can enter only after an independent source-coverage and
semantics review, so the unavailable 2008 example is not fabricated.

A future executable spec must still be committed and clean, match an entry in
the separate committed review registry, bind its exact independently reviewed
Git blob and review ancestry, and pass semantic validation of every mandatory
cell. Outcome authorization must then reauthenticate that source and obtain an
atomic spend receipt from an independently pinned, cross-machine append-only
permanent-look authority before any outcome I/O. No local file or SQLite
database can grant or reset that authority. Both the reviewed-spec registry
and external spend-authority integration remain absent: the committed
authority artifact declares exact `zero_access`, every authorization attempt
refuses before the outcome loader can execute, and the legacy machine-local
ledger path has no authority. No credential, provider row, price, return, or
outcome was accessed; no look was consumed.

Source precedence is explicit: normative strategy design governs the intended
formula, while observed provider availability/history governs factual data
claims. Neither category is permitted to overwrite the other.

## 4. Exact next step

The next step is independent review of this ARV2-0 owner-decision candidate:

1. Codex validates, commits, records, and pushes the exact bounded ARV2-0
   candidate on `codex/strategy-analyst-revisions-v2`, without opening source
   or outcome authority;
2. Claude independently reviews that exact pushed snapshot commit by commit
   and pushes the complete disposition and any corrections to the same lane;
3. Codex counter-reviews every Claude commit before accepting ARV2-0 or
   combining that disposition with the next authorized bounded milestone; and
4. only after that review chain closes may a read-only, zero-outcome
   entitlement/source audit bind real evidence or ARV2-1 capture a governed raw
   analyst snapshot. ARV2-1 must not begin from this unreviewed candidate.

The reviewed spec anchor, audited corporate-action/security-master sources,
normalized dataset and code identities, vendor-to-QC processing rights, and
external append-only permanent-look authority remain required before any
production normalization, price/outcome join, real score, ETF construction,
nonempty portfolio, QC run, or QuantConnect launch. Until then the candidate
is unaccepted and every production research/outcome boundary remains
zero-access.

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
