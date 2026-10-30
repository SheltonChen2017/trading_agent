"""Original-terminal count transport accounting; never source/input admission.

Only the fixed outer coordinator's authenticated post-context origin can issue
a ClosedCountChunk. Pair/control closure, caller JSON, hashes and complete
flags cannot create the witness or release one byte of a budget reservation.
"""
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_count_durable_budget as accounting

MAXIMUM_BYTES, MAXIMUM_MEMBERS = 2 * 1024 ** 2, 4 * 528 + 16
_ISSUED, _FAILED = {}, set()
_CODES = frozenset("""closed_chunk_factory_required closed_chunk_binding_changed
closed_chunk_terminal_required closed_chunk_manifest_changed closed_chunk_roster_changed
closed_chunk_response_changed closed_chunk_coverage_changed closed_chunk_negative
closed_chunk_reused_origin""".split())


class ClosedCountChunkRefusal(ValueError): pass


def require(value, code):
    if not value: raise ClosedCountChunkRefusal("REFUSED: " + code)


def authority():
    return {"transport_accounting_only": True, "source_admitted": False,
        "denominator_admitted": False, "actual_input_execution_admitted": False,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0}


def failure_summary(error):
    code = None
    if type(error) is ClosedCountChunkRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = (next((name for name in _CODES if args[0] == "REFUSED: " + name), None)
            if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None)
    return {"category": "local_contract_refusal" if code is not None else "unknown_local_error",
        "contract_code": code, "errno_name": None}


class ClosedCountChunk:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise ClosedCountChunkRefusal("REFUSED: closed_chunk_factory_required")
    def __repr__(self): return "<ClosedCountChunk redacted>"


def _parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM_BYTES, "closed_chunk_manifest_changed")
    def pairs(items):
        result = {}
        for key, value in items:
            require(type(key) is str and key not in result, "closed_chunk_manifest_changed")
            result[key] = value
        return result
    try: value = json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError): raise ClosedCountChunkRefusal("REFUSED: closed_chunk_manifest_changed") from None
    require(canonical_json(value).encode() == raw, "closed_chunk_manifest_changed")
    return value


