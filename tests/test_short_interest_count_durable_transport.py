"""Genuine toy budget/query types; explicitly fabricated lease/wire/control IO.

No source archive, credential reader, network, image or native setter is used.
The fake lease/controls are named test-only registration/custody seams, not
operational closure or source authority.
"""
import _thread
from types import SimpleNamespace
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import http.client
from io import BytesIO
from datetime import date, timedelta

import pytest

from data.hashing import hash_bytes, hash_payload

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

from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_count_durable_budget as budget_module
from test_short_interest_count_durable_budget import genuine_plan, isolated_registries_and_no_network
from test_short_interest_body_receipt_custody import kernel


def genuine_headers(*pairs):
    headers = http.client.HTTPMessage()
    for name, value in pairs: headers[name] = value
    return headers


@pytest.fixture
def operation(monkeypatch, tmp_path, request):
    for name, value in (("_OPERATIONS", {}), ("_FAILED", set()), ("_OBSERVATIONS", {}),
        ("_TERMINALS", {}), ("_CANDIDATES", {}), ("_RESPONSE_CAPS", {}), ("_RECEIVED_CAPS", {}),
        ("_FINAL_CAPS", {}), ("_WINDOWS", {}), ("_VOLUMES", {}), ("_DRAINED", {}),
        ("_DOWNGRADES", {}), ("_DRAIN_ORIGINS", {}), ("_OBS_COMPLETED", {}), ("_WIRE_RESULTS", {}),
        ("_WIRE_ERROR_HOLD", {}), ("_OBS_WIRE", {}), ("_REMOTE_BATCHES", {}),
        ("_START_PERMISSIONS", {}), ("_START_CONSUMED", set())):
        monkeypatch.setattr(transport, name, value)
    for name in ("_CAP_INDEXES", "_CAP_INDEX_PINS", "_CAP_INDEX_MINTS"):
        monkeypatch.setattr(transport, name, {})
    plan = genuine_plan(monkeypatch)
    budget = budget_module.open_durable_count_budget(plan)
    tickets = tuple(budget.reserve_start_slot(position) for position in plan.chunk_positions(1))
    h = SimpleNamespace(plan=plan, budget=budget, tickets=tickets, tick=100.0, wire_calls=[],
        key_calls=[], live=True, source_checks=0, failure=None, raw=b'{"results":[]}', status=200)
    monkeypatch.setattr(transport, "ROOT", tmp_path)
    monkeypatch.setattr(transport, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(transport, "PROTOCOL_SHA256", hash_payload(transport.policy()))
    monkeypatch.setattr(transport.time, "monotonic", lambda: h.tick)
    # Explicit fabricated registration: no actual source or Git route is run.
    monkeypatch.setattr(transport, "_registered", lambda *args: None)
    monkeypatch.setattr(transport, "_capacity_before_dispatch", lambda operation, ticket: None)  # Explicit fake physical-volume seam.
    class Lease: pass
    h.lease = Lease()
    source = (h.lease, tmp_path, "c" * 40, "b" * 40, plan, budget,
        plan._parts[1]._parts[1].query_plan, (("fabricated.py", "d" * 64),), "e" * 64,
        transport.SOURCE_AUTHORITY_SHA256, transport.PROTOCOL_SHA256, tmp_path / "mounted" / "capture",
        _thread.RLock(), "2026-10-27T00:00:00Z", h.tick, object())
    def live(lease):
        assert lease is h.lease and h.live
        h.source_checks += 1
        return source
    h.terminal = None; h.member_rows = []
    def terminal(op, candidate):
        assert not h.live and h.terminal is not None
        return h.terminal
    h.coordinator = SimpleNamespace(CountSourceLease=Lease, source_lease_binding=lambda lease: source,
        source_lease_live_binding=live, source_lease_terminal_binding=lambda lease: source,
        terminal_chunk_binding=terminal, final_member_rows=lambda op, candidate: h.member_rows)
    class SourceBatch: pass
    h.source_batches, h.refresh_calls, h.remote_ref = {}, [], source[3]
    def refresh(lease, op, tickets):
        assert lease is h.lease and op is h.op
        h.refresh_calls.append(tickets)
        if h.remote_ref != source[3]:
            raise transport.CountTransportRefusal("REFUSED: count_operator_START_permission_changed")
        value = SourceBatch()
        original = value, op, source, transport.operation_binding(op), tickets, object(), "a" * 64, object()
        value._anchor = value._identity = original; h.source_batches[value] = original; return value
    def source_batch(value):
        original = h.source_batches.get(value)
        assert type(value) is SourceBatch and original is value._anchor is value._identity
        return original
    h.coordinator.SourceStartBatchEvidence = SourceBatch
    h.coordinator.source_lease_authorize_start_batch = refresh
    h.coordinator.source_start_batch_binding = source_batch
    monkeypatch.setattr(transport, "_coordinator", lambda: h.coordinator)
    h.op = transport.bind_registered_operation(h.lease, budget)
    class Claim: pass
    class Start: pass
    class Received: pass
    class Response: pass
    class Final: pass
    claims, starts, received, responses, finals = {}, {}, {}, {}, {}
    h.claim = Claim(); op = transport.operation_binding(h.op)
    claims[h.claim] = (h.claim, h.op, budget, plan, 1, op[5], "f" * 64, op[6], None, None, source[13], object())
    for ticket in tickets:
        value = Start(); original = budget_module.ticket_binding(ticket)
        starts[value] = (value, h.op, ticket, h.claim, hash_payload([original[9], "START"]),
            original[8], op[5], claims[h.claim][6], source[13], None, None, object())
    h.starts = {value[2]: cap for cap, value in starts.items()}
    h.controls = SimpleNamespace(CountReceived=Received, claim_binding=lambda cap: claims[cap],
        start_binding=lambda cap: starts[cap], received_binding=lambda cap: received[cap],
        final_control_binding=lambda cap: finals[cap])
    h.responses = SimpleNamespace(CountResponseCustody=Response, response_binding=lambda cap: responses[cap])
    monkeypatch.setattr(transport, "_controls", lambda: h.controls)
    monkeypatch.setattr(transport, "_responses", lambda: h.responses)
    def key(name):
        assert name == "massive"; h.key_calls.append(name)
        return transport.KeychainSecret("FAKE_UNIT_SECRET_DO_NOT_PUBLISH")
    monkeypatch.setattr(transport, "read_named_keychain", key)
    monkeypatch.setattr(transport, "_clock", lambda: "2026-10-27T00:00:01Z")
    class WireResponse:
        def __init__(self, raw):
            self.raw, self.offset, self.status = raw, 0, h.status
            self.headers = genuine_headers(("Content-Type", "application/json"), ("Content-Length", str(len(raw))))
            self.read_calls = []
        def read(self, maximum):
            self.read_calls.append(maximum)
            piece = self.raw[self.offset:self.offset + maximum]; self.offset += len(piece); return piece
        def close(self): pass
    def open_wire(request, *, timeout):
        assert request.get_method() == "GET" and timeout == 30
        assert request.get_header("Authorization").startswith("Bearer ")
        h.wire_calls.append(True)
        if h.failure is not None: raise h.failure
        return WireResponse(h.raw)
    opener = SimpleNamespace(open=open_wire)
    h.opener, h.response = opener, WireResponse
    monkeypatch.setattr(transport.legacy.transport, "build_protected_opener", lambda: opener)
    monkeypatch.setattr(transport.legacy.transport, "_opener", lambda value: None if value is opener else pytest.fail("bad opener"))
    def receive(observation):
        bound = transport.http_observation_binding(observation); ticket = bound[2]
        got = Received(); received[got] = (got, h.op, ticket, observation, h.claim, bound[4],
            hash_payload([bound[14], "received"]), None, None, bound[12], bound[7], object())
        h.op.accept_received_control(got)
        pair = None
        if type(bound[10]) is bytes and bound[10]:
            pair = Response(); responses[pair] = (pair, h.op, ticket, observation, h.claim, bound[4],
                hash_bytes(bound[10]), len(bound[10]), "9" * 64, None, None, object(), object())
            h.op.accept_closed_response(pair)
        return got, pair
    h.receive, h.claims, h.start_bindings, h.received, h.response_bindings, h.finals = receive, claims, starts, received, responses, finals
    def retry_ticket(position):
        ticket = budget.reserve_start_slot(position); value = Start(); original = budget_module.ticket_binding(ticket)
        starts[value] = (value, h.op, ticket, h.claim, hash_payload([original[9], "START"]), original[8],
            op[5], claims[h.claim][6], source[13], None, None, object())
        h.starts[ticket] = value
        return ticket
    h.retry_ticket = retry_ticket
    if getattr(request, "param", True): h.op.authorize_start_batch(h.tickets)
    return h


def test_default_source_registration_refuses_before_key_wire_or_storage(monkeypatch):
    calls = []
    monkeypatch.setattr(transport, "read_named_keychain", lambda name: calls.append("key"))
    with pytest.raises(transport.CountTransportRefusal, match="registration_pending"):
        with transport.open_registered_operation(transport.ROOT, budget=object(), runtime_head="a" * 40,
                actual_remote="b" * 40, complete_code_manifest={}): pytest.fail("unregistered operator")
    assert calls == []


def _genuine_512_missing_plan(monkeypatch):
    """Fabricated516-anchor domain; every plan/ledger/ticket uses its factory."""
    import test_short_interest_count_durable_budget as support
    epoch, research, historical = support.support.support, support.budget.research_budget, support.support.historical
    parallel, references = epoch.parallel, epoch.references
    ceiling = 515 * parallel.MAXIMUM_RESPONSE_BYTES
    dates = tuple((date(2022, 1, 3) + timedelta(days=offset)).isoformat() for offset in range(516))
    # Alternating FABRICATED class identity makes each daily cell a genuine
    # new anchor instead of asking the source model to bypass quarterly reuse.
    reports = tuple(epoch.fabricated.identity(at, class_id=(epoch.fabricated.CLASS
        if index % 2 == 0 else epoch.fabricated.NEXT_CLASS)) for index, at in enumerate(dates))
    source = epoch.fabricated.plan(dates, reports=reports)
    assert len(source.query_plan.to_payload()["selected_query_ordinals"]) == 516
    for name, value in {"ORIGINAL_COUNT": 516, "MAXIMUM_CUMULATIVE_STARTS": 517,
            "MAXIMUM_CUMULATIVE_BYTES": ceiling, "PARENT_STARTED": 3, "PARENT_HTTP": 2,
            "PARENT_RAW": 2, "RECOVERY_STARTED": 3, "RECOVERY_HTTP": 3, "RECOVERY_RAW": 2,
            "FAILED_PARENT_POSITION": 2, "ANCHOR_PLAN_SHA256": source.sha256}.items():
        monkeypatch.setattr(historical, name, value)
    parent_plan = parallel.freeze_parallel_count_plan(source.query_plan, maximum_total_response_bytes=ceiling)
    parent = epoch._inventory(parent_plan, 3, 2, offset=0, failed_http=False)
    charged = parent.to_payload()["charged_response_bytes"]
    monkeypatch.setattr(historical, "PARENT_CHARGED_BYTES", charged)
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    queries = references.freeze_native_class_query_plan(source._matrix, mode="explicit_anchors",
        selected_query_ordinals=tuple(selected[position - 1] for position in (2, 4, *range(5, 517))))
    child_plan = parallel.freeze_parallel_count_plan(queries, maximum_total_response_bytes=ceiling - charged)
    child = epoch._inventory(child_plan, 3, 3, offset=20, failed_http=True)
    monkeypatch.setattr(historical, "RECOVERY_CHARGED_BYTES", child.to_payload()["charged_response_bytes"])
    pins = tuple(tuple((label, None if value is None else hash_payload((index, label))) for label, value in row)
        for index, row in enumerate(historical._PROOF_PINS))
    monkeypatch.setattr(historical, "_PROOF_PINS", pins)
    proofs = tuple(tuple((label, value or "a" * 64) for label, value in row) for row in pins)
    ledger = historical.seal_registered_count_epoch_ledger(source, epoch.epochs_from((source, parent, child, proofs)))
    old = ledger.public_summary()
    for name, value in {"BASELINE_LEDGER_SHA256": ledger.sha256, "PRIOR_STARTS": old["START_debits"],
            "PRIOR_CHARGED_BYTES": old["charged_response_bytes"], "HISTORICAL_START_CEILING": 517,
            "MAXIMUM_CUMULATIVE_STARTS": 534, "MAXIMUM_CUMULATIVE_BYTES": ceiling,
            "MISSING_POSITIONS": 512, "POSITIONS_PER_CHUNK": 512, "MAXIMUM_CHUNKS": 1,
            "EXTRA_ATTEMPTS_PER_CHUNK": 16, "_PLAN_MINTS": {}, "_BUDGET_MINTS": {}, "_PLAN_KEYS": set()}.items():
        monkeypatch.setattr(research, name, value)
    monkeypatch.setattr(budget_module, "_EXPECTED_SOURCE_PROFILE", budget_module._source_profile())
    return research.freeze_count_recovery_plan(ledger)


def test_512_original_ticket_caps_have_linear_binder_calls_at_accept_and_each_freeze(monkeypatch, tmp_path):
    """Exact real cap CLASSES, explicit fabricated closed-issuer/binder IO.

    This counts semantic validators, not512 physical files or an actual1h
    deadline. Genuine physical custody/mutation is checked separately below.
    No HTTP, key, native kernel, image or source operation is dispatched.
    """
    from scripts import short_interest_count_control_custody as controls
    from scripts import short_interest_count_response_custody as responses
    monkeypatch.setitem(globals(), "genuine_plan", _genuine_512_missing_plan)
    h = operation.__wrapped__(monkeypatch, tmp_path, SimpleNamespace(param=False))
    originals, counts = {}, {"received": 0, "response": 0}
    observations, received_caps, response_caps = [], [], []
    def authenticate(cap, role):
        counts[role] += 1
        original = originals.get(cap)
        transport.require(type(original) is tuple and original[0] is cap
            and cap._anchor is cap._identity is original, "count_operator_observation_changed")
        return original
    h.controls.CountReceived = controls.CountReceived
    h.controls.received_binding = lambda cap: authenticate(cap, "received")
    h.responses.CountResponseCustody = responses.CountResponseCustody
    h.responses.response_binding = lambda cap: authenticate(cap, "response")
    anchor = transport.operation_binding(h.op)
    for ticket in h.tickets:
        query = budget_module.ticket_binding(ticket); start = h.starts[ticket]
        obs = object.__new__(transport.HttpObservation)
        bound = (obs, h.op, ticket, h.claim, start, query[8], h.start_bindings[start][4], anchor[5],
            True, 200, b"SYNTHETIC", "application/json", "2026-10-27T00:00:01Z", None,
            hash_payload(("fabricated_observation", query[4])), object())
        obs._anchor = obs._identity = bound; transport._OBSERVATIONS[obs] = bound; observations.append(obs)
        got = object.__new__(controls.CountReceived)
        receipt = got, h.op, ticket, obs, h.claim, start, hash_payload((query[4], "receipt")), object(), object(), bound[12], anchor[5], object()
        got._anchor = got._identity = receipt; originals[got] = receipt; received_caps.append(got)
        pair = object.__new__(responses.CountResponseCustody)
        body = pair, h.op, ticket, obs, h.claim, start, hash_bytes(bound[10]), len(bound[10]), "9" * 64, object(), object(), object(), object()
        pair._anchor = pair._identity = body; originals[pair] = body; response_caps.append(pair)
    state = transport._OPERATIONS[h.op][1]
    transport._OPERATIONS[h.op] = anchor, (state[0], h.tickets, (), tuple(observations), None, None)
    for received, response in zip(received_caps, response_caps):
        h.op.accept_received_control(received); h.op.accept_closed_response(response)
    assert counts == {"received": 512, "response": 512}
    assert len(transport._CAP_INDEX_MINTS) == 1  # No retained quadratic map history.
    for unused in range(2):
        before = dict(counts)
        candidate = h.op.freeze_provisional_root()
        assert counts == {name: value + 512 for name, value in before.items()}
        # The separately requested candidate authenticator STILL performs its
        # own mandatory complete pass; indexing never caches a complete flag.
        bound = transport.provisional_candidate_binding(candidate)
        assert len(bound[3]) == len(bound[4]) == len(bound[5]) == len(bound[6]) == 512
        assert counts == {name: value + 1024 for name, value in before.items()}
    assert h.wire_calls == h.key_calls == []


@pytest.mark.parametrize("change", ["copy", "nonce", "mutable", "roster"])
def test_forged_or_copied_custody_indexes_never_mint_provisional_root(operation, change):
    h = operation
    for ticket in h.tickets: h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket]))
    original = transport._CAP_INDEXES[h.op]
    if change == "copy": transport._CAP_INDEXES[h.op] = tuple(list(original))
    elif change == "roster": transport._RECEIVED_CAPS[h.op] = tuple(list(original[1]))
    else:
        mutated = list(original)
        if change == "nonce": mutated[7] = object()
        else: mutated[3] = dict(original[3])
        transport._CAP_INDEXES[h.op] = transport._CAP_INDEX_PINS[h.op] = tuple(mutated)
    with pytest.raises(transport.CountTransportRefusal, match="observation_changed"):
        h.op.freeze_provisional_root()
    assert not transport._CANDIDATES and h.op in transport._FAILED


