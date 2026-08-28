# Post-integration Full Project Review and remaining P2/P3 remediation

Status: **QUEUED — owner-directed record, 2026-08-28; not active and not
authorized for implementation before the activation gate below**

Source review:
`docs/Archive/Review/COUNTER_REVIEW_2026-08-27_ROOT_REMEDIATION.md`

Record baseline: `da7e0d8b63aeb48a19dca86f0811777c8c74078c`, the merge of
the corrected root-remediation counter-review into `main` through PR #319.

## 1. Owner direction and activation gate

The owner intends to initiate another Full Project Review after the three
strategy feature branches are complete and merged into `main`. That future
work must do both of the following:

1. review the exact integrated project and correct every newly confirmed
   finding within the then-authorized scope; and
2. revalidate and close every remaining P2/P3 item carried in this plan.

This record preserves that future scope. It does **not** start it. Work may
begin only after all three conditions are true:

1. `codex/strategy-analyst-revisions-v2`,
   `codex/strategy-insider-buying`, and
   `codex/strategy-short-interest` have each completed their lane-owned
   implementation/review/counter-review requirements;
2. the owner has merged all three completed feature branches into `main`; and
3. the owner explicitly starts the new Full Project Review and correction
   work from the exact integrated `main` commit.

Branch completion or merge alone is not authorization to start. Until the
third condition occurs, this plan remains queued under `docs/Plan/`.

At activation, “complete” must be evidenced—not inferred from a branch name:
each lane record must carry its terminal accepted, accepted-after-correction,
rejected or valid-null disposition; its final Codex/Claude review and Codex
counter-review chain must be complete and pushed; and the owner must have
merged those exact remote heads while recording merge order and conflict
resolution. Local `main` and `origin/main` must match and the worktree must be
clean before the integrated head is frozen.

This review/remediation occurs before any separately owner-scheduled combined
strategy evaluation, final-holdout use or autopilot integration. It reviews
merged software and evidence claims; it does not consume an outcome look.

## 2. Product boundary and scope ownership

The repository currently hosts two logically separated products plus a
temporary shared kernel. The physical SEP-3 extraction is frozen and
unauthorized, so the future review must preserve ownership without pretending
that the repositories have already been split.

| Surface | Responsibility | Carried findings |
|---|---|---|
| Trading assistant / paper-live operations | Portfolio capture, proposals, approval, Alpaca paper execution, reconciliation, operator storage and incident handling | `RCR-014` through `RCR-018`, plus the assistant-reporting part of `RCR-019` and the runtime part of `RCR-020` |
| Strategy research / QuantConnect | Hypotheses, point-in-time data, signal construction, backtests, statistical validation and QC parity | None of the seven carried root findings; this product must nevertheless receive a complete new review after the feature merges |
| Temporary shared kernel | Provider-neutral financial primitives and contracts, currently under `data/` and other classified neutral surfaces | The `decimal_text` and shared-arithmetic part of `RCR-019` |
| Architecture/security boundary | Product ownership, composition, process trust and future physical extraction | `RCR-020`, and the SEP ownership impact of any change to shared files |

These paper/live findings do not invalidate research evidence by themselves.
Conversely, a successful research/QC review cannot close paper/live execution
or recovery findings. The future report must assess the two products and their
integration seam separately before giving a whole-project verdict.

This plan does not unfreeze SEP-3. If remediation changes a contested SEP-3
file, composition root, dependency, test placement or runtime topology, the
change must be recorded as new input to a later owner-authorized separation
dry run. It must not silently revise the frozen eighth-dry-run manifest.

## 3. Carried issue ledger

All seven findings are open on the record baseline. Their original evidence
and correction rationale remain in the source counter-review. Integration may
change their implementation locations or may independently fix one, but it
does not erase an ID: the future review must revalidate each item and record
how it closed.

