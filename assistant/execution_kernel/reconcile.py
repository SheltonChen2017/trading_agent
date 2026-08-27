"""Manual submission reconciliation: resolve a stuck submission by re-query.

GR-1D extraction. ``run_submission_reconciliation()`` is the user-facing
manual path for a proposal stranded in "submitting" or "submission_unknown":
re-query the broker under the proposal's own idempotency key, cross-check
the result against the stored intent, resolve replacement chains, and either
journal the authoritative order, confirm aged absence, or return the
proposal to a retryable unresolved state. It never releases a reservation on
an ambiguous outcome, never converts a local error into broker-confirmed
absence, and treats a same-key mismatched order as a platform-halt anomaly
(persistent kill switch), never something to adopt automatically.

Dependency injection, not namespace resolution: every facade-derived runtime
name this orchestration consults arrives explicitly via
``ReconciliationDeps``. The facade (assistant.execution_service) constructs
that contract AT CALL TIME from its own module namespace, so a monkeypatch
on ``assistant.execution_service._lookup_order_outcome`` (or any other
injected runtime name, including the exception class, the status constants,
and the clock) still reaches this module.
tests/test_execution_characterization.py freezes each seam directly, and the
broker module arrives via ``deps.import_broker()`` executed at the exact
point the historical inline ``import execution.alpaca_broker`` statement
ran -- first inside the try block, AFTER the atomic claim -- so an
unimportable broker package lands in the same unexpected-error recovery path
it always did, and sys.modules-level broker fakes keep working unchanged.

This module imports none of the injected collaborators, which also keeps
GR-1 section 6.2 satisfied structurally: no private peer imports exist to
forbid. The atomic claim and every conditional status transition remain
storage-level operations invoked through the ``store`` argument; nothing
here re-implements or splits them.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable

from assistant.storage import AssistantStore


@dataclasses.dataclass(frozen=True)
class ReconciliationDeps:
    """Every facade-resolved runtime name used by manual reconciliation.

    The facade builds this AT CALL TIME from its own module globals -- never
    at import time, never from this module's namespace. The injection
    boundary is exact and symtable-pinned:
    ``run_submission_reconciliation()`` resolves no runtime collaborator
    from module scope. That includes the exception class (raised AND caught
    through the same injected object, preserving pre-GR-1D patch behavior),
    the three behavior-bearing status constants, both clock collaborators,
    and the deferred broker import.

    ``test_gr1d_the_kernel_body_reads_no_module_globals`` pins the empty
    runtime-global set. Adding any module-global read to the body --
    including quietly resolving a formerly injected dependency directly --
    fails and requires the collaborator to join this contract.
    """

    # Deferred provider for execution.alpaca_broker, called at the exact
    # point the historical inline import ran (first statement inside the
    # try, after the atomic claim). A provider rather than the module object
    # so an unimportable broker package still takes the unexpected-error
    # recovery path, and so sys.modules/parent-package broker fakes are
    # resolved at call time exactly as the inline import resolved them.
    import_broker: Callable[[], Any]
    open_broker_session: Callable[[Any], Any]
    datetime_type: Any
    timezone_type: Any
    proposal_execution_error: type[Exception]
    submitting: str
    submission_unknown: str
    reconciling: str
    intent_from_dict: Callable[[dict], Any]
    lookup_order_outcome: Callable[..., Any]
    order_matches_intent: Callable[..., tuple]
    observed_broker_account: Callable[..., Any]
    assert_expected_broker_account: Callable[..., Any]
    canonical_order_for_proposal: Callable[..., dict]
    authoritative_order_for: Callable[..., tuple]
    broker_absence_is_old_enough: Callable[..., bool]
    journal_broker_order_update: Callable[..., Any]


def run_submission_reconciliation(
    proposal_id: str,
    store: AssistantStore,
    *,
    deps: ReconciliationDeps,
) -> dict:
    """Body of the facade's ``reconcile_submission()``, moved verbatim.

    See the facade wrapper for the full outcome contract docstring; the
    behavior, branch order, exception identities, state transitions, and
    reservation handling are exactly the pre-GR-1D facade behavior.
    """
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise deps.proposal_execution_error(f"Unknown proposal: {proposal_id}")

    claimed = store.claim_proposal(
        proposal_id,
        expected_status=(deps.submitting, deps.submission_unknown),
        new_status=deps.reconciling,
    )
    if claimed is None:
        current_status = proposal["status"]
        raise deps.proposal_execution_error(
            f"Proposal {proposal_id} is not reconcilable (status={current_status!r}) -- reconciliation "
            "only applies to proposals stuck in 'submitting' or 'submission_unknown'."
        )

    try:
        broker_module = deps.import_broker()
        broker = deps.open_broker_session(broker_module)

        stored_intent = deps.intent_from_dict(proposal["intent"])
        observed_account = deps.observed_broker_account(broker)
        try:
            deps.assert_expected_broker_account(proposal, observed_account)
        except Exception as binding_exc:
            reconciled_at = deps.datetime_type.now(
                deps.timezone_type.utc
            ).isoformat()
            reason = (
                "Manual reconciliation cannot prove the proposal belongs to "
                f"the connected broker account: {binding_exc}. Persistent kill "
                "switch activated; investigate manually."
            )
            store.park_reconciliation_anomaly_and_halt(
                proposal_id,
                expected_statuses=(deps.reconciling,),
                reconciled_at=reconciled_at,
                reason=reason,
                new_status=deps.submission_unknown,
                details={"path": "manual_account_binding"},
                anomaly_key="manual_account_binding_mismatch",
            )
            raise deps.proposal_execution_error(reason) from binding_exc
        outcome = deps.lookup_order_outcome(broker, proposal["idempotency_key"])
        reconciled_at = deps.datetime_type.now(deps.timezone_type.utc).isoformat()

        if isinstance(outcome, dict):
            try:
                root_order = deps.canonical_order_for_proposal(
                    outcome,
                    stored_intent,
                    proposal,
                    observed_account=observed_account,
                    root_order=True,
                )
            except Exception as evidence_exc:
                mismatch_detail = str(evidence_exc)
                expected_desc = f"{stored_intent.side} {stored_intent.shares} {stored_intent.ticker} {stored_intent.order_type}"
                if stored_intent.order_type == "limit":
                    expected_desc += f" @ {stored_intent.limit_price}"
                reason = (
                    f"Reconciliation found an order under this idempotency key that does NOT match the "
                    f"proposal's intent (mismatch: {mismatch_detail}; expected {expected_desc}; broker "
                    f"returned {outcome}) -- persistent kill switch activated; investigate manually."
                )
                store.park_reconciliation_anomaly_and_halt(
                    proposal_id,
                    expected_statuses=(deps.reconciling,),
                    reconciled_at=reconciled_at,
                    reason=reason,
                    new_status=deps.submission_unknown,
                    details={"mismatch": mismatch_detail, "path": "manual_lookup"},
                    anomaly_key="manual_lookup_identity_mismatch",
                )
                raise deps.proposal_execution_error(
                    f"Reconciliation for {proposal_id} found a MISMATCHED order ({mismatch_detail}) -- left "
                    "as 'submission_unknown' for manual investigation, not auto-resolved."
                )

            # The order found under our idempotency key may have been REPLACED
            # out of band; the live state then lives on the replacement, which
            # has its own order id. Resolve before journaling, or this manual
            # operation cannot fix the very condition it exists to fix.
            (
                authoritative,
                chain_error,
                is_mismatch,
                chain,
                replacement_order_path,
            ) = deps.authoritative_order_for(
                broker,
                root_order,
                stored_intent,
                proposal=proposal,
                observed_account=observed_account,
            )
            if chain_error is not None:
                reason = (
                    f"Manual reconciliation for {proposal_id} could not trust the replacement chain: "
                    f"{chain_error}. "
                    + ("Persistent kill switch activated; investigate manually."
                       if is_mismatch else "Left retryable as 'submission_unknown'.")
                )
                if is_mismatch:
                    store.park_reconciliation_anomaly_and_halt(
                        proposal_id,
                        expected_statuses=(deps.reconciling,),
                        reason=reason,
                        reconciled_at=reconciled_at,
                        new_status=deps.submission_unknown,
                        details={"path": "manual_replacement_chain"},
                        anomaly_key="manual_replacement_chain_identity_mismatch",
                    )
                else:
                    store.update_proposal_status_if_current(
                        proposal_id,
                        expected_statuses=(deps.reconciling,),
                        new_status=deps.submission_unknown,
                        reconciled_at=reconciled_at,
                        error=reason,
                    )
                raise deps.proposal_execution_error(reason)

            deps.journal_broker_order_update(
                store,
                proposal_id,
                authoritative,
                event_type="manual_reconciliation",
                event_at=reconciled_at,
                clear_error=True,
                extra_updates={"reconciled_at": reconciled_at},
                raw_event={"replacement_chain": list(chain)} if chain else None,
                broker_order_root_id=(
                    replacement_order_path[0]
                    if replacement_order_path
                    else None
                ),
                replacement_order_path=replacement_order_path,
            )
            return authoritative

        if outcome is None:
            if not deps.broker_absence_is_old_enough(
                claimed, now=deps.datetime_type.now(deps.timezone_type.utc)
            ):
                store.update_proposal_status_if_current(
                    proposal_id,
                    expected_statuses=(deps.reconciling,),
                    new_status=deps.submission_unknown,
                    # Restore the ORIGINAL timestamp: this bounce made no
                    # progress, and the grace period is measured from
                    # updated_at. Writing "now" here would push the deadline
                    # out on every attempt, so a user re-clicking Reconcile
                    # inside the window could never let the proposal age
                    # enough to resolve -- and would starve the background
                    # poller too, since it reads the same column.
                    preserve_updated_at=str(claimed.get("_claimed_from_updated_at") or "")
                    or None,
                    reconciled_at=reconciled_at,
                    error=(
                        "Reconciliation found no matching broker order, but the unresolved "
                        "state is too recent for absence to be reliable. The execution "
                        "reservation remains held; retry after the broker-indexing grace period."
                    ),
                )
                raise deps.proposal_execution_error(
                    f"Reconciliation for {proposal_id} found no order, but the broker-indexing "
                    "grace period has not elapsed -- still 'submission_unknown'."
                )
            transitioned = store.mark_submission_failed_and_release(
                proposal_id,
                expected_statuses=(deps.reconciling,),
                reconciled_at=reconciled_at,
                error="Reconciliation: the broker confirms no order exists for this idempotency key.",
            )
            if transitioned is None:
                current = store.get_proposal(proposal_id)
                if current is not None and current.get("broker_order"):
                    return current["broker_order"]
            raise deps.proposal_execution_error(
                f"Reconciliation for {proposal_id}: the broker confirms this order was never accepted -- "
                "marked 'submission_failed'."
            )

        # outcome is _LOOKUP_UNCONFIRMED
        unresolved = store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=(deps.reconciling,),
            new_status=deps.submission_unknown,
            reconciled_at=reconciled_at,
            error="Reconciliation attempted but the broker lookup itself failed -- still unresolved.",
        )
        if unresolved is None:
            current = store.get_proposal(proposal_id)
            if current is not None and current.get("broker_order"):
                return current["broker_order"]
        raise deps.proposal_execution_error(
            f"Reconciliation for {proposal_id} could not confirm the broker's outcome (the lookup itself "
            "failed) -- still 'submission_unknown'. Try again once connectivity is restored."
        )
    except deps.proposal_execution_error:
        raise
    except Exception as exc:
        # Genuinely unexpected: a malformed stored intent, the broker-
        # order journal write failing, an unexpected database error, etc.
        # Never leave the proposal stranded in "reconciling" (unretriable
        # via the normal interface), and never claim "submission_failed"
        # -- that status specifically means the broker CONFIRMED absence,
        # which an unexpected local error never establishes.
        try:
            recovered = store.update_proposal_status_if_current(
                proposal_id,
                expected_statuses=(deps.reconciling,),
                new_status=deps.submission_unknown,
                reconciled_at=deps.datetime_type.now(deps.timezone_type.utc).isoformat(),
                error=f"Unexpected error during reconciliation: {exc}",
            )
            if recovered is None:
                current = store.get_proposal(proposal_id)
                if current is not None and current.get("broker_order"):
                    return current["broker_order"]
        except Exception as write_exc:
            raise RuntimeError(
                f"CRITICAL: reconciliation for {proposal_id} failed unexpectedly ({exc!r}), and recording "
                f"that failure ALSO failed ({write_exc!r}) -- this proposal is likely stranded in "
                "'reconciling'. The broker outcome is NOT known; do not assume success or failure. Manual "
                "database intervention, or recover_stale_reconciliation() once it's old enough, will be "
                "needed."
            ) from exc
        raise deps.proposal_execution_error(
            f"Reconciliation for {proposal_id} failed unexpectedly ({exc}) -- marked 'submission_unknown' "
            "rather than left stranded in 'reconciling'. The broker outcome is not known; retry once the "
            "underlying issue is fixed."
        ) from exc
