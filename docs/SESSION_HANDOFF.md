# Development session handoff

Prepared: 2026-08-04 after Claude implemented UI-2d (durable proposal
dismiss/archive) and pushed it for independent review.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Current outcome

UI-2d — dismiss/archive for unused proposals — is **implemented and pushed,
awaiting independent review**. This is the first UI Phase 2 milestone that
changes durable runtime state (a new lifecycle status and payload metadata),
though it grants no execution authority. The contract is
`docs/reference/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` (as
rewritten by the 2026-08-03 plan review: dismissal only — automatic expiry
is a separately approved follow-up that was NOT implemented, and physical
purge remains deferred).

What was implemented, per that plan:

- **Lifecycle** (`assistant/proposal_status.py`): terminal `DISMISSED`
  status appended to `STATUSES`; deliberately absent from
  IN_FLIGHT/UNRESOLVED/ACTIVE/TERMINAL_BROKER sets (holds no ticker/side
  slot, implies no broker order); `DISMISSIBLE_SOURCE_STATUSES = (proposed,
  expired)` — `override_available` is excluded because it proves validation
  was attempted. UI-2b's exhaustive outcome mapping gained
  `dismissed -> Closed without fill` (the exhaustiveness test forced this
  same-change update, exactly as designed), and the frozen literals in
  `tests/test_proposal_outcome_groups.py` and
  `tests/test_personal_assistant_ui.py` were updated as deliberate reviewed
  regroupings.
- **Storage** (`assistant/storage.py`): `proposal_dismissal_eligibility()`
  (read-only preview: per-row verdicts, exact refusal reasons, and a
  canonical sha256 preview hash over id/status/updated_at/verdicts) and
  `dismiss_proposals()` (BEGIN IMMEDIATE; recomputes eligibility with the
  SAME shared `_dismissal_records()` rule so preview and mutation can never
  drift; refuses all-or-nothing when any non-dismissed row is ineligible;
  refuses a stale preview hash; per-row compare-and-set UPDATE guarded by
  rowcount; writes dismissed_at/by/reason/from_status into the payload in
  the same transaction; idempotent replay when every row is already
  dismissed — original metadata never rewritten, nothing enforced or
  written). Eligibility refuses on: non-dismissible status, any
  broker_orders/broker_order_events/execution_reservations child row,
  any allocation-batch payload reference (proposal_ids or legs; an
  UNREADABLE batch payload fails closed against every candidate), and any
  execution-shaped payload key (`_DISMISSAL_EXECUTION_EVIDENCE_KEYS`:
  approved_at, broker_order, broker_order_update, broker_status,
  cancel_requested_at, error, executed_at, filled_at, policy_override,
  reconciled_at, submitted_at, violations) so a status corrupted back to
  `proposed` still refuses. `list_proposals()` gained keyword-only
  `include_dismissed`/`include_expired` flags (default True for audit
  callers; applied ONLY when `status is None` so an explicit exact-status
  selection always wins). No schema migration was needed: `status` is an
  unconstrained TEXT column and the payload is JSON.
- **CLI** (`scripts/run_personal_assistant.py`): `dismiss-proposals`
  defaults to preview (JSON rows + refusal reasons + preview hash);
  mutation requires `--reason`, `--confirm-preview-hash <sha256>` AND
  `--confirm-dismiss unused-paper-proposals`; calls the same storage
  functions as the UI.
- **UI** (`scripts/personal_assistant_ui.py`): History gains default-off
  `Include expired proposals` / `Include dismissed proposals` checkboxes
  (whitelisted benign filters) that govern ONLY the unfiltered view —
  outcome-group or exact-status selection always shows its rows, with a
  caption stating the auto-visibility when expired/dismissed is selected
  and a "Hiding X and Y" caption otherwise. The "Manage unused proposals"
  expander lists only currently dismissible rows (storage decides; the UI
  reproduces no eligibility rule), shows a preview table, requires a
  non-empty reason plus the exact phrase `dismiss N proposals`, and the
  button stays disabled until both match. Success clears every
  per-proposal confirm/override/committee/digest/cancel session key for
  the dismissed IDs plus the expander's own keys, then reruns with the
  notice carried in a non-widget session key. The
  `dismiss_selection`/`dismiss_reason`/`dismiss_confirmation` keys are
  deliberately NOT navigation-persistent (added to the sensitive-key
  structural test). `_proposal_status_category()` gained a "dismissed"
  branch ahead of every fallback so a stale card renders the dismissal
  record, never approval controls or "in progress".

Deliberately NOT implemented: `expire_due_proposals()`/`expire-proposals`
(the optional follow-up), any physical deletion, any broker call in
dismissal code, any change to approval/claim/reconciliation logic (a
dismissed row is simply never claimable because claims expect
proposed/override_available — pinned by test).