The archived source report remains unchanged as the exact historical review
record. This queued plan adds future implementation detail and sharper
acceptance language; it does not retroactively rewrite the original evidence,
priority or disposition.

| ID | Priority | Status | Original label | Product owner | Required closure |
|---|---|---|---|---|---|
| `RCR-014` | P2 | Open — queued | `BRK-001` | Trading assistant | Permit only evidence-complete risk-reducing sells when position identities/quantities and the full order book are authoritative but unrelated valuation evidence is unusable, without authorizing exposure increase or overselling. |
| `RCR-015` | P2 | Open — queued | Root follow-up to `STO-001` | Trading assistant operations/storage | Provide an integrity-preserving offline quarantine/restore/recovery workflow; never repair the source in place or silently bless corrupt history. |
| `RCR-016` | P3 | Open — queued | `BRK-008` | Trading assistant broker contract | Distinguish provider-observed order account identity from session-bound account context and migrate durable wording/schema truthfully. |
| `RCR-017` | P3 | Open — queued | `BRK-009` | Trading assistant broker/proposal boundary | Preserve exact limit-price evidence from intent and authorization through the final request representation. |
| `RCR-018` | P3 | Open — queued | `STO-009` | Trading assistant storage | Bound normal store-open cost without weakening the declared broker-event integrity model or eliminating a complete audit. |
| `RCR-019` | P3 | Open — queued | Root follow-up | Shared kernel and assistant reporting | Bound non-exponent Decimal serialization and remove remaining ambient-context/display arithmetic from named reporting surfaces. |
| `RCR-020` | P3 | Open — queued | Root follow-up | Architecture/security | State and enforce the same-process trust boundary; use process isolation only if untrusted code enters scope. |

Definition of “close” in this plan is strict. On the final integrated tree,
each ID must be one of:

- **Closed by correction**, with a red-before/green-after regression and
  cumulative validation;
- **Closed as already corrected by an integrated feature change**, with the
  exact commit and a regression that proves the current behavior; or
- **Closed as a verified false alarm**, with concrete counter-evidence.

`Deferred`, `accepted risk`, `not currently reachable`, and `provider may not
support it` do not satisfy this plan's definition of done. When a provider
does not expose evidence, the safe correction is truthful unavailability or
session-bound provenance—not a fabricated observation.

## 4. P2-1 — incomplete position book and legitimate risk reduction

### 4.1 Current behavior and impact

`assistant/portfolio_snapshot.py` requires a coherent complete account book
for the normal execution snapshot. One malformed or unavailable position
valuation—or unusable cash evidence—therefore prevents every order, including
a sell of an unrelated, correctly identified long position. Dropping a row
whose identity or quantity is unknown would be unsafe because it could hide
the target holding, understate exposure or invalidate held-share authority.

The current refusal is conservative for buys but can obstruct legitimate risk
reduction. Reachability of the originally reproduced malformed Alpaca fields
has not been demonstrated against a real paper account; that uncertainty is
why the item remains P2 rather than P1. Provider access was not authorized by
the source review and is not authorized by this plan.

### 4.2 Required design

Implement a separate immutable, target-specific risk-reduction evidence
contract rather than weakening `PortfolioSnapshot`. Its exact name may change,
but it must bind at least:

- broker session identity, account ID/mode, capture timestamp and freshness;
- canonical identity and exact held quantity for every position row, with no
  duplicate, unknown or noncanonical identity; valuation evidence may be
  explicitly incomplete because it is not used to prove sellable shares;
- canonical target security identity, long-only asset eligibility and exact
  held target quantity with its evidence source;
- the complete account-wide active/unresolved order book, preserving the
  existing deliberate all-or-nothing order-evidence rule, including every
  target sell, partial fill, ambiguous dispatch and durable share reservation
  so remaining sellable shares cannot be overstated;
- explicit `position_valuation_complete=False` state and the identities/reasons
  for unusable valuation fields; and
