"""Post-restart conservative negative basis, never source readmission authority.

The old run's actuals and lost process capability stay UNKNOWN. This distinct
pure factory retains the original four-epoch ledger, an original permanent
eight-page allocation and its original nine-part future plan. It never opens
an old footprint, reconstructs a mounted epoch or issues a source permission.
"""
from dataclasses import dataclass, field
import json

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_count_epoch_ledger as historical
import research.short_interest_etf.native_count_run13448_exposure as exposure
import research.short_interest_etf.native_count_recovery_budget as plans

POLICY_SHA256 = "828c2b34b3cf1817a912aef00f27948b049b296cf4493b071ba9771d738ee5d3"
_EXPECTED_PROFILE = ("b3a8ac9057f8461bd4c450ffc911a5adac8c129ced762e33c5e56660215861e3",
    13992, 23452681, 81876, 84005, 4294967296, 67885, 512, 133, 16, 3, 8, 2097152, 8, 16, 1)
_AUTHORITY = (("conservative_negative_basis_only", True), ("SourceAUTH_release", False),
    ("dispatch_authority", False), ("credential_authority", False), ("retry_authority", False),
    ("new_claim_authority", False), ("budget_release_authority", False), ("refund_authority", False),
    ("old_claim_reuse_authority", False), ("historical_actuals_certified", False),
    ("forensic_resolution_authenticated", False), ("old_mounted_epoch_authenticated", False),
    ("old_process_exit_attested", False), ("source_admitted", False), ("denominator_admitted", False),
    ("ready_for_backtest", False), ("QC_or_Safari", False), ("provider_HTTP", 0),
    ("credential_reads", 0), ("new_STARTs", 0), ("new_charged_bytes", 0), ("outcome_looks", 0), ("qc_attempts", 0))
_MINTS, _SCOPES, _KEYS, _ATTEMPTED, _FAILED = {}, {}, {}, set(), set()
_CURRENT_SCOPE = None
_CODES = frozenset("""basis_policy_changed basis_unregistered basis_factory_required basis_changed
basis_permanently_stopped basis_scope_changed basis_exact_ledger_required basis_baseline_changed
basis_exact_exposure_required basis_exact_plan_required basis_accounting_changed basis_already_attempted
basis_capacity basis_producer_changed""".split())


class ConservativeReadmissionRefusal(ValueError): pass


def require(value, code):
    if not value: raise ConservativeReadmissionRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is ConservativeReadmissionRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
    return {"category": "local_contract_refusal" if code is not None else "unknown_local_error",
        "contract_code": code, "errno_name": None}


def authority(): return dict(_AUTHORITY)


def _profile():
    return (plans.BASELINE_LEDGER_SHA256, plans.PRIOR_STARTS, plans.PRIOR_CHARGED_BYTES,
        plans.HISTORICAL_START_CEILING, plans.MAXIMUM_CUMULATIVE_STARTS, plans.MAXIMUM_CUMULATIVE_BYTES,
        plans.MISSING_POSITIONS, plans.POSITIONS_PER_CHUNK, plans.MAXIMUM_CHUNKS,
        plans.EXTRA_ATTEMPTS_PER_CHUNK, plans.MAXIMUM_TOTAL_TRIES_PER_POSITION,
        exposure.EXPOSURE_SLOTS, exposure.PAGE_BYTES, exposure.FIRST_CHUNK_FUTURE_EXTRAS,
        exposure.LATER_CHUNK_FUTURE_EXTRAS, exposure.MAXIMUM_EXPOSURES)


def policy():
    profile = _profile()
    require(type(_EXPECTED_PROFILE) is tuple and len(profile) == len(_EXPECTED_PROFILE)
        and all(type(a) is type(b) and a == b for a, b in zip(profile, _EXPECTED_PROFILE)), "basis_policy_changed")
    require(profile[11:] == (8, 2097152, 8, 16, 1), "basis_policy_changed")
    return {"schema": "si-count-post-restart-conservative-basis-policy-v1",
        "owner_authority": exposure.OWNER_AUTHORITY, "owner_restart_statement": "The Mac was restarted",
        "profile": list(profile), "negative_exposure_policy_sha256": exposure.registered_sha256(),
        "nine_part_plan_policy_sha256": hash_payload(plans.exposure_plan_policy()),
        "historical_actuals": "UNKNOWN_not_zero", "qualified_coverage_contribution": 0,
        "positive_closed_chunk_contribution": 0, "original_epoch_ledger_rewritten": False,
        "old_capability_recreated": False, "old_footprint_or_mounted_epoch_reopened": False,
        "allocation": "permanent8_START_upper_debits_and16MiB_never_refund_or_settle",
        "scope": "only_exact_original_ledger_exposure_nine_part_plan_one_attempt_one_basis",
        "operational_readmission": "separate_complete_typed_Main_custody_code_storage_and_source_conjunction_required",
        "maximum_process_bases": 1, "authority": authority()}


