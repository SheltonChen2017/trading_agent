"""Synthetic isolated proof of the seven-request, one-shot source probe."""
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_source_probe as probe
from research.target_price_revisions_qc import extended_source_probe_driver as driver

NOW = datetime(2026, 10, 10, 18, tzinfo=timezone.utc)
SECRET = "SYNTHETIC_MASSIVE_TEST_SECRET"


@pytest.fixture(autouse=True)
def no_external_access(monkeypatch):
    """A test or mutation must never reach real roots, credentials or HTTPS."""
    actual_root = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
    original_directory = probe._open_directory
    original_resolver = probe.helper._production_credential
    original_transport = probe._https_get
    blocked = []
    def directory(path):
        if path == actual_root or path.is_relative_to(actual_root):
            blocked.append("physical-lane-directory")
            pytest.fail("test firewall refused actual physical lane/private directory")
        return original_directory(path)
    def forbidden(*_args, **_kwargs):
        blocked.append("external-operation")
        pytest.fail("test firewall refused real credential or HTTPS operation")
    monkeypatch.setattr(probe, "_open_directory", directory)
    monkeypatch.setattr(probe.helper, "_production_credential", forbidden)
    monkeypatch.setattr(probe, "_https_get", forbidden)
    monkeypatch.setattr(probe.http.client, "HTTPSConnection", forbidden)
    return {"resolver": original_resolver, "transport": original_transport,
            "directory": original_directory, "blocked": blocked}


def plan(mode="offline-fixture"):
    return probe.freeze_probe_plan(code_sha256="a" * 64,
        helper_hashes={path: "b" * 64 for path in probe.HELPER_PATHS},
        git_sha="c" * 40, owner_instruction_sha256="d" * 64,
        created_utc="2026-10-10T17:00:00+00:00", expires_utc="2026-10-12T17:00:00+00:00",
        mode=mode)


def root(tmp_path):
    result = tmp_path / "private-probe"
    result.mkdir(mode=0o700)
    return result


def sample(start="2021-01-01", **changes):
    row = {"benzinga_id": 123, "benzinga_firm_id": "SYNTHETIC_FIRM",
           "ticker": "SYNTHETIC", "date": start,
           "last_updated": start + "T12:00:00Z", "currency": "USD",
           "price_target_action": "raises", "price_target": "11.123456789012345678901234567890",
           "previous_price_target": "10"}
    row.update(changes)
    return row


def response(body=None, status=200, *, headers=None, complete=True):
    if body is None:
        body = {"status": "OK", "results": [sample()]}
    payload = body if type(body) is bytes else json.dumps(body).encode("utf-8")
    if headers is None:
        headers = (("content-type", "application/json"), ("content-length", str(len(payload))))
    return probe.ProbeResponse(status, headers, payload, complete)


def execute(tmp_path, *, resolver=None, transport=None, frozen=None, now=NOW):
    private = root(tmp_path)
    actual = frozen or plan()
    resolver = resolver or (lambda _provider: SECRET)
    transport = transport or (lambda query, _key: response({"status": "OK", "results": [sample(dict(query)["date.gte"])]}))
    result = probe._execute_fixture_probe(actual, private, now=now,
                                        credential_resolver=resolver, transport=transport)
    return private, actual, result, json.loads(result.payload)


def rewrite_plan(body):
    payload = probe._canonical(body)
    return probe.ProbePlan(payload, hashlib.sha256(payload).hexdigest())


def test_fixed_queries_have_exact_seven_windows():
    assert len(probe.QUERIES) == 7
    assert probe.WINDOWS == (("2020-09-01", "2020-12-31"), ("2021-01-01", "2021-12-31"),
        ("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31"),
        ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"),
        ("2026-01-01", "2026-10-09"))
    for query, (start, end) in zip(probe.QUERIES, probe.WINDOWS):
        assert query == (("date.gte", start), ("date.lte", end), ("limit", "1"), ("sort", "date.asc"))


def test_good_samples_are_closed_counts_not_history_admission(tmp_path):
    private, frozen, result, report = execute(tmp_path)
    assert result.sha256 == hashlib.sha256(result.payload).hexdigest()
    assert report["all_requests_succeeded"] is True
    assert report["attempted_requests"] == report["sampled_rows"] == 7
    assert report["complete_history"] is report["point_in_time_data"] is False
    assert report["rights_verified"] is report["full_capture_admitted"] is False
    assert report["development_looks"] == report["quantconnect_attempts"] == report["outcome_reads"] == 0
    assert report["reserved_requests"] == 7
    assert len(list(private.iterdir())) == 18
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in private.iterdir())
    terminal = json.loads(result.terminal_path.read_bytes())
    assert terminal["status"] == "COMPLETED"
    assert terminal["aggregate_sha256"] == result.sha256
    for index, row in enumerate(report["windows"]):
        assert row["request_index"] == index + 1
        assert row["projection"]["date_in_window_count"] == 1
        assert row["projection"]["aware_touch_clock_count"] == 1
        assert row["projection"]["positive_nominal_pair_count"] == 1
        receipt = json.loads((private / f"{probe.OPERATION_ID}.request.{index + 1}.terminal.json").read_bytes())
        assert len(receipt["response_sha256"]) == 64 and receipt["response_complete"] is True
    assert frozen.body()["freeze_sha256"] == probe.FREEZE_SHA256


