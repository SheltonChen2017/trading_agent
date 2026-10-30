"""Reader core with explicit fake Main/storage terminal registries.

Genuine toy-budget/operator/wire-origin objects are used. The lease, file,
volume, control and terminal closures below are FABRICATED test seams; these
tests establish no actual source, filesystem durability or HTTP observation.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload

# The runtime under test imports POSIX-only stdlib modules at import time, so
# this module cannot even be collected on the supported Windows host; see the
# lane record SI-CR18-001. Portable contract logic stays covered on POSIX.
pytest.importorskip(
    "resource",
    reason=(
        "the protected-capture runtime imports the POSIX-only module "
        "resource at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from scripts import short_interest_closed_count_chunk as reader
from scripts import short_interest_count_durable_transport as transport
from test_short_interest_count_durable_transport import operation, isolated_registries_and_no_network


@pytest.fixture
def chunk(operation, monkeypatch):
    h = operation
    monkeypatch.setattr(reader, "_ISSUED", {})
    monkeypatch.setattr(reader, "_FAILED", set())
    for ticket in h.tickets: h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket]))
    h.candidate = h.op.freeze_provisional_root()
    bound = transport.provisional_candidate_binding(h.candidate)
    finals = []
    class Final: pass
    def final(role):
        raw = transport._final_control_payload(h.op, h.candidate, role)
        cap = Final(); origin = (None, None, None, role, raw, hash_bytes(raw), None, None, None,
            None, None, None, None, None, None)
        h.finals[cap] = cap, h.op, role, hash_bytes(raw), origin, None, h.candidate, object()
        h.op.accept_final_control(cap); finals.append(cap)
        return cap
    for role in transport.FINAL_ROLES[:-1]: final(role)
    rows = []  # External spent claim is authenticated separately, never recast as a capture member.
    for ticket, obs, evidence in zip(h.tickets, bound[4], bound[5]):
        ordinal = ticket.public_summary()["reservation_ordinal"]
        rows.extend([{"name": f"starts/{ordinal:06d}/START.spent.json", "bytes": 1,
            "sha256": h.start_bindings[h.starts[ticket]][4]},
            {"name": f"received/{ordinal:06d}/received.private.json", "bytes": 1,
                "sha256": h.received[evidence[0]][6]},
            {"name": f"responses/{ordinal:06d}/attempt-body.raw", "bytes": len(h.raw), "sha256": hash_bytes(h.raw)},
            {"name": f"responses/{ordinal:06d}/attempt-receipt.private.json", "bytes": 1, "sha256": "9" * 64}])
    filenames = {"inventory": "inventory.private.json", "provisional": "provisional.json", "closed": "closed.json"}
    for cap in finals:
        role, digest, origin = h.finals[cap][2:5]
        rows.append({"name": "final_" + role + "/" + filenames[role], "bytes": len(origin[4]), "sha256": digest})
    h.member_rows = sorted(rows, key=lambda row: row["name"])
    manifest = final("manifest"); raw = h.finals[manifest][4][4]
    h.terminal = (h.op, h.candidate, object(), object(), h.claim,
        tuple(h.starts[ticket] for ticket in h.tickets), bound[4], bound[5], tuple(finals), raw,
        hash_bytes(raw), "2026-10-27T00:00:02Z", object(), "a" * 64)
    h.live = False
    h.issue = lambda: reader._issue_original_closed_chunk(h.op, h.candidate)
    return h


def test_original_terminal_witness_returns_exact_seven_bound_accounting_fields(chunk):
    h = chunk; closed = h.issue(); account = reader.closed_count_chunk_accounting(closed)
    assert len(account) == 7 and account[0] is h.budget.budget_identity and account[1] is h.plan
    assert account[2] == 1 and all(left is right for left, right in zip(account[3], h.tickets))
    assert account[4] == tuple(len(h.raw) for unused in h.tickets)
    assert account[5] == h.plan.chunk_positions(1) and account[6] == h.terminal[10]
    assert reader.authority()["source_admitted"] is reader.authority()["ready_for_backtest"] is False


def test_outer_terminal_cannot_be_replaced_by_live_pair_or_provisional_controls(chunk):
    h = chunk; h.live = True
    with pytest.raises(AssertionError): h.issue()
    h.live = False
    with pytest.raises(transport.CountTransportRefusal): h.issue()
    assert reader._ISSUED == {}


def test_arbitrary_constructor_copy_and_complete_fields_cannot_mint_witness(chunk):
    with pytest.raises(reader.ClosedCountChunkRefusal): reader.ClosedCountChunk()
    forged = object.__new__(reader.ClosedCountChunk)
    forged._anchor = forged._identity = ("complete", True, chunk.terminal[10])
    with pytest.raises(reader.ClosedCountChunkRefusal): reader.closed_count_chunk_accounting(forged)


@pytest.mark.parametrize("kind", ["missing", "extra_negative", "self", "duplicate", "hash", "partial_ticket"])
def test_complete_FINAL_manifest_and_original_roster_are_required(chunk, kind):
    h = chunk; original = list(h.terminal)
    if kind == "partial_ticket": original[5] = original[5][:-1]
    else:
        value = reader._parse(original[9]); rows = value["payload"]["members"]
        if kind == "missing": rows.pop()
        elif kind == "extra_negative": rows.append({"name": "run.refused.json", "bytes": 1, "sha256": "a" * 64})
        elif kind == "self": rows.append({"name": "final_manifest/manifest.private.json", "bytes": 1, "sha256": "a" * 64})
        elif kind == "duplicate": rows.append(deepcopy(rows[0]))
        elif kind == "hash": original[10] = "0" * 64
        if kind != "hash":
            raw = canonical_json(value).encode(); original[9], original[10] = raw, hash_bytes(raw)
    h.terminal = tuple(original)
    with pytest.raises(reader.ClosedCountChunkRefusal): h.issue()
    assert reader._ISSUED == {}


def test_recorded_attempts_are_not_resolved_transport_coverage(chunk):
    h = chunk; original = list(transport._CANDIDATES[h.candidate]); original[6] = ()
    # Explicit private-registry fault injection, not a public authority path.
    transport._CANDIDATES[h.candidate] = tuple(original)
    with pytest.raises(transport.CountTransportRefusal): h.issue()


def test_original_terminal_revalidation_cannot_be_swapped_after_witness(chunk):
    h = chunk; closed = h.issue(); h.terminal = tuple([*h.terminal])
    with pytest.raises(reader.ClosedCountChunkRefusal): reader.closed_count_chunk_accounting(closed)
    with pytest.raises(reader.ClosedCountChunkRefusal): reader.closed_count_chunk_accounting(closed)


def test_witness_origin_is_single_issuance_not_multiple_capacity_releases(chunk):
    h = chunk; h.issue()
    with pytest.raises(reader.ClosedCountChunkRefusal, match="reused_origin"): h.issue()


def test_fixed_failure_projection_never_formats_source_body_or_exception_text():
    value = reader.failure_summary(RuntimeError("PRIVATE TOKEN BODY AND URL"))
    assert value == {"category": "unknown_local_error", "contract_code": None, "errno_name": None}
