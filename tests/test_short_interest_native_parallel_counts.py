"""Fabricated causal parallel tests; no source/key/network or live capture."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import threading
import sys

import pytest
from data.hashing import hash_bytes, hash_payload
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError
from research.short_interest_etf import native_dated_class_reference as references

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("parallel_anchor_test_fixtures", HERE / "test_short_interest_native_reported_anchor_plan.py")
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)

import research.short_interest_etf.native_parallel_count_contract as contract
import scripts.capture_short_interest_native_parallel_counts as runtime

SYNTHETIC_SECRET = "FABRICATED_PARALLEL_SECRET_42"
START = "2026-10-14T01:00:00Z"
RAW = b'{"status":"OK","results":{}}'


def plan(count=12, maximum_bytes=None):
    days = tuple((datetime(2022, 1, 4) + timedelta(days=index)).date().isoformat() for index in range(count))
    matrix = fixtures.matrix([("SYN", at) for at in days])
    queries = references.freeze_native_class_query_plan(matrix, mode="explicit_anchors", selected_query_ordinals=tuple(range(1, count + 1)))
    return contract.freeze_parallel_count_plan(queries, maximum_total_response_bytes=maximum_bytes or count * contract.MAXIMUM_RESPONSE_BYTES)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 14, 1, tzinfo=timezone.utc)
        self.lock = threading.Lock()
    def __call__(self):
        with self.lock:
            self.value += timedelta(microseconds=1)
            return self.value.isoformat().replace("+00:00", "Z")


def setup(monkeypatch, count=12, maximum_bytes=None):
    frozen = plan(count, maximum_bytes)
    monkeypatch.setattr(runtime, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(runtime, "_guard", lambda *args: None)
    monkeypatch.setattr(runtime, "PLAN_SHA256", frozen.sha256)
    monkeypatch.setattr(runtime, "PROTOCOL_SHA256", hash_payload(runtime.protocol()))
    events, stored, calls = [], {}, []
    lock = threading.Lock()
    def code(value):
        value.guard()
    def source(value):
        value.guard()
    def claim(value):
        events.append("claim")
        assert value["maximum_attempts"] == count
    def key(provider):
        events.append("key")
        assert provider == "massive"
        return KeychainSecret(SYNTHETIC_SECRET)
    def publish(directory, name, value):
        with lock:
            assert name not in stored
            stored[name] = value
    def http(opener, request, maximum):
        with lock:
            calls.append(request)
        return RAW, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    kwargs = dict(head="a"*40, remote="b"*40, started_at=START, verify_sources=source,
                  verify_code=code, claim_budget=claim, publish=publish, publish_json=publish,
                  read_secret=key, clock=Clock())
    return frozen, kwargs, events, stored, calls


def run(frozen, kwargs):
    return runtime.capture_with_seams(Path("/fabricated/root"), Path("/fabricated/capture"), frozen, **kwargs)


def test_all_exact_tickets_complete_once_and_claim_before_key(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    result = run(frozen, kwargs).to_payload()
    assert events == ["claim", "key"]
    assert len(calls) == result["attempts_started"] == result["http_invocations"] == 12
    assert result["complete_frozen_request_sequence"] is True and result["halted"] is False
    assert result["charged_response_bytes"] == len(RAW) * 12
    assert all("apikey" not in request.full_url and SYNTHETIC_SECRET not in request.full_url for request in calls)
    assert all(request.get_header("Authorization") == "Bearer " + SYNTHETIC_SECRET for request in calls)
    assert len([name for name in stored if name.endswith(".started.json")]) == 12


def test_actual_worker_overlap_at_most_eight_and_all_attempts_drained(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    lock, gate = threading.Lock(), threading.Event()
    active, maximum = 0, 0
    def http(opener, request, maximum_bytes):
        nonlocal active, maximum
        with lock:
            calls.append(request)
            active += 1
            maximum = max(maximum, active)
            if len(calls) == 8:
                gate.set()
        assert gate.wait(2)
        with lock:
            active -= 1
        return RAW, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    result = run(frozen, kwargs)
    assert maximum == 8 and active == 0 and len(calls) == 12
    assert result.to_payload()["complete_frozen_request_sequence"]


def test_receipt_order_inversion_preserved_and_typed_verifier_accepts(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=2)
    second_published = threading.Event()
    original_publish = kwargs["publish_json"]
    def publish(directory, name, value):
        original_publish(directory, name, value)
        if name == "query-00000002.received.json":
            second_published.set()
    kwargs["publish_json"] = publish
    first_day = frozen._queries.to_payload()["selected_query_ordinals"][0]
    def http(opener, request, maximum):
        calls.append(request)
        if "date=2022-01-04" in request.full_url:
            assert second_published.wait(2)
        return RAW, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    inventory = run(frozen, kwargs)
    receipts = list(inventory.iter_receipts())
    assert receipts[0]["received_at"] > receipts[1]["received_at"]
    assert [receipt["query_ordinal"] for receipt in receipts] == [1, 2]
    for query in frozen._queries.iter_queries():
        ordinal = query.to_payload()["query_ordinal"]
        receipt = inventory.receipt_for_ordinal(ordinal)
        capture = references.capture_native_dated_class_response(query, raw=RAW, raw_sha256=hash_bytes(RAW),
             request_sha256=query.to_payload()["request_sha256"], received_at=receipt["received_at"],
             http_status=200, content_type="application/json", body_observed=True)
        assert contract.verify_capture_receipt(inventory, capture)["received_at"] == receipt["received_at"]


@pytest.mark.parametrize("status", [403, 429, 500, None, "unexpected"])
def test_material_failure_halts_new_scheduling_but_drains_eight_started(monkeypatch, status):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    lock, gate, failure_published = threading.Lock(), threading.Event(), threading.Event()
    original_publish = kwargs["publish_json"]
    def publish(directory, name, value):
        original_publish(directory, name, value)
        if name == "query-00000001.received.json":
            failure_published.set()
    kwargs["publish_json"] = publish
    def http(opener, request, maximum):
        with lock:
            calls.append(request)
            first = "date=2022-01-04" in request.full_url
            if len(calls) == 8:
                gate.set()
        assert gate.wait(2)
        if first:
            if status == "unexpected":
                raise RuntimeError(SYNTHETIC_SECRET + request.full_url)
            raise SharadarCaptureRefusal("fabricated_http_refused", status=status)
        assert failure_published.wait(2)
        return RAW, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    inventory = run(frozen, kwargs)
    result = inventory.to_payload()
    assert len(calls) == result["attempts_started"] == 8
    assert result["halted"] is True and result["complete_frozen_request_sequence"] is False
    assert result["unstarted_tickets"] == 4
    failure = inventory.receipt_for_ordinal(1)
    assert failure["http_status"] == (None if status == "unexpected" else status) and failure["body_observed"] is False
    assert failure["raw_sha256"] is None
    assert len([name for name in stored if name.endswith(".received.json")]) == 8


def test_404_is_retained_negative_unobserved_and_does_not_halt(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=2)
    def http(opener, request, maximum):
        calls.append(request)
        if "date=2022-01-04" in request.full_url:
            raise SharadarCaptureRefusal("fabricated_missing", status=404)
        return RAW, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    inventory = run(frozen, kwargs)
    receipt = inventory.receipt_for_ordinal(1)
    assert receipt["http_status"] == 404 and receipt["body_observed"] is False
    assert all(receipt[field] is None for field in ("raw_sha256", "raw_path", "raw_bytes", "content_type"))
    assert inventory.to_payload()["complete_frozen_request_sequence"] is True
    query = next(frozen._queries.iter_queries())
    negative = references.capture_native_dated_class_response(query, raw=b"", raw_sha256=hash_bytes(b""),
        request_sha256=query.to_payload()["request_sha256"], received_at=receipt["received_at"],
        http_status=404, content_type="", body_observed=False)
    assert contract.verify_capture_receipt(inventory, negative)["code"] == "HTTP_404_body_unobserved"


def test_whole_page_reservation_blocks_unaffordable_second_START(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=2, maximum_bytes=contract.MAXIMUM_RESPONSE_BYTES)
    raw = b" " * contract.MAXIMUM_RESPONSE_BYTES
    def http(opener, request, maximum):
        calls.append(request)
        return raw, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    inventory = run(frozen, kwargs).to_payload()
    assert len(calls) == inventory["attempts_started"] == 1
    assert "query-00000002.started.json" not in stored
    assert inventory["charged_response_bytes"] == contract.MAXIMUM_RESPONSE_BYTES
    assert inventory["halted"] and not inventory["complete_frozen_request_sequence"]


def test_small_bodies_release_only_unused_reservations_not_attempt_budget(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=12, maximum_bytes=2 * contract.MAXIMUM_RESPONSE_BYTES)
    result = run(frozen, kwargs).to_payload()
    assert result["attempts_started"] == 12 and len(calls) == 12
    assert result["complete_frozen_request_sequence"] is True


@pytest.mark.parametrize("kind", ["literal", "unicode", "percent"])
def test_secret_echo_discarded_before_raw_hash_or_publication(monkeypatch, kind):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=1)
    echo = SYNTHETIC_SECRET.encode() if kind == "literal" else (b"".join(f"\\u{ord(c):04x}".encode() for c in SYNTHETIC_SECRET)
           if kind == "unicode" else b"".join(f"%{ord(c):02X}".encode() for c in SYNTHETIC_SECRET))
    def http(opener, request, maximum):
        calls.append(request)
        return b'{"error":"' + echo + b'"}', "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda raw: hashes.append(raw) or "a"*64)
    result = run(frozen, kwargs).to_payload()
    assert hashes == [] and not any(name.endswith(".raw") for name in stored)
    assert result["halted"] and result["charged_response_bytes"] == contract.MAXIMUM_RESPONSE_BYTES


def test_claimed_key_failure_has_owned_zero_HTTP_receipt(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    kwargs["read_secret"] = lambda provider: (_ for _ in ()).throw(ShortInterestKeychainError("fabricated_unavailable"))
    with pytest.raises(contract.ParallelCountRefusal, match="after_claim"):
        run(frozen, kwargs)
    assert events == ["claim"] and calls == []
    assert stored["run.refused.json"]["http_invocations"] == stored["run.refused.json"]["attempts_started"] == 0


def test_exclusive_claim_refusal_precedes_key_and_HTTP(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    kwargs["claim_budget"] = lambda value: (_ for _ in ()).throw(FileExistsError("fabricated_spent"))
    with pytest.raises(FileExistsError):
        run(frozen, kwargs)
    assert events == [] and calls == [] and stored == {}


@pytest.mark.parametrize("pin", ["PLAN_SHA256", "PROTOCOL_SHA256"])
def test_pending_pin_refuses_before_claim_key_HTTP(monkeypatch, pin):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    monkeypatch.setattr(runtime, pin, "PENDING")
    with pytest.raises(contract.ParallelCountRefusal, match="pending_or_changed"):
        run(frozen, kwargs)
    assert events == [] and calls == [] and stored == {}


def test_post_HTTP_protocol_change_cannot_publish_raw_or_complete(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=1)
    def http(opener, request, maximum):
        calls.append(request)
        monkeypatch.setattr(runtime, "PROTOCOL_SHA256", "PENDING")
        return RAW, "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    with pytest.raises(contract.ParallelCountRefusal, match="after_drain"):
        run(frozen, kwargs)
    assert len(calls) == 1 and not any(name.endswith(".raw") for name in stored)
    assert "inventory.private.json" not in stored


def receipt_for(frozen, ordinal, began, ended):
    ticket = tuple(frozen._queries.iter_queries())[ordinal - 1].to_payload()
    return {"query_ordinal": ordinal, "request_sha256": ticket["request_sha256"], "started_at": began,
            "received_at": ended, "http_attempted": True, "http_status": 200, "body_observed": True,
            "raw_path": f"query-{ordinal:08d}.raw", "raw_sha256": hash_bytes(RAW), "raw_bytes": len(RAW),
            "content_type": "application/json", "code": "received"}


@pytest.mark.parametrize("change", ["backdate", "after_completion", "duplicate", "wrong_ticket", "hole"])
def test_receipt_per_attempt_enclosing_and_ordinal_bindings_refused(change):
    frozen = plan(2)
    first = receipt_for(frozen, 1, "2026-10-14T01:00:01Z", "2026-10-14T01:00:03Z")
    second = receipt_for(frozen, 2, "2026-10-14T01:00:02Z", "2026-10-14T01:00:03Z")
    receipts = (first, second)
    if change == "backdate": first["received_at"] = START
    elif change == "after_completion": first["received_at"] = "2026-10-14T01:00:05Z"
    elif change == "duplicate": receipts = (first, first)
    elif change == "wrong_ticket": second["request_sha256"] = "a"*64
    else: receipts = (second,)
    with pytest.raises(contract.ParallelCountRefusal):
        contract.seal_parallel_inventory(frozen, receipts, started_at=START, completed_at="2026-10-14T01:00:04Z", halted=False)


def test_more_than_eight_observed_overlaps_refused():
    frozen = plan(9)
    receipts = tuple(receipt_for(frozen, ordinal, "2026-10-14T01:00:01Z", "2026-10-14T01:00:03Z") for ordinal in range(1, 10))
    with pytest.raises(contract.ParallelCountRefusal, match="inflight_ceiling"):
        contract.seal_parallel_inventory(frozen, receipts, started_at=START, completed_at="2026-10-14T01:00:04Z", halted=False)


def test_unsealed_boolean_or_dict_cannot_supply_parallel_registry_gate():
    with pytest.raises(contract.ParallelCountRefusal, match="exact_parallel_inventory"):
        contract.verify_capture_receipt({"parallel_authorized": True}, object())
    with pytest.raises(contract.ParallelCountRefusal, match="no_operational_entrypoint"):
        runtime.main()


def test_truncated_reflective_inventory_anchor_cannot_exclude_digest(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, count=1)
    inventory = run(frozen, kwargs)
    truncated = inventory._anchor[:3]
    object.__setattr__(inventory, "_anchor", truncated)
    object.__setattr__(inventory, "_identity", truncated)
    object.__setattr__(inventory, "_digest", "a"*64)
    with pytest.raises(contract.ParallelCountRefusal, match="inventory_changed"):
        inventory.sha256