def test_all_spent_claims_precede_credentials_and_queries(tmp_path):
    private = root(tmp_path)
    calls = []
    def resolver(provider):
        assert provider == "massive"
        assert (private / f"{probe.OPERATION_ID}.access.spent.json").exists()
        for index in range(1, 8):
            assert (private / f"{probe.OPERATION_ID}.request.{index}.spent.json").exists()
        calls.append("credentials")
        return SECRET
    def fetch(query, credential):
        assert calls and calls[0] == "credentials"
        assert credential == SECRET
        assert query == probe.QUERIES[len(calls) - 1]
        calls.append("request")
        return response({"status": "OK", "results": [sample(dict(query)["date.gte"])]})
    probe._execute_fixture_probe(plan(), private, now=NOW, credential_resolver=resolver, transport=fetch)
    assert calls == ["credentials"] + ["request"] * 7


def test_second_run_and_new_plan_cannot_renew_operation(tmp_path):
    private, frozen, _, _ = execute(tmp_path)
    called = []
    for alternate in (frozen, rewrite_plan({**frozen.body(), "git_sha": "e" * 40})):
        with pytest.raises(probe.ProbeError, match="already spent"):
            probe._execute_fixture_probe(alternate, private, now=NOW,
                credential_resolver=lambda _: called.append("credential"),
                transport=lambda *_: called.append("request"))
    assert called == []


@pytest.mark.parametrize("name,value", [
    ("queries", [{"date.gte": "2000-01-01", "date.lte": "2030-01-01", "limit": "1000", "sort": "date.asc"}]),
    ("host", "unrelated.invalid"), ("endpoint", "/v3/reference"),
    ("private_root", "/tmp/other"), ("freeze_sha256", "e" * 64),
    ("limits", {"requests": 8}), ("raw_response_retention", True),
    ("outcome_access", True), ("unknown_field", True), ("mode", "invalid")])
def test_widened_or_unknown_plan_is_rejected(name, value):
    body = plan().body()
    body[name] = value
    with pytest.raises(probe.ProbeError):
        rewrite_plan(body).body()


@pytest.mark.parametrize("payload,digest", [(b"{}", "a" * 64), (b"NaN", "a" * 64),
    (b"{}", True), (b"x" * 16385, "a" * 64), ("not bytes", "a" * 64)])
def test_invalid_or_tampered_plan_frame(payload, digest):
    with pytest.raises(probe.ProbeError):
        probe.ProbePlan(payload, digest).body()


@pytest.mark.parametrize("key,value", [("code_sha256", "bad"), ("git_sha", "a" * 39),
    ("owner_instruction_sha256", True), ("helper_hashes", {}),
    ("expires_utc", "2026-10-12T17:00:01Z"), ("created_utc", "2026-10-10T17:00:00")])
def test_invalid_freeze_fields(key, value):
    values = {name: plan().body()[name] for name in ("code_sha256", "git_sha",
        "owner_instruction_sha256", "helper_hashes", "created_utc", "expires_utc", "mode")}
    values[key] = value
    with pytest.raises(probe.ProbeError):
        probe.freeze_probe_plan(**values)


@pytest.mark.parametrize("now", [datetime(2026, 10, 10, 16, tzinfo=timezone.utc),
    datetime(2026, 10, 12, 17, tzinfo=timezone.utc), datetime(2026, 10, 10, 18)])
def test_expired_or_invalid_clock_spends_nothing(tmp_path, now):
    private = root(tmp_path)
    with pytest.raises(probe.ProbeError):
        probe._execute_fixture_probe(plan(), private, now=now,
            credential_resolver=lambda _: SECRET, transport=lambda *_: None)
    assert list(private.iterdir()) == []


