"""Finite historical transport contributions; never count/input admission.

Only an ORIGINAL just-checked ClosedCountChunk can mint a contribution. Its
past closure facts and privately retained immutable bytes have separate pure
provenance: later access never resurrects expired source/volume contexts or
asserts perpetual filesystem stability. Union also requires irreversible
original budget settlement; a closure or caller payload alone cannot join it.
"""
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_count_epoch_ledger as historical
from research.short_interest_etf import native_count_recovery_budget as plans
from scripts import short_interest_count_durable_budget as accounting
from scripts import short_interest_closed_count_chunk as original_reader

_ORIGINAL_CLOSED_CLASS = original_reader.ClosedCountChunk

MAXIMUM_CONTRIBUTIONS, MAXIMUM_UNIONS = 133, 1
MAXIMUM_TICKETS_PER_CHUNK, MAXIMUM_BODY_BYTES = 528, 2097152
MAXIMUM_CUMULATIVE_STARTS, MAXIMUM_CUMULATIVE_BYTES = 84005, 4 * 1024 ** 3
_CONTRIBUTIONS, _PRIVATE_PROOFS, _CLOSED_ORIGINS, _UNIONS = {}, {}, {}, {}
_FAILED, _UNION_FAILED = set(), set()
_AUTHORITY = (("historical_transport_observations_only", True), ("source_admitted", False),
    ("count_source_qualified", False), ("denominator_admitted", False),
    ("actual_input_execution_admitted", False), ("ready_for_backtest", False),
    ("dispatch_authority", False), ("budget_release_authority", False),
    ("perpetual_filesystem_custody_claimed", False), ("outcome_looks", 0), ("qc_attempts", 0))
_CODES = frozenset("""transport_union_factory_required transport_union_policy_changed
transport_union_baseline_changed transport_union_plan_changed transport_union_binding_changed
transport_union_latched_failure transport_union_original_chunk_required transport_union_original_terminal_changed
transport_union_original_observation_changed transport_union_duplicate_chunk transport_union_capacity_exhausted
transport_union_original_settlement_required transport_union_settlement_changed transport_union_incomplete
transport_union_overlap transport_union_budget_exceeded transport_union_retention_changed""".split())


class CountTransportUnionRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountTransportUnionRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is CountTransportUnionRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
    return {"category": "local_contract_refusal" if type(error) is CountTransportUnionRefusal
        else "unknown_local_error", "contract_code": code, "errno_name": None}


def authority(): return dict(_AUTHORITY)


def policy():
    require(all(type(value) is int and value == expected for value, expected in zip(
        (MAXIMUM_CONTRIBUTIONS, MAXIMUM_UNIONS, MAXIMUM_TICKETS_PER_CHUNK, MAXIMUM_BODY_BYTES,
            MAXIMUM_CUMULATIVE_STARTS, MAXIMUM_CUMULATIVE_BYTES), (133, 1, 528, 2097152, 84005, 4294967296))),
        "transport_union_policy_changed")
    profile = authority()
    require(type(profile) is dict and tuple(profile) == tuple(name for name, unused in _AUTHORITY)
        and all(type(profile[name]) is type(value) and profile[name] == value for name, value in _AUTHORITY),
        "transport_union_policy_changed")
    return {"schema": "si-count-transport-union-policy-v1", "maximum_contributions": MAXIMUM_CONTRIBUTIONS,
        "maximum_unions": MAXIMUM_UNIONS, "maximum_tickets_per_chunk": MAXIMUM_TICKETS_PER_CHUNK,
        "maximum_body_bytes": MAXIMUM_BODY_BYTES, "maximum_cumulative_STARTs": MAXIMUM_CUMULATIVE_STARTS,
        "maximum_cumulative_bytes": MAXIMUM_CUMULATIVE_BYTES,
        "mint": "exact_original_ClosedCountChunk_authenticated_twice_within_its_original_closure_window",
        "retention": "private_original_opaque_observation_response_and_immutable_bytes_no_raw_public_reader",
        "pure_access": "original_process_issued_tuple_hash_nonce_only_never_expired_reader_lease_volume_or_FAILED_budget",
        "union": "exact_old_four_epochs_original_plan_full_ordered_disjoint_chunks_original_settled_account7_identity",
        "operative_accounting": "original_plan_budget_profile_permanent_negative_floor_never_historical_B3_rewrite_or_refund",
        "restart_reload_authority": False, "authority": profile}


