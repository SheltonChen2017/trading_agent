"""Pure permanent negative allocation; no historical counts or dispatch proof.

The genuine four-epoch B3 ledger is unchanged. This separate allocation charges
eight whole pages and one possible prior try to each of its first eight missing
positions. A separately authenticated operational forensic witness is still
required: this pure factory cannot release SourceAUTH or resolve the old run.
"""
from dataclasses import dataclass, field
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_count_epoch_ledger as historical

POLICY_SHA256 = "e7c5c99e7c05ae61167f1a2eb2f789504219ce0ea4e2aa11287aace7248c7cd3"
BASELINE_LEDGER_SHA256 = "b3a8ac9057f8461bd4c450ffc911a5adac8c129ced762e33c5e56660215861e3"
OWNER_AUTHORITY, OWNER_DECISION = "SI-AUTH-20261028-02", "SI-DEC-20261028-01"
RUN_HEAD = "e7567635cea6e921d6cecef15e67517a1689c5f6"
RUN_PLAN_SHA256 = "2aa15b2fae72b6421a75702ea961af530a3b0901de342f670c21e1caaa328cd0"
PRIOR_STARTS, PRIOR_CHARGED_BYTES, HISTORICAL_START_CEILING = 13992, 23452681, 81876
MAXIMUM_STARTS, MAXIMUM_BYTES, PAGE_BYTES = 84005, 4 * 1024 ** 3, 2 * 1024 ** 2
MISSING_POSITIONS, POSITIONS_PER_CHUNK, CHUNKS = 67885, 512, 133
EXPOSURE_SLOTS, FIRST_CHUNK_FUTURE_EXTRAS, LATER_CHUNK_FUTURE_EXTRAS = 8, 8, 16
MAXIMUM_LIFETIME_TRIES, MAXIMUM_EXPOSURES = 3, 1
_EXPECTED_PROFILE = (13992, 23452681, 81876, 84005, 4294967296, 2097152,
    67885, 512, 133, 8, 8, 16, 3, 1)
_MINTS, _KEYS, _FAILED = {}, set(), set()
_AUTHORITY = (("negative_allocation_only", True), ("dispatch_authority", False),
    ("SourceAUTH_release", False), ("historical_actuals_certified", False),
    ("positive_chunk_admission", False), ("source_admitted", False), ("denominator_admitted", False),
    ("historical_PIT_admitted", False), ("actual_input_execution_admitted", False),
    ("budget_release_authority", False), ("refund_authority", False), ("old_claim_reuse_authority", False),
    ("ready_for_backtest", False), ("trading_authority", False), ("outcome_looks", 0), ("qc_attempts", 0))
_CODES = frozenset("""run13448_profile_changed run13448_authority_changed run13448_policy_unregistered
run13448_exact_ledger_required run13448_baseline_changed run13448_baseline_accounting_changed
run13448_missing_scope_changed run13448_prior_tries_changed run13448_required_future_try_unavailable
run13448_allocation_already_minted run13448_allocation_capacity run13448_factory_required
run13448_allocation_changed run13448_allocation_permanently_stopped run13448_exact_position_required
run13448_exact_chunk_required""".split())


class Run13448ExposureRefusal(ValueError): pass


def require(value, code):
    if not value: raise Run13448ExposureRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is Run13448ExposureRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((value for value in _CODES if args[0] == "REFUSED: " + value), None)
    return {"category": "local_contract_refusal" if code is not None else "unknown_local_error",
        "contract_code": code, "errno_name": None}


def authority(): return dict(_AUTHORITY)


def _profile():
    return (PRIOR_STARTS, PRIOR_CHARGED_BYTES, HISTORICAL_START_CEILING, MAXIMUM_STARTS, MAXIMUM_BYTES,
        PAGE_BYTES, MISSING_POSITIONS, POSITIONS_PER_CHUNK, CHUNKS, EXPOSURE_SLOTS,
        FIRST_CHUNK_FUTURE_EXTRAS, LATER_CHUNK_FUTURE_EXTRAS, MAXIMUM_LIFETIME_TRIES, MAXIMUM_EXPOSURES)


