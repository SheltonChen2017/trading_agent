"""Synthetic-only focused capture/driver tests with an always-on real-I/O firewall."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlencode

import pytest

from research.target_price_revisions_qc import extended_source_capture as capture
from research.target_price_revisions_qc import extended_source_capture_driver as driver

ACTUAL_LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
ORIGINAL_OPEN = capture._open_directory
ORIGINAL_READ = capture._read_source
ORIGINAL_TRANSPORT = capture._https_get
ORIGINAL_CREDENTIAL = capture.helper._production_credential
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
OWNER = "b" * 64
PIN = "c" * 40
TOKEN = "SYNTHETIC_MASSIVE_SECRET_123"
SHARADAR_TOKEN = "SYNTHETIC_SHARADAR_SECRET_456"
CREATED, EXPIRES = "2026-10-10T00:00:00+00:00", "2026-10-11T00:00:00+00:00"


@pytest.fixture(autouse=True)
def real_io_firewall(monkeypatch):
    """Hard literal root does not drift with patched/copy-globals mutants."""
    def guarded_open(path):
        selected = Path(path)
        if selected == ACTUAL_LANE_ROOT or selected.is_relative_to(ACTUAL_LANE_ROOT):
            pytest.fail("real lane/private directory access forbidden in fixtures")
        return ORIGINAL_OPEN(selected)
    def forbidden(*_args, **_kwargs):
        pytest.fail("real credential/provider transport forbidden in fixtures")
    monkeypatch.setattr(capture, "_open_directory", guarded_open)
    monkeypatch.setattr(capture.probe, "_open_directory", guarded_open)
    monkeypatch.setattr(capture.helper, "_production_credential", forbidden)
    monkeypatch.setattr(capture, "_https_get", forbidden)
    monkeypatch.setattr(capture.probe, "_https_get", forbidden)
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", forbidden)
    return guarded_open, forbidden


def source_hashes():
    return {key: capture.PUBLIC_HASHES.get(key, "a" * 64) for key in capture.SOURCE_PATHS}


def plan(**changes):
    arguments = dict(source_hashes=source_hashes(), git_sha=PIN,
        owner_instruction_sha256=OWNER, created_utc=CREATED, expires_utc=EXPIRES, mode="offline-fixture")
    arguments.update(changes)
    return capture.freeze_capture_plan(**arguments)


@pytest.fixture
def private_root(tmp_path):
    root = tmp_path / "synthetic_capture"
    root.mkdir(mode=0o700)
    return root


def revision(window, **changes):
    row = {"benzinga_id": "EVENT-" + window[0], "benzinga_firm_id": "FIRM-1", "ticker": "ABC",
           "date": window[0], "last_updated": window[0] + "T12:00:00Z", "currency": "USD",
           "price_target_action": "raises", "price_target": "101.0000000000000000001",
           "previous_price_target": "100.0000000000000000000"}
    row.update(changes)
    return row


def json_response(rows, *, status=200, next_url=None, api_status="OK"):
    body = {"status": api_status, "results": rows}
    if next_url is not None:
        body["next_url"] = next_url
    payload = capture._canonical(body)
    return capture.CaptureResponse(status, (("content-type", "application/json"),
        ("content-length", str(len(payload)))), payload)


def csv_response(dataset, rows=None, **changes):
    headers = {"tickers": "ticker,permaticker,figi,category,exchange,isdelisted\n",
               "actions": "ticker,date,action,contraticker\n"}
    defaults = {"tickers": "ABC,1,,Domestic Common Stock,NASDAQ,N\n",
                "actions": "ABC,1999-01-02,split,\n"}
    payload = (headers[dataset] + (defaults[dataset] if rows is None else rows)).encode()
    response = capture.CaptureResponse(200, (("content-type", "text/csv"),
        ("content-length", str(len(payload)))), payload)
    return replace(response, **changes)


def default_transport(provider, dataset, query, credential, seconds):
    assert credential.startswith("SYNTHETIC_")
    assert 0 < seconds <= 30
    if provider == "massive":
        values = dict(query)
        window = values["date.gte"], values["date.lte"]
        return json_response([revision(window)])
    return csv_response(dataset)


def execute(root, *, selected=None, resolver=None, transport=None, now=NOW, monotonic=lambda: 0.0):
    return capture._execute_fixture_capture(selected or plan(), root, now=now,
        credential_resolver=resolver or (lambda provider: TOKEN if provider == "massive" else SHARADAR_TOKEN),
        transport=transport or default_transport, monotonic=monotonic)


def report(result):
    return json.loads(result.payload)


def index(root):
    return json.loads((root / capture.INDEX_NAME).read_bytes())


def test_exact_frozen_dimensions():
    body = plan().body()
    assert len(capture.WINDOWS) == 74
    assert capture.WINDOWS[0] == ("2020-09-01", "2020-09-30")
    assert capture.WINDOWS[-1] == ("2026-10-01", "2026-10-09")
    assert ("2024-02-01", "2024-02-29") in capture.WINDOWS
    assert body["scope"]["limits"] == capture.LIMITS
    assert len(body["source_hashes"]) == 11
    assert capture.DRIVER_RELATIVE in body["source_hashes"]
    assert body["point_in_time_data"] is False
    assert body["old_receipts_renewed"] is False


@pytest.mark.parametrize("change", [
    {"source_hashes": {}}, {"git_sha": "X" * 40}, {"owner_instruction_sha256": "Z" * 64},
    {"mode": "fixture"}, {"expires_utc": CREATED}, {"expires_utc": "2026-10-13T00:00:00Z"},
    {"created_utc": "2026-10-10T00:00:00"}, {"source_hashes": {**source_hashes(), "extra": "a" * 64}},
    {"source_hashes": {**source_hashes(), next(iter(capture.PUBLIC_HASHES)): "e" * 64}},
])
def test_bad_plan_rejected(change):
    with pytest.raises(ValueError):
        plan(**change)


@pytest.mark.parametrize("key,value", [("private_root", "/tmp/elsewhere"), ("lane_branch", "main"),
    ("outcome_access", True), ("quantconnect", True), ("original_wire_retention_private", False)])
def test_rehashed_widened_plan_refused(key, value):
    body = plan().body()
    body[key] = value
    payload = capture._canonical(body)
    with pytest.raises(capture.CaptureError):
        capture.CapturePlan(payload, capture.probe._digest(payload)).body()


def test_payload_tamper_refused():
    selected = plan()
    with pytest.raises(capture.CaptureError):
        replace(selected, payload=selected.payload + b" ").body()


def test_fixture_never_accepts_real_adapters(private_root):
    for resolver, transport in ((ORIGINAL_CREDENTIAL, default_transport),
                               (lambda _: TOKEN, ORIGINAL_TRANSPORT)):
        with pytest.raises(capture.CaptureError):
            execute(private_root, resolver=resolver, transport=transport)
    assert not list(private_root.iterdir())


def test_fixture_real_directory_refused_before_open():
    with pytest.raises(capture.CaptureError):
        execute(capture.PRIVATE_ROOT)


def test_global_and_each_claim_before_credentials_and_request(private_root):
    credentials_seen = []
    requests = []
    def resolver(provider):
        assert (private_root / (capture.OPERATION_ID + ".access.spent.json")).is_file()
        expected = 1 if provider == "massive" else 75
        assert (private_root / f"request.{expected:04}.spent.json").is_file()
        credentials_seen.append(provider)
        return TOKEN if provider == "massive" else SHARADAR_TOKEN
    def transport(provider, dataset, query, credential, seconds):
        requests.append((provider, dataset, query))
        assert (private_root / f"request.{len(requests):04}.spent.json").is_file()
        return default_transport(provider, dataset, query, credential, seconds)
    result = execute(private_root, resolver=resolver, transport=transport)
    outcome = report(result)
    assert outcome["status"] == "COMPLETED"
    assert outcome["capture_complete"] is True
    assert outcome["source_input_admitted"] is False
    assert outcome["reserved_requests"] == outcome["attempted_requests"] == 76
    assert outcome["source_rows"] == 76
    assert credentials_seen == ["massive", "sharadar"]
    assert set(outcome) == capture.PUBLIC_KEYS
    for position, window in enumerate(capture.WINDOWS):
        assert requests[position] == ("massive", "ratings", capture._massive_query(window))
    assert dict(requests[-1][2])["to"] == "2026-10-09"
    assert "from" not in dict(requests[-1][2])
    retained = index(private_root)
    assert len(retained["census"]) == 76
    assert all(row["terminated"] for row in retained["census"])
    assert retained["action_history_no_lower_bound"] is True
    for page in retained["pages"]:
        for prefix in ("wire", "projection"):
            payload = (private_root / page[prefix + "_file"]).read_bytes()
            assert len(payload) == page[prefix + "_bytes"]
            assert capture.probe._digest(payload) == page[prefix + "_sha256"]
    first = json.loads((private_root / retained["pages"][0]["projection_file"]).read_bytes())
    assert first["rows"][0]["source"]["price_target"] == "101.0000000000000000001"
    last = json.loads((private_root / retained["pages"][-1]["projection_file"]).read_bytes())
    assert last["rows"][0]["source"]["date"] == "1999-01-02"
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in private_root.iterdir())
    assert TOKEN not in result.payload.decode() and "ABC" not in result.payload.decode()


def test_second_run_refused_before_credentials(private_root):
    execute(private_root)
    def forbidden(_):
        pytest.fail("spent capture resolved credentials again")
    with pytest.raises(capture.CaptureError):
        execute(private_root, resolver=forbidden)


def test_credential_failure_preserves_spent_unknown_zero_http(private_root):
    result = execute(private_root, resolver=lambda _: None)
    outcome = report(result)
    assert outcome["status"] == "FAILED"
    assert outcome["reserved_requests"] == 1 and outcome["attempted_requests"] == 0
    assert len(index(private_root)["census"]) == 76
    assert index(private_root)["pages"][0]["disposition"] == "refused_unknown_spent"
    assert (private_root / "request.0001.spent.json").exists()


@pytest.mark.parametrize("now", [datetime(2026, 10, 9, tzinfo=timezone.utc),
    datetime(2026, 10, 11, tzinfo=timezone.utc), datetime(2026, 10, 10)])
def test_expired_or_invalid_clock_before_claim(private_root, now):
    with pytest.raises(capture.CaptureError):
        execute(private_root, now=now)
    assert not list(private_root.iterdir())


def test_late_credential_does_not_extend_wall_budget(private_root):
    ticks = iter((0.0, 0.0, 5400.1))
    def forbidden(*_args):
        pytest.fail("transport launched after credential consumed wall budget")
    result = execute(private_root, transport=forbidden, monotonic=lambda: next(ticks))
    assert report(result)["attempted_requests"] == 0
    assert report(result)["reserved_requests"] == 1


@pytest.mark.parametrize("response", [
    replace(json_response([]), status=302), replace(json_response([]), status=403),
    replace(json_response([]), complete=False),
    replace(json_response([]), headers=(("content-encoding", "gzip"),)),
    replace(json_response([]), headers=(("content-length", "10"), ("content-length", "11"))),
    replace(json_response([]), headers=(("content-length", "-1"),)),
    replace(json_response([]), headers=(("content-type", "text/html"),)),
    json_response([], api_status="UNKNOWN"),
    capture.CaptureResponse(200, (), b'{"status":"OK","status":"OK","results":[]}'),
    capture.CaptureResponse(200, (), b'{"status":"OK","results":[],"n":NaN}'),
    capture.CaptureResponse(200, (), b"{"),
])
def test_failed_and_unknown_responses_spent_not_retried(private_root, response):
    called = []
    def transport(*_args):
        called.append(True)
        return response
    result = execute(private_root, transport=transport)
    assert report(result)["status"] == "FAILED"
    assert report(result)["capture_complete"] is False
    assert len(called) == 1
    assert (private_root / "request.0001.terminal.json").exists()
    assert not any(row["terminated"] for row in index(private_root)["census"])


@pytest.mark.parametrize("encoded", [TOKEN, quote(TOKEN, safe=""),
    "".join("\\u%04x" % ord(c) for c in TOKEN),
    "".join("&#%d;" % ord(c) for c in TOKEN),
    "".join("%%%02x" % ord(c) for c in TOKEN)])
def test_credential_echo_refused_before_wire_hash_or_write(private_root, encoded):
    body = ('{"status":"OK","results":[],"extra":"' + encoded + '"}').encode()
    result = execute(private_root, transport=lambda *_: capture.CaptureResponse(200, (), body))
    assert report(result)["status"] == "FAILED"
    page = index(private_root)["pages"][0]
    assert page["wire_sha256"] is None
    assert not list(private_root.glob("*.wire.*"))
    assert all(TOKEN.encode() not in path.read_bytes() for path in private_root.iterdir())


def test_deeply_url_escaped_secret_refused_before_persistence(private_root):
    encoded = "".join("%%%02x" % ord(c) for c in TOKEN)
    for _ in range(6):
        encoded = encoded.replace("%", "%25")
    body = ('{"status":"OK","results":[],"extra":"' + encoded + '"}').encode()
    result = execute(private_root, transport=lambda *_: capture.CaptureResponse(200, (), body))
    assert report(result)["status"] == "FAILED"
    assert index(private_root)["pages"][0]["wire_sha256"] is None


@pytest.mark.parametrize("next_url", [
    "http://api.massive.com/benzinga/v1/ratings?cursor=a",
    "https://evil.invalid/benzinga/v1/ratings?cursor=a",
    "https://api.massive.com:443/benzinga/v1/ratings?cursor=a",
    "https://user@api.massive.com/benzinga/v1/ratings?cursor=a",
    "https://api.massive.com/other?cursor=a",
    "https://api.massive.com/benzinga/v1/ratings?cursor=a#x",
    "https://api.massive.com/benzinga/v1/ratings?cursor=a&api_key=secret",
    "https://api.massive.com/benzinga/v1/ratings?cursor=a&date.gte=2019-01-01",
    "https://api.massive.com/benzinga/v1/ratings?cursor=a&sort=date.desc",
    "https://api.massive.com/benzinga/v1/ratings?cursor=a&limit=1001",
    "https://api.massive.com/benzinga/v1/ratings?cursor=a&cursor=b",
    "https://api.massive.com/benzinga/v1/ratings?cursor=",
    "https://api.massive.com/benzinga/v1/ratings?extra=x",
])
def test_changed_or_credentialed_pagination_refused(next_url):
    with pytest.raises(ValueError):
        capture._next_query({"next_url": next_url}, capture.WINDOWS[0])


def test_provider_cursor_rebuilds_entire_fixed_scope():
    window = capture.WINDOWS[0]
    value = "https://api.massive.com/benzinga/v1/ratings?cursor=trusted%2Bcursor%3D"
    assert capture._next_query({"next_url": value}, window) == capture._massive_query(window, "trusted+cursor=")


def test_pagination_cycle_stays_failed(private_root):
    calls = []
    def transport(provider, dataset, query, credential, seconds):
        calls.append(query)
        window = capture.WINDOWS[0]
        return json_response([revision(window, benzinga_id=f"EVENT{len(calls)}")],
            next_url="https://api.massive.com/benzinga/v1/ratings?cursor=one")
    result = execute(private_root, transport=transport)
    assert report(result)["status"] == "FAILED" and len(calls) == 2
    assert report(result)["terminated_massive_windows"] == 0


def test_repeated_wire_stays_failed(private_root):
    response = json_response([], next_url="https://api.massive.com/benzinga/v1/ratings?cursor=one")
    result = execute(private_root, transport=lambda *_: response)
    assert report(result)["status"] == "FAILED"
    assert report(result)["attempted_requests"] == 2


def test_monthly_page_cap_is_not_a_complete_history(private_root):
    calls = []
    def transport(*_args):
        calls.append(True)
        return json_response([], next_url="https://api.massive.com/benzinga/v1/ratings?cursor=page" + str(len(calls)))
    result = execute(private_root, transport=transport)
    assert len(calls) == 64
    assert report(result)["status"] == "FAILED"
    assert report(result)["terminated_massive_windows"] == 0
    assert index(private_root)["census"][0]["pages"] == 64


def test_row_cap_in_json_refuses_1001_rows():
    window = capture.WINDOWS[0]
    with pytest.raises(capture.CaptureError):
        capture._massive_projection(json_response([revision(window)] * 1001).body, window, NOW, {})


def test_row_cap_in_csv_refuses_10001_rows():
    payload = b"ticker,date,action,contraticker\n" + b"ABC,2000-01-01,split,\n" * 10001
    with pytest.raises(capture.CaptureError):
        capture._csv_projection(payload, "actions", {})


def test_unsorted_revisions_refused():
    window = capture.WINDOWS[0]
    with pytest.raises(capture.CaptureError):
        capture._massive_projection(json_response([revision(window, date="2020-09-02"), revision(window)]).body, window, NOW, {})


def test_action_after_endpoint_stops_capture_and_retains_refusal(private_root):
    def transport(provider, dataset, query, credential, seconds):
        if dataset == "actions":
            return csv_response(dataset, "ABC,2026-10-10,split,\n")
        return default_transport(provider, dataset, query, credential, seconds)
    result = execute(private_root, transport=transport)
    assert report(result)["status"] == "FAILED"
    assert report(result)["terminated_sharadar_datasets"] == 1
    assert report(result)["row_refusals"] == 1
    assert index(private_root)["pages"][-1]["projection_file"] is not None


def test_http_failure_safe_wire_preserved_and_received_count_visible(private_root):
    response = json_response([], status=403)
    result = execute(private_root, transport=lambda *_: response)
    page = index(private_root)["pages"][0]
    assert report(result)["status"] == "FAILED"
    assert page["http_status"] == 403
    assert page["received_bytes"] == page["wire_bytes"] == len(response.body)
    assert (private_root / page["wire_file"]).read_bytes() == response.body


@pytest.mark.parametrize("changes", [{"date": "2020-08-31"}, {"date": "2020-10-01"},
    {"date": "2020-09-31"}])
def test_row_outside_month_refused(changes):
    window = capture.WINDOWS[0]
    with pytest.raises(capture.CaptureError):
        capture._massive_projection(json_response([revision(window, **changes)]).body, window, NOW, {})


def test_missing_nonrevision_is_not_denial_or_zero():
    window = capture.WINDOWS[0]
    payload = json_response([revision(window, price_target=None, previous_price_target=None,
        price_target_action="announces")]).body
    projection, _ = capture._massive_projection(payload, window, NOW, {})
    assert projection["row_refusals"] == 0
    assert projection["rows"][0]["nominal_disposition"] == "nominal_pair_unavailable"
    assert projection["rows"][0]["source"]["price_target"] is None


def test_typed_native_ids_and_exact_decimal_lexical_numbers():
    window = capture.WINDOWS[0]
    payload = (b'{"status":"OK","results":[{"date":"2020-09-01","benzinga_id":1,'
        b'"benzinga_firm_id":"1","ticker":"ABC","last_updated":"2020-09-01T12:00:00Z",'
        b'"currency":"USD","price_target_action":"raises","price_target":100.1000,'
        b'"previous_price_target":99.99000000000000001}]}')
    projection, _ = capture._massive_projection(payload, window, NOW, {})
    row = projection["rows"][0]["source"]
    assert type(row["benzinga_id"]) is int and type(row["benzinga_firm_id"]) is str
    assert row["price_target"] == "100.1000"
    assert row["previous_price_target"] == "99.99000000000000001"


@pytest.mark.parametrize("changes", [{"benzinga_id": True}, {"benzinga_firm_id": None},
    {"last_updated": "2020-09-01T12:00:00"}, {"last_updated": "2020-08-01T12:00:00Z"},
    {"last_updated": "2027-01-01T00:00:00Z"}, {"ticker": ""}])
def test_invalid_native_semantics_retained_as_refusals(changes):
    window = capture.WINDOWS[0]
    projection, _ = capture._massive_projection(json_response([revision(window, **changes)]).body, window, NOW, {})
    assert projection["source_rows"] == projection["row_refusals"] == 1
    assert projection["rows"][0]["refusals"]


def test_cross_page_native_duplicate_conflict_visible():
    window, seen = capture.WINDOWS[0], {}
    wire = json_response([revision(window)]).body
    capture._massive_projection(wire, window, NOW, seen)
    duplicate, _ = capture._massive_projection(wire, window, NOW, seen)
    conflict, _ = capture._massive_projection(json_response([revision(window, price_target="150")]).body, window, NOW, seen)
    assert duplicate["identical_duplicate_rows"] == 1
    assert conflict["conflicting_duplicate_rows"] == conflict["row_refusals"] == 1


def test_native_csv_extra_columns_and_missing_optional_not_fabricated():
    payload = b"ticker,permaticker,category,exchange,isdelisted,providerextra\nABC,1,Domestic Common Stock,NASDAQ,N,value\n"
    projection = capture._csv_projection(payload, "tickers", {})
    assert projection["rows"][0]["source"]["figi"] is None
    assert projection["missing_optional_column"] is True
    assert set(projection["rows"][0]["source"]) == set(capture.CSV_FIELDS["tickers"])
    assert projection["current_vintage_not_point_in_time"] is True


def test_pre_warmup_cumulative_actions_retained():
    projection = capture._csv_projection(b"ticker,date,action\nABC,1901-01-02,split\n", "actions", {})
    assert projection["row_refusals"] == 0
    assert projection["rows"][0]["source"]["contraticker"] is None
    assert projection["rows"][0]["source"]["date"] == "1901-01-02"


@pytest.mark.parametrize("payload", [b"ticker,ticker\nABC,ABC\n", b"ticker,date,action\nABC,2026-01-01\n",
    b"ticker,date,action\nABC,2020-01-01,split,extra\n", b"\x00", b"", b"garbage\n"])
def test_bad_csv_structure_refused(payload):
    with pytest.raises(capture.CaptureError):
        capture._csv_projection(payload, "actions", {})


@pytest.mark.parametrize("line", ["ABC,2026-10-10,split,\n", "ABC,not-date,split,\n",
    "ABC,2020-01-01,,\n", "bad symbol,2020-01-01,split,\n"])
def test_bad_action_semantics_not_silently_dropped(line):
    projection = capture._csv_projection(csv_response("actions", line).body, "actions", {})
    assert projection["source_rows"] == projection["row_refusals"] == 1
    assert len(projection["rows"]) == 1


@pytest.mark.parametrize("provider,dataset,query", [
    ("evil", "ratings", capture._massive_query(capture.WINDOWS[0])),
    ("massive", "ratings", (("date.gte", "2010-01-01"),)),
    ("sharadar", "actions", tuple(sorted({**capture.CSV_QUERY["actions"], "skip": "1"}.items()))),
    ("sharadar", "actions", tuple(sorted({**capture.CSV_QUERY["actions"], "skip": "0", "from": "2020-09-01"}.items()))),
    ("sharadar", "actions", tuple(sorted({**capture.CSV_QUERY["actions"], "skip": "1280000"}.items()))),
])
def test_transport_scope_rejects_unfrozen(provider, dataset, query):
    with pytest.raises(capture.CaptureError):
        capture._transport_scope(provider, dataset, query)


def test_wire_cap_boundary_no_sentinel_read(monkeypatch):
    reads, requests = [], []
    class FakeResponse:
        status = 200
        def getheaders(self):
            return [("Content-Type", "application/json")]
        def read(self, maximum):
            reads.append(maximum)
            return b"x" * maximum
        def isclosed(self):
            return False
    class FakeConnection:
        def __init__(self, host, port, **kwargs):
            assert host == "api.massive.com" and port == 443
            assert kwargs["context"].keylog_filename is None
        def set_debuglevel(self, _):
            pass
        def request(self, method, path, headers):
            requests.append((method, path, headers))
        def getresponse(self):
            return FakeResponse()
        def close(self):
            pass
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", FakeConnection)
    response = ORIGINAL_TRANSPORT("massive", "ratings", capture._massive_query(capture.WINDOWS[0]), TOKEN, 0.5)
    assert reads == [2 * 1024**2] and response.complete is False
    assert requests[0][2]["Authorization"] == "Bearer " + TOKEN
    assert TOKEN not in requests[0][1]


def test_declared_oversize_no_read(monkeypatch):
    class FakeResponse:
        status = 200
        def getheaders(self):
            return [("Content-Length", str(capture.MASSIVE_PAGE_BYTES + 1))]
        def read(self, *_):
            pytest.fail("oversized declared body read")
    class FakeConnection:
        def __init__(self, *_a, **_kw):
            pass
        def set_debuglevel(self, *_):
            pass
        def request(self, *_a, **_kw):
            pass
        def getresponse(self):
            return FakeResponse()
        def close(self):
            pass
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", FakeConnection)
    result = ORIGINAL_TRANSPORT("massive", "ratings", capture._massive_query(capture.WINDOWS[0]), TOKEN, 0.5)
    assert result.body == b"" and result.complete is False


def test_capture_custody_hash_mismatch_before_claim(monkeypatch, private_root):
    selected = plan(mode="production")
    calls = []
    monkeypatch.setattr(capture, "_verify_imports", lambda: None)
    monkeypatch.setattr(capture.probe, "_git_identity", lambda body: calls.append("git"))
    monkeypatch.setattr(capture, "_read_source", lambda relative: b"wrong-source")
    with pytest.raises(capture.CaptureError):
        capture.execute_capture(selected)
    assert calls == ["git"] and not list(private_root.iterdir())


def test_production_has_no_fixture_adapters():
    with pytest.raises(TypeError):
        capture.execute_capture(plan(), transport=default_transport)
    with pytest.raises(capture.CaptureError):
        capture.execute_capture(plan())


def test_import_identity_inspection_only_with_original_function_objects(monkeypatch):
    # Temporarily restore identity objects ONLY for a pure identity inspection.
    # No filesystem, credential resolution or transport is invoked here.
    with monkeypatch.context() as identity:
        identity.setattr(capture, "_open_directory", ORIGINAL_OPEN)
        identity.setattr(capture, "_read_source", ORIGINAL_READ)
        identity.setattr(capture.helper, "_production_credential", ORIGINAL_CREDENTIAL)
        identity.setattr(capture, "_https_get", ORIGINAL_TRANSPORT)
        capture._verify_imports()
        driver._verify_imports()


def test_driver_uncommitted_current_source_refused_before_directory(monkeypatch):
    monkeypatch.setattr(driver, "_git_head", lambda: PIN)
    monkeypatch.setattr(capture, "_read_source", lambda _: b"synthetic changed current source")
    monkeypatch.setattr(driver.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(stdout=b"synthetic committed source"))
    with pytest.raises(driver.DriverError):
        driver._bound_inventory(PIN)


def test_driver_mid_verification_head_change_refused(monkeypatch):
    monkeypatch.setattr(driver, "_git_head", lambda: "d" * 40)
    monkeypatch.setattr(capture, "_read_source", lambda _: pytest.fail("source read after HEAD change"))
    with pytest.raises(driver.DriverError):
        driver._bound_inventory(PIN)


def test_all_real_transport_and_credentials_firewalled(real_io_firewall):
    for function, arguments in ((capture._open_directory, (ACTUAL_LANE_ROOT,)),
        (capture.helper._production_credential, ("massive",)), (capture._https_get, ()),
        (capture.http.client.HTTPSConnection, ("api.massive.com",))):
        with pytest.raises(pytest.fail.Exception):
            function(*arguments)


@pytest.fixture
def driver_fixture(tmp_path, monkeypatch):
    lane = tmp_path / "synthetic_lane"
    lane.mkdir(mode=0o700)
    monkeypatch.setattr(driver, "LANE_ROOT", lane)
    monkeypatch.setattr(capture, "LANE_ROOT", lane)
    monkeypatch.setattr(capture, "PRIVATE_ROOT", lane / "artifacts" / "target_price_extended" / capture.STUDY_ID / "source_capture")
    monkeypatch.setattr(driver, "_verify_imports", lambda: None)
    monkeypatch.setattr(driver, "_git_head", lambda: PIN)
    monkeypatch.setattr(driver, "_bound_inventory", lambda _: source_hashes())
    monkeypatch.setattr(driver, "_now", lambda: NOW)
    monkeypatch.setattr(capture, "_verify_execution_identity", lambda _: None)
    return lane


def driver_run():
    return driver.run_capture(owner_instruction_sha256=OWNER, created_utc=CREATED, expires_utc=EXPIRES)


def test_driver_exact_plan_before_invoke(monkeypatch, driver_fixture):
    observed = []
    def fake_execute(selected):
        observed.append(selected)
        root = capture.PRIVATE_ROOT
        assert root.stat().st_mode & 0o777 == 0o700
        assert (root / driver.DRIVER_PLAN_NAME).read_bytes() == selected.payload
        preparation = json.loads((root / driver.DRIVER_RECEIPT_NAME).read_bytes())
        assert preparation["source_hashes"] == selected.body()["source_hashes"]
        assert preparation["status"] == "not_yet_invoked_by_driver"
        assert not (root / (capture.OPERATION_ID + ".access.spent.json")).exists()
        raise capture.CaptureError("synthetic post-preparation refusal")
    monkeypatch.setattr(capture, "execute_capture", fake_execute)
    with pytest.raises(capture.CaptureError):
        driver_run()
    assert len(observed) == 1
    assert len(list(capture.PRIVATE_ROOT.iterdir())) == 2


def test_driver_existing_leaf_refused_without_execution(monkeypatch, driver_fixture):
    root = capture.PRIVATE_ROOT
    root.mkdir(parents=True, mode=0o700)
    for parent in (root.parent, root.parent.parent):
        parent.chmod(0o700)
    monkeypatch.setattr(capture, "execute_capture", lambda *_: pytest.fail("reused prepared root"))
    with pytest.raises(driver.DriverError):
        driver_run()
    assert not list(root.iterdir())


def test_driver_symlink_parent_refused(monkeypatch, driver_fixture, tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    (driver_fixture / "artifacts").symlink_to(target, target_is_directory=True)
    with pytest.raises(driver.DriverError):
        driver_run()
    assert not list(target.iterdir())


def test_driver_root_mismatch_before_preparation(monkeypatch, driver_fixture):
    original_git_head = driver._git_head
    monkeypatch.setattr(driver, "_git_head", lambda: (_ for _ in ()).throw(driver.DriverError("synthetic mismatch")))
    with pytest.raises(driver.DriverError):
        driver_run()
    assert not (driver_fixture / "artifacts").exists()
    monkeypatch.setattr(driver, "_git_head", original_git_head)


def test_driver_clock_rejected_before_preparation(monkeypatch, driver_fixture):
    monkeypatch.setattr(driver, "_now", lambda: datetime(2026, 10, 12, tzinfo=timezone.utc))
    with pytest.raises(driver.DriverError):
        driver_run()
    assert not (driver_fixture / "artifacts").exists()


def test_stale_copied_global_root_refused_before_mkdir(monkeypatch, driver_fixture):
    # Explicit stale-root regression is guarded BEFORE any actual filesystem
    # access. Do not compile a mutant from copied production module globals.
    monkeypatch.setattr(driver, "LANE_ROOT", ACTUAL_LANE_ROOT)
    with pytest.raises(pytest.fail.Exception):
        driver._create_private_directory()
    assert not (driver_fixture / "artifacts").exists()


def test_driver_cli_unknown_status_does_not_invent_no_http(monkeypatch, capsys):
    monkeypatch.setattr(driver, "run_capture", lambda **_: (_ for _ in ()).throw(driver.DriverError("never echo secret")))
    code = driver.main(["--owner-instruction-sha256", OWNER, "--created-utc", CREATED, "--expires-utc", EXPIRES])
    public = json.loads(capsys.readouterr().out)
    assert code == 1 and set(public) == driver.PUBLIC_KEYS
    assert public["scope_spent"] is None and public["attempted_requests"] is None
    assert public["preparation_may_exist"] is True
    assert public["outcome_reads"] == public["quantconnect_attempts"] == 0


def test_driver_public_projection_rejects_added_provider_fields(private_root, monkeypatch):
    result = execute(private_root)
    body = report(result)
    body["ticker"] = "ABC"
    payload = capture._canonical(body)
    altered = capture.CaptureResult(payload, capture.probe._digest(payload), capture.PRIVATE_ROOT / capture.INDEX_NAME)
    with pytest.raises(driver.DriverError):
        driver._safe_result(altered)


def test_driver_public_projection_accepts_only_closed_counts(private_root):
    result = execute(private_root)
    altered = replace(result, index_path=capture.PRIVATE_ROOT / capture.INDEX_NAME)
    projected = driver._safe_result(altered)
    assert set(projected) == driver.PUBLIC_KEYS
    assert projected["capture_complete"] is True and projected["source_input_admitted"] is False