- a fresh execution-capture fingerprint bound into revalidation,
  authorization and durable pre-contact context. It must not be retrofitted
  into the already-approved proposal ID in a way that invalidates every fresh
  pre-submit capture.

If the provider SDK constructs a full position model before the strict row
validator can isolate a valuation defect, add a narrow public/raw enumeration
adapter with explicit row-by-row normalization. Do not assume the current SDK
can return usable siblings after one row fails construction.

The exceptional path may authorize only a sell that cannot open or enlarge a
short position. Exact requested quantity plus every active or unresolved
target sell and reserved target quantity in the complete order book must not
exceed exact verified held shares. It must never
authorize a buy, a new position, a basket allocation, an exposure override, a
rebalance that contains a buy leg, or a policy claim requiring the unknown
sibling exposure.

All still-meaningful safety checks remain in force: canonical identity,
account/mode sealing, freshness, trading eligibility, duplicate/idempotency
fences, kill switch, approval binding, broker snapshot mutation detection and
reconciliation. Every portfolio-wide check that cannot be computed must be
recorded as unavailable; it must not render as zero or silently pass.

### 4.3 Required verification

Provider-independent tests must cover, at minimum:

- malformed unrelated valuation with a valid target sell;
- provider model-construction failure with public/raw row isolation that
  preserves every usable sibling and refuses any unprovable identity/quantity;
- malformed/unknown sibling identity or quantity, malformed target identity or
  quantity, missing target, duplicate target and non-long target;
- exact boundary sell, oversell, active sell, partial fill and concurrent
  target-order mutation;
- incomplete or malformed account-wide order evidence;
- stale capture, session rotation, account/mode mismatch and ticker alias;
- ambiguous prior dispatch and idempotent retry;
- kill-switch, approval and broker-mutation refusal before submission;
- proof that every buy/increase path remains refused; and
- proof that provider-independent refusal tests make no network contact.

The future owner may separately authorize a read-only paper-provider
characterization after the offline design is independently reviewed. Such a
probe is validation evidence, not permission to weaken the contract.

### 4.4 Closure gate

`RCR-014` closes only when an unrelated valuation defect no longer blocks a
target-specific risk-reducing sell through the real execution service in
fixtures, every identity/quantity/order ambiguity and dangerous counterexample
refuses before broker submission, and Claude has
independently reviewed the exact pushed correction followed by Codex
counter-review.

## 5. P2-2 — integrity-preserving broker-event-ledger recovery

### 5.1 Current behavior and impact

Strict writable `AssistantStore` construction correctly refuses after a
broker-event integrity violation. Capability-limited emergency cancel-all
remains available, but normal operation has no supported quarantine, restore
or recovery workflow. Permanent refusal is safer than silently trusting
corrupt history, yet the missing recovery procedure is a material operational
gap.

The current broker-event metadata uses canonical content plus unkeyed SHA-256
and SQLite append-only triggers. That detects inconsistency under the trusted
writer/process model; it does not prove hostile-tamper resistance when an
actor can rewrite both content and hash. Future documentation and code must
not call this cryptographically authenticated evidence unless a key or anchor
outside the mutable database actually supplies that authority.

This recovery work and the ordered-integrity/checkpoint design in section 8
must share one frozen threat model. Today's row-local hashes do not detect a
self-consistent deletion, insertion, reorder or content-plus-hash rewrite, so
the recovery tool must not promise those guarantees before an ordered prefix
and appropriate trust anchor exist. Under the current model it may make only
the narrower consistency claims the source actually supports.

### 5.2 Required workflow

Add a broker-disconnected offline recovery command or tool with these phases:

1. enter an external recovery stop, quiesce every assistant writer/process/task
   and refuse any broker client construction; do not write a database-resident
   kill switch into the source being preserved;
2. inventory the complete SQLite file set (main database plus any WAL, SHM or
   rollback-journal files), record path/size/hash metadata, and acquire the
   required external lock or verified quiescent state;
