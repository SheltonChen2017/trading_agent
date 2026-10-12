"""Portable, fabricated-only checks of protected capture's host boundary.

These tests do not skip on Windows and never access a credential, retained
capture, provider or real budget. An OS facade tests capability declarations;
downstream spies make ordering observable without granting storage authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_short_interest_native_master_offline as native
from scripts import calibrate_finra_short_interest as calibration
from scripts import capture_short_interest_securities_master as master
from scripts import finalize_short_interest_master_offline as finalizer
from scripts import qualify_finra_short_interest as finra
from scripts import qualify_sharadar_companion as sharadar
from scripts import qualify_short_interest_action_supplement as supplement


CODE = "protected_capture_platform_unavailable"
RUNTIMES = (finra, calibration, sharadar, supplement, master, finalizer, native)
HEAD = "a" * 40
REMOTE = "b" * 40


def _caps(**overrides):
    values = dict(name="posix", getuid=lambda: 1000, O_NOFOLLOW=1, O_NONBLOCK=2)
    values.update(overrides)
    return SimpleNamespace(**values)


def _guard():
    guard = getattr(finra, "_require_capture_platform", None)
    assert callable(guard), "the protected-runtime preflight is missing"
    return guard


def _assert_refusal(error):
    assert type(error).__name__ == "CapturePlatformRefusal"
    assert isinstance(error, finra.CaptureRefusal)
    assert str(error) == CODE
    assert error.code == CODE
    assert error.http_status is None


@pytest.mark.parametrize("facade", [
    _caps(name="nt"), _caps(name="unknown"),
    SimpleNamespace(name="posix", O_NOFOLLOW=1, O_NONBLOCK=2),
    _caps(getuid=None), _caps(getuid=1000),
    _caps(getuid=lambda: True), _caps(getuid=lambda: -1),
    _caps(getuid=lambda: "1000"), _caps(getuid=lambda: 1.0),
    *[_caps(**{flag: value}) for flag in ("O_NOFOLLOW", "O_NONBLOCK")
      for value in (None, True, False, 0, -1, "1", 1.0)],
    SimpleNamespace(name="posix", getuid=lambda: 1000, O_NOFOLLOW=1),
    SimpleNamespace(name="posix", getuid=lambda: 1000, O_NONBLOCK=2),
])
def test_missing_or_invalid_capabilities_refuse_with_fixed_code(monkeypatch, facade):
    monkeypatch.setattr(finra, "os", facade)
    with pytest.raises(finra.CaptureRefusal) as failure:
        _guard()()
    _assert_refusal(failure.value)


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_failed_uid_probe_never_emits_external_exception_text(monkeypatch, error_type):
    def failed_uid():
        raise error_type("fabricated-private-exception-canary")
    monkeypatch.setattr(finra, "os", _caps(getuid=failed_uid))
    with pytest.raises(finra.CaptureRefusal) as failure:
        _guard()()
    _assert_refusal(failure.value)
    assert "canary" not in str(failure.value)


@pytest.mark.parametrize("uid", [0, 1000])
def test_supported_capabilities_pass_only_the_host_prerequisite(monkeypatch, uid):
    monkeypatch.setattr(finra, "os", _caps(getuid=lambda: uid))
    assert _guard()() is None


def test_actual_host_has_explicit_capability_result():
    import os
    if os.name == "posix" and all(hasattr(os, name) for name in
                                  ("getuid", "O_NOFOLLOW", "O_NONBLOCK")):
        assert _guard()() is None
    else:
        with pytest.raises(finra.CaptureRefusal) as failure:
            _guard()()
        _assert_refusal(failure.value)


def _argv(module):
    if module in (finra, calibration):
        prefix = "finra-source" if module is finra else "finra-calibration"
        return ["--execute-frozen-protocol", "--expected-worktree", str(Path.cwd()),
                "--expected-head", HEAD, "--expected-protocol-sha256", module.PROTOCOL_SHA256,
                "--credential-file", "fabricated-never-opened.env",
                "--run-id", prefix + "-20261012T000000Z"]
    result = ["--expected-head", HEAD, "--expected-remote", REMOTE]
    if module is sharadar:
        result += ["--credential-file", "fabricated-never-opened.env",
                   "--run-id", "sharadar-companion-20261012T000000Z"]
    return result


SENSITIVE = (
    "_guard_lane", "_guard", "_git", "_read_credentials", "_read_key", "_existing_key",
    "_protected_bytes", "_prepare_capture_directory", "_publish", "_publish_json",
    "_claim", "_claim_budget", "_capture", "_build", "_finalize", "_code_hashes",
    "_reload", "_rebuild_sharadar", "_source_index", "_request", "_source_request",
    "_http", "_issuer_location", "_public_addresses", "_download", "_write_report",
)


def _block_downstream(monkeypatch, *, except_function=None):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("downstream")
        raise AssertionError("host refusal must precede every sensitive action")
    for module in RUNTIMES:
        for name in SENSITIVE:
            if hasattr(module, name) and getattr(module, name) is not except_function:
                monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(finra.urllib.request, "build_opener", forbidden)
    return calls


@pytest.mark.parametrize("module", RUNTIMES, ids=lambda module: module.__name__)
def test_cli_refuses_before_any_sensitive_action(monkeypatch, capsys, module):
    monkeypatch.setattr(finra, "os", _caps(name="nt"))
    calls = _block_downstream(monkeypatch)
    assert module.main(_argv(module)) == 2
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload.get("reason", payload.get("code")) == CODE
    assert payload["ready_for_empirical_backtest"] is False
    assert calls == []
    assert output.err == ""
    assert "fabricated-never-opened" not in output.out
    for field in ("provider_requests", "credential_reads", "outcomes_accessed", "qc_attempts"):
        if field in payload:
            assert payload[field] == 0


# Poisoned arguments are not real paths, credentials or openers. The preflight
# must execute before inspecting them; removing a guard cannot access private
# state while these tests reproduce the regression.
class _Untouched:
    def __getattribute__(self, name):
        raise AssertionError("argument inspected before host refusal")
    def __truediv__(self, other):
        raise AssertionError("path used before host refusal")


POISON = _Untouched()
DIRECT = (
    (finra, "_guard_lane", (POISON, HEAD), {}),
    (finra, "_read_credentials", (POISON,), {}),
    (finra, "_prepare_capture_directory", (POISON,), {}),
    (finra, "_publish", (POISON, "fixture.json", b"{}"), {}),
    (finra, "_request", (POISON, POISON, 1), {}),
    (finra, "_capture", (POISON, POISON, POISON), {"tickers": [], "dates": []}),
    (calibration, "_source_request", (POISON, POISON, 1), {}),
    (calibration, "_capture", (POISON, POISON, POISON), {}),
    (sharadar, "_read_key", (POISON,), {}),
    (sharadar, "_http", (POISON, POISON, 1), {}),
    (sharadar, "_capture", (POISON, POISON, POISON, POISON),
     {"expected_head": HEAD, "expected_remote": REMOTE}),
    (supplement, "_existing_key", (), {}),
    (supplement, "_protected_bytes", (POISON, 1), {}),
    (supplement, "_rebuild_sharadar", (POISON,), {}),
    (supplement, "_claim_budget", (POISON,),
     {"expected_head": HEAD, "expected_remote": REMOTE, "started_at": "2026-10-12T00:00:00Z"}),
    (supplement, "_capture", (POISON, POISON, POISON, POISON, POISON),
     {"expected_head": HEAD, "expected_remote": REMOTE}),
    (master, "_issuer_location", (POISON, POISON, POISON), {}),
    (master, "_public_addresses", (POISON,), {}),
    (master, "_download", (POISON, POISON), {}),
    (master, "_claim", (POISON, HEAD, REMOTE, "2026-10-12T00:00:00Z"), {}),
    (master, "_capture", (POISON, POISON, POISON, POISON), {"head": HEAD, "remote": REMOTE}),
    (finalizer, "_reload", (POISON,), {}),
    (finalizer, "_write_report", (POISON, POISON, POISON, POISON),
     {"head": HEAD, "remote": REMOTE, "started": "2026-10-12T00:00:00Z"}),
    (finalizer, "_finalize", (POISON,), {"head": HEAD, "remote": REMOTE}),
    (native, "_source_index", (POISON, POISON), {}),
    (native, "_build", (POISON,), {"head": HEAD, "remote": REMOTE}),
)


@pytest.mark.parametrize("module,name,args,kwargs", DIRECT,
                         ids=[module.__name__ + "." + name for module, name, _, _ in DIRECT])
def test_direct_sensitive_entry_cannot_bypass_host_guard(monkeypatch, module, name, args, kwargs):
    function = getattr(module, name)
    monkeypatch.setattr(finra, "os", _caps(name="nt"))
    # A fabricated environment mapping prevents reading real credentials even
    # if the implementation's direct environment guard is accidentally absent.
    monkeypatch.setattr(supplement, "os", SimpleNamespace(environ=POISON))
    calls = _block_downstream(monkeypatch, except_function=function)
    with pytest.raises(finra.CaptureRefusal) as failure:
        function(*args, **kwargs)
    _assert_refusal(failure.value)
    assert calls == []


def test_direct_pinned_connection_refuses_before_socket_or_context(monkeypatch):
    monkeypatch.setattr(finra, "os", _caps(name="nt"))
    with pytest.raises(finra.CaptureRefusal) as failure:
        master._PinnedHTTPS.connect(POISON)
    _assert_refusal(failure.value)
