"""Fabricated bounded chunks; no provider, credentials or source rows."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading

import pytest

from data.hashing import hash_payload
from scripts import capture_short_interest_bounded_count_chunk as chunk

spec = importlib.util.spec_from_file_location("bounded_chunk_fabricated_anchor_fixture",
    Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
fabricated = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fabricated
spec.loader.exec_module(fabricated)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


class Harness:
    def __init__(self, monkeypatch, tmp_path):
        monkeypatch.setattr(chunk, "DESCRIPTORS", 3)
        monkeypatch.setattr(chunk, "EXTRA_ATTEMPTS", 2)
        monkeypatch.setattr(chunk, "MAXIMUM_ATTEMPTS", 5)
        monkeypatch.setattr(chunk, "FIRST_POSITION", 1)
        monkeypatch.setattr(chunk, "MAXIMUM_RESPONSE_BYTES", 65536)
        monkeypatch.setattr(chunk, "PREDECESSOR_MANIFEST_SHA256", "a" * 64)
        monkeypatch.setattr(chunk, "PROTOCOL_SHA256", hash_payload(chunk.protocol()))
        dates = ("2023-01-01", "2023-02-01", "2023-03-01")
        source = fabricated.plan(dates, reports=tuple(fabricated.identity(at,
            class_id=fabricated.CLASS if n % 2 else fabricated.NEXT_CLASS) for n, at in enumerate(dates)))
        self.queries = source.query_plan
        assert len(tuple(self.queries.iter_queries())) == 3
        self.root = tmp_path.resolve()
        self.root.chmod(0o700)
        self.directory = self.root / "child"
        self.directory.mkdir(mode=0o700)
        self.owned = chunk._OwnedOutput(self.directory, lambda: None)
        self.tick, self.n, self.lock = 0.0, 0, threading.Lock()
        self.events, self.calls, self.sleeps = [], [], []
        self.failure = lambda n, request: None
        self.hook = lambda: None
        self.registration = {"head": "a" * 40, "remote": "b" * 40, "code_identity_sha256": "c" * 64}
        self.real_publish = chunk._OwnedOutput.publish

    def clock(self):
        with self.lock:
            self.n += 1
            return (datetime(2026, 10, 24, tzinfo=timezone.utc)
                + timedelta(seconds=self.tick, microseconds=self.n)).isoformat().replace("+00:00", "Z")

    def sleep(self, seconds):
        self.sleeps.append(seconds); self.tick += seconds

    def check(self):
        self.events.append("check")

    def refresh(self):
        self.events.append("remote"); self.hook()

    def secret(self, name):
        self.events.append("key")
        assert (self.root / chunk.CLAIM).exists()
        return chunk.KeychainSecret("fabricated-secret")

    def http(self, opener, request, maximum):
        with self.lock:
            self.calls.append(request); n = len(self.calls)
        assert maximum == chunk.MAXIMUM_RESPONSE_BYTES
        failure = self.failure(n, request)
        if isinstance(failure, BaseException):
            raise failure
        return failure if type(failure) is tuple else (b'{"status":"OK"}', "application/json", 200)

    def run(self, **changes):
        try:
            return chunk.capture_chunk(self.queries, registration=self.registration,
                check=self.check, refresh=self.refresh, owned=self.owned, get_secret=self.secret,
                http=self.http, clock=self.clock, sleep=self.sleep, monotonic=lambda: self.tick, **changes)
        finally:
            self.owned.close()

    def payload(self, name):
        return json.loads((self.directory / name).read_bytes())


def transient():
    return chunk.transport.RecoveryTransportFailure("network_failure", phase="open",
        failure_class="timeout", retryable=True)


def test_new_chunk_claim_receipts_manifest_and_source_gates(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    value = h.run()
    assert value["START_debits"] == value["HTTP_invocations"] == value["resolved_descriptors"] == 3
    assert value["cumulative_STARTs"] == chunk.PRIOR_STARTS + 3
    assert value["cumulative_charged_bytes"] == chunk.PRIOR_BYTES + value["charged_bytes"]
    assert value["complete_transport_chunk"] and not value["complete_original_source"]
    assert not value["authority"]["ready_for_backtest"]
    assert (h.directory / "chunk.closed.json").exists()
    assert not (h.directory / "run.refused.json").exists()
    assert h.payload("manifest.private.json")
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in h.directory.iterdir())


def test_statusless_retry_has_own_START_full_charge_and_backoff(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    h.failure = lambda n, request: transient() if n == 1 else None
    value = h.run()
    assert value["START_debits"] == value["HTTP_invocations"] == 4
    assert value["extra_attempts"] == 1
    assert value["charged_bytes"] == chunk.MAXIMUM_RESPONSE_BYTES + 3 * len(b'{"status":"OK"}')
    first = next(h.payload(f"attempt-{n:05d}.received.json") for n in range(1, 4)
        if h.payload(f"attempt-{n:05d}.received.json")["diagnostic"] is not None)
    retried = h.payload("attempt-00004.received.json")
    assert first["diagnostic"]["failure_class"] == "timeout"
    assert not first["body_observed"] and first["charged_bytes"] == chunk.MAXIMUM_RESPONSE_BYTES
    assert retried["retry_of"] == first["attempt"] and retried["try_number"] == 2
    assert first["request_sha256"] == retried["request_sha256"]
    assert sum(h.sleeps) >= 2


def test_two_retries_are_finitely_debited_and_claim_not_reset(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    h.failure = lambda n, request: transient() if n in (1, 4) else None
    value = h.run()
    assert value["START_debits"] == 5 and value["extra_attempts"] == 2
    assert h.payload("attempt-00005.received.json")["try_number"] == 3
    assert sum(h.sleeps) >= 12
    assert value["charged_bytes"] == 2 * chunk.MAXIMUM_RESPONSE_BYTES + 3 * len(b'{"status":"OK"}')


@pytest.mark.parametrize("failure", [
    RuntimeError("https://private.invalid/?token=SECRET"),
    chunk.transport.RecoveryTransportFailure("network_failure", phase="open", failure_class="tls"),
    chunk.transport.RecoveryTransportFailure("network_failure", phase="open", failure_class="resource_exhausted", errno_name="ENOSPC"),
    chunk.transport.RecoveryTransportFailure("network_failure", phase="read", failure_class="timeout", status=200),
    *[chunk.transport.RecoveryTransportFailure("http_not_200", phase="open", failure_class="http_status", status=s)
      for s in (403, 429, 500, 503)],
])
def test_nonretryable_failure_drains_batch_and_never_positive(monkeypatch, tmp_path, failure):
    h = Harness(monkeypatch, tmp_path); h.failure = lambda n, request: failure if n == 1 else None
    assert h.run() is None
    value = h.payload("run.refused.json")
    assert value["START_debits"] == value["known_HTTP_invocations"] == 3
    assert value["charged_bytes"] == chunk.MAXIMUM_RESPONSE_BYTES + 2 * len(b'{"status":"OK"}')
    assert not (h.directory / "chunk.closed.json").exists()
    assert "SECRET" not in repr(value) + (h.directory / "attempt-00001.received.json").read_text()


def test_404_is_status_only_no_retry_full_page_conservative_charge(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    h.failure = lambda n, request: chunk.transport.RecoveryTransportFailure("http_not_200",
        phase="open", failure_class="http_status", status=404) if n == 1 else None
    value = h.run()
    assert value["START_debits"] == 3 and value["extra_attempts"] == 0
    assert value["charged_bytes"] == chunk.MAXIMUM_RESPONSE_BYTES + 2 * len(b'{"status":"OK"}')
    assert not next(h.payload(f"attempt-{n:05d}.received.json") for n in range(1, 4)
        if h.payload(f"attempt-{n:05d}.received.json")["http_status"] == 404)["body_observed"]


def test_extra_attempt_pool_exhaustion_cannot_silently_drop_failed_slots(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path); h.failure = lambda n, request: transient()
    assert h.run() is None
    value = h.payload("run.refused.json")
    assert value["START_debits"] == value["known_HTTP_invocations"] == 3
    assert value["charged_bytes"] == 3 * chunk.MAXIMUM_RESPONSE_BYTES
    assert not (h.directory / "chunk.closed.json").exists()


def test_claim_collision_prevents_key_and_HTTP(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    (h.root / chunk.CLAIM).write_bytes(b"spent old bytes")
    with pytest.raises(FileExistsError):
        h.run()
    assert "key" not in h.events and h.calls == []
    assert (h.root / chunk.CLAIM).read_bytes() == b"spent old bytes"


def test_partial_START_publication_debit_is_not_released_or_sent(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    def publish(owned, name, raw, **kwargs):
        if name == "attempt-00002.started.json":
            raise OSError("private local failure")
        return h.real_publish(owned, name, raw, **kwargs)
    monkeypatch.setattr(chunk._OwnedOutput, "publish", publish)
    assert h.run() is None
    value = h.payload("run.refused.json")
    assert value["START_debits"] == 2 and value["known_HTTP_invocations"] == 0
    assert value["unreceipted_attempts"] == [1, 2]
    assert value["charged_bytes"] == 2 * chunk.MAXIMUM_RESPONSE_BYTES
    assert h.calls == []


@pytest.mark.parametrize("stage", ["inventory.private.json", "chunk.completed.provisional.json", "chunk.closed.json"])
def test_postpublication_remote_drift_dominates_all_markers(monkeypatch, tmp_path, stage):
    h = Harness(monkeypatch, tmp_path)
    def refresh():
        if (h.directory / stage).exists():
            raise chunk.lane.LaneBatchRefusal("matching_actual_remote_advanced_or_ambiguous")
    h.hook = refresh
    assert h.run() is None
    assert h.payload("run.refused.json")["code"] == "postpublication_chunk_refused"


@pytest.mark.parametrize("tamper", ["body", "receipt", "negative_sibling"])
def test_actual_closed_membership_and_bytes_not_memory_alone(monkeypatch, tmp_path, tamper):
    h = Harness(monkeypatch, tmp_path)
    fired = []
    def change():
        if (h.directory / "attempt-00003.received.json").exists() and not fired:
            fired.append(True)
            if tamper == "negative_sibling":
                (h.directory / "round.closed.refused.json").write_bytes(b"negative")
            else:
                name = "attempt-00001.raw" if tamper == "body" else "attempt-00001.received.json"
                (h.directory / name).write_bytes(b"changed original bytes")
    h.hook = change
    assert h.run() is None
    assert (h.directory / "run.refused.json").exists()
    assert not (h.directory / "chunk.closed.json").exists()


@pytest.mark.parametrize("body,media", [(b"fabricated-secret", "application/json"), (b"{}", "text/html")])
def test_echo_and_invalid_media_are_not_persisted_or_retried(monkeypatch, tmp_path, body, media):
    h = Harness(monkeypatch, tmp_path)
    h.failure = lambda n, request: (body, media, 200) if n == 1 else None
    assert h.run() is None
    refused = next(h.payload(f"attempt-{n:05d}.received.json") for n in range(1, 4)
        if h.payload(f"attempt-{n:05d}.received.json")["diagnostic"] is not None)
    assert not (h.directory / f'attempt-{refused["attempt"]:05d}.raw').exists()
    assert refused["charged_bytes"] == chunk.MAXIMUM_RESPONSE_BYTES
    assert len(h.calls) == 3


def test_unregistered_runtime_refuses_before_any_source_or_key(monkeypatch):
    monkeypatch.setattr(chunk, "PREDECESSOR_MANIFEST_SHA256", "PENDING")
    with pytest.raises(chunk.BoundedRecoveryRefusal, match="prospective_bounded_protocol"):
        chunk.run_registered(chunk.lane.ROOT, runtime_head="a" * 40,
            actual_remote="b" * 40, complete_code_manifest={})


def test_closure_cannot_predate_any_actual_receipt(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    previous = h.clock
    def clock():
        # global start + three STARTs + three receipts, then the eighth
        # observation is a closure clock stepped back behind all receipts.
        value = previous()
        return "2026-10-24T00:00:00.000002Z" if h.n == 8 else value
    h.clock = clock
    assert h.run() is None
    assert (h.directory / "run.refused.json").exists()


def test_deadline_during_HTTP_drains_but_cannot_claim_positive(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    def response(n, request):
        h.tick = chunk.MAXIMUM_SECONDS + 1
    h.failure = response
    assert h.run() is None
    value = h.payload("run.refused.json")
    assert value["START_debits"] == 3
    assert 1 <= len(h.calls) == value["known_HTTP_invocations"] <= 3
    assert value["HTTP_count_exact"] and value["unreceipted_attempts"] == []
    assert value["code"] in {"postpublication_chunk_refused", "unrecovered_attempt_no_more_STARTs"}
    assert not (h.directory / "chunk.closed.json").exists()


@pytest.mark.parametrize("stage", ["attempt-00001.received.json", "chunk.completed.provisional.json"])
def test_external_new_spent_claim_remains_under_custody(monkeypatch, tmp_path, stage):
    h = Harness(monkeypatch, tmp_path); fired = []
    def tamper():
        if (h.directory / stage).exists() and not fired:
            fired.append(True)
            (h.root / chunk.CLAIM).write_bytes(b"changed spent claim")
    h.hook = tamper
    assert h.run() is None
    assert (h.directory / "run.refused.json").exists()


def test_final_audit_cannot_finish_positive_after_deadline(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    def late():
        if (h.directory / "chunk.closed.json").exists():
            h.tick = chunk.MAXIMUM_SECONDS + 1
    h.hook = late
    assert h.run() is None
    assert h.payload("run.refused.json")["code"] == "postpublication_chunk_refused"


def test_final_audit_revisits_earlier_member_stamps(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path); fired = []
    real_read = chunk.os.read
    def read(fd, maximum):
        later = h.directory / "attempt-00003.raw"
        if (h.directory / "chunk.closed.json").exists() and later.exists() and not fired:
            if chunk.os.fstat(fd).st_ino == later.stat().st_ino:
                fired.append(True)
                earlier = h.directory / "attempt-00001.raw"
                earlier.write_bytes(b"X" * earlier.stat().st_size)
        return real_read(fd, maximum)
    monkeypatch.setattr(chunk.os, "read", read)
    assert h.run() is None
    assert fired and (h.directory / "run.refused.json").exists()


def test_deadline_rechecked_before_each_START_not_just_batch(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    def publish(owned, name, raw, **kwargs):
        value = h.real_publish(owned, name, raw, **kwargs)
        if name == "attempt-00001.started.json":
            h.tick = chunk.MAXIMUM_SECONDS + 1
        return value
    monkeypatch.setattr(chunk._OwnedOutput, "publish", publish)
    assert h.run() is None
    assert h.payload("run.refused.json")["START_debits"] == 1
    assert h.calls == []


@pytest.mark.parametrize("stage", ["before_inventory", "after_provisional", "after_close"])
def test_failed_complete_source_audit_is_dominant_negative(monkeypatch, tmp_path, stage):
    h = Harness(monkeypatch, tmp_path)
    state = {"source_failed": False}
    def check():
        if state["source_failed"]:
            raise chunk.BoundedRecoveryRefusal("old_source_changed")
    h.check = check
    def source_final_audit():
        refused = (stage == "before_inventory" or (stage == "after_provisional"
            and (h.directory / "chunk.completed.provisional.json").exists()) or (stage == "after_close"
            and (h.directory / "chunk.closed.json").exists()))
        if refused:
            state["source_failed"] = True
            raise chunk.BoundedRecoveryRefusal("old_source_changed")
    assert h.run(source_final_audit=source_final_audit, refusal_check=lambda: None) is None
    assert (h.directory / "run.refused.json").exists()


def test_full_current_code_reuses_cache_FDs_without_losing_members(monkeypatch, tmp_path):
    root = tmp_path.resolve(); root.chmod(0o700)
    (root / "base.py").write_bytes(b"old base")
    (root / "extra.py").write_bytes(b"new extra")
    monkeypatch.setattr(chunk, "code_paths", lambda: ("base.py", "extra.py"))
    monkeypatch.setattr(chunk.old.cache, "COUNT_CODE_FILES", ("base.py",))
    monkeypatch.setattr(chunk.lane, "ROOT", root)
    with chunk.old.cache.HeldFiles((root / "base.py",), protected=False, boundary=lambda: None) as base, \
         chunk.old.cache.HeldFiles((root / "extra.py",), protected=False, boundary=lambda: None) as extra:
        combined = chunk._ComposedCodeCustody(root, base, extra)
        assert combined.read(root / "base.py", 64) == b"old base"
        assert combined.read(root / "extra.py", 64) == b"new extra"
        with pytest.raises(chunk.BoundedRecoveryRefusal):
            combined.read(root / "absent.py", 64)
        (root / "base.py").write_bytes(b"changed base")
        with pytest.raises(Exception):
            combined.check()


def test_insufficient_FD_headroom_is_preclaim_not_new_spent_debit(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    def refuse():
        raise chunk.old.RecoveryRefusal("REFUSED: insufficient_preclaim_descriptor_headroom")
    monkeypatch.setattr(chunk.old, "require_fd_headroom", refuse)
    with pytest.raises(chunk.old.RecoveryRefusal, match="insufficient_preclaim_descriptor_headroom"):
        h.run()
    assert not (h.root / chunk.CLAIM).exists()
    assert "key" not in h.events and h.calls == []
