"""Fabricated protected outputs only; network denied and no real key read."""
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest

from data.hashing import hash_bytes, hash_payload
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.continue_short_interest_native_identity import ContinuationRefusal
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret
import scripts.capture_short_interest_native_reported_count_round as m

SPEC = importlib.util.spec_from_file_location("operational_anchor_fixtures",
        Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
HEAD, REMOTE, CODE = "a" * 40, "b" * 40, "d" * 64
KEY = "FABRICATED_COUNT_RUNTIME_KEY_73"
RAW = b'{"status":"OK","results":{}}'


class Clock:
    def __init__(self):
        self.current = datetime(2026, 10, 14, 4, tzinfo=timezone.utc)
        self.lock = threading.Lock()
    def __call__(self):
        with self.lock:
            self.current += timedelta(microseconds=1)
            return self.current.isoformat().replace("+00:00", "Z")


def setup(monkeypatch, tmp_path, count=12, maximum=None):
    dates = tuple((date(2022, 1, 3) + timedelta(days=index * 100)).isoformat() for index in range(count))
    matrix = f.matrix([("SYN", day) for day in dates])
    source = m.anchors.build_native_reported_anchor_plan(matrix, tuple(f.identity(day) for day in dates),
            f.actions(), f.dictionary())
    budget = maximum or count * m.parallel.MAXIMUM_RESPONSE_BYTES
    plan = m.parallel.freeze_parallel_count_plan(source.query_plan, maximum_total_response_bytes=budget)
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    for name, value in (("ANCHOR_PLAN_SHA256", source.sha256), ("PARALLEL_PLAN_SHA256", plan.sha256),
            ("CACHE_CLOSURE_SHA256", "c" * 64),
            ("MAXIMUM_TOTAL_RESPONSE_BYTES", budget)):
        monkeypatch.setattr(m, name, value)
    monkeypatch.setattr(m, "PROTOCOL_SHA256", hash_payload(m.protocol()))
    state = {"head": HEAD, "remote": REMOTE, "remote_reads": 0, "keys": 0, "http": [], "publications": []}
    def runner(root, command):
        if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return (str(m.lane.ROOT) + "\n").encode()
        if command[:2] == ["git", "status"]:
            return ("# branch.oid " + state["head"] + "\n# branch.head codex/strategy-short-interest\n").encode()
        assert command == ["git", "ls-remote", "--exit-code", "origin", m.lane.REF]
        state["remote_reads"] += 1
        return (state["remote"] + "\t" + m.lane.REF + "\n").encode()
    guard = m.lane.LaneGuard(m.lane.ROOT, expected_head=HEAD, expected_remote=REMOTE,
            runner=runner, physical=lambda root: None)
    parent = tmp_path.resolve() / "protected"
    parent.mkdir(mode=0o700)
    directory = parent / "run"
    directory.mkdir(mode=0o700)
    def key(provider):
        state["keys"] += 1
        assert provider == "massive"
        assert any(p.name.startswith("budget-") for p in parent.iterdir())
        assert (directory / "started.json").exists() and (directory / "protocol.private.json").exists()
        return KeychainSecret(KEY)
    def http(opener, request, maximum):
        state["http"].append(request)
        ordinal = len(state["http"])
        assert (directory / f"query-{ordinal:08d}.started.json").exists()
        assert request.get_header("Authorization") == "Bearer " + KEY
        assert KEY not in request.full_url and maximum == m.parallel.MAXIMUM_RESPONSE_BYTES
        return RAW, "application/json", 200
    args = dict(head=HEAD, remote=REMOTE, code_identity_sha256=CODE, source_custody=lambda: None,
            code_custody=lambda: None, read_secret=key, clock=Clock(), guard=guard, http=http)
    return source, plan, directory, args, state


def run(value):
    source, plan, directory, args, state = value
    with _OwnedOutput(directory, lambda: None) as owned:
        return m.capture_loaded_source(m.lane.ROOT, directory, source, plan, owned=owned, **args)


def test_exact_all_queries_claim_before_key_start_before_http_and_private_zero_authority(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    result = run(value)
    state, directory = value[4], value[2]
    assert len(state["http"]) == 12 and state["keys"] == 1
    assert result.to_payload()["complete_frozen_request_sequence"] is True
    assert result.to_payload()["authority"]["outcome_looks"] == 0
    assert (directory / "completed.json").exists()
    assert len(list(directory.glob("*.raw"))) == 12
    # Remote reads are bounded publication/HTTP batches, not worker/chunk calls.
    assert state["remote_reads"] == 18


def test_duplicate_global_claim_is_immutable_and_key_never_read_again(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path, count=2)
    run(value)
    old = {p.name: hash_bytes(p.read_bytes()) for p in value[2].parent.iterdir() if p.is_file()}
    second = value[2].parent / "run-second"
    second.mkdir(mode=0o700)
    with _OwnedOutput(second, lambda: None) as owned, pytest.raises(FileExistsError):
        m.capture_loaded_source(m.lane.ROOT, second, value[0], value[1], owned=owned, **value[3])
    assert value[4]["keys"] == 1 and not tuple(second.iterdir())
    assert old == {p.name: hash_bytes(p.read_bytes()) for p in second.parent.iterdir() if p.is_file()}


def test_named_key_unavailable_has_owned_zero_http_refusal_after_consumed_claim(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path, count=2)
    def missing(provider):
        raise ValueError("not published external text")
    value[3]["read_secret"] = missing
    with pytest.raises(m.parallel.ParallelCountRefusal, match="named_key_or_custody"):
        run(value)
    refusal = json.loads((value[2] / "run.refused.json").read_bytes())
    assert refusal["attempts_started"] == 0 and not value[4]["http"]
    assert len(list(value[2].parent.glob("budget-*.json"))) == 1


@pytest.mark.parametrize("mode", ["raw", "unicode", "percent", "media"])
def test_secret_echo_refuses_before_body_hash_or_persistence(monkeypatch, tmp_path, mode):
    value = setup(monkeypatch, tmp_path, count=2)
    encoded = (KEY.encode() if mode == "raw" else ("".join("\\u%04x" % ord(c) for c in KEY).encode()
            if mode == "unicode" else "".join("%%%02x" % ord(c) for c in KEY).encode()))
    raw = RAW if mode == "media" else b'{"echo":"' + encoded + b'"}'
    media = "application/json; key=" + KEY if mode == "media" else "application/json"
    original_hash = m.hash_bytes
    def no_bad_hash(candidate):
        assert candidate != raw
        return original_hash(candidate)
    monkeypatch.setattr(m, "hash_bytes", no_bad_hash)
    value[3]["http"] = lambda *args: (raw, media, 200)
    result = run(value)
    assert result.to_payload()["halted"] and not list(value[2].glob("*.raw"))
    assert not (value[2] / "completed.json").exists()
    assert all(r["body_observed"] is False for r in result.iter_receipts())


def test_current_key_echo_in_descriptor_refuses_before_started_receipt_and_http(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path, count=2)
    value[3]["read_secret"] = lambda provider: KeychainSecret("SYN")
    result = run(value)
    assert result.to_payload()["attempts_started"] == 0 and not value[4]["http"]
    assert not list(value[2].glob("query-*.started.json"))


def test_404_retained_unobserved_negative_all_later_frozen_queries_continue(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    def missing(opener, request, maximum):
        value[4]["http"].append(request)
        raise SharadarCaptureRefusal("fixed", status=404)
    value[3]["http"] = missing
    inventory = run(value)
    assert inventory.to_payload()["complete_frozen_request_sequence"] and len(value[4]["http"]) == 12
    assert not list(value[2].glob("*.raw"))
    assert all(r["http_status"] == 404 and r["body_observed"] is False and r["raw_sha256"] is None
            for r in inventory.iter_receipts())


@pytest.mark.parametrize("status", [403, 429, 500, None])
def test_material_failure_drains_at_most_eight_started_without_new_batch(monkeypatch, tmp_path, status):
    value = setup(monkeypatch, tmp_path)
    def failed(opener, request, maximum):
        value[4]["http"].append(request)
        if status is None:
            raise OSError("not published source exception")
        raise SharadarCaptureRefusal("fixed", status=status)
    value[3]["http"] = failed
    inventory = run(value)
    assert len(value[4]["http"]) == inventory.to_payload()["attempts_started"] == 8
    assert inventory.to_payload()["halted"] and not (value[2] / "completed.json").exists()
    assert len(list(value[2].glob("*.received.json"))) == 8


def test_remote_advancement_drains_exact_started_prefix_without_success_or_next_batch(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    original = value[3]["http"]
    def advanced(*args):
        result = original(*args)
        value[4]["remote"] = "e" * 40
        return result
    value[3]["http"] = advanced
    inventory = run(value)
    assert len(value[4]["http"]) == 8 and inventory.to_payload()["halted"]
    assert len(list(value[2].glob("*.raw"))) == len(list(value[2].glob("*.received.json"))) == 8
    assert not (value[2] / "completed.json").exists() and (value[2] / "run.refused.json").exists()


def test_full_page_reservation_ceiling_blocks_next_query_before_http(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path, maximum=m.parallel.MAXIMUM_RESPONSE_BYTES)
    inventory = run(value)
    assert len(value[4]["http"]) == 1 and inventory.to_payload()["halted"]
    assert inventory.to_payload()["charged_response_bytes"] == len(RAW)


def test_pending_protocol_or_scope_reflection_never_reads_key_or_spends_claim(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path, count=2)
    monkeypatch.setattr(m, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(m.parallel.ParallelCountRefusal, match="pending_or_changed"):
        run(value)
    assert not value[4]["keys"] and not value[4]["http"] and not tuple(value[2].iterdir())


def test_callback_cannot_change_imported_response_budget_after_prospective_freeze(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    original = value[3]["http"]
    def mutation(*args):
        result = original(*args)
        monkeypatch.setattr(m.parallel, "MAXIMUM_RESPONSE_BYTES", 2 * 1024 * 1024 + 1)
        return result
    value[3]["http"] = mutation
    with pytest.raises(m.parallel.ParallelCountRefusal, match="scope_changed|pins_pending_or_changed"):
        run(value)
    assert not (value[2] / "completed.json").exists() and not list(value[2].glob("*.raw"))


def test_prepared_owned_directory_mode_drift_never_publishes_sensitive_results(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    original = value[3]["http"]
    def mutation(*args):
        result = original(*args)
        value[2].chmod(0o755)
        return result
    value[3]["http"] = mutation
    with pytest.raises(ContinuationRefusal, match="protection"):
        run(value)
    assert not list(value[2].glob("*.raw")) and not (value[2] / "completed.json").exists()


def test_backward_worker_clock_refuses_no_completed_receipt_and_no_retry(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path, count=2)
    good = value[3]["clock"]
    lock, count = threading.Lock(), 0
    def backwards():
        nonlocal count
        with lock:
            count += 1
            # Enclosing start and the two request starts remain genuine;
            # only the first worker's observed end moves backward.
            return "2022-01-01T00:00:00Z" if count == 4 else good()
    value[3]["clock"] = backwards
    with pytest.raises(m.parallel.ParallelCountRefusal, match="receipt_clock_backdated"):
        run(value)
    assert len(value[4]["http"]) == 2 and not (value[2] / "completed.json").exists()


def test_publication_fault_after_authorized_debit_raises_not_undercounted_inventory(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    original = _OwnedOutput.publish
    def failure(self, name, raw, **kwargs):
        if name == "query-00000001.started.json":
            raise ContinuationRefusal("fabricated_started_publication_failed")
        return original(self, name, raw, **kwargs)
    monkeypatch.setattr(_OwnedOutput, "publish", failure)
    with pytest.raises(m.parallel.ParallelCountRefusal, match="started_debit_without_bound_receipt"):
        run(value)
    refused = json.loads((value[2] / "run.refused.json").read_bytes())
    assert refused["attempts_started"] == 8 and not value[4]["http"]
    assert len(list(value[2].parent.glob("budget-*.json"))) == 1
    assert not (value[2] / "completed.json").exists() and not (value[2] / "inventory.private.json").exists()


def test_all_eight_descriptors_prevalidated_before_any_authorized_debit(monkeypatch, tmp_path):
    value = setup(monkeypatch, tmp_path)
    original, seen = m._wire_request, []
    def failure(query, key):
        seen.append(query.to_payload()["query_ordinal"])
        if len(seen) == 2:
            raise m.parallel.ParallelCountRefusal("REFUSED: fabricated_second_descriptor_refused")
        return original(query, key)
    monkeypatch.setattr(m, "_wire_request", failure)
    inventory = run(value)
    assert inventory.to_payload()["attempts_started"] == 0 and not value[4]["http"]
    assert json.loads((value[2] / "run.refused.json").read_bytes())["attempts_started"] == 0
    assert not list(value[2].glob("query-*.started.json"))


def test_supported_host_guard_is_first_before_source_or_output_access(monkeypatch):
    def platform():
        raise ValueError("unsupported")
    monkeypatch.setattr(m, "_require_capture_platform", platform)
    with pytest.raises(ValueError, match="unsupported"):
        m.capture_loaded_source(None, None, None, None, head=HEAD, remote=REMOTE,
            code_identity_sha256=CODE, source_custody=lambda: pytest.fail("source touched"),
            code_custody=lambda: pytest.fail("code touched"), owned=None)
