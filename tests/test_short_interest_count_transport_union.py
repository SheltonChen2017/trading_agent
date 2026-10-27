"""Genuine toy ledger/plan/budget/operator/reader; explicit fake IO terminals.

The original reader fixture supplies named fabricated source, storage, wire,
control and outer-terminal registries. No actual archive, source admission,
native flag, image, keychain or HTTP operation is proved by these tests.
"""
from copy import deepcopy

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_transport_union as union
from scripts import short_interest_closed_count_chunk as reader
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_count_durable_budget as accounting
from test_short_interest_count_durable_transport import operation, isolated_registries_and_no_network
from test_short_interest_closed_count_chunk import chunk as first_chunk


@pytest.fixture(autouse=True)
def fresh_union_registries(monkeypatch):
    for name in ("_CONTRIBUTIONS", "_PRIVATE_PROOFS", "_CLOSED_ORIGINS", "_UNIONS"):
        monkeypatch.setattr(union, name, {})
    monkeypatch.setattr(union, "_FAILED", set()); monkeypatch.setattr(union, "_UNION_FAILED", set())


def first_contribution(h):
    closed = h.issue()
    return closed, union.freeze_closed_count_transport_contribution(closed)


def next_closed_chunk(h):
    """Advance via original budget/operation/reader factories, fake control IO.

    This copies only the original reader test's explicit terminal publisher
    seam for the SECOND toy chunk. No source/control/FS witness is invented
    by the production union module and no original seven-field value is cast.
    """
    h.live = True
    h.tickets = tuple(h.budget.reserve_start_slot(position)
        for position in h.plan.chunk_positions(h.budget.public_summary()["current_chunk"]))
    claim_type, start_type = type(h.claim), type(next(iter(h.starts.values())))
    h.op = transport.bind_registered_operation(h.lease, h.budget)
    h.op.authorize_start_batch(h.tickets)
    op = transport.operation_binding(h.op)
    h.claim = claim_type()
    h.claims[h.claim] = (h.claim, h.op, h.budget, h.plan, op[4], op[5], "f" * 64, op[6],
        None, None, "2026-10-27T00:00:00Z", object())
    h.starts = {}
    for ticket in h.tickets:
        start = start_type(); original = accounting.ticket_binding(ticket)
        h.start_bindings[start] = (start, h.op, ticket, h.claim, hash_payload([original[9], "START"]),
            original[8], op[5], h.claims[h.claim][6], "2026-10-27T00:00:00Z", None, None, object())
        h.starts[ticket] = start
    for ticket in h.tickets: h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket]))
    return finish_fabricated_terminal(h)


def finish_fabricated_terminal(h):
    """Original reader fixture's explicit control/whole-storage terminal seam."""
    h.candidate = h.op.freeze_provisional_root(); candidate = transport.provisional_candidate_binding(h.candidate)
    finals = []
    class Final: pass
    def final(role):
        raw = transport._final_control_payload(h.op, h.candidate, role)
        value = Final(); origin = (None, None, None, role, raw, hash_bytes(raw), None, None, None,
            None, None, None, None, None, None)
        h.finals[value] = value, h.op, role, hash_bytes(raw), origin, None, h.candidate, object()
        h.op.accept_final_control(value); finals.append(value)
        return value
    for role in transport.FINAL_ROLES[:-1]: final(role)
    rows = []
    for ticket, observed, evidence in zip(h.tickets, candidate[4], candidate[5]):
        number = accounting.ticket_binding(ticket)[4]
        rows.extend([{"name": f"starts/{number:06d}/START.spent.json", "bytes": 1,
                "sha256": h.start_bindings[h.starts[ticket]][4]},
            {"name": f"received/{number:06d}/received.private.json", "bytes": 1,
                "sha256": h.received[evidence[0]][6]}])
        if evidence[1] is not None:
            observed_origin = transport.http_observation_binding(observed)
            rows.extend([{"name": f"responses/{number:06d}/response.raw", "bytes": len(observed_origin[10]),
                    "sha256": hash_bytes(observed_origin[10])},
                {"name": f"responses/{number:06d}/response.receipt.private.json", "bytes": 1, "sha256": "9" * 64}])
    filenames = {"inventory": "inventory.private.json", "provisional": "provisional.json", "closed": "closed.json"}
    for value in finals:
        role, digest, origin = h.finals[value][2:5]
        rows.append({"name": "final_" + role + "/" + filenames[role], "bytes": len(origin[4]), "sha256": digest})
    h.member_rows = sorted(rows, key=lambda row: row["name"])
    manifest = final("manifest"); raw = h.finals[manifest][4][4]
    h.terminal = (h.op, h.candidate, object(), object(), h.claim,
        tuple(h.starts[ticket] for ticket in h.tickets), candidate[4], candidate[5], tuple(finals), raw,
        hash_bytes(raw), "2026-10-27T00:00:02Z", object(), "a" * 64)
    h.live = False
    return reader._issue_original_closed_chunk(h.op, h.candidate)


