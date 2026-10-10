# LEAN order-based synthetic source candidate

`main.py` contains an actual `QCAlgorithm`, `PythonData` reader and custom
`FillModel`: it issues native buy limit / asynchronous sell market orders,
handles submission/fill/cancellation callbacks, checks exact fill price,
quantity and cumulative-fee receipts, and reconciles final inventory and cash.
It does not call AddEquity, History, Download, providers or a brokerage. Its
only subscription and benchmark are the invented `SYN-GDR` custom security.

The strict reader treats the sidecar as one multiday source: timestamps come
from its exact validated records, not the source-creation date passed by LEAN.
Duplicate JSON keys, floating/type aliases and unknown/altered frames refuse.
Submission and cancellation control events may use LEAN's zero-fee `QCC`
sentinel only when quantity, price and fee are all zero. Economic fills remain
USD-only. Requested `CancelPending` acknowledges intent without releasing
reservations; a subsequent ordered `Canceled` receipt performs the release.
Exact event-ID redeliveries are idempotent; conflicting or out-of-order events
and unsolicited transitions refuse.

Before each frame advances, the algorithm also compares native whole-share
inventory and cash with the fully acknowledged shadow state. Native cash must
equal shadow settled cash plus outstanding receivables because the native
model is immediate settlement. Cash reservations do not reduce this envelope.
Any discrepancy refuses before consuming a frame or trace record, even if it
would disappear by the final callback. Prior pending fill/cancel receipts must
be acknowledged first. No account observation is taken inside the receipt
callback, where native portfolio-update ordering remains unverified.

This is **source plus local contract-test coverage, not a verified LEAN/QC
execution**. AlgorithmImports, QuantConnect and the Python/.NET runtime were
not installed on this machine for author validation. The Python SDK shim in
tests exercises the real methods but cannot prove native overloads, binding
conversion, reader integration, event ordering or transaction scheduling.
In particular, native fill evaluation must occur after that minute's shadow
receipt becomes available and before the next frame. The bridge refuses a
shifted fill rather than silently changing its clock. An authorized actual
engine run must establish this behavior; it has not been established here.

Local tests model both pre- and post-OnData transaction scans and a complete
372-record, 93-session source enumeration, including partial fill and pending
cancellation. This checks the source protocol against public engine code, not
native scheduling, SDK overloads or cloud completion.

## Bounded callback evidence

`SyntheticOrderBridge.protocol_trace()` returns a detached, in-memory transcript
of accepted frames, native-ID bindings, fill issuance and normalized receipt
acknowledgments. Canonical records link their predecessor hashes to a genesis
binding the fixed sidecar and base/stress mode. Exact duplicate callbacks and
repeat fill-model scans create no new records. Failed calls do not append or
consume effects. Limits are 1,024 records and 4 KiB per record; exhaustion
refuses atomically rather than silently truncating evidence. `finish()` includes
the count, genesis and final hash. The explicit projection remains the trace
source. The native entrypoint now exports that actual projection using bounded
ordered log fragments and observed runtime/configuration/valuation evidence.
Failure diagnostics retain the accepted partial trace and re-raise; incomplete
runs cannot emit success. Passive reconstruction refuses missing, duplicate,
reordered or corrupted fragments before existing trace replay.

This is synthetic normalized protocol evidence, not raw broker receipts,
durable recovery, an external trust root or proof that a native engine ran.
Runtime/cloud flags remain false even when the local transcript reconciles.

The separate offline `completion_evidence` module now transports the entire
transcript as bounded canonical chunks and replays it against the fixed
bridge. A successful check requires all 372 per-frame account checkpoints,
the exact calendar and receipt/economic sequence, retained trace identity,
and (for a dossier) current source/project identities plus a complete passive
compile/run attempt chain. Supplied `Completed` status is not authenticated
engine evidence. Run-output bytes must also match the receipt hash and bind
the complete trace/chunk inventory. Locally generating that envelope is not
a native run; these checks never promote native/cloud or empirical flags.
The new `paired_bridge`/`callback_plan` prototypes are not substituted into
this native algorithm and do not expand the approved synthetic run.

## Explicit accounting envelope

The deterministic shadow engine owns signal selection, quantities, limits,
next-minute eligibility, partial-fill capacity, spread/slippage, commission
floors, dated settlement and spending reservations. The custom native fill
model emits those receipts once; `on_order_event` must acknowledge them before
advancing. The native fee model is zero because each receipt supplies its fee.

The native source must record one successful account checkpoint for every
frame (372 in the fixed fixture); its base transcript now has 752 records.
The offline bridge can still run without account observations for protocol
diagnostics (380 base records). Those diagnostics cannot satisfy the native
source's end-of-run checkpoint-count requirement. Observations record the
immediate envelope, settled cash and receivables, with settlement parity false.

Native settlement is explicitly immediate. It is a cash reconciliation
envelope, **not cash-account settlement parity**: only the shadow's dated
settlement permits another order. Matching ending cash does not validate
intermediate buying power or settlement. Neither native nor shadow cash is
connected to an account. Unsupported order amendments, native rejections,
missing acknowledgements or incomplete calendars fail visibly. The stream
contains the original 93 invented sessions and one source strategy; comparator
and corporate-action coverage is in the separate local ENG-15 composition,
not a claim of native comparator/corporate-action parity.

