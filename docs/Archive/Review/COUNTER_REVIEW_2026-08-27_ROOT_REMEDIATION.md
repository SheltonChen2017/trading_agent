# Codex counter-review — root remediation independent review

Counter-review completed: 2026-08-28
Implementer/counter-reviewer: Codex
Independent reviewer being counter-reviewed: Claude
Workflow: generic separate-review-branch workflow
Counter-review branch: `codex/counterreview-root-remediation-20260827`

## 1. Outcome

**Disposition: accepted after correction.** No P0 remains. The six Claude
commits named below were reviewed individually. Their merge mechanics are
sound, and their useful corrections are retained, but their content and
records are accepted only after the counter-review correction commit:

`242f8eb7ef5022ed17e86502896ae19e7621e55c`

The corrected implementation passed the complete repository suite:

**5,720 passed, 2 skipped, 0 failed, 25 warnings** on Python 3.13.14 / pytest
9.1.1 in 1,843.55 seconds.

This is a main-line counter-review only. Per owner direction, no strategy-lane
branch, strategy worktree, lane implementation record, research code, provider,
outcome source, broker account, operator database, deployment, scheduled task,
QuantConnect resource, or evidence epoch was accessed or changed. No push was
performed.

The remaining open items are explicit design or scalability work, not hidden
acceptance conditions: incomplete-position-book risk reduction (`BRK-001`),
authenticated corrupt-journal recovery, per-order account provenance, exact
limit-price transport, authenticated event-ledger checkpoints, and bounded
reporting/serialization hardening. They do not authorize implementation by
inference; section 10 gives the required design and verification work.

## 2. Governing sources and scope

This counter-review follows, in order:

1. `CLAUDE.md`;
2. `AGENTS.md`;
3. `docs/ACTION_PLAN_2026-08-20.md`;
4. `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`;
5. `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`;
6. Claude's historical review and the exact six-commit correction range.

The owner separately assigned Analyst Revisions V2, Insider Buying, and Short
Interest to parallel strategy worktrees. Therefore `ARV-001` through
`ARV-014` are **delegated/excluded**, not accepted, closed, or silently
dropped here. This counter-review neither inspected nor modified those lane
worktrees.

## 3. Exact snapshot and commit graph

| Item | Exact value |
|---|---|
| Published base at counter-review start | `6a507341896850076c13050da080f888d6eb31aa` (`origin/main` and local `main`) |
| Counter-review branch | `codex/counterreview-root-remediation-20260827` |
| Code correction commit | `242f8eb7ef5022ed17e86502896ae19e7621e55c` |
| Code correction parent | `6a507341896850076c13050da080f888d6eb31aa` |
| Code correction tree | `b97cccb5be0a2f19fe96ffc5a194bdfa411a83f3` |
| Remote state | Local only; not pushed by this counter-review |

The Claude range is non-linear:

```text
e6a654d ── 4fc2c60 ── 0eaf420 ── eeeab13 ── 76139b4
    \                     \                         \
     └──── ae55d86 ───────┴──────────────────────── 6a50734
```

More precisely:

- `4fc2c60` has parent `e6a654d`.
- `0eaf420` has parent `4fc2c60`.
- merge `ae55d86` has parents `e6a654d` and `0eaf420`; its tree is exactly
  the second parent's tree `635577ac035ec4870d500400a7ebf0e2f289ac0f`.
- `eeeab13` has parent `0eaf420`, not merge `ae55d86`.
- `76139b4` has parent `eeeab13`.
- merge `6a50734` has parents `ae55d86` and `76139b4`; its tree is exactly
  the second parent's tree `b6f8057e4166bc614330a2e4d8cc1d8057878bb7`.

Tree equality accepts merge mechanics only. It does not independently accept
the inherited report, handoff, code, tests, or claims.

## 4. Claude commit-by-commit dispositions