@pytest.mark.parametrize("kind", ["received", "response"])
@pytest.mark.parametrize("copy_cap", [False, True])
def test_duplicate_ticket_cap_is_rejected_without_reauditing_prior_caps(operation, kind, copy_cap):
    h = operation; obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    got, pair = h.receive(obs)
    cap = got if kind == "received" else pair
    if copy_cap:
        registry = h.received if kind == "received" else h.response_bindings
        duplicate = type(cap)(); registry[duplicate] = (duplicate, *registry[cap][1:]); cap = duplicate
    with pytest.raises(transport.CountTransportRefusal, match="observation_changed"):
        (h.op.accept_received_control if kind == "received" else h.op.accept_closed_response)(cap)
    assert h.op in transport._FAILED and not transport._CANDIDATES


@pytest.mark.parametrize("kind", ["received", "response"])
def test_foreign_cap_type_is_refused_before_any_custody_validator(operation, monkeypatch, kind):
    h = operation; calls = []
    owner, name = (h.controls, "received_binding") if kind == "received" else (h.responses, "response_binding")
    monkeypatch.setattr(owner, name, lambda cap: calls.append(cap))
    with pytest.raises(transport.CountTransportRefusal, match="observation_changed"):
        (h.op.accept_received_control if kind == "received" else h.op.accept_closed_response)(object())
    assert not calls and not transport._CANDIDATES