def _registered():
    require(type(POLICY_SHA256) is str and len(POLICY_SHA256) == 64
        and all(c in "0123456789abcdef" for c in POLICY_SHA256)
        and hash_payload(policy()) == POLICY_SHA256, "basis_unregistered")


def _producers():
    return (historical.CountEpochLedger._guard, exposure.freeze_run13448_exposure,
        exposure.exposure_binding, plans.freeze_count_recovery_plan_with_exposure, plans.CountRecoveryPlan._guard)


_PRODUCERS = tuple((function, function.__code__) for function in _producers())


def _check_producers():
    current = _producers()
    require(len(current) == len(_PRODUCERS) and all(a is b and a.__code__ is code
        for a, (b, code) in zip(current, _PRODUCERS)), "basis_producer_changed")


@dataclass(frozen=True, slots=True, init=False, eq=False)
class SourceBasisScope:
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self): raise ConservativeReadmissionRefusal("REFUSED: basis_factory_required")


def _scope_binding(scope):
    require(type(scope) is SourceBasisScope, "basis_scope_changed")
    original = _SCOPES.get(id(scope))
    require(type(original) is tuple and len(original) == 4 and original[0] is scope
        and scope is _CURRENT_SCOPE and scope._anchor is scope._identity is original, "basis_scope_changed")
    _registered(); _check_producers()
    require(original[1] == canonical_json(policy()).encode() and hash_bytes(original[1]) == original[2]
        == POLICY_SHA256, "basis_scope_changed")
    return original


def _scope():
    global _CURRENT_SCOPE
    _registered(); _check_producers()
    if _CURRENT_SCOPE is None:
        require(not _SCOPES, "basis_scope_changed")
        value = object.__new__(SourceBasisScope)
        raw = canonical_json(policy()).encode(); row = value, raw, hash_bytes(raw), object()
        object.__setattr__(value, "_anchor", row); object.__setattr__(value, "_identity", row)
        _SCOPES[id(value)] = row; _CURRENT_SCOPE = value
    _scope_binding(_CURRENT_SCOPE); return _CURRENT_SCOPE


def _report(ledger, allocated, plan):
    ledger._guard()
    require(type(ledger) is historical.CountEpochLedger and ledger.sha256 == plans.BASELINE_LEDGER_SHA256,
        "basis_baseline_changed")
    bound = exposure.exposure_binding(allocated)
    require(bound[1] is ledger, "basis_exact_exposure_required")
    require(type(plan) is plans.CountRecoveryPlan, "basis_exact_plan_required"); plan._guard()
    require(len(plan._parts) == 9 and plan._parts[1] is ledger and plan._parts[8] is allocated,
        "basis_exact_plan_required")
    profile = plan.budget_profile(); old = ledger.public_summary(); observed = allocated.public_summary()
    slots, page = exposure.EXPOSURE_SLOTS, exposure.PAGE_BYTES
    starts, charged = old["START_debits"] + slots, old["charged_response_bytes"] + slots * page
    require(profile["permanent_unknown_START_upper_debits"] == slots == 8
        and profile["permanent_unknown_byte_debits"] == slots * page == 16777216
        and profile["initial_START_upper_bound"] == starts and profile["initial_byte_upper_bound"] == charged
        and profile["maximum_cumulative_STARTs"] == plans.MAXIMUM_CUMULATIVE_STARTS
        and profile["maximum_cumulative_bytes"] == plans.MAXIMUM_CUMULATIVE_BYTES
        and profile["negative_exposure_sha256"] == allocated.sha256
        and observed["qualified_coverage_contribution"] == observed["positive_closed_chunk_contribution"] == 0
        and all(value is None for value in observed["historical_actual_counts"].values())
        and not observed["allocation_is_operational_resolution"] and not observed["forensic_witness_authenticated"],
        "basis_accounting_changed")
    return {"schema": "si-count-post-restart-conservative-basis-v1", "policy_sha256": POLICY_SHA256,
        "baseline_ledger_sha256": ledger.sha256, "negative_exposure_sha256": allocated.sha256,
        "nine_part_plan_sha256": plan.sha256, "known_baseline_START_debits": old["START_debits"],
        "known_baseline_charged_bytes": old["charged_response_bytes"],
        "permanent_unknown_START_upper_debits": slots, "permanent_unknown_byte_debits": slots * page,
        "initial_START_upper_bound": starts, "initial_byte_upper_bound": charged,
        "remaining_START_upper_capacity": plans.MAXIMUM_CUMULATIVE_STARTS - starts,
        "remaining_byte_capacity": plans.MAXIMUM_CUMULATIVE_BYTES - charged,
        "historical_actual_counts": dict(observed["historical_actual_counts"]), "old_process_exit": None,
        "qualified_coverage_contribution": 0, "positive_closed_chunk_contribution": 0,
        "old_capability_recreated": False, "forensic_resolution_authenticated": False,
        "old_mounted_epoch_authenticated": False, "authority": authority()}