def _policy():
    require(hash_payload(policy()) == _POLICY_SHA256, "transport_union_policy_changed")


def _source(baseline, plan):
    require(type(baseline) is historical.CountEpochLedger and type(plan) is plans.CountRecoveryPlan,
        "transport_union_baseline_changed")
    baseline._guard(); plan._guard()
    require(plan._parts[1] is baseline and len(baseline._parts[2]) == 4
        and tuple(epoch._parts[3] for epoch in baseline._parts[2])
            == ("original48", "refused13944", "v2zero", "v3zero"), "transport_union_baseline_changed")
    require(0 < len(plan._parts[3]) <= MAXIMUM_CONTRIBUTIONS, "transport_union_plan_changed")
    return baseline.public_summary()


def _operative_profile(plan, old):
    profile = plan.budget_profile()
    exposed = plans.negative_exposure.exposure_binding(plan._parts[8]) if len(plan._parts) == 9 else None
    slots = len(exposed[3]) if exposed is not None else 0
    require(profile["known_baseline_START_debits"] == old["START_debits"]
        and profile["known_baseline_charged_bytes"] == old["charged_response_bytes"]
        and profile["permanent_unknown_START_upper_debits"] == slots
        and profile["permanent_unknown_byte_debits"] == slots * MAXIMUM_BODY_BYTES
        and profile["negative_exposure_sha256"] == (exposed[8] if exposed is not None else None)
        and profile["initial_START_upper_bound"] == old["START_debits"] + profile["permanent_unknown_START_upper_debits"]
        and profile["initial_byte_upper_bound"] == old["charged_response_bytes"] + profile["permanent_unknown_byte_debits"]
        and profile["maximum_cumulative_STARTs"] <= MAXIMUM_CUMULATIVE_STARTS
        and profile["maximum_cumulative_bytes"] <= MAXIMUM_CUMULATIVE_BYTES,
        "transport_union_baseline_changed")
    return profile


def _negative_fields(profile, starts, charges):
    if profile["negative_exposure_sha256"] is None: return {}
    return {"negative_exposure_sha256": profile["negative_exposure_sha256"],
        "permanent_unknown_START_upper_debits": profile["permanent_unknown_START_upper_debits"],
        "permanent_unknown_byte_debits": profile["permanent_unknown_byte_debits"],
        "operative_initial_START_upper_bound": profile["initial_START_upper_bound"],
        "operative_initial_byte_upper_bound": profile["initial_byte_upper_bound"],
        "operative_cumulative_START_upper_bound": profile["initial_START_upper_bound"] + starts,
        "operative_cumulative_byte_upper_bound": profile["initial_byte_upper_bound"] + charges}


class ClosedCountTransportContribution:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportUnionRefusal("REFUSED: transport_union_factory_required")
    def __repr__(self): return "<ClosedCountTransportContribution redacted>"
    def public_summary(self): return json.loads(contribution_binding(self)[7])
    @property
    def sha256(self): return contribution_binding(self)[8]


def contribution_binding(value):
    """Original redacted10; no raw bytes or expired operational accessor."""
    try:
        require(type(value) is ClosedCountTransportContribution
            and ClosedCountTransportContribution.__hash__ is object.__hash__
            and ClosedCountTransportContribution.__eq__ is object.__eq__, "transport_union_binding_changed")
        saved = _CONTRIBUTIONS.get(value)
        require(type(saved) is tuple and len(saved) == 3 and type(saved[0]) is tuple
            and len(saved[0]) == 10 and saved[0] is value._anchor is value._identity
            and saved[0][0] is value and value not in _FAILED, "transport_union_binding_changed")
        original, retained, scope = saved
        _policy(); _source(original[1], original[2])
        require(scope == _POLICY_SHA256 and type(original[7]) is bytes
            and hash_bytes(original[7]) == original[8] and type(original[9]) is object
            and _PRIVATE_PROOFS.get(value) is retained and type(retained) is tuple and len(retained) == 2
            and type(retained[0]) is tuple and type(retained[1]) is tuple
            and len(retained[1]) == len(original[5][3]) > 0, "transport_union_retention_changed")
        # Immutable original tuple/bytes references were authenticated during
        # issuance. Deliberately do NOT inspect mutable old caps or callbacks.
        return original
    except BaseException:
        if type(value) is ClosedCountTransportContribution: _FAILED.add(value)
        raise


