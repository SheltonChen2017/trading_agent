"""Invented native-schema source fixtures; no actual rows/credentials/requests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import csv
import json
import socket
import stat

import pytest

from research.target_price_revisions_development import raw_sharadar_source as source

NOW = datetime(2026, 10, 7, 18, tzinfo=timezone.utc)
KEY = "SYNTHETIC_SHARADAR_RAW_SOURCE_KEY"
TICKER = {"ticker": "SYNTH", "permaticker": "123", "figi": "BBG000000001",
    "category": "Domestic Common Stock", "exchange": "NASDAQ", "isdelisted": "N"}
ACTION = {"ticker": "SYNTH", "date": "2025-02-03", "action": "dividend",
    "contraticker": ""}


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual source credential/socket operation in synthetic fixtures")
    monkeypatch.setattr(source, "_production_credential", forbidden)
    monkeypatch.setattr(source, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def plan(mode="offline-fixture", **changes):
    values = dict(code_sha256="1" * 64, git_sha="2" * 40,
        owner_instruction_sha256="3" * 64, created_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode=mode)
    values.update(changes)
    return source.freeze_capture_plan(**values)


def csv_bytes(dataset, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=source.FIELDS[dataset])
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def response(dataset, rows):
    payload = csv_bytes(dataset, rows)
    return source.CaptureResponse(200, (("content-type", "text/csv"),
        ("content-length", str(len(payload)))), payload)


@pytest.fixture
def private_root(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    return root


def execute(root, *, frozen=None, resolver=None, transport=None):
    return source.execute_capture(frozen or plan(), root, now=NOW,
        credential_resolver=resolver or (lambda _provider: KEY),
        transport=transport or (lambda dataset, _page, _key, _budget:
            response(dataset, [TICKER] if dataset == "tickers" else [ACTION])))


def test_complete_capture_retains_private_native_fields_not_public_values(private_root, capsys):
    result = execute(private_root)
    report = json.loads(result.payload)
    assert report["status"] == "COMPLETED"
    assert report["row_counts"] == {"tickers": 1, "actions": 1}
    assert report["provider_requests"] == 0 and report["fixture_transport_calls"] == 2
    assert report["in_window_action_kind_counts"]["dividend"] == 1
    assert report["pagination_terminated"] is True
    assert report["point_in_time_identity"] is report["real_backtest_ready"] is False
    assert report["canonical_admission"] is report["trading"] is False
    assert report["outcome_reads"] == report["development_looks"] == report["quantconnect_attempts"] == 0
    native = json.loads(result.source_path.read_bytes())
    assert native["tickers"] == [TICKER] and native["actions"] == [ACTION]
    assert native["transactional_snapshot"] is native["history_versions_complete"] is False
    assert native["pages"]["tickers"][0]["sha256"] == hashlib.sha256(csv_bytes("tickers", [TICKER])).hexdigest()
    assert result.aggregate_path.read_bytes() == result.payload
    assert json.loads(result.terminal_path.read_bytes())["source_sha256"] == report["source_sha256"]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in private_root.iterdir())
    assert KEY.encode() not in b"".join(path.read_bytes() for path in private_root.iterdir())
    assert all(value.encode() not in result.payload for value in ("SYNTH", "BBG000000001"))
    assert capsys.readouterr() == ("", "")


def test_claim_precedes_credential_and_changed_plan_cannot_renew(private_root):
    def resolver(provider):
        assert provider == "sharadar"
        assert (private_root / (source.CAPTURE_ID + ".spent.json")).is_file()
        return KEY
    execute(private_root, resolver=resolver)
    with pytest.raises(source.SharadarSourceError, match="already spent"):
        execute(private_root, frozen=plan(code_sha256="a" * 64), resolver=lambda _:
            pytest.fail("second credential resolution"))


@pytest.mark.parametrize("changes", [{"code_sha256": True}, {"git_sha": "a" * 39},
    {"owner_instruction_sha256": None}, {"mode": True}, {"mode": "unknown"},
    {"expires_utc": NOW.isoformat()}, {"expires_utc": (NOW + timedelta(hours=49)).isoformat()}])
def test_invalid_plan_refuses(changes):
    with pytest.raises(source.SourceAuditError):
        plan(**changes)


@pytest.mark.parametrize("mutate", [lambda b: b.update(extra=True),
    lambda b: b["queries"]["actions"].update(to="2027-10-01"),
    lambda b: b["limits"].update(retries=1), lambda b: b.update(outcomes=True),
    lambda b: b.update(d0_renewed=True)])
def test_rehashed_policy_mutation_refuses_before_claim(private_root, mutate):
    frozen = plan()
    body = frozen.body()
    mutate(body)
    payload = source._canonical(body)
    forged = replace(frozen, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(source.SourceAuditError):
        execute(private_root, frozen=forged)
    assert list(private_root.iterdir()) == []


def test_fixed_queries_scope_pages_and_fields():
    body = plan().body()
    assert body["queries"]["tickers"]["table"] == "stocks"
    assert body["queries"]["actions"]["from"] == "2024-08-01"
    assert body["queries"]["actions"]["to"] == "2025-03-31"
    assert dict(source.request_query("actions", 2))["skip"] == "20000"
    assert body["limits"]["requests"] == 20
    assert body["rights"] == "owner-assumed-personal-local-not-vendor-attested"
    for dataset, page in [("sep", 0), ("actions", True), ("actions", -1), ("tickers", 10)]:
        with pytest.raises(source.SharadarSourceError):
            source.request_query(dataset, page)


def test_full_page_follows_fixed_offset_not_provider_url(private_root):
    calls = []
    def fetch(dataset, page, credential, budget):
        calls.append((dataset, page, credential, budget))
        if dataset == "tickers":
            return response(dataset, [TICKER] * 10000 if page == 0 else [])
        return response(dataset, [])
    report = json.loads(execute(private_root, transport=fetch).payload)
    assert report["status"] == "COMPLETED"
    assert [(d, p) for d, p, _, _ in calls] == [("tickers", 0), ("tickers", 1), ("actions", 0)]
    assert report["row_counts"]["tickers"] == 10000


def test_repeated_full_page_is_not_complete(private_root):
    report = json.loads(execute(private_root, transport=lambda dataset, *_:
        response(dataset, [TICKER] * 10000)).payload)
    assert report["status"] == "FAILED" and report["pagination_terminated"] is False
    assert report["source_sha256"] is None and report["fixture_transport_calls"] == 2
    assert (private_root / (source.CAPTURE_ID + ".terminal.json")).exists()


def test_page_ceiling_refuses_no_retry(private_root):
    def fetch(dataset, page, *_args):
        return response(dataset, [dict(TICKER, permaticker=str(page + 1))] * 10000)
    report = json.loads(execute(private_root, transport=fetch).payload)
    assert report["status"] == "FAILED" and report["fixture_transport_calls"] == 10
    assert report["pagination_terminated"] is False


@pytest.mark.parametrize("bad", [source.CaptureResponse(302, (("location", "PRIVATE"),), b"PRIVATE"),
    source.CaptureResponse(200, (("content-type", "application/json"),), b'{"PRIVATE":"value"}'),
    source.CaptureResponse(200, (("content-type", "text/csv"), ("content-encoding", "gzip")), b"PRIVATE"),
    source.CaptureResponse(200, (("content-type", "text/csv"),), b"PRIVATE", False),
    source.CaptureResponse(200, (("content-type", "text/csv"), ("content-length", "100")), b"PRIVATE"),
    source.CaptureResponse(200, (("content-type", "text/csv"), ("Content-Type", "text/csv")), b"PRIVATE"),
    source.CaptureResponse(True, (("content-type", "text/csv"),), b"PRIVATE")])
def test_response_refusals_are_terminal_without_body_retention(private_root, bad):
    result = execute(private_root, transport=lambda *_: bad)
    assert json.loads(result.payload)["status"] == "FAILED"
    assert result.source_path is None
    assert all(b"PRIVATE" not in path.read_bytes() for path in private_root.iterdir())


def test_credential_echo_is_not_retained(private_root):
    result = execute(private_root, transport=lambda dataset, *_:
        response(dataset, [dict(TICKER, category=KEY)]))
    assert json.loads(result.payload)["status"] == "FAILED"
    assert all(KEY.encode() not in path.read_bytes() for path in private_root.iterdir())


def test_provider_exception_values_never_reach_report(private_root):
    def bad(*_args):
        raise RuntimeError("SECRET_" + KEY)
    result = execute(private_root, transport=bad)
    assert json.loads(result.payload)["failure"] == "capture_failed"
    assert all(b"SECRET_" not in path.read_bytes() for path in private_root.iterdir())


def test_invalid_credential_spends_scope_without_request(private_root):
    report = json.loads(execute(private_root, resolver=lambda _: "NOT_REAL",
        transport=lambda *_: pytest.fail("non-synthetic credentials requested")).payload)
    assert report["status"] == "FAILED" and report["fixture_transport_calls"] == 0


def test_interrupt_retains_terminal(private_root):
    def interrupted(*_args):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt, match="scope remains spent"):
        execute(private_root, transport=interrupted)
    assert json.loads((private_root / (source.CAPTURE_ID + ".terminal.json")).read_bytes())["status"] == "INTERRUPTED"


@pytest.mark.parametrize("dataset,payload", [("tickers", b'{"files":[]}'),
    ("tickers", b"ticker,ticker,permaticker,figi,category,exchange,isdelisted\n"),
    ("actions", b"ticker,date,action,contraticker,unknown\n"),
    ("tickers", csv_bytes("tickers", [dict(TICKER, permaticker="NaN")])),
    ("tickers", csv_bytes("tickers", [dict(TICKER, isdelisted="unknown")])),
    ("actions", csv_bytes("actions", [dict(ACTION, date="2025-02-30")])),
    ("actions", csv_bytes("actions", [dict(ACTION, date="2027-01-02")])),
    ("actions", csv_bytes("actions", [dict(ACTION, action="bad\ncell")])),
    ("actions", csv_bytes("actions", [dict(ACTION, ticker="SECRET?key")])),
    ("actions", b"ticker,date,action,contraticker\nSYNTH,2025-01-01,split\n")])
def test_invalid_csv_refuses(dataset, payload):
    with pytest.raises(source.SharadarSourceError, match="CSV"):
        source.parse_source_csv(payload, dataset)


def test_unknown_kind_is_private_and_aggregate_other(private_root):
    result = execute(private_root, transport=lambda dataset, *_:
        response(dataset, [TICKER] if dataset == "tickers" else [dict(ACTION, action="SOURCE_PRIVATE_KIND")]))
    report = json.loads(result.payload)
    assert report["action_kind_counts"]["other"] == 1
    assert b"SOURCE_PRIVATE_KIND" not in result.payload
    assert json.loads(result.source_path.read_bytes())["actions"][0]["action"] == "SOURCE_PRIVATE_KIND"


def test_missing_source_classification_values_retained_for_later_adjudication(private_root):
    native = dict(TICKER, figi="", category="", exchange="")
    result = execute(private_root, transport=lambda dataset, *_:
        response(dataset, [native] if dataset == "tickers" else []))
    report = json.loads(result.payload)
    assert report["status"] == "COMPLETED"
    assert report["source_caveats"]["missing_identity_fields"] == {"figi": 1, "category": 1, "exchange": 1}
    assert json.loads(result.source_path.read_bytes())["tickers"] == [native]


def test_duplicate_and_conflicting_projected_keys_are_not_silently_deduped(private_root):
    rows = [TICKER, TICKER, dict(TICKER, category="Other Common Stock")]
    result = execute(private_root, transport=lambda dataset, *_:
        response(dataset, rows if dataset == "tickers" else [ACTION, ACTION]))
    report = json.loads(result.payload)
    caveats = report["source_caveats"]
    assert caveats["duplicate_projected_rows"] == {"tickers": 1, "actions": 1}
    assert caveats["conflicting_projected_keys"] == {"tickers": 1, "actions": 0}
    assert caveats["rows_deduplicated"] is False
    assert caveats["native_action_key_unique_proven"] is False
    assert caveats["offset_pagination_stability_proven"] is caveats["global_source_completeness_proven"] is False
    assert len(json.loads(result.source_path.read_bytes())["tickers"]) == 3


@pytest.mark.parametrize("spell", [lambda key: key.replace("_", "%5f"),
    lambda key: key.replace("_", "&#95;"), lambda key: key.replace("_", "\\u005f")])
def test_escaped_credential_echo_not_retained(private_root, spell):
    result = execute(private_root, transport=lambda dataset, *_:
        response(dataset, [dict(TICKER, category=spell(KEY))]))
    assert json.loads(result.payload)["failure_stage"] == "response"
    assert not list(private_root.glob("*.csv"))


def test_schema_failure_preserves_private_source_evidence_before_offline_repair(private_root):
    raw = b"ticker,permaticker,figi,category,exchange,isdelisted,new_source_column\r\nSYNTH,123,BBG000000001,Domestic Common Stock,NASDAQ,N,PRIVATE_VALUE\r\n"
    result = execute(private_root, transport=lambda *_:
        source.CaptureResponse(200, (("content-type", "text/csv"),), raw))
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "csv_schema"
    assert report["csv_schema_failures"] == 1 and report["last_http_status"] == 200
    assert report["pagination_terminated"] is False and result.source_path is None
    assert (private_root / "tickers.000.csv").read_bytes() == raw
    assert b"PRIVATE_VALUE" not in result.payload


def test_partial_claim_failure_keeps_scope_spent_and_terminal(private_root, monkeypatch):
    def bad_write(fd, _payload):
        source.os.write(fd, b"{")
        raise OSError("PRIVATE_CREDENTIAL_" + KEY)
    monkeypatch.setattr(source, "_write_fd", bad_write)
    result = execute(private_root, resolver=lambda _: pytest.fail("credential after failed claim"))
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "claim"
    assert report["fixture_transport_calls"] == 0 and report["outcome_reads"] == 0
    assert (private_root / (source.CAPTURE_ID + ".spent.json")).read_bytes() == b"{"
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_owned_https_transport_fixed_host_no_redirect_or_body_read(monkeypatch):
    calls = []
    class Reply:
        status = 302
        def getheaders(self):
            return [("content-type", "text/csv")]
        def read(self, _budget):
            pytest.fail("redirect body was read")
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            calls.append((host, port, timeout, context.keylog_filename))
        def set_debuglevel(self, value):
            assert value == 0
        def request(self, method, path, headers):
            assert method == "GET" and path.startswith("/v1.0/data/tickers?")
            assert "table=stocks" in path and "api_key=" + KEY in path
            assert headers["Accept-Encoding"] == "identity"
        def getresponse(self):
            return Reply()
        def close(self):
            calls.append("closed")
    monkeypatch.setattr(source.http.client, "HTTPSConnection", Connection)
    result = source._FIXED_TRANSPORT("tickers", 0, KEY, 1024)
    assert result.status == 302 and result.body == b"" and result.complete is False
    assert calls == [("api.sharadar.com", 443, 30, None), "closed"]


def test_native_http_refusal_code_is_diagnostic_not_raw_body(private_root):
    result = execute(private_root, transport=lambda *_:
        source.CaptureResponse(401, (("content-type", "application/json"),), b"", False))
    report = json.loads(result.payload)
    assert report["last_http_status"] == 401 and report["failure_stage"] == "response"
    assert report["fixture_transport_calls"] == 1 and not list(private_root.glob("*.csv"))


def test_source_scope_never_requests_action_cash_or_terminal_payoffs():
    body = plan().body()
    assert body["queries"]["actions"]["fields"] == "ticker,date,action,contraticker"
    assert body["action_cash_or_terminal_payoff_fields"] is False
    assert "value" not in source.FIELDS["actions"]


def test_remaining_response_budget_prevents_sentinel_byte_overread(monkeypatch):
    reads = []
    class Reply:
        status = 200
        def getheaders(self):
            return [("content-type", "text/csv"), ("content-length", "20")]
        def read(self, _budget):
            pytest.fail("oversized declared response was read")
    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass
        def set_debuglevel(self, _value):
            pass
        def request(self, *_args, **_kwargs):
            pass
        def getresponse(self):
            return Reply()
        def close(self):
            reads.append("closed")
    monkeypatch.setattr(source.http.client, "HTTPSConnection", Connection)
    result = source._FIXED_TRANSPORT("actions", 0, KEY, 10)
    assert result.status == 200 and result.body == b"" and result.complete is False
    assert reads == ["closed"]


def test_pre_window_and_study_action_counts_differ(private_root):
    result = execute(private_root, transport=lambda dataset, *_:
        response(dataset, [TICKER] if dataset == "tickers" else [ACTION, dict(ACTION, date="2024-09-01")]))
    report = json.loads(result.payload)
    assert report["action_kind_counts"]["dividend"] == 2
    assert report["in_window_action_kind_counts"]["dividend"] == 1


@pytest.mark.parametrize("mode", ["production", "offline-fixture"])
def test_mode_and_root_refuse_cross_route_before_claim(private_root, monkeypatch, mode):
    monkeypatch.setattr(source, "_verify_identity", lambda _: None)
    if mode == "production":
        with pytest.raises(source.SharadarSourceError, match="injected"):
            execute(private_root, frozen=plan(mode))
    else:
        with pytest.raises(source.SharadarSourceError, match="root"):
            execute(source.PRIVATE_ROOT)
    assert list(private_root.iterdir()) == []


def test_symlink_or_world_accessible_root_refuses(private_root):
    private_root.chmod(0o755)
    with pytest.raises(source.SharadarSourceError, match="custody"):
        execute(private_root)
    private_root.chmod(0o700)
    alias = private_root.parent / "alias"
    alias.symlink_to(private_root, target_is_directory=True)
    with pytest.raises(source.SharadarSourceError, match="root"):
        execute(alias)


def test_expired_plan_does_not_claim(private_root):
    with pytest.raises(source.SharadarSourceError, match="expired"):
        source.execute_capture(plan(), private_root, now=NOW + timedelta(days=2),
            credential_resolver=lambda _: KEY, transport=lambda *_: pytest.fail("request"))
    assert list(private_root.iterdir()) == []


def test_no_later_page_starts_after_frozen_expiry(private_root, monkeypatch):
    clocks = iter((NOW, NOW, NOW, NOW + timedelta(days=2)))
    monkeypatch.setattr(source, "_now", lambda: next(clocks))
    calls = []
    def fetch(dataset, page, *_args):
        calls.append((dataset, page))
        return response(dataset, [TICKER] * 10000)
    result = source.execute_capture(plan(), private_root,
        credential_resolver=lambda _: KEY, transport=fetch)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "expiry"
    assert calls == [("tickers", 0)]
    assert report["fixture_transport_calls"] == 1
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_claim_delay_past_expiry_never_resolves_credentials(private_root, monkeypatch):
    clocks = iter((NOW, NOW + timedelta(days=2)))
    monkeypatch.setattr(source, "_now", lambda: next(clocks))
    result = source.execute_capture(plan(), private_root,
        credential_resolver=lambda _: pytest.fail("credential resolution after expired claim"),
        transport=lambda *_: pytest.fail("request after expired claim"))
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "expiry"
    assert report["fixture_transport_calls"] == 0
