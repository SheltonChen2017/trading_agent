"""Finite source-only chunk accounting; never a provider dispatch authority.

Every slot permanently spends a START/try and reserves an entire response page.
Only the fixed operational reader's original terminal chunk witness can replace
CURRENT-chunk reservations by authenticated durable charges. No pair receipt,
caller payload, completion flag, callback or individual-ticket refund can do so.
The old research ConservativeCountBudget and all historical debts stay intact.
"""
import _thread
from dataclasses import dataclass, field
from functools import wraps
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_count_recovery_budget as research_budget
import research.short_interest_etf.native_dated_class_reference as references

_EXPECTED_SOURCE_PROFILE = ("b3a8ac9057f8461bd4c450ffc911a5adac8c129ced762e33c5e56660215861e3", 13992, 23452681,
    81876, 84005, 4 * 1024 ** 3, 2 * 1024 ** 2, 67885, 512, 133, 16, 3)
MAXIMUM_COORDINATORS = 1
_BUDGETS, _TICKETS, _LOCKS, _FAILED, _CONSUMED = {}, {}, {}, set(), set()
_SETTLEMENT_MINTS, _SETTLED_VIEWS, _APPEND_ORIGINS = {}, {}, {}
_RLOCK_TYPE = type(_thread.RLock())
_AUTHORITY = (("source_only", True), ("accounting_only", True),
    ("dispatch_authority", False), ("source_admitted", False),
    ("actual_input_execution_admitted", False), ("ready_for_backtest", False),
    ("budget_settlement_is_source_admission", False), ("outcome_looks", 0),
    ("qc_attempts", 0), ("trading_authority", False))
_CODES = frozenset("""durable_budget_policy_changed exact_recovery_plan_required
durable_budget_factory_required durable_budget_already_opened durable_budget_capacity_exhausted
durable_budget_binding_changed durable_budget_permanently_stopped durable_budget_owner_changed
attempt_ticket_factory_required attempt_ticket_binding_changed attempt_ticket_no_longer_active exact_current_chunk_position_required
current_chunk_required current_chunk_START_cap current_chunk_extra_cap lifetime_try_cap
cumulative_START_cap full_page_byte_capacity chunk_reader_required closed_chunk_binding_changed
closed_chunk_already_consumed closed_chunk_partial_roster closed_chunk_charge_changed
closed_chunk_missing_base_position settled_accounting_changed""".split())


class DurableCountBudgetRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise DurableCountBudgetRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is DurableCountBudgetRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str and len(args[0]) <= 256:
            code = next((name for name in _CODES if args[0] == "REFUSED: " + name), None)
    return {"category": "local_contract_refusal" if type(error) is DurableCountBudgetRefusal
        else "unknown_local_error", "errno_name": None, "contract_code": code}


def authority(): return dict(_AUTHORITY)


def _identity_class(cls):
    return cls.__hash__ is object.__hash__ and cls.__eq__ is object.__eq__


def _lock(value):
    require(type(value) is DurableCountBudget and _identity_class(DurableCountBudget),
        "durable_budget_binding_changed")
    original = _LOCKS.get(value) if type(value) is DurableCountBudget else None
    require(type(original) is tuple and len(original) == 2 and original[0] is value
        and type(original[1]) is _RLOCK_TYPE, "durable_budget_binding_changed")
    return original[1]


def _coherent(function):
    """Only the original pinned native RLock surrounds mutable observations."""
    @wraps(function)
    def locked(self, *args, **kwargs):
        with _lock(self): return function(self, *args, **kwargs)
    return locked


def _source_profile():
    return tuple(getattr(research_budget, name) for name in (
        "BASELINE_LEDGER_SHA256", "PRIOR_STARTS", "PRIOR_CHARGED_BYTES",
        "HISTORICAL_START_CEILING", "MAXIMUM_CUMULATIVE_STARTS", "MAXIMUM_CUMULATIVE_BYTES",
        "MAXIMUM_RESPONSE_BYTES", "MISSING_POSITIONS", "POSITIONS_PER_CHUNK", "MAXIMUM_CHUNKS",
        "EXTRA_ATTEMPTS_PER_CHUNK", "MAXIMUM_TOTAL_TRIES_PER_POSITION"))