def all_settled(h):
    first, c1 = first_contribution(h); h.budget.settle_closed_chunk(first)
    second = next_closed_chunk(h); c2 = union.freeze_closed_count_transport_contribution(second)
    h.budget.settle_closed_chunk(second)
    return first, second, (c1, c2)


def test_original_immediate_contribution_retains_private_bytes_and_redacted_identity(first_chunk):
    h = first_chunk; closed, cap = first_contribution(h)
    original = union.contribution_binding(cap)
    assert len(original) == 10 and original[1] is h.plan._parts[1] and original[2] is h.plan
    assert original[3] is h.budget and original[4] is h.budget.budget_identity
    assert original[5] is reader._ISSUED[closed][4] and original[6] is closed
    assert original[8] == cap.sha256 == hash_bytes(original[7])
    report = cap.public_summary()
    assert report["START_debits"] == len(h.tickets) and report["charged_response_bytes"] == len(h.raw) * len(h.tickets)
    assert report["authority"]["source_admitted"] is report["authority"]["count_source_qualified"] is False
    assert "results" not in canonical_json(report)
    proofs = union._PRIVATE_PROOFS[cap]
    assert all(item[5] is item[1][10] for item in proofs[1])
    assert all(not hasattr(cap, name) for name in ("read_body", "iter_counts", "iter_cells", "private_payload"))
    report["START_debits"] = 0
    assert cap.public_summary()["START_debits"] == len(h.tickets)


def test_snapshot_refuses_unclosed_or_forged_reader_values_before_mint(first_chunk):
    h = first_chunk
    with pytest.raises(union.CountTransportUnionRefusal): union.ClosedCountTransportContribution()
    with pytest.raises(union.CountTransportUnionRefusal): union.CountTransportUnion()
    for value in (True, {}, object(), h.candidate):
        with pytest.raises(union.CountTransportUnionRefusal): union.freeze_closed_count_transport_contribution(value)
    fake = object.__new__(reader.ClosedCountChunk); fake._anchor = fake._identity = ("complete", True)
    with pytest.raises(reader.ClosedCountChunkRefusal): union.freeze_closed_count_transport_contribution(fake)
    assert union._CONTRIBUTIONS == {}


@pytest.mark.parametrize("slot", ["__hash__", "__eq__"])
def test_changed_original_reader_identity_slots_refuse_before_any_lookup_callback(first_chunk, monkeypatch, slot):
    closed = first_chunk.issue(); calls = []
    if slot == "__hash__":
        def changed(value): calls.append(True); return object.__hash__(value)
    else:
        def changed(value, other): calls.append(True); return value is other
    monkeypatch.setattr(reader.ClosedCountChunk, slot, changed)
    with pytest.raises(union.CountTransportUnionRefusal, match="original_chunk_required"):
        union.freeze_closed_count_transport_contribution(closed)
    assert calls == [] and union._CONTRIBUTIONS == {}


def test_replaced_reader_class_cannot_supply_foreign_lookup_methods(monkeypatch):
    calls = []
    class Foreign:
        def __hash__(self): calls.append(True); return 1
    monkeypatch.setattr(reader, "ClosedCountChunk", Foreign)
    with pytest.raises(union.CountTransportUnionRefusal, match="original_chunk_required"):
        union.freeze_closed_count_transport_contribution(Foreign())
    assert calls == [] and union._CONTRIBUTIONS == {}


def test_original_closed_chunk_is_snapshotted_once_not_relabelled(first_chunk):
    h = first_chunk; closed, cap = first_contribution(h)
    with pytest.raises(union.CountTransportUnionRefusal, match="duplicate_chunk"):
        union.freeze_closed_count_transport_contribution(closed)
    assert union.contribution_binding(cap)[6] is closed


def test_new_retry_negative_debit_and_lifetime_identity_survive_semantic_snapshot(operation):
    h = operation; first, second = h.tickets
    h.failure = transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True)
    h.receive(h.op.dispatch(first, h.claim, h.starts[first]))
    h.failure = None; h.tick += 2
    h.receive(h.op.dispatch(second, h.claim, h.starts[second]))
    retry = h.retry_ticket(accounting.ticket_binding(first)[5])
    h.op.authorize_start_batch((retry,))
    h.receive(h.op.dispatch(retry, h.claim, h.starts[retry])); h.tickets = (first, second, retry)
    closed = finish_fabricated_terminal(h)
    cap = union.freeze_closed_count_transport_contribution(closed)
    original = union.contribution_binding(cap); summary = cap.public_summary()
    assert original[5][4] == (2097152, len(h.raw), len(h.raw))
    assert summary["START_debits"] == 3 and summary["unknown_full_page_START_debits"] == 1
    assert summary["unknown_full_page_charged_bytes"] == 2097152
    assert summary["covered_transport_positions"] == 2 and summary["retained_raw_attempts"] == 2
    assert accounting.ticket_binding(retry)[7] == accounting.ticket_binding(first)[7] + 1
    assert union._PRIVATE_PROOFS[cap][1][0][5] is None