3. copy that whole file set to a new immutable forensic bundle using atomic
   file handling, verify pre/post hashes, then create a separate consistent
   logical working snapshot from the copy; never checkpoint, migrate or
   “repair” the source bundle in place;
4. verify schema and broker-event integrity in deterministic row order,
   recording the first failure and all independently observable later
   failures without projecting corrupt rows into operational state;
5. export a canonical recovery dossier containing failure location, row
   identity, available ordering/context evidence, tool/code version and every
   operator decision—without credentials or private account identifiers;
6. permit restoration only from a separately verified backup into a new,
   non-existing destination with a new database identity and permanent link to
   the forensic bundle; if no verified backup exists, remain durably blocked;
   any lossy prefix salvage/truncation requires a separate owner decision and
   can never be described as complete authenticated history; and
7. require a second independent full verification of the new database before
   writable construction can resume.

A separately authorized lossy quarantine would start a visibly new ledger
epoch/genesis with permanent linkage to the forensic bundle; it cannot pose as
a repaired continuation. Later operational reactivation also requires a
separate authorized broker reconciliation. Neither action is part of offline
implementation tests or granted by this queued plan.

If a stronger hostile-tamper threat model is selected, use a keyed MAC,
signature or immutable external anchor whose key/authority is not stored in
the same writable database. A newly calculated plain digest is not sufficient.

### 5.3 Required verification

Test fresh and migrated schemas; rollback-journal and WAL-mode databases;
content tamper; recomputed unkeyed hash;
deleted, inserted, duplicated and reordered rows; truncated database; wrong
backup; wrong database identity; schema drift; failed/partial copy; disk-full
and interrupted recovery; source mutation during capture; repeated recovery;
destination collision; bad typed confirmation; broker factory tripwires; and
byte preservation of the complete original SQLite file set.

Run an offline recovery drill from a corrupted fixture through verified new
database construction. The drill must prove that emergency containment
remains active until an explicit, audited re-arm after independent review.

### 5.4 Closure gate

`RCR-015` closes only when the original SQLite file set remains byte-identical,
the recovered artifact has a complete durable dossier, no broker contact is
possible, and
both success and interruption paths are independently reviewed. This work
should reconcile with, but does not automatically activate, GR-6 in
`docs/Plan/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`.

## 6. P3-1 — truthful per-order account provenance

### 6.1 Current behavior and impact

`ValidatedBrokerOrder.account` is populated from the verified broker session
at paths where the order row does not necessarily contain independently
observed account evidence. Session sealing is valuable and prevents a request
from drifting across the captured account, but durable records can overstate
that session-derived value as an order-row observation.

### 6.2 Required design and verification

Separate at least these concepts in the broker contract and durable event
projection:

- `session_account_id`: account/mode proven for the captured broker session;
- `order_account_id_observed`: independently present in the raw order payload,
  otherwise absent; and
- provenance such as `provider_observed`, `session_bound`, or `unavailable`.

Never duplicate `session_account_id` into the observed field. Preserve the raw
field through normalization when the pinned provider exposes it; reject a
conflict. Preserve append-only event content: use additive schema/read-time
compatibility for legacy rows, labeling them `legacy_unknown` unless existing
immutable evidence proves a session binding; never upgrade them to
provider-observed. New provenance belongs in a new event fingerprint/schema
version. Update UI, telemetry, reports and incident wording so they never say
“observed on order” for session-derived evidence.

Tests must cover field-present match/mismatch, field absence, partial SDK
models, raw REST payloads, legacy migration, session rotation, cross-account
collision, replacement chains, streams, reconciliation, serialization and
journal replay. A provider that lacks the field does not block closure:
truthful `session_bound` provenance is the correction for new session-bound
rows, while unprovable history remains `legacy_unknown`.

## 7. P3-2 — exact limit-price evidence through submission

### 7.1 Current behavior and impact