@dataclass(frozen=True, slots=True, init=False, eq=False)
class ConservativeCountRecoveryBasis:
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self): raise ConservativeReadmissionRefusal("REFUSED: basis_factory_required")

    @property
    def sha256(self): return conservative_basis_binding(self)[6]

    def public_summary(self): return json.loads(conservative_basis_binding(self)[5])


def conservative_basis_binding(value):
    """Original9: basis, scope, ledger, exposure, plan, report, SHA, key, nonce."""
    try:
        require(type(value) is ConservativeCountRecoveryBasis, "basis_changed")
        original = _MINTS.get(id(value))
        require(type(original) is tuple and len(original) == 9 and original[0] is value
            and value._anchor is value._identity is original, "basis_changed")
        require(id(value) not in _FAILED, "basis_permanently_stopped")
        _scope_binding(original[1])
        require(_KEYS.get(original[7]) is original and original[7] in _ATTEMPTED
            and original[7] == (original[2].sha256, POLICY_SHA256), "basis_changed")
        raw = canonical_json(_report(*original[2:5])).encode()
        require(type(original[5]) is bytes and original[5] == raw and hash_bytes(raw) == original[6], "basis_changed")
        return original
    except BaseException:
        if type(value) is ConservativeCountRecoveryBasis and id(value) in _MINTS: _FAILED.add(id(value))
        raise


def freeze_conservative_count_basis(ledger):
    """One pure attempt; failure never releases allocations or retries a mint."""
    try:
        scope = _scope()
        require(type(ledger) is historical.CountEpochLedger, "basis_exact_ledger_required")
        ledger._guard(); require(ledger.sha256 == plans.BASELINE_LEDGER_SHA256, "basis_baseline_changed")
        key = ledger.sha256, POLICY_SHA256
        if key in _ATTEMPTED:
            existing = _KEYS.get(key)
            if existing is not None: _FAILED.add(id(existing[0]))
            raise ConservativeReadmissionRefusal("REFUSED: basis_already_attempted")
        require(not _MINTS and not _ATTEMPTED, "basis_capacity")
        _ATTEMPTED.add(key)  # Before either original factory; never reset after partial failure.
        allocated = exposure.freeze_run13448_exposure(ledger)
        plan = plans.freeze_count_recovery_plan_with_exposure(ledger, allocated)
        raw = canonical_json(_report(ledger, allocated, plan)).encode()
        _scope_binding(scope)
        value = object.__new__(ConservativeCountRecoveryBasis)
        row = value, scope, ledger, allocated, plan, raw, hash_bytes(raw), key, object()
        object.__setattr__(value, "_anchor", row); object.__setattr__(value, "_identity", row)
        _MINTS[id(value)] = row; _KEYS[key] = row
        conservative_basis_binding(value); return value
    except BaseException:
        # A public factory failure against an already issued original ledger
        # also permanently vetoes that basis, including a failed scope check.
        if type(ledger) is historical.CountEpochLedger:
            for original in _MINTS.values():
                if original[2] is ledger: _FAILED.add(id(original[0]))
        raise