def test_reentrant_index_replacement_during_full_authentication_cannot_mint_root(operation, monkeypatch):
    h = operation
    for ticket in h.tickets: h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket]))
    original = h.controls.received_binding; changed = [False]
    def validate(cap):
        result = original(cap)
        if not changed[0]:
            changed[0] = True; transport._CAP_INDEXES[h.op] = tuple(list(transport._CAP_INDEXES[h.op]))
        return result
    monkeypatch.setattr(h.controls, "received_binding", validate)
    with pytest.raises(transport.CountTransportRefusal, match="observation_changed"):
        h.op.freeze_provisional_root()
    assert changed[0] and not transport._CANDIDATES and h.op in transport._FAILED


def test_direct_index_constructor_cannot_remint_a_copied_original_roster(operation):
    h = operation
    for ticket in h.tickets: h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket]))
    original = transport._CAP_INDEXES[h.op]
    with pytest.raises(transport.CountTransportRefusal, match="observation_changed"):
        transport._issue_cap_indexes(h.op, original[0], tuple(list(original[1])), tuple(list(original[2])),
            original[5], original[6])
    assert transport._CAP_INDEXES[h.op] is original and len(transport._CAP_INDEX_MINTS) == 1


def test_every_freeze_reauthenticates_late_original_physical_nine_field_seal(operation, kernel, monkeypatch):
    import os
    import test_short_interest_count_response_custody as physical
    physical.response_registry.__wrapped__(monkeypatch)
    h = physical.h.__wrapped__(operation, kernel, monkeypatch)
    for ticket in h.tickets:
        pair, unused = physical.close_response(h, ticket)
        h.op.accept_closed_response(pair)
    first = h.response_path(h.tickets[0]) / physical.custody.BODY_NAME
    h.op.freeze_provisional_root()  # A prior provisional pass cannot cache completeness.
    os.utime(first, None)
    with pytest.raises(physical.custody.CountResponseRefusal): h.op.freeze_provisional_root()
    assert h.op in transport._FAILED and h.budget in budget_module._FAILED