def test_original_window_must_still_pass_before_semantic_snapshot(first_chunk, monkeypatch):
    h = first_chunk; closed = h.issue()
    def expired(*args): raise RuntimeError("FABRICATED_EXPIRED_TERMINAL_NO_SOURCE")
    monkeypatch.setattr(h.coordinator, "terminal_chunk_binding", expired)
    with pytest.raises(RuntimeError): union.freeze_closed_count_transport_contribution(closed)
    assert union._CONTRIBUTIONS == {} and closed in reader._FAILED


def test_original_deadline_is_rechecked_after_snapshot_preparation_before_issuance(first_chunk, monkeypatch):
    h = first_chunk; closed = h.issue()
    original = reader.closed_count_chunk_accounting; calls = []
    def finite_window(value):
        calls.append(True)
        if len(calls) == 2:
            raise reader.ClosedCountChunkRefusal("REFUSED: closed_chunk_terminal_required")
        return original(value)
    monkeypatch.setattr(reader, "closed_count_chunk_accounting", finite_window)
    with pytest.raises(reader.ClosedCountChunkRefusal): union.freeze_closed_count_transport_contribution(closed)
    assert len(calls) == 2 and union._CONTRIBUTIONS == union._PRIVATE_PROOFS == union._CLOSED_ORIGINS == {}


def test_snapshot_provenance_and_failure_latch_reject_copies_and_resets(first_chunk):
    h = first_chunk; unused, cap = first_contribution(h)
    fake = object.__new__(union.ClosedCountTransportContribution)
    fake._anchor = fake._identity = cap._anchor
    with pytest.raises(union.CountTransportUnionRefusal): union.contribution_binding(fake)
    original = cap._identity; cap._identity = tuple(list(original))
    with pytest.raises(union.CountTransportUnionRefusal): union.contribution_binding(cap)
    cap._identity = original
    with pytest.raises(union.CountTransportUnionRefusal): cap.public_summary()


def test_private_original_retention_is_not_reconstructed_from_matching_payload(first_chunk):
    h = first_chunk; unused, cap = first_contribution(h)
    original = union._PRIVATE_PROOFS[cap]
    union._PRIVATE_PROOFS[cap] = tuple(list(original))
    with pytest.raises(union.CountTransportUnionRefusal, match="retention_changed"): cap.public_summary()
    union._PRIVATE_PROOFS[cap] = original
    with pytest.raises(union.CountTransportUnionRefusal): cap.public_summary()


def test_pure_contribution_survives_later_budget_failure_and_expired_lease(first_chunk, monkeypatch):
    h = first_chunk; unused, cap = first_contribution(h); before = cap.public_summary()
    def no_old_context(*args): raise AssertionError("expired operational context was consulted")
    monkeypatch.setattr(reader, "closed_count_chunk_accounting", no_old_context)
    monkeypatch.setattr(h.coordinator, "terminal_chunk_binding", no_old_context)
    h.budget._latch()
    assert cap.public_summary() == before
    assert union.contribution_binding(cap) is cap._anchor


def test_partial_or_unsettled_contributions_cannot_form_full_union(first_chunk):
    h = first_chunk; unused, cap = first_contribution(h); baseline = h.plan._parts[1]
    with pytest.raises(union.CountTransportUnionRefusal, match="incomplete"):
        union.seal_count_transport_union(baseline, h.plan, (cap,), h.budget)
    with pytest.raises(union.CountTransportUnionRefusal, match="original_settlement"):
        union.seal_count_transport_union(baseline, h.plan, (cap, cap), h.budget)
    assert union._UNIONS == {}


