"""Prospective count recovery plan and conservative, NON-dispatch accounting.

The old four-epoch ledger/claims remain unchanged. No receipt-durability
adapter exists here: every reserved slot keeps its entire page permanently.
No operation releases bytes, observes a real START, proves chunk closure or
authorizes HTTP. A later authenticated adapter is required before dispatch.
The mutable coordinator is single-caller only, with no callbacks or I/O in
its check-and-append transition; it is not a concurrent worker/service API.
"""
from dataclasses import dataclass, field
import json

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_count_epoch_ledger as historical

BASELINE_LEDGER_SHA256 = "b3a8ac9057f8461bd4c450ffc911a5adac8c129ced762e33c5e56660215861e3"
PRIOR_STARTS, PRIOR_CHARGED_BYTES = 13_992, 23_452_681
HISTORICAL_START_CEILING, MAXIMUM_CUMULATIVE_STARTS = 81_876, 84_005
MAXIMUM_CUMULATIVE_BYTES, MAXIMUM_RESPONSE_BYTES = 4 * 1024 ** 3, 2 * 1024 ** 2
MISSING_POSITIONS, POSITIONS_PER_CHUNK, MAXIMUM_CHUNKS = 67_885, 512, 133
EXTRA_ATTEMPTS_PER_CHUNK, MAXIMUM_TOTAL_TRIES_PER_POSITION = 16, 3
MAXIMUM_PLANS, MAXIMUM_COORDINATORS = 4, 4
_PLAN_MINTS, _BUDGET_MINTS, _PLAN_KEYS = {}, {}, set()
_AUTHORITY = (("source_only", True), ("accounting_only", True), ("dispatch_authority", False),
    ("source_admitted", False), ("denominator_admitted", False), ("historical_PIT_admitted", False),
    ("actual_input_execution_admitted", False), ("ready_for_backtest", False), ("trading_authority", False),
    ("durable_receipt_verified", False), ("outcome_looks", 0), ("qc_attempts", 0))
_CODES = frozenset("""source_only_policy_changed exact_policy_bounds_required exact_historical_ledger_required baseline_ledger_changed
baseline_accounting_changed missing_position_plan_changed prospective_START_allowance_changed
plan_factory_required sealed_plan_changed plan_scope_changed finite_plan_capacity_exhausted
baseline_plan_already_minted exact_chunk_number_required coordinator_factory_required
sealed_coordinator_changed coordinator_permanently_stopped finite_coordinator_capacity_exhausted
plan_coordinator_already_minted exact_missing_position_required chunk_START_allowance_exhausted
chunk_extra_allowance_exhausted total_try_allowance_exhausted cumulative_START_allowance_exhausted
full_page_byte_capacity_exhausted""".split())


class CountRecoveryBudgetRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise CountRecoveryBudgetRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is CountRecoveryBudgetRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str and len(args[0]) <= 256:
            code = next((name for name in _CODES if args[0] == "REFUSED: " + name), None)
    return {"category": "local_contract_refusal" if type(error) is CountRecoveryBudgetRefusal else
        "unknown_local_error", "errno_name": None, "contract_code": code}


def authority(): return dict(_AUTHORITY)


