# Proposal History Cleanup Implementation Plan

Status: **ARCHIVED — implemented and retained as the original contract.**

## 1. Purpose

The paper-trading UI currently keeps every generated proposal in
`trade_proposals`. Trying different Watchlist combinations therefore leaves a
long list of unused proposals in History.

This plan adds safe history cleanup without weakening the trading audit trail.
The normal user action will be **dismiss/archive**, not physical deletion.
Proposals that reached validation, approval, reservation, submission, or any
broker lifecycle must remain permanently auditable.

This document is a deferred implementation plan. It does not authorize or
implement database changes yet.

## 2. Current behavior

The current implementation has these properties:

- `AssistantStore.list_proposals()` returns the newest rows from
  `trade_proposals`; the UI's row limit only limits display.
- History has status filtering but no proposal-dismissal or proposal-retention
  action.
- The History cancellation control cancels a broker order. It does not remove
  the proposal that created the order.
- Proposal expiry is primarily an execution guard. A stale `proposed` or
  `override_available` row is changed to `expired` when an approval attempt
  discovers that its expiry has passed; merely opening History does not
  currently perform that transition.
- SQLite triggers prevent deletion of a proposal that has broker-order,
  broker-event, or execution-reservation children.
- Allocation batches contain proposal IDs inside `payload_json`, without a
  foreign-key relationship. Any future cleanup eligibility check must inspect
  those references explicitly.
- There is an explicit, opt-in retention command for decision packets, but no
  equivalent proposal lifecycle or retention policy.

Consequently unused proposals persist until the database is manually altered
or replaced.

## 3. Product decision

Implement three separate concepts and do not make one a hidden prerequisite
of another:

1. **Dismiss/archive:** removes an unused proposal from the default History
   view while retaining its complete database record.
2. **Automatic expiry:** an optional lifecycle-normalization milestone,
   separately approved after dismissal. It is not required to remove unused
   entries from the default UI and must not run merely because History was
   opened in the first release.
3. **Physical purge:** destructive database maintenance, excluded from the
   first implementation. It may be considered later only for already-dismissed,
   never-submitted paper proposals, with a dry run, backup, typed confirmation,
   and separate owner authorization.

The first release must solve the UI problem entirely through dismissal and
filtering. It must not automatically expire rows or delete trading evidence.

## 4. Lifecycle contract

### 4.1 New status

Add one status to `assistant/proposal_status.py`:

```text
dismissed
```

`dismissed` is terminal and non-executable. It must not be included in:

- `IN_FLIGHT_INTENT_STATUSES`;
- `UNRESOLVED_BROKER_STATE_STATUSES`;
- `ACTIVE_BROKER_ORDER_STATUSES`; or
- any approval-eligible status set.

It must be included in the canonical `STATUSES` list so old and new clients can
render it honestly.

### 4.2 Allowed transitions

The first implementation may dismiss only:

```text
proposed -> dismissed
expired  -> dismissed
```

`override_available` is deliberately excluded: it proves that validation was
attempted and a human-reviewable policy result was produced. Likewise,
`blocked`, `validation_failed`, `approved`, every submission state, and every
broker state remain audit history and cannot be dismissed.

Automatic expiry may perform only:

```text
proposed           -> expired
override_available -> expired
```

and only when `expires_at < now`. It must never rewrite `validating`,
`approved`, submitting, unresolved, working, or terminal broker states.

### 4.3 Dismissal metadata

Persist the following fields in the proposal payload during the same
transaction as the status transition:

```json
{
  "dismissed_at": "timezone-aware UTC timestamp",
  "dismissed_by": "local_operator",
  "dismissed_reason": "unused watchlist experiment",
  "dismissed_from_status": "proposed"
}
```

Require a non-empty reason. The status column remains authoritative, consistent
with existing storage behavior, while the payload carries the human-readable
audit detail.

## 5. Eligibility rules

A proposal is dismissible only if every check below passes inside one database
transaction:

- current status is exactly `proposed` or `expired`;
- no `broker_orders` row references the proposal;
- no `broker_order_events` row references the proposal;
- no `execution_reservations` row references the proposal;
- no allocation-batch payload references the proposal;
- payload contains no broker-order, approval, submission, fill, cancellation,
  reconciliation, or policy-override evidence; and
- the compare-and-set transition still sees the expected status at write time.