def test_full_union_uses_original_irreversible_account7_and_no_expired_context(first_chunk, monkeypatch):
    h = first_chunk; first, second, contributions = all_settled(h)
    settled = accounting.settled_chunk_accounting(h.budget)
    assert settled[3][0] is union.contribution_binding(contributions[0])[5]
    assert settled[3][1] is union.contribution_binding(contributions[1])[5]
    def expired(*args): raise AssertionError("old terminal/lease/volume reentered")
    monkeypatch.setattr(reader, "closed_count_chunk_accounting", expired)
    monkeypatch.setattr(h.coordinator, "terminal_chunk_binding", expired)
    # The normal budget FAILED flag blocks new work, never its prior facts.
    h.budget._latch()
    joined = union.seal_count_transport_union(h.plan._parts[1], h.plan, contributions, h.budget)
    summary = joined.public_summary()
    assert summary["complete_transport_coverage"] is True and summary["transport_position_count"] == 8
    assert summary["historical_START_debits"] == 6 and summary["new_START_debits"] == 4
    assert summary["cumulative_START_debits"] == 10 and summary["closed_settled_chunks"] == 2
    assert summary["new_charged_bytes"] == 4 * len(h.raw)
    assert summary["any_count_source_qualified"] is summary["authority"]["ready_for_backtest"] is False
    summary["transport_position_count"] = 0
    assert joined.public_summary()["transport_position_count"] == 8
    monkeypatch.setattr(accounting, "settled_chunk_accounting", expired)
    assert joined.public_summary()["transport_position_count"] == 8
    with pytest.raises(union.CountTransportUnionRefusal, match="capacity_exhausted"):
        union.seal_count_transport_union(h.plan._parts[1], h.plan, contributions, h.budget)


@pytest.mark.parametrize("kind", ["reverse", "duplicate", "copied_account", "missing_account"])
def test_union_rejects_replay_reordering_or_fresh_account_payloads(first_chunk, monkeypatch, kind):
    h = first_chunk; unused, unused2, contributions = all_settled(h)
    if kind == "reverse": contributions = contributions[::-1]
    elif kind == "duplicate": contributions = (contributions[0], contributions[0])
    else:
        original = accounting.settled_chunk_accounting(h.budget)
        accounts = original[3][:-1] if kind == "missing_account" else (tuple(list(original[3][0])), original[3][1])
        monkeypatch.setattr(accounting, "settled_chunk_accounting", lambda value: (*original[:3], accounts))
    with pytest.raises(union.CountTransportUnionRefusal):
        union.seal_count_transport_union(h.plan._parts[1], h.plan, contributions, h.budget)
    assert union._UNIONS == {}


def test_unions_are_factory_issued_and_permanent_failure_vetoes_reflection(first_chunk):
    h = first_chunk; unused, unused2, contributions = all_settled(h)
    joined = union.seal_count_transport_union(h.plan._parts[1], h.plan, contributions, h.budget)
    original = joined._identity; joined._identity = tuple(list(original))
    with pytest.raises(union.CountTransportUnionRefusal): joined.public_summary()
    joined._identity = original
    with pytest.raises(union.CountTransportUnionRefusal): joined.public_summary()


def test_policy_caps_no_IO_or_source_admission_and_fixed_safe_errors():
    value = union.policy()
    assert (value["maximum_contributions"], value["maximum_unions"]) == (133, 1)
    assert value["maximum_cumulative_STARTs"] == 84005 and value["maximum_cumulative_bytes"] == 4 * 1024 ** 3
    assert value["restart_reload_authority"] is False
    assert not any(value["authority"][name] for name in ("source_admitted", "count_source_qualified",
        "denominator_admitted", "actual_input_execution_admitted", "ready_for_backtest"))
    calls = []
    class Hostile:
        def __eq__(self, other): calls.append(True); raise AssertionError("caller comparison")
        def __str__(self): calls.append(True); raise AssertionError("caller formatting")
    assert union.failure_summary(union.CountTransportUnionRefusal(Hostile()))["contract_code"] is None
    assert "PRIVATE_BODY" not in canonical_json(union.failure_summary(RuntimeError("PRIVATE_BODY")))
    assert calls == []


def test_finite_contribution_registry_cannot_grow_a_134th_entry(first_chunk, monkeypatch):
    h = first_chunk; closed = h.issue()
    # Explicit saturated registry bookkeeping seam, not forged contribution
    # authority. The capacity gate must refuse before inspecting any member.
    monkeypatch.setattr(union, "_CONTRIBUTIONS", {object(): None for unused in range(133)})
    with pytest.raises(union.CountTransportUnionRefusal, match="capacity_exhausted"):
        union.freeze_closed_count_transport_contribution(closed)
    assert len(union._CONTRIBUTIONS) == 133 and not union._CLOSED_ORIGINS


@pytest.mark.parametrize("name,value", [("MAXIMUM_CONTRIBUTIONS", 134), ("MAXIMUM_CUMULATIVE_STARTS", 84006),
    ("MAXIMUM_CUMULATIVE_BYTES", 4294967297), ("MAXIMUM_UNIONS", True)])
def test_literal_policy_cannot_expand_or_bool_cast_source_bounds(monkeypatch, name, value):
    monkeypatch.setattr(union, name, value)
    with pytest.raises(union.CountTransportUnionRefusal, match="policy_changed"): union.policy()
