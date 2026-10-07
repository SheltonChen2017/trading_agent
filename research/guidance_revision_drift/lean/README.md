# LEAN order-based synthetic source candidate

`main.py` contains an actual `QCAlgorithm`, `PythonData` reader and custom
`FillModel`: it issues native buy limit / asynchronous sell market orders,
handles submission/fill/cancellation callbacks, checks exact fill price,
quantity and cumulative-fee receipts, and reconciles final inventory and cash.
It does not call AddEquity, History, Download, providers or a brokerage. Its
only subscription and benchmark are the invented `SYN-GDR` custom security.

This is **source plus local contract-test coverage, not a verified LEAN/QC
execution**. AlgorithmImports, QuantConnect and the Python/.NET runtime were
not installed on this machine for author validation. The Python SDK shim in
tests exercises the real methods but cannot prove native overloads, binding
conversion, reader integration, event ordering or transaction scheduling.
In particular, native fill evaluation must occur after that minute's shadow
receipt becomes available and before the next frame. The bridge refuses a
shifted fill rather than silently changing its clock. An authorized actual
engine run must establish this behavior; it has not been established here.

## Explicit accounting envelope

The deterministic shadow engine owns signal selection, quantities, limits,
next-minute eligibility, partial-fill capacity, spread/slippage, commission
floors, dated settlement and spending reservations. The custom native fill
model emits those receipts once; `on_order_event` must acknowledge them before
advancing. The native fee model is zero because each receipt supplies its fee.

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
beside `main.py` by the authorized packaging process. No such sidecar is
silently created or uploaded by the current CLI. Initialization verifies every
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