def test_original_operation_and_HTTP_bindings_are_opaque_and_exact(operation):
    h = operation; op = transport.operation_binding(h.op)
    assert len(op) == 14 and op[1] is h.budget and op[2] is h.plan and op[12] is h.lease
    assert op[11] is h.coordinator.source_lease_binding(h.lease)[12]
    observation = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    bound = transport.http_observation_binding(observation)
    assert len(bound) == 16 and bound[1] is h.op and bound[2] is h.tickets[0]
    assert bound[8] is True and bound[9] == 200 and bound[10] == h.raw
    assert len(h.wire_calls) == 1 and "SECRET" not in repr(observation)
    assert "SECRET" not in repr(h.op) and bound[5] == h.tickets[0].public_summary()["request_sha256"]
    with pytest.raises(transport.CountTransportRefusal): transport.HttpObservation()


@pytest.mark.parametrize("kind", ["404", "timeout"])
def test_negative_wire_observations_never_invent_zero_count_or_retry(operation, kind):
    h = operation
    h.failure = (transport.wire.RecoveryTransportFailure("http_not_200", phase="response", failure_class="http_status", status=404)
        if kind == "404" else transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True))
    observation = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    bound = transport.http_observation_binding(observation)
    assert bound[10] is bound[11] is None and bound[8] is True
    assert bound[9] == (404 if kind == "404" else None)
    assert len(h.wire_calls) == 1 and h.budget.public_summary()["cumulative_charged_plus_reserved_bytes"] > 0
    assert dict(bound[13])["retryable"] is (kind == "timeout")


def test_reusing_original_START_never_causes_second_GET_and_latches(operation):
    h = operation; ticket = h.tickets[0]
    h.op.dispatch(ticket, h.claim, h.starts[ticket])
    with pytest.raises(transport.CountTransportRefusal, match="dispatch_reused"):
        h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert len(h.wire_calls) == 1
    with pytest.raises(transport.CountTransportRefusal): transport.operation_binding(h.op)


def test_secret_echo_is_never_issued_as_a_qualified_body(operation):
    h = operation; h.raw = b'{"echo":"FAKE_UNIT_SECRET_DO_NOT_PUBLISH"}'
    drained = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert type(drained) is transport.UnqualifiedHttpObservation
    assert transport.drained_http_observation_binding(drained)[10] == h.raw
    with pytest.raises(transport.CountTransportRefusal): transport.http_observation_binding(drained)
    assert transport._OBSERVATIONS == {} and not transport._OPERATIONS[h.op][1][2]


def test_local_failure_stops_new_HTTP_but_drains_both_already_started_original_bodies(operation, monkeypatch):
    h = operation; entered = threading.Barrier(3); release = threading.Event()
    def wire(request, *, timeout):
        entered.wait(timeout=5); assert release.wait(timeout=5)
        return h.response(b'{"already_received":true}')
    monkeypatch.setattr(h.opener, "open", wire)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(h.op.dispatch, ticket, h.claim, h.starts[ticket]) for ticket in h.tickets]
        entered.wait(timeout=5)
        transport._latch(h.op)  # Explicit fabricated local custody failure.
        release.set(); observations = [future.result(timeout=5) for future in futures]
    assert len(observations) == len(transport._DRAINED) == 2
    for obs in observations:
        assert type(obs) is transport.UnqualifiedHttpObservation
        assert transport.drained_http_observation_binding(obs)[10] == b'{"already_received":true}'
        with pytest.raises(transport.CountTransportRefusal): transport.http_observation_binding(obs)
    assert not transport._OPERATIONS[h.op][1][2]
    with pytest.raises(transport.CountTransportRefusal): h.op.freeze_provisional_root()
    assert transport._OBSERVATIONS == {}