def freeze_closed_count_transport_contribution(closed):
    """Snapshot a genuine just-closed chunk, before its finite clock expires."""
    from scripts import short_interest_closed_count_chunk as reader
    from scripts import short_interest_count_durable_transport as transport
    _policy()
    require(reader is original_reader and reader.ClosedCountChunk is _ORIGINAL_CLOSED_CLASS
        and type(closed) is _ORIGINAL_CLOSED_CLASS
        and _ORIGINAL_CLOSED_CLASS.__hash__ is object.__hash__
        and _ORIGINAL_CLOSED_CLASS.__eq__ is object.__eq__, "transport_union_original_chunk_required")
    require(closed not in _CLOSED_ORIGINS, "transport_union_duplicate_chunk")
    require(len(_CONTRIBUTIONS) < MAXIMUM_CONTRIBUTIONS, "transport_union_capacity_exhausted")
    account = reader.closed_count_chunk_accounting(closed)
    issued = reader._ISSUED.get(closed)
    require(type(issued) is tuple and len(issued) == 6 and issued[0] is closed
        and closed._anchor is closed._identity is issued and issued[4] is account,
        "transport_union_original_chunk_required")
    terminal, operation = issued[3], issued[2]
    op = transport.operation_binding(operation); plan, baseline = account[1], account[1]._parts[1]
    old = _source(baseline, plan)
    require(type(account) is tuple and len(account) == 7 and account[0] is op[3]
        and account[1] is op[2] and type(account[2]) is int and account[2] == op[4]
        and type(account[3]) is tuple and 0 < len(account[3]) <= min(MAXIMUM_TICKETS_PER_CHUNK,
            len(plan.chunk_positions(account[2])) + plan.chunk_extra_limit(account[2]))
        and type(account[4]) is tuple and len(account[4]) == len(account[3])
        and account[5] == plan.chunk_positions(account[2]), "transport_union_original_chunk_required")
    require(type(terminal) is tuple and len(terminal) == 14 and terminal[0] is operation
        and terminal[1] is issued[1] and len(terminal[5]) == len(terminal[6]) == len(terminal[7]) == len(account[3]),
        "transport_union_original_terminal_changed")
    require(not any(saved[0][2] is plan and saved[0][5][2] == account[2]
        for saved in _CONTRIBUTIONS.values()), "transport_union_duplicate_chunk")
    claim = transport._controls().claim_binding(terminal[4])
    final_controls = tuple(transport._controls().final_control_binding(control) for control in terminal[8])
    retained, lineage = [], []
    raw_count = raw_bytes = unknown = 0
    for ticket, charge, obs, evidence, start in zip(account[3], account[4], terminal[6], terminal[7], terminal[5]):
        ticket_origin = accounting.ticket_binding(ticket)
        observed = transport.http_observation_binding(obs)
        started = transport._controls().start_binding(start)
        require(type(evidence) is tuple and len(evidence) == 2, "transport_union_original_observation_changed")
        received = transport._controls().received_binding(evidence[0])
        require(ticket_origin[0] is ticket and ticket_origin[1] is op[1] and ticket_origin[2] is plan
            and ticket_origin[3] == account[2] and observed[1] is operation and observed[2] is ticket
            and observed[4] is start and started[2] is ticket and received[2] is ticket and received[3] is obs,
            "transport_union_original_observation_changed")
        raw = observed[10]; durable = None
        if observed[8] is True and type(observed[9]) is int and observed[9] == 200 and type(raw) is bytes and raw:
            durable = transport._responses().response_binding(evidence[1])
            require(type(durable) is tuple and len(durable) == 13 and durable[2] is ticket and durable[3] is obs
                and durable[6] == hash_bytes(raw) and type(durable[7]) is int and durable[7] == len(raw)
                and type(charge) is int and charge == len(raw) <= MAXIMUM_BODY_BYTES,
                "transport_union_original_observation_changed")
            raw_count += 1; raw_bytes += len(raw)
        else:
            require(evidence[1] is None and (raw is None or (type(raw) is bytes and not raw))
                and type(charge) is int and charge == MAXIMUM_BODY_BYTES,
                "transport_union_original_observation_changed")
            unknown += 1
        retained.append((ticket_origin, observed, started, received, durable, raw))
        lineage.append((ticket_origin[4], ticket_origin[5], ticket_origin[6], ticket_origin[7],
            ticket_origin[8], ticket_origin[9], observed[14], started[4], received[6],
            None if durable is None else durable[6], None if durable is None else durable[8],
            None if durable is None else hash_payload(durable[9:11]),
            hash_payload(started[10]), hash_payload(received[8]), charge))
    profile = _operative_profile(plan, old)
    require(profile["initial_START_upper_bound"] + len(account[3]) <= profile["maximum_cumulative_STARTs"]
        and profile["initial_byte_upper_bound"] + sum(account[4]) <= profile["maximum_cumulative_bytes"],
        "transport_union_budget_exceeded")
    payload = {"schema": "si-closed-count-transport-contribution-v1", "baseline_sha256": baseline.sha256,
        "plan_sha256": plan.sha256, "chunk": account[2], "START_debits": len(account[3]),
        "charged_response_bytes": sum(account[4]), "retained_raw_attempts": raw_count,
        "retained_raw_bytes": raw_bytes, "unknown_full_page_START_debits": unknown,
        "unknown_full_page_charged_bytes": unknown * MAXIMUM_BODY_BYTES,
        "covered_transport_positions": len(account[5]), "covered_positions_sha256": hash_payload(account[5]),
        "attempt_lineage_sha256": hash_payload(lineage), "manifest_root_sha256": account[6],
        "terminal_lineage_sha256": hash_payload({"claim_raw_sha256": claim[6], "claim_seal": claim[9],
            "final_controls": [(item[2], item[3], item[5]) for item in final_controls],
            "runtime_heads": (op[8], op[9]), "registration_sha256": op[6]}),
        "closed_at": terminal[11], "operator_protocol_sha256": op[5], "outer_protocol_sha256": terminal[13],
        **_negative_fields(profile, len(account[3]), sum(account[4])),
        "authority": authority()}
    raw_payload = canonical_json(payload).encode()
    # Expensive snapshot preparation does not move the deadline. The original
    # complete reader/outer checks run AGAIN before any semantic mint occurs.
    require(reader.closed_count_chunk_accounting(closed) is account
        and reader._ISSUED.get(closed) is issued, "transport_union_original_terminal_changed")
    value = object.__new__(ClosedCountTransportContribution)
    original = (value, baseline, plan, op[1], op[3], account, closed, raw_payload, hash_bytes(raw_payload), object())
    value._anchor = value._identity = original
    proofs = ((terminal, op, claim, final_controls), tuple(retained))
    _CONTRIBUTIONS[value] = original, proofs, _POLICY_SHA256
    _PRIVATE_PROOFS[value] = proofs; _CLOSED_ORIGINS[closed] = value
    contribution_binding(value)
    return value