def policy():
    current = _source_profile()
    require(type(_EXPECTED_SOURCE_PROFILE) is tuple and len(current) == len(_EXPECTED_SOURCE_PROFILE) == 12
        and all(type(value) is type(expected) and value == expected
            for value, expected in zip(current, _EXPECTED_SOURCE_PROFILE))
        and type(MAXIMUM_COORDINATORS) is int and MAXIMUM_COORDINATORS == 1,
        "durable_budget_policy_changed")
    profile = authority()
    require(type(profile) is dict and len(profile) == len(_AUTHORITY)
        and all(type(key) is str for key in profile)
        and all(name in profile and type(profile[name]) is type(value) and profile[name] == value
            for name, value in _AUTHORITY), "durable_budget_policy_changed")
    return {"schema": "si-durable-count-chunk-budget-v1", "research_policy_sha256": hash_payload(research_budget.policy()),
        "baseline_ledger_sha256": current[0], "prior_STARTs": current[1], "prior_charged_bytes": current[2],
        "maximum_cumulative_STARTs": current[4], "maximum_cumulative_bytes": current[5],
        "whole_attempt_reservation_bytes": current[6], "maximum_chunks": current[9],
        "positions_per_chunk": current[8], "extra_attempts_per_chunk": current[10],
        "maximum_LIFETIME_tries_per_position": current[11], "maximum_coordinators": MAXIMUM_COORDINATORS,
        "owner": "one_original_coordinator_same_thread", "START_and_tries": "permanent_append_never_refund",
        "worker_authentication": "original_pinned_RLock_coherent_readonly_ticket_guard_no_reserve_or_settle",
        "settled_accounting": "original_append_issued_account7_only_pure_history_no_old_reader_clock_or_FAILED_veto",
        "release_barrier": "fixed_reader_exact_original_ClosedCountChunk_all_contexts_postclose_audits",
        "unknown_no_body": "full_page_charge_preserved", "individual_ticket_release": False,
        "operative_balance": "original_guarded_plan_profile_known_B3_plus_permanent_negative_exposure_never_settled_or_refunded",
        "chunk_extra_limit": "original_guarded_plan_per_chunk_limit_not_global_default",
        "actual_START_or_HTTP_observation": False, "authority": profile}


@dataclass(frozen=True, slots=True, init=False, eq=False)
class CountAttemptTicket:
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self): raise DurableCountBudgetRefusal("REFUSED: attempt_ticket_factory_required")

    def public_summary(self):
        original = ticket_binding(self)
        return json.loads(original[13])

    @property
    def sha256(self): return ticket_binding(self)[9]

    @property
    def reservation_sha256(self): return ticket_binding(self)[9]


def _ticket_binding(ticket, *, active):
    """Authenticate one exact issued ticket; return original immutable bindings.

    Tuple: ticket,budget,plan,chunk,ordinal,position,matrixordinal,lifetime_try,
    requestSHA,reservationSHA,accountingpolicySHA,pagebytes,budgetidentity,raw.
    This is custody/accounting identity, never source/provider permission.
    """
    original = _TICKETS.get(ticket) if type(ticket) is CountAttemptTicket and _identity_class(CountAttemptTicket) else None
    try:
        require(type(original) is tuple and len(original) == 14 and original[0] is ticket,
            "attempt_ticket_binding_changed")
        with _lock(original[1]):
            require(CountAttemptTicket.__hash__ is object.__hash__ and CountAttemptTicket.__eq__ is object.__eq__
                and object.__getattribute__(ticket, "_anchor") is original
                and object.__getattribute__(ticket, "_identity") is original, "attempt_ticket_binding_changed")
            plan, state = original[1]._guard(owner=False)
            require(original[2] is plan and original[12] is original[1]._anchor[3]
                and any(ticket is issued for issued in state[1]), "attempt_ticket_binding_changed")
            if active:
                require(any(ticket is issued for issued in state[2]) and ticket not in _CONSUMED,
                    "attempt_ticket_no_longer_active")
            return original
    except BaseException:
        if type(original) is tuple: original[1]._latch()
        raise