def test_root_permissions_and_symlinks_are_refused_before_credentials(tmp_path):
    private = root(tmp_path)
    private.chmod(0o755)
    called = []
    with pytest.raises(probe.ProbeError):
        probe._execute_fixture_probe(plan(), private, now=NOW,
            credential_resolver=lambda _: called.append(True), transport=lambda *_: None)
    private.chmod(0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(private, target_is_directory=True)
    with pytest.raises(probe.ProbeError):
        probe._execute_fixture_probe(plan(), alias, now=NOW,
            credential_resolver=lambda _: called.append(True), transport=lambda *_: None)
    assert called == []


def test_parent_symlink_is_refused(tmp_path):
    parent = tmp_path / "safe-parent"
    parent.mkdir()
    private = parent / "private"
    private.mkdir(mode=0o700)
    alias = tmp_path / "parent-alias"
    alias.symlink_to(parent, target_is_directory=True)
    with pytest.raises(probe.ProbeError):
        probe._execute_fixture_probe(plan(), alias / "private", now=NOW,
            credential_resolver=lambda _: SECRET, transport=lambda *_: None)


@pytest.mark.parametrize("resolver", [lambda _: None, lambda _: "REAL_LOOKING_KEY_123",
    lambda _: "SYNTHETIC_BAD\nKEY", lambda _: (_ for _ in ()).throw(RuntimeError("SYNTHETIC_PROVIDER_DETAIL"))])
def test_missing_or_nonsynthetic_fixture_credentials_leave_claims_spent(tmp_path, resolver):
    calls = []
    private, _, result, report = execute(tmp_path, resolver=resolver,
                                         transport=lambda *_: calls.append(True))
    assert calls == [] and report["attempted_requests"] == 0
    assert report["all_requests_succeeded"] is False
    assert len(list(private.glob("*.spent.json"))) == 8
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_interruption_preserves_unknown_spent_receipts(tmp_path):
    private = root(tmp_path)
    def interrupted(*_):
        raise KeyboardInterrupt("PRIVATE_VALUE")
    with pytest.raises(KeyboardInterrupt, match="scope remains spent"):
        probe._execute_fixture_probe(plan(), private, now=NOW,
            credential_resolver=lambda _: SECRET, transport=interrupted)
    terminal = json.loads((private / f"{probe.OPERATION_ID}.terminal.json").read_bytes())
    assert terminal["status"] == "INTERRUPTED"
    assert terminal["attempted_requests"] == 1
    assert len(list(private.glob("*.spent.json"))) == 8
    assert b"PRIVATE_VALUE" not in b"".join(path.read_bytes() for path in private.iterdir())


def test_fixture_cannot_take_production_adapters_or_plan(tmp_path):
    private = root(tmp_path)
    for frozen, resolver, transport in (
        (plan("production"), lambda _: SECRET, lambda *_: None),
        (plan(), probe._FIXED_RESOLVER, lambda *_: None),
        (plan(), lambda _: SECRET, probe._FIXED_TRANSPORT)):
        with pytest.raises(probe.ProbeError):
            probe._execute_fixture_probe(frozen, private, now=NOW,
                                        credential_resolver=resolver, transport=transport)
    with pytest.raises(probe.ProbeError):
        probe._execute_fixture_probe(plan(), probe.PRIVATE_ROOT, now=NOW,
            credential_resolver=lambda _: SECRET, transport=lambda *_: None)
    assert list(private.iterdir()) == []


def test_public_production_api_has_no_fixture_adapters():
    with pytest.raises(TypeError):
        probe.execute_probe(plan("production"), credential_resolver=lambda _: SECRET)
    with pytest.raises(probe.ProbeError):
        probe.execute_probe(plan())


def test_production_custody_precedes_executor(monkeypatch):
    called = []
    def refuse(_body):
        called.append("verify")
        raise probe.ProbeError("synthetic source mismatch")
    monkeypatch.setattr(probe, "_verify_execution_identity", refuse)
    monkeypatch.setattr(probe, "_execute", lambda *_: called.append("execute"))
    with pytest.raises(probe.ProbeError, match="mismatch"):
        probe.execute_probe(plan("production"))
    assert called == ["verify"]


def install_custody_stubs(monkeypatch, tmp_path):
    body = plan("production").body()
    sources = {path: b"SYNTHETIC_SOURCE" for path in probe.HELPER_PATHS}
    body["helper_hashes"] = {path: hashlib.sha256(payload).hexdigest() for path, payload in sources.items()}
    sources[probe.SOURCE_RELATIVE] = b"SYNTHETIC_CODE"
    body["code_sha256"] = hashlib.sha256(sources[probe.SOURCE_RELATIVE]).hexdigest()
    sources[probe.FREEZE_RELATIVE] = b"SYNTHETIC_FREEZE"
    monkeypatch.setattr(probe, "FREEZE_SHA256", hashlib.sha256(sources[probe.FREEZE_RELATIVE]).hexdigest())
    body["freeze_sha256"] = probe.FREEZE_SHA256
    monkeypatch.setattr(probe, "_execution_paths", lambda: (probe.LANE_ROOT, probe.LANE_ROOT))
    def git(command, **kwargs):
        if command[:2] == ["git", "show"]:
            assert command[2].startswith(body["git_sha"] + ":")
            return SimpleNamespace(stdout=sources[command[2].split(":", 1)[1]])
        if command == ["git", "rev-parse", "--show-toplevel"]:
            value = str(probe.LANE_ROOT)
        elif command == ["git", "branch", "--show-current"]:
            value = probe.LANE_BRANCH
        elif command == ["git", "rev-parse", "HEAD"]:
            value = body["git_sha"]
        else:
            assert command == ["git", "status", "--short"]
            value = ""
        return SimpleNamespace(stdout=value.encode())
    monkeypatch.setattr(probe.subprocess, "run", git)
    # No repository/operator/private input is read by this synthetic verifier.
    monkeypatch.setattr(probe, "_open_directory", lambda _: os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY))
    monkeypatch.setattr(probe, "_read_source", lambda relative: sources[relative])
    return body, sources