## Later, separately authorized evaluation

`launch-preflight` always exits 2 and cannot certify external human approval.
The lane record's section 19.6 retains the owner's conditional synthetic-only
QC upload/run approval; all empirical freeze/source/calendar/evidence gates
remain closed. Each producing source, including added cloud loaders, still
requires exact-source Claude review and Codex counter-review before upload.
No real market/reference/action data or empirical outcomes are authorized.

For a later explicitly authorized *synthetic engine integration* evaluation,
retain the repository package layout, neutral `data` helpers and candidate
file shown in the release manifest. The exact sidecar bytes come from
`lean_bridge.fixture_stream()` and must be placed as `gdr-synthetic.jsonl`
beside `main.py` by the authorized packaging process. The explicit local
`prepare-bundle` command creates a verified archive containing those sidecar
bytes and the inventoried source. It does not automatically extract or upload
anything. Initialization verifies every
byte; alternate data, symbols or dates cannot be selected with parameters.
The new `native_bundle`/`qc_project` candidate carries the exact native import
closure and unchanged sidecar through size-bounded literal Python payloads plus
root `main.py`, reserving capacity for the default notebook. The full review
bundle stays separate. Runtime-source and full-review identities are distinct.
At runtime its root loader checks every carrier, exact archive anchor/member
inventory and metadata before private temporary materialization. The loader
uses static imports and exposes one callback-inheriting algorithm subclass
with runtime bundle/candidate/fixture anchors; fixture economics are unchanged. No carrier code
is executed while parsing its literal payload. This is a proposed cloud
filesystem route, not demonstrated QC support: fresh source review and the
later native run must establish discovery, permissions and reader access.
Select `GuidanceRevisionDriftAlgorithm`, pin the LEAN version and record the
project source hash, compile/run IDs, callback trace and terminal diagnostics.
Test reader/frame alignment, fills, fees, final cash, and native settlement
limitations explicitly. A future empirical candidate needs a separately
reviewed rights-cleared data/order/settlement adapter, not a renamed fixture.

Use order-based evaluation. Each unsuccessful compile/runtime/terminal launch
counts toward the owner's maximum of **three attempts for that candidate**.
After the third, stop; use authenticated controllable QC Mia if available,
otherwise return to the owner. Retrieve any successful Mia source, compare it
to the exact local candidate, and port only verified lane-specific fixes.
`Completed` alone never accepts changed economics or grants trading authority.

API shapes were checked against official [custom-security documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/importing-data/streaming-data/custom-securities/key-concepts),
[fill-model documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts),
[OrderEvent source](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/OrderEvent.cs)
and [settlement models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/supported-models)
on 2026-10-07. Documentation alignment is not native runtime validation.

Protocol corrections were checked on 2026-10-07 against official LEAN source:
[zero-fee definition](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/Fees/OrderFee.cs),
[null currency](https://github.com/QuantConnect/Lean/blob/master/Common/Currencies.cs),
[cancellation request events](https://github.com/QuantConnect/Lean/blob/master/Engine/TransactionHandlers/BrokerageTransactionHandler.cs),
[single-source enumeration](https://github.com/QuantConnect/Lean/blob/master/Engine/DataFeeds/SubscriptionDataReader.cs),
[fixed reader date](https://github.com/QuantConnect/Lean/blob/master/Engine/DataFeeds/TextSubscriptionDataSourceReader.cs),
and [transaction scan ordering](https://github.com/QuantConnect/Lean/blob/master/Engine/AlgorithmManager.cs).
These references describe current public source, not a pinned runtime accepted
for this candidate. The three-attempt rule still applies to any later launch.

The NE-1..NE-10 candidate requires a new exact-source review. It adds bounded
immutable early-event snapshots, actual runtime/configuration readbacks and
per-frame invented price-50/whole-account NAV checks; native quantity/cash and
shadow economic rules are unchanged. Runtime labels missing from Python test
doubles stay missing/unverified, never replaced by expected SDK labels.

Complete native evidence uses distinct routine `log` fragments, not a burst of
rate-limited `debug` messages. Measured invented output exceeds the Free tier's
10KB per-backtest quota. Verify existing organization tier, remaining rolling
log quota and exact complete evidence budget before a launch; no tier upgrade,
purchase or alternative-storage authorization is granted here. Only invented
software-fixture/protocol observations are exported, never vendor/market
dataset values. Truncated output cannot pass reconstruction. Current official
[logging documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/logging)
and [resource quotas](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/resources)
were checked on 2026-10-09; documentation is not actual runtime evidence.

`native_completion_dossier` composes reconstructed retrieved fragments,
observations/valuation checks, exact current carrier and the full retained
owner-cycle ledger. Raw LF-delimited message bytes and their fragment inventory
have distinct anchors. Retrieval wrappers and all other job output must also
be retained by the authenticated operator, not silently dropped. Matching
invented/passive inputs still leave native/provenance/empirical flags false.