## 2. Canonical Git state

Repository: https://github.com/SheltonChen2017/trading_agent

    base/main/origin-main = 5cb831c (post PR #142)
    implementation = the first commit on this branch
    docs/handoff = the branch-tip commit containing this file
    branch = user/claude/ui-2d-proposal-dismissal-20260804 (pushed)

Nothing has been merged. The owner opens the PR (this machine's gh account
cannot create PRs).

## 3. Validation (development machine, Python 3.13, exact final tree)

    dismissal storage + CLI tests (tests/test_proposal_dismissal.py): 43
    History dismissal AppTests (tests/test_ui_history_dismissal.py): 6
    all UI-2d-adjacent focused suites (incl. outcome groups, UI-2b filter,
        UI helpers, feature controls, import boundary): 124 passed
    full suite: 2,663 passed, 1 skipped, 25 warnings in 629.63s
    compileall (all packages + root modules): clean
    git diff --check: clean

Reverse-mutation proofs (each applied, shown red, restored):

1. Widening `DISMISSIBLE_SOURCE_STATUSES` with `approved` → caught by
   THREE tests (lifecycle literal, the parametrized per-status refusal,
   and all-or-nothing).
2. Disabling the preview-hash comparison in `dismiss_proposals` → caught
   at BOTH layers (storage stale-hash test and the CLI wrong-hash test).
3. Removing the `dismissed` branch from `_proposal_status_category` →
   caught by the exhaustive status-router coverage test (dismissed fell
   through to "in_progress").

Known coverage limits, stated for the reviewer: there is no
multi-process/threaded concurrency test for dismiss-vs-claim races (the
compare-and-set UPDATE + BEGIN IMMEDIATE + the benign-state-change hash
test cover the mechanism single-threaded, and claim_proposal's own
concurrency coverage exists elsewhere); the UI expander's
stale-selection sanitization (another process dismissing a selected row
mid-session) is exercised only indirectly through the hash-refusal path.

## 4. Review guidance

Review range: the implementation commit plus this handoff commit on
`user/claude/ui-2d-proposal-dismissal-20260804`, based on `5cb831c`. The
contract is `docs/reference/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md`
sections 3–8 and 10 (dismissal scope only). Adversarial attention is most
useful on:

- the eligibility rule: any way a proposal that touched
  validation/batching/reservation/broker can still pass (payload-key set
  completeness; the allocation-batch scan's `proposal_ids`+`legs` reach);
- the preview-hash canonicalization: any state change that should
  invalidate a confirmation but does not alter the hash inputs
  (id/status/updated_at/dismissible/refusal_reasons);
- the idempotent-replay branch (all-rows-dismissed → no-op without hash
  enforcement): whether it can be abused to skip a check;
- transaction discipline in `dismiss_proposals` (BEGIN IMMEDIATE, rowcount
  guard, rollback paths, connection close);
- Streamlit state: the pre-instantiation sanitization of
  `dismiss_selection`, post-success key clearing + rerun notice, and that
  no dismissal key survives navigation; and
- CLI confirmation ordering (preview default, exact confirm string, hash
  required, refusals exit nonzero without partial writes).

## 5. What is next (do not start without owner direction)

- Independent review of this branch, then the owner's merge decision.
- The optional automatic-expiry follow-up remains unapproved and
  unimplemented; physical purge remains deferred and owner-authorized.
- UI Phase 2 is otherwise complete (UI-2a/2b/2c/3 reviewed; UI-2d in
  review). Phase 5 (operational deployment + epoch start) remains
  owner-heavy, blocked only on the four decisions in
  `docs/PHASE5_DEPLOYMENT_SESSION.md` §2. Note: if the owner starts a
  model-1 frozen-runtime epoch before this branch merges, deployment of
  UI-2d to the operational machine waits for the epoch boundary.

## 6. Non-negotiable boundaries

- Paper trading is the only execution mode in scope.
- Dismissal is archive, never delete: no row, payload, or idempotency key
  leaves the database, and no cleanup action can call the broker or alter
  an order.
- Only never-broker-touched `proposed`/`expired` rows are dismissible;
  everything else is permanent audit history.
- A dismissed proposal can never be approved, claimed, or executed —
  through service, CLI, or stale UI state.
- ML/LLM output remains advisory or observational only.
- Never commit credentials, operator databases, licensed data, or evidence
  artifacts.

## 7. Machine-local state

The owner's Streamlit app may be running from an earlier checkout; it does
not gain dismissal until this branch merges and the app reloads. This
session did not stop, restart, or mutate that process. All tests ran
against the pytest-isolated session database; the operator database was
not touched.