def policy():
    require(all(type(value) is int and 0 < value <= 2 ** 63 for value in (PRIOR_STARTS, PRIOR_CHARGED_BYTES,
        HISTORICAL_START_CEILING, MAXIMUM_CUMULATIVE_STARTS, MAXIMUM_CUMULATIVE_BYTES, MAXIMUM_RESPONSE_BYTES,
        MISSING_POSITIONS, POSITIONS_PER_CHUNK, MAXIMUM_CHUNKS, EXTRA_ATTEMPTS_PER_CHUNK,
        MAXIMUM_TOTAL_TRIES_PER_POSITION)) and all(type(value) is int and 0 <= value <= 4
        for value in (MAXIMUM_PLANS, MAXIMUM_COORDINATORS)) and PRIOR_STARTS <= HISTORICAL_START_CEILING
        < MAXIMUM_CUMULATIVE_STARTS <= 84_005 and PRIOR_CHARGED_BYTES <= MAXIMUM_CUMULATIVE_BYTES <= 4 * 1024 ** 3
        and POSITIONS_PER_CHUNK <= 512 and EXTRA_ATTEMPTS_PER_CHUNK <= 16 and MAXIMUM_CHUNKS <= 133
        and MAXIMUM_TOTAL_TRIES_PER_POSITION <= 3 and MAXIMUM_RESPONSE_BYTES == 2 * 1024 ** 2,
        "exact_policy_bounds_required")
    profile = authority()
    require(type(profile) is dict and set(profile) == {name for name, unused in _AUTHORITY}
        and all(type(profile[name]) is type(value) and profile[name] == value for name, value in _AUTHORITY),
        "source_only_policy_changed")
    return {"schema": "si-prospective-count-recovery-budget-v1", "owner_authority": "SI-AUTH-20261025-01",
        "owner_decision": "SI-DEC-20261025-06", "baseline_ledger_sha256": BASELINE_LEDGER_SHA256,
        "prior_STARTs": PRIOR_STARTS, "prior_charged_bytes": PRIOR_CHARGED_BYTES,
        "historical_START_ceiling_unchanged": HISTORICAL_START_CEILING,
        "prospective_cumulative_START_ceiling": MAXIMUM_CUMULATIVE_STARTS,
        "maximum_cumulative_bytes": MAXIMUM_CUMULATIVE_BYTES, "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
        "missing_positions": MISSING_POSITIONS, "positions_per_chunk": POSITIONS_PER_CHUNK,
        "maximum_chunks": MAXIMUM_CHUNKS, "extra_attempts_per_chunk": EXTRA_ATTEMPTS_PER_CHUNK,
        "maximum_total_tries_per_position": MAXIMUM_TOTAL_TRIES_PER_POSITION,
        "historical_attempts_count_toward_tries": True, "reservation_releases_supported": False,
        "actual_START_or_HTTP_observation": False, "single_coordinator_required": True,
        "live_custody_adapter_required_before_dispatch": True,
        "maximum_process_plans": MAXIMUM_PLANS, "maximum_process_coordinators": MAXIMUM_COORDINATORS,
        "authority": profile}


@dataclass(frozen=True, slots=True, init=False, eq=False)
class CountRecoveryPlan:
    _parts: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self): raise CountRecoveryBudgetRefusal("REFUSED: plan_factory_required")

    def _guard(self):
        minted = _PLAN_MINTS.get(id(self)) if type(self) is CountRecoveryPlan else None
        try: parts, identity = object.__getattribute__(self, "_parts"), object.__getattribute__(self, "_identity")
        except AttributeError: parts, identity = None, object()
        require(type(parts) is tuple and len(parts) == 8 and parts is identity and minted is parts
            and parts[0] is self, "sealed_plan_changed")
        parts[1]._guard()
        require(parts[6] == hash_payload(policy()) and hash_bytes(parts[5]) == parts[7], "plan_scope_changed")

    @property
    def sha256(self): self._guard(); return self._parts[7]

    def public_summary(self): self._guard(); return json.loads(self._parts[5])

    def chunk_positions(self, chunk_number):
        self._guard()
        require(type(chunk_number) is int and 1 <= chunk_number <= len(self._parts[3]),
            "exact_chunk_number_required")
        return self._parts[3][chunk_number - 1]

    def chunk_matrix_ordinals(self, chunk_number):
        positions = self.chunk_positions(chunk_number)
        selected = self._parts[1]._parts[1].query_plan.to_payload()["selected_query_ordinals"]
        return tuple(selected[position - 1] for position in positions)


