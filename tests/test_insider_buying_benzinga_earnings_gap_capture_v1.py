"""Invented inputs only; use OS process-tree network and /usr/bin/security exec denial."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from email.message import Message
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody support")
FILE = Path(__file__).resolve().parents[1] / "research/insider_buying_benzinga_earnings_gap_capture_v1.py"
spec = importlib.util.spec_from_file_location("benzinga_gap_active_test", FILE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

KEY = "invented-private-credential-not-an-actual-key"
HEAD = "a" * 40
RUN = "ib-benzinga-gap-fixture-once"
NOW = "2026-10-14T03:00:00Z"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def body(window=m.WINDOWS[0], *, rows=None, **changes):
    row = {"benzinga_id": "invented-id", "ticker": "INVENTED", "company_name": "Invented Company",
        "date": window[0], "time": "07:30:00", "date_status": "confirmed",
        "last_updated": "2026-10-13T18:00:00Z", "actual_eps": -12345.625,
        "actual_revenue": 9876543210, "estimated_eps": 0.75, "previous_eps": None,
        "fiscal_year": int(window[0][:4]), "importance": 3, "notes": "Not part of metadata projection"}
    result = {"status": "OK", "results": [row] if rows is None else rows,
        "count": 1 if rows is None else len(rows), "request_id": "invented-request"}
    result.update(changes)
    return result


def identity(head):
    assert head == HEAD
    return {"root": "invented-private-root", "branch": m.LANE_BRANCH, "head": HEAD,
        "source_sha256": {"invented.py": "b" * 64},
        "source_inventory_sha256": m._sha(encoded({"invented.py": "b" * 64})), "clean": True}


def folder(root):
    return root.joinpath(*m.ARTIFACT_PARTS, "runs", RUN)


def claims(root):
    return root.joinpath(*m.ARTIFACT_PARTS, "claims")


def invoke(root, *, responses=None, credential=None, transport=None, ident=identity, previous_guard=lambda: None,
           sleeper=None, monotonic=None):
    calls, credential_calls, ticks = [], [], [0.0]
    def read_credential():
        credential_calls.append(len(calls))
        leaf = folder(root) / f"{len(calls):02d}-started.json"
        assert leaf.is_file()
        assert len(list(claims(root).iterdir())) == len(calls) + 1
        return KEY if credential is None else credential()
    def supplied(item):
        m._validate_request(item)
        assert (folder(root) / f"{len(calls):02d}-started.json").is_file()
        calls.append(item)
        index = len(calls) - 1
        return m.ProviderMetadataResponse(200, encoded(body(m.WINDOWS[index]))) if responses is None else responses[index]
    def sleep(seconds):
        assert seconds == m.COOLDOWN_SECONDS
        ticks[0] += seconds
    result = m.run_fixture(RUN, HEAD, root=root, identity=ident,
        credential_loader=read_credential, transport=supplied if transport is None else transport,
        previous_guard=previous_guard, clock=lambda: NOW,
        sleep=sleep if sleeper is None else sleeper,
        monotonic=(lambda: ticks[0]) if monotonic is None else monotonic)
    return result, calls, credential_calls


def test_fixed_exact_three_windows_urls_no_pre2010_or_field_projection():
    assert m.WINDOWS == (("2018-08-01", "2018-08-31"), ("2019-02-01", "2019-02-28"),
                         ("2020-02-01", "2020-02-29"))
    assert len(m.URLS) == 3 and all("limit=50000&sort=date.asc" in url for url in m.URLS)
    assert all("ticker" not in url and "fields" not in url and "apiKey" not in url for url in m.URLS)
    assert m.previous.REQUEST_URL not in m.URLS
    with pytest.raises(m.EarningsGapError, match="fixed_window_refused"):
        m._url(("2006-01-01", "2006-01-31"))


def test_three_claims_starts_before_secret_three_calls_metadata_only_private_custody(tmp_path):
    result, calls, read = invoke(tmp_path)
    assert [item.url for item in calls] == list(m.URLS)
    assert read == [0, 1, 2] and all(KEY not in repr(item) for item in calls)
    assert result["claimed_started_windows"] == result["candidate_metadata_windows"] == 3
    assert result["refused_windows"] == 0 and result["originally_unattempted_windows"] == []
    assert result["source_rows"] == 3 and result["looks_jobs_backtests"] == [0, 0, 0]
    for flag in m.FALSE_FLAGS:
        assert result[flag] is False
    output = folder(tmp_path)
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    leaves = set(p.name for p in output.iterdir())
    assert leaves == {"manifest.json", "complete.json", *[f"{i:02d}-{kind}.json" for i in range(3)
        for kind in ("started", "raw", "metadata", "complete")]}
    for leaf in (*output.iterdir(), *claims(tmp_path).iterdir()):
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o600 and leaf.stat().st_nlink == 1
        if not leaf.name.endswith("-raw.json"):
            raw = leaf.read_bytes()
            assert KEY.encode() not in raw and b"-12345.625" not in raw and b"9876543210" not in raw
    metadata = json.loads((output / "00-metadata.json").read_bytes())
    row = metadata["rows"][0]
    assert row["financial_fields_present"] == ["actual_eps", "actual_revenue", "estimated_eps", "previous_eps"]
    assert row["financial_fields_null"] == ["previous_eps"] and row["actual_value_fields_nonnull"] == ["actual_eps", "actual_revenue"]
    assert "notes" not in row and "fiscal_year" not in row and "actual_eps" not in row
    assert row["actual_release_proven"] is False and metadata["actual_release_archive_verified"] is False
    raw = (output / "00-raw.json").read_bytes()
    assert m.replay_supplied_metadata(raw, hashlib.sha256(raw).hexdigest(), m.WINDOWS[0]) == metadata


def test_permanent_claims_block_second_id_before_secret_and_transport(tmp_path):
    invoke(tmp_path)
    before = {p.name: p.read_bytes() for p in folder(tmp_path).iterdir()}
    def forbidden(*args):
        pytest.fail("a consumed scope reached credential/transport")
    with pytest.raises(m.EarningsGapError, match="already_claimed"):
        m.run_fixture("ib-benzinga-gap-another-once", HEAD, root=tmp_path, identity=identity,
            credential_loader=forbidden, transport=forbidden, clock=lambda: NOW)
    assert before == {p.name: p.read_bytes() for p in folder(tmp_path).iterdir()}


def test_reserved_start_survives_credential_failure_no_call_suffix_unattempted(tmp_path):
    def missing():
        raise RuntimeError("do not print supplied secret text")
    result, calls, read = invoke(tmp_path, credential=missing)
    assert not calls and read == [0]
    assert result["claimed_started_windows"] == result["refused_windows"] == 1
    assert result["originally_unattempted_windows"] == [list(w) for w in m.WINDOWS[1:]]
    assert len(list(claims(tmp_path).iterdir())) == 1
    assert json.loads((folder(tmp_path) / "00-complete.json").read_bytes())["receipt"]["disposition"] == "credential_unavailable"


@pytest.mark.parametrize("status", [401, 403, 429, 500, 301])
def test_http_refusal_stops_one_attempt_error_body_never_retained(tmp_path, status):
    raw = encoded({"error": KEY, "row": "private-upstream-message"})
    result, calls, _ = invoke(tmp_path, responses=[m.ProviderMetadataResponse(status, raw)])
    assert len(calls) == 1 and result["refused_windows"] == 1
    assert result["retained_raw_bytes"] == 0 and result["source_rows"] == 0
    assert not (folder(tmp_path) / "00-raw.json").exists()
    for leaf in folder(tmp_path).iterdir():
        assert KEY.encode() not in leaf.read_bytes() and b"private-upstream-message" not in leaf.read_bytes()


@pytest.mark.parametrize("code", sorted(m._TRANSPORT_CODES))
def test_ambiguous_transport_stays_consumed_without_retries(tmp_path, code):
    result, calls, _ = invoke(tmp_path, responses=[m.ProviderMetadataResponse(None, b"", False, code)])
    assert len(calls) == 1 and result["refused_windows"] == 1
    assert len(list(claims(tmp_path).iterdir())) == 1


def test_paginated_safe_body_retained_but_window_refused_no_followup(tmp_path):
    raw = encoded(body(next_url="https://api.massive.com/benzinga/v1/earnings?cursor=invented-cursor"))
    result, calls, _ = invoke(tmp_path, responses=[m.ProviderMetadataResponse(200, raw)])
    assert len(calls) == 1 and result["candidate_metadata_windows"] == 0 and result["refused_windows"] == 1
    assert (folder(tmp_path) / "00-raw.json").read_bytes() == raw
    metadata = json.loads((folder(tmp_path) / "00-metadata.json").read_bytes())
    assert metadata["pagination_present_not_followed"] is True and metadata["source_page_underfill_refused"] is True


def test_empty_page_accounted_not_certified_complete_archive(tmp_path):
    responses = [m.ProviderMetadataResponse(200, encoded(body(w, rows=[]))) for w in m.WINDOWS]
    result, calls, _ = invoke(tmp_path, responses=responses)
    assert len(calls) == 3 and result["source_rows"] == 0
    metadata = json.loads((folder(tmp_path) / "00-metadata.json").read_bytes())
    assert metadata["empty_page_is_complete_archive"] is False and metadata["historical_coverage_verified"] is False


@pytest.mark.parametrize("count", [True, False, None, "1", 0, 2, 1.0, -1, 50001])
def test_count_type_and_exact_numeric_shape(count):
    with pytest.raises(m.EarningsGapError):
        m._project(encoded(body(count=count)), m.WINDOWS[0], credential=KEY)


@pytest.mark.parametrize("field,value", [("date", "2018-09-01"), ("date", "2018-08-32"),
    ("date", "2006-01-01"), ("time", "24:00:00"), ("date_status", "released"),
    ("last_updated", "2020-01-01T00:00:00"), ("actual_eps", "12.75"),
    ("actual_eps", True), ("actual_revenue", {}), ("ticker", "NAME\nCONTROL")])
def test_source_schema_failure_does_not_become_metadata(field, value):
    source = body()
    source["results"][0][field] = value
    with pytest.raises(m.EarningsGapError):
        m._project(encoded(source), m.WINDOWS[0], credential=KEY)


@pytest.mark.parametrize("raw", [b'{"status":"OK","status":"OK","results":[]}',
    b'{"status":"OK","results":[],"count":NaN}',
    b'{"status":"OK","results":[{"actual_eps":Infinity}]}',
    b'{"status":"OK","results":[{"actual_eps":1e99999}]}', b'[]', b'null', b'{}', b'\xff'])
def test_invalid_json_duplicates_nonfinite_or_oversized_numeric_lexeme(raw):
    with pytest.raises(m.EarningsGapError):
        m._project(raw, m.WINDOWS[0], credential=KEY)


@pytest.mark.parametrize("location", ["company_name", "notes", "request_id", "next_url"])
def test_literal_and_json_escaped_secret_echo_refused(location):
    source = body()
    if location in {"company_name", "notes"}:
        source["results"][0][location] = KEY
    else:
        source[location] = KEY
    raw = encoded(source).replace(KEY.encode(), b"\\u0069" + KEY[1:].encode())
    assert KEY.encode() not in raw
    with pytest.raises(m.EarningsGapError, match="credential_echo_refused"):
        m._project(raw, m.WINDOWS[0], credential=KEY)


@pytest.mark.parametrize("url", ["https://evil.example/benzinga/v1/earnings?cursor=x",
    "http://api.massive.com/benzinga/v1/earnings?cursor=x",
    "https://api.massive.com/benzinga/v1/earnings?apiKey=something",
    "https://api.massive.com/benzinga/v1/earnings?cursor=x&extra=y"])
def test_next_url_not_callable_untrusted_or_credentials_refused(url):
    with pytest.raises(m.EarningsGapError, match="pagination_url_refused"):
        m._project(encoded(body(next_url=url)), m.WINDOWS[0], credential=KEY)


def test_all_rows_missing_date_or_identity_metadata_retained_in_quarantine():
    rows = [dict(body()["results"][0], ticker=None), dict(body()["results"][0], date=None),
            dict(body()["results"][0], benzinga_id=None)]
    report = m._project(encoded(body(rows=rows)), m.WINDOWS[0], credential=KEY)
    assert report["source_rows"] == report["quarantined_rows"] == 3 and report["metadata_candidate_rows"] == 0
    assert [r["source_ordinal"] for r in report["rows"]] == [0, 1, 2]


def test_source_limit_reached_retains_page_but_refuses_underfill(monkeypatch):
    monkeypatch.setattr(m, "MAX_ROWS", 1)
    report = m._project(encoded(body()), m.WINDOWS[0], credential=KEY)
    assert report["row_limit_reached"] is True and report["source_page_underfill_refused"] is True


def test_missing_or_extra_original_pin_refuses_before_any_source_or_credential(monkeypatch):
    def forbidden(*args):
        pytest.fail("invalid external pin reached real identity")
    monkeypatch.setattr(m, "_identity", forbidden)
    with pytest.raises(m.EarningsGapError, match="previous_external_pin_refused"):
        m.run_capture(RUN, HEAD, expected_previous_complete_sha256="d" * 64)


def test_actual_cli_inactive_path_refuses_before_any_git_prior_source_or_key(monkeypatch, capsys):
    monkeypatch.setattr(m, "__file__", str(m.LANE_ROOT / "artifacts/insider_buying/development_drafts/inactive-benzinga.py"))
    def forbidden(*args):
        pytest.fail("inactive private source reached an external constructor")
    monkeypatch.setattr(m, "_git", forbidden)
    monkeypatch.setattr(m, "_PreviousAccess", forbidden)
    monkeypatch.setattr(m, "_keychain_credential", forbidden)
    assert m.main(["--run-id", RUN, "--expected-head", HEAD, "--expected-previous-complete-sha256",
        m.PREVIOUS_HASHES["complete.json"]]) == 2
    assert json.loads(capsys.readouterr().out) == {"disposition": "bounded_earnings_capture_refused_claims_preserved",
        "capture_failure": {"phase": "preflight", "exception_category": "earnings_gap_error", "recognized_os_errno": None}}


@pytest.mark.parametrize("phase", ["guard_current_identity", "guard_previous_access", "guard_current_journal"])
def test_capture_cli_exposes_only_fixed_phase_class_errno_not_exception_values(monkeypatch, capsys, phase):
    secret = "INVENTED SECRET /not/an/actual/path"
    error = PermissionError(13, secret, secret)
    error._earnings_capture_failure_phase = phase
    def refused(*args, **kwargs):raise error
    monkeypatch.setattr(m, "run_capture", refused)
    assert m.main(["--run-id", RUN, "--expected-head", HEAD,
        "--expected-previous-complete-sha256", m.PREVIOUS_HASHES["complete.json"]]) == 2
    raw = capsys.readouterr().out
    assert secret not in raw
    assert json.loads(raw) == {"disposition": "bounded_earnings_capture_refused_claims_preserved",
        "capture_failure": {"phase": phase, "exception_category": "os_error",
                            "recognized_os_errno": 13}}


def test_real_fixture_guard_conversion_keeps_sanitized_phase_without_changing_refusal_type(tmp_path):
    calls = []
    def guarded(head):
        calls.append(True)
        if len(calls) > 1:raise PermissionError(13, "INVENTED PRIVATE SECRET")
        return identity(head)
    with pytest.raises(m.EarningsGapError) as caught:
        invoke(tmp_path, ident=guarded)
    assert m._capture_diagnostic(caught.value) == {"phase": "guard_current_identity",
        "exception_category": "os_error", "recognized_os_errno": 13}
    assert list(claims(tmp_path).iterdir()) == []
    assert set(p.name for p in folder(tmp_path).iterdir()) == {"manifest.json"}


def test_verifier_launcher_accepts_exact_one_print_framing_lf(monkeypatch, tmp_path):
    result = {"fixture_only": True, "sanitized_fixture": True}
    monkeypatch.setattr(m.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stderr=b"", stdout=m._canonical(result)+b"\n"))
    payload = {"run_id": RUN, "current_identity": {"head": HEAD}, "expected_complete_sha256": "a" * 64}
    assert m._launch_verify_worker(payload, root=tmp_path) == result


@pytest.mark.parametrize("suffix", [b"\n\n", b" \n", b"\r\n"])
def test_verifier_launcher_refuses_noncanonical_or_repeated_framing(monkeypatch, tmp_path, suffix):
    monkeypatch.setattr(m.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stderr=b"", stdout=b'{}'+suffix))
    payload = {"run_id": RUN, "current_identity": {"head": HEAD}, "expected_complete_sha256": "a" * 64}
    with pytest.raises(m.EarningsGapError, match="control_json_refused"):
        m._launch_verify_worker(payload, root=tmp_path)


@pytest.mark.parametrize("alias", ["literal", "case", "ancestor-case", "descendant", "symlink"])
def test_fixture_actual_root_and_alias_fence_before_callbacks(tmp_path, monkeypatch, alias):
    called = []
    root = m.LANE_ROOT
    if alias == "case":
        root = root.with_name(root.name.upper())
        if not root.exists() or not root.samefile(m.LANE_ROOT):
            pytest.skip("case-insensitive filesystem alias not present")
    elif alias == "ancestor-case":
        root = Path(str(root).replace("Documents", "DOCUMENTS"))
        if not root.exists() or not root.samefile(m.LANE_ROOT):
            pytest.skip("case-insensitive ancestor alias not present")
    elif alias == "descendant":
        root = m.LANE_ROOT / "artifacts"
    elif alias == "symlink":
        root = tmp_path / "invented-alias"
        root.symlink_to(m.LANE_ROOT, target_is_directory=True)
    def forbidden(*args):
        called.append(True)
        pytest.fail("real root alias reached callback or output constructor")
    monkeypatch.setattr(m, "_parent", forbidden)
    with pytest.raises(m.EarningsGapError, match="fixture_root_refused"):
        m.run_fixture(RUN, HEAD, root=root, identity=forbidden, credential_loader=forbidden, transport=forbidden)
    assert not called


def test_fixture_real_transport_reference_rejected_before_io(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("real transport constructor reached")
    monkeypatch.setattr("http.client.HTTPSConnection", forbidden)
    monkeypatch.setattr("urllib.request.build_opener", forbidden)
    with pytest.raises(m.EarningsGapError, match="fixture_real_callback_refused"):
        m.run_fixture(RUN, HEAD, root=tmp_path, identity=identity, credential_loader=lambda: KEY,
                      transport=m._default_transport)


def test_wrong_head_format_refuses_before_callback(tmp_path):
    def forbidden(*args):
        pytest.fail("bad format reached callback")
    with pytest.raises(m.EarningsGapError, match="run_identity_refused"):
        m.run_fixture(RUN, "bad", root=tmp_path, identity=forbidden, credential_loader=forbidden, transport=forbidden)


def test_source_drift_after_started_consumes_start_and_never_reads_secret(tmp_path):
    number = [0]
    def drifting(head):
        number[0] += 1
        return identity(head) if number[0] < 4 else {"changed": True}
    with pytest.raises(m.EarningsGapError, match="current_source_changed"):
        invoke(tmp_path, ident=drifting)
    assert (folder(tmp_path) / "00-started.json").is_file()
    assert len(list(claims(tmp_path).iterdir())) == 1
    assert not (folder(tmp_path) / "00-complete.json").exists()


def test_post_response_custody_tamper_refuses_body_and_claim_survives(tmp_path):
    def transport(item):
        (folder(tmp_path) / "00-started.json").write_bytes(b"{}");
        return m.ProviderMetadataResponse(200, encoded(body()))
    with pytest.raises(m.EarningsGapError, match="journal_hash_changed"):
        invoke(tmp_path, transport=transport)
    assert not (folder(tmp_path) / "00-raw.json").exists()
    assert len(list(claims(tmp_path).iterdir())) == 1


def test_post_completion_cooldown_is_load_bearing(tmp_path):
    with pytest.raises(m.EarningsGapError, match="post_completion_cooldown_refused"):
        invoke(tmp_path, sleeper=lambda seconds: None, monotonic=lambda: 1.0)
    assert (folder(tmp_path) / "00-complete.json").is_file()
    assert not (folder(tmp_path) / "01-started.json").exists()


@pytest.mark.parametrize("offset", [-1, 0])
def test_disk_exact_bound_or_one_byte_short_before_secret(tmp_path, monkeypatch, offset):
    required = m.MIN_FREE_BYTES + len(m.WINDOWS) * (m.MAX_BODY_BYTES + m.MAX_METADATA_BYTES + 2*m.MAX_CONTROL_BYTES) + 2*m.MAX_CONTROL_BYTES
    monkeypatch.setattr(m.os, "fstatvfs", lambda fd: SimpleNamespace(f_bavail=required+offset, f_frsize=1))
    if offset < 0:
        with pytest.raises(m.EarningsGapError, match="disk_reserve_refused"):
            invoke(tmp_path)
        assert not list(claims(tmp_path).iterdir())
    else:
        assert invoke(tmp_path)[0]["candidate_metadata_windows"] == 3


@pytest.mark.parametrize("available,block", [(True, 1), (-1, 1), (1, True), (1, 0)])
def test_disk_observation_types_refused(tmp_path, monkeypatch, available, block):
    monkeypatch.setattr(m.os, "fstatvfs", lambda fd: SimpleNamespace(f_bavail=available, f_frsize=block))
    with pytest.raises(m.EarningsGapError, match="disk_observation_refused"):
        invoke(tmp_path)


class Stream(io.BytesIO):
    def __init__(self, raw, headers):
        super().__init__(raw)
        self.headers = Message()
        for key, value in headers.items():
            self.headers[key] = value


@pytest.mark.parametrize("headers,raw,disposition", [({"Content-Encoding": "gzip"}, b"x", "unsupported-content-encoding"),
    ({"Content-Length": "1"}, b"xx", "truncated-response"), ({"Content-Length": "-1"}, b"x", "invalid-content-length"),
    ({"Content-Length": str(m.MAX_BODY_BYTES+1)}, b"", "oversized-response")])
def test_bounded_reader_checks_actual_framing(headers, raw, disposition):
    result = m._read_bounded(Stream(raw, headers), 200)
    assert result.disposition == disposition and result.body_complete is False


def test_bounded_reader_complete_and_oversize_no_unbounded_read(monkeypatch):
    assert m._read_bounded(Stream(b"{}", {"Content-Length": "2"}), 200).body == b"{}"
    monkeypatch.setattr(m, "MAX_BODY_BYTES", 4)
    result = m._read_bounded(Stream(b"123456", {}), 200)
    assert result.disposition == "oversized-response" and result.body == b""


@pytest.mark.parametrize("change", [{"method": "POST"}, {"timeout_seconds": True},
    {"url": m.previous.REQUEST_URL}, {"url": m.URLS[0] + "&apiKey=not-allowed"},
    {"headers": (("Authorization", "Bearer invented"),)}])
def test_fixed_request_shape_refuses_mutation(change):
    item = m.EarningsGapRequest(m.URLS[0], (("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                           ("Authorization", "Bearer " + KEY)))
    with pytest.raises(m.EarningsGapError, match="fixed_request_refused"):
        m._validate_request(replace(item, **change))


def test_external_raw_pin_does_not_accept_unbound_or_changed_bytes():
    raw = encoded(body())
    with pytest.raises(m.EarningsGapError, match="external_body_pin_refused"):
        m.replay_supplied_metadata(raw, "d" * 64, m.WINDOWS[0])


def test_claim_schema_boolean_attempts_and_hash_url_forgery_refused(tmp_path):
    registry = tmp_path / "invented-claims"
    registry.mkdir(mode=0o700)
    name = m._sha(m.URLS[0].encode()) + ".json"
    record = {"schema": m.SCHEMA, "run_id": RUN, "window": list(m.WINDOWS[0]), "url": m.URLS[0],
        "claimed_at_utc": NOW, "maximum_attempts": True}
    (registry / name).write_bytes(encoded(record)); (registry / name).chmod(0o600)
    fd = os.open(registry, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(m.EarningsGapError, match="claim_registry_refused"):
            m._old_claims(fd)
    finally:
        os.close(fd)


def test_main_arbitrary_secret_exception_is_generic_not_echoed(monkeypatch, capsys):
    def refusal(*args, **kwargs):
        raise RuntimeError(KEY, {"secret": KEY})
    monkeypatch.setattr(m, "run_capture", refusal)
    assert m.main(["--run-id", RUN, "--expected-head", HEAD,
        "--expected-previous-complete-sha256", m.PREVIOUS_HASHES["complete.json"]]) == 2
    out = capsys.readouterr().out
    assert KEY not in out and json.loads(out) == {"disposition": "bounded_earnings_capture_refused_claims_preserved",
        "capture_failure": {"phase": "preflight", "exception_category": "unclassified_error", "recognized_os_errno": None}}


def supplied_controls(tmp_path):
    result = invoke(tmp_path)[0]
    leaves = {p.name: p.read_bytes() for p in folder(tmp_path).iterdir()}
    claim_bytes = {p.name: p.read_bytes() for p in claims(tmp_path).iterdir()}
    return result, leaves, claim_bytes


def test_independent_terminal_replays_every_body_metadata_start_and_claim(tmp_path):
    result, leaves, claim_bytes = supplied_controls(tmp_path)
    replay = m.verify_supplied_terminal(leaves["complete.json"], result["complete_sha256"], leaves, claim_bytes,
        fixture_only=True)
    assert replay["claimed_started_windows"] == 3 and replay["source_rows"] == 3
    assert replay["retained_raw_bytes"] == result["retained_raw_bytes"]


@pytest.mark.parametrize("field,value", [("planned_windows", True), ("terminal_windows", 2),
    ("claimed_started_windows", True), ("candidate_metadata_windows", 2), ("refused_windows", True),
    ("backtesting_ready", True), ("January2006_coverage_supplied", True),
    ("originally_unattempted_windows", [["2006-01-01", "2006-01-31"]])])
def test_rehashed_terminal_counts_or_authority_forgery_refused(tmp_path, field, value):
    _, leaves, claim_bytes = supplied_controls(tmp_path)
    complete = json.loads(leaves["complete.json"])
    complete[field] = value
    leaves["complete.json"] = encoded(complete)
    with pytest.raises(m.EarningsGapError):
        m.verify_supplied_terminal(leaves["complete.json"], m._sha(leaves["complete.json"]), leaves, claim_bytes,
            fixture_only=True)


@pytest.mark.parametrize("field,value", [("http_status", True), ("body_bytes", True),
    ("metadata_source_rows", 2), ("quarantined_rows", True), ("retained_raw", False),
    ("disposition", "unknown-success"), ("disposition", "partial_page_refused_no_pagination")])
def test_rehashed_per_window_receipt_forgery_cannot_invent_replay(tmp_path, field, value):
    _, leaves, claim_bytes = supplied_controls(tmp_path)
    complete = json.loads(leaves["complete.json"])
    terminal = complete["results"][0]
    terminal["receipt"][field] = value
    leaves["00-complete.json"] = encoded(terminal)
    complete["current_journal_sha256"]["00-complete.json"] = m._sha(leaves["00-complete.json"])
    leaves["complete.json"] = encoded(complete)
    with pytest.raises(m.EarningsGapError):
        m.verify_supplied_terminal(leaves["complete.json"], m._sha(leaves["complete.json"]), leaves, claim_bytes,
            fixture_only=True)


def test_rehashed_underfilled_page_cannot_claim_accepted_window(tmp_path):
    raw = encoded(body(next_url="https://api.massive.com/benzinga/v1/earnings?cursor=fixture"))
    result = invoke(tmp_path, responses=[m.ProviderMetadataResponse(200, raw)])[0]
    leaves = {p.name: p.read_bytes() for p in folder(tmp_path).iterdir()}
    claim_bytes = {p.name: p.read_bytes() for p in claims(tmp_path).iterdir()}
    assert m.verify_supplied_terminal(leaves["complete.json"], result["complete_sha256"], leaves, claim_bytes,
        fixture_only=True)["refused_windows"] == 1
    complete = json.loads(leaves["complete.json"])
    terminal = complete["results"][0]
    terminal["receipt"]["disposition"] = "candidate_metadata_observed"
    complete["candidate_metadata_windows"], complete["refused_windows"] = 1, 0
    leaves["00-complete.json"] = encoded(terminal)
    complete["current_journal_sha256"]["00-complete.json"] = m._sha(leaves["00-complete.json"])
    leaves["complete.json"] = encoded(complete)
    with pytest.raises(m.EarningsGapError, match="terminal_underfill_refused"):
        m.verify_supplied_terminal(leaves["complete.json"], m._sha(leaves["complete.json"]), leaves, claim_bytes,
            fixture_only=True)


@pytest.mark.parametrize("field,value", [("available_bytes", True), ("required_bytes", 1),
    ("remaining_windows", True)])
def test_resource_receipt_typed_arithmetic_guard(field, value):
    required = m.MIN_FREE_BYTES + 3 * (m.MAX_BODY_BYTES + m.MAX_METADATA_BYTES + 2*m.MAX_CONTROL_BYTES) + 2*m.MAX_CONTROL_BYTES
    record = {"available_bytes": required, "required_bytes": required, "remaining_windows": 3}
    record[field] = value
    with pytest.raises(m.EarningsGapError, match="terminal_resource_refused"):
        m._verify_resource(record, 3)


def test_empty_identity_strings_remain_accounted_quarantine_not_candidate():
    rows = [dict(body()["results"][0], ticker=""), dict(body()["results"][0], benzinga_id=" ")]
    report = m._project(encoded(body(rows=rows)), m.WINDOWS[0], credential=KEY)
    assert report["source_rows"] == report["quarantined_rows"] == 2
    assert report["metadata_candidate_rows"] == 0


def test_nested_financial_count_never_receives_numeric_conversion_even_when_refused(monkeypatch):
    converted = []
    real_int = int
    def observe(value):
        if type(value) is str:
            converted.append(value)
        return real_int(value)
    monkeypatch.setattr(m, "int", observe, raising=False)
    source = body()
    source.pop("count")
    source["results"][0]["actual_eps"] = {"count": 42}
    with pytest.raises(m.EarningsGapError):
        m._project(encoded(source), m.WINDOWS[0], credential=KEY)
    assert converted == []


@pytest.mark.parametrize("extra", [{"Content-Length": "2"}, {"Transfer-Encoding": "chunked"},
    {"Content-Encoding": "gzip"}])
def test_duplicate_or_mixed_framing_headers_refused(extra):
    stream = Stream(b"{}", {"Content-Length": "2", "Content-Encoding": "identity"})
    for key, value in extra.items():
        stream.headers[key] = value
    observed = m._read_bounded(stream, 200)
    assert observed.body_complete is False and observed.disposition in {
        "invalid-content-length", "unsupported-content-encoding", "partial-read"}


def test_impossible_stream_overdelivery_refused_not_truncated(monkeypatch):
    monkeypatch.setattr(m, "MAX_BODY_BYTES", 4)
    class Overdelivery:
        headers = Message()
        def read(self, size):
            assert size == 5
            return b"{}" + b" " * 4
    observed = m._read_bounded(Overdelivery(), 200)
    assert observed.body_complete is False and observed.disposition == "partial-read"


def test_missing_multivalue_header_interface_refused_without_read():
    class InvalidHeaders:
        headers = {"Content-Length": "2"}
        def read(self, size):
            pytest.fail("unvalidated header shape reached body read")
    observed = m._read_bounded(InvalidHeaders(), 200)
    assert observed.body_complete is False and observed.disposition == "partial-read"


@pytest.mark.parametrize("changes", [{"unknown_source_metadata": "invented"}, {"date_status": "other-status"},
    {"time": "unsupported-coarse-label"}, {"actual_eps": "text-not-a-number"}])
def test_valid_private_raw_retained_when_metadata_schema_quarantined_without_requery(tmp_path, changes):
    source = body()
    source["results"][0].update(changes)
    raw = encoded(source)
    result, calls, _ = invoke(tmp_path, responses=[m.ProviderMetadataResponse(200, raw)])
    assert len(calls) == 1 and result["refused_windows"] == 1
    assert (folder(tmp_path) / "00-raw.json").read_bytes() == raw
    assert not (folder(tmp_path) / "00-metadata.json").exists()
    assert result["source_rows"] is None and result["unknown_metadata_windows"] == 1
    terminal = json.loads((folder(tmp_path) / "00-complete.json").read_bytes())
    assert terminal["receipt"]["disposition"] == "source_metadata_quarantined"
    assert terminal["receipt"]["metadata_source_rows"] is None and terminal["receipt"]["retained_raw"] is True
    leaves = {p.name: p.read_bytes() for p in folder(tmp_path).iterdir()}
    claim_bytes = {p.name: p.read_bytes() for p in claims(tmp_path).iterdir()}
    replay = m.verify_supplied_terminal(leaves["complete.json"], result["complete_sha256"], leaves, claim_bytes,
        fixture_only=True)
    assert replay["source_rows"] is None and replay["unknown_metadata_windows"] == 1


def test_full_known_run_inventory_change_after_start_refuses_before_secret(tmp_path, monkeypatch):
    calls = [0]
    original = m._journal
    def inventory_changed(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 3:
            rogue = tmp_path.joinpath(*m.ARTIFACT_PARTS, "runs", "unexpected-concurrent-root")
            rogue.mkdir(mode=0o700)
        return original(*args, **kwargs)
    monkeypatch.setattr(m, "_journal", inventory_changed)
    with pytest.raises(m.EarningsGapError, match="run_inventory_changed"):
        invoke(tmp_path)
    assert (folder(tmp_path) / "00-started.json").is_file()
    assert not (folder(tmp_path) / "00-raw.json").exists()


def test_lock_baseline_full_version_cannot_be_rebased_after_start(tmp_path, monkeypatch):
    number = [0]
    original = m._journal
    def change_lock(*args, **kwargs):
        number[0] += 1
        if number[0] == 3:
            path = tmp_path.joinpath(*m.ARTIFACT_PARTS, "capture.lock")
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns+1_000_000_000))
        return original(*args, **kwargs)
    monkeypatch.setattr(m, "_journal", change_lock)
    with pytest.raises(m.EarningsGapError, match="journal_lock_detached"):
        invoke(tmp_path)
    assert (folder(tmp_path) / "00-started.json").is_file()
    assert not (folder(tmp_path) / "00-raw.json").exists()


def test_private_raw_source_schema_quarantine_forgery_cannot_hide_valid_metadata(tmp_path):
    _, leaves, claim_bytes = supplied_controls(tmp_path)
    complete = json.loads(leaves["complete.json"])
    terminal = complete["results"][0]
    terminal["receipt"].update(disposition="source_metadata_quarantined", qualification_code="row_schema_refused",
        metadata_source_rows=None, metadata_candidate_rows=None, quarantined_rows=None)
    terminal["metadata_sha256"] = None
    del leaves["00-metadata.json"]
    leaves["00-complete.json"] = encoded(terminal)
    complete["current_journal_sha256"] = {name: m._sha(raw) for name,raw in leaves.items() if name != "complete.json"}
    leaves["complete.json"] = encoded(complete)
    with pytest.raises(m.EarningsGapError, match="quarantined_raw_refusal_refused"):
        m.verify_supplied_terminal(leaves["complete.json"], m._sha(leaves["complete.json"]), leaves, claim_bytes,
            fixture_only=True)


def test_supplied_terminal_claim_set_must_match_every_requested_month(tmp_path):
    result, leaves, claim_bytes = supplied_controls(tmp_path)
    claim_bytes.pop(next(iter(claim_bytes)))
    with pytest.raises(m.EarningsGapError):
        m.verify_supplied_terminal(leaves["complete.json"], result["complete_sha256"], leaves, claim_bytes,
            fixture_only=True)


def test_prior_access_failure_closes_both_held_descriptors(monkeypatch):
    fake = iter((123, 456))
    closed = []
    monkeypatch.setattr(m.previous, "_parent", lambda root, create: next(fake))
    monkeypatch.setattr(m, "_directory", lambda parent, name, create: next(fake))
    monkeypatch.setattr(m.os, "close", closed.append)
    def refuse(self):
        raise m.EarningsGapError("previous_access_pin_refused")
    monkeypatch.setattr(m._PreviousAccess, "check", refuse)
    with pytest.raises(m.EarningsGapError, match="previous_access_pin_refused"):
        m._PreviousAccess(Path("/invented-never-opened"))
    assert closed == [456, 123]


class _InventedSecurity:
    """Invented `security` process for the shared reader; never the real Keychain."""
    def __init__(self, output, code=0):
        import subprocess as _subprocess
        self._child = _subprocess.Popen([sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                                        stdin=_subprocess.PIPE, stdout=_subprocess.PIPE, start_new_session=True)
        self._child.stdin.write(output);self._child.stdin.close()
        self.code = code
        self.calls = 0

    def __call__(self, args, **kwargs):
        assert args == ("/usr/bin/security", "find-generic-password", "-s", "trading-agent-massive", "-a", "massive", "-w")
        self.calls += 1
        return self._child


# Section 194 (Claude review): the loader now delegates to the shared bounded reader, so
# these five invalid outputs are refused by that reader's checks, end to end.
@pytest.mark.parametrize("value", ["", "test-api-key\n", "has newline\ninside\n", " \n", "\x00bad\n"])
def test_keychain_loader_fixed_item_invalid_output_refused_without_account_read(monkeypatch, value):
    from research import insider_buying_keychain_credentials as keychain
    # Preserve Popen's class identity: the shared reader uses isinstance for
    # both bounded reads and cleanup. Only the factory is injected; replacing
    # Popen with a function would refuse before the grammar checks under test.
    fake = _InventedSecurity(value.encode())
    output_sizes, refused = [], []
    original_bounded = keychain._bounded_stdout
    def bounded(process, deadline):
        raw = original_bounded(process, deadline)
        output_sizes.append(len(raw))
        return raw
    def reader(provider):
        try:
            return keychain.read_keychain_credential(provider, _process_factory=fake)
        except keychain.KeychainCredentialError as exc:
            refused.append(exc.args[0])
            raise
    monkeypatch.setattr(keychain, "_bounded_stdout", bounded)
    monkeypatch.setattr(m, "read_keychain_credential", reader)
    try:
        with pytest.raises(m.EarningsGapError, match="^credential_unavailable$"):
            m._keychain_credential()
        assert fake.calls == 1 and output_sizes == [len(value.encode())]
        assert refused == ["keychain_credential_refused"]
        assert fake._child.poll() == 0 and fake._child.stdout.closed
    finally:
        fake._child.wait(timeout=1)
        fake._child.stdout.close()


def test_invented_valid_keychain_output_reaches_bounded_grammar_not_class_refusal(monkeypatch):
    from research import insider_buying_keychain_credentials as keychain
    fake = _InventedSecurity((KEY + "\n").encode())
    output_sizes = []
    original_bounded = keychain._bounded_stdout
    def bounded(process, deadline):
        raw = original_bounded(process, deadline)
        output_sizes.append(len(raw))
        return raw
    monkeypatch.setattr(keychain, "_bounded_stdout", bounded)
    try:
        observed = keychain.read_keychain_credential("massive", _process_factory=fake)
        assert observed.provider == "massive" and observed.value == KEY and observed.fixture_only is True
        assert fake.calls == 1 and output_sizes == [len(KEY.encode()) + 1]
        assert fake._child.poll() == 0 and fake._child.stdout.closed
    finally:
        fake._child.wait(timeout=1)
        fake._child.stdout.close()


def test_keychain_loader_uses_the_shared_reader_for_the_fixed_massive_item(monkeypatch):
    from research import insider_buying_keychain_credentials as keychain
    seen = []
    def reader(provider):
        seen.append(provider)
        return keychain.KeychainCredential("massive", KEY, False)
    monkeypatch.setattr(m, "read_keychain_credential", reader)
    assert m._keychain_credential() == KEY and seen == ["massive"]
    for refused in (keychain.KeychainCredential("massive", KEY, True), keychain.KeychainCredential("fmp", KEY, False)):
        monkeypatch.setattr(m, "read_keychain_credential", lambda provider, refused=refused: refused)
        with pytest.raises(m.EarningsGapError, match="^credential_unavailable$"):
            m._keychain_credential()
    def missing(provider):
        raise keychain.KeychainCredentialError("keychain_item_missing")
    monkeypatch.setattr(m, "read_keychain_credential", missing)
    with pytest.raises(m.EarningsGapError, match="^credential_unavailable$") as caught:
        m._keychain_credential()
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_metadata_rows_are_lossless_dates_not_a_cross_source_identity_join():
    rows = [dict(body()["results"][0], benzinga_id="same-id", ticker="REUSED"),
            dict(body()["results"][0], benzinga_id="same-id", ticker="REUSED", company_name="Different Co")]
    report = m._project(encoded(body(rows=rows)), m.WINDOWS[0], credential=KEY)
    assert report["source_rows"] == 2 and len(report["rows"]) == 2
    assert [row["source_ordinal"] for row in report["rows"]] == [0, 1]
    assert all(row["identity_pit_rights_ready"] is False for row in report["rows"])


def fixture_verifier_input(root, monkeypatch):
    capture = invoke(root)[0]
    source = root / "invented.py"
    source.write_bytes(b"marker = 'invented verifier source'\n")
    newer_head = "d" * 40
    current_inventory = {"invented.py": m._sha(source.read_bytes())}
    current = {"root": str(root), "branch": m.LANE_BRANCH, "head": newer_head, "clean": True,
        "source_sha256": current_inventory, "source_inventory_sha256": m._sha(encoded(current_inventory))}
    def current_identity(head):
        assert head == newer_head
        return current
    def original(producer):
        assert producer["head"] == HEAD and producer["head"] != newer_head
        return {"head": producer["head"], "source_sha256": producer["source_sha256"],
            "source_inventory_sha256": producer["source_inventory_sha256"],
            "original_committed_bytes_verified": False, "whole_historical_environment_executed": False}
    monkeypatch.setattr(m, "_verify_isolation", lambda: {"network_denied": True, "fork_denied": True, "all_write_denied": True})
    def fixture_worker(payload, *, root):
        # Explicit invented worker callback. This does not observe OS isolation
        # or authenticate actual producer Git; fixture_only remains True.
        return m._verify_worker(payload, root=root, fixture_only=True)
    return capture, newer_head, current_identity, original, fixture_worker


def test_held_fixture_verifier_binds_distinct_original_and_current_head(tmp_path, monkeypatch):
    capture, current_head, ident, original, worker = fixture_verifier_input(tmp_path, monkeypatch)
    result = m.verify_fixture_capture(RUN, current_head, capture["complete_sha256"], root=tmp_path,
        identity=ident, producer_inventory=original, launch_worker=worker)
    assert result["fixture_only"] is True and result["private_source_custody_rechecked"] is True
    assert result["current_verifier_identity"]["head"] == current_head
    assert result["original_producer_inventory"]["head"] == HEAD
    assert result["original_producer_inventory"]["original_committed_bytes_verified"] is False
    assert result["terminal_replay"]["source_rows"] == 3 and result["historical_environment_executed"] is False
    assert result["leaf_count"] == 18


@pytest.mark.parametrize("kind", ["extra-run", "raw-rewrite-same-bytes", "claim-rewrite-same-bytes", "lock-version"])
def test_verifier_parent_detects_full_snapshot_change_after_child(tmp_path, monkeypatch, kind):
    capture, current_head, ident, original, worker = fixture_verifier_input(tmp_path, monkeypatch)
    def changed(payload, *, root):
        result = worker(payload, root=root)
        if kind == "extra-run":
            folder(root).parent.joinpath("ib-benzinga-gap-concurrent-root").mkdir(mode=0o700)
        elif kind == "raw-rewrite-same-bytes":
            raw = folder(root) / "00-raw.json"
            raw.write_bytes(raw.read_bytes())
        elif kind == "claim-rewrite-same-bytes":
            leaf = next(iter(claims(root).iterdir()))
            leaf.write_bytes(leaf.read_bytes())
        else:
            lock = root.joinpath(*m.ARTIFACT_PARTS, "capture.lock")
            stamp = lock.stat()
            os.utime(lock, ns=(stamp.st_atime_ns, stamp.st_mtime_ns+1_000_000_000))
        return result
    with pytest.raises(m.EarningsGapError) as refused:
        m.verify_fixture_capture(RUN, current_head, capture["complete_sha256"], root=tmp_path,
            identity=ident, producer_inventory=original, launch_worker=changed)
    assert refused.value.failure_fields["phase"] == "after_worker_custody"


def test_verifier_holds_older_run_leaves_not_only_current_leaf(tmp_path, monkeypatch):
    capture, current_head, ident, original, worker = fixture_verifier_input(tmp_path, monkeypatch)
    old = folder(tmp_path).parent / "ib-benzinga-gap-old-registration-only"
    old.mkdir(mode=0o700)
    old_leaf = old / "manifest.json"
    old_leaf.write_bytes(b'{}'); old_leaf.chmod(0o600)
    def changed(payload, *, root):
        result = worker(payload, root=root)
        old_leaf.write_bytes(b'{}')
        return result
    with pytest.raises(m.EarningsGapError) as refused:
        m.verify_fixture_capture(RUN, current_head, capture["complete_sha256"], root=tmp_path,
            identity=ident, producer_inventory=original, launch_worker=changed)
    assert refused.value.failure_fields["phase"] == "after_worker_custody"


@pytest.mark.parametrize("field,value", [("leaf_count", True), ("observation_sha256", "e"*64),
    ("current_verifier_identity", {}), ("historical_environment_executed", True), ("backtesting_ready", True),
    ("isolation", {"network_denied": True, "fork_denied": True, "all_write_denied": False})])
def test_parent_refuses_rehashed_or_wrong_worker_receipt(tmp_path, monkeypatch, field, value):
    capture, current_head, ident, original, worker = fixture_verifier_input(tmp_path, monkeypatch)
    def forge(payload, *, root):
        result = worker(payload, root=root)
        result[field] = value
        return result
    with pytest.raises(m.EarningsGapError) as refused:
        m.verify_fixture_capture(RUN, current_head, capture["complete_sha256"], root=tmp_path,
            identity=ident, producer_inventory=original, launch_worker=forge)
    assert refused.value.failure_fields["fixed_code"] == "verification_worker_reply_refused"


def test_post_worker_current_source_inventory_drift_refuses(tmp_path, monkeypatch):
    capture, current_head, ident, original, worker = fixture_verifier_input(tmp_path, monkeypatch)
    calls = [0]
    def drift(head):
        calls[0] += 1
        return ident(head) if calls[0] <= 2 else {"changed": True}
    with pytest.raises(m.EarningsGapError) as refused:
        m.verify_fixture_capture(RUN, current_head, capture["complete_sha256"], root=tmp_path,
            identity=drift, producer_inventory=original, launch_worker=worker)
    assert refused.value.failure_fields["phase"] == "after_worker_identity"


@pytest.mark.parametrize("root_kind", ["literal", "case", "symlink"])
def test_fixture_verification_cannot_touch_actual_roots_before_callbacks(tmp_path, monkeypatch, root_kind):
    root = m.LANE_ROOT
    if root_kind == "case":
        root = root.with_name(root.name.upper())
        if not root.exists() or not root.samefile(m.LANE_ROOT):
            pytest.skip("case alias not available")
    elif root_kind == "symlink":
        root = tmp_path / "invented-alias"
        root.symlink_to(m.LANE_ROOT, target_is_directory=True)
    def forbidden(*args, **kwargs):
        pytest.fail("real custody reached callback/constructor")
    monkeypatch.setattr(m, "_VerificationTree", forbidden)
    with pytest.raises(m.EarningsGapError, match="fixture_root_refused"):
        m.verify_fixture_capture(RUN, HEAD, "e"*64, root=root, identity=forbidden,
            producer_inventory=forbidden, launch_worker=forbidden)


def test_inactive_actual_verifier_refuses_before_tree_git_or_worker(monkeypatch):
    monkeypatch.setattr(m, "__file__", str(m.LANE_ROOT / "artifacts/insider_buying/development_drafts/inactive-benzinga.py"))
    def forbidden(*args, **kwargs):
        pytest.fail("inactive source reached production I/O")
    monkeypatch.setattr(m, "_git", forbidden)
    monkeypatch.setattr(m, "_VerificationTree", forbidden)
    monkeypatch.setattr(m, "_launch_verify_worker", forbidden)
    with pytest.raises(m.EarningsGapError) as refused:
        m.verify_actual_capture(RUN, HEAD, "e" * 64)
    assert refused.value.failure_fields["fixed_code"] == "inactive_or_other_worktree_refused"


def test_current_source_closure_invented_internal_imports_and_packages(tmp_path, monkeypatch):
    research = tmp_path / "research"; research.mkdir()
    local = tmp_path / "invented_package"; local.mkdir()
    for path,raw in [(research/"__init__.py", b""), (research/"seed.py", b"from research import helper\n"),
        (research/"helper.py", b"from invented_package import leaf\n"), (local/"__init__.py", b""),
        (local/"leaf.py", b"marker = 'invented'\n")]:
        path.write_bytes(raw)
    monkeypatch.setattr(m, "SOURCE_FILES", ("research/seed.py",))
    assert m._current_source_paths(tmp_path) == ("invented_package/__init__.py", "invented_package/leaf.py",
        "research/__init__.py", "research/helper.py", "research/seed.py")


def producer_fixture(monkeypatch, *, omitted_dependency=False, bad_source=False, empty_package=False):
    originals = {name:b"marker = 'invented original'\n" for name in m.SOURCE_FILES}
    if empty_package:
        originals["research/__init__.py"] = b""
    if omitted_dependency:
        originals[m.SELF_PATH] = b"from research import missing_dependency\n"
    inventory = {name:m._sha(raw) for name,raw in originals.items()}
    declared = dict(inventory)
    if bad_source:
        declared[m.SELF_PATH] = "e"*64
    identity_record = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
        "source_sha256": declared, "source_inventory_sha256": m._sha(encoded(declared))}
    calls = []
    def git(root, *args):
        assert root == m.LANE_ROOT
        calls.append(args)
        if args[0] == "show":
            prefix, name = args[1].split(":", 1)
            assert prefix == HEAD
            return originals[name]
        assert args == ("ls-tree", "-r", "--name-only", HEAD)
        names = set(originals)
        if omitted_dependency:
            names.add("research/missing_dependency.py")
        return ("\n".join(sorted(names))+"\n").encode()
    monkeypatch.setattr(m, "_git", git)
    return identity_record, calls


def test_original_git_inventory_uses_original_commit_not_current_head(monkeypatch):
    original, calls = producer_fixture(monkeypatch)
    observed = m._producer_git_inventory(original)
    assert observed["head"] == HEAD and observed["original_committed_bytes_verified"] is True
    assert observed["whole_historical_environment_executed"] is False
    assert len(calls) == len(m.SOURCE_FILES)+1 and all(HEAD in " ".join(args) for args in calls)


def test_original_zero_byte_package_init_is_valid_hash_bound_source(monkeypatch):
    original,_=producer_fixture(monkeypatch,empty_package=True)
    observed=m._producer_git_inventory(original)
    assert observed["original_committed_bytes_verified"] is True
    assert observed["source_sha256"]["research/__init__.py"]==m._sha(b"")


@pytest.mark.parametrize("omitted,bad,code", [(True,False,"producer_static_closure_refused"),
    (False,True,"producer_source_inventory_refused")])
def test_original_git_missing_import_or_changed_module_bytes_refuse(monkeypatch, omitted, bad, code):
    original, _ = producer_fixture(monkeypatch, omitted_dependency=omitted, bad_source=bad)
    with pytest.raises(m.EarningsGapError, match=code):
        m._producer_git_inventory(original)


def test_production_launcher_fixed_deny_policy_minimal_env_canonical_stdin_no_credentials(monkeypatch):
    payload = {"run_id":RUN,"expected_complete_sha256":"e"*64,"current_identity":{"head":HEAD}}
    def fake(args, **kwargs):
        assert args[:4] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec")
        assert args[4:6] == ("-p", m.VERIFICATION_POLICY)
        assert all(name in m.VERIFICATION_POLICY for name in ("deny network*", "deny process-fork", "deny file-write*"))
        assert kwargs["cwd"] == m.LANE_ROOT and kwargs["env"] == {"PATH":"/usr/bin:/bin:/usr/sbin:/sbin"}
        assert kwargs["input"] == encoded(payload) and kwargs["capture_output"] is True
        assert "MASSIVE_API_KEY" not in " ".join(args) and "security" not in " ".join(args)
        return SimpleNamespace(returncode=0,stdout=b'{"invented":true}',stderr=b'')
    monkeypatch.setattr(m.subprocess, "run", fake)
    assert m._launch_verify_worker(payload,root=m.LANE_ROOT) == {"invented":True}


def test_verification_cli_does_not_echo_arbitrary_failure_fields(monkeypatch,capsys):
    def bad(*args):
        exc=RuntimeError(KEY)
        exc.failure_fields={"phase":KEY,"secret":KEY}
        raise exc
    monkeypatch.setattr(m,"verify_actual_capture",bad)
    assert m.main(["--verify-only","--run-id",RUN,"--expected-head",HEAD,"--expected-complete-sha256","e"*64]) == 2
    output=capsys.readouterr().out
    assert KEY not in output and "secret" not in output


@pytest.mark.parametrize("exc", [RuntimeError(KEY),KeyError(KEY),OSError(13,KEY,"private-path")])
def test_verification_failure_field_whitelist_only(exc):
    observed=m._failure_fields(exc,"not-a-phase-"+KEY)
    assert set(observed)=={"phase","exception_category","fixed_code","recognized_os_errno"}
    assert KEY not in encoded(observed).decode()


# Section 194 (Claude review): echo screening and retention, end to end through _response.
def _ok(raw):
    return m.ProviderMetadataResponse(200, raw, True, None)


@pytest.mark.parametrize("encode", ["percent", "plus"])
def test_percent_encoded_secret_echo_is_refused_and_never_retained(encode):
    import urllib.parse
    quoted = ("".join("%%%02X" % byte for byte in KEY.encode()) if encode == "percent"
              else urllib.parse.quote_plus(KEY.replace("-", " ")))
    secret = KEY if encode == "percent" else KEY.replace("-", " ")
    raw = encoded(body(next_url="https://api.massive.com/benzinga/v1/earnings?cursor=" + quoted))
    assert secret.encode() not in raw
    receipt, retained, metadata = m._response(_ok(raw), m.WINDOWS[0], secret)
    assert receipt["disposition"] == "credential_echo_refused" and retained is None and metadata is None
    assert receipt["retained_raw"] is False and receipt["body_sha256"] is None


def test_echo_found_only_during_projection_is_never_retained(monkeypatch):
    raw = encoded(body())
    monkeypatch.setattr(m, "_private_json", lambda raw, *, credential: None)  # an earlier screen that missed it
    def project(raw, window, *, credential):
        raise m.EarningsGapError("credential_echo_refused")
    monkeypatch.setattr(m, "_project", project)
    receipt, retained, metadata = m._response(_ok(raw), m.WINDOWS[0], KEY)
    assert receipt["disposition"] == "credential_echo_refused" and retained is None and metadata is None
    assert receipt["retained_raw"] is False and receipt["body_sha256"] is None


# Codex counter-review: privacy screening must survive common nested URL encoding.
def _percent_layers(value, depth):
    for _ in range(depth):
        value = "".join("%%%02X" % byte for byte in value.encode("ascii"))
    return value


@pytest.mark.parametrize("depth", [2, 3])
@pytest.mark.parametrize("location", ["cursor", "nested", "key"])
def test_nested_percent_encoded_credential_is_refused_without_body_or_metadata(depth, location):
    echo = _percent_layers(KEY, depth)
    value = body()
    if location == "cursor":
        value["next_url"] = "https://api.massive.com/benzinga/v1/earnings?cursor=" + echo
    elif location == "nested":
        value["results"][0]["company_name"] = {"invented": [echo]}
    else:
        value[echo] = "invented"
    raw = encoded(value)
    assert KEY.encode() not in raw
    receipt, retained, metadata = m._response(_ok(raw), m.WINDOWS[0], KEY)
    assert receipt["disposition"] == "credential_echo_refused"
    assert retained is metadata is None and receipt["retained_raw"] is False
    assert receipt["body_bytes"] is receipt["body_sha256"] is None


@pytest.mark.parametrize("secret", ["invented+private-key", "invented private key"])
def test_mixed_plus_and_percent_encoding_preserves_both_secret_tracks(secret):
    from urllib.parse import quote_plus
    echo = quote_plus(quote_plus(secret, safe=""), safe="")
    raw = encoded(body(next_url="https://api.massive.com/benzinga/v1/earnings?cursor=" + echo))
    assert secret.encode() not in raw
    receipt, retained, metadata = m._response(_ok(raw), m.WINDOWS[0], secret)
    assert receipt["disposition"] == "credential_echo_refused"
    assert retained is metadata is None and receipt["retained_raw"] is False
    assert receipt["body_bytes"] is receipt["body_sha256"] is None


def test_literal_plus_secret_cannot_disappear_during_percent_unwrapping():
    secret = "invented+private-key"
    # Plus-aware decoding loses the literal '+' before the percent-encoded
    # letter is unwrapped; the independent plain track is necessary here.
    raw = encoded(body(next_url="https://api.massive.com/benzinga/v1/earnings?cursor=inv%2565nted+private-key"))
    assert secret.encode() not in raw
    receipt, retained, metadata = m._response(_ok(raw), m.WINDOWS[0], secret)
    assert receipt["disposition"] == "credential_echo_refused"
    assert retained is metadata is None and receipt["retained_raw"] is False
    assert receipt["body_bytes"] is receipt["body_sha256"] is None


def test_unresolved_encoding_past_the_bound_refuses_even_without_a_secret_echo():
    # Repeatedly escaping only '%' keeps this invented benign control small.
    echo = "%41"
    for _ in range(12):
        echo = echo.replace("%", "%25")
    raw = encoded(body(next_url="https://api.massive.com/benzinga/v1/earnings?cursor=" + echo))
    receipt, retained, metadata = m._response(_ok(raw), m.WINDOWS[0], KEY)
    assert receipt["disposition"] == "credential_echo_refused"
    assert retained is metadata is None and receipt["retained_raw"] is False
    assert receipt["body_bytes"] is receipt["body_sha256"] is None


def test_stable_benign_url_encoding_remains_metadata_candidate_not_authority():
    raw = encoded(body())
    value = json.loads(raw)
    value["results"][0]["company_name"] = "Invented%2520Company+Only"
    receipt, retained, metadata = m._response(_ok(encoded(value)), m.WINDOWS[0], KEY)
    assert receipt["disposition"] == "candidate_metadata_observed" and receipt["retained_raw"]
    assert retained == encoded(value) and metadata["rows"][0]["company_name"] == value["results"][0]["company_name"]
    assert metadata["actual_release_archive_verified"] is False


# Section 194 (Claude review): this module's own transport had no direct test.
def _gap_request():
    return m.EarningsGapRequest(m.URLS[0], (("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                            ("Authorization", "Bearer " + KEY)))


class _Stream:
    def __init__(self, status=200, url=None, raw=None):
        self.raw = encoded(body()) if raw is None else raw
        self.headers = Message();self.headers["Content-Length"] = str(len(self.raw))
        self.status, self.url, self.closed, self.offset = status, url, False, 0

    def getcode(self): return self.status
    def geturl(self): return self.url
    def read(self, size=-1):
        chunk = self.raw[self.offset:] if size < 0 else self.raw[self.offset:self.offset + size]
        self.offset += len(chunk);return chunk
    def close(self): self.closed = True


@pytest.mark.parametrize("case", ["exact", "origin", "redirect"])
def test_default_transport_tls_no_proxy_no_redirect_and_exact_origin(monkeypatch, case):
    import ssl
    seen = {}
    stream = _Stream(status=302 if case == "redirect" else 200,
                     url="https://evil.example/x" if case == "origin" else m.URLS[0])
    class Opener:
        def open(self, req, timeout):
            seen["request"], seen["timeout"] = req, timeout
            return stream
    def build_opener(*handlers):
        seen["handlers"] = handlers
        return Opener()
    monkeypatch.setattr(m.request, "build_opener", build_opener)
    response = m._default_transport(_gap_request())
    proxy, deny, https = seen["handlers"]
    assert proxy.proxies == {} and type(deny) is m._DenyRedirect
    assert https._context.verify_mode == ssl.CERT_REQUIRED and https._context.check_hostname is True
    assert seen["request"].full_url == m.URLS[0] and seen["request"].get_method() == "GET"
    assert seen["timeout"] == m.TIMEOUT_SECONDS and stream.closed
    if case == "exact":
        assert response.status == 200 and response.body == stream.raw and response.body_complete
    elif case == "origin":
        assert response.disposition == "response-origin-mismatch" and response.body == b""
    else:
        assert response.disposition == "redirect-refused" and response.body == b""
