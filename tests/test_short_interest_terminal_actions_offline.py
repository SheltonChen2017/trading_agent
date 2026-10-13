"""Fabricated offline custody/output tests; no provider or credential action."""
from __future__ import annotations

import os
import pytest
from data.hashing import hash_bytes
import scripts.qualify_short_interest_terminal_actions_offline as offline
from tests.test_short_interest_terminal_consideration import ACTION_HEADERS, DICT_HEADERS, action, archive, dictionary

HEAD, REMOTE = "a" * 40, "b" * 40
ANCHOR, START, END = "2026-10-12T06:00:00Z", "2026-10-14T00:00:00Z", "2026-10-14T00:00:01Z"
_REAL_SOURCES = offline._sources
_POSIX = pytest.mark.skipif(not hasattr(os, "getuid"), reason="protected owned 0700/0600 publication requires POSIX; pure and early-refusal tests remain active")


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    # Fabricated bytes only; do not waive the production platform check.
    monkeypatch.setattr(offline, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(offline, "_guard", lambda *args: None)
    monkeypatch.setattr(offline, "_git", lambda root, command, path: path)
    monkeypatch.setattr(offline, "_code_identity", lambda *args: "c" * 64)
    monkeypatch.setattr(offline, "_sources", lambda *args: (
        archive("actions", ACTION_HEADERS, [action()]), archive("descriptions", DICT_HEADERS, [dictionary()]), ANCHOR))
    clocks = iter([START, END])
    monkeypatch.setattr(offline, "_utc_now", lambda: next(clocks))
    return tmp_path


@_POSIX
def test_private_output_protected_exclusive_and_safe_cli_receipt(runtime):
    result = offline._build(runtime, head=HEAD, remote=REMOTE)
    target = runtime / offline.OUTPUT
    assert {path.name for path in target.iterdir()} == {"protocol.json", "started.json", "consideration.private.json", "completed.json"}
    assert target.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in target.iterdir())
    assert result["provider_requests"] == result["credential_reads"] == result["outcome_looks"] == result["qc_attempts"] == 0
    assert result["backtest_result_exists"] is False
    assert result["private_report_bytes_sha256"] == hash_bytes((target / "consideration.private.json").read_bytes())
    assert "terminal_events" not in result and "packages" not in result


def test_invalid_injected_offset_clock_refuses_before_output_creation(runtime, monkeypatch):
    # A fabricated invalid injection is not evidence of a production mismatch.
    monkeypatch.setattr(offline, "_utc_now", lambda: "2026-10-14T00:00:00.123456+00:00")
    with pytest.raises(offline.CaptureRefusal, match="invalid_receipt_clock"):
        offline._build(runtime, head=HEAD, remote=REMOTE)
    assert not (runtime / offline.OUTPUT).exists()


def test_actual_imported_runtime_clock_emits_canonical_Z(monkeypatch):
    from datetime import datetime
    import scripts.qualify_sharadar_companion as companion
    class FabricatedClock:
        @staticmethod
        def now(zone):
            assert zone is companion.timezone.utc
            return datetime(2026, 10, 14, 0, 0, 0, 123456, tzinfo=zone)
    monkeypatch.setattr(companion, "datetime", FabricatedClock)
    assert offline._utc_now is companion._utc_now
    assert offline._utc_now() == "2026-10-14T00:00:00.123456Z"


@_POSIX
def test_existing_output_not_modified_or_appended(runtime, monkeypatch):
    offline._build(runtime, head=HEAD, remote=REMOTE)
    target = runtime / offline.OUTPUT
    before = {path.name: path.read_bytes() for path in target.iterdir()}
    monkeypatch.setattr(offline, "_utc_now", lambda: START)
    with pytest.raises(offline.TerminalActionsOfflineRefusal, match="already_exists"):
        offline._build(runtime, head=HEAD, remote=REMOTE)
    assert {path.name: path.read_bytes() for path in target.iterdir()} == before