| Commit | Scope | Disposition | Counter-review reason |
|---|---|---|---|
| `4fc2c60e41c49056b4c3babf35af3acc56c6e6fe` | Independent review report | **Accepted after correction** | Useful findings were reproduced, but the report used an unauthorized P4 class, misstated the unique count as 46 instead of 45, claimed explicit dispositions for 27 earlier commits without providing them, omitted mandatory ledger fields, and reached a conditional verdict before its corrections were reviewed. |
| `0eaf420293733b7a31b4b62e07fe3eb0c2dfdad8` | Session handoff | **Accepted after correction** | The handoff accurately preserved some boundaries but repeated the false count, false per-commit-disposition claim, stale test state, and conditional acceptance as current truth. |
| `ae55d865f184d513448e571ebe3e1e8bd863aa34` | PR #317 merge | **Accepted after correction** | Merge topology and tree identity are accepted. Inherited report/handoff content is accepted only after the authoritative supersession in this counter-review. |
| `eeeab1370923ec0c2bf6f06c643f5d63ec6019c9` | Production corrections and tests | **Accepted after correction** | It closed several real issues, but the ambiguity guard trusted equality on an arbitrary object, and corrupt-journal containment exposed a full mutable `AssistantStore` through a caller opt-in. Subsequent adversarial review also found boundary, exact-arithmetic, read-only, fill-evidence, identity, and availability gaps. All are corrected in `242f8eb`. |
| `76139b4efb751de8f7fd863a7a5dfc6f2f92da9d` | Updated report and handoff | **Accepted after correction** | It recorded useful validation but declared the correction complete before Codex counter-review, retained inaccurate count/disposition claims, and did not identify the mutable containment escape. |
| `6a507341896850076c13050da080f888d6eb31aa` | PR #318 merge | **Accepted after correction** | Merge topology and tree identity are accepted. Inherited content is accepted only with `242f8eb` and this authoritative record. |

## 5. Review-record corrections

The historical Claude report remains unchanged except for a supersession
banner. These corrections govern current state:

1. The historical ledger has **45 unique IDs**, not 46: P1=2, P2=13,
   P3=20, P4=10 under its original classification. `BRK-003` has no row.
2. The governing process permits P0 through P3 only. Former P4 issues are
   either P3 or informational.
3. The report does not contain explicit dispositions for the 27 earlier
   implementation commits it says it dispositioned. This counter-review does
   not invent missing historical review evidence.
4. The six Claude commits above are the exact counter-reviewed range.
5. Merge-tree equality proves content transport, not content correctness.
6. The corrected implementation changed production behavior outside Claude's
   originally named files because adversarial reproduction found the same root
   causes at authorization, persistence, ledger, reporting, and UI consumers.
7. The historical report's section saying no production code changed
   conflicts with its own correction section; current state is the code commit
   above.
8. The historical validation of intermediate trees is preserved as history,
   but only the final 5,720-test run certifies the accepted code tree.
9. Analyst findings are delegated to their owner-scoped lane; they are not
   accepted or closed by a root-only review.
10. Current handoff truth is replaced separately after this report commit.

## 6. Counter-review P0–P3 ledger

