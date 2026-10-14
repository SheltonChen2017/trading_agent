"""Fabricated transport and custody only; no credentials or provider rows."""
from __future__ import annotations

from pathlib import Path
import urllib.parse

import pytest
from short_interest_capture_fixtures import portable_capture_platform

from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.native_dated_identity as identity
import scripts.capture_short_interest_native_identity as capture
from scripts.short_interest_keychain import KeychainSecret
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from test_short_interest_native_dated_identity import archive, row

KEY = "fabricated-native-identity-key/one"
HEAD, REMOTE = "a" * 40, "b" * 40
NOW = "2026-10-14T01:00:00Z"
DATES = ("2023-01-13", "2023-01-31")


def response(rows=(), following=None, **changes):
    payload = {"status": "OK", "results": list(rows)}
    if following is not None:
        payload["next_url"] = following
    payload.update(changes)
    return canonical_json(payload).encode(), "application/json", 200


@pytest.fixture
def offline(monkeypatch):
    events, saved, responses, requests = [], {}, [], []
    monkeypatch.setattr(identity, "EXPECTED_DATES", len(DATES))
    monkeypatch.setattr(identity, "MAXIMUM_PAGES_PER_PANEL", 2)
    monkeypatch.setattr(identity, "MAXIMUM_REQUESTS", 8)
    monkeypatch.setattr(capture, "SETTLEMENT_DATES_SHA256", hash_payload(list(DATES)))
    monkeypatch.setattr(identity, "POLICY_SHA256", hash_payload(identity.identity_policy()))
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", hash_payload(capture.protocol()))
    monkeypatch.setattr(capture, "_guard", lambda *args: events.append("guard"))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    def publish(directory, name, value):
        key = (str(directory), name)
        if key in saved:
            raise capture.CaptureRefusal("artifact_already_exists")
        saved[key] = value
        events.append(name)
    monkeypatch.setattr(capture, "_publish", publish)
    monkeypatch.setattr(capture, "_publish_json", publish)
    def http(opener, request, maximum):
        assert events[-1] == "guard"
        assert any(name.endswith(".started.json") for _, name in saved)
        assert request.get_header("Authorization") == "Bearer " + KEY
        assert KEY not in request.full_url
        assert maximum == identity.MAXIMUM_RESPONSE_BYTES
        requests.append(request)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(capture, "_http", http)
    return events, saved, responses, requests


def run(offline):
    return capture.capture_dates(Path("/fabricated"), Path("/fabricated/output"), None,
        KeychainSecret(KEY), DATES, identity.build_composite_native_index(archive()),
        head=HEAD, remote=REMOTE, started_at=NOW)


@pytest.mark.usefixtures("portable_capture_platform")
def test_complete_capture_runs_each_fixed_date_and_panel_keeps_private_inventory_and_zero_looks(offline):
    events, saved, responses, requests = offline
    responses.extend([response([row()]), response(), response([row()]), response()])
    result = run(offline)
    assert result["status"] == "dated_identity_capture_complete" and result["http_attempts"] == 4
    assert result["outcome_looks"] == result["qc_attempts"] == 0
    assert result["backtest_result_exists"] is False
    assert [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(request.full_url).query))["active"]
            for request in requests] == ["true", "false", "true", "false"]
    assert all("locale=" not in request.full_url for request in requests)
    assert len([name for _, name in saved if name.endswith(".raw")]) == 4
    assert len([name for _, name in saved if name.endswith(".qualified.private.json")]) == 2
    inventory = saved[("/fabricated/output", "inventory.private.json")]
    assert inventory["raw_bytes"] == sum(len(saved[("/fabricated/output", name)])
         for directory, name in saved if name.endswith(".raw"))
    assert inventory["decoded_rows"] == 2 and inventory["source_admitted"] is False


