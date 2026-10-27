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

import pytest

from data.hashing import hash_bytes, hash_payload
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_count_durable_budget as budget_module
from test_short_interest_count_durable_budget import genuine_plan, isolated_registries_and_no_network


@pytest.fixture
def operation(monkeypatch, tmp_path):
    for name, value in (("_OPERATIONS", {}), ("_FAILED", set()), ("_OBSERVATIONS", {}),
        ("_TERMINALS", {}), ("_CANDIDATES", {}), ("_RESPONSE_CAPS", {}), ("_RECEIVED_CAPS", {}),
        ("_FINAL_CAPS", {}), ("_WINDOWS", {}), ("_VOLUMES", {}), ("_DRAINED", {}),
        ("_DOWNGRADES", {}), ("_DRAIN_ORIGINS", {}), ("_OBS_COMPLETED", {}), ("_WIRE_RESULTS", {})):
        monkeypatch.setattr(transport, name, value)
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
        def __init__(self, raw): self.raw, self.offset, self.status, self.headers = raw, 0, h.status, {
            "Content-Type": "application/json", "Content-Length": str(len(raw))}
        def read(self, maximum):
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
    return h


def test_default_source_registration_refuses_before_key_wire_or_storage(monkeypatch):
    calls = []
    monkeypatch.setattr(transport, "read_named_keychain", lambda name: calls.append("key"))
    with pytest.raises(transport.CountTransportRefusal, match="registration_pending"):
        with transport.open_registered_operation(transport.ROOT, budget=object(), runtime_head="a" * 40,
                actual_remote="b" * 40, complete_code_manifest={}): pytest.fail("unregistered operator")
    assert calls == []


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
    with pytest.raises(transport.CountTransportRefusal, match="final_incomplete"): h.op.freeze_provisional_root()


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


def test_OPEN_retry_requires_original_completion_backoff_and_new_START(operation):
    h = operation; first = h.tickets[0]
    h.failure = transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True)
    original = h.op.dispatch(first, h.claim, h.starts[first]); ticket = h.retry_ticket(first.public_summary()["source_position"])
    h.tick += 2; h.failure = None
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
        status, headers = 200, {"Content-Type": "application/json"}
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
    if declared == "absent": response.headers.pop("Content-Length")
    if declared == "ambiguous": response.headers["Content-Length"] = "2097152, 2097152"
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
    h = operation; response = h.response(b"short"); response.headers["Content-Length"] = "20"
    monkeypatch.setattr(h.opener, "open", lambda *a, **k: response)
    obs = h.op.dispatch(h.tickets[0], h.claim, h.starts[h.tickets[0]])
    assert transport.drained_http_observation_binding(obs)[10] == b"short"
    assert type(obs) is transport.UnqualifiedHttpObservation
    assert dict(transport.drained_http_observation_binding(obs)[13])["retryable"] is False