Statuses mean: **Closed** = corrected and validated in `242f8eb`;
**Open** = reproduced/design-relevant work remains; **Delegated** = explicitly
outside this owner-scoped branch. No P0 is open or closed because none was
found.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `RCR-001` | P1 | Closed | `242f8eb` | `assistant/execution_service.py`; `tests/test_execution_characterization.py` | Claude's sell bypass accepted any object comparing equal to `"sell"`, allowing malformed side evidence to bypass the account ambiguity fence. | Hostile equality object reproduced the bypass. | An account-level dispatch fence must recognize only the canonical built-in sell side. | Require `type(side) is str and side == "sell"`; retain buy/unknown refusal. | Characterization regression plus changed-file and full suites. |
| `RCR-002` | P1 | Closed | `242f8eb` | `assistant/storage.py`; contained-integrity and schema tests | Claude's `permit_contained_integrity_failure` returned a full mutable store after journal authentication failure; read-only writer coverage also ignored helper-indirected mutations. | Direct mutation surface and AST counterexamples reproduced. | Corrupt-journal emergency access must expose only cancellation capabilities, and read-only state must refuse before DB/runtime contact. | Remove the opt-in; add a capability-limited cancel-all wrapper; make ordinary `_connect()` read-only; route every mutator through `_connect_writable()`/guarded primitives; pin the complete writer inventory. | 240 focused storage/broker, 286 fixture, 150 consumer, 1,681 changed-file, and full suites. |
| `RCR-003` | P2 | Closed | `242f8eb` | `data/financial_primitives.py`; risk, execution, allocation, proposal, sleeve, rebalance, ledger modules | Ambient Decimal precision could round caps, quantities, notionals, balances, basis, dividend pools, proposal identities, and displays; a daily cap bypass and a $1-unbalanced journal acceptance were reproduced. | Low-context probes changed authorization and durable values. | Python's ambient Decimal context is mutable process state and cannot be financial authority. | Add bounded exact add/subtract/multiply/sum, deterministic division/quantization, tuple-based decimal text/scale; migrate authorization and durable arithmetic; fail closed on unrepresentable values. | Financial primitive regressions; 309 strategy tests; 354 ledger/storage/risk tests; final full suite. |
| `RCR-004` | P2 | Closed | `242f8eb` | `data/security_identity.py`; `assistant/portfolio_snapshot.py`; `execution/alpaca_broker.py`; gate tests | `AAP L` passed the old uppercase/strip check, hiding an existing same-security position from an `AAPL` concentration decision. | Strict-capture and pure-gate reproduction approved a projected 44% position against a 5% cap. | Ticker identity must use one closed grammar across broker and portfolio boundaries. | Centralize `[A-Z][A-Z0-9.\-]{0,31}` identity; reject noncanonical snapshot rows; register the neutral module in product ownership. | Strict broker capture, dotted/hyphenated controls, gate regression, full suite. |
| `RCR-005` | P2 | Closed | `242f8eb` | `assistant/portfolio_ledger.py`; `assistant/storage.py`; broker-event tests | Exact fill companions were discarded for legacy floats during journal sync; nonterminating derived remainders claimed `provider_exact`. | Exact quantity/price lost digits and changed durable shares/cost basis. | Display floats cannot drive accounting when exact provider evidence exists. | Require exact companions for `provider_exact`, preserve exact metadata/duplicate identity, and label nonexact derived remainders `derived_rounded`. | End-to-end `list_fills → sync_app_fills`, duplicate-conflict, 99 ledger and 354 combined tests. |
| `RCR-006` | P2 | Closed | `242f8eb` | broker contract, reconciliation, operations/readiness, risk timestamp parsing | Year-boundary offsets could raise raw overflow; one malformed legacy row could abort emergency per-order cancellation. | Year 1 `+14:00` and year 9999 `-14:00` probes reproduced raw errors. | External timestamps are untrusted evidence; normalization must fail closed without disabling unrelated risk reduction. | Normalize ISO, offset, UTC, and OS errors to typed refusal/`None`; retain visible-order cancellation. | Broker/coherent snapshot tests and 31-test cancel-all file. |
| `RCR-007` | P2 | Closed | `242f8eb` | context builder, risk copilot, LLM/CLI/UI, allocation/proposal paths | Unavailable risk/order/analytics evidence rendered safe-looking zeros or still permitted buy proposal generation. | Corrupt/unavailable packet paths showed zero risk facts and actionable buy controls. | Unknown evidence is not zero and cannot authorize exposure increase. | Add explicit availability/reason fields; suppress derived portfolio claims; refuse buy/allocation/steering proposals; preserve independently validated sell controls and order-count facts. | Context, UI, CLI, copilot, allocation, analytics, and full suites. |
| `RCR-008` | P2 | Closed | `242f8eb` | `risk/execution_gate.py`; allocation batch; execution budget storage | Available-capital overrides replaced authoritative cash/BP and could loosen the gate; exact budget accumulation could round below caps. | Inflated overrides changed a refusal to approval; precision-3 cap bypass reproduced. | Overrides are ceilings, never replacement evidence. | Use the conservative minimum of authoritative cash, BP, and valid overrides; reject negative/malformed overrides; exactify cap accumulation/reservation. | Primitive, execution-bound, batch, storage, and full-suite regressions. |
| `RCR-009` | P2 | Closed | `242f8eb` | `assistant/ai_advisor.py`; `data/filing_extraction.py` | Decimal `normalize()` made distinct financial figures (`1.2344`, `1.2345`) both look like `1.23`, weakening source grounding. | Low-context grounding probe treated an invented value as sourced. | Financial source identity must not depend on ambient precision. | Use tuple-based context-free canonical decimal text; preserve trailing-zero equivalence. | 59 focused advisor/filing tests and full suite. |
| `RCR-010` | P2 | Closed | `242f8eb` | portfolio mandate/policy, broker session/order contract, stream/reconciler | Optional identity fields, partial SDK identity, missing stream events, malformed numerics/timestamps, and permanent snapshot-integrity conditions had inconsistent classification or coverage. | Field-by-field and partial-SDK probes found unpinned branches; missing event substituted order status. | Broker and policy evidence must be explicit, typed, and account-scoped. | Strict identity/JSON parsing, public emergency SDK surface, optional-field normalization, event unavailability, permanent integrity classification, and complete parameterized coverage. | 240 storage/broker and 152 Decimal/broker-order/cancel-all tests; full suite. |
| `RCR-011` | P2 | Closed | `242f8eb` | `assistant/storage.py`; `assistant/order_reconciler.py` | Legacy EXECUTED rows caused false incomplete cancel-all, schema ordinal noise masked drift, containment IDs collided, recurrence records diverged, and cancel records had inconsistent/false-zero fields. | Direct database and emergency-cancel probes reproduced each outcome. | Incident and reconciliation records are safety evidence, not presentation. | Age/absence handling, exact migrated schema exception, reason-bound incident IDs, recurrence alert updates, unified cancel schema, truthful availability/counts, read-only guards. | Storage schema, atomic anomaly, cancel-all, event-ledger, and full suites. |
| `RCR-012` | P3 | Closed | `242f8eb` | allocation/discrete/rebalance/UI and portfolio analytics | Planner/UI summaries re-summed floats, could round dollar sizing over budget, lost planner refusal state, and exposed derived values when analytics were unavailable. | Low-context/floating boundary probes changed shares, spend, identity, or UI claims. | Preview, proposal, and execution must describe the same exact plan. | Add exact planned-notional provenance, exact floor/cross-product sizing, deterministic displays, explicit refusals, and unavailable rendering. | 141 UI/financial, 122 focused, changed-file, and full suites. |
| `RCR-013` | P3 | Closed | `242f8eb` | `assistant/portfolio_snapshot.py`; `assistant/schemas.py`; gate tests | `buying_power_exact` could exist while the optional display field claimed buying power absent. | Manual snapshot passed the old canonical validator; bound execution separately refused. | Optional evidence companions must agree even on read-only/manual paths. | Reject orphan exact companion; degrade reports; add typed gate violation. | Seven narrow, 354 combined, and full suites. |
| `RCR-014` | P2 | Open | `6a50734` | `assistant/portfolio_snapshot.py`; `assistant/execution_service.py`; `risk/execution_gate.py` | `BRK-001`: an incomplete unrelated position can block a legitimate risk-reducing sell because execution capture requires a complete account book. | Structural/reproduction evidence exists; real Alpaca reachability remains unconfirmed and provider access was not authorized. | Dropping unknown positions would corrupt exposure and held-share authority; a safe partial-book sell needs a new contract. | See section 10.1. | Requires owner-approved design, provider-independent fixtures, and independent review. |
| `RCR-015` | P2 | Open | `6a50734` | storage recovery/CLI/operations docs | Contained cancel-all survives journal corruption, but there is no authenticated repair/quarantine/restore workflow for normal operation. | Strict construction correctly remains unavailable after tamper. | Re-enabling a general store without an evidence-preserving recovery protocol would weaken tamper detection. | See section 10.2. | Offline corruption fixtures, byte-preserving backup, audit record, and independent restore review required. |
| `RCR-016` | P3 | Open | `6a50734` | broker order provenance | `BRK-008`: per-order account provenance is session-derived rather than independently observed from each order row. | Expected and observed account values share the same session evidence. | Current session sealing prevents cross-account dispatch, but journal wording can overstate per-row observation. | See section 10.3. | Contract and journal migration tests required. |
| `RCR-017` | P3 | Open | `6a50734` | `TradeIntent` and Alpaca submission schemas | `BRK-009`: limit price still crosses the final SDK/REST boundary as a binary float. | Quantity has exact transport; limit price does not. | Gate validation mitigates policy bypass, but transport can drift. | See section 10.4. | Exact-companion migration and broker-request capture required. |
| `RCR-018` | P3 | Open | `6a50734` | broker-event initialization | `STO-009`: every store construction reauthenticates the entire broker-event ledger. | Correct O(n) full scan is visible in initialization. | Correctness is preserved, but latency grows without bound. | See section 10.5. | Authenticated checkpoint/tail/full-audit tests required. |
| `RCR-019` | P3 | Open | `6a50734` | `data/financial_primitives.py`; remaining reporting modules | Direct extreme exponents can cause large non-exponent string allocation; attribution/cash/history/telemetry/sleeve reporting retains bounded ambient/display arithmetic. | Static audit found no remaining execution authorization path, but reporting availability/honesty can still degrade. | This is availability/reporting hardening, not a demonstrated trade fail-open. | See section 10.6. | Resource-bound and low-context reporting tests required. |
| `RCR-020` | P3 | Open | `6a50734` | contained cancel-all internal surface | Same-process Python can construct or monkeypatch private internals. | Direct import-level manipulation is possible. | The application is not a hostile-code sandbox; module privacy is not a security boundary. | See section 10.7. | Document trust boundary; use process/OS isolation if hostile plugins become in scope. |
| `ARV-001..014` | P1–P3 | Delegated | — | Analyst Revisions V2 lane | Analyst strategy findings require lane-owned implementation/review and were explicitly excluded by the owner. | Owner scoped three parallel strategy worktrees. | Root edits would race or overwrite authorized lane work. | None here. | Must be dispositioned on the Analyst lane's exact pushed snapshot. |