`TradeIntent.limit_price` and Alpaca submission APIs still use binary `float`
at the final boundary even though broker normalization and policy checks can
carry `Decimal`. The execution gate mitigates policy bypass, but the value
bound into proposal identity and the value serialized toward the broker can
drift or lose sub-cent digits. Numerically equivalent trailing-zero forms must
canonicalize to the same identity rather than being treated as different
prices.

### 7.2 Required design and verification

Introduce canonical exact limit-price evidence across the complete path:

- exact intent field and legacy display compatibility validation;
- proposal JSON, fingerprint and approval/authorization payload;
- policy tick/scale validation and stored order expectation;
- SDK or REST request construction; and
- normalized broker response and duplicate/reconciliation comparison.

The authoritative value must be a finite positive `Decimal` or canonical
decimal string. A float may remain only as an explicitly derived display/
compatibility field that cannot authorize or fingerprint an order. On the
record baseline the pinned alpaca-py `LimitOrderRequest.limit_price` surface is
typed as float; re-check the installed version at implementation time and
capture the actual outgoing SDK/HTTP bytes, not only the request object's
Python attribute. If exact serialization cannot be proved, use a verified
canonical REST adapter, deliberately upgrade the pinned SDK under dependency
review, or fail closed by refusing limit orders. Do not silently round and call
it exact.

Legacy pending/executable limit proposals that lack exact source text cannot
be upgraded from their float; keep them readable as history but
non-executable and require regeneration. Migration must refuse incompatible
exact/legacy twins. Tests must cover sub-cent values, allowed tick sizes,
trailing-zero equivalence, float disagreement, proposal replay, HMAC binding,
REST and SDK capture, rejection before network contact and exact broker-response
comparison. The future review must also search price-bearing stop/stop-limit
paths for the same generalized defect without expanding order authority.

## 8. P3-3 — bounded broker-event integrity verification

### 8.1 Current behavior and impact

Every ordinary writable `AssistantStore` construction scans and recomputes
integrity metadata for the complete `broker_order_events` table. This is
correct under the current declared model but O(n) in lifetime event count and
therefore makes writable startup progressively slower. Read-only construction
skips initialization, and Streamlit caches its store resource; the finding
must not overstate those unaffected paths.

### 8.2 Required design and verification

First write the exact integrity threat model. Under the current trusted-process
model, unkeyed hashes are consistency checks, not hostile-tamper authentication.
If stronger protection is required, establish the keyed/external authority
before using the word “authenticated.” A checkpoint cannot be stronger than
the event evidence it summarizes.

Define a canonical monotonic event sequence or equivalent unambiguous ordered
prefix; current row-local hashes alone do not prove deletion or reordering.
Use a versioned append-only checkpoint that binds database identity, schema
version, verified ordered prefix/count, terminal event identity/prefix digest,
predecessor checkpoint and integrity-mode version. Normal startup may verify the latest
trusted checkpoint plus the tail. A separate operator full-audit command must
still verify every row and all checkpoint ancestry. Never trust only a mutable
row offset, timestamp, cached digest or `MAX(rowid)`. A checkpoint stored only
inside the same database cannot prove whole-database rollback; hostile rollback
resistance requires an owner-authorized keyed monotonic anchor outside it.

Test row deletion/insertion/reordering, same-count replacement, checkpoint
rollback, wrong database, copied checkpoint, schema/key/version rotation,
tail corruption, partial checkpoint write, missing checkpoint, legacy
database and full-audit disagreement. Measure startup and full-audit scaling
on declared fixture sizes; choose a performance acceptance bound from measured
operational needs rather than inventing an arbitrary number in advance.

## 9. P3-4 — bounded Decimal serialization and honest reporting arithmetic

### 9.1 Current behavior and impact