def freeze_count_recovery_plan(ledger):
    policy()
    require(type(ledger) is historical.CountEpochLedger, "exact_historical_ledger_required")
    ledger._guard(); require(ledger.sha256 == BASELINE_LEDGER_SHA256, "baseline_ledger_changed")
    old = ledger.public_summary()
    require(all(type(old.get(name)) is int and old[name] == expected for name, expected in (
        ("START_debits", PRIOR_STARTS), ("charged_response_bytes", PRIOR_CHARGED_BYTES),
        ("maximum_historical_STARTs", HISTORICAL_START_CEILING), ("maximum_historical_bytes", MAXIMUM_CUMULATIVE_BYTES))),
        "baseline_accounting_changed")
    selected, unused = historical._source_positions(ledger._parts[1])
    retained = frozenset(ledger._parts[6])
    missing = tuple(position for position in range(1, len(selected) + 1) if position not in retained)
    chunks = tuple(missing[offset:offset + POSITIONS_PER_CHUNK] for offset in range(0, len(missing), POSITIONS_PER_CHUNK))
    require(len(missing) == MISSING_POSITIONS and len(chunks) == MAXIMUM_CHUNKS
        and old["missing_transport_observation_positions"] == len(missing), "missing_position_plan_changed")
    tries, position_chunks = [0] * len(selected), [0] * len(selected)
    for epoch in ledger._parts[2]:
        for position in epoch._parts[5]: tries[position - 1] += 1
    for number, chunk in enumerate(chunks, 1):
        for position in chunk: position_chunks[position - 1] = number
    require(PRIOR_STARTS + len(missing) + len(chunks) * EXTRA_ATTEMPTS_PER_CHUNK == MAXIMUM_CUMULATIVE_STARTS,
        "prospective_START_allowance_changed")
    scope = hash_payload(policy()); key = ledger.sha256, scope
    require(key not in _PLAN_KEYS, "baseline_plan_already_minted")
    require(len(_PLAN_MINTS) < MAXIMUM_PLANS, "finite_plan_capacity_exhausted")
    report = {"schema": "si-prospective-count-recovery-plan-v1", "policy_sha256": scope,
        "baseline_ledger_sha256": ledger.sha256, "missing_position_plan_sha256": hash_payload(missing),
        "chunks_sha256": hash_payload(chunks), "missing_positions": len(missing), "chunks": len(chunks),
        "full_chunks": sum(len(chunk) == POSITIONS_PER_CHUNK for chunk in chunks),
        "final_chunk_positions": len(chunks[-1]), "final_chunk_maximum_slots": len(chunks[-1]) + EXTRA_ATTEMPTS_PER_CHUNK,
        "maximum_new_slots": MAXIMUM_CUMULATIVE_STARTS - PRIOR_STARTS,
        "maximum_extra_slots": len(chunks) * EXTRA_ATTEMPTS_PER_CHUNK,
        "unchanged_remaining_bytes": MAXIMUM_CUMULATIVE_BYTES - PRIOR_CHARGED_BYTES,
        "maximum_cumulative_STARTs": MAXIMUM_CUMULATIVE_STARTS, "historical_ledger_rewritten": False,
        "positive_closed_chunks": 0, "authority": authority()}
    raw = canonical_json(report).encode(); value = object.__new__(CountRecoveryPlan)
    parts = value, ledger, missing, chunks, (tuple(tries), tuple(position_chunks)), raw, scope, hash_bytes(raw)
    object.__setattr__(value, "_parts", parts); object.__setattr__(value, "_identity", parts)
    _PLAN_MINTS[id(value)] = parts; _PLAN_KEYS.add(key); value._guard(); return value