@pytest.mark.parametrize("tamper", [None, "module", "freeze", *probe.HELPER_PATHS])
def test_production_checks_every_reachable_hash(monkeypatch, tmp_path, tamper):
    body, sources = install_custody_stubs(monkeypatch, tmp_path)
    if tamper:
        path = probe.SOURCE_RELATIVE if tamper == "module" else probe.FREEZE_RELATIVE if tamper == "freeze" else tamper
        sources[path] += b"MUTATION"
        with pytest.raises(probe.ProbeError, match="hash mismatch"):
            probe._verify_execution_identity(body)
    else:
        probe._verify_execution_identity(body)


@pytest.mark.parametrize("mismatch", ["root", "branch", "HEAD", "module_path"])
def test_production_refuses_wrong_execution_identity(monkeypatch, tmp_path, mismatch):
    body, _ = install_custody_stubs(monkeypatch, tmp_path)
    if mismatch == "root":
        monkeypatch.setattr(probe, "_execution_paths", lambda: (tmp_path, tmp_path))
    elif mismatch == "module_path":
        monkeypatch.setattr(probe, "__file__", str(tmp_path / "untrusted.py"))
    else:
        prior = probe.subprocess.run
        def git(command, **kwargs):
            if mismatch == "branch" and command == ["git", "branch", "--show-current"]:
                return SimpleNamespace(stdout=b"codex/unrelated")
            if mismatch == "HEAD" and command == ["git", "rev-parse", "HEAD"]:
                return SimpleNamespace(stdout=b"f" * 40)
            return prior(command, **kwargs)
        monkeypatch.setattr(probe.subprocess, "run", git)
    with pytest.raises(probe.ProbeError):
        probe._verify_execution_identity(body)


def test_production_requires_current_sources_to_be_committed(monkeypatch, tmp_path):
    body, _ = install_custody_stubs(monkeypatch, tmp_path)
    prior = probe.subprocess.run
    def git(command, **kwargs):
        if command[:2] == ["git", "show"]:
            return SimpleNamespace(stdout=b"UNCOMMITTED_OLD_SOURCE")
        return prior(command, **kwargs)
    monkeypatch.setattr(probe.subprocess, "run", git)
    with pytest.raises(probe.ProbeError, match="committed source hash mismatch"):
        probe._verify_execution_identity(body)


@pytest.mark.parametrize("bad", [
    response(b"x" * (probe.MAX_BYTES + 1)), response(complete=False),
    response(headers=(("content-length", "1"),)),
    response(headers=(("content-type", "text/html"),)),
    response(headers=(("content-encoding", "gzip"),)),
    response(headers=(("content-length", "12"), ("content-length", "12"))),
    response(headers=(("unexpected", "value"),)), response(b"{malformed"),
    response(b'{"status":"OK","results":[],"status":"BAD"}'),
    response(b'{"status":"OK","results":[NaN]}'),
    response({"status": "UNEXPECTED", "results": []}),
    response({"results": []}), response({"status": "OK", "results": "wrong"}),
    response({"status": "OK", "results": [sample(), sample()]}),
    response({"status": "OK", "results": [None]}),
    response({"status": "OK", "results": [sample("2020-01-01")]}),
    response({"status": "OK", "results": [sample("2021-02-30")]}),
    response(status=True), response(complete=1)])
def test_bad_wire_headers_schema_or_scope_refused(bad):
    with pytest.raises(probe.ProbeError):
        probe._reduce_response(bad, SECRET, ("2021-01-01", "2021-12-31"), NOW)


def test_exact_response_byte_bound():
    prefix = b'{"status":"OK","results":[],"padding":"'
    payload = prefix + b"x" * (probe.MAX_BYTES - len(prefix) - 2) + b'"}'
    assert len(payload) == probe.MAX_BYTES
    disposition, _ = probe._reduce_response(response(payload), SECRET, probe.WINDOWS[1], NOW)
    assert disposition == "sample_empty"


@pytest.mark.parametrize("secret_body", [
    {"status": "OK", "results": [], "echo": SECRET},
    {"status": "OK", "results": [], SECRET: "echo"},
    ('{"status":"OK","results":[],"echo":"' + ''.join('\\u%04x' % ord(ch) for ch in SECRET) + '"}').encode()])
def test_raw_or_escaped_token_echo_never_persists_hash_or_value(tmp_path, secret_body):
    private, _, _, report = execute(tmp_path, transport=lambda *_: response(secret_body))
    assert report["all_requests_succeeded"] is False
    assert report["attempted_requests"] == 7
    for path in private.glob("*.terminal.json"):
        body = json.loads(path.read_bytes())
        if "response_sha256" in body:
            assert body["response_sha256"] is None
    assert SECRET.encode() not in b"".join(path.read_bytes() for path in private.iterdir())


def test_missing_targets_are_sampled_not_entitlement_denial():
    disposition, counts = probe._reduce_response(response({"status": "OK", "results": [sample(price_target=None)]}),
                                                SECRET, probe.WINDOWS[1], NOW)
    assert disposition == "sampled"
    assert counts["positive_nominal_pair_count"] == 0