`data/financial_primitives.py::decimal_text` constructs non-exponent text from
the immutable Decimal tuple, correctly avoiding ambient-context rounding. It
does not preflight output length. A direct finite Decimal with an extreme
exponent can therefore allocate a very large string. Reporting-only arithmetic
also remains in `assistant/attribution.py`, `assistant/cash_reporting.py`,
`assistant/portfolio_history.py`, `assistant/sleeve_report.py` and
`assistant/execution_telemetry.py` that has not received the same complete
exact/context-independent audit as authorization paths.

Treat this one finding as two explicit closure tranches: `RCR-019A` is the
provider-neutral shared primitive and requires consumer tests in both
products; `RCR-019B` is assistant-owned reporting. The durable ledger ID
remains `RCR-019` and closes only when both tranches close.

### 9.2 Required design and verification

Derive a maximum canonical-output contract from legitimate persisted schemas,
provider limits and display requirements. Before joining a large coefficient
or allocating zero padding, calculate coefficient and projected output lengths
from `Decimal.as_tuple()` and raise a narrow provider-neutral representation
error when a limit is exceeded. Each product maps that error to its own typed
refusal or unavailability result. Preserve canonical zero, sign and
trailing-zero equivalence for accepted values.

Inventory every remaining addition, subtraction, multiplication, division,
quantization and formatting expression in the named reporting modules and
classify it as authoritative, durable, comparison, derived report or
display-only. Include `assistant.execution_telemetry._number_text`, whose
non-exponent formatting has the same output-allocation concern. Migrate
authoritative/durable operations to exact helpers; use explicit deterministic
division/quantization for derived reports; and represent unavailable
calculations truthfully. Explicitly labeled statistical/NumPy float output may
remain when it is non-authoritative. A reporting failure must not silently
become zero, but it also must not obstruct an independently valid risk-reducing
sell unless that report is genuinely required by the action.

Tests must set hostile low/high Decimal contexts and cover huge positive and
negative exponents (including extreme-exponent zero), long coefficients,
signed zero, underflow-shaped inputs, nonterminating ratios, rounding
boundaries, JSON/storage rendering and resource-bounded refusal. Exact output
limits need below-boundary, at-boundary and one-unit-over-boundary cases so the
guard neither allocates first nor rejects the largest permitted value.
Boundary tests must prove that changing shared `data` code creates no new
research-to-execution authority and must record the change for future SEP-3
reclassification.

## 10. P3-5 — same-process containment trust boundary

### 10.1 Current behavior and impact

Capability-limited private Python objects reduce accidental misuse, but code
running in the same interpreter can import, construct or monkeypatch private
internals. The current product is a single-owner local application and does
not claim to execute hostile plugins, so this is a P3 threat-model/documentation
gap rather than a demonstrated live-authority escape.

### 10.2 Required resolution

The future review must choose and enforce one truthful state:

1. **Trusted-process model:** document that all imported Python code is trusted,
   forbid unreviewed plugin/arbitrary-code loading in execution-capable
   processes, keep private capability surfaces narrow, and remove any claim
   that module privacy is a security sandbox; or
2. **Untrusted-extension model:** isolate storage mutation, broker submission
   and emergency containment behind a separate least-privilege process/OS
   identity with authenticated IPC, explicit request schemas, replay defense,
   rate limits, kill-switch ownership and failure drills.

Under the second model, isolating storage/cancel-all alone is insufficient.
The privileged boundary must also own broker credentials, proposal/approval
verification, the risk-gate signing authority, dispatch permits,
reconciliation and kill-switch authority; otherwise hostile same-process code
could bypass the intended boundary before IPC.

The first resolution is sufficient for the current declared product if it is
made explicit and mechanically guarded. The second is mandatory if untrusted
plugins or arbitrary imported code become a requirement. It is not authorized
by this queued plan and would require an owner decision because
`GENERAL_READINESS_IMPLEMENTATION_PLAN.md` currently defers microservice
decomposition.

Physical SEP-3 extraction could reduce research/runtime co-residency, but it is
neither required for the current trusted-process resolution nor authorized by
this plan.