The child-row checks intentionally duplicate the existing delete-trigger
boundary. Dismissal does not delete those rows, but refusing an inconsistent
"unused" classification is safer than hiding a proposal that touched execution.

If any selected proposal is ineligible or changes concurrently, a bulk
dismissal must fail atomically and dismiss none of the selection. The UI then
refreshes authoritative state and explains which proposal blocked the action.

No broker API call is permitted anywhere in dismissal or expiry code.

## 6. Storage implementation

Add narrowly named dismissal methods to `AssistantStore`; do not expose a
generic arbitrary-status update to the UI. The expiry method shown below
belongs only to the separately approved follow-up:

```python
expire_due_proposals(*, now: datetime, limit: int = 500) -> ExpiryResult

proposal_dismissal_eligibility(
    proposal_ids: Sequence[str],
) -> DismissalPreview

dismiss_proposals(
    proposal_ids: Sequence[str],
    *,
    dismissed_by: str,
    reason: str,
    expected_preview_hash: str,
) -> DismissalResult
```

### 6.1 Optional follow-up: expiry sweep

This subsection is a separate follow-up milestone, not part of the first
dismiss/archive release. Its implementation requires separate owner approval
and review. Until then, existing approval-time expiry behavior remains
unchanged and opening History performs no durable lifecycle mutation.

`expire_due_proposals()` must:

- require a timezone-aware `now`;
- select only due `proposed` and `override_available` rows;
- parse and update payload JSON as well as the authoritative status column;
- record `expired_at` and `expired_from_status`;
- use a bounded batch size;
- perform conditional updates so a concurrent approval claim wins safely; and
- return examined, expired, skipped-race, and malformed counts.

A malformed timestamp or payload must be reported, not silently expired.

### 6.2 Dismissal preview and binding

The preview must return, for every requested ID:

- proposal ID, ticker, side, shares, status, creation and expiry time;
- dismissible boolean;
- exact refusal reasons; and
- a canonical hash covering the complete preview and current database state.

The mutation must require that preview hash. This prevents the user from
confirming one set of proposals while a refresh or concurrent process changes
their status or identity.

Use `BEGIN IMMEDIATE` or the repository's equivalent serialized transaction
pattern for the final eligibility recheck and updates.

### 6.3 Listing API

Extend listing with explicit visibility arguments rather than silently changing
the meaning of `status=None`:

```python
list_proposals(
    status: str | None = None,
    limit: int = 100,
    *,
    include_dismissed: bool = True,
    include_expired: bool = True,
) -> list[dict]
```

Keep both flags `True` by default at the storage layer for backward
compatibility and audit callers. The UI will choose cleaner defaults.

## 7. UI behavior

Update the History tab in `scripts/personal_assistant_ui.py`.

### 7.1 Automatic lifecycle refresh (optional follow-up only)

Do not run an expiry sweep in the first dismissal release. If the separately
approved expiry milestone later ships, its trigger must be chosen explicitly
(for example the existing operations cycle or an operator action) rather than
silently making a read-oriented page visit mutate lifecycle state. Display a
small notice when that explicit action expires rows or finds malformed data.

### 7.2 Visibility controls

Add:

- `Include expired proposals`, default off;
- `Include dismissed proposals`, default off; and
- the existing canonical status filter.

If a specific `expired` or `dismissed` status is selected, automatically make
the matching visibility flag effective and explain the behavior. Avoid a
filter combination that misleadingly says no rows exist.

Filled, canceled, rejected, unresolved, and other execution-relevant proposals
remain visible by default.

### 7.3 Dismiss controls

Provide a separate **Manage unused proposals** expander containing:

- a multiselect limited to currently dismissible proposals;
- a preview table;
- a required non-empty reason;
- the exact confirmation phrase `dismiss N proposals`; and
- an action button disabled until the phrase matches.

After success:

- clear every proposal-specific Streamlit confirmation, override, stale, and
  committee-review key for the dismissed IDs;
- refresh from storage;
- display the number dismissed; and
- keep `Include dismissed proposals` off unless the user explicitly enables it.

Never label this action `Delete`. The copy should state: "Dismissed proposals
remain in the local audit history and cannot be executed."

## 8. CLI parity

The first dismissal release adds `dismiss-proposals`. The optional expiry
follow-up adds `expire-proposals`; it is not a prerequisite for dismissal:

