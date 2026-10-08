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
the count, genesis and final hash. The full transcript is available only from
the explicit projection method; this package does not silently persist it.

This is synthetic normalized protocol evidence, not raw broker receipts,
durable recovery, an external trust root or proof that a native engine ran.
Runtime/cloud flags remain false even when the local transcript reconciles.

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

Do not upload or run this package under the current gates. `launch-preflight`
always exits 2. A future owner authorization must name the exact source hash,
data/processing rights, candidate and QC action. Independent Claude review and
the original freeze/source/calendar/evidence gates are still required.

For a later explicitly authorized *synthetic engine integration* evaluation,
retain the repository package layout, neutral `data` helpers and candidate
file shown in the release manifest. The exact sidecar bytes come from
`lean_bridge.fixture_stream()` and must be placed as `gdr-synthetic.jsonl`
beside `main.py` by the authorized packaging process. The explicit local
`prepare-bundle` command creates a verified archive containing those sidecar
bytes and the inventoried source. It does not automatically extract or upload
anything. Initialization verifies every
byte; alternate data, symbols or dates cannot be selected with parameters.
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