@dataclass(frozen=True, slots=True, init=False, eq=False)
class ConservativeCountBudget:
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)
    _state: tuple = field(repr=False)

    def __init__(self): raise CountRecoveryBudgetRefusal("REFUSED: coordinator_factory_required")

    def _latch(self):
        original = _BUDGET_MINTS.get(id(self))
        if type(original) is tuple and len(original) == 4 and original[0] is self:
            _BUDGET_MINTS[id(self)] = (*original[:3], True)

    def _guard(self):
        original = _BUDGET_MINTS.get(id(self)) if type(self) is ConservativeCountBudget else None
        try:
            try:
                anchor, identity, state = (object.__getattribute__(self, name) for name in ("_anchor", "_identity", "_state"))
            except AttributeError:
                raise CountRecoveryBudgetRefusal("REFUSED: sealed_coordinator_changed") from None
            require(type(original) is tuple and len(original) == 4 and original[0] is self
                and original[1] is anchor is identity and type(anchor) is tuple and len(anchor) == 2
                and original[2] is state and type(state) is tuple, "sealed_coordinator_changed")
            require(original[3] is False, "coordinator_permanently_stopped")
            anchor[0]._guard(); return anchor[0], state
        except BaseException:
            self._latch(); raise

    def public_summary(self):
        unused, rows = self._guard()
        return {"reserved_START_upper_bound": len(rows), "full_page_bytes_reserved": len(rows) * MAXIMUM_RESPONSE_BYTES,
            "cumulative_START_upper_bound": PRIOR_STARTS + len(rows),
            "cumulative_bytes_reserved_upper_bound": PRIOR_CHARGED_BYTES + len(rows) * MAXIMUM_RESPONSE_BYTES,
            "actual_STARTs_observed": 0, "receipt_durability_adapter_present": False,
            "reservation_journal_sha256": hash_payload(rows), "authority": authority()}

    def reserve_start_slot(self, position):
        """Append one non-releasable slot; NOT an operational START permit."""
        try:
            plan, rows = self._guard()
            prior_tries, position_chunks = plan._parts[4]
            require(type(position) is int and 1 <= position <= len(prior_tries)
                and position_chunks[position - 1] > 0, "exact_missing_position_required")
            chunk = position_chunks[position - 1]
            same_chunk = tuple(row for row in rows if row[0] == chunk)
            require(len(same_chunk) < len(plan._parts[3][chunk - 1]) + EXTRA_ATTEMPTS_PER_CHUNK,
                "chunk_START_allowance_exhausted")
            repeats = len(same_chunk) - len({row[1] for row in same_chunk})
            if any(row[1] == position for row in same_chunk):
                require(repeats < EXTRA_ATTEMPTS_PER_CHUNK, "chunk_extra_allowance_exhausted")
            tries = prior_tries[position - 1] + sum(row[1] == position for row in rows) + 1
            require(tries <= MAXIMUM_TOTAL_TRIES_PER_POSITION, "total_try_allowance_exhausted")
            require(PRIOR_STARTS + len(rows) + 1 <= MAXIMUM_CUMULATIVE_STARTS,
                "cumulative_START_allowance_exhausted")
            require(PRIOR_CHARGED_BYTES + (len(rows) + 1) * MAXIMUM_RESPONSE_BYTES <= MAXIMUM_CUMULATIVE_BYTES,
                "full_page_byte_capacity_exhausted")
            # No I/O or caller callback separates capacity checks and append.
            updated = (*rows, (chunk, position, tries))
            object.__setattr__(self, "_state", updated)
            _BUDGET_MINTS[id(self)] = self, self._anchor, updated, False
            return {"reservation_ordinal": len(updated), "chunk_number": chunk, "try_number": tries,
                "bytes_reserved": MAXIMUM_RESPONSE_BYTES, "dispatch_authority": False}
        except BaseException:
            self._latch(); raise


def open_conservative_count_budget(plan):
    require(type(plan) is CountRecoveryPlan, "sealed_plan_changed"); plan._guard()
    require(not any(entry[1][0] is plan for entry in _BUDGET_MINTS.values()), "plan_coordinator_already_minted")
    require(len(_BUDGET_MINTS) < MAXIMUM_COORDINATORS, "finite_coordinator_capacity_exhausted")
    value = object.__new__(ConservativeCountBudget); anchor, state = (plan, plan.sha256), ()
    object.__setattr__(value, "_anchor", anchor); object.__setattr__(value, "_identity", anchor)
    object.__setattr__(value, "_state", state); _BUDGET_MINTS[id(value)] = value, anchor, state, False
    value._guard(); return value