def ticket_binding(ticket):
    """Historical identity only; it cannot authorize a fresh response creation."""
    return _ticket_binding(ticket, active=False)


def active_ticket_binding(ticket):
    """Current unresolved original roster only; custody must claim it once."""
    return _ticket_binding(ticket, active=True)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class DurableCountBudget:
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)
    _state: tuple = field(repr=False)

    def __init__(self): raise DurableCountBudgetRefusal("REFUSED: durable_budget_factory_required")

    def _latch(self):
        if type(self) is not DurableCountBudget or not _identity_class(DurableCountBudget): return
        original = _LOCKS.get(self)
        if type(original) is tuple and original[0] is self:
            with original[1]: _FAILED.add(self)

    @_coherent
    def _guard(self, *, owner=True):
        original = _BUDGETS.get(self) if type(self) is DurableCountBudget and _identity_class(DurableCountBudget) else None
        try:
            require(DurableCountBudget.__hash__ is object.__hash__ and DurableCountBudget.__eq__ is object.__eq__
                and type(original) is tuple and len(original) == 3 and original[0] is self
                and original[1] is object.__getattribute__(self, "_anchor")
                is object.__getattribute__(self, "_identity")
                and original[2] is object.__getattribute__(self, "_state")
                and original[1][4] is _lock(self), "durable_budget_binding_changed")
            require(self not in _FAILED, "durable_budget_permanently_stopped")
            anchor = original[1]
            require(type(owner) is bool and (not owner or _thread.get_ident() == anchor[2]),
                "durable_budget_owner_changed")
            require(hash_payload(policy()) == anchor[1], "durable_budget_policy_changed")
            anchor[0]._guard()
            return anchor[0], original[2]
        except BaseException:
            self._latch(); raise

    @_coherent
    def current_tickets(self):
        unused, state = self._guard()
        return state[2]

    @property
    @_coherent
    def budget_identity(self):
        self._guard()
        return self._anchor[3]

    @property
    @_coherent
    def plan(self):
        plan, unused = self._guard()
        return plan

    @_coherent
    def public_summary(self):
        plan, state = self._guard()
        profile = plan.budget_profile()
        chunk, tickets, active, settlements, charged = state
        report = {"schema": "si-durable-count-budget-observation-v1", "plan_sha256": plan.sha256,
            "current_chunk": chunk, "closed_chunks": len(settlements),
            "new_START_reservations": len(tickets), "cumulative_START_debits_upper_bound": profile["initial_START_upper_bound"] + len(tickets),
            "new_closed_charged_bytes": charged, "historical_charged_bytes": research_budget.PRIOR_CHARGED_BYTES,
            "outstanding_full_page_bytes": len(active) * research_budget.MAXIMUM_RESPONSE_BYTES,
            "cumulative_charged_plus_reserved_bytes": profile["initial_byte_upper_bound"] + charged
                + len(active) * research_budget.MAXIMUM_RESPONSE_BYTES,
            "settled_tickets": len(tickets) - len(active), "actual_START_or_HTTP_observation": False,
            "authority": authority()}
        if profile["negative_exposure_sha256"] is not None:
            report.update(permanent_unknown_START_upper_debits=profile["permanent_unknown_START_upper_debits"],
                permanent_unknown_byte_debits=profile["permanent_unknown_byte_debits"],
                negative_exposure_sha256=profile["negative_exposure_sha256"])
        return report

    @_coherent
    def reserve_start_slot(self, position):
        """Spend one source-only reservation before any future START publication."""
        try:
            plan, state = self._guard(); profile = plan.budget_profile()
            require(_identity_class(CountAttemptTicket), "attempt_ticket_binding_changed")
            chunk, tickets, active, settlements, charged = state
            require(chunk <= len(plan._parts[3]), "current_chunk_required")
            positions = plan.chunk_positions(chunk)
            require(type(position) is int and position in positions, "exact_current_chunk_position_required")
            prior_tries = plan._parts[4][0]
            tries = prior_tries[position - 1] + sum(_TICKETS[item][5] == position for item in tickets) + 1
            ordinals = plan.chunk_matrix_ordinals(chunk)
            # Derive request identity from the original typed source query. No
            # URL or row enters a ticket/report; no caller descriptor is accepted.
            query_plan = plan._parts[1]._parts[1].query_plan
            matrix_ordinal = ordinals[positions.index(position)]
            selected = references.freeze_native_class_query_plan(query_plan._matrix,
                mode="explicit_anchors", selected_query_ordinals=(matrix_ordinal,))
            request = next(selected.iter_queries()).to_payload()["request_sha256"]
            value = object.__new__(CountAttemptTicket)
            payload = {"schema": "si-count-attempt-reservation-v1", "plan_sha256": plan.sha256,
                "chunk_number": chunk, "reservation_ordinal": len(tickets) + 1,
                "source_position": position, "matrix_query_ordinal": matrix_ordinal,
                "lifetime_try": tries, "request_sha256": request,
                "accounting_policy_sha256": self._anchor[1], "bytes_reserved": research_budget.MAXIMUM_RESPONSE_BYTES,
                "dispatch_authority": False}
            raw = canonical_json(payload).encode()
            parts = (value, self, plan, chunk, len(tickets) + 1, position, matrix_ordinal,
                tries, request, hash_bytes(raw), self._anchor[1], research_budget.MAXIMUM_RESPONSE_BYTES, self._anchor[3], raw)
            updated = (chunk, (*tickets, value), (*active, value), settlements, charged)
            repeats = len(active) - len({_TICKETS[item][5] for item in active})
            extra_limit = plan.chunk_extra_limit(chunk)
            require(len(active) + 1 <= len(positions) + extra_limit, "current_chunk_START_cap")
            require(not any(_TICKETS[item][5] == position for item in active)
                or repeats + 1 <= extra_limit, "current_chunk_extra_cap")
            require(tries <= research_budget.MAXIMUM_TOTAL_TRIES_PER_POSITION, "lifetime_try_cap")
            require(profile["initial_START_upper_bound"] + len(tickets) + 1 <= research_budget.MAXIMUM_CUMULATIVE_STARTS,
                "cumulative_START_cap")
            require(profile["initial_byte_upper_bound"] + charged + (len(active) + 1) * research_budget.MAXIMUM_RESPONSE_BYTES
                <= research_budget.MAXIMUM_CUMULATIVE_BYTES, "full_page_byte_capacity")
            # No I/O, callback, hashing, source access or caller code between
            # these capacity checks and the original append transition.
            object.__setattr__(value, "_anchor", parts); object.__setattr__(value, "_identity", parts)
            _TICKETS[value] = parts
            object.__setattr__(self, "_state", updated); _BUDGETS[self] = self, self._anchor, updated
            return value
        except BaseException:
            self._latch(); raise

    def settle_closed_chunk(self, closed):
        """Consume the fixed reader's original terminal witness exactly once.

        The reader is an independently registered operational boundary, not a
        supplied validator. Its I/O/custody audit runs OUTSIDE the accounting
        lock; no positive implementation is fabricated or minted here. The
        seven immutable bindings include independently resolved positions,
        because an attempted ticket alone never proves source coverage.
        """
        try:
            with _lock(self):
                plan, before = self._guard()
            try:
                from scripts import short_interest_closed_count_chunk as reader
            except ImportError:
                raise DurableCountBudgetRefusal("REFUSED: chunk_reader_required") from None
            require(type(closed) is reader.ClosedCountChunk, "chunk_reader_required")
            account = reader.closed_count_chunk_accounting(closed)
            # Reentrant changes or worker-visible state must never be adopted
            # from the validation interval. Only the original coordinator
            # owner may perform this final, callback-free pure transition.
            with _lock(self):
                current_plan, state = self._guard()
                profile = current_plan.budget_profile()
                require(_identity_class(CountAttemptTicket), "attempt_ticket_binding_changed")
                require(current_plan is plan and state is before, "closed_chunk_binding_changed")
                chunk, tickets, active, settlements, charged = state
                require(type(account) is tuple and len(account) == 7
                    and account[0] is self._anchor[3] and account[1] is plan
                    and type(account[2]) is int and account[2] == chunk,
                    "closed_chunk_binding_changed")
                roster, charges, covered, digest = account[3:]
                require(type(roster) is tuple and len(roster) == len(active) > 0
                    and all(original is supplied for original, supplied in zip(active, roster)),
                    "closed_chunk_partial_roster")
                require(type(charges) is tuple and len(charges) == len(roster)
                    and all(type(charge) is int and 1 <= charge <= research_budget.MAXIMUM_RESPONSE_BYTES
                        for charge in charges), "closed_chunk_charge_changed")
                require(chunk <= len(plan._parts[3]) and type(covered) is tuple
                    and all(type(position) is int for position in covered)
                    and covered == plan.chunk_positions(chunk)
                    and {_TICKETS[ticket][5] for ticket in roster} == set(covered),
                    "closed_chunk_missing_base_position")
                require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                    "closed_chunk_binding_changed")
                require(not any(item[0] is closed or item[1] == digest for item in settlements)
                    and not any(ticket in _CONSUMED for ticket in roster), "closed_chunk_already_consumed")
                total = sum(charges)
                history = settled_chunk_accounting(self)
                record = closed, digest, roster, charges, account
                issuance = self, self._anchor, record, account, object()
                minted = (*_SETTLEMENT_MINTS[self][2], issuance)
                view = self, self._anchor[3], plan, (*history[3], account)
                updated = (chunk + 1, tickets, (), (*settlements, record), charged + total)
                require(total <= len(active) * research_budget.MAXIMUM_RESPONSE_BYTES
                    and profile["initial_byte_upper_bound"] + charged + total <= research_budget.MAXIMUM_CUMULATIVE_BYTES,
                    "closed_chunk_charge_changed")
                # No reader/caller I/O, callback, hash, source access or partial
                # ticket release occurs in this original locked append.
                _CONSUMED.update(roster)
                object.__setattr__(self, "_state", updated); _BUDGETS[self] = self, self._anchor, updated
                _SETTLEMENT_MINTS[self] = self, self._anchor, minted, view
                _SETTLED_VIEWS[self] = view
                _APPEND_ORIGINS[issuance[4]] = self, self._anchor, record, issuance, account
                return {"settled_chunk": chunk, "settled_attempts": len(roster), "new_charged_bytes": total,
                    "next_chunk": chunk + 1, "dispatch_authority": False}
        except BaseException:
            self._latch(); raise