def policy():
    values = _profile()
    require(type(_EXPECTED_PROFILE) is tuple and len(values) == len(_EXPECTED_PROFILE)
        and all(type(value) is int and type(expected) is int and value == expected
            for value, expected in zip(values, _EXPECTED_PROFILE)), "run13448_profile_changed")
    require(type(BASELINE_LEDGER_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", BASELINE_LEDGER_SHA256)
        and (OWNER_AUTHORITY, OWNER_DECISION, RUN_HEAD, RUN_PLAN_SHA256) == (
            "SI-AUTH-20261028-02", "SI-DEC-20261028-01", "e7567635cea6e921d6cecef15e67517a1689c5f6",
            "2aa15b2fae72b6421a75702ea961af530a3b0901de342f670c21e1caaa328cd0")
        and historical.MAXIMUM_CUMULATIVE_STARTS == HISTORICAL_START_CEILING
        and historical.MAXIMUM_CUMULATIVE_BYTES == MAXIMUM_BYTES
        and EXPOSURE_SLOTS <= POSITIONS_PER_CHUNK and MAXIMUM_LIFETIME_TRIES == 3
        and PAGE_BYTES == 2097152 and MAXIMUM_EXPOSURES == 1
        and PRIOR_STARTS + EXPOSURE_SLOTS + MISSING_POSITIONS + FIRST_CHUNK_FUTURE_EXTRAS
            + (CHUNKS - 1) * LATER_CHUNK_FUTURE_EXTRAS == MAXIMUM_STARTS
        and PRIOR_CHARGED_BYTES + EXPOSURE_SLOTS * PAGE_BYTES < MAXIMUM_BYTES,
        "run13448_profile_changed")
    profile = authority()
    require(type(profile) is dict and set(profile) == {name for name, unused in _AUTHORITY}
        and all(type(profile[name]) is type(value) and profile[name] == value for name, value in _AUTHORITY),
        "run13448_authority_changed")
    return {"schema": "si-run13448-negative-exposure-policy-v1", "owner_authority": OWNER_AUTHORITY,
        "owner_decision": OWNER_DECISION, "run_HEAD": RUN_HEAD, "run_plan_sha256": RUN_PLAN_SHA256,
        "baseline_ledger_sha256": BASELINE_LEDGER_SHA256, "historical_scope_sha256": historical._scope_sha256(),
        "baseline_START_debits": PRIOR_STARTS, "baseline_charged_bytes": PRIOR_CHARGED_BYTES,
        "historical_START_ceiling_unchanged": HISTORICAL_START_CEILING,
        "maximum_cumulative_STARTs": MAXIMUM_STARTS, "maximum_cumulative_bytes": MAXIMUM_BYTES,
        "permanent_unknown_START_upper_debits": EXPOSURE_SLOTS,
        "permanent_unknown_byte_debits": EXPOSURE_SLOTS * PAGE_BYTES, "page_bytes": PAGE_BYTES,
        "position_derivation": "first_eight_genuine_B3_missing_positions_original_typed_matrix_order",
        "possible_lifetime_try_increment_per_affected_position": 1, "maximum_lifetime_tries": MAXIMUM_LIFETIME_TRIES,
        "required_new_capture_try_preserved": True, "missing_positions": MISSING_POSITIONS,
        "positions_per_chunk": POSITIONS_PER_CHUNK, "chunks": CHUNKS,
        "first_chunk_future_extras": FIRST_CHUNK_FUTURE_EXTRAS,
        "later_chunk_future_extras": LATER_CHUNK_FUTURE_EXTRAS,
        "qualified_coverage_contribution": 0, "old_ledger_rewritten": False,
        "forensic_witness_required_separately": True, "historical_actual_counts": "UNKNOWN_not_zero",
        "allocation_release_or_settlement": "never", "maximum_process_allocations": MAXIMUM_EXPOSURES,
        "authority": profile}


def registered_sha256():
    value = policy()
    require(type(POLICY_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", POLICY_SHA256)
        and hash_payload(value) == POLICY_SHA256, "run13448_policy_unregistered")
    return POLICY_SHA256


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Run13448Exposure:
    _parts: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self): raise Run13448ExposureRefusal("REFUSED: run13448_factory_required")

    def _latch(self):
        record = _MINTS.get(id(self))
        if type(record) is tuple and record[0] is self: _FAILED.add(id(self))

    def _guard(self):
        try:
            require(type(self) is Run13448Exposure, "run13448_allocation_changed")
            try: parts, identity = object.__getattribute__(self, "_parts"), object.__getattribute__(self, "_identity")
            except AttributeError: parts, identity = None, None
            require(type(parts) is tuple and len(parts) == 9 and parts is identity
                and parts[0] is self and _MINTS.get(id(self)) is parts, "run13448_allocation_changed")
            require(id(self) not in _FAILED, "run13448_allocation_permanently_stopped")
            parts[1]._guard()
            require(parts[1].sha256 == BASELINE_LEDGER_SHA256 and parts[7] == registered_sha256()
                and type(parts[6]) is bytes and hash_bytes(parts[6]) == parts[8], "run13448_allocation_changed")
            return parts
        except BaseException:
            self._latch(); raise

    @property
    def sha256(self): return self._guard()[8]

    def public_summary(self): return json.loads(self._guard()[6])

    def possible_reservation_positions(self): return self._guard()[3]

    def lifetime_try_upper_bound(self, position):
        try:
            parts = self._guard()
            require(type(position) is int and 1 <= position <= len(parts[4]), "run13448_exact_position_required")
            return parts[4][position - 1] + int(position in parts[3])
        except BaseException:
            self._latch(); raise

    def future_extra_allowance(self, chunk):
        try:
            parts = self._guard()
            require(type(chunk) is int and 1 <= chunk <= len(parts[5]), "run13448_exact_chunk_required")
            return parts[5][chunk - 1]
        except BaseException:
            self._latch(); raise


def exposure_binding(value):
    """Exact original allocation9 for a separately authenticated wrapper only."""
    require(type(value) is Run13448Exposure, "run13448_allocation_changed")
    return value._guard()


def freeze_run13448_exposure(ledger):
    scope = registered_sha256()
    require(type(ledger) is historical.CountEpochLedger, "run13448_exact_ledger_required")
    ledger._guard(); require(ledger.sha256 == BASELINE_LEDGER_SHA256, "run13448_baseline_changed")
    old = ledger.public_summary()
    require(all(type(old.get(name)) is int and old[name] == value for name, value in (
        ("START_debits", PRIOR_STARTS), ("charged_response_bytes", PRIOR_CHARGED_BYTES),
        ("maximum_historical_STARTs", HISTORICAL_START_CEILING), ("maximum_historical_bytes", MAXIMUM_BYTES),
        ("missing_transport_observation_positions", MISSING_POSITIONS))), "run13448_baseline_accounting_changed")
    selected, unused = historical._source_positions(ledger._parts[1])
    retained = frozenset(ledger._parts[6])
    missing = tuple(position for position in range(1, len(selected) + 1) if position not in retained)
    chunks = tuple(missing[offset:offset + POSITIONS_PER_CHUNK] for offset in range(0, len(missing), POSITIONS_PER_CHUNK))
    require(len(missing) == MISSING_POSITIONS and len(chunks) == CHUNKS and len(missing) >= EXPOSURE_SLOTS,
        "run13448_missing_scope_changed")
    prior = [0] * len(selected)
    for epoch in ledger._parts[2]:
        for position in epoch._parts[5]:
            require(type(position) is int and 1 <= position <= len(prior), "run13448_prior_tries_changed")
            prior[position - 1] += 1
    affected = missing[:EXPOSURE_SLOTS]
    require(all(prior[position - 1] + 1 < MAXIMUM_LIFETIME_TRIES for position in affected)
        and all(prior[position - 1] < MAXIMUM_LIFETIME_TRIES for position in missing),
        "run13448_required_future_try_unavailable")
    extras = (FIRST_CHUNK_FUTURE_EXTRAS,) + (LATER_CHUNK_FUTURE_EXTRAS,) * (CHUNKS - 1)
    key = ledger.sha256, scope
    require(key not in _KEYS, "run13448_allocation_already_minted")
    require(len(_MINTS) < MAXIMUM_EXPOSURES, "run13448_allocation_capacity")
    report = {"schema": "si-run13448-negative-exposure-v1", "policy_sha256": scope,
        "baseline_ledger_sha256": ledger.sha256, "owner_authority": OWNER_AUTHORITY, "owner_decision": OWNER_DECISION,
        "known_baseline_START_debits": PRIOR_STARTS, "known_baseline_charged_bytes": PRIOR_CHARGED_BYTES,
        "permanent_unknown_START_upper_debits": EXPOSURE_SLOTS, "permanent_unknown_byte_debits": EXPOSURE_SLOTS * PAGE_BYTES,
        "budget_counted_START_upper_bound": PRIOR_STARTS + EXPOSURE_SLOTS,
        "budget_counted_byte_upper_bound": PRIOR_CHARGED_BYTES + EXPOSURE_SLOTS * PAGE_BYTES,
        "remaining_START_upper_capacity": MAXIMUM_STARTS - PRIOR_STARTS - EXPOSURE_SLOTS,
        "remaining_byte_capacity": MAXIMUM_BYTES - PRIOR_CHARGED_BYTES - EXPOSURE_SLOTS * PAGE_BYTES,
        "missing_positions": len(missing), "missing_positions_sha256": hash_payload(missing),
        "possible_reserved_positions_sha256": hash_payload(affected), "baseline_prior_tries_sha256": hash_payload(prior),
        "possible_lifetime_tries_sha256": hash_payload(tuple(prior[position - 1] + 1 for position in affected)),
        "future_extra_allowances_sha256": hash_payload(extras), "maximum_future_extra_slots": sum(extras),
        "qualified_coverage_contribution": 0, "positive_closed_chunk_contribution": 0,
        "historical_actual_counts": {"START_reservations": None, "START_controls": None,
            "provider_key_reads": None, "provider_GET_requests": None, "received_response_bytes": None},
        "old_ledger_rewritten": False, "forensic_witness_authenticated": False,
        "allocation_is_operational_resolution": False, "authority": authority()}
    raw = canonical_json(report).encode(); value = object.__new__(Run13448Exposure)
    parts = value, ledger, missing, affected, tuple(prior), extras, raw, scope, hash_bytes(raw)
    object.__setattr__(value, "_parts", parts); object.__setattr__(value, "_identity", parts)
    _MINTS[id(value)] = parts; _KEYS.add(key); value._guard(); return value