def test_complete_body_and_received_roster_produces_only_provisional_candidate(operation):
    h = operation
    for ticket in h.tickets: h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket]))
    candidate = h.op.freeze_provisional_root(); original = transport.provisional_candidate_binding(candidate)
    assert original[3] == h.tickets and original[6] == h.plan.chunk_positions(1)
    assert all(len(evidence) == 2 for evidence in original[5])
    with pytest.raises(transport.CountTransportRefusal): h.op.closed_chunk()
    with pytest.raises(transport.CountTransportRefusal): transport.ProvisionalRootClosureCandidate()


def test_prior_qualified_result_remains_available_only_as_unqualified_after_later_failure(operation):
    h = operation; ticket = h.tickets[0]
    original = h.op.dispatch(ticket, h.claim, h.starts[ticket])
    bound = transport.http_observation_binding(original)
    with pytest.raises(transport.CountTransportRefusal):
        transport.downgrade_http_observation_for_preservation(original)
    transport._latch(h.op)  # A later publisher failed, after the first GET returned.
    with pytest.raises(transport.CountTransportRefusal): transport.http_observation_binding(original)
    negative = transport.downgrade_http_observation_for_preservation(original)
    retained = transport.drained_http_observation_binding(negative)
    assert type(negative) is transport.UnqualifiedHttpObservation
    assert all(left is right for left, right in zip(retained[1:15], bound[1:15]))
    assert retained[10] is bound[10] and retained[10] == h.raw
    assert transport.downgrade_http_observation_for_preservation(original) is negative
    with pytest.raises(transport.CountTransportRefusal): transport.http_observation_binding(negative)
    with pytest.raises(transport.CountTransportRefusal): h.op.freeze_provisional_root()
    with pytest.raises(transport.CountTransportRefusal): h.op.dispatch(h.tickets[1], h.claim, h.starts[h.tickets[1]])
    assert len(h.wire_calls) == 1 and h.op in transport._FAILED


def test_downgraded_result_cannot_adopt_replaced_original_registry_tuple(operation):
    h = operation; original = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    transport._latch(h.op)
    negative = transport.downgrade_http_observation_for_preservation(original)
    transport._OBSERVATIONS[original] = tuple(list(transport._OBSERVATIONS[original]))
    with pytest.raises(transport.CountTransportRefusal): transport.drained_http_observation_binding(negative)


def test_received_control_alone_cannot_become_body_coverage(operation):
    h = operation
    for ticket in h.tickets:
        observation = h.op.dispatch(ticket, h.claim, h.starts[ticket]); h.receive(observation)
    transport._RESPONSE_CAPS[h.op] = ()  # Explicit fabricated missing-custody fault.
    with pytest.raises(transport.CountTransportRefusal, match="observation_changed"): h.op.freeze_provisional_root()


def test_backward_or_expired_operator_clock_refuses_before_any_HTTP(operation):
    h = operation; h.tick = 99
    with pytest.raises(transport.CountTransportRefusal, match="clock_refused"):
        h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert h.key_calls == h.wire_calls == []


def test_fixed_payload_root_keeps_external_claim_separate_from_capture_manifest(operation):
    h = operation; base = h.coordinator.source_lease_binding(h.lease)[11]
    assert transport._control_directory(h.op, "claim") == base.parent / "claim"
    assert transport._control_directory(h.op, "start", h.tickets[0]) == base / "starts" / "000001"
    assert transport._control_directory(h.op, "received", h.tickets[0]) == base / "received" / "000001"
    assert transport._control_directory(h.op, "manifest") == base / "final_manifest"


@pytest.mark.parametrize("kind", ["success", "404", "read", "tls"])
def test_retry_after_nonretryable_prior_result_never_reads_another_key_or_GET(operation, kind):
    h = operation; first = h.tickets[0]
    if kind == "404": h.failure = transport.wire.RecoveryTransportFailure("http_not_200", phase="response", failure_class="http_status", status=404)
    elif kind == "read": h.failure = transport.wire.RecoveryTransportFailure("network_failure", phase="read", failure_class="timeout", status=200)
    elif kind == "tls": h.failure = transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="tls")
    h.op.dispatch(first, h.claim, h.starts[first]); ticket = h.retry_ticket(first.public_summary()["source_position"])
    h.tick += 100
    with pytest.raises(transport.CountTransportRefusal, match="retry_chain_refused"):
        h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert len(h.key_calls) == len(h.wire_calls) == 1


@pytest.mark.parametrize("operation", [False], indirect=True)
def test_OPEN_retry_requires_original_completion_backoff_and_new_START(operation):
    h = operation; first = h.tickets[0]
    h.op.authorize_start_batch((first,))
    h.failure = transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True)
    original = h.op.dispatch(first, h.claim, h.starts[first]); ticket = h.retry_ticket(first.public_summary()["source_position"])
    h.tick += 2; h.failure = None
    h.op.authorize_start_batch((ticket,))
    retried = h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert transport.http_observation_binding(original)[9] is None
    assert transport.http_observation_binding(retried)[9] == 200
    assert len(h.wire_calls) == len(h.key_calls) == 2 and h.starts[ticket] is not h.starts[first]
    assert h.budget.public_summary()["new_START_reservations"] == 3


def test_early_OPEN_retry_refuses_before_new_key_or_GET(operation):
    h = operation; first = h.tickets[0]
    h.failure = transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True)
    h.op.dispatch(first, h.claim, h.starts[first]); ticket = h.retry_ticket(first.public_summary()["source_position"])
    h.tick += 1.999
    with pytest.raises(transport.CountTransportRefusal, match="retry_backoff_refused"):
        h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert len(h.key_calls) == len(h.wire_calls) == 1