@pytest.mark.parametrize("kind", ["ASCII", "Unicode", "percent", "slash", "media"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_secret_echo_refuses_before_raw_hash_or_persistence(offline, monkeypatch, kind):
    events, saved, responses, requests = offline
    raw = {"ASCII": KEY.encode(), "Unicode": "".join("\\u%04x" % ord(char) for char in KEY).encode(),
           "percent": urllib.parse.quote(KEY, safe="").encode(), "slash": KEY.replace("/", "\\/").encode(),
           "media": b"{}"}[kind]
    media = KEY if kind == "media" else "application/json"
    responses.append((raw, media, 200))
    real_hash = capture.hash_bytes
    def checked_hash(value):
        assert value != raw, "secret echo hashed"
        return real_hash(value)
    monkeypatch.setattr(capture, "hash_bytes", checked_hash)
    with pytest.raises(capture.NativeIdentityCaptureError, match="credential_echo"):
        run(offline)
    assert len(requests) == 1 and not any(name.endswith(".raw") for _, name in saved)
    assert not any(name == "completed.json" for _, name in saved)
    assert any(name.endswith(".refused.json") for _, name in saved)


@pytest.mark.parametrize("url", ["https://outside.invalid/v3/reference/tickers?cursor=x",
    identity.ENDPOINT + "?cursor=x&apiKey=fabricated", identity.ENDPOINT + "?cursor=x&date=2024-01-01",
    identity.ENDPOINT + "?cursor=x&active=false", identity.ENDPOINT + "?cursor=x&limit=2000"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_unsafe_cursor_is_preserved_private_but_never_followed(offline, url):
    _, saved, responses, requests = offline
    responses.append(response(following=url))
    with pytest.raises(identity.NativeDatedIdentityError):
        run(offline)
    assert len(requests) == 1
    assert any(name.endswith(".raw") for _, name in saved)
    assert not any(name == "completed.json" for _, name in saved)


@pytest.mark.usefixtures("portable_capture_platform")
def test_two_page_budget_never_calls_third_or_next_panel_when_unterminated(offline):
    _, saved, responses, requests = offline
    responses.extend([response(following=identity.ENDPOINT + "?cursor=first"),
                      response(following=identity.ENDPOINT + "?cursor=second")])
    with pytest.raises(capture.NativeIdentityCaptureError, match="panel_page_budget"):
        run(offline)
    assert len(requests) == 2 and len([name for _, name in saved if name.endswith(".raw")]) == 2
    assert not any(name.endswith(".qualified.private.json") for _, name in saved)


@pytest.mark.parametrize("bad", [(b'{"status":"OK","results":[],"status":"OK"}', "application/json", 200),
    (b"{}", "text/html", 200), (b"{}", "application/json", 404),
    (b"{}", "application/json", True), (b"invalid", "application/json", 200),
    capture.CaptureRefusal("fabricated_transport_failure")])
@pytest.mark.usefixtures("portable_capture_platform")
def test_source_media_status_JSON_or_transport_failure_keeps_attempt_and_never_retries(offline, bad):
    _, saved, responses, requests = offline
    responses.append(bad)
    with pytest.raises((capture.CaptureRefusal, identity.NativeDatedIdentityError)):
        run(offline)
    assert len(requests) == 1
    assert any(name.endswith(".started.json") for _, name in saved)
    assert any(name.endswith(".refused.json") for _, name in saved)
    assert not any(name == "completed.json" for _, name in saved)


@pytest.mark.parametrize("kind,status", [("http_not_200", 429), ("network_failure", None)])
@pytest.mark.usefixtures("portable_capture_platform")
def test_fixed_transport_reason_and_HTTP_status_survive_without_retry_or_external_text(offline, kind, status):
    _, saved, responses, requests = offline
    responses.append(SharadarCaptureRefusal(kind, status=status))
    with pytest.raises(SharadarCaptureRefusal):
        run(offline)
    receipt = next(value for (_, name), value in saved.items() if name.endswith(".refused.json"))
    assert receipt["http_status"] == status
    assert receipt["failure_category"] == kind
    assert receipt["schema"] == "si-native-identity-page-refused-v2"
    assert len(requests) == 1
    assert not any(name.endswith(".raw") or name == "completed.json" for _, name in saved)


@pytest.mark.usefixtures("portable_capture_platform")
def test_unrecognized_external_failure_text_never_enters_durable_reason(offline):
    _, saved, responses, requests = offline
    responses.append(SharadarCaptureRefusal("untrusted_" + KEY, status=403))
    with pytest.raises(SharadarCaptureRefusal):
        run(offline)
    receipt = next(value for (_, name), value in saved.items() if name.endswith(".refused.json"))
    assert receipt["failure_category"] == "source_or_guard_refused"
    assert receipt["http_status"] == 403
    assert KEY not in canonical_json(receipt)
    assert len(requests) == 1


@pytest.mark.usefixtures("portable_capture_platform")
def test_malformed_exception_code_cannot_break_fixed_refusal_publication(offline):
    _, saved, responses, requests = offline
    responses.append(SharadarCaptureRefusal(["untrusted"], status=503))
    with pytest.raises(SharadarCaptureRefusal):
        run(offline)
    receipt = next(value for (_, name), value in saved.items() if name.endswith(".refused.json"))
    assert receipt["failure_category"] == "source_or_guard_refused"
    assert receipt["http_status"] == 503
    assert len(requests) == 1


@pytest.mark.parametrize("budget", ["rows", "bytes"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_insufficient_whole_page_budget_refuses_before_start_HTTP_or_response_persistence(offline, monkeypatch, budget):
    _, saved, responses, requests = offline
    if budget == "rows":
        monkeypatch.setattr(identity, "MAXIMUM_ROWS", 999)
    else:
        monkeypatch.setattr(identity, "MAXIMUM_TOTAL_BYTES", identity.MAXIMUM_RESPONSE_BYTES - 1)
    responses.extend([response([row()]), response(), response([row()]), response()])
    monkeypatch.setattr(identity, "POLICY_SHA256", hash_payload(identity.identity_policy()))
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", hash_payload(capture.protocol()))
    with pytest.raises(capture.NativeIdentityCaptureError, match="cumulative"):
        run(offline)
    assert requests == [] and saved == {}


@pytest.mark.usefixtures("portable_capture_platform")
def test_transport_response_beyond_per_page_byte_ceiling_refuses_before_hash_or_raw_persistence(offline, monkeypatch):
    monkeypatch.setattr(identity, "MAXIMUM_RESPONSE_BYTES", 10)
    monkeypatch.setattr(identity, "POLICY_SHA256", hash_payload(identity.identity_policy()))
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", hash_payload(capture.protocol()))
    offline[2].append((b"x" * 11, "application/json", 200))
    with pytest.raises(capture.NativeIdentityCaptureError, match="response_shape_or_size"):
        run(offline)
    assert len(offline[3]) == 1
    assert any(name.endswith(".refused.json") for _, name in offline[1])
    assert not any(name.endswith(".raw") or name == "completed.json" for _, name in offline[1])


@pytest.mark.parametrize("at", ["2026-10-14T00:00:00Z", "2026-10-13T00:00:00Z"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_enclosing_start_cannot_precede_registered_source_completion(offline, at):
    with pytest.raises(capture.NativeIdentityCaptureError, match="source_completion"):
        capture.capture_dates(Path("/fabricated"), Path("/fabricated/output"), None, KeychainSecret(KEY),
             DATES, identity.build_composite_native_index(archive()), head=HEAD, remote=REMOTE, started_at=at)
    assert offline[3] == []


@pytest.mark.usefixtures("portable_capture_platform")
def test_pending_prospective_protocol_prevents_even_one_request(offline, monkeypatch):
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(capture.NativeIdentityCaptureError, match="pending_or_changed"):
        run(offline)
    assert offline[3] == [] and offline[1] == {}


@pytest.mark.usefixtures("portable_capture_platform")
def test_same_length_sorted_different_date_inventory_cannot_authorize_requests(offline):
    with pytest.raises(capture.NativeIdentityCaptureError, match="frozen_settlement_dates"):
        capture.capture_dates(Path("/fabricated"), Path("/fabricated/output"), None, KeychainSecret(KEY),
             ("2023-01-13", "2023-02-15"), identity.build_composite_native_index(archive()),
             head=HEAD, remote=REMOTE, started_at=NOW)
    assert offline[3] == []


@pytest.mark.usefixtures("portable_capture_platform")
def test_scope_changed_by_http_callback_blocks_next_request(offline, monkeypatch):
    original = capture._http
    offline[2].append(response(following=identity.ENDPOINT + "?cursor=next"))
    def changed(*args):
        result = original(*args)
        monkeypatch.setattr(identity, "MAXIMUM_ROWS", 9)
        return result
    monkeypatch.setattr(capture, "_http", changed)
    with pytest.raises(capture.NativeIdentityCaptureError, match="protocol_changed"):
        run(offline)
    assert len(offline[3]) == 1


@pytest.mark.usefixtures("portable_capture_platform")
def test_global_exclusive_claim_is_published_before_key_and_cannot_be_reused_with_new_head_time(offline, monkeypatch):
    events, saved, _, _ = offline
    root = Path("/fabricated")
    index = identity.build_composite_native_index(archive())
    monkeypatch.setattr(capture, "_source", lambda *args, **kwargs: (DATES, index))
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[1])
    monkeypatch.setattr(capture, "_prepare_capture_directory", lambda path: path)
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"fabricated code")
    reads = []
    def credential(*args, **kwargs):
        assert any(name.startswith("budget-") for _, name in saved)
        assert any(name == "started.json" for _, name in saved)
        reads.append(1)
        raise capture.CaptureRefusal("fabricated_missing_named_key")
    monkeypatch.setattr(capture.credential_reader, "_credential", credential)
    with pytest.raises(capture.CaptureRefusal):
        capture.run(root, head=HEAD, remote=REMOTE)
    assert len(reads) == 1
    monkeypatch.setattr(capture, "_utc_now", lambda: "2026-10-14T01:00:01Z")
    with pytest.raises(capture.CaptureRefusal):
        capture.run(root, head="c" * 40, remote=REMOTE)
    assert len(reads) == 1 and offline[3] == []


@pytest.mark.usefixtures("portable_capture_platform")
def test_publication_and_HTTP_have_fresh_lane_guards(offline):
    events, _, responses, _ = offline
    responses.extend([response(), response(), response(), response()])
    run(offline)
    for position, item in enumerate(events):
        if item != "guard":
            assert position > 0 and events[position - 1] == "guard"


@pytest.mark.parametrize("edge", [0, 1, 2, 4, 10, 11])
@pytest.mark.usefixtures("portable_capture_platform")
def test_every_enclosing_request_response_report_completion_clock_edge_refuses(offline, monkeypatch, edge):
    values = [NOW] * 14
    values[edge] = "2026-10-14T00:59:59Z"
    clocks = iter(values)
    monkeypatch.setattr(capture, "_utc_now", lambda: next(clocks, NOW))
    offline[2].extend([response(), response(), response(), response()])
    with pytest.raises((capture.NativeIdentityCaptureError, identity.NativeDatedIdentityError), match="chronology"):
        run(offline)
    assert not any(name == "completed.json" for _, name in offline[1])