Tests for the trusted-process resolution must at least guard execution roots
against dynamic plugin loading and prove the emergency wrapper exposes no
general mutable store. Tests for an isolated process, if authorized, must cover
authentication failure, replay, malformed messages, process death, timeout,
privilege/file-access boundaries and safe risk reduction during failure.

## 11. Future Full Project Review and correction sequence

The future work is one owner-directed program but must retain bounded,
reviewable checkpoints. The generic workflow applies; the temporary same-lane
exception for the three feature branches does not automatically extend to
this integrated review.

### FPR-0 — establish and review the integrated snapshot

1. Fetch the exact pushed `main` after all three owner merges.
2. Record its full hash, merge parents, tree and the complete ordered range
   from `da7e0d8` to the integrated head.
3. Verify every lane's final record, reviewed head, look accounting, data
   authority and merge-tree result; do not infer acceptance from merge alone.
4. Review every commit/merge disposition and also scan the cumulative whole
   tree, including research/QC, shared contracts, assistant/execution,
   operations, documentation, dependencies and product boundaries.
5. Create a new P0–P3 ledger. Retain resolved findings and map generalized
   instances instead of patching only the first example.
6. Reproduce material findings before correction when practical.
7. Freeze the activation-time decisions in section 12, especially the
   trusted-versus-hostile process and database integrity threat models.

### FPR-1 — correct catastrophic/critical and integration findings

Any new P0 stops all other work and is handled under the governing safety
process. New P1 findings precede P2/P3 work. Merge conflicts, lost safety
fixes, research-authority crossings and changed shared contracts are reviewed
before treating the integrated tree as a valid remediation base.

### FPR-2 — close the independent risk-reduction P2

Implement `RCR-014` with focused red/green tests and its own independent review
checkpoint. It is independent of the broker-event recovery/schema tranche and
must not weaken the complete account-wide order-book invariant.

### FPR-3 — freeze shared/broker schema prerequisites

Bound the provider-neutral `RCR-019A` primitive first if later durable schemas
will rely on its canonical text. Then implement `RCR-016` and `RCR-017`
together only if the integrated design proves their broker schema/proposal
migration is one coherent contract. Otherwise keep separate commits/checkpoints.
This dependency ordering does not lower the priority of the recovery P2; it
prevents that recovery/checkpoint format from being obsolete on arrival.
Neither change may broaden live authority.

### FPR-4 — co-design ordered integrity and close recovery

Design `RCR-018`'s event sequence/prefix/integrity authority together with
`RCR-015`'s recovery proof. Close the P2 recovery workflow first once its
claims are supportable, then complete the bounded-startup checkpoint. Do not
introduce a checkpoint whose security claim exceeds its actual threat model.

### FPR-5 — finish reporting and the process trust boundary

Close `RCR-019B`, then close `RCR-020` under the threat model selected at
FPR-0. Record every SEP ownership effect without editing the frozen manifest.

### FPR-6 — cumulative validation and independent acceptance

Run affected tests first, then the complete repository suite and required
compile/diff/secret checks on the exact final tree. Exercise dangerous
mutations for risk reduction, corrupt recovery, provenance, exact transport,
checkpoint rollback, Decimal resource bounds and the selected process trust
model. Validate research/QC and paper/live products separately, then their
approved integration seams.

Codex must commit a stable implementation snapshot. Claude independently
reviews every exact pushed commit under the generic workflow, commits any
authorized corrections on a separate review branch, and updates the review
record. Codex counter-reviews every Claude commit before acceptance. The owner
retains merge authority.

The standing default remains one bounded milestone/branch followed by
independent review. If the owner later wants one umbrella correction branch and
one review only at its end, that future instruction must say so explicitly;
calling the work “large” does not silently waive the review checkpoints.

## 12. Activation-time decisions and safe defaults

The future review must record the owner's choices before dependent
implementation. These recommendations prevent an unanswered question from
turning into an unsafe convenience or indefinite deferral:

