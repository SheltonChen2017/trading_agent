"""Fabricated pagination/credentials only: never source or Keychain access."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.parse

import pytest
from short_interest_capture_fixtures import portable_capture_platform
from data.hashing import canonical_json, hash_payload
import scripts.capture_short_interest_native_population as capture
from scripts.short_interest_keychain import KeychainSecret

KEY = "fabricated-native-population-key/one"
HEAD, REMOTE = "a" * 40, "b" * 40
NOW = "2026-10-14T00:00:00Z"


@pytest.fixture
def offline(monkeypatch):
    events, saved, responses, requests = [], {}, [], []
    monkeypatch.setattr(capture, "_guard", lambda *args: events.append("guard"))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    def publish(directory, name, value):
        if name in saved:
            raise capture.CaptureRefusal("artifact_already_exists")
        saved[name] = value
        events.append(name)
    monkeypatch.setattr(capture, "_publish_json", publish)
    monkeypatch.setattr(capture, "_publish", publish)
    def http(opener, request, maximum):
        ordinal = len(requests) + 1
        assert f"page-{ordinal:02d}.started.json" in saved
        assert events[-1] == "guard"
        assert request.get_header("Authorization") == "Bearer " + KEY
        assert KEY not in request.full_url and maximum == capture.MAXIMUM_BYTES
        requests.append(request)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(capture, "_http", http)
    return events, saved, responses, requests


def page(*, next_url=None, rows=(), status="OK"):
    result = {"status": status, "results": list(rows)}
    if next_url is not None:
        result["next_url"] = next_url
    return canonical_json(result).encode(), "application/json", 200


def run(offline):
    return capture.capture_pages(Path("/fabricated"), Path("/fabricated/output"), None, KeychainSecret(KEY),
                                 head=HEAD, remote=REMOTE, started_at=NOW)


@pytest.mark.parametrize("kind", ["ASCII_body", "Unicode_body", "percent_body", "slash_body", "ASCII_media", "percent_media"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_echo_is_refused_before_response_persistence_or_hashing(offline, monkeypatch, kind):
    _, saved, responses, _ = offline
    value, media = KEY, "application/json"
    if kind == "Unicode_body":
        value = "".join("\\u%04x" % ord(char) for char in KEY)
    elif kind == "percent_body":
        value = urllib.parse.quote(KEY, safe="")
    elif kind == "slash_body":
        value = KEY.replace("/", "\\/")
    elif kind.endswith("media"):
        media += "; hint=" + (KEY if kind == "ASCII_media" else urllib.parse.quote(KEY, safe=""))
        value = "no credential in body"
    raw = ('{"status":"OK","results":[],"notice":"' + value + '"}').encode()
    responses.append((raw, media, 200))
    hashed = []
    original = capture.hash_bytes
    monkeypatch.setattr(capture, "hash_bytes", lambda value: hashed.append(value) or original(value))
    with pytest.raises(capture.NativePopulationCaptureError, match="credential_echo_refused"):
        run(offline)
    assert not hashed
    assert set(saved) == {"page-01.started.json", "page-01.refused.json"}


@pytest.mark.usefixtures("portable_capture_platform")
def test_complete_two_page_chain_requests_every_exact_link_and_retains_all_rows(offline):
    _, saved, responses, requests = offline
    continuation = capture.ENDPOINT + "?cursor=fabricated-page-two"
    responses.extend((page(next_url=continuation, rows=[{"ticker": "OLD1"}]), page(rows=[{"ticker": "OLD2"}])))
    result = run(offline)
    assert result["status"] == "source_capture_complete" and result["http_attempts"] == 2
    assert requests[0].full_url == capture.ENDPOINT + "?" + urllib.parse.urlencode(capture.PARAMS)
    assert requests[1].full_url == continuation
    report = saved["population.private.json"]
    assert report["complete_advertised_page_chain"] is True
    assert report["scope"] == "reported_provider_population_not_US_universe"
    assert [row["ordinal"] for row in report["pages"]] == [1, 2]
    assert report["pages"][0]["next_url"] == continuation and report["pages"][1]["next_url"] is None
    assert len([name for name in saved if name.endswith(".raw")]) == 2
    assert report["outcome_looks"] == report["qc_attempts"] == 0
    assert report["ready_for_empirical_backtest"] is False and report["signal_or_return_computed"] is False
    assert KEY not in repr(report) and KEY not in repr(KeychainSecret(KEY))


@pytest.mark.parametrize("url", [
    "http://api.massive.com/stocks/v1/short-interest?cursor=x",
    "https://evil.invalid/stocks/v1/short-interest?cursor=x",
    "https://api.massive.com:443/stocks/v1/short-interest?cursor=x",
    "https://user@api.massive.com/stocks/v1/short-interest?cursor=x",
    "https://api.massive.com/stocks/v1/short-volume?cursor=x",
    "https://api.massive.com/stocks/v1/short-interest?cursor=x#secret",
    "https://api.massive.com/stocks/v1/short-interest?cursor=x&api_key=unknown-secret",
    "https://api.massive.com/stocks/v1/short-interest?cursor=x&cursor=y",
    "https://api.massive.com/stocks/v1/short-interest?cursor=",
    "https://api.massive.com/stocks/v1/short-interest?cursor=x&settlement_date.lte=2030-01-01",
])
@pytest.mark.usefixtures("portable_capture_platform")
def test_unsafe_continuation_never_followed_and_failed_page_retained(offline, url):
    _, saved, responses, requests = offline
    responses.append(page(next_url=url))
    with pytest.raises(capture.CaptureRefusal):
        run(offline)
    assert len(requests) == 1
    assert "page-01.raw" in saved and "page-01.received.json" in saved and "page-01.refused.json" in saved
    assert "page-02.started.json" not in saved and "completed.json" not in saved


@pytest.mark.usefixtures("portable_capture_platform")
def test_same_next_link_cycle_refuses_before_third_request(offline):
    _, saved, responses, requests = offline
    continuation = capture.ENDPOINT + "?cursor=unchanged"
    responses.extend((page(next_url=continuation), page(next_url=continuation)))
    with pytest.raises(capture.CaptureRefusal, match="pagination_cycle"):
        run(offline)
    assert len(requests) == 2 and "page-02.received.json" in saved
    assert "page-03.started.json" not in saved and "population.private.json" not in saved


@pytest.mark.parametrize("complete", [False, True])
@pytest.mark.usefixtures("portable_capture_platform")
def test_exact_32_page_budget_never_makes_33rd_request_or_partial_completion(offline, complete):
    _, saved, responses, requests = offline
    for ordinal in range(32):
        next_url = None if complete and ordinal == 31 else capture.ENDPOINT + "?cursor=page" + str(ordinal + 2)
        responses.append(page(next_url=next_url))
    if complete:
        assert run(offline)["http_attempts"] == 32
    else:
        with pytest.raises(capture.CaptureRefusal, match="page_budget_exhausted"):
            run(offline)
        assert "page-32.refused.json" in saved and "completed.json" not in saved
    assert len(requests) == 32 and "page-33.started.json" not in saved


@pytest.mark.parametrize("error", [capture.CaptureRefusal("fixed-network-failure"), OSError("external-text-never-published")])
@pytest.mark.usefixtures("portable_capture_platform")
def test_transport_failure_retains_started_attempt_and_no_retry_or_skipped_page(offline, error):
    _, saved, responses, requests = offline
    responses.append(error)
    with pytest.raises((capture.CaptureRefusal, OSError)):
        run(offline)
    assert len(requests) == 1 and set(saved) == {"page-01.started.json", "page-01.refused.json"}
    assert "external-text-never-published" not in repr(saved)


@pytest.mark.parametrize("gap", ["enclosing", "response", "between", "report", "completion"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_all_enclosing_request_response_report_completion_clock_edges_refuse(offline, monkeypatch, gap):
    _, saved, responses, requests = offline
    responses.extend((page(next_url=capture.ENDPOINT + "?cursor=next"), page()))
    earlier, later = "2026-10-13T23:59:59Z", "2026-10-14T00:00:01Z"
    clocks = [NOW] * 6
    if gap == "enclosing":
        clocks[0] = earlier
    elif gap == "response":
        clocks[0] = later
    elif gap == "between":
        clocks[1:] = [later] * 5
        clocks[2] = NOW
    elif gap == "report":
        clocks[4] = earlier
    else:
        clocks[4] = later
    values = iter(clocks)
    monkeypatch.setattr(capture, "_utc_now", lambda: next(values, later))
    with pytest.raises(capture.CaptureRefusal, match="chronology"):
        run(offline)
    assert "completed.json" not in saved
    assert len(requests) == (0 if gap == "enclosing" else 1 if gap in {"response", "between"} else 2)


@pytest.mark.usefixtures("portable_capture_platform")
def test_existing_first_receipt_stops_restart_without_transport(offline):
    _, saved, responses, requests = offline
    saved["page-01.started.json"] = {"preserved": True}
    with pytest.raises(capture.CaptureRefusal, match="already_exists"):
        run(offline)
    assert not requests and saved["page-01.started.json"] == {"preserved": True}


@pytest.mark.parametrize("raw,media,status", [(None, "application/json", 200), (b"{}", None, 200),
    (b"{}", "application/json", 403), (b"{}", "text/html", 200), (b"[]", "application/json", 200),
    (b'{"status":"OK","status":"OK","results":[]}', "application/json", 200)])
@pytest.mark.usefixtures("portable_capture_platform")
def test_invalid_response_types_HTTP_media_and_page_contract_never_complete(offline, raw, media, status):
    _, saved, responses, requests = offline
    responses.append((raw, media, status))
    with pytest.raises((capture.CaptureRefusal, ValueError, TypeError)):
        run(offline)
    assert len(requests) == 1 and "completed.json" not in saved
    if raw is None or media is None:
        assert "page-01.raw" not in saved


@pytest.mark.usefixtures("portable_capture_platform")
def test_pending_protocol_refuses_before_started_receipt_or_key_header(offline, monkeypatch):
    _, saved, responses, requests = offline
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(capture.CaptureRefusal, match="protocol_pending"):
        run(offline)
    assert not saved and not requests


@pytest.mark.usefixtures("portable_capture_platform")
def test_scope_callback_change_after_first_response_refuses_before_second_GET(offline, monkeypatch):
    _, saved, responses, requests = offline
    responses.append(page(next_url=capture.ENDPOINT + "?cursor=next"))
    original_http = capture._http
    def http(*args):
        value = original_http(*args)
        changed = dict(capture.PARAMS)
        changed["settlement_date.lte"] = "2030-01-01"
        monkeypatch.setattr(capture, "PARAMS", changed)
        return value
    monkeypatch.setattr(capture, "_http", http)
    with pytest.raises(capture.CaptureRefusal, match="protocol_changed"):
        run(offline)
    assert len(requests) == 1
    assert "page-01.received.json" in saved and "page-02.started.json" not in saved
    assert "completed.json" not in saved


@pytest.mark.usefixtures("portable_capture_platform")
def test_hypothetically_frozen_one_page_child_budget_still_cannot_launch_second_GET(offline, monkeypatch):
    _, saved, responses, requests = offline
    monkeypatch.setattr(capture, "MAXIMUM_PAGES", 1)
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", hash_payload(capture.protocol()))
    responses.append(page(next_url=capture.ENDPOINT + "?cursor=next"))
    with pytest.raises(capture.CaptureRefusal, match="page_budget_exhausted"):
        run(offline)
    assert len(requests) == 1 and "page-01.refused.json" in saved
    assert "page-02.started.json" not in saved and "completed.json" not in saved


@pytest.mark.usefixtures("portable_capture_platform")
def test_run_rechecks_lane_before_each_freeze_publication_and_code_file_read(monkeypatch):
    events = []
    monkeypatch.setattr(capture, "_guard", lambda *args: events.append("guard"))
    monkeypatch.setattr(capture, "_git", lambda *args: args[-1])
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    monkeypatch.setattr(capture, "_prepare_capture_directory", lambda target: target)
    monkeypatch.setattr(capture, "CODE_FILES", ("scripts/fabricated-only.py",))
    def publish(directory, name, value):
        assert events[-1] == "guard", "publication had no fresh invariant check"
        events.append(name)
    monkeypatch.setattr(capture, "_publish_json", publish)
    def read(path):
        assert events[-1] == "guard", "code read had no fresh invariant check"
        events.append("read")
        return b"fabricated-code-only"
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(capture, "read_named_keychain", lambda name: KeychainSecret(KEY))
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: None)
    monkeypatch.setattr(capture, "capture_pages", lambda *args, **kwargs: {"status": "fabricated_complete"})
    assert capture.run(Path("/fabricated"), head=HEAD, remote=REMOTE)["status"] == "fabricated_complete"


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="protected POSIX custody required; SI-CR-WIN-20261012-002")
def test_exclusive_owned_run_and_whole_protocol_budget_survive_new_head_and_time(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_guard", lambda *args: None)
    monkeypatch.setattr(capture, "_git", lambda *args: args[-1])
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    monkeypatch.setattr(capture, "CODE_FILES", ())
    monkeypatch.setattr(capture, "read_named_keychain", lambda name: KeychainSecret(KEY))
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: None)
    calls = []
    monkeypatch.setattr(capture, "capture_pages", lambda *args, **kwargs: calls.append(1) or {"status": "fabricated_only"})
    capture.run(tmp_path, head=HEAD, remote=REMOTE)
    parent = tmp_path / capture.PARENT
    first = next(path for path in parent.iterdir() if path.is_dir())
    before = {path.name: path.read_bytes() for path in first.iterdir()}
    budget = parent / ("budget-" + capture.PROTOCOL_SHA256 + ".json")
    budget_before = budget.read_bytes()
    with pytest.raises(FileExistsError):
        capture.run(tmp_path, head=HEAD, remote=REMOTE)
    assert before == {path.name: path.read_bytes() for path in first.iterdir()}
    monkeypatch.setattr(capture, "_utc_now", lambda: "2026-10-15T00:00:00Z")
    with pytest.raises(capture.CaptureRefusal, match="artifact_already_exists"):
        capture.run(tmp_path, head="c" * 40, remote=REMOTE)
    second = next(path for path in parent.iterdir() if path.is_dir() and path != first)
    assert {path.name for path in second.iterdir()} == {"refused.json"}
    assert budget.read_bytes() == budget_before and len(calls) == 1
    assert before == {path.name: path.read_bytes() for path in first.iterdir()}
