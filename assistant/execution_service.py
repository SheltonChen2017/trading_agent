"""User-approved, policy-bound, paper-only proposal execution.

2026-07-27 update (independent Codex review, verified against this code
before acting): closed 5 real gaps between this module's safety promises
and what it actually enforced --
  1. Open-order lookup failing open: a broker order-endpoint error was
     silently treated as "no open orders," which is exactly the state a
     duplicate-order check must NOT trust. Now checks
     current_portfolio.open_orders_available and fails closed.
  2. Earnings blackout was accepted as a parameter but never supplied by
     any caller, so the check in risk/execution_gate.py was always
     skipped. Now fetches it live (data/event_data.py) when the caller
     doesn't override it, same "honestly unavailable, never guessed"
     discipline the rest of this project already uses for missing data.
  3. Same-day proposal regeneration silently no-op'd against a stale row
     (see assistant/proposals.py's _stable_id docstring for the fix).
  4. Proposal claiming was read-then-later-write, not atomic -- two
     concurrent approvals could both pass the initial status check. Now
     uses AssistantStore.claim_proposal()'s single conditional UPDATE.
  5. Price staleness was asserted, not measured: price_timestamp was set
     to "now", so the check compared now against itself and could never
     fail regardless of how stale the actual quote was. Now fetches a
     real quote + its own timestamp via execution.alpaca_broker.get_latest_quote().

2026-07-27 follow-up (second independent review of the above fix, again
verified before acting): found one real regression the first pass
introduced, plus two smaller gaps --
  6. The expiry check ran BEFORE the atomic claim and used an
     unconditional status write, so re-invoking approval on an
     already-executed proposal after its expiry window had passed could
     silently flip its status back to "expired" -- and could race an
     in-flight claim. Fixed: expiry is now folded into the same atomic
     conditional UPDATE as the claim (AssistantStore.claim_proposal()'s
     `not_expired_after`), and the fallback "mark expired" write is
     itself conditioned on the row still being "proposed" at that
     moment, so it can never clobber a terminal/in-flight status.
  7. Missing earnings data silently skipped the blackout check with no
     way to require otherwise. Added TradingPolicy.require_earnings_data
     (default False, preserving the existing "honestly unavailable,
     never guessed" behavior) -- when enabled, a BUY is blocked if
     earnings data can't be resolved; risk-reducing SELLs are exempt.
  8. Only ProposalExecutionError was caught around the validation stage,
     so a genuinely unexpected exception (a bug, a malformed stored
     intent, etc.) left the claimed proposal stranded in "validating"
     forever. Added a catch-all that marks a distinct "validation_failed"
     status and re-raises -- never silently swallowed, never auto-reset
     to "proposed".

2026-07-28 update (independent GPT review, verified against this code
before acting) -- closed the remaining execution-safety gaps:
  9. Submission reconciliation: an exception during broker.submit_*_order
     no longer assumes rejection. Alpaca might have accepted the order
     and only the response was lost (a network timeout, for example) --
     in that case treating it as "submission_failed" would let a later
     retry submit a genuine duplicate real order. Now, on any submission
     exception, this module queries the broker BY THE SAME idempotency
     key (client_order_id) via broker.find_order_by_client_id(). If found,
     the order is journaled in its real broker lifecycle state (acceptance
     is not treated as a fill). If the lookup itself can't confirm either way, the
     proposal is marked "submission_unknown" (a distinct, non-terminal
     status) instead of "submission_failed" -- and AssistantStore.
     recent_executed_intents() now also treats "submitting"/
     "submission_unknown" proposals as live duplicate-order risk, so a
     regenerated proposal for the same ticker/side is blocked until a
     human reconciles the unknown proposal against the actual Alpaca
     account. A "submitting" status is written just before the broker
     call for the same reason -- so even a crash between the call and the
     response leaves a non-terminal, duplicate-blocking status behind
     instead of nothing. A local lifecycle-projection failure AFTER a
     confirmed broker acceptance is also handled separately: the proposal still
     preserves the working broker order (without claiming it filled) with the local
     journaling failure recorded in its `error` field, rather than losing
     the fact that a real order exists.
 10. The kill switch was only enforced by callers reading
     TRADING_ASSISTANT_KILL_SWITCH and passing kill_switch_active=True --
     a caller that forgot to pass it silently bypassed the switch. Now
     this function itself also reads the environment variable and ORs it
     in, so the kill switch is an invariant of the execution service
     itself, not a presentation-layer convention every caller must
     remember to honor.
 11. Market orders (the only order type any built-in proposal generator
     creates) had no protection against a wide bid/ask spread -- the
     existing max_slippage_pct check only fired for limit orders compared
     against their own limit price. broker.get_latest_quote() now returns
     bid/ask separately (not just a collapsed mid), and validate_trade_
     intent() gained a bid/ask spread check (TradingPolicy.max_spread_pct)
     that applies to every order type.
 12. Approved intents with order_type="limit" were always submitted via
     submit_market_order() regardless -- broker-side authorization would
     actually reject the mismatch (the reconstructed intent used inside
     submit_market_order never matches a limit-order authorization's
     fingerprint), so this was a dormant bug rather than a live one (no
     generator in this repo creates limit intents yet), but it made the
     policy's allowed_order_types=["market","limit"] advertise unsupported
     behavior. This module now routes by intent.order_type to the correct
     broker function.

2026-07-29 update (third independent GPT review, verified against this
code before acting) -- closed the remaining gaps in the round-2 fixes:
 13. broker.find_order_by_client_id() used to catch every exception and
     return None, making "the order definitely doesn't exist" (a genuine
     404) indistinguishable from "the lookup itself failed" (network/
     auth/5xx). Now it only returns None on a confirmed HTTP 404 and lets
     any other exception propagate. This module's own submission-error
     handling (and the new reconcile_submission() below) both now use
     _lookup_order_outcome() to get a real three-way answer: found /
     confirmed-absent / unconfirmed -- a confirmed-absent result after a
     submission error now correctly resolves straight to
     "submission_failed" (the broker is telling us it was never
     accepted) instead of the more conservative "submission_unknown".
 14. There was no way to ever resolve a proposal stuck in "submitting"
     or "submission_unknown" -- re-running approval can't help (the
     proposal is no longer "proposed"), so short of hand-editing SQLite
     it could block that ticker/side's duplicate check forever. Added
     reconcile_submission(), exposed as
     `python scripts/run_personal_assistant.py reconcile <proposal_id>`,
     which atomically claims the proposal, re-queries the broker by the
     same idempotency key, cross-checks the returned order's ticker/side
     against the proposal's own intent before trusting it (a mismatch is
     left unresolved rather than silently accepted), and only then
     transitions to a terminal state -- recording `reconciled_at` on
     every outcome as an audit trail.
 15. A limit intent with limit_price=None/0/negative/non-finite could
     pass validate_trade_intent() (only the slippage check, which is
     skipped when limit_price is None, guarded it) and reach
     submit_limit_order(), where it would fail at the broker and could
     land in "submission_unknown" for no good reason. The gate now
     requires a positive, finite limit_price whenever order_type ==
     "limit", and separately rejects non-finite reference prices and
     one-sided/crossed bid-ask quotes instead of silently skipping the
     spread check on them (see risk/execution_gate.py).

2026-07-27 update (fourth independent GPT review, verified against this
code before acting):
 16. Pending (not-yet-filled) BUY orders were invisible to every
     exposure/concentration check (per-position, total, basket,
     leveraged-ETF) -- those only look at portfolio.positions, which a
     pending order doesn't appear in yet. _pending_buy_value_by_ticker()
     below estimates each pending buy's dollar value (from the order's
     own notional/limit_price, falling back to one live quote per
     market-type pending order) and feeds it into validate_trade_intent()
     via the new pending_buy_value_by_ticker parameter (see
     risk/execution_gate.py).

2026-07-27 update (fifth independent GPT review, verified against this
code before acting):
 17. _pending_buy_value_by_ticker()'s live-quote fallback used to catch
     any lookup failure and silently drop that order's value to zero --
     undercounting exposure exactly like fix #16 above was meant to
     prevent, just one step removed. The fallback now lets the exception
     propagate, and this module fails the approval closed (for a BUY
     only -- a risk-reducing sell never consults this value) rather than
     silently proceeding with an undercounted exposure figure.

2026-07-28 update (sixth independent GPT review, verified against this
code before acting):
 18. Approval only compared proposal["policy_version"] to policy.version
     as a plain string -- two policy files (e.g. a hand-edited personal
     one copied from the default) could share the same version yet have
     materially different limits, making them silently interchangeable.
     Now also requires proposal["policy_fingerprint"] (a hash over every
     behavior-affecting policy field, see assistant/policy.py's
     compute_policy_fingerprint()) to match the active policy's CURRENT
     fingerprint -- catches an edited-but-not-rebumped policy file
     regardless of whether version was bumped, and fails closed (rather
     than being grandfathered in) for any proposal that predates
     fingerprint binding entirely.

2026-07-28 feature (user-requested, after confirming scope): a policy
block on a concentration cap (position/total-exposure/basket/leveraged-
ETF) or the earnings blackout window can now be knowingly overridden --
these are risk-preference/business-calendar calls, not data-integrity
problems, and the broker itself would still accept the order. Stale
price, closed market, a bad bid/ask quote, a duplicate order, the kill
switch, insufficient cash, and any invalid intent can NEVER be
overridden, even if they co-occur with an overridable violation --
risk.execution_gate.authorize_overridden_trade_intent() independently
re-verifies this itself rather than trusting the caller. The simplified
confirmation phrase (below) also applies: `confirmation` is just
"approve" now, not "APPROVE <proposal_id>" -- the proposal_id is already
the caller-supplied parameter, so the exact phrase no longer needs to
re-encode which proposal is being approved.

2026-07-28 update (seventh independent GPT review, verified before
acting):
 19. Reconciliation (both the submission-error path below and
     reconcile_submission()) only checked ticker+side before trusting a
     broker order found under the expected idempotency key -- so an
     order under that key for BUY 1 AAPL could reconcile a proposal for
     BUY 100 AAPL, or a market order could be mistaken for a limit
     order. execution.alpaca_broker.find_order_by_client_id() now also
     returns order type, limit price, and time_in_force;
     _order_matches_intent() below compares the COMPLETE material
     identity (ticker, side, shares, order type, limit price for limit
     orders) and fails closed on any missing field -- a mismatch is
     never auto-resolved as a match, and numerically-equivalent share
     counts (e.g. 10 vs 10.0) are treated as equal.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from assistant.execution_kernel.outcomes import (
    _LOOKUP_UNCONFIRMED,
    _authoritative_order_for,
    _broker_absence_is_old_enough,
    _lookup_order_outcome,
    _order_matches_intent,
    resolve_failed_submission,
)
from assistant.execution_kernel.errors import (
    PolicyOverridableBlockError,
    ProposalExecutionError,
    _ProposalClaimLostError,
)
from assistant.execution_kernel.intents import (
    _intent_from_dict,
    _shares_from_stored_value,
)
from assistant.execution_kernel.claim import (
    PRE_BROKER_STRANDED_STATUSES,
    _parse_recovery_timestamp,
    _transition_pre_broker_claim,
    claim_for_execution,
    resolve_kill_switch,
    verify_execution_preconditions,
)
from assistant.execution_kernel.revalidate import (
    _pending_buy_value_by_ticker,
    _resolve_earnings_days_away,
    _review_digest,
    build_reviewed_override_record,
    classify_override_review,
)
from assistant.execution_kernel.submit import (
    _execution_budget_notional,
    journal_accepted_order,
    release_after_telemetry_failure,
    reserve_daily_budget,
    resolve_submission_call,
)
from assistant.execution_kernel.validate import (
    ProposalValidationDeps,
    ProposalValidationOutcome,
    run_proposal_validation,
)
from assistant.execution_kernel.reconcile import (
    ReconciliationDeps,
    run_submission_reconciliation,
)
from assistant.share_reconciliation import detect_split_like_share_mismatch
from assistant.kill_switch import env_kill_switch_active
from assistant.execution_telemetry import (
    FAILURE_DATA_INTEGRITY,
    FAILURE_DETERMINISTIC_POLICY,
    FAILURE_INFRASTRUCTURE,
    FAILURE_NONE,
    execution_attempt_id,
    record_submission_started,
    record_validation_exception,
    record_validation_outcome,
)
from assistant.order_lifecycle import (
    journal_broker_order_update,
    proposal_status_for_order,
)
# MoneyInput/to_decimal, the FAILURE_* constants, and risk.execution_gate's
# TradeIntent/ValidationResult/intent_fingerprint below are no longer called
# on the facade after GR-1C moved the validation body into the kernel -- they
# stay imported because they were importable from this module before GR-1
# began, and the facade's importable surface is a compatibility contract
# (independent review, 2026-08-02: dropping DuplicateIntentConflict during
# GR-1B was rejected on exactly this ground).
from assistant.money import MoneyInput, to_decimal
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.proposal_status import (
    APPROVED,
    BLOCKED,
    IN_FLIGHT_INTENT_STATUSES,
    POLICY_OVERRIDE_AVAILABLE,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
    VALIDATING,
    VALIDATION_FAILED,
)
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore, DuplicateIntentConflict
from risk.execution_gate import (
    TradeIntent,
    ValidationResult,
    authorize_overridden_trade_intent,
    authorize_trade_intent,
    intent_fingerprint,
    validate_trade_intent,
)

# Sentinel: the broker lookup itself failed (network/auth/5xx/etc.), so
# presence or absence of the order still can't be determined. Distinct
# from `None`, which _lookup_order_outcome() reserves for a broker 404.
# Whether that 404 is old enough to count as reliable absence is decided
# separately by the reconciliation grace-period rules.


# ProposalValidationOutcome is defined in assistant/execution_kernel/validate.py
# since GR-1C and re-exported above -- same class object, so isinstance checks
# and `from assistant.execution_service import ProposalValidationOutcome` are
# unaffected.


def _import_execution_broker():
    """Deferred broker import, injected into the validation and
    reconciliation kernels.

    A provider function rather than a module-level import so each kernel can
    run it at the exact point its historical inline
    ``import execution.alpaca_broker`` statement sat -- for validation,
    AFTER the existence/expiry/policy refusals (preserving which error wins
    when the broker package itself cannot import); for reconciliation, first
    inside the try block AFTER the atomic claim (so an unimportable broker
    package still takes the unexpected-error recovery path).
    """
    import execution.alpaca_broker as broker

    return broker


#: Proposal families whose validity depends on the allocation profile as
#: well as the trading policy. Keyed by evidence status so every other family
#: returns from the context check immediately and keeps its prior behavior.
_PROFILE_BOUND_EVIDENCE_STATUSES = frozenset(
    {"user_directed_rebalance_buy", "user_directed_rebalance_trim"}
)


def _validate_proposal_context(proposal: dict) -> str | None:
    """Fail closed when a context-bound proposal outlives that context.

    Most proposal families are fully bound by the trading-policy fingerprint.
    REBAL-1 steering and trimming also depend on the owner's allocation
    profile, which is a separate preference document and therefore needs its
    own execution-time check. The deferred import keeps the generic execution
    kernel independent of the rebalancing feature.

    Stage 3 trims are bound for a stronger reason than Stage 2 buys. A stale
    buy spends money toward a target the owner has since moved; a stale trim
    SELLS toward one, realizing gains for a shape that is no longer the
    stated intent, and no later edit can un-realize them.
    """
    if proposal.get("evidence_status") not in _PROFILE_BOUND_EVIDENCE_STATUSES:
        return None
    expected_impact = proposal.get("expected_impact")
    expected = (
        expected_impact.get("allocation_profile_fingerprint")
        if isinstance(expected_impact, dict)
        else None
    )
    if not expected:
        return (
            "Rebalancing proposal is missing its allocation profile "
            "fingerprint. Regenerate it from Portfolio Rebalancing."
        )
    from assistant.rebalance_profile import (
        OWNER_APPROVED_PROFILE,
        compute_profile_fingerprint,
    )

    current = compute_profile_fingerprint(OWNER_APPROVED_PROFILE)
    if expected != current:
        return (
            "Proposal's allocation profile does not match the active owner "
            "profile. Regenerate it from Portfolio Rebalancing."
        )
    return None


def validate_proposal_for_execution(
    proposal_id: str,
    current_portfolio: PortfolioSnapshot,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    now_et: datetime,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
    proposal: dict | None = None,
    extra_pending_buy_value_by_ticker: dict[str, float] | None = None,
    available_cash_override: float | None = None,
    available_buying_power_override: float | None = None,
    extra_open_order_count: int = 0,
) -> ProposalValidationOutcome:
    """
    Checks, in the same order execute_approved_paper_proposal() always
    has: existence, expiration, policy version/fingerprint, execution
    mode, paper-broker mode/configuration, open-order availability, side/
    order-type/new-position policy rules, quote freshness inputs, pending
    -order exposure, the earnings-data requirement, and finally
    validate_trade_intent() itself. Pass an already-fetched `proposal`
    dict when the caller has just claimed/read one (avoids a redundant
    re-fetch); otherwise it's loaded fresh via store.get_proposal().

    `extra_pending_buy_value_by_ticker`: additional simulated pending-buy
    value to add on top of whatever's derived from
    current_portfolio.open_orders -- lets a caller simulating a SEQUENCE
    of proposals (assistant.allocation_batch's cumulative preflight)
    reserve earlier legs' planned notional against later legs' exposure/
    concentration checks, without this function needing to know anything
    about batches itself. None/empty for the real single-proposal
    execution path (unaffected, backward compatible).

    `available_cash_override`/`available_buying_power_override`: passed
    straight through to validate_trade_intent() (see its docstring) --
    lets the SAME caller tighten cash/buying-power availability to
    reflect earlier reserved legs WITHOUT touching `current_portfolio.
    cash`/`buying_power` themselves, since those two also feed the
    exposure-side arithmetic there and must stay at their real,
    unreserved values to avoid double-counting a reservation (GPT review,
    2026-07-29: passing a `dataclasses.replace()`'d portfolio with cash
    already reduced counted each earlier leg twice -- once via the
    shrunk cash figure, once via `extra_pending_buy_value_by_ticker`).
    None (the default) for both preserves exact single-proposal-execution
    behavior.

    GR-1C: the orchestration body lives in assistant/execution_kernel/
    validate.py's run_proposal_validation(); this wrapper only assembles its
    dependency contract. The ProposalValidationDeps construction below MUST
    stay inside this function body, built from bare names: each bare name is
    resolved from THIS module's namespace at call time, which is precisely
    what keeps a monkeypatch such as
    ``execution_service.validate_trade_intent = stub`` working after the
    move. Hoisting the construction to module scope (or importing the seams
    inside the kernel) would freeze import-time bindings and silently defeat
    every such patch -- tests/test_execution_characterization.py freezes
    each seam against exactly that edit.
    """
    return run_proposal_validation(
        proposal_id,
        current_portfolio,
        policy,
        store,
        now_et=now_et,
        deps=ProposalValidationDeps(
            import_broker=_import_execution_broker,
            outcome_factory=ProposalValidationOutcome,
            datetime_type=datetime,
            timezone_type=timezone,
            decimal_factory=Decimal,
            trade_intent_factory=TradeIntent,
            to_decimal=to_decimal,
            env_kill_switch_active=env_kill_switch_active,
            compute_policy_fingerprint=compute_policy_fingerprint,
            validate_proposal_context=_validate_proposal_context,
            intent_from_dict=_intent_from_dict,
            detect_split_like_share_mismatch=detect_split_like_share_mismatch,
            pending_buy_value_by_ticker=_pending_buy_value_by_ticker,
            resolve_earnings_days_away=_resolve_earnings_days_away,
            validate_trade_intent=validate_trade_intent,
            failure_data_integrity=FAILURE_DATA_INTEGRITY,
            failure_infrastructure=FAILURE_INFRASTRUCTURE,
        ),
        kill_switch_active=kill_switch_active,
        earnings_days_away=earnings_days_away,
        proposal=proposal,
        extra_pending_buy_value_by_ticker=extra_pending_buy_value_by_ticker,
        available_cash_override=available_cash_override,
        available_buying_power_override=available_buying_power_override,
        extra_open_order_count=extra_open_order_count,
    )


def execute_approved_paper_proposal(
    proposal_id: str,
    confirmation: str,
    current_portfolio: PortfolioSnapshot,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    now_et: datetime,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
    override_policy_violations: bool = False,
) -> dict:
    """
    Revalidate and submit one proposal.

    The exact confirmation phrase is "approve" (case-insensitive). This
    is deliberately no longer "APPROVE <proposal_id>": the proposal_id is
    already a separate, caller-supplied parameter, so the confirmation
    phrase doesn't need to re-encode which proposal is being approved --
    that's chosen by which proposal_id the caller passes in, not by what
    gets typed (2026-07-28, user-requested simplification).

    `override_policy_violations`: if the ONLY reason this proposal would
    be blocked is one or more override-eligible violations (concentration
    caps or the earnings blackout -- see risk.execution_gate.
    ValidationResult.overridable_violations), passing True proceeds --
    but ONLY if the CURRENT violations (revalidated fresh against
    `current_portfolio`/live quote, right now) exactly match a
    PREVIOUSLY-STORED reviewed-override record for this proposal (GPT
    review, 2026-07-30: passing True used to be treated as blanket
    permission to accept whatever override-eligible conditions happened
    to exist at the later execution instant, not specifically the ones a
    human actually reviewed -- a position-cap violation could become
    materially more severe, a basket/leveraged-ETF/earnings violation
    could newly appear, or one override-eligible violation could be
    replaced by another, all between an initial PolicyOverridableBlockError
    and a later `override_policy_violations=True` call, with nothing
    checking that the human saw the SAME set before accepting it).

    Concretely: every time this proposal is blocked ONLY by override-
    eligible violations, the service stores a reviewed-override record
    (the trade intent's fingerprint plus canonically-ordered violation
    codes/messages) and raises PolicyOverridableBlockError -- REGARDLESS
    of whether the caller already passed `override_policy_violations=
    True`. Only a SECOND call, with that flag set, whose freshly
    revalidated violations produce the exact same digest as the stored
    record, actually proceeds to authorization. A digest mismatch (first
    presentation, or the reviewed conditions changed) always re-stores
    the new record and raises again -- `PolicyOverridableBlockError.
    conditions_changed` distinguishes "changed since a prior review" from
    "first presentation" for caller messaging. Any non-overridable
    violation (stale price, closed market, a bad quote, a duplicate
    order, the kill switch, insufficient cash, invalid quantities) still
    hard-blocks regardless of any of this -- see
    authorize_overridden_trade_intent()'s docstring.

    Proposals are single-use, short-lived, and currently restricted to
    Alpaca paper accounts regardless of the global broker configuration.
    """
    # PHASE 1-3: admission. Kill switch, then preconditions, then the atomic
    # claim -- in that order, and none of them contacts the broker.
    kill_switch_active = resolve_kill_switch(store, kill_switch_active)
    proposal = verify_execution_preconditions(store, proposal_id, confirmation, policy)
    now_utc = datetime.now(timezone.utc)
    claim_for_execution(store, proposal_id, now_utc)

    import execution.alpaca_broker as broker

    validation = None
    validation_outcome = None
    intent = None
    reference_price = None
    attempt_started_at = now_utc.isoformat()
    attempt_id = execution_attempt_id(proposal_id, attempt_started_at)
    try:
        validation_outcome = validate_proposal_for_execution(
            proposal_id,
            current_portfolio,
            policy,
            store,
            now_et=now_et,
            kill_switch_active=kill_switch_active,
            earnings_days_away=earnings_days_away,
            proposal=proposal,
        )
        record_validation_outcome(
            store,
            attempt_id=attempt_id,
            proposal_id=proposal_id,
            attempted_at=datetime.now(timezone.utc).isoformat(),
            outcome=validation_outcome,
        )
        if validation_outcome.error is not None:
            # Every check up through validate_trade_intent() lives in
            # validate_proposal_for_execution() now (2026-07-29, GPT
            # review) -- shared with preflight_allocation_batch() so the
            # two can never drift again the way they had (preflight was
            # missing several of these checks).
            raise ProposalExecutionError(validation_outcome.error)
        intent = validation_outcome.intent
        validation = validation_outcome.validation
        reference_price = validation_outcome.reference_price
        if not validation.approved:
            if not validation.overridable:
                # At least one violation isn't override-eligible (or there
                # are no violations at all, which shouldn't happen for a
                # rejection) -- this is a hard block regardless of
                # override_policy_violations. `.overridable` is computed
                # fresh from validation.violation_codes (which
                # validation_proof cryptographically binds) against the
                # fixed OVERRIDABLE_VIOLATION_CODES constant -- there is
                # no separate mutable field here to trust or mistrust.
                raise ProposalExecutionError(
                    "Execution gate blocked the proposal: " + "; ".join(validation.violations)
                )
            reviewed_matches, conditions_changed, current_digest = (
                classify_override_review(
                    proposal,
                    intent,
                    validation.violation_codes,
                    validation.violations,
                    override_policy_violations,
                )
            )
            if not reviewed_matches:
                _transition_pre_broker_claim(
                    store,
                    proposal_id,
                    expected_status=VALIDATING,
                    new_status=POLICY_OVERRIDE_AVAILABLE,
                    violations=list(validation.violations),
                    reviewed_override=build_reviewed_override_record(
                        intent,
                        validation.violation_codes,
                        validation.violations,
                        current_digest,
                        now_utc.isoformat(),
                    ),
                )
                raise PolicyOverridableBlockError(
                    "Execution gate blocked this proposal, but every violation is override-eligible "
                    "(a risk-preference or earnings-calendar call, not unreliable data): "
                    + "; ".join(validation.violations),
                    overridable_violations=list(validation.violations),
                    conditions_changed=conditions_changed,
                )
            # override_policy_violations=True, every violation is
            # override-eligible, AND the current violations exactly match
            # what was previously reviewed: fall through to
            # authorize_overridden_trade_intent() below instead of the
            # normal approved path.
    except _ProposalClaimLostError:
        raise
    except PolicyOverridableBlockError:
        raise
    except ProposalExecutionError as exc:
        violations = list(validation.violations) if validation is not None and not validation.approved else [str(exc)]
        _transition_pre_broker_claim(
            store,
            proposal_id,
            expected_status=VALIDATING,
            new_status=BLOCKED,
            violations=violations,
        )
        raise
    except Exception as exc:
        # Something genuinely unexpected (not a validation/policy
        # rejection) -- do not leave the claimed proposal stranded in
        # "validating" forever with no record of why. Distinct status
        # from "blocked" so this is visibly different from an ordinary
        # policy rejection in the History tab / store.
        failure_error = str(exc)
        if validation_outcome is None:
            try:
                record_validation_exception(
                    store,
                    attempt_id=attempt_id,
                    proposal_id=proposal_id,
                    event_at=datetime.now(timezone.utc).isoformat(),
                    error=failure_error,
                )
            except Exception as telemetry_exc:
                failure_error += f"; execution telemetry also failed: {telemetry_exc}"
        _transition_pre_broker_claim(
            store,
            proposal_id,
            expected_status=VALIDATING,
            new_status=VALIDATION_FAILED,
            error=failure_error,
        )
        raise

    if validation.approved:
        authorization = authorize_trade_intent(intent, validation)
        _transition_pre_broker_claim(
            store,
            proposal_id,
            expected_status=VALIDATING,
            new_status=APPROVED,
            approved_at=now_utc.isoformat(),
            violations=[],
        )
    else:
        # Only reachable when override_policy_violations=True and every
        # violation was override-eligible (the branch above already
        # raised for anything else). Audit trail: the overridden
        # violations are recorded on the proposal rather than silently
        # disappearing into an ordinary approval.
        authorization = authorize_overridden_trade_intent(intent, validation)
        _transition_pre_broker_claim(
            store,
            proposal_id,
            expected_status=VALIDATING,
            new_status=APPROVED,
            approved_at=now_utc.isoformat(),
            violations=[],
            policy_override={
                "overridden_violations": list(validation.violations),
                "overridden_at": now_utc.isoformat(),
            },
        )

    # Enter a reconcilable state before the last local operations preceding
    # submission. If the process dies after this write, startup polling can
    # safely prove broker absence instead of leaving an "approved" proposal
    # with a stranded reservation and no recovery path.
    _transition_pre_broker_claim(
        store,
        proposal_id,
        expected_status=APPROVED,
        new_status=SUBMITTING,
    )

    # PHASE 7-9: reserve, choose the dispatch, record the attempt. Order is
    # load-bearing -- see assistant/execution_kernel/submit.py.
    reserve_daily_budget(
        store, proposal_id, intent, reference_price, policy, now_et.date().isoformat()
    )
    submit, submit_kwargs = resolve_submission_call(
        broker,
        store,
        proposal_id,
        intent,
        whole_shares_only=policy.whole_shares_only,
    )
    # Telemetry is part of the execution evidence contract, and this CALL
    # stays on the facade on purpose: tests and tooling monkeypatch
    # execution_service.record_submission_started, and resolving it inside
    # the kernel would silently defeat those patches. Only the failure
    # handling is delegated.
    try:
        record_submission_started(
            store,
            attempt_id=attempt_id,
            proposal_id=proposal_id,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            outcome=validation_outcome,
        )
    except Exception as exc:
        release_after_telemetry_failure(store, proposal_id, exc)
        # Unreachable today -- the helper is NoReturn -- but load-bearing as a
        # guard: if it ever gains a return path, this re-raise still stops
        # execution before the broker-contact line below, instead of letting a
        # telemetry failure fall through to a live order submission.
        raise

    # PHASE 10: the only line in this function that contacts the broker.
    try:
        order = submit(
            intent.ticker,
            intent.shares,
            side=intent.side,
            authorization=authorization,
            idempotency_key=proposal["idempotency_key"],
            **submit_kwargs,
        )
    except Exception as exc:
        # PHASE 11: the submit raised. What that MEANS is the kernel's job --
        # it may or may not have reached the broker, and only a lookup under
        # the same idempotency key can tell us. Never a blind retry.
        return resolve_failed_submission(
            broker, store, proposal_id, proposal["idempotency_key"], intent, exc
        )

    # PHASE 12: the broker accepted it. A local journal failure from here on
    # must never be reported as a submission failure.
    return journal_accepted_order(store, proposal_id, order)


def reconcile_submission(proposal_id: str, store: AssistantStore) -> dict:
    """
    Manually resolve a proposal stuck in "submitting" or
    "submission_unknown" -- the only two states a submission-time
    reconciliation attempt can leave behind when it couldn't confirm the
    broker's outcome. Re-running execute_approved_paper_proposal() cannot
    help here: the proposal is no longer "proposed", so it would just be
    rejected as unclaimable. This is the sole path forward short of
    hand-editing the database.

    Re-queries the broker for the same idempotency key (client_order_id)
    and, since a look-alike order under the right key should never
    legitimately have the wrong ticker/side, cross-checks the result
    against the proposal's own stored intent before trusting it -- a
    mismatch is left unresolved (still "submission_unknown") rather than
    silently journaled, since blindly trusting it could misattribute
    someone else's order.

    Outcomes (every one records `reconciled_at` as an audit trail):
      - Order found and matches the proposal's intent: journaled in the
        broker's actual accepted/partial/filled/terminal state.
      - Order found but does NOT match (ticker/side mismatch -- should
        never happen with unique idempotency keys, but this is exactly
        the kind of anomaly that must not be auto-resolved): stays
        "submission_unknown" with the mismatch recorded; raises.
      - Broker returns HTTP 404 only after the unresolved state has aged past
        the broker-indexing grace period: marked "submission_failed" -- it is
        then old enough to treat absence as reliable. A newer 404 stays
        "submission_unknown" and retains its execution reservation.
      - The lookup itself still can't confirm either way (network/auth/
        etc.): returned to "submission_unknown", unchanged, safe to
        retry again later.
      - Anything genuinely unexpected after the claim (a malformed
        stored intent, the broker-order journal write failing, an
        unexpected database error, ...): falls back to
        "submission_unknown" too (2026-07-28, GPT review) -- previously
        the proposal was left stranded in "reconciling" with no way to
        retry, since only "submitting"/"submission_unknown" are
        re-claimable. Never converted to "submission_failed": that
        status means the broker CONFIRMED absence, which an unexpected
        local error never establishes. If even that recovery write
        itself fails, this raises a distinct RuntimeError rather than
        silently leaving the proposal claimed with no record of why --
        see recover_stale_reconciliation() below for the crash-recovery
        path this can't cover (no in-process handler survives a crash).
    """
    # GR-1D: the orchestration body lives in
    # assistant/execution_kernel/reconcile.py. The dependency bundle is
    # constructed HERE, inside the wrapper, on every call, from bare names --
    # each resolves from this module's namespace at call time, so replacing
    # any of them on the facade (tests, tooling) still reaches the kernel
    # exactly as it did when the body was inline. Hoisting this construction
    # to module scope would silently freeze every seam.
    return run_submission_reconciliation(
        proposal_id,
        store,
        deps=ReconciliationDeps(
            import_broker=_import_execution_broker,
            datetime_type=datetime,
            timezone_type=timezone,
            proposal_execution_error=ProposalExecutionError,
            submitting=SUBMITTING,
            submission_unknown=SUBMISSION_UNKNOWN,
            reconciling=RECONCILING,
            intent_from_dict=_intent_from_dict,
            lookup_order_outcome=_lookup_order_outcome,
            order_matches_intent=_order_matches_intent,
            authoritative_order_for=_authoritative_order_for,
            broker_absence_is_old_enough=_broker_absence_is_old_enough,
            journal_broker_order_update=journal_broker_order_update,
        ),
    )


def recover_stale_reconciliation(
    proposal_id: str, store: AssistantStore, stale_after_seconds: int = 300,
) -> dict:
    """
    Recovers a proposal stranded in "reconciling" after a crash left no
    in-process handler to run reconcile_submission()'s own recovery logic
    (an ordinary exception inside that function already falls back to
    "submission_unknown" itself -- see its docstring; this function only
    matters when the PROCESS died mid-reconciliation, before any handler
    could run at all).

    Only recovers a proposal that has been sitting in "reconciling" since
    before `stale_after_seconds` ago (measured against `updated_at`, which
    every status transition -- including the claim into "reconciling" --
    rewrites) -- a recent claim is presumed to be a genuinely in-flight
    attempt, not stranded, and is left untouched. Uses the same atomic
    conditional-UPDATE pattern as claim_proposal(), so two concurrent
    recovery attempts (or a recovery racing a real in-flight
    reconciliation) can never both "win" (2026-07-28, GPT review).

    Recovers to "submission_unknown" (never "submission_failed" -- a
    stranded local process proves nothing about what the broker actually
    did), leaving the proposal retryable via reconcile_submission().

    The status transition AND the audit metadata (`recovered_at`,
    `error`) are written in ONE atomic conditional UPDATE via
    store.reclaim_stale_status()'s `extra_updates` -- not via a separate,
    later write. A prior version wrote the status here and then called
    update_proposal_status() (unconditional on current status) afterward
    to add the audit fields; in the gap between those two writes, another
    worker could have claimed the newly-retryable proposal, resolved it
    to "executed", and had that second write silently overwrite it back
    to "submission_unknown" (2026-07-29, GPT review).

    `stale_after_seconds` must be a positive int -- a zero or negative
    value makes `cutoff` equal to or later than "now", so a reconciliation
    claimed moments (or never) ago would already compare as older than
    the cutoff, defeating this function's entire concurrency guarantee
    (GPT review, 2026-07-29, independently reproduced: the CLI exposed
    this raw via --stale-after-seconds with no validation at either
    layer). Validated FIRST, before any read or mutation of proposal
    state, so a bad value can never even attempt a reclaim.
    """
    if isinstance(stale_after_seconds, bool) or not isinstance(stale_after_seconds, int) or stale_after_seconds <= 0:
        raise ValueError(
            f"stale_after_seconds must be a positive int, got {stale_after_seconds!r} "
            f"({type(stale_after_seconds).__name__}) -- zero, negative, non-integer, and bool values are "
            "never valid: they would let a genuinely in-flight reconciliation be reclaimed immediately."
        )
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
    recovered_at = datetime.now(timezone.utc).isoformat()
    recovered = store.reclaim_stale_status(
        proposal_id,
        expected_status=RECONCILING,
        new_status=SUBMISSION_UNKNOWN,
        stale_before=cutoff,
        extra_updates={
            "recovered_at": recovered_at,
            "error": (
                f"Recovered from a stale 'reconciling' status (no update for at least "
                f"{stale_after_seconds}s, most likely a process crash mid-reconciliation) -- marked "
                "'submission_unknown' so it can be reconciled again."
            ),
        },
    )
    if recovered is None:
        current = store.get_proposal(proposal_id)
        if current is None:
            raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is not a stale 'reconciling' proposal (status={current['status']!r}) "
            f"-- either it's not in 'reconciling', or it was claimed less than {stale_after_seconds}s ago "
            "and is presumed to be a genuinely in-flight reconciliation, not stranded."
        )
    return recovered


def recover_stale_claim(
    proposal_id: str, store: AssistantStore, stale_after_seconds: int = 900,
) -> dict:
    """
    Releases a proposal stranded in a PRE-BROKER status after a process died
    between claiming it and its next write.

    Why this is needed, and why it did not used to be: an ordinary exception
    during validation is already caught and marked "validation_failed", so this
    only matters when the PROCESS died outright (SIGKILL, power loss, a
    Streamlit restart mid-approval). Such a row used to be a harmless orphan --
    the user simply generated a new proposal.

    It stopped being harmless when claim_proposal() started holding a
    ticker+side slot across IN_FLIGHT_INTENT_STATUSES to close the
    cross-proposal duplicate race (2026-07-30). "validating" and "approved" are
    in that set, so one stranded row silently blocked EVERY future proposal for
    that ticker and side, and nothing could clear it:
    recover_stale_reconciliation() only accepts "reconciling", expiry sweeps
    only touch "proposed", and no CLI command reached it. The only remedy was
    hand-editing SQLite. Found by reviewing the change that caused it.

    Recovers to "validation_failed", not "proposed": the row WAS claimed, and
    silently making it approvable again would erase that a human-initiated
    attempt vanished mid-flight. The user regenerates a fresh proposal, which
    is cheap and re-runs every check against current prices.

    Uses the same stale-guard + single conditional UPDATE as
    recover_stale_reconciliation(), so a recently claimed validation is left
    alone and two concurrent recoveries cannot both win. Staleness is not
    proof that the original worker is dead, however: it may merely be paused.
    Safety therefore also depends on execute_approved_paper_proposal() using
    _transition_pre_broker_claim() for every later transition. If this recovery
    wins, those conditional writes fence the old worker out before any budget
    reservation or broker call.
    """
    if (
        isinstance(stale_after_seconds, bool)
        or not isinstance(stale_after_seconds, int)
        or stale_after_seconds <= 0
    ):
        raise ValueError(
            f"stale_after_seconds must be a positive int, got {stale_after_seconds!r} -- "
            "a zero or negative value would make every claim look stale immediately, "
            "defeating the guard."
        )
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=stale_after_seconds)).isoformat()
    for status in PRE_BROKER_STRANDED_STATUSES:
        recovered = store.reclaim_stale_status(
            proposal_id,
            expected_status=status,
            new_status=VALIDATION_FAILED,
            stale_before=cutoff,
            extra_updates={
                "recovered_at": now.isoformat(),
                "error": (
                    f"Recovered from a stale {status!r} status (no update for at least "
                    f"{stale_after_seconds}s, most likely a process crash before submission). "
                    "No broker order exists for this proposal -- that status is written before "
                    "any broker call. Marked 'validation_failed' so it stops holding this "
                    "ticker/side against new proposals; generate a fresh one."
                ),
            },
        )
        if recovered is not None:
            return recovered

    current = store.get_proposal(proposal_id)
    if current is None:
        raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")

    # An unparseable updated_at reaches the generic message below as "claimed
    # less than Ns ago", which is simply the wrong reason: the staleness guard
    # is a lexical `updated_at < cutoff` comparison in SQL, and a non-timestamp
    # string loses it regardless of age. Recovery genuinely CANNOT proceed --
    # staleness is unprovable, and assuming stale would revoke a live worker's
    # claim, which is exactly the P1 this fencing round closed. But readiness
    # now blocks on such a row, so the operator must at least be told the real
    # reason rather than sent to wait out a window that will never expire.
    if (
        current["status"] in PRE_BROKER_STRANDED_STATUSES
        and _parse_recovery_timestamp(store, proposal_id) is None
    ):
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is in {current['status']!r} but its updated_at is not a "
            "readable timestamp, so its age cannot be proved and recovery cannot safely run "
            "(assuming it is stale would revoke a possibly-live worker's claim). This is a "
            "data-integrity problem, not a timing one: repair the row's updated_at directly, "
            "then re-run this command."
        )
    raise ProposalExecutionError(
        f"Proposal {proposal_id} is not a stale pre-broker claim (status={current['status']!r}) -- "
        f"either it is not in {' / '.join(PRE_BROKER_STRANDED_STATUSES)}, or it was claimed less "
        f"than {stale_after_seconds}s ago and is presumed genuinely in flight. Post-submission "
        "statuses are NOT recoverable this way: use reconcile_submission() or "
        "recover_stale_reconciliation(), which never assume a broker order is absent."
    )