@pytest.mark.parametrize("entry", ["_sources", "_build", "main"])
def test_unsupported_host_refuses_before_reads_or_outputs(monkeypatch, entry):
    def deny(): raise offline.CapturePlatformRefusal()
    monkeypatch.setattr(offline, "_require_capture_platform", deny)
    for name in ("_guard", "_prepare_capture_directory", "_publish", "_publish_json"):
        monkeypatch.setattr(offline, name, lambda *args: pytest.fail("sensitive action reached"))
    monkeypatch.setattr(offline.finalizer, "_reload", lambda *args: pytest.fail("source read reached"))
    if entry == "main": assert offline.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    else:
        with pytest.raises(offline.CapturePlatformRefusal):
            getattr(offline, entry)(None, **({"head": HEAD, "remote": REMOTE} if entry == "_build" else {}))


def test_source_reader_reuses_exact_master_custody_once_without_full_report(runtime, monkeypatch):
    captures = (archive("tickers", ["table", "permaticker", "ticker", "exchange", "isdelisted", "category"], []),
                archive("actions", ACTION_HEADERS, []), archive("descriptions", DICT_HEADERS, []))
    calls = []
    monkeypatch.setattr(offline.finalizer, "_reload", lambda root: (calls.append(root) or captures, ANCHOR))
    actions, descriptions, anchor = _REAL_SOURCES(runtime)
    assert calls == [runtime]
    assert actions is captures[1] and descriptions is captures[2] and anchor == ANCHOR


@pytest.mark.parametrize("name,value", [("SOURCE_HEAD", "d" * 40), ("SOURCE_INVENTORY_SHA256", "d" * 64), ("BUDGET_SHA256", "d" * 64)])
def test_mutated_custodian_pins_refuse_before_raw_replay(runtime, monkeypatch, name, value):
    monkeypatch.setattr(offline.finalizer, name, value)
    monkeypatch.setattr(offline.finalizer, "_reload", lambda *args: pytest.fail("source read before fixed-pin refusal"))
    with pytest.raises(offline.TerminalActionsOfflineRefusal, match="pins"):
        _REAL_SOURCES(runtime)


def test_start_before_source_anchor_cannot_create_output(runtime, monkeypatch):
    monkeypatch.setattr(offline, "_utc_now", lambda: "2026-10-12T05:59:59Z")
    with pytest.raises(offline.TerminalActionsOfflineRefusal, match="chronology"):
        offline._build(runtime, head=HEAD, remote=REMOTE)
    assert not (runtime / offline.OUTPUT).exists()


@_POSIX
def test_completion_before_report_keeps_owned_refusal_without_success(runtime, monkeypatch):
    clocks = iter([START, "2026-10-13T23:59:59Z", END])
    monkeypatch.setattr(offline, "_utc_now", lambda: next(clocks))
    with pytest.raises(offline.TerminalActionsOfflineRefusal, match="chronology"):
        offline._build(runtime, head=HEAD, remote=REMOTE)
    target = runtime / offline.OUTPUT
    assert (target / "consideration.private.json").exists()
    assert (target / "refused.json").exists() and not (target / "completed.json").exists()


def test_unignored_output_refuses_before_creation(runtime, monkeypatch):
    monkeypatch.setattr(offline, "_git", lambda *args: "")
    with pytest.raises(offline.TerminalActionsOfflineRefusal, match="ignored"):
        offline._build(runtime, head=HEAD, remote=REMOTE)
    assert not (runtime / offline.OUTPUT).exists()


@_POSIX
def test_later_guard_failure_never_publishes_completion(runtime, monkeypatch):
    def fail_at_report(root, head, remote):
        if (root / offline.OUTPUT / "consideration.private.json").exists():
            raise offline.CaptureRefusal("fabricated remote advancement")
    monkeypatch.setattr(offline, "_guard", fail_at_report)
    with pytest.raises(offline.CaptureRefusal): offline._build(runtime, head=HEAD, remote=REMOTE)
    assert not (runtime / offline.OUTPUT / "completed.json").exists()


def test_no_full_report_materialization_credential_or_transport_exports():
    assert not hasattr(offline, "_http") and not hasattr(offline, "_read_key")
    assert not hasattr(offline, "qualify_sharadar_securities_master")
    protocol = offline.build_protocol()
    assert protocol["consumed_budget_sha256"] == offline.finalizer.BUDGET_SHA256
    assert protocol["provider_requests"] == protocol["credential_reads"] == 0