def test_different_tickets_for_one_position_cannot_dispatch_concurrently(operation, monkeypatch):
    h = operation; first = h.tickets[0]; retry = h.retry_ticket(first.public_summary()["source_position"])
    entered, release = threading.Event(), threading.Event()
    def wire(*args, **kwargs):
        entered.set(); assert release.wait(timeout=5)
        return h.response(h.raw)
    monkeypatch.setattr(h.opener, "open", wire)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.op.dispatch, first, h.claim, h.starts[first]); assert entered.wait(timeout=5)
        try:
            with pytest.raises(transport.CountTransportRefusal, match="retry_chain_refused"):
                h.op.dispatch(retry, h.claim, h.starts[retry])
        finally: release.set()
        assert type(future.result(timeout=5)) is transport.UnqualifiedHttpObservation
    assert len(h.key_calls) == 1


@pytest.mark.parametrize("kind", ["read-prefix", "incomplete-read", "close"])
def test_read_or_close_failure_preserves_every_observed_prefix_only_unqualified(operation, monkeypatch, kind):
    h = operation; returned, partial = b'{"partial":', b'"SYNTHETIC"}'
    class FailedResponse:
        status, headers = 200, genuine_headers(("Content-Type", "application/json"))
        def __init__(self): self.reads, self.closed = 0, False
        def read(self, maximum):
            assert 0 < maximum <= 65536; self.reads += 1
            if self.reads == 1: return returned
            if kind == "read-prefix": raise TimeoutError("PRIVATE_URL_SECRET_EXCEPTION_SENTINEL")
            if kind == "incomplete-read": raise http.client.IncompleteRead(partial, 999)
            return b""
        def close(self):
            self.closed = True
            if kind == "close": raise OSError(5, "PRIVATE_URL_SECRET_EXCEPTION_SENTINEL")
    response = FailedResponse()
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert type(obs) is transport.UnqualifiedHttpObservation and response.closed
    bound = transport.drained_http_observation_binding(obs)
    assert bound[10] == returned + (partial if kind == "incomplete-read" else b"")
    assert dict(bound[13])["retryable"] is False
    assert "SENTINEL" not in str(dict(bound[13])) and "SENTINEL" not in repr(obs)
    with pytest.raises(transport.CountTransportRefusal): transport.http_observation_binding(obs)
    assert h.op in transport._FAILED


@pytest.mark.parametrize("declared", ["exact", "absent", "ambiguous", "transfer-encoded"])
def test_maximum_body_never_reads_MAX_plus_one_and_requires_authoritative_length(operation, monkeypatch, declared):
    h = operation; raw = b"x" * transport.MAXIMUM_RESPONSE_BYTES
    response = h.response(raw); requested = []; original_read = response.read
    if declared == "absent": del response.headers["Content-Length"]
    if declared == "ambiguous":
        del response.headers["Content-Length"]
        response.headers["Content-Length"] = "2097152, 2097152"
    if declared == "transfer-encoded": response.headers["Transfer-Encoding"] = "chunked"
    def read(maximum): requested.append(maximum); return original_read(maximum)
    response.read = read
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    if declared == "exact":
        assert transport.http_observation_binding(obs)[10] == raw
        assert response.offset == sum(requested) == transport.MAXIMUM_RESPONSE_BYTES
    elif declared == "absent":
        assert type(obs) is transport.UnqualifiedHttpObservation
        assert transport.drained_http_observation_binding(obs)[10] == raw
        assert response.offset == sum(requested) == transport.MAXIMUM_RESPONSE_BYTES
    else:
        assert transport.http_observation_binding(obs)[10] is None and requested == []
    assert all(0 < number <= 65536 for number in requested)


def test_truncated_declared_body_is_preserved_and_never_source_retry_evidence(operation, monkeypatch):
    h = operation; response = h.response(b"short"); del response.headers["Content-Length"]
    response.headers["Content-Length"] = "20"
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.drained_http_observation_binding(obs)[10] == b"short"
    assert type(obs) is transport.UnqualifiedHttpObservation
    assert dict(transport.drained_http_observation_binding(obs)[13])["retryable"] is False


@pytest.mark.parametrize("kind", ["CL_conflict", "CL_equal", "CT_duplicate", "TE_duplicate", "CL_and_TE", "CE_gzip", "CE_duplicate"])
def test_duplicate_or_unsupported_original_HTTPMessage_framing_is_rejected_before_body(operation, monkeypatch, kind):
    h = operation; response = h.response(h.raw)
    if kind == "CL_conflict": response.headers["Content-Length"] = "999"
    elif kind == "CL_equal": response.headers["Content-Length"] = str(len(h.raw))
    elif kind == "CT_duplicate": response.headers["Content-Type"] = "text/plain"
    elif kind == "TE_duplicate":
        del response.headers["Content-Length"]
        response.headers["Transfer-Encoding"] = "chunked"; response.headers["Transfer-Encoding"] = "chunked"
    elif kind == "CL_and_TE": response.headers["Transfer-Encoding"] = "chunked"
    elif kind == "CE_gzip": response.headers["Content-Encoding"] = "gzip"
    elif kind == "CE_duplicate":
        response.headers["Content-Encoding"] = "identity"; response.headers["Content-Encoding"] = "identity"
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    bound = transport.http_observation_binding(h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]]))
    assert bound[10] is None and response.read_calls == []
    assert dict(bound[13])["retryable"] is False


def genuine_chunked_response(body, *, transfer="chunked", trailer=b"0\r\n\r\n"):
    raw = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: "
        + transfer.encode("ascii") + b"\r\n\r\n" + f"{len(body):x}".encode() + b"\r\n" + body + b"\r\n" + trailer)
    class FakeSocket:
        def makefile(self, mode): assert mode == "rb"; return BytesIO(raw)
    response = http.client.HTTPResponse(FakeSocket(), method="GET"); response.begin(); return response