def test_counts_preserve_invalid_ids_and_clocks_without_zero_signal():
    disposition, counts = probe._reduce_response(response({"status": "OK", "results": [sample(
        benzinga_id=True, benzinga_firm_id=None, last_updated="2021-01-01T12:00:00")]}),
        SECRET, probe.WINDOWS[1], NOW)
    assert disposition == "sampled"
    assert counts["event_id_valid_count"] == counts["event_id_integer_count"] == 0
    assert counts["firm_id_valid_count"] == counts["aware_touch_clock_count"] == 0


def test_exact_decimal_targets_do_not_float_round(monkeypatch):
    seen = []
    original = probe._positive_target
    def inspect(value):
        seen.append(value)
        return original(value)
    monkeypatch.setattr(probe, "_positive_target", inspect)
    payload = b'{"status":"OK","results":[{"date":"2021-01-01","price_target":11.123456789012345678901234567890,"previous_price_target":10}]}'
    _, counts = probe._reduce_response(response(payload), SECRET, probe.WINDOWS[1], NOW)
    assert seen[0] == Decimal("11.123456789012345678901234567890")
    assert type(seen[0]) is Decimal
    assert counts["positive_nominal_pair_count"] == 1


def test_non200_and_empty_are_explicit_without_pagination():
    disposition, counts = probe._reduce_response(response({"status": "NOT_AUTHORIZED"}, status=403),
                                                SECRET, probe.WINDOWS[1], NOW)
    assert disposition == "http_refused" and counts["sample_count"] == 0
    disposition, counts = probe._reduce_response(response({"status": "OK", "results": [], "next_url": "https://other.invalid"}),
                                                SECRET, probe.WINDOWS[1], NOW)
    assert disposition == "sample_empty" and counts["pagination_present"] is True


def test_public_report_contains_only_closed_metadata_and_counts(tmp_path):
    _, _, result, report = execute(tmp_path)
    expected = {"schema", "operation_id", "study_id", "plan_sha256", "windows", "reserved_requests",
        "attempted_requests", "successful_sample_responses", "sampled_rows", "response_bytes",
        "all_requests_succeeded", "interrupted", "scope_spent", "samples_only", "complete_history",
        "point_in_time_data", "rights_verified", "outcome_reads", "development_looks",
        "quantconnect_attempts", "canonical_admission", "trading", "old_receipts_renewed", "full_capture_admitted"}
    assert set(report) == expected
    for row in report["windows"]:
        assert set(row) == {"window_start", "window_end", "request_index", "http_status", "disposition", "projection"}
        assert set(row["projection"]) == set(probe._empty_projection())
    for token in (SECRET, "SYNTHETIC_FIRM", "SYNTHETIC\"", "11.123456789", "benzinga_id", "price_target", "request_id"):
        assert token.encode() not in result.payload


def test_claim_failure_leaves_global_spent_and_never_loads_credentials(tmp_path):
    private = root(tmp_path)
    (private / f"{probe.OPERATION_ID}.request.3.spent.json").write_bytes(b"PREEXISTING")
    called = []
    with pytest.raises(probe.ProbeError, match="already spent"):
        probe._execute_fixture_probe(plan(), private, now=NOW,
            credential_resolver=lambda _: called.append(True), transport=lambda *_: None)
    assert called == []
    assert (private / f"{probe.OPERATION_ID}.access.spent.json").exists()
    assert (private / f"{probe.OPERATION_ID}.request.3.spent.json").read_bytes() == b"PREEXISTING"