def open_durable_count_budget(plan):
    require(_identity_class(DurableCountBudget) and _identity_class(CountAttemptTicket), "durable_budget_binding_changed")
    require(type(plan) is research_budget.CountRecoveryPlan, "exact_recovery_plan_required")
    plan._guard(); scope = hash_payload(policy())
    require(not any(original[1][0] is plan for original in _BUDGETS.values()), "durable_budget_already_opened")
    require(len(_BUDGETS) < MAXIMUM_COORDINATORS, "durable_budget_capacity_exhausted")
    value = object.__new__(DurableCountBudget)
    lock = _thread.RLock()
    anchor = plan, scope, _thread.get_ident(), object(), lock
    state = 1, (), (), (), 0
    object.__setattr__(value, "_anchor", anchor); object.__setattr__(value, "_identity", anchor)
    object.__setattr__(value, "_state", state); _LOCKS[value] = value, lock
    _BUDGETS[value] = value, anchor, state
    view = value, anchor[3], plan, ()
    _SETTLEMENT_MINTS[value] = value, anchor, (), view
    _SETTLED_VIEWS[value] = view
    value._guard(); return value


def settled_chunk_accounting(budget):
    """Return the ORIGINAL4 journal, independent of expired operational readers.

    A later chunk's refusal does not erase already appended accounting. Only
    the normal FAILED veto and owner-thread restriction are absent here;
    original lock/state/plan/profile and each append-issued identity/nonce
    remain mandatory. No reader, source filesystem, clock or callback runs.
    """
    with _lock(budget):
        require(_identity_class(CountAttemptTicket), "attempt_ticket_binding_changed")
        original = _BUDGETS.get(budget) if type(budget) is DurableCountBudget else None
        require(type(original) is tuple and len(original) == 3 and original[0] is budget
            and original[1] is object.__getattribute__(budget, "_anchor")
            is object.__getattribute__(budget, "_identity")
            and original[2] is object.__getattribute__(budget, "_state")
            and original[1][4] is _lock(budget), "settled_accounting_changed")
        anchor, state = original[1:]
        require(hash_payload(policy()) == anchor[1], "durable_budget_policy_changed")
        plan = anchor[0]; plan._guard()  # Original pure model, never a closed source/reader lease.
        minted, view = _SETTLEMENT_MINTS.get(budget), _SETTLED_VIEWS.get(budget)
        require(type(minted) is tuple and len(minted) == 4 and minted[0] is budget and minted[1] is anchor
            and type(minted[2]) is tuple and minted[3] is view, "settled_accounting_changed")
        require(type(state) is tuple and len(state) == 5 and type(state[3]) is tuple
            and type(view) is tuple and len(view) == 4 and view[0] is budget
            and view[1] is anchor[3] and view[2] is plan and type(view[3]) is tuple
            and len(state[3]) == len(minted[2]) == len(view[3]), "settled_accounting_changed")
        flattened, charges = [], 0
        for number, (record, issuance, account) in enumerate(zip(state[3], minted[2], view[3]), 1):
            require(type(record) is tuple and len(record) == 5 and type(issuance) is tuple and len(issuance) == 5
                and issuance[0] is budget and issuance[1] is anchor and issuance[2] is record
                and issuance[3] is account is record[4] and type(issuance[4]) is object,
                "settled_accounting_changed")
            nonce_origin = _APPEND_ORIGINS.get(issuance[4])
            require(type(nonce_origin) is tuple and len(nonce_origin) == 5
                and nonce_origin[0] is budget and nonce_origin[1] is anchor and nonce_origin[2] is record
                and nonce_origin[3] is issuance and nonce_origin[4] is account, "settled_accounting_changed")
            require(type(account) is tuple and len(account) == 7 and account[0] is anchor[3] and account[1] is plan
                and type(account[2]) is int and account[2] == number
                and account[3] is record[2] and account[4] is record[3] and account[6] == record[1]
                and type(account[3]) is tuple and type(account[4]) is tuple
                and len(account[3]) == len(account[4]) > 0
                and all(type(value) is int and 1 <= value <= research_budget.MAXIMUM_RESPONSE_BYTES for value in account[4])
                and type(account[5]) is tuple and all(type(position) is int for position in account[5])
                and account[5] == plan.chunk_positions(number), "settled_accounting_changed")
            for ticket in account[3]:
                parts = _TICKETS.get(ticket) if type(ticket) is CountAttemptTicket and _identity_class(CountAttemptTicket) else None
                require(type(parts) is tuple and len(parts) == 14 and parts[0] is ticket
                    and ticket._anchor is ticket._identity is parts and parts[1] is budget and parts[2] is plan
                    and parts[3] == number and parts[12] is anchor[3], "settled_accounting_changed")
                flattened.append(ticket)
            charges += sum(account[4])
        require(type(state[0]) is int and state[0] == len(state[3]) + 1
            and type(state[1]) is tuple and type(state[2]) is tuple and type(state[4]) is int and state[4] == charges
            and len(state[1]) == len(flattened) + len(state[2])
            and all(actual is expected for actual, expected in zip(state[1], (*flattened, *state[2]))),
            "settled_accounting_changed")
        return view