1. **Partial-position sell policy.** Recommended default: never bypass the kill
   switch; require canonical identity/exact quantity for every position and a
   complete account-wide active/unresolved order book; tolerate only valuation
   evidence that is explicitly unnecessary to the target sell.
2. **Recovery policy.** Recommended default: forensic diagnosis plus restore
   from a verified backup to a new database only. No automatic truncation,
   re-blessing or lossy salvage.
3. **Process threat model.** Recommended default: only repository-reviewed
   trusted code runs in execution-capable processes; untrusted plugins and
   arbitrary code are forbidden there.
4. **Database/checkpoint threat model.** Recommended default: describe current
   guarantees as trusted-writer integrity checks. Use “authenticated” or claim
   rollback resistance only after an owner-authorized keyed/monotonic anchor
   outside the mutable database exists.
5. **Exact limit-price fallback.** Recommended default: if canonical wire bytes
   cannot be proved, refuse limit-order execution rather than transmit float.
6. **Branch/review topology.** Recommended default: bounded generic-workflow
   milestones with independent review between them.
7. **Provider/account characterization.** Recommended default: none. Use
   fixtures, installed SDK inspection and official contracts; request separate
   authority only if a real provider observation becomes indispensable.

These choices refine implementation and evidence requirements. They do not
authorize provider, operator-database, order or deployment activity.

## 13. Definition of done

This future program is not complete until all of the following are true:

- all three feature branches were merged and their exact merge results were
  included in the review;
- every reviewed commit and merge has an explicit disposition;
- every new confirmed finding has a P0–P3 ledger entry, correction and
  verification within authorized scope;
- `RCR-014` through `RCR-020` are individually revalidated and closed under
  section 3's closure rules—none remains deferred or merely accepted;
- research/QC, paper/live and shared/integration conclusions are stated
  separately;
- exact schema, migration, compatibility, data-authority and SEP ownership
  effects are recorded;
- focused, complete-suite, compile, diff, credential-shape and required
  mutation checks pass on the final tree;
- Claude's independent review and Codex's counter-review are complete;
- the accepted correction tree is owner-merged and post-merge validation proves
  the exact final `main` tree, not only a pre-merge topic branch;
- the authoritative review/remediation record and Session Handoff name every
  final commit and remaining external/owner gate; and
- no claim of alpha, QC readiness, paper sufficiency, live readiness or
  autonomous authority exceeds the evidence actually produced.

## 14. Explicit exclusions and retained authority boundaries

Nothing in this queued plan authorizes implementation now, provider or
credential access, licensed-row retrieval, a research/outcome look,
QuantConnect execution, broker contact, operator-database mutation, task or
scheduler changes, deployment, evidence-epoch changes, paper orders, live
orders, funded-account access, SEP-3 work or physical repository extraction.

Completing software corrections later will not prove predictive alpha, satisfy
a research gate, complete a paper-evidence epoch or authorize live trading.
Those remain separate evidence and owner decisions.

## 15. Copyable activation prompt

```text
The three strategy feature branches are complete and have now been merged into
main. Start the owner-authorized post-integration Full Project Review from the
exact fetched main head. Read CLAUDE.md, AGENTS.md,
ACTION_PLAN_2026-08-20.md,
POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md, all three final
lane records, the project-separation freeze, and the review/handoff process.
Review every commit and merge since da7e0d8 and perform a whole-tree audit.
Apply authorized corrections for every newly confirmed finding and close all
seven carried findings RCR-014 through RCR-020 under the plan's acceptance
criteria. Keep research/QC, paper/live and shared-boundary conclusions
separate. Do not infer provider, outcome, QC, broker, operator-database,
deployment, evidence-epoch, paper-order, live-order or SEP-3 authority. Produce
an exact P0-P3 ledger, full validation, independent Claude review, Codex
counter-review, authoritative documentation and a final merge-ready handoff.
```