def _manifest(operation, candidate, terminal):
    raw = terminal[9]
    require(type(terminal[10]) is str and hash_bytes(raw) == terminal[10], "closed_chunk_manifest_changed")
    value = _parse(raw); op = transport.operation_binding(operation)
    expected_keys = {"schema", "role", "chunk", "operator_protocol_sha256", "registration_sha256",
        "candidate_sha256", "payload", "source_admitted", "budget_release_authority"}
    original = transport.provisional_candidate_binding(candidate)
    require(type(value) is dict and set(value) == expected_keys and value["schema"] == "si-count-final-control-v1"
        and value["role"] == "manifest" and type(value["chunk"]) is int and value["chunk"] == op[4]
        and value["operator_protocol_sha256"] == op[5] and value["registration_sha256"] == op[6]
        and value["candidate_sha256"] == original[7] and value["source_admitted"] is False
        and value["budget_release_authority"] is False and type(value["payload"]) is dict
        and set(value["payload"]) == {"members"}, "closed_chunk_manifest_changed")
    members = value["payload"]["members"]
    require(type(members) is list and 0 < len(members) <= MAXIMUM_MEMBERS, "closed_chunk_manifest_changed")
    names = []
    for row in members:
        require(type(row) is dict and set(row) == {"name", "bytes", "sha256"}
            and type(row["name"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", row["name"])
            and not any(part in {".", ".."} for part in row["name"].split("/"))
            and not row["name"].startswith("claim/")
            and row["name"] != "final_manifest/manifest.private.json"
            and not row["name"].endswith((".refused.json", "post-publication-refused.json"))
            and type(row["bytes"]) is int and 0 <= row["bytes"] <= MAXIMUM_BYTES
            and type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
            "closed_chunk_manifest_changed")
        names.append(row["name"])
    require(names == sorted(set(names)) and members == transport._coordinator().final_member_rows(operation, candidate),
        "closed_chunk_manifest_changed")
    return hash_bytes(raw)


def _checked_terminal(operation, candidate):
    anchor = transport.operation_binding(operation)
    original = transport.provisional_candidate_binding(candidate)
    require(original[1] is operation and original[2] is anchor, "closed_chunk_binding_changed")
    terminal = transport._coordinator().terminal_chunk_binding(operation, candidate)
    require(type(terminal) is tuple and len(terminal) == 14 and terminal[0] is operation
        and terminal[1] is candidate and type(terminal[12]) is object
        and type(terminal[13]) is str and re.fullmatch(r"[0-9a-f]{64}", terminal[13]), "closed_chunk_terminal_required")
    require(type(terminal[5]) is tuple and type(terminal[6]) is tuple and type(terminal[7]) is tuple
        and len(terminal[5]) == len(terminal[6]) == len(terminal[7]) == len(original[3]) > 0
        and all(actual is expected for actual, expected in zip(terminal[6], original[4]))
        and all(actual is expected for actual, expected in zip(terminal[7], original[5])), "closed_chunk_roster_changed")
    claim = transport._controls().claim_binding(terminal[4])
    require(claim[1] is operation and claim[2] is anchor[1] and claim[3] is anchor[2]
        and claim[4] == anchor[4] and claim[5] == anchor[5] and claim[7] == anchor[6], "closed_chunk_binding_changed")
    require(type(terminal[8]) is tuple and len(terminal[8]) == 4, "closed_chunk_terminal_required")
    for control, role in zip(terminal[8], transport.FINAL_ROLES):
        bound = transport._controls().final_control_binding(control)
        require(type(bound) is tuple and len(bound) == 8 and bound[0] is control and bound[1] is operation
            and bound[2] == role and bound[6] is candidate, "closed_chunk_terminal_required")
        if role == "manifest":
            require(bound[4][4] == terminal[9] and bound[3] == terminal[10], "closed_chunk_manifest_changed")
    charges, covered = [], set()
    for ticket, obs, evidence, start in zip(original[3], terminal[6], terminal[7], terminal[5]):
        reserved = accounting.ticket_binding(ticket); observed = transport.http_observation_binding(obs)
        started = transport._controls().start_binding(start)
        require(type(evidence) is tuple and len(evidence) == 2, "closed_chunk_response_changed")
        received = transport._controls().received_binding(evidence[0])
        require(reserved[1] is anchor[1] and reserved[2] is anchor[2] and reserved[3] == anchor[4]
            and observed[1] is operation and observed[2] is ticket and observed[3] is terminal[4]
            and observed[4] is start and observed[5] == reserved[8] and observed[6] == started[4]
            and started[1] is operation and started[2] is ticket and started[3] is terminal[4]
            and type(received) is tuple and len(received) == 12 and received[1] is operation
            and received[2] is ticket and received[3] is obs and received[4] is terminal[4] and received[5] is start,
            "closed_chunk_response_changed")
        raw = observed[10]
        if observed[8] is True and type(observed[9]) is int and observed[9] == 200 and type(raw) is bytes and raw:
            durable = transport._responses().response_binding(evidence[1])
            require(type(durable) is tuple and len(durable) == 13 and durable[0] is evidence[1]
                and durable[1] is operation and durable[2] is ticket and durable[3] is obs
                and durable[6] == hash_bytes(raw) and type(durable[7]) is int and durable[7] == len(raw)
                and 0 < len(raw) <= MAXIMUM_BYTES, "closed_chunk_response_changed")
            charges.append(len(raw)); covered.add(reserved[5])
        else:
            # 404/statusless/no-body remain negative full-page debts. A later
            # successful retry can cover a position without erasing this ticket.
            require(evidence[1] is None, "closed_chunk_response_changed")
            charges.append(MAXIMUM_BYTES)
    expected = anchor[2].chunk_positions(anchor[4])
    require(tuple(sorted(covered)) == original[6] == expected, "closed_chunk_coverage_changed")
    root = _manifest(operation, candidate, terminal)
    return terminal, (anchor[3], anchor[2], anchor[4], original[3], tuple(charges), expected, root)


def _issue_original_closed_chunk(operation, candidate):
    """Fixed outer finish only; authenticators, not caller completion, decide."""
    try:
        terminal, accounting_tuple = _checked_terminal(operation, candidate)
        require(not any(record[1] is candidate for record in _ISSUED.values()), "closed_chunk_reused_origin")
        value = object.__new__(ClosedCountChunk)
        original = value, candidate, operation, terminal, accounting_tuple, object()
        value._anchor = value._identity = original; _ISSUED[value] = original
        return value
    except BaseException:
        transport._latch(operation); raise


def closed_count_chunk_accounting(value):
    try:
        original = _ISSUED.get(value) if type(value) is ClosedCountChunk else None
        require(type(original) is tuple and len(original) == 6 and original[0] is value
            and value._anchor is value._identity is original and value not in _FAILED,
            "closed_chunk_binding_changed")
        terminal, current = _checked_terminal(original[2], original[1])
        require(terminal is original[3] and current[:4] == original[4][:4]
            and current[4:] == original[4][4:], "closed_chunk_binding_changed")
        return original[4]
    except BaseException:
        if type(value) is ClosedCountChunk: _FAILED.add(value)
        raise