def fake_http(monkeypatch, body, *, headers=None, closed=True, status=200):
    calls = []
    class Wire:
        def getheaders(self):
            return headers if headers is not None else [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        def read(self, bound):
            calls.append(("read", bound))
            return body[:bound]
        def isclosed(self):
            return closed
    wire = Wire()
    wire.status = status
    class Connection:
        def __init__(self, host, port, **kwargs):
            calls.append(("connect", host, port, kwargs["timeout"]))
        def set_debuglevel(self, value):
            assert value == 0
        def request(self, method, url, headers):
            calls.append(("request", method, url))
            assert headers["Authorization"] == "Bearer " + SECRET
            assert headers["Accept-Encoding"] == "identity"
        def getresponse(self):
            return wire
        def close(self):
            calls.append(("close",))
    monkeypatch.setattr(probe, "_deadline", nullcontext)
    monkeypatch.setattr(probe.http.client, "HTTPSConnection", Connection)
    return calls


def test_transport_bounds_no_redirect_no_retry_no_pagination(monkeypatch, no_external_access):
    body = b'{"status":"OK","results":[]}'
    calls = fake_http(monkeypatch, body)
    wire = no_external_access["transport"](probe.QUERIES[0], SECRET)
    assert wire.body == body and wire.complete is True
    assert calls == [("connect", "api.massive.com", 443, 30),
        ("request", "GET", "/benzinga/v1/ratings?date.gte=2020-09-01&date.lte=2020-12-31&limit=1&sort=date.asc"),
        ("read", 65536), ("close",)]


@pytest.mark.parametrize("headers", [[("Content-Length", "65537")], [("Content-Encoding", "gzip")],
    [("Content-Type", "text/html")], [("Content-Length", "1"), ("Content-Length", "1")]])
def test_bad_http_headers_refuse_body_consumption(monkeypatch, headers, no_external_access):
    calls = fake_http(monkeypatch, b"PRIVATE_BODY", headers=headers)
    wire = no_external_access["transport"](probe.QUERIES[0], SECRET)
    assert wire.body == b"" and wire.complete is False
    assert not any(call[0] == "read" for call in calls)


def test_http_unfinished_and_short_body_are_not_complete(monkeypatch, no_external_access):
    calls = fake_http(monkeypatch, b"{}", headers=[("Content-Length", "3")], closed=False)
    wire = no_external_access["transport"](probe.QUERIES[0], SECRET)
    assert wire.complete is False and ("read", 65536) in calls


def test_transport_scope_widening_refused_before_http(monkeypatch, no_external_access):
    calls = []
    monkeypatch.setattr(probe.http.client, "HTTPSConnection", lambda *_a, **_k: calls.append(True))
    with pytest.raises(probe.ProbeError):
        no_external_access["transport"]((("limit", "1000"),), SECRET)
    assert calls == []


def test_wall_deadline_sets_and_finally_restores_handler(monkeypatch):
    calls = []
    monkeypatch.setattr(probe.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(probe.signal, "getsignal", lambda _: "OLD")
    monkeypatch.setattr(probe.signal, "signal", lambda *args: calls.append(("handler", args)))
    monkeypatch.setattr(probe.signal, "setitimer", lambda *args: calls.append(("timer", args)))
    with pytest.raises(RuntimeError):
        with probe._deadline():
            raise RuntimeError("synthetic")
    assert calls[1] == ("timer", (probe.signal.ITIMER_REAL, 30))
    assert calls[-2] == ("timer", (probe.signal.ITIMER_REAL, 0))
    assert calls[-1] == ("handler", (probe.signal.SIGALRM, "OLD"))


def safe_report(**changes):
    result = {"schema": "tpr-extended-source-probe-report-v1", "operation_id": probe.OPERATION_ID,
        "study_id": probe.STUDY_ID, "scope_spent": True, "reserved_requests": 7,
        "attempted_requests": 7, "successful_sample_responses": 7, "sampled_rows": 7,
        "response_bytes": 777, "all_requests_succeeded": True, "interrupted": False,
        "samples_only": True, "complete_history": False, "point_in_time_data": False,
        "rights_verified": False, "full_capture_admitted": False, "canonical_admission": False,
        "trading": False, "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0}
    result.update(changes)
    payload = probe._canonical(result)
    return probe.ProbeResult(payload, probe._digest(payload), Path("SYNTHETIC_AGGREGATE"), Path("SYNTHETIC_TERMINAL"))


def install_driver_stubs(monkeypatch, tmp_path):
    sources = {relative: ("SYNTHETIC_" + relative).encode() for relative in driver.SOURCE_PATHS}
    hashes = {relative: probe._digest(payload) for relative, payload in sources.items()}
    monkeypatch.setattr(driver, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(probe, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(probe, "PRIVATE_ROOT", tmp_path / "artifacts" / "target_price_extended" / probe.STUDY_ID / "source_probe")
    monkeypatch.setattr(probe, "FREEZE_SHA256", hashes[probe.FREEZE_RELATIVE])
    monkeypatch.setattr(driver, "_verify_imports", lambda: None)
    monkeypatch.setattr(driver, "_git_head", lambda: "c" * 40)
    monkeypatch.setattr(driver, "_bound_inventory", lambda _sha: hashes)
    monkeypatch.setattr(driver, "_now", lambda: NOW)
    monkeypatch.setattr(probe, "_verify_execution_identity", lambda _body: None)
    calls = []
    def execute(frozen):
        private = probe.PRIVATE_ROOT
        saved_plan = private / driver.DRIVER_PLAN_NAME
        assert saved_plan.read_bytes() == frozen.payload
        saved_receipt = json.loads((private / driver.DRIVER_RECEIPT_NAME).read_bytes())
        assert saved_receipt["plan_sha256"] == frozen.sha256
        assert saved_receipt["source_hashes"] == hashes
        assert saved_receipt["driver_sha256"] == hashes[driver.SOURCE_RELATIVE]
        assert saved_receipt["provider_operation_stage"] == "not_yet_invoked_by_driver"
        assert not list(private.glob("*.spent.json"))
        calls.append(frozen)
        return safe_report()
    monkeypatch.setattr(probe, "execute_probe", execute)
    return sources, hashes, calls


def driver_args():
    return {"owner_instruction_sha256": "d" * 64,
            "created_utc": "2026-10-10T17:00:00Z", "expires_utc": "2026-10-12T17:00:00Z"}


def test_driver_persists_exact_committed_preparation_before_probe(monkeypatch, tmp_path):
    _, _, calls = install_driver_stubs(monkeypatch, tmp_path)
    result = driver.run_probe(**driver_args())
    report = json.loads(result.payload)
    assert result.sha256 == probe._digest(result.payload)
    assert len(calls) == 1
    assert report["status"] == "COMPLETED"
    assert set(report) == driver.PUBLIC_KEYS
    assert all((probe.PRIVATE_ROOT / name).stat().st_mode & 0o777 == 0o600
               for name in (driver.DRIVER_PLAN_NAME, driver.DRIVER_RECEIPT_NAME))
    for directory in (tmp_path / "artifacts" / "target_price_extended",
                      probe.PRIVATE_ROOT.parent, probe.PRIVATE_ROOT):
        assert directory.stat().st_mode & 0o777 == 0o700
    with pytest.raises(driver.DriverError, match="already exists"):
        driver.run_probe(**driver_args())
    assert len(calls) == 1


@pytest.mark.parametrize("preexisting", ["empty_leaf", "spent_leaf", "symlink_leaf", "symlink_parent", "unsafe_parent"])
def test_driver_never_reuses_or_follows_private_root(monkeypatch, tmp_path, preexisting):
    _, _, calls = install_driver_stubs(monkeypatch, tmp_path)
    parent = probe.PRIVATE_ROOT.parent
    parent.mkdir(mode=0o700, parents=True)
    (tmp_path / "artifacts" / "target_price_extended").chmod(0o700)
    parent.chmod(0o700)
    if preexisting in ("empty_leaf", "spent_leaf"):
        probe.PRIVATE_ROOT.mkdir(mode=0o700)
        if preexisting == "spent_leaf":
            (probe.PRIVATE_ROOT / "access.spent.json").write_bytes(b"HISTORICAL_SYNTHETIC")
    elif preexisting == "symlink_leaf":
        probe.PRIVATE_ROOT.symlink_to(tmp_path, target_is_directory=True)
    elif preexisting == "unsafe_parent":
        parent.chmod(0o755)
    else:
        parent.rmdir()
        parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(driver.DriverError):
        driver.run_probe(**driver_args())
    assert calls == []
    if preexisting == "spent_leaf":
        assert (probe.PRIVATE_ROOT / "access.spent.json").read_bytes() == b"HISTORICAL_SYNTHETIC"


@pytest.mark.parametrize("gate", ["imports", "head", "sources", "probe_sources"])
def test_driver_refuses_custody_before_any_private_preparation(monkeypatch, tmp_path, gate):
    _, _, calls = install_driver_stubs(monkeypatch, tmp_path)
    def refuse(*_):
        raise driver.DriverError("SYNTHETIC_CUSTODY_REFUSAL")
    if gate == "imports":
        monkeypatch.setattr(driver, "_verify_imports", refuse)
    elif gate == "head":
        monkeypatch.setattr(driver, "_git_head", refuse)
    elif gate == "sources":
        monkeypatch.setattr(driver, "_bound_inventory", refuse)
    else:
        monkeypatch.setattr(probe, "_verify_execution_identity", refuse)
    with pytest.raises(driver.DriverError):
        driver.run_probe(**driver_args())
    assert not (tmp_path / "artifacts").exists()
    assert calls == []


def test_driver_expiry_and_invalid_instruction_fail_before_preparation(monkeypatch, tmp_path):
    _, _, calls = install_driver_stubs(monkeypatch, tmp_path)
    for changes in ({"owner_instruction_sha256": "invalid"}, {"expires_utc": "2026-10-10T17:30:00Z"}):
        with pytest.raises((driver.DriverError, probe.ProbeError)):
            driver.run_probe(**{**driver_args(), **changes})
    assert not (tmp_path / "artifacts").exists() and calls == []


def test_driver_preserves_prepared_root_after_unknown_probe_failure(monkeypatch, tmp_path):
    install_driver_stubs(monkeypatch, tmp_path)
    def fail(_plan):
        raise probe.ProbeError("SYNTHETIC_UNKNOWN_TERMINAL")
    monkeypatch.setattr(probe, "execute_probe", fail)
    with pytest.raises(probe.ProbeError):
        driver.run_probe(**driver_args())
    assert (probe.PRIVATE_ROOT / driver.DRIVER_PLAN_NAME).exists()
    with pytest.raises(driver.DriverError, match="already exists"):
        driver.run_probe(**driver_args())


def test_driver_complete_import_function_identity_positive_and_wrong_function(monkeypatch, no_external_access):
    # Temporarily expose only the function object for filename/type inspection;
    # neither the resolver nor production executor is invoked in this context.
    with monkeypatch.context() as identity:
        identity.setattr(probe.helper, "_production_credential", no_external_access["resolver"])
        driver._verify_imports()
        identity.setattr(probe, "execute_probe", lambda _: None)
        with pytest.raises(driver.DriverError, match="function identity"):
            driver._verify_imports()


def test_driver_inventory_includes_driver_probe_freeze_and_all_helpers(monkeypatch):
    current = {relative: ("SYNTHETIC_BYTES:" + relative).encode() for relative in driver.SOURCE_PATHS}
    monkeypatch.setattr(probe, "FREEZE_SHA256", probe._digest(current[probe.FREEZE_RELATIVE]))
    monkeypatch.setattr(driver, "_git_head", lambda: "c" * 40)
    monkeypatch.setattr(probe, "_read_source", lambda relative: current[relative])
    def committed(command, **kwargs):
        assert command[:2] == ["git", "show"]
        relative = command[2].split(":", 1)[1]
        return SimpleNamespace(stdout=current[relative])
    monkeypatch.setattr(driver.subprocess, "run", committed)
    inventory = driver._bound_inventory("c" * 40)
    assert set(inventory) == set(driver.SOURCE_PATHS)
    assert len(inventory) == 7
    monkeypatch.setattr(driver.subprocess, "run", lambda *_a, **_k: SimpleNamespace(stdout=b"OLD_SOURCE"))
    with pytest.raises(driver.DriverError, match="committed sources"):
        driver._bound_inventory("c" * 40)


def test_driver_inventory_detects_mid_verification_head_change(monkeypatch):
    monkeypatch.setattr(driver, "_git_head", lambda: "e" * 40)
    with pytest.raises(driver.DriverError, match="advanced"):
        driver._bound_inventory("c" * 40)


@pytest.mark.parametrize("change", [{"sampled_rows": True}, {"sampled_rows": 8},
    {"attempted_requests": -1}, {"response_bytes": 7 * 65536 + 1},
    {"scope_spent": False}, {"point_in_time_data": True}, {"full_capture_admitted": True},
    {"development_looks": 1}, {"all_requests_succeeded": False}, {"reserved_requests": True},
    {"successful_sample_responses": 6}, {"interrupted": "false"}])
def test_driver_closed_result_counts_and_authority_refuse(change):
    with pytest.raises(driver.DriverError):
        driver._safe_result(safe_report(**change))


def test_driver_unknown_fields_never_enter_public_summary():
    public = driver._safe_result(safe_report(unknown_secret="SYNTHETIC_CREDENTIAL"))
    assert set(public) == driver.PUBLIC_KEYS
    assert "SYNTHETIC_CREDENTIAL" not in json.dumps(public)


def test_driver_cli_requires_exact_arguments_and_prints_closed_refusal(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(driver, "run_probe", lambda **_args: called.append(True))
    assert driver.main(["--credential", "SYNTHETIC_PRIVATE_VALUE"]) == 1
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "REFUSED" and public["scope_spent"] is None
    assert public["attempted_requests"] is None
    assert public["preparation_may_exist"] is True
    assert "SYNTHETIC_PRIVATE_VALUE" not in json.dumps(public)
    assert set(public) == driver.PUBLIC_KEYS and called == []


def test_driver_cli_actual_prepare_path_is_explicit_and_closed(monkeypatch, tmp_path, capsys):
    _, _, calls = install_driver_stubs(monkeypatch, tmp_path)
    args = ["--owner-instruction-sha256", "d" * 64,
            "--created-utc", "2026-10-10T17:00:00Z", "--expires-utc", "2026-10-12T17:00:00Z"]
    assert driver.main(args) == 0
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "COMPLETED" and len(calls) == 1
    assert set(public) == driver.PUBLIC_KEYS
    assert driver.main(args) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == "REFUSED" and refused["attempted_requests"] is None


def test_driver_public_entry_has_no_alternate_root_or_adapters():
    with pytest.raises(TypeError):
        driver.run_probe(**driver_args(), private_root=Path("/tmp/unrelated"))
    with pytest.raises(TypeError):
        driver.run_probe(**driver_args(), credential_resolver=lambda _: SECRET)


def test_copied_globals_cannot_escape_synthetic_root_firewall(monkeypatch, tmp_path, no_external_access):
    """Reproduce the incident's stale-global shape, refusing before any mkdir."""
    import ast
    import inspect
    namespace = dict(driver.__dict__)
    source = ast.parse(inspect.getsource(driver._create_private_directory))
    exec(compile(source, "<synthetic-copied-globals-firewall-proof>", "exec"), namespace)
    copied = namespace["_create_private_directory"]
    install_driver_stubs(monkeypatch, tmp_path)
    with pytest.raises(pytest.fail.Exception, match="actual physical lane"):
        copied()
    assert no_external_access["blocked"] == ["physical-lane-directory"]
    assert not (tmp_path / "artifacts").exists()


def test_real_resolver_and_transport_seams_are_forbidden(no_external_access):
    for function, args in ((probe.helper._production_credential, ("massive",)),
                           (probe._https_get, (probe.QUERIES[0], SECRET)),
                           (probe.http.client.HTTPSConnection, ("api.massive.com",))):
        with pytest.raises(pytest.fail.Exception, match="real credential or HTTPS"):
            function(*args)
    assert no_external_access["blocked"] == ["external-operation"] * 3
