# Architecture debt

Known structural gaps this project has consciously chosen not to fix
yet, and why — so they don't get silently rediscovered from scratch in a
future review, or silently forgotten because nothing points at them.
See also `docs/MANDATE.md` for the numeric-target/scope-decision
counterpart to this file.

## 1. Execution kernel structural split

`assistant/execution_service.py` (proposal lifecycle state machine,
broker submission/reconciliation, duplicate-order/pending-exposure
estimation, policy-fingerprint binding, override review-digest
bookkeeping, earnings-data resolution) and `assistant/allocation_batch.py`
(batch orchestration, cross-leg reservation math) mix several distinct
concerns that would ideally live in smaller, state-machine-oriented
components.

**Deferred to a dedicated future session — not attempted 2026-07-28**
alongside the mandate/risk-metrics work in this same round. Reason:
`execution_service.py`'s module docstring documents 19 sequential rounds
of independent adversarial review (Codex/GPT, 2026-07-27 through
2026-07-31) closing real safety gaps — atomic proposal claiming,
fail-closed open-order lookups, three-way submission reconciliation,
kill-switch enforcement as a service-level invariant, strict order-
matching, policy-fingerprint binding, HMAC-signed authorization proofs
(most recently hardened against a `dataclasses.replace()` token-swap
bypass). Many of these fixes are not visible in any single function's
logic but in the *sequencing* between functions — e.g. the expiry check
folded into the same atomic conditional `UPDATE` as the proposal claim
specifically to close a race window. A structural split risks separating
two pieces of state that were deliberately kept atomic together,
silently reintroducing exactly the class of bug those 19 rounds closed.
This needs its own dedicated, carefully-reviewed session, not a subtask
squeezed alongside unrelated documentation/metrics work.

**Partially addressed 2026-07-29** by the transaction-ready order
lifecycle work (commit 84da938), which did get its own dedicated session
and extracted three genuinely separable concerns out of what would
otherwise have been further `execution_service.py` growth:
`assistant/order_lifecycle.py` (broker-status → proposal-state mapping
and event projection), `assistant/order_reconciler.py` (startup polling,
trade-update stream, stale-order cancellation), and
`assistant/readiness.py` (operational preflight). The atomic
state-transition primitives moved into `assistant/storage.py`
(`project_broker_order_event`, `reserve_execution_budget`,
`mark_submission_failed_and_release`), which keeps each
multi-row transition inside a single `BEGIN IMMEDIATE` transaction rather
than spreading it across service-layer calls — the specific failure mode
this entry warned about.

**Partially addressed 2026-08-02** by GR-1's reviewed
`assistant/execution_kernel/` helper extraction. Broker-outcome
interpretation, stored-intent parsing, pre-broker claim fencing/recovery
support, revalidation inputs, submission sizing, and the shared exception
hierarchy now have explicit modules behind the unchanged
`assistant.execution_service` facade. GR-1B then moved the claim,
precondition, override-review, budget-reservation, submission-dispatch,
ambiguous-outcome, and accepted-order-journaling orchestration into named
kernel phases while retaining the storage-level atomic transition primitives.

**Partially addressed 2026-08-02 (GR-1C)**: the 315-line validation
orchestration moved into `assistant/execution_kernel/validate.py` behind an
explicit `ProposalValidationDeps` injection contract that the facade builds
at call time from its own namespace — which is what preserves the
`execution_service.validate_trade_intent` monkeypatch seam the previous
paragraph of this entry said made the move unsafe without DI.

**Still open**: `execution_service.py` remains 1,090 lines after the GR-1C
review restored the complete facade surface and injected every runtime
collaborator formerly resolved there. Its 276-line
execution composition and 221-line manual reconciliation function still keep
substantial state-machine orchestration on the facade, and it is not yet the
thin composition layer in the GR-1 definition of done. `allocation_batch.py`
also still owns cross-leg reservation math separately from the storage-level
budget reservation. The remaining split is smaller than it was, but not done.

## 2. Risk-check scatter

The core risk-governor rule engine (`risk/execution_gate.py`'s
`validate_trade_intent()` — kill switch, concentration caps, exposure
limits, staleness/gap checks, calendar checks, duplicate-order
detection, earnings blackout) is consolidated in one module. However,
risk-adjacent logic that feeds it, or shadows it, is scattered across
three other files:

- `assistant/execution_service.py::_pending_buy_value_by_ticker()` —
  pending-order exposure estimation, computed independently of the gate.
- `assistant/allocation_batch.py::preflight_allocation_batch()` —
  cumulative cross-leg reservation math for a multi-proposal batch,
  also computed independently and fed back into the gate via override
  parameters.
- `assistant/proposals.py::generate_risk_reduction_proposals()` — a
  simpler, proposal-generation-only concentration check (decides what
  to *suggest*), not gated through `validate_trade_intent()` (which
  decides what to *permit*) — by design, but a real second source of
  concentration-limit logic that could drift out of sync with the real
  gate over time.

**Not consolidated this round; cross-reference comments added
2026-07-28** at all three locations (and in `risk/execution_gate.py`'s
own module docstring, under "Known scatter points") so the drift is at
least visible to a future reader, even though the underlying logic
hasn't moved. Consolidation folds into item 1's kernel split when that
happens — moving this logic now, ahead of that split, would just mean
moving it twice.

## 3. `max_drawdown_pct` duplication — RESOLVED 2026-07-28

Was: `backtest/portfolio_simulator.py`'s private `_max_drawdown_pct()`
and `strategies/leverage_rotation.py`'s public `max_drawdown_pct()` were
two independent, byte-for-byte-identical implementations with no shared
source — the kind of duplication that silently drifts the next time one
gets tweaked and the other doesn't.

Fixed by introducing `backtest/risk_metrics.py::max_drawdown_pct()` as
the single canonical implementation; both prior call sites now delegate
to it (`portfolio_simulator.py` via a direct import, `leverage_rotation.py`
via a one-line re-export so its ~15 existing dependents don't need any
import changes). Verified via the full existing test suite plus new
tests in `tests/test_risk_metrics.py` — zero output change.
