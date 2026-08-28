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