## 7. Disposition of Claude's 45 unique finding IDs

| Claude ID(s) | Counter-review disposition | Current result |
|---|---|---|
| `EXE-001` | Accepted after correction | Closed by canonical built-in sell recognition; malformed/unknown side stays fenced. |
| `STO-001` | Accepted after correction | Emergency cancel-all retained through a capability wrapper; full mutable store escape removed. Authenticated repair remains separate open item `RCR-015`. |
| `VAL-001` | Accepted | Closed; 110-finding guard remains hard-coded and mutation-proved. |
| `POL-001`, `POL-002` | Accepted after correction | Typed exact conversion and canonical execution/report validation now share the required invariants. |
| `BRK-001` | Accepted as open | Open as `RCR-014`; no provider reachability or owner design authority was assumed. |
| `STO-002`, `STO-003`, `STO-004` | Accepted after correction | Closed with legacy absence, migrated-layout, and reason-bound incident fixes. |
| `EXE-002` | Accepted after correction | Closed with explicit unavailable risk/analytics and consumer suppression. |
| `BRK-002`, `BRK-004`, `BRK-005`, `BRK-006`, `BRK-007` | Accepted after correction | Closed with permanent/transient classification, truthful degradation, optional fields, public emergency client, and session identity. |
| `STO-005`, `STO-006`, `STO-007`, `STO-008` | Accepted after correction | Closed with recurrence, unified records, truthful counts, and complete writable guards. |
| `STO-009` | Accepted as open P3 | Open as `RCR-018`; correctness retained. |
| `POL-003`, `POL-004` | Accepted after correction | Closed with bounded calendar and strict JSON parsing. |
| `BRK-008`, `BRK-009` | Reclassified from P4 to P3; open | Open as `RCR-016` and `RCR-017`. |
| `POL-005`, `POL-006`, `POL-007`, `BRK-010` | Reclassified from P4 to P3; accepted after correction | Closed with typed policy identity, UTC-aware timestamp rules, exact downstream aggregation, and explicit missing-event semantics. |
| `DOC-001` | Accepted after correction | Current handoff is replaced after this report; stale correction branch wording removed. |
| `DOC-002` | Informational | Its own as-of qualifier makes it historical, not a current P0–P3 issue. |
| `ENV-001` | Informational/out of scoped repository | External temporary worktrees were not needed or touched. The two verified in-repository counter-review temp directories were removed after validation. |
| `ARV-001` through `ARV-014` | Delegated/excluded | Not disposed or closed here; owned by the Analyst Revisions V2 lane. |