class CountTransportUnion:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportUnionRefusal("REFUSED: transport_union_factory_required")
    def __repr__(self): return "<CountTransportUnion redacted>"
    def public_summary(self): return json.loads(_union_binding(self)[4])
    @property
    def sha256(self): return _union_binding(self)[5]


def _union_binding(value):
    try:
        require(type(value) is CountTransportUnion and CountTransportUnion.__hash__ is object.__hash__
            and CountTransportUnion.__eq__ is object.__eq__, "transport_union_binding_changed")
        original = _UNIONS.get(value)
        require(type(original) is tuple and len(original) == 9 and original[0] is value
            and original is value._anchor is value._identity and value not in _UNION_FAILED,
            "transport_union_binding_changed")
        _policy(); _source(original[1], original[2])
        for item in original[3]: contribution_binding(item)
        require(type(original[4]) is bytes and hash_bytes(original[4]) == original[5]
            and original[7] == _POLICY_SHA256 and type(original[8]) is object,
            "transport_union_binding_changed")
        return original
    except BaseException:
        if type(value) is CountTransportUnion: _UNION_FAILED.add(value)
        raise


def seal_count_transport_union(baseline, plan, contributions, settled_budget):
    """Full planned transport union, never caller completeness or count truth."""
    _policy(); old = _source(baseline, plan)
    require(len(_UNIONS) < MAXIMUM_UNIONS, "transport_union_capacity_exhausted")
    require(type(contributions) is tuple and len(contributions) == len(plan._parts[3]),
        "transport_union_incomplete")
    require(type(settled_budget) is accounting.DurableCountBudget, "transport_union_original_settlement_required")
    settled = accounting.settled_chunk_accounting(settled_budget)
    require(type(settled) is tuple and len(settled) == 4 and settled[0] is settled_budget
        and settled[2] is plan and type(settled[3]) is tuple and len(settled[3]) == len(contributions),
        "transport_union_original_settlement_required")
    positions = set(baseline._parts[6]); starts, charges, raws = 0, 0, 0
    reports = []
    for number, (contribution, account) in enumerate(zip(contributions, settled[3]), 1):
        original = contribution_binding(contribution)
        require(original[1] is baseline and original[2] is plan and original[3] is settled_budget
            and original[4] is settled[1] and original[5] is account and type(account) is tuple
            and len(account) == 7 and account[0] is settled[1] and account[1] is plan
            and type(account[2]) is int and account[2] == number,
            "transport_union_settlement_changed")
        require(account[5] == plan.chunk_positions(number) and not positions.intersection(account[5]),
            "transport_union_overlap")
        positions.update(account[5]); starts += len(account[3]); charges += sum(account[4])
        report = json.loads(original[7]); raws += report["retained_raw_bytes"]; reports.append(report)
    require(positions == set(range(1, historical.ORIGINAL_COUNT + 1)), "transport_union_incomplete")
    profile = _operative_profile(plan, old)
    require(profile["initial_START_upper_bound"] + starts <= profile["maximum_cumulative_STARTs"]
        and profile["initial_byte_upper_bound"] + charges <= profile["maximum_cumulative_bytes"],
        "transport_union_budget_exceeded")
    payload = {"schema": "si-count-transport-union-v1", "baseline_sha256": baseline.sha256,
        "plan_sha256": plan.sha256, "original_spent_epochs": 4, "closed_settled_chunks": len(contributions),
        "historical_START_debits": old["START_debits"], "new_START_debits": starts,
        "cumulative_START_debits": old["START_debits"] + starts,
        "historical_charged_bytes": old["charged_response_bytes"], "new_charged_bytes": charges,
        "cumulative_charged_bytes": old["charged_response_bytes"] + charges,
        **_negative_fields(profile, starts, charges),
        "new_retained_raw_bytes": raws, "transport_position_count": len(positions),
        "retained_position_union_sha256": hash_payload(sorted(positions)),
        "contribution_sha256s": [item.sha256 for item in contributions],
        "settled_accounting_roots_sha256": hash_payload([account[6] for account in settled[3]]),
        "complete_transport_coverage": True, "any_count_source_qualified": False, "authority": authority()}
    raw = canonical_json(payload).encode(); value = object.__new__(CountTransportUnion)
    original = (value, baseline, plan, contributions, raw, hash_bytes(raw), settled, _POLICY_SHA256, object())
    value._anchor = value._identity = original; _UNIONS[value] = original
    _union_binding(value)
    return value


_POLICY_SHA256 = hash_payload(policy())