```text
expire-proposals
dismiss-proposals <proposal-id> [<proposal-id> ...]
  --reason <text>
  --preview
  --confirm-preview-hash <sha256>
```

`dismiss-proposals` should default to preview-only. Mutation requires both the
preview hash and an exact confirmation option such as
`--confirm-dismiss unused-paper-proposals`.

CLI and UI must call the same storage/service functions. Neither may reproduce
eligibility rules independently.

## 9. Physical purge remains deferred

Do not add `DELETE FROM trade_proposals` to the first release.

If storage size later becomes a demonstrated problem, write a separate plan
and require explicit owner approval for an opt-in command with all of these
properties:

- operates only on `dismissed` paper proposals older than a declared age;
- defaults to dry-run and prints IDs plus refusal reasons;
- verifies no broker, event, reservation, or allocation-batch reference;
- verifies a recent successful database backup and restore drill;
- records a cleanup manifest outside the rows being deleted;
- uses an exact typed confirmation and all-or-nothing transaction; and
- never runs automatically, during startup, or during UI rendering.

This deferred purge must also address the idempotency consequence: deleting a
proposal removes its unique `idempotency_key`, which may allow the same logical
proposal to be generated again. Dismissal avoids that risk because the original
row and key remain present.

## 10. Tests

### 10.1 Status and optional expiry follow-up

- the first dismissal release proves `dismissed` is canonical, terminal,
  non-approvable, and non-inflight;
- when the optional expiry follow-up is implemented, a proposal one
  microsecond before expiry is not expired;
- in that follow-up, a proposal exactly at the chosen expiry boundary follows the documented
  inclusive/exclusive rule;
- due `proposed` and `override_available` rows expire in that follow-up;
- no other status can be changed by its sweep;
- malformed timestamps/payloads are reported and preserved; and
- a concurrent approval claim cannot be overwritten by that expiry sweep.

### 10.2 Dismissal safety

- pristine `proposed` and `expired` proposals can be dismissed;
- every other status is refused;
- any broker order, event, reservation, or allocation-batch reference refuses
  dismissal;
- execution-shaped payload evidence refuses dismissal even if the status was
  corrupted back to `proposed`;
- stale preview hashes are refused;
- bulk operations are all-or-nothing;
- repeated dismissal is idempotently reported, not rewritten;
- dismissal makes no broker call and creates no order/event/reservation; and
- dismissed proposals cannot be approved through service, CLI, or stale UI
  state.

### 10.3 Presentation

- History hides expired and dismissed rows by default;
- either class is recoverable through explicit visibility controls;
- selecting its exact status cannot be contradicted by a hidden visibility
  filter;
- proposal-specific session state is cleared after dismissal;
- filled, canceled, rejected, and unresolved orders remain visible; and
- row limits and status filtering remain deterministic.

### 10.4 Regression

- proposal idempotency behavior remains unchanged;
- duplicate-order protection remains unchanged;
- allocation batch resume/reconciliation remains unchanged;
- foreign-key and integrity audit tests remain green;
- paper execution and broker reconciliation suites remain green; and
- full repository test suite passes with real broker credentials removed.

## 11. Implementation sequence

1. Add `DISMISSED` and lifecycle classification tests.
2. Add typed dismissal result contracts.
3. Implement storage eligibility, preview hashing, and atomic dismissal.
4. Add storage and concurrency tests, including allocation-batch JSON
   references.
5. Add preview-first CLI commands and tests.
6. Add History visibility and dismissal UI using the shared service.
7. Add stale Streamlit-session cleanup tests.
8. Update README/operations documentation with the archive-versus-delete
   distinction.
9. Run the focused lifecycle/UI suites and the complete offline suite.
10. Have the implementation adversarially reviewed before merge.

Optional expiry is planned and reviewed afterwards as a separate milestone,
using the contracts in sections 4.2, 6.1, and 10.1 without changing the
accepted dismissal release retroactively.

## 12. Definition of done

This feature is complete only when:

- unused Watchlist experiments can be bulk-dismissed from the UI;
- expired and dismissed proposals no longer clutter the default History view;
- all dismissed records remain queryable with their reason, actor, source
  status, and timestamp;
- no proposal that touched validation/override, allocation batching,
  reservation, submission, or broker lifecycle can be dismissed;
- no cleanup action can call the broker or alter an order;
- stale UI state cannot approve a dismissed proposal;
- no automatic physical deletion exists; and
- all focused and full-suite tests pass.