@pytest.mark.parametrize("transfer", ["chunked", "ChUnKeD"])
def test_single_chunked_uses_genuine_original_HTTPResponse_decoder_and_bounded_eof(operation, monkeypatch, transfer):
    h = operation; response = genuine_chunked_response(h.raw, transfer=transfer)
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.http_observation_binding(obs)[10] == h.raw and response.fp is None


@pytest.mark.parametrize("kind", ["fake_flag", "subclass", "read_override", "read_code", "other_TE"])
def test_chunked_flag_or_substituted_decoder_cannot_admit_body(operation, monkeypatch, kind):
    h = operation
    if kind == "fake_flag":
        response = h.response(h.raw); del response.headers["Content-Length"]
        response.headers["Transfer-Encoding"] = "chunked"; response.chunked = True; response.length = None
    else:
        response = genuine_chunked_response(h.raw)
        if kind == "subclass":
            class Derived(http.client.HTTPResponse): pass
            response.__class__ = Derived
        elif kind == "read_override": response.read = lambda maximum: pytest.fail("substituted read executed")
        elif kind == "read_code":
            def replacement(self, maximum=None): raise AssertionError("substituted original function code executed")
            monkeypatch.setattr(http.client.HTTPResponse.read, "__code__", replacement.__code__)
        elif kind == "other_TE":
            del response.headers["Transfer-Encoding"]
            response.headers["Transfer-Encoding"] = "gzip"
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    bound = transport.http_observation_binding(h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]]))
    assert bound[10] is None and dict(bound[13])["retryable"] is False


def test_original_HTTPMessage_function_code_cannot_be_replaced_in_place(operation, monkeypatch):
    h = operation; response = h.response(h.raw)
    def replacement(self, name, failobj=None): raise AssertionError("substituted header parser executed")
    monkeypatch.setattr(http.client.HTTPMessage.get_all, "__code__", replacement.__code__)
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    bound = transport.http_observation_binding(h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]]))
    assert bound[10] is None and response.read_calls == []


def test_chunked_exact_MAX_stays_unqualified_without_an_extra_decoded_read(operation, monkeypatch):
    h = operation; raw = b"x" * transport.MAXIMUM_RESPONSE_BYTES
    response = genuine_chunked_response(raw)
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.drained_http_observation_binding(obs)[10] == raw
    assert type(obs) is transport.UnqualifiedHttpObservation


def test_original_HTTPConnection_request_path_inserts_single_identity_encoding_without_socket(operation):
    h = operation; query = transport._query_for_ticket(h.tickets[0])
    request = transport.legacy._wire_request(query, transport.KeychainSecret("FAKE_HEADER_TEST_SECRET"))
    assert request.get_header("Accept-encoding") is None  # Original builder unchanged.
    class SinkSocket:
        def __init__(self): self.parts = []
        def sendall(self, raw): self.parts.append(raw)
        def close(self): pass
    connection = http.client.HTTPConnection("synthetic.invalid")
    sink = SinkSocket(); connection.sock = sink; connection.auto_open = 0
    connection.request("GET", "/fixed-synthetic", headers=dict(request.header_items()))
    sent = b"".join(sink.parts); connection.close()
    assert sent.count(b"Accept-Encoding: identity\r\n") == 1


@pytest.mark.parametrize("case,framed,expected", [
    ("first_chunk", b"5\r\nabc", b"abc"),
    ("completed_then_partial", b"3\r\none\r\n5\r\ntwo", b"onetwo"),
    ("malformed_next_size", b"3\r\none\r\nZZ\r\n", b"one"),
    ("truncated_delimiter", b"3\r\none\r", b"one")])
