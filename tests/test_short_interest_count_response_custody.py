"""Genuine toy operation/tickets and physical custody with fake wire/volume/kernel.

Source registration, wire and volume are named fabricated seams, not actual
source/storage qualification. No real provider, keychain, image or flag calls.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import ast
import inspect
import json
import os
from pathlib import Path
import threading
import textwrap

import pytest

from data.hashing import hash_bytes
from scripts import short_interest_count_response_custody as custody
from scripts import short_interest_count_control_custody as controls
from scripts import short_interest_count_response_volume as volume
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_body_receipt_custody as prior
from test_short_interest_count_durable_transport import operation as operation_fixture
from test_short_interest_count_durable_budget import isolated_registries_and_no_network
import test_short_interest_count_durable_budget as budget_tests
import test_short_interest_count_durable_transport as transport_tests
from test_short_interest_body_receipt_custody import kernel
from test_short_interest_new_metadata_custody import Clock


@pytest.fixture(autouse=True)
def response_registry(monkeypatch):
    for name in ("_BINDINGS", "_FILES", "_CHOICES", "_SEALS", "_FILE_ISSUED", "_PAIRS",
            "_PAIR_ISSUED", "_FILE_STATES", "_PAIR_PHASES", "_RESPONSES"):
        monkeypatch.setattr(custody, name, {})
    for name in ("_FAILED", "_ATTEMPTED", "_RESPONSE_ATTEMPTED"):
        monkeypatch.setattr(custody, name, set())


@pytest.fixture
def h(operation_fixture, kernel, monkeypatch):
    h = operation_fixture
    # Explicit shared UTC seam aligns genuine START controls with the toy
    # issuer's fixed received clock; no production clock checks are removed.
    monkeypatch.setattr(controls.kernel, "_utc_now", lambda: "2026-10-27T00:00:00Z")
    monkeypatch.setattr(custody, "_utc_now", lambda: "2026-10-27T00:00:01Z")
    # Exercise the NEW bounded GET issuer using an explicit fake response,
    # rather than replacing its source/result capability or parser checks.
    class Response:
        def __init__(self):
            self.status = h.status; self.offset = 0
            self.headers = {"Content-Type": "application/json", "Content-Length": str(len(h.raw))}
        def read(self, maximum):
            assert type(maximum) is int and 0 < maximum <= 65536
            part = h.raw[self.offset:self.offset + maximum]; self.offset += len(part)
            return part
        def close(self): pass
    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 30 and request.get_method() == "GET"
            h.wire_calls.append(True)
            if h.failure is not None: raise h.failure
            return Response()
    opener = Opener()
    monkeypatch.setattr(transport.legacy.transport, "build_protected_opener", lambda: opener)
    monkeypatch.setattr(transport.legacy.transport, "_opener", lambda value: None if value is opener else pytest.fail("wrong fake opener"))
    original = transport.operation_binding(h.op)
    mount = h.coordinator.source_lease_binding(h.lease)[11].parent
    mount.mkdir(mode=0o700, parents=True)
    fake_volume = object.__new__(volume.CountResponseVolume)
    fake_volume._anchor = fake_volume._identity = (object(),)
    volume_origin = (fake_volume, h.op, mount, original[4], original[10], original[5],
        fake_volume._anchor, original, object())
    def volume_binding(value, *, live=False):
        assert value is fake_volume
        if live: assert h.live
        return volume_origin
    # Explicit fabricated volume-issuer seam, separately covered by the full
    # source-volume native/device/provenance fixture. No pathname grants it.
    monkeypatch.setattr(volume, "volume_binding", volume_binding)
    h.op.bind_volume(fake_volume)
    monkeypatch.setattr(transport, "_controls", lambda: controls)
    monkeypatch.setattr(transport, "_responses", lambda: custody)
    h.kernel, h.volume, h.volume_origin = kernel, fake_volume, volume_origin
    @contextmanager
    def owned(path):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.mkdir(mode=0o700)
        with custody._OwnedOutput(path, lambda: None) as value: yield value
    def boundary(): assert original[11]._is_owned(), "shared source guard escaped original RLock"
    h.owned, h.boundary = owned, boundary
    h.clock = Clock()
    with owned(transport._control_directory(h.op, "claim")) as output:
        with controls.prepare_owned_count_claim(output, h.op, boundary=boundary,
                monotonic=h.clock, sleep=h.clock.sleep) as claim: claim.check()
    h.claim = claim
    h.starts = {}
    for ticket in h.tickets:
        with owned(transport._control_directory(h.op, "start", ticket)) as output:
            with controls.prepare_owned_count_start(output, h.op, ticket, claim,
                    boundary=boundary, monotonic=h.clock, sleep=h.clock.sleep) as start: start.check()
        h.starts[ticket] = start
    def observe(ticket, raw=None):
        if raw is not None: h.raw = raw
        observation = h.op.dispatch(ticket, claim, h.starts[ticket])
        with owned(transport._control_directory(h.op, "received", ticket)) as output:
            with controls.prepare_owned_count_received(output, h.op, observation,
                    boundary=boundary, monotonic=h.clock, sleep=h.clock.sleep) as received: received.check()
        h.op.accept_received_control(received)
        return observation
    h.observe = observe
    h.response_path = lambda ticket: mount / "capture" / "responses" / f"{ticket._anchor[4]:06d}"
    h.prepare = lambda output, ticket, observation, clock=None: custody.prepare_owned_count_response(output,
        ticket=ticket, observation=observation, boundary=boundary,
        monotonic=h.clock if clock is None else clock, sleep=h.clock.sleep if clock is None else clock.sleep)
    return h


def close_response(h, ticket=None, *, raw=None):
    ticket = h.tickets[0] if ticket is None else ticket
    observation = h.observe(ticket, raw)
    with h.owned(h.response_path(ticket)) as output:
        with h.prepare(output, ticket, observation) as pair: pair.check()
    return pair, observation


def _genuine_eight_missing_plan(monkeypatch):
    """Explicit12-anchor toy domain, genuine original source/ledger/plan factories.

    This expands ONLY fabricated dates and test-profile constants. It never
    alters a real source policy, manufactures a typed cap or bypasses a guard.
    """
    support = budget_tests.support; epoch = support.support
    historical, research = support.historical, support.budget
    parallel, references = epoch.parallel, epoch.references
    page = parallel.MAXIMUM_RESPONSE_BYTES; ceiling = 11 * page
    dates = tuple(f"{year}-{month}-14" for year in (2023, 2024, 2025)
        for month in ("01", "04", "07", "10"))
    source = epoch.fabricated.plan(dates)
    for name, value in {"ORIGINAL_COUNT": 12, "MAXIMUM_CUMULATIVE_STARTS": 9,
            "MAXIMUM_CUMULATIVE_BYTES": ceiling, "PARENT_STARTED": 3, "PARENT_HTTP": 2,
            "PARENT_RAW": 2, "RECOVERY_STARTED": 3, "RECOVERY_HTTP": 3, "RECOVERY_RAW": 2,
            "FAILED_PARENT_POSITION": 2, "ANCHOR_PLAN_SHA256": source.sha256}.items():
        monkeypatch.setattr(historical, name, value)
    parent_plan = parallel.freeze_parallel_count_plan(source.query_plan, maximum_total_response_bytes=ceiling)
    parent = epoch._inventory(parent_plan, 3, 2, offset=0, failed_http=False)
    charged_parent = parent.to_payload()["charged_response_bytes"]
    monkeypatch.setattr(historical, "PARENT_CHARGED_BYTES", charged_parent)
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    queries = references.freeze_native_class_query_plan(source._matrix, mode="explicit_anchors",
        selected_query_ordinals=tuple(selected[position - 1] for position in (2, 4, *range(5, 13))))
    child_plan = parallel.freeze_parallel_count_plan(queries, maximum_total_response_bytes=ceiling - charged_parent)
    child = epoch._inventory(child_plan, 3, 3, offset=20, failed_http=True)
    monkeypatch.setattr(historical, "RECOVERY_CHARGED_BYTES", child.to_payload()["charged_response_bytes"])
    pins = tuple(tuple((label, None if value is None else budget_tests.hash_payload([index, label]))
        for label, value in row) for index, row in enumerate(historical._PROOF_PINS))
    monkeypatch.setattr(historical, "_PROOF_PINS", pins)
    proofs = tuple(tuple((label, value or "a" * 64) for label, value in row) for row in pins)
    ledger = historical.seal_registered_count_epoch_ledger(source,
        epoch.epochs_from((source, parent, child, proofs)))
    old = ledger.public_summary()
    for name, value in {"BASELINE_LEDGER_SHA256": ledger.sha256, "PRIOR_STARTS": old["START_debits"],
            "PRIOR_CHARGED_BYTES": old["charged_response_bytes"], "HISTORICAL_START_CEILING": 9,
            "MAXIMUM_CUMULATIVE_STARTS": 16, "MAXIMUM_CUMULATIVE_BYTES": ceiling,
            "MISSING_POSITIONS": 8, "POSITIONS_PER_CHUNK": 8, "MAXIMUM_CHUNKS": 1,
            "EXTRA_ATTEMPTS_PER_CHUNK": 2, "_PLAN_MINTS": {}, "_BUDGET_MINTS": {}, "_PLAN_KEYS": set()}.items():
        monkeypatch.setattr(research, name, value)
    monkeypatch.setattr(budget_tests.budget, "_EXPECTED_SOURCE_PROFILE", budget_tests.budget._source_profile())
    return research.freeze_count_recovery_plan(ledger)


@pytest.fixture
def h8(monkeypatch, request):
    monkeypatch.setattr(transport_tests, "genuine_plan", _genuine_eight_missing_plan)
    return request.getfixturevalue("h")


def test_response_accessor_has_no_factory_descriptor_cleanup_or_error_masking(monkeypatch):
    fake = object.__new__(custody.CountResponseCustody)
    def refused(self): raise custody.CountResponseRefusal("REFUSED: count_response_binding_changed")
    monkeypatch.setattr(custody.CountResponseCustody, "_binding", refused)
    with pytest.raises(custody.CountResponseRefusal, match="binding_changed"):
        custody.response_binding(fake)


def test_genuine_ticket_HTTP_and_closed_controls_issue_only_original_closed_response(h):
    ticket = h.tickets[0]; observation = h.observe(ticket)
    with pytest.raises(custody.CountResponseRefusal):
        with h.owned(h.response_path(ticket)) as output:
            with h.prepare(output, ticket, observation) as pair:
                assert pair.read_body() == h.raw
                receipt = json.loads(pair.read_receipt())
                assert len(pair.read_receipt()) <= 1024
                assert receipt["body_sha256"] == hash_bytes(h.raw)
                assert receipt["http_status"] == 200 and receipt["http_invoked"] is True
                assert receipt["source_admitted"] is receipt["budget_release_authority"] is False
                with pytest.raises(custody.CountResponseRefusal): custody.response_binding(pair)
    assert pair in custody._FAILED


def test_original_closed_response_binding_has_exact_source_and_nine_field_seals(h):
    ticket = h.tickets[0]; observation = h.observe(ticket)
    with h.owned(h.response_path(ticket)) as output:
        with h.prepare(output, ticket, observation) as pair:
            assert pair.read_body() == h.raw
            live = pair.observation()
    original = custody.response_binding(pair)
    assert len(original) == 13 and original[:6] == (pair, h.op, ticket, observation, h.claim, h.starts[ticket])
    assert original[6:8] == (hash_bytes(h.raw), len(h.raw))
    assert len(original[9]) == len(original[10]) == 9 and original[9][:2] != original[10][:2]
    assert custody.response_binding(pair) is original
    closed = pair.closed_summary()
    assert closed["status"] == "closed_count_response_custody_only"
    assert all(row["original_context_closed"] for row in closed["files"])
    assert [row["seal_stamp_sha256"] for row in live["files"]] == [row["seal_stamp_sha256"] for row in closed["files"]]
    assert len(h.kernel.calls) == 6  # genuine claim, two STARTs, received, body, receipt
    assert h.budget.public_summary()["settled_tickets"] == 0


def test_maximum_2MiB_body_comes_only_from_original_HTTP_observation(h):
    raw = b"synthetic-source-transport-only\n" * 80000
    raw = raw[:custody.MAXIMUM_BODY_BYTES]
    assert len(raw) == 2097152
    pair, observation = close_response(h, raw=raw)
    original = custody.response_binding(pair)
    assert original[3] is observation and original[6:8] == (hash_bytes(raw), len(raw))
    assert (h.response_path(h.tickets[0]) / custody.BODY_NAME).read_bytes() == raw
    assert len((h.response_path(h.tickets[0]) / custody.RECEIPT_NAME).read_bytes()) <= 1024
    assert h.budget.public_summary()["closed_chunks"] == 0


@pytest.mark.parametrize("kind", ["bare_body", "fake_observation", "swapped_ticket", "wrong_directory"])
def test_only_exact_genuine_qualified_sources_and_derived_directory_can_create(h, kind):
    ticket = h.tickets[0]; observation = h.observe(ticket)
    before = len(h.kernel.calls)
    with h.owned(h.response_path(ticket)) as output:
        with pytest.raises((TypeError, custody.CountResponseRefusal, transport.CountTransportRefusal)):
            if kind == "bare_body":
                with custody.prepare_owned_count_response(output, h.raw, ticket=ticket, observation=observation,
                        boundary=h.boundary): pytest.fail("caller body admitted")
            elif kind == "fake_observation":
                fake = object.__new__(transport.HttpObservation)
                with h.prepare(output, ticket, fake): pytest.fail("fake observation admitted")
            elif kind == "swapped_ticket":
                with h.prepare(output, h.tickets[1], observation): pytest.fail("cross-ticket body admitted")
            else:
                with h.owned(h.response_path(ticket).with_name("arbitrary")) as wrong:
                    with h.prepare(wrong, ticket, observation): pytest.fail("wrong path admitted")
        assert list(output._anchor[0].iterdir()) == []
    assert len(h.kernel.calls) == before


@pytest.mark.parametrize("kind", ["404", "timeout", "empty200"])
def test_negative_or_absent_body_has_received_control_but_never_body_pair_or_zero_count(h, kind):
    ticket = h.tickets[0]
    if kind != "empty200":
        h.failure = (transport.wire.RecoveryTransportFailure("http_not_200", phase="response",
            failure_class="http_status", status=404) if kind == "404" else
            transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True))
    else: h.raw = b""
    observation = h.observe(ticket)
    bound = transport.http_observation_binding(observation)
    assert bound[10] is None or bound[10] == b""
    before = len(h.kernel.calls)
    with h.owned(h.response_path(ticket)) as output:
        with pytest.raises(custody.CountResponseRefusal, match="bounds_refused"):
            with h.prepare(output, ticket, observation): pytest.fail("empty/nonbody promoted")
        assert not list(output._anchor[0].iterdir())
        with pytest.raises(custody.CountResponseRefusal, match="ticket_spent"):
            with h.prepare(output, ticket, observation): pytest.fail("failed response attempted twice")
    assert len(h.kernel.calls) == before and h.budget.public_summary()["settled_tickets"] == 0
    assert len(transport._RECEIVED_CAPS[h.op]) == 1 and transport._RESPONSE_CAPS[h.op] == ()


def test_original_ticket_cannot_be_republished_after_clean_closed_pair(h):
    pair, observation = close_response(h); ticket = h.tickets[0]
    before = len(h.kernel.calls)
    with custody._OwnedOutput(h.response_path(ticket), lambda: None) as output:
        with pytest.raises(custody.CountResponseRefusal, match="ticket_spent"):
            with h.prepare(output, ticket, observation): pytest.fail("old pair adopted")
    assert len(h.kernel.calls) == before and custody.response_binding(pair)[2] is ticket


@pytest.mark.parametrize("kind", ["ctime", "flags", "membership", "binding_identity", "public_state"])
def test_detected_original_drift_latches_and_cannot_be_reset_to_false_closure(h, kind):
    ticket = h.tickets[0]; observation = h.observe(ticket)
    with pytest.raises((custody.CountResponseRefusal, custody.cache.contract.AnchorCacheRefusal)):
        with h.owned(h.response_path(ticket)) as output:
            with h.prepare(output, ticket, observation) as pair:
                body = pair._anchor[3][0]; origin = body._anchor
                if kind == "ctime": os.fchmod(origin[7], 0o600)
                elif kind == "flags": h.kernel.flags[origin[8][:2]] = 0
                elif kind == "membership": (output._anchor[0] / "extra").write_bytes(b"fabricated")
                elif kind == "binding_identity": pair._identity = tuple(list(pair._anchor))
                else: custody._PAIRS[pair][1]["phase"] = "CLOSED"
                with pytest.raises((custody.CountResponseRefusal, custody.cache.contract.AnchorCacheRefusal)): pair.check()
                if kind == "flags": h.kernel.flags[origin[8][:2]] = 2
                if kind == "binding_identity": pair._identity = pair._anchor
                if kind == "public_state": custody._PAIRS[pair][1]["phase"] = "LIVE"
                pair.check()
    assert pair not in custody._PAIR_ISSUED
    with pytest.raises(custody.CountResponseRefusal): pair.closed_summary()


def test_terminal_control_tuple_allocation_is_allowed_but_original_anchor_or_nonce_substitution_refuses(h):
    pair, unused = close_response(h)
    original = custody._binding_anchor(pair._anchor[2])[3:]
    clone = (*original[:4], tuple(list(original[4])), tuple(list(original[5])))
    custody._same_inputs(clone, original)
    changed = (*clone[:4], (*clone[4][:-1], object()), clone[5])
    with pytest.raises(custody.CountResponseRefusal): custody._same_inputs(changed, original)


@pytest.mark.parametrize("kind", ["deadline", "backwards", "native_failure"])
def test_original_file_time_and_native_failure_are_not_retried_or_promoted(h, kind, monkeypatch):
    ticket = h.tickets[0]; observation = h.observe(ticket)
    before = len(h.kernel.calls)
    if kind == "native_failure":
        monkeypatch.setattr(type(h.kernel.operation), "__call__", lambda self, fd, target: -1)
    else:
        def change(unused): h.clock.value += 9 if kind == "deadline" else -1
        h.kernel.hooks.append(change)
    with h.owned(h.response_path(ticket)) as output:
        with pytest.raises((custody.CountResponseRefusal, custody.immutable.ImmutableMetadataRefusal)):
            with h.prepare(output, ticket, observation): pytest.fail("failed kernel/time became closed pair")
        assert set(os.listdir(output._anchor[0])) == {custody.BODY_NAME}
        with pytest.raises(custody.CountResponseRefusal, match="ticket_spent"):
            with h.prepare(output, ticket, observation): pytest.fail("same spent response retried")
    assert len(h.kernel.calls) == before + (kind != "native_failure")
    assert not custody._PAIR_ISSUED


def test_original_per_file_kernel_predicates_are_identical_versioned_code():
    class Normalize(ast.NodeTransformer):
        def visit_Name(self, node):
            node.id = {"CountResponseFileCustody": "BodyReceiptFileCustody",
                "CountResponseCustody": "BodyReceiptCustody"}.get(node.id, node.id)
            return node
        def visit_Constant(self, node):
            if type(node.value) is str: node.value = node.value.replace("count_response_", "body_receipt_")
            return node
    for name in ("_file_state", "_update_file", "_close_all", "_pair", "_read_original"):
        old = ast.parse(textwrap.dedent(inspect.getsource(getattr(prior, name))))
        new = ast.parse(textwrap.dedent(inspect.getsource(getattr(custody, name))))
        assert ast.dump(Normalize().visit(new), include_attributes=False) == ast.dump(old, include_attributes=False)


def test_scope_policy_never_casts_source_or_settles_budget():
    policy = custody.policy()
    assert policy["per_file_seconds"] == 8.0 and policy["per_file_samples"] == 16
    assert policy["sample_seconds"] == .25 and policy["quiet_seconds"] == 1
    assert policy["maximum_body_bytes"] == 2097152 and policy["maximum_receipt_bytes"] == 1024
    assert policy["authority"]["source_admitted"] is policy["authority"]["dispatch_authority"] is False
    assert policy["authority"]["ready_for_backtest"] is policy["authority"]["budget_release_authority"] is False
    assert prior.MAXIMUM_BODY_BYTES == 2097152 and prior.MAXIMUM_RECEIPT_BYTES == 1024


def test_quiet_sleeps_are_outside_original_shared_lock_and_parallel_pairs_keep_private_FDs(h8):
    h = h8
    assert len(h.tickets) == 8
    observations = [h.observe(ticket) for ticket in h.tickets]
    from contextlib import ExitStack
    original = transport.operation_binding(h.op)
    with ExitStack() as outputs:
        owned = [outputs.enter_context(h.owned(h.response_path(ticket))) for ticket in h.tickets]
        def worker(index):
            clock = Clock(); base_sleep = clock.sleep
            def sleep(value):
                assert not original[11]._is_owned(), "quiet sleep held shared operation guard"
                base_sleep(value)
            with custody.prepare_owned_count_response(owned[index], ticket=h.tickets[index],
                    observation=observations[index], boundary=h.boundary, monotonic=clock, sleep=sleep) as pair:
                pair.check(); assert pair.read_body() == h.raw
            assert clock.sleeps == [.25] * 8
            return pair
        with ThreadPoolExecutor(max_workers=8) as workers:
            pairs = tuple(workers.map(worker, range(8)))
    bound = tuple(custody.response_binding(pair) for pair in pairs)
    assert len({item[9][:2] for item in bound}) == 8
    assert all(item[1] is h.op for item in bound) and h.budget.public_summary()["settled_tickets"] == 0
