"""Fabricated complete monthly controls; no private source, key or network."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
from types import MappingProxyType

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import capture_short_interest_native_market_inputs as capture
from scripts import qualify_finra_short_interest as captureio
from scripts import qualify_short_interest_native_monthly_market as operational
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)


REGISTRATION = {"head": "a" * 40, "remote": "b" * 40, "code_identity_sha256": "c" * 64}
START = "2026-10-14T00:42:32Z"


def row(table, month, ticker="FABRICATED", **changes):
    at = next(bounds[1] for bounds in capture.inputs.MONTHS if bounds[0] == month)
    result = dict.fromkeys(capture.inputs.FIELDS[table], 1)
    result.update(ticker=ticker, date=at, lastupdated="2026-10-13")
    result.update(changes)
    return result


class FakeSnapshot:
    def __init__(self, files, claim):
        self.files, self.claim_raw = files, claim
        self.reads, self.full_checks, self.broken = [], 0, False
        self.hook = lambda: None
        self.manifest_raw = canonical_json([{"name": name, "bytes": len(raw), "sha256": hash_bytes(raw)}
            for name, raw in sorted(files.items())]).encode()

    @property
    def controls(self):
        return MappingProxyType({name: self.files[name] for name in operational.source.CONTROL_PINS})

    def names(self):
        self.check()
        return tuple(sorted(self.files))

    def check(self):
        self.hook()
        if self.broken:
            raise operational.MonthlyMarketOperationalRefusal("REFUSED: fabricated_source_custody_changed")

    def full_check(self):
        self.check(); self.full_checks += 1

    def read(self, name, maximum):
        self.check(); self.reads.append(name)
        raw = self.files[name]
        assert len(raw) <= maximum
        return raw

    def payload(self, name):
        return json.loads(self.files[name])

    def save(self, name, value):
        self.files[name] = (canonical_json(value) + "\n").encode()

    def reseal_inventory(self):
        report = self.payload("inventory.private.json")
        report["report_sha256"] = hash_payload({key: value for key, value in report.items() if key != "report_sha256"})
        self.save("inventory.private.json", report)
        completed = self.payload("completed.json")
        completed["private_report_sha256"] = report["report_sha256"]
        self.save("completed.json", completed)


@pytest.fixture(autouse=True)
def deny_network_processes(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("fabricated monthly tests cannot perform I/O")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "run", denied)


def fabricated(monkeypatch, *, issue=False, cross_page=False):
    files, clock_count = {}, [0]
    def clock():
        clock_count[0] += 1
        return (datetime(2026, 10, 14, 0, 42, 32, tzinfo=timezone.utc)
            + timedelta(seconds=clock_count[0])).isoformat().replace("+00:00", "Z")
    def raw_save(owner, name, value):
        assert name not in files and type(value) is bytes
        files[name] = value
    def http(opener, request, maximum):
        number = len([name for name in files if name.endswith(".started.json")])
        panel = json.loads(files[f"attempt-{number:05d}.started.json"])
        values = [row(panel["table"], panel["month"])]
        if cross_page and panel["table"] == "stocks" and panel["month"] == "2022-01":
            values = ([row("stocks", "2022-01", ticker=f"FAB{index:05d}") for index in range(10000)]
                if panel["page"] == 0 else [row("stocks", "2022-01", ticker=" FAB00000 ")])
        if issue and number == 1:
            values.append(row(panel["table"], panel["month"], ticker=" FABRICATED ", close="1"))
        return canonical_json({"count": len(values), "data": values}).encode(), "application/json", 200
    with monkeypatch.context() as nested:
        nested.setattr(capture, "_guard", lambda *unused: None)
        # Keep the ORIGINAL serializer. Its global raw sink is the only seam;
        # replacing _publish_json would hide source-control byte conventions.
        assert capture._publish_json is captureio._publish_json
        nested.setattr(captureio, "_publish", raw_save)
        nested.setattr(capture, "_publish", raw_save)
        nested.setattr(capture, "_utc_now", clock)
        nested.setattr(capture, "_http", http)
        capture._capture(Path("/fabricated"), Path("/fabricated/run"), object(),
            capture.KeychainSecret("fabricated-only-key"), head=operational.source.SOURCE_HEAD,
            remote=operational.source.SOURCE_REMOTE, started_at=START)
    protocol = capture.protocol()
    files["protocol.json"] = (canonical_json(protocol) + "\n").encode()
    files["started.json"] = (canonical_json({"schema": "si-native-market-input-start-v1",
        "code_head": operational.source.SOURCE_HEAD, "remote_head": operational.source.SOURCE_REMOTE,
        "protocol_sha256": operational.SOURCE_PROTOCOL_SHA256,
        "code_identity_sha256": operational.source.CODE_IDENTITY_SHA256, "started_at": START,
        "maximum_requests": protocol["maximum_requests"], "outcome_looks": 0, "qc_attempts": 0}) + "\n").encode()
    claim = (canonical_json({"schema": "si-native-market-input-budget-v1", "claim_sha256": operational.source.CLAIM_ID,
        "code_head": operational.source.SOURCE_HEAD, "remote_head": operational.source.SOURCE_REMOTE,
        "run_id": operational.source.DIRECTORY.name, "protocol_sha256": operational.SOURCE_PROTOCOL_SHA256,
        "maximum_requests": protocol["maximum_requests"], "started_at": START, "restart_or_resume": False}) + "\n").encode()
    assert len(files) == (456 if cross_page else 452)
    return FakeSnapshot(files, claim)


def qualify(snapshot, check=lambda: None):
    return operational._qualify_snapshot(snapshot, check=check, registration=copy.deepcopy(REGISTRATION))


def test_exact_original_json_publisher_one_LF_is_required(monkeypatch):
    saved = {}
    value = {"schema": "fabricated-control", "count": 1}
    monkeypatch.setattr(captureio, "_publish", lambda owner, name, raw: saved.setdefault(name, raw))
    captureio._publish_json(Path("/fabricated"), "control.json", value)
    assert saved["control.json"] == (canonical_json(value) + "\n").encode()
    assert operational._parsed(saved["control.json"]) == value


@pytest.mark.parametrize("prefix,suffix", [(b"", b""), (b"", b"\n\n"), (b"", b"\n\t"),
    (b"", b"\n "), (b"", b" \n"), (b"", b"\t\n"), (b" ", b"\n"), (b"\t", b"\n")])
def test_non_original_control_whitespace_is_not_normalized(prefix, suffix):
    raw = prefix + canonical_json({"schema": "fabricated-control", "count": 1}).encode() + suffix
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="original_canonical_control_required"):
        operational._parsed(raw)


@_POSIX_CAPTURE_ONLY
def test_all112_panels_before_first_yield_and_bounded_replay(monkeypatch):
    snap = fabricated(monkeypatch)
    with qualify(snap) as report:
        assert len([name for name in snap.reads if name.endswith(".raw")]) == 112
        assert all(type(entry) is str for entry in report._entries)
        with pytest.raises(TypeError):
            report._entries[0]["qualification_sha256"] = "mutable checkpoint forbidden"
        assert "FABRICATED" not in repr(report)
        public = report.public_summary()
        assert public["original_panels_replayed"] == public["original_attempts_replayed"] == 112
        assert set(public) == {"schema", "original_panels_replayed", "original_attempts_replayed",
            "source_protocol_sha256", "runtime_code_identity_sha256", "authority"}
        assert not public["authority"]["ready_for_backtesting"]
        assert not public["authority"]["actual_input_execution_admitted"]
        first = next(report.iter_panels())
        assert first.to_payload()["rows"][0]["normalized"]["raw_volume"] == {"numerator": 1, "denominator": 1}
        assert len([name for name in snap.reads if name.endswith(".raw")]) == 113
        detached = report.to_payload(); detached["runtime_lineage"]["head"] = "changed"
        detached["panels"][0]["before"][0] = 999
        assert report.to_payload()["runtime_lineage"]["head"] == REGISTRATION["head"]
        assert report.to_payload()["panels"][0]["before"][0] == 0
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="sealed_monthly_context_changed"):
        report.to_payload()


@_POSIX_CAPTURE_ONLY
def test_original_malformed_and_duplicate_events_are_retained_not_terminal(monkeypatch):
    snap = fabricated(monkeypatch, issue=True)
    with qualify(snap) as report:
        rows = next(report.iter_panels()).to_payload()["rows"]
        assert len(rows) == 2 and all(item["normalized"] is None for item in rows)
        assert all("all_identifiable_duplicate_peers_quarantined" in item["refusal_reasons"] for item in rows)


@_POSIX_CAPTURE_ONLY
def test_cross_page_duplicate_peer_origins_replayed_from_real_original_events(monkeypatch):
    snap = fabricated(monkeypatch, cross_page=True)
    monkeypatch.setattr(operational, "EXPECTED_ATTEMPTS", 113)
    monkeypatch.setattr(operational.source, "ATTEMPTS", 113)
    page_events = snap.payload("attempt-00002.refusals.private.json")["refusals"]
    assert page_events[-1]["first_source_origin"]["attempt"] == 1
    assert page_events[-1]["new_source_origins"][0]["attempt"] == 2
    with qualify(snap) as report:
        first = next(report.iter_panels()).to_payload()
        assert len(first["page_origins"]) == 2 and len(first["rows"]) == 10001
        assert first["rows"][0]["normalized"] is None and first["rows"][-1]["normalized"] is None
        assert first["rows"][0]["source_origin"]["page_number"] == 0
        assert first["rows"][-1]["source_origin"]["page_number"] == 1


@pytest.mark.parametrize("kind", ["missing", "extra_negative", "START", "request", "raw_hash", "clock", "totals", "panel_order", "receipt_extra", "malformed_event", "duplicate_group"])
@_POSIX_CAPTURE_ONLY
def test_corrupt_last_or_original_evidence_prevents_any_yield(monkeypatch, kind):
    snap = fabricated(monkeypatch, issue=True)
    if kind == "missing":
        del snap.files["attempt-00112.raw"]
    elif kind == "extra_negative":
        snap.files["attempt-00001.refused.json"] = b"{}"
    elif kind in {"START", "request"}:
        value = snap.payload("attempt-00112.started.json")
        if kind == "START": value["attempt"] = 111
        else: value["request"]["params"]["offset"] = "10000"
        snap.save("attempt-00112.started.json", value)
    elif kind in {"raw_hash", "clock", "receipt_extra"}:
        value = snap.payload("attempt-00112.received.json")
        if kind == "raw_hash": value["raw_sha256"] = "0" * 64
        elif kind == "clock": value["received_at"] = START
        else: value["unknown"] = "ignored-is-not-allowed"
        snap.save("attempt-00112.received.json", value)
    else:
        value = snap.payload("inventory.private.json")
        if kind == "totals": value["total_raw_rows"] += 1
        elif kind == "panel_order": value["panels"][-2:] = list(reversed(value["panels"][-2:]))
        elif kind == "malformed_event": value["panels"][0]["malformed_refusals"] = []
        else: value["panels"][0]["duplicate_groups"] = []
        snap.save("inventory.private.json", value); snap.reseal_inventory()
    with pytest.raises((ValueError, KeyError)):
        with qualify(snap):
            pytest.fail("unverified complete source escaped")


@_POSIX_CAPTURE_ONLY
def test_page_refusal_event_origin_loss_refuses_even_when_top_report_is_unchanged(monkeypatch):
    snap = fabricated(monkeypatch, issue=True)
    value = snap.payload("attempt-00001.refusals.private.json")
    value["refusals"][1]["new_source_origins"] = []
    snap.save("attempt-00001.refusals.private.json", value)
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="original_page_refusal_events_required"):
        with qualify(snap):
            pytest.fail("missing original peer origin escaped")


@pytest.mark.parametrize("kind", ["rows", "bytes", "attempts"])
@_POSIX_CAPTURE_ONLY
def test_whole_next_page_budget_is_checked_before_reading_a_new_attempt(monkeypatch, kind):
    snap = fabricated(monkeypatch)
    panel = capture.protocol()["panels"][0]
    original = snap.payload("inventory.private.json")["panels"][0]
    state = [0, 0, 0, START]
    if kind == "rows": state[2] = capture.inputs.MAXIMUM_ROWS - capture.inputs.PAGE_LIMIT + 1
    elif kind == "bytes": state[1] = capture.inputs.MAXIMUM_RAW_BYTES - capture.inputs.MAXIMUM_BYTES + 1
    else: state[0] = capture.inputs.MAXIMUM_REQUESTS
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="whole_next_page_budget"):
        operational._replay_panel(snap, panel, original, state=state,
            retrieved_at=snap.payload("inventory.private.json")["retrieved_at"], check=lambda: None)
    assert snap.reads == []


@_POSIX_CAPTURE_ONLY
def test_prefix_consumer_cannot_skip_late_panel_verification(monkeypatch):
    snap = fabricated(monkeypatch)
    last = snap.payload("attempt-00112.refusals.private.json")
    last["financial_values_normalized"] = True
    snap.save("attempt-00112.refusals.private.json", last)
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="original_page_refusal_events_required"):
        with qualify(snap) as report:
            next(report.iter_panels())


@pytest.mark.parametrize("kind", ["start_code", "claim", "digest", "retrieved", "completed", "authority"])
@_POSIX_CAPTURE_ONLY
def test_original_global_proofs_and_clocks_cannot_be_substituted(monkeypatch, kind):
    snap = fabricated(monkeypatch)
    if kind == "start_code":
        value = snap.payload("started.json"); value["code_identity_sha256"] = "0" * 64
        snap.save("started.json", value)
    elif kind == "claim":
        value = json.loads(snap.claim_raw); value["restart_or_resume"] = True
        snap.claim_raw = (canonical_json(value) + "\n").encode()
    elif kind == "completed":
        value = snap.payload("completed.json"); value["completed_at"] = START
        snap.save("completed.json", value)
    else:
        value = snap.payload("inventory.private.json")
        if kind == "digest": value["report_sha256"] = "0" * 64
        elif kind == "retrieved": value["retrieved_at"] = START
        else: value["data_or_fitness_admitted"] = True
        snap.save("inventory.private.json", value)
        if kind != "digest": snap.reseal_inventory()
    with pytest.raises(ValueError):
        with qualify(snap):
            pytest.fail("unproven global source controls escaped")


@_POSIX_CAPTURE_ONLY
def test_late_final_source_custody_failure_cannot_escape_first_yield(monkeypatch):
    snap = fabricated(monkeypatch)
    original = snap.full_check
    def fail_final():
        original()
        if snap.full_checks == 2:
            snap.broken = True
    snap.full_check = fail_final
    with pytest.raises(ValueError, match="fabricated_source_custody_changed"):
        with qualify(snap):
            pytest.fail("late full-source custody failure escaped")


@pytest.mark.parametrize("kind", ["source", "current_code", "controls"])
@_POSIX_CAPTURE_ONLY
def test_custody_remains_live_through_prefix_consumption_and_exit(monkeypatch, kind):
    snap, changed = fabricated(monkeypatch), [False]
    def check():
        if changed[0]:
            raise ValueError("fabricated_current_code_changed")
    with pytest.raises(ValueError):
        with qualify(snap, check=check) as report:
            next(report.iter_panels())
            if kind == "source": snap.broken = True
            elif kind == "current_code": changed[0] = True
            else: snap.files["protocol.json"] += b" "
            report.public_summary()


@_POSIX_CAPTURE_ONLY
def test_mid_context_capture_protocol_change_cannot_silently_make_iteration_empty(monkeypatch):
    snap = fabricated(monkeypatch)
    with qualify(snap) as report:
        with monkeypatch.context() as nested:
            original = operational.inputs.market_input_protocol
            nested.setattr(operational.inputs, "market_input_protocol", lambda: {**original(), "panels": []})
            with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="policy|protocol"):
                list(report.iter_panels())


@_POSIX_CAPTURE_ONLY
def test_mid_context_pure_policy_change_cannot_relabel_cached_qualification(monkeypatch):
    snap = fabricated(monkeypatch)
    with qualify(snap) as report:
        with monkeypatch.context() as nested:
            original = operational.monthly.qualification_policy
            nested.setattr(operational.monthly, "qualification_policy", lambda: {**original(), "raw_volume": "changed"})
            with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="policy"):
                report.public_summary()


def test_unregistered_current_code_refuses_before_snapshot_or_Git(monkeypatch):
    monkeypatch.setattr(operational, "CURRENT_CODE_FILES", ())
    monkeypatch.setattr(operational.source, "load_registered_snapshot", lambda *unused: pytest.fail("source reached"))
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="current_code_paths_pending"):
        with operational.qualify_registered(operational.lane.ROOT, runtime_head="a" * 40,
            actual_remote="b" * 40, complete_code_manifest={}):
            pytest.fail("PENDING current code gate passed")


@_POSIX_CAPTURE_ONLY
def test_current_committed_manifest_mismatch_refuses_before_source(monkeypatch):
    class FakeGuard:
        def __init__(self, *args, **kwargs): pass
        def check(self): pass
        def refresh(self): pass
    class Held:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def check(self): pass
    names = (operational.DRIVER,)
    monkeypatch.setattr(operational, "CURRENT_CODE_FILES", names)
    monkeypatch.setattr(operational, "CURRENT_CODE_PATHS_SHA256", hash_payload(list(names)))
    monkeypatch.setattr(operational.lane, "LaneGuard", FakeGuard)
    monkeypatch.setattr(operational.custody, "HeldFiles", Held)
    monkeypatch.setattr(operational.custody, "_code_manifest", lambda *unused: (({"path": names[0], "sha256": "0" * 64},), "1" * 64))
    monkeypatch.setattr(operational.source, "load_registered_snapshot", lambda *unused: pytest.fail("source reached"))
    with pytest.raises(operational.MonthlyMarketOperationalRefusal, match="current_committed_code_bytes_changed"):
        with operational.qualify_registered(operational.lane.ROOT, runtime_head="a" * 40,
            actual_remote="b" * 40, complete_code_manifest={names[0]: "f" * 64}):
            pytest.fail("different code manifest passed")