`BRK-003` is not in this table because Claude's report contains no `BRK-003`
finding row; `POL-001` says it supersedes that label.

## 8. What changed in the accepted implementation

### 8.1 Execution and broker boundary

- Only a canonical built-in `"sell"` receives the ambiguity risk-reduction
  exception.
- Execution snapshots, order books, order rows, timestamps, account identity,
  optional SDK state, quantity precision, and symbol identity are typed and
  fail closed.
- Broker stream absence stays absent; polling remains fallback evidence.
- Available-capital overrides can only tighten authoritative cash and buying
  power.
- Emergency cancellation stays reachable through corrupt local journal state
  without exposing a general mutable store.

### 8.2 Financial arithmetic and persistence

- Exact arithmetic helpers are independent of ambient Decimal context and
  bounded against unrepresentable coefficients/exponents.
- Authorization comparisons use exact operands/cross-products; deterministic
  division/quantization is display or derived evidence only.
- Execution budget, allocation batch, dividends, earmarks, fill reconstruction,
  ledger balances, split/share math, proposal identity, sell sizing, and
  rebalance paths consume exact companions.
- Provider-exact fills remain exact through durable journal sync and duplicate
  verification.
- Read-only storage refuses mutation before database/runtime contact; ordinary
  read connections are read-only even for a writable store.

