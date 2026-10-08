"""Synthetic-only proofs for the fresh bounded ratings capture."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import socket
import stat
from types import SimpleNamespace

import pytest

from research.target_price_revisions_development import raw_source_capture as capture
from research.target_price_revisions_development.source_audit import AuditResponse

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
TOKEN = "SYNTHETIC_CAPTURE_TOKEN"


@pytest.fixture(autouse=True)
def no_real_credentials_or_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential or transport used by fixture capture")
    monkeypatch.setattr(capture, "_production_credential", forbidden)
    monkeypatch.setattr(capture, "_https_get", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def root(tmp_path):
    result = tmp_path / "capture"
    result.mkdir(mode=0o700)
    return result


def plan(**changes):
    values = dict(code_sha256="a" * 64, git_sha="b" * 40, owner_instruction_sha256="c" * 64,
                  created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")
    values.update(changes)
    return capture.freeze_capture_plan(**values)


def row(**changes):
    value = {"benzinga_id": "fixture-event", "benzinga_firm_id": 12, "ticker": "ZZTEST",
             "date": "2025-01-02", "last_updated": "2025-01-02T15:00:00Z", "currency": "USD",
             "price_target_action": "raises", "price_target": 110, "previous_price_target": 100,
             "licensed_unknown_field": "never persists"}
    value.update(changes)
    return value


def response(rows=None, next_url=None, status=200):
    body = {"status": "OK", "results": [row()] if rows is None else rows}
    if next_url is not None:
        body["next_url"] = next_url
    payload = json.dumps(body, separators=(",", ":")).encode()
    return AuditResponse(status, (("content-type", "application/json"),), payload)


def execute(root, pages=None, **changes):
    pages = [response()] if pages is None else pages
    calls = []
    def resolver(provider):
        assert provider == "massive"
        assert (root / (capture.CAPTURE_ID + ".spent.json")).exists()
        return TOKEN
    def transport(query, token, byte_limit):
        assert token == TOKEN
        assert dict(query)["limit"] == "1000"
        assert 0 < byte_limit <= capture.MAX_PAGE_BYTES
        calls.append(query)
        return pages[len(calls) - 1]
    args = dict(now=NOW, credential_resolver=resolver, transport=transport)
    args.update(changes)
    return capture._execute_fixture_capture(plan(), root, **args), calls


def test_claim_precedes_credentials_and_exact_native_projection_is_private(root):
    result, calls = execute(root)
    aggregate = json.loads(result.payload)
    assert aggregate["complete"] is True and aggregate["rows"] == 1
    assert aggregate["malformed"] == 0 and aggregate["positive_raw_pairs"] == 1
    assert aggregate["positive_pairs_touch_by_latest_cutoff"] == 1
    assert aggregate["source_blocker"] is False
    assert aggregate["point_in_time_data"] is False and aggregate["rights_verified"] is False
    projection = json.loads(result.projection_path.read_bytes())
    assert set(projection["ratings"][0]) == set(capture.FIELDS)
    assert projection["ratings"][0]["price_target"] == "110"
    assert "licensed_unknown_field" not in projection["ratings"][0]
    assert b"ZZTEST" not in result.payload and TOKEN.encode() not in result.payload
    assert len(calls) == 1 and dict(calls[0])["date.gte"] == "2024-08-01"
    for path in root.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


def test_valid_opaque_cursor_follows_same_endpoint_once_without_lifting_filters(root):
    next_url = "https://api.massive.com/benzinga/v1/ratings?cursor=opaque%2Btoken%3D"
    result, calls = execute(root, [response(next_url=next_url), response([row(benzinga_id="second")])])
    assert len(calls) == 2 and dict(calls[1])["cursor"] == "opaque+token="
    assert dict(calls[1])["date.lte"] == "2025-03-31"
    assert json.loads(result.payload)["rows"] == 2


@pytest.mark.parametrize("url", [
    "http://api.massive.com/benzinga/v1/ratings?cursor=x", "https://evil.example/benzinga/v1/ratings?cursor=x",
    "https://api.massive.com/benzinga/v1/earnings?cursor=x", "https://api.massive.com/benzinga/v1/ratings?apiKey=x&cursor=x",
    "https://api.massive.com/benzinga/v1/ratings?cursor=x&cursor=y", "https://user@api.massive.com/benzinga/v1/ratings?cursor=x",
    "https://api.massive.com/benzinga/v1/ratings?cursor=x&limit=50000", "https://api.massive.com/benzinga/v1/ratings?cursor=x#fragment",
])
def test_cursor_scope_escalation_stops_without_second_request(root, url):
    result, calls = execute(root, [response(next_url=url)])
    assert len(calls) == 1 and json.loads(result.payload)["complete"] is False
    assert result.projection_path is None


def test_repeated_cursor_refuses_and_constant_capture_id_cannot_be_rearmed(root):
    url = "https://api.massive.com/benzinga/v1/ratings?cursor=same"
    result, calls = execute(root, [response(next_url=url), response(next_url=url)])
    assert len(calls) == 2 and json.loads(result.payload)["complete"] is False
    with pytest.raises(capture.SourceCaptureError, match="already spent"):
        execute(root)


def test_later_touches_create_real_source_blocker_without_outcomes(root):
    result, _ = execute(root, [response([row(last_updated="2026-10-07T01:00:00Z")])])
    aggregate = json.loads(result.payload)
    assert aggregate["positive_raw_pairs"] == 1
    assert aggregate["positive_pairs_touch_by_latest_cutoff"] == 0
    assert aggregate["source_blocker"] is True and aggregate["outcome_access"] is False


def test_malformed_source_fields_are_retained_as_named_dispositions(root):
    result, _ = execute(root, [response([row(price_target="bad"), row(benzinga_id="second", previous_price_target=0)])])
    aggregate = json.loads(result.payload)
    assert aggregate["rows"] == 2 and aggregate["malformed"] == 1 and aggregate["positive_raw_pairs"] == 0
    projection = json.loads(result.projection_path.read_bytes())
    assert len(projection["ratings"]) == len(projection["dispositions"]) == 2
    assert projection["dispositions"][0] == "malformed_native_fields"


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
def test_redirects_auth_failures_and_server_failures_are_spent_without_retry(root, status):
    result, calls = execute(root, [response(status=status)])
    assert len(calls) == 1 and json.loads(result.payload)["complete"] is False
    assert result.projection_path is None and result.terminal_path.exists()


def test_raw_and_json_escaped_credential_echo_never_persists(root):
    escaped = "".join("\\u" + format(ord(char), "04x") for char in TOKEN)
    payload = ("{\"status\":\"OK\",\"results\":[],\"unknown\":\"" + escaped + "\"}").encode()
    result, _ = execute(root, [AuditResponse(200, (), payload)])
    assert json.loads(result.payload)["failure"] == "capture_refused"
    assert result.projection_path is None
    assert all(TOKEN.encode() not in path.read_bytes() for path in root.iterdir())


def test_page_budget_refuses_before_fetching_an_extra_page(root, monkeypatch):
    monkeypatch.setattr(capture, "MAX_PAGES", 1)
    result, calls = execute(root, [response(next_url="https://api.massive.com/benzinga/v1/ratings?cursor=x")])
    assert len(calls) == 1 and json.loads(result.payload)["complete"] is False


def test_public_production_api_refuses_fixture_plan_without_any_credential_lookup(root):
    with pytest.raises(capture.SourceCaptureError):
        capture.execute_capture(plan(), root)


def test_fixture_seam_rejects_production_adapters_and_production_root_before_activation(root):
    with pytest.raises(capture.SourceCaptureError):
        capture._execute_fixture_capture(plan(), capture.PRIVATE_ROOT, now=NOW,
            credential_resolver=lambda _: TOKEN, transport=lambda *_: response())
    with pytest.raises(capture.SourceCaptureError):
        capture._execute_fixture_capture(plan(), root, now=NOW,
            credential_resolver=capture._production_credential, transport=lambda *_: response())
    assert not (root / (capture.CAPTURE_ID + ".spent.json")).exists()


def test_symlink_parent_and_nonprivate_root_refuse(root):
    link = root.parent / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(capture.SourceCaptureError):
        execute(link)
    root.chmod(0o755)
    with pytest.raises(capture.SourceCaptureError):
        execute(root)


def test_native_numeric_targets_are_serialized_exactly_without_float_rounding():
    projected, malformed, positive, cutoff = capture._project(row(price_target=Decimal("110.125")))
    assert projected["price_target"] == "110.125" and not malformed and positive and cutoff


def test_remaining_byte_budget_is_passed_before_an_extra_body_is_read(root, monkeypatch):
    first = response(next_url="https://api.massive.com/benzinga/v1/ratings?cursor=x")
    monkeypatch.setattr(capture, "MAX_PAGE_BYTES", len(first.body) + 100)
    monkeypatch.setattr(capture, "MAX_TOTAL_BYTES", len(first.body) + 7)
    limits = []
    def transport(query, token, byte_limit):
        limits.append(byte_limit)
        return first if len(limits) == 1 else AuditResponse(200, (), b"x" * byte_limit)
    result, _ = execute(root, transport=transport)
    assert limits == [len(first.body) + 7, 7]
    aggregate = json.loads(result.payload)
    assert aggregate["response_bytes"] == len(first.body) + 7 and not aggregate["complete"]


def test_claim_write_failure_is_terminal_and_cannot_renew_scope(root, monkeypatch):
    def fail_claim(*_args):
        raise OSError("fixture secret must not escape")
    monkeypatch.setattr(capture, "_write_fd", fail_claim)
    result, calls = execute(root)
    assert not calls and result.terminal_path.exists()
    assert json.loads(result.terminal_path.read_bytes())["scope_spent"] is True
    assert b"fixture secret" not in result.payload
    with pytest.raises(capture.SourceCaptureError, match="already spent"):
        execute(root)


def test_overlapping_native_event_ids_refuse_as_incomplete_without_deduplicating(root):
    result, calls = execute(root, [response(next_url="https://api.massive.com/benzinga/v1/ratings?cursor=x"), response()])
    assert len(calls) == 2 and not json.loads(result.payload)["complete"]
    assert result.projection_path is None


def test_nonregular_code_is_refused_before_reading_or_blocking(monkeypatch):
    monkeypatch.setattr(capture, "_verify_execution_identity", lambda _: None)
    monkeypatch.setattr(capture.os, "fstat", lambda _: SimpleNamespace(st_mode=stat.S_IFIFO | 0o600, st_size=1))
    def forbidden_read(*_args):
        pytest.fail("nonregular code was read")
    monkeypatch.setattr(capture.os, "read", forbidden_read)
    with pytest.raises(capture.SourceCaptureError, match="code identity"):
        capture._verify_identity(plan().body())


def test_transport_uses_bearer_without_redirects_and_rejects_oversize_before_read(monkeypatch):
    reads, requests, closed = [], [], []
    class Response:
        status = 200
        def getheaders(self):
            return [("Content-Length", "8"), ("Content-Type", "application/json")]
        def read(self, limit):
            reads.append(limit)
            return b"12345678"
    class Connection:
        def __init__(self, host, port, **kwargs):
            assert host == "api.massive.com" and port == 443 and kwargs["timeout"] == 30
        def set_debuglevel(self, value):
            assert value == 0
        def request(self, method, url, headers):
            assert method == "GET" and url.startswith("/benzinga/v1/ratings?")
            assert TOKEN not in url and headers["Authorization"] == "Bearer " + TOKEN
            requests.append(url)
        def getresponse(self):
            return Response()
        def close(self):
            closed.append(True)
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", Connection)
    with pytest.raises(capture.SourceCaptureError, match="headers refused"):
        capture._FIXED_TRANSPORT(capture.QUERY, TOKEN, 7)
    assert len(requests) == 1 and not reads and closed == [True]