def test_genuine_native_chunked_IncompleteRead_keeps_body_pieces_once_and_excludes_framing(operation, monkeypatch, case, framed, expected):
    h = operation
    class FakeSocket:
        def makefile(self, mode):
            return BytesIO(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n" + framed)
    response = http.client.HTTPResponse(FakeSocket(), method="GET"); response.begin()
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    bound = transport.drained_http_observation_binding(obs)
    assert bound[10] == expected and type(obs) is transport.UnqualifiedHttpObservation
    assert dict(bound[13])["retryable"] is False and transport.unqualified_preservation_blocker(obs) is None


def test_genuine_Content_Length_truncation_keeps_every_returned_body_byte(operation, monkeypatch):
    h = operation
    class FakeSocket:
        def makefile(self, mode):
            return BytesIO(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 5\r\n\r\nabc")
    response = http.client.HTTPResponse(FakeSocket(), method="GET"); response.begin()
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.drained_http_observation_binding(obs)[10] == b"abc"
    assert transport.unqualified_preservation_blocker(obs) is None


@pytest.mark.parametrize("kind", ["same_valued_cause", "cycle", "deep"])
def test_unproved_IncompleteRead_chain_keeps_original_error_and_prefix_without_duplicate_adoption(operation, monkeypatch, kind):
    h = operation; outer = http.client.IncompleteRead(b"prefix", 1)
    if kind == "cycle": outer.__cause__ = outer
    else:
        current = outer
        for unused in range(8 if kind == "deep" else 1):
            following = http.client.IncompleteRead(b"prefix", 1); current.__cause__ = following; current = following
    response = h.response(b"unused")
    def read(maximum): raise outer
    response.read = read
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.drained_http_observation_binding(obs)[10] == b"prefix"
    assert transport.unqualified_preservation_blocker(obs) == "native_partial_chain_unproven"
    assert any(held[1] is outer for held in transport._WIRE_ERROR_HOLD.values())
    assert dict(transport.drained_http_observation_binding(obs)[13])["preservation_blocker"] == "native_partial_chain_unproven"


@pytest.mark.parametrize("at", ["before_key", "before_GET"])
def test_fresh_physical_capacity_refusal_retains_full_reservation_and_prevents_GET(operation, monkeypatch, at):
    h = operation; checks = []
    def capacity(op, ticket):
        assert op is h.op and ticket is h.tickets[0]; checks.append(True)
        if len(checks) == (1 if at == "before_key" else 2):
            raise transport.CountTransportRefusal("REFUSED: count_operator_storage_not_registered")
    monkeypatch.setattr(transport, "_capacity_before_dispatch", capacity)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert type(obs) is transport.UnqualifiedHttpObservation
    assert transport.drained_http_observation_binding(obs)[8] is False and h.wire_calls == []
    assert len(h.key_calls) == (0 if at == "before_key" else 1)
    with pytest.raises(budget_module.DurableCountBudgetRefusal): h.budget.public_summary()
    assert budget_module.settled_chunk_accounting(h.budget)[3] == () and len(h.budget._state[2]) == 2


@pytest.mark.parametrize("operation", [False], indirect=True)
def test_unissued_remote_START_slot_refuses_before_key_or_GET(operation):
    h = operation
    with pytest.raises(transport.CountTransportRefusal, match="START_permission_required"):
        h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert h.key_calls == h.wire_calls == h.refresh_calls == []


@pytest.mark.parametrize("operation", [False], indirect=True)
def test_one_fresh_remote_evidence_binds_exact_original_roster_once(operation):
    h = operation; h.op.authorize_start_batch(h.tickets)
    originals = tuple(transport.start_permission_binding(h.op, ticket) for ticket in h.tickets)
    assert len(h.refresh_calls) == 1 and h.refresh_calls[0] is h.tickets
    assert all(original[4][4] is h.tickets for original in originals)
    for ticket in h.tickets:
        h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert len(h.refresh_calls) == 1 and len(h.wire_calls) == 2
    assert all(ticket in transport._START_CONSUMED for ticket in h.tickets)
    with pytest.raises(transport.CountTransportRefusal, match="remote_batch_refused"):
        h.op.authorize_start_batch(h.tickets)
    assert len(h.refresh_calls) == 1


@pytest.mark.parametrize("operation", [False], indirect=True)
@pytest.mark.parametrize("kind", ["list", "empty", "over8", "same_ticket", "same_position", "forged"])
def test_remote_batch_does_not_admit_foreign_or_unbounded_slots(operation, kind):
    h = operation
    roster = (list(h.tickets) if kind == "list" else () if kind == "empty" else h.tickets * 5
        if kind == "over8" else (h.tickets[0], h.tickets[0]) if kind == "same_ticket" else
        (h.tickets[0], h.retry_ticket(h.tickets[0].public_summary()["source_position"])) if kind == "same_position"
        else (object.__new__(budget_module.CountAttemptTicket),))
    with pytest.raises((transport.CountTransportRefusal, budget_module.DurableCountBudgetRefusal)):
        h.op.authorize_start_batch(roster)
    assert h.refresh_calls == h.key_calls == h.wire_calls == []
    assert h.op in transport._FAILED and transport._START_PERMISSIONS == {}


@pytest.mark.parametrize("operation", [False], indirect=True)
def test_actual_ref_change_vetoes_new_START_permission_without_key_or_GET(operation):
    h = operation; h.remote_ref = "f" * 40
    with pytest.raises(transport.CountTransportRefusal, match="START_permission_changed"):
        h.op.authorize_start_batch((h.tickets[0],))
    assert len(h.refresh_calls) == 1 and transport._START_PERMISSIONS == {}
    assert h.key_calls == h.wire_calls == [] and h.op in transport._FAILED


def test_exact_ticket_permission_cannot_be_replayed_as_a_second_dispatch(operation):
    h = operation; ticket = h.tickets[0]
    original = transport.start_permission_binding(h.op, ticket)
    h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert original is transport.start_permission_binding(h.op, ticket)
    with pytest.raises(transport.CountTransportRefusal, match="dispatch_reused"):
        h.op.dispatch(ticket, h.claim, h.starts[ticket])
    assert len(h.wire_calls) == 1


@pytest.mark.parametrize("operation", [False], indirect=True)
def test_remote_evidence_cannot_be_queued_for_unstarted_future_batches(operation):
    h = operation; h.op.authorize_start_batch((h.tickets[0],))
    with pytest.raises(transport.CountTransportRefusal, match="remote_batch_refused"):
        h.op.authorize_start_batch((h.tickets[1],))
    assert len(h.refresh_calls) == 1 and h.key_calls == h.wire_calls == []


def test_operator_failure_permanently_stops_original_budget_reserve_and_keeps_debits(operation):
    h = operation; before = h.budget._state
    transport._latch(h.op)
    with pytest.raises(budget_module.DurableCountBudgetRefusal, match="permanently_stopped"):
        h.budget.reserve_start_slot(h.plan.chunk_positions(1)[0])
    assert h.budget._state is before and budget_module.settled_chunk_accounting(h.budget)[3] == ()
    assert h.op in transport._FAILED and h.budget in budget_module._FAILED


def test_failure_latch_serializes_with_original_outbound_acceptance_lock(operation, monkeypatch):
    h = operation; lock = transport.operation_binding(h.op)[11]
    reached, worker_box = threading.Event(), []
    class ObservedRegistry(dict):
        def get(self, key, default=None):
            result = super().get(key, default)
            if worker_box and threading.current_thread() is worker_box[0]: reached.set()
            return result
    monkeypatch.setattr(transport, "_OPERATIONS", ObservedRegistry(transport._OPERATIONS))
    worker = threading.Thread(target=transport._latch, args=(h.op,)); worker_box.append(worker)
    with lock:
        worker.start(); assert reached.wait(timeout=5)
        assert h.op not in transport._FAILED  # Atomic latch waits for original A, never races an accepted slot.
    worker.join(timeout=5)
    assert not worker.is_alive() and h.op in transport._FAILED and h.budget in budget_module._FAILED


def test_named_existing_key_read_is_inside_same_original_failure_acceptance_lock(operation, monkeypatch):
    h = operation; original = transport.read_named_keychain
    def read(name):
        assert h.op._anchor[11]._is_owned()
        return original(name)
    monkeypatch.setattr(transport, "read_named_keychain", read)
    observed = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.http_observation_binding(observed)[9] == 200 and len(h.key_calls) == 1