### 8.3 Portfolio evidence, proposals, and UI

- Risk and analytics unavailability are explicit, never safe-looking zeroes.
- Buy proposal, allocation, steering, and discrete-buy paths refuse when
  portfolio or active-order evidence is incomplete.
- Risk-reducing sell controls remain available when their required evidence is
  independently valid.
- Allocation and discrete sizing use exact floors and exact planned-notional
  provenance; UI summaries no longer re-sum floats.
- Source-grounding canonicalization cannot collapse distinct financial values
  under a hostile Decimal context.

## 9. Validation evidence

All authoritative commands ran from
`C:\git\customizedAgent\trading_agent` on the final implementation tree.

| Validation | Result |
|---|---|
| Changed and new test files (47 files) | **1,681 passed, 0 failed, 1 warning in 250.54s** |
| First full run on near-final tree | 5,716 passed, 2 skipped, **4 failed**, 25 warnings in 1,827.60s; correctly rejected as final evidence |
| Four-failure targeted rerun | **4 passed** |
| Complete affected fault/separation files | **41 passed** |
| Final complete repository suite | **5,720 passed, 2 skipped, 0 failed, 25 warnings in 1,843.55s** |
| Compile | `python -m compileall -q assistant data execution risk scripts signals strategies backtest ml tests research baskets.py config.py market_analytics.py` exited 0 |
| Diff integrity | `git diff --check` clean before code commit |
| Credential-shape scan | No matching added credential/private-key shapes |
| Temp hygiene | Verified and removed `.tmp_counterreview_pair` and `.tmp_counterreview_single`; both were inside the repository and dated 2026-08-27 |

The 25 warnings are one third-party `websockets.legacy` deprecation and 24
NumPy/joblib deprecations. No warning is a test skip or an application failure.

Supporting focused evidence included 309 strategy-arithmetic tests, 141
financial/UI tests, 240 storage/broker tests, 354 ledger/storage/tax/corporate/
risk tests, 152 Decimal/broker/cancel-all tests, 99 direct ledger tests, and 59
source-grounding tests. The complete suite remains the certification authority.

## 10. Remaining work: HOW and WHERE

### 10.1 `BRK-001`: safe risk reduction with an incomplete position book

**Where:** `assistant/portfolio_snapshot.py`, `assistant/execution_service.py`,
`risk/execution_gate.py`, broker-session contract, and new focused tests.

**How:**

1. Define a separate immutable `RiskReductionPositionEvidence` contract; do
   not weaken the complete `PortfolioSnapshot` contract.
2. Bind it to one broker session/account/mode/capture time and one target
   symbol's exact held quantity, price evidence, and asset eligibility.
3. Carry an explicit `account_book_complete=False` state and the identities of
   unusable sibling rows; never silently drop them.
4. Permit only a long-only sell whose exact quantity is positive and no greater
   than verified held shares. Refuse buys, short opening, basket/exposure
   overrides, and any intent requiring unknown sibling exposure.
5. Decide, with owner approval, which policy checks remain meaningful under
   incomplete account evidence. Record every intentionally unavailable check.
6. Add provider-independent fixtures for malformed target row, malformed
   unrelated row, duplicate symbol, partial fills, active sells, stale capture,
   account mismatch, and broker mutation.
7. Require independent review before any provider validation. A live/provider
   probe is not authorized by this record.

### 10.2 Authenticated corrupt-journal recovery

**Where:** `assistant/storage.py`, CLI operations, operations documentation, and
new offline recovery tests.

**How:**

1. Keep current strict construction and contained cancel-all unchanged.
2. Add an offline command that opens the source read-only, records its byte
   hash, copies it to a new quarantine/recovery artifact, and never edits the
   original.
3. Verify the authenticated chain until the first failing row; export the
   failing row, predecessor hash, schema, and incident identity.
4. Support only explicit restore from a separately verified backup or an
   owner-confirmed quarantine operation that produces a new database and a
   permanent audit record.
5. Require typed confirmation, active kill switch, no broker contact, and a
   second independent review of the recovered chain before writable use.
6. Test tamper, truncation, reordered rows, duplicate IDs, schema mismatch,
   failed backup, interrupted recovery, and wrong-source restoration.

### 10.3 Per-order account provenance (`BRK-008`)

**Where:** `execution/broker_contract.py`, Alpaca normalization/session layer,
broker-event schema and journal projection.

**How:** distinguish `session_account_id` from `order_account_id_observed`.
Persist the latter only when the provider row actually supplies independently
verified evidence. Otherwise record `account_provenance=session_bound`, not an
observed row claim. Migrate readers and add cross-account/session-rotation
tests.

### 10.4 Exact limit-price transport (`BRK-009`)

**Where:** `TradeIntent`, proposal serialization/fingerprint, policy validation,
REST/SDK request builders, stored order evidence.

**How:** add canonical `limit_price_exact`, validate compatibility with the
legacy display field, include it in stable identity, migrate stored proposals,
and submit Decimal/canonical text at the final broker boundary where supported.
Capture the outgoing request in tests and prove sub-cent/trailing-zero identity
does not drift.

### 10.5 Authenticated event-ledger checkpoints (`STO-009`)

**Where:** broker-event journal schema, store initialization, schema verifier,
and a separate full-audit command.

**How:** create versioned, hash-chained checkpoints that bind row count, terminal
event hash, schema version, checkpoint predecessor, and database identity.
Normal initialization may verify the authenticated checkpoint plus tail; an
operator full-audit command must still reauthenticate every row. Never trust a
plain row offset or mutable cached digest. Test deletion, insertion, reordering,
checkpoint rollback, wrong database, and key/version rotation.

### 10.6 Remaining Decimal availability/reporting hardening

**Where:** `data/financial_primitives.py::decimal_text`, then reporting-only
arithmetic in attribution, cash reporting, portfolio history, sleeve reports,
and execution telemetry.

**How:** impose an explicit exponent/output-length bound before non-exponent
text materialization; return typed domain unavailability instead of allocating
unbounded strings. Migrate remaining report sums/divisions to exact or explicit
deterministic helpers, keeping authorization comparisons exact. Add low-context,
huge-exponent, underflow, and nonterminating-ratio tests. Do not turn a report
failure into a trade or proposal refusal unless its evidence is actually
required by that action.

### 10.7 Same-process containment trust boundary

**Where:** architecture/security documentation and plugin/process design.

**How:** state explicitly that Python-private classes are capability hygiene,
not a hostile-code sandbox. If untrusted plugins or arbitrary imported code
become in scope, move emergency containment and storage mutation into a
separate least-privilege process/OS identity with an authenticated IPC
contract. Do not claim import privacy as a security boundary.

## 11. Quality assessment

| Artifact | Rating | Reason |
|---|---:|---|
| Claude independent review/correction series | **5.5 / 10** | It found important real defects and added useful tests, but its ledger/count/process claims were inaccurate, its correction exposed a full mutable contained store, and acceptance preceded required Codex counter-review. |
| Corrected main-line code snapshot `242f8eb` | **8.8 / 10** | High-risk execution, storage, evidence, exact-arithmetic, ledger, UI, and test controls are strongly covered and the complete suite is green. Rating is held below 10 by the explicit open design/scalability items in section 10. |

## 12. Final boundary and next step

- No P0 remains.
- All six Claude commits are **accepted after correction**.
- The code snapshot is local-only until the owner asks for a push.
- No strategy branch or worktree was touched.
- No feature milestone is declared complete by this review, so
  `docs/FEATURE_MILESTONE_RECORD.md` is unchanged.
- Sequencing, milestone status, and gates did not change, so
  `docs/ACTION_PLAN_2026-08-20.md` is unchanged.
- After the separate Session Handoff commit, the next authorized action is to
  push only if the owner requests it, then archive this session until the three
  strategy lanes are complete. A later owner-initiated whole-project review
  must start from the exact integrated main snapshot at that time.
