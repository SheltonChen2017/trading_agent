"""Invented control chains only; OS process-tree network denial required."""
import hashlib
import io
import json
import os
from pathlib import Path
import ssl

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX Calendar custody; Windows port deferred")
from research import insider_buying_eodhd_earnings_continuation3 as m
from test_insider_buying_eodhd_earnings_continuation import prior_fixture as genesis_fixture

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
            "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64}
TOKEN = "invented_continuation3_calendar_token_1234"
CAMPAIGN = "ib-eodhd-campaign-v3-invented"
WINDOWS = m.REGISTERED_WINDOWS[:3]
ROW = {"code": "AAPL.US", "report_date": "2018-09-04", "date": "2018-06-30",
       "before_after_market": "AfterMarket", "currency": "unvalidated-nonessential",
       "actual": 1.234567, "estimate": 2, "difference": -0.765433, "percent": -38.27165}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def payload(window=WINDOWS[0], rows=None):
    return {"type": "Earnings", "description": "Historical and upcoming Earnings",
            "from": window[0], "to": window[1], "earnings":
            [{**ROW, "report_date": window[0]}] if rows is None else rows}


def response(window=WINDOWS[0], raw=None, status=200, complete=True, disposition=None):
    return m.ProviderMetadataResponse(status, encoded(payload(window)) if raw is None else raw,
                                      complete, disposition)


def token_file(tmp_path):
    path = tmp_path / "invented-token3"
    path.write_bytes(TOKEN.encode())
    path.chmod(0o600)
    return path


def artifact(tmp_path, campaign_id=CAMPAIGN):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, "campaigns", campaign_id)


def previous_artifact(tmp_path):
    return tmp_path.joinpath(*m.legacy.ARTIFACT_PARTS, "campaigns", m.PREVIOUS_CAMPAIGN_ID)


def prior_fixture(tmp_path, monkeypatch, *, reported_real=False):
    """Build 151 invented control records; no transport or real source rows."""
    genesis_fixture(tmp_path, monkeypatch, reported_real=reported_real)
    parent = tmp_path.joinpath(*m.genesis.ARTIFACT_PARTS)
    lock = os.open(parent / "campaign.lock", os.O_RDWR)
    try:
        anchor = m.legacy._previous_anchor(tmp_path, m.REGISTERED_WINDOWS, lock, fixture_only=not reported_real)
    finally:
        os.close(lock)
    parent = tmp_path.joinpath(*m.legacy.ARTIFACT_PARTS)
    parent.mkdir(mode=0o700)
    scopes, campaigns = parent / "scopes", parent / "campaigns"
    scopes.mkdir(mode=0o700)
    campaigns.mkdir(mode=0o700)
    (parent / "campaign.lock").write_bytes(b"")
    (parent / "campaign.lock").chmod(0o600)
    directory = previous_artifact(tmp_path)
    directory.mkdir(mode=0o700)
    def publish(path, body, *, raw=False):
        data = body if raw else encoded(body)
        path.write_bytes(data)
        path.chmod(0o600)
        return sha(data)
    manifest = {"schema": m.legacy.SCHEMA, "profile": m.legacy.PROFILE,
        "campaign_id": m.PREVIOUS_CAMPAIGN_ID, "identity": IDENTITY,
        "fixture_only": not reported_real, "previous_campaign_anchor": anchor,
        "windows": [list(window) for window in m.legacy.REGISTERED_WINDOWS],
        "window_scope_sha256": [m.legacy._fingerprint(window) for window in m.legacy.REGISTERED_WINDOWS],
        "maximum_attempts_per_window": 1, "retry_resume_permitted": False}
    manifest_sha = publish(directory / "manifest.json", manifest)
    results = []
    for index, window in enumerate(m.legacy.REGISTERED_WINDOWS[:151]):
        prefix = f"window-{index:04d}"
        scope = {"schema": m.legacy.SCHEMA, "scope": m.legacy._scope(window),
            "campaign_id": m.PREVIOUS_CAMPAIGN_ID, "reserved_at_utc": "2026-10-13T00:00:00Z", "maximum_attempts": 1}
        scope_sha = publish(scopes / (m.legacy._fingerprint(window) + ".json"), scope)
        started = {"schema": m.legacy.SCHEMA, "window": list(window), "index": index,
            "started_at_utc": "2026-10-13T00:00:00Z", "manifest_sha256": manifest_sha,
            "scope_reservation_sha256": scope_sha, "maximum_attempts": 1}
        start_sha = publish(directory / (prefix + "-started.json"), started)
        receipt = {"http_status": 200, "transport_invocation_count": 1,
            "calendar_window_observed": index < 150, "response_body_retained": index < 150,
            "disposition": "calendar_window_observed" if index < 150 else "oversized-response",
            "body_sha256": None, "body_size_bytes": None, "metadata_sha256": None,
            **{name: False for name in m.FALSE_FLAGS}}
        if index < 150:
            raw = encoded(payload(window, []))
            receipt["body_sha256"] = publish(directory / (prefix + "-response.json"), raw, raw=True)
            receipt["body_size_bytes"] = len(raw)
            metadata = {"schema": m.legacy.SCHEMA, "body_sha256": sha(raw), "rows": [],
                        "metadata_acceptance_is_source_coverage_or_identity_admission": False}
            receipt["metadata_sha256"] = publish(directory / (prefix + "-metadata.json"), metadata)
        done = {"schema": m.legacy.SCHEMA, "window": list(window), "index": index,
            "manifest_sha256": manifest_sha, "started_sha256": start_sha,
            "scope_reservation_sha256": scope_sha, "receipt": receipt}
        complete_sha = publish(directory / (prefix + "-complete.json"), done)
        results.append({"index": index, "window": list(window), "receipt": receipt, "complete_sha256": complete_sha})
    complete = {"schema": m.legacy.SCHEMA, "campaign_id": m.PREVIOUS_CAMPAIGN_ID,
        "manifest_sha256": manifest_sha, "identity": IDENTITY, "fixture_only": not reported_real,
        "previous_campaign_anchor": anchor, "planned_windows": 246, "transport_invocation_count": 151,
        "observed_windows": 150, "refused_or_ambiguous_windows": 1, "all_registered_windows_observed": False,
        "unattempted_windows": [list(window) for window in m.REGISTERED_WINDOWS], "window_results": results,
        **{name: False for name in m.FALSE_FLAGS}}
    complete_sha = publish(directory / "complete.json", complete)
    monkeypatch.setattr(m, "PREVIOUS_COMPLETE_SHA256", complete_sha)
    monkeypatch.setattr(m, "PREVIOUS_MANIFEST_SHA256", manifest_sha)
    monkeypatch.setattr(m, "PREVIOUS_EXECUTION_HEAD", HEAD)
    monkeypatch.setattr(m, "PREVIOUS_SOURCE_INVENTORY_SHA256", IDENTITY["source_inventory_sha256"])
    return {str(path.relative_to(tmp_path)): sha(path.read_bytes()) for path in parent.rglob("*") if path.is_file()}


def run(tmp_path, *, windows=WINDOWS, transport=None, campaign_id=CAMPAIGN, **kwargs):
    return m.run_continuation(campaign_id, HEAD, token_file(tmp_path), windows=windows,
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=lambda *a, **k: dict(IDENTITY),
        transport=transport or (lambda window: response(window)), clock=lambda: "2026-10-13T00:00:00Z", **kwargs)


def test_exact_95_never_started_windows_and_immutable_predecessor_images():
    assert len(m.REGISTERED_WINDOWS) == 95
    assert m.REGISTERED_WINDOWS == m.legacy.REGISTERED_WINDOWS[151:]
    assert m.REGISTERED_WINDOWS[0] == ("2018-09-01", "2018-09-30")
    assert m.REGISTERED_WINDOWS[-1] == ("2026-07-01", "2026-07-31")
    assert m.MAX_BODY_BYTES == 16 * 1024 * 1024 and m.MAX_ROWS == 200_000
    assert m.MAX_METADATA_BYTES == 256 * 1024 * 1024 and m.MAX_CONTROL_BYTES == 1024 * 1024
    assert m.SCHEMA not in {m.legacy.SCHEMA, m.genesis.SCHEMA}
    assert m.ARTIFACT_PARTS not in {m.legacy.ARTIFACT_PARTS, m.genesis.ARTIFACT_PARTS}


def test_v3_binds_all_predecessor_scopes_metadata_producer_hashes_and_preserves_old_roots(tmp_path, monkeypatch):
    previous = prior_fixture(tmp_path, monkeypatch)
    calls = []
    def transport(window):
        directory = artifact(tmp_path)
        assert (directory / f"window-{len(calls):04d}-started.json").exists()
        manifest = json.loads((directory / "manifest.json").read_bytes())
        assert manifest["previous_campaign_anchor"]["complete_sha256"] == m.PREVIOUS_COMPLETE_SHA256
        assert len(manifest["previous_campaign_anchor"]["scope_sha256"]) == 151
        assert len(manifest["previous_campaign_anchor"]["genesis_campaign_anchor"]["scope_sha256"]) == 2
        assert manifest["maximum_metadata_bytes_per_window"] == m.MAX_METADATA_BYTES
        calls.append(window)
        return response(window)
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS) and result["source_rows"] == result["metadata_accepted_rows"] == 3
    assert result["all_registered_windows_observed"] and result["quarantined_rows"] == 0
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert all(sha((tmp_path / path).read_bytes()) == digest for path, digest in previous.items())
    assert TOKEN not in json.dumps(result) and "1.234567" not in json.dumps(result)
    complete = json.loads((artifact(tmp_path) / "window-0000-complete.json").read_bytes())
    metadata = (artifact(tmp_path) / "window-0000-metadata.json").read_bytes()
    assert complete["receipt"]["metadata_sha256"] == sha(metadata)


@pytest.mark.parametrize("window", [m.genesis.REGISTERED_WINDOWS[1], m.legacy.REGISTERED_WINDOWS[150],
                                    ("2018-08-31", "2018-09-01"), ("2026-08-01", "2026-08-01")])
def test_earlier_failed_months_and_broader_windows_refuse_before_configuration(tmp_path, window):
    with pytest.raises(m.EarningsCampaignError, match="outside_frozen_support_envelope"):
        run(tmp_path, windows=(window,))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("leaf", ["complete.json", "manifest.json", "window-0000-started.json", "window-0149-metadata.json", "scope"])
def test_historical_ancestor_tampering_refuses_before_any_new_root(tmp_path, monkeypatch, leaf):
    prior_fixture(tmp_path, monkeypatch)
    path = previous_artifact(tmp_path) / leaf
    if leaf == "scope":
        path = previous_artifact(tmp_path).parent.parent / "scopes" / (m.legacy._fingerprint(m.legacy.REGISTERED_WINDOWS[149]) + ".json")
    path.write_bytes(b"corrupt")
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, transport=lambda window: pytest.fail("provider"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_valid_json_unbound_predecessor_control_change_refused_by_external_anchor(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    path = previous_artifact(tmp_path) / "complete.json"
    body = json.loads(path.read_bytes())
    body["invented_unbound_metadata"] = True
    path.write_bytes(encoded(body))
    with pytest.raises(m.EarningsCampaignError, match="previous_external_anchor_mismatch"):
        run(tmp_path, transport=lambda window: response(window))


def test_disk_preflight_requires_full_explicit_metadata_and_raw_budget(tmp_path, monkeypatch):
    class Info:
        f_frsize = 1
        f_bavail = m.MIN_FREE_BYTES + 95 * (m.MAX_BODY_BYTES + m.MAX_METADATA_BYTES + 3 * m.MAX_CONTROL_BYTES)
    monkeypatch.setattr(m.os, "fstatvfs", lambda fd: Info())
    result = m._disk_reserve(-1, 95)
    assert result["available_bytes_at_preflight"] == Info.f_bavail
    Info.f_bavail -= 1
    with pytest.raises(m.EarningsCampaignError, match="disk_reserve_insufficient"):
        m._disk_reserve(-1, 95)


def test_insufficient_disk_stops_before_new_root_or_dispatch(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    class Info:
        f_frsize = 1
        f_bavail = m.MIN_FREE_BYTES
    monkeypatch.setattr(m.os, "fstatvfs", lambda fd: Info())
    with pytest.raises(m.EarningsCampaignError, match="disk_reserve_insufficient"):
        run(tmp_path, transport=lambda window: pytest.fail("provider"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("failure", ["http", "timeout", "oversize", "envelope", "echo"])
def test_failed_window_stops_and_never_retries_others_are_accounted(tmp_path, monkeypatch, failure):
    prior_fixture(tmp_path, monkeypatch)
    calls = []
    def transport(window):
        calls.append(window)
        if failure == "http":
            return response(window, raw=TOKEN.encode(), status=403)
        if failure == "timeout":
            return response(window, raw=b"", status=None, complete=False, disposition="transport-timeout")
        if failure == "oversize":
            return response(window, raw=b"", complete=False, disposition="oversized-response")
        if failure == "envelope":
            return response(window, raw=b'{"error":"private"}')
        return response(window, raw=encoded(payload(window, [{**ROW, "currency": TOKEN}])))
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS[:1]) and result["unattempted_windows_count"] == 2
    assert result["refused_or_ambiguous_windows"] == 1
    assert not (artifact(tmp_path) / "window-0000-response.json").exists()
    assert TOKEN.encode() not in b"".join(path.read_bytes() for path in artifact(tmp_path).iterdir())
    with pytest.raises(m.EarningsCampaignError, match="completed_or_ambiguous_window_cannot_repeat"):
        run(tmp_path, campaign_id="ib-eodhd-campaign-v3-repeat", transport=lambda window: pytest.fail("provider"))


def test_all_rows_source_ordinals_quarantines_and_opaque_financial_lexemes_preserved():
    rows = [ROW, {**ROW, "code": None}, {**ROW, "before_after_market": None}, None]
    raw = encoded(payload(rows=rows)).replace(b'"actual":1.234567', b'"actual":1e999999')
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["sample_rows"] == 4 and receipt["metadata_accepted_rows"] == 1 and receipt["quarantined_rows"] == 3
    assert [row["source_row_ordinal"] for row in projection] == list(range(4))
    assert all("currency" not in row and not m._FINANCIAL.intersection(row) for row in projection)
    assert receipt["metadata_sha256"] is None


@pytest.mark.parametrize("escaped", [False, True])
def test_credential_echo_even_unknown_currency_never_hashed(escaped):
    raw = encoded(payload(rows=[{**ROW, "currency": TOKEN}]))
    if escaped:
        raw = raw.replace(TOKEN.encode(), TOKEN.replace("_", "\\u005f").encode())
    receipt, rows = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert rows is None and receipt["disposition"] == "credential_echo_refused"
    assert receipt["body_sha256"] is None


def test_control_and_metadata_publication_bounds_are_enforced_before_write(tmp_path, monkeypatch):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(m, "MAX_CONTROL_BYTES", 16)
        monkeypatch.setattr(m, "MAX_METADATA_BYTES", 32)
        assert m._publish(fd, "small.json", {"x": 1})
        with pytest.raises(m.EarningsCampaignError, match="immutable_json_byte_bound"):
            m._publish(fd, "too-big.json", {"x": "x" * 32})
        with pytest.raises(m.EarningsCampaignError, match="immutable_json_byte_bound"):
            m._publish(fd, "window-0000-metadata.json", {"x": "x" * 33})
        assert set(os.listdir(fd)) == {"small.json"}
    finally:
        os.close(fd)


def test_metadata_reserve_covers_conservative_maximum_per_row_field_width():
    reasons = ["source_row_not_object", "source_row_field_shape_unknown", "source_code_unknown",
        "source_report_date_unknown", "source_fiscal_date_unknown", "report_date_outside_registered_scope",
        "fiscal_date_after_report_date", "source_timing_unknown", "source_financial_shape_unknown",
        "current_provider_reported_status_unknown"]
    # Deliberate overestimate: some reasons are mutually exclusive with the
    # maximum valid field values, but the reserve must still cover this image.
    maximum = {"source_row_ordinal": m.MAX_ROWS - 1, "metadata_accepted": False,
        "quarantine_reasons": reasons, "code": "A" * 80 + "." + "B" * 12,
        "report_date": "2026-07-31", "fiscal_date": "2026-07-31",
        "before_after_market": "BeforeMarket", "current_provider_reported_status": "reported"}
    assert m.MAX_METADATA_BYTES > m.MAX_ROWS * (len(encoded(maximum)) + 1) + 1024


@pytest.mark.parametrize("which", ["genesis", "legacy"])
def test_each_ancestor_lock_prevents_another_caller_before_new_start(tmp_path, monkeypatch, which):
    prior_fixture(tmp_path, monkeypatch)
    def transport(window):
        module = m.genesis if which == "genesis" else m.legacy
        lock = os.open(tmp_path.joinpath(*module.ARTIFACT_PARTS, "campaign.lock"), os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                m.fcntl.flock(lock, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
        finally:
            os.close(lock)
        return response(window)
    assert run(tmp_path, windows=WINDOWS[:1], transport=transport)["observed_windows"] == 1


def test_metadata_producer_sha_is_not_self_rehashed_after_publication(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    publish = m._publish
    def missing_hash(directory, name, body):
        if name.endswith("-complete.json"):
            assert body["receipt"]["metadata_sha256"] is not None
        return publish(directory, name, body)
    monkeypatch.setattr(m, "_publish", missing_hash)
    assert run(tmp_path, windows=WINDOWS[:1])["observed_windows"] == 1


class Stream(io.BytesIO):
    def __init__(self, raw, status, url):
        super().__init__(raw)
        self.status, self.url, self.headers, self.read_calls = status, url, {}, 0
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url
    def read(self, *args):
        self.read_calls += 1
        return super().read(*args)


def test_default_three_locks_exact_tls_no_proxy_and_non200_no_read(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch, reported_real=True)
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_identity", lambda head, root=None: IDENTITY)
    calls, streams = [], []
    class Opener:
        def open(self, item, timeout):
            calls.append((item, timeout))
            stream = Stream(TOKEN.encode(), 403, item.full_url)
            streams.append(stream)
            return stream
    def build(*handlers):
        assert handlers[0].proxies == {}
        assert isinstance(handlers[1], m._DenyRedirect)
        assert handlers[2]._context.verify_mode == ssl.CERT_REQUIRED
        return Opener()
    monkeypatch.setattr(m.request, "build_opener", build)
    result = m.run_continuation(CAMPAIGN, HEAD, token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)
    assert len(calls) == 1 and result["unattempted_windows_count"] == 94
    item, timeout = calls[0]
    assert item.full_url == m._url(WINDOWS[0]).replace("<redacted>", TOKEN)
    assert "symbols=" not in item.full_url and item.get_method() == "GET" and timeout == 15
    assert streams[0].read_calls == 0 and streams[0].closed


@pytest.mark.parametrize("headers,raw,code", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"private", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Encoding": "gzip"}, b"private", "unsupported-content-encoding"),
    ({"Content-Length": "-1"}, b"private", "invalid-content-length"),
])
def test_v3_response_cap_and_encoding_fail_closed(headers, raw, code):
    stream = Stream(raw, 200, "invented")
    stream.headers = headers
    assert m._read_window_bounded(stream, 200).disposition == code


def test_v3_accepts_16mib_boundary_reader_without_relaxing_frozen_v2():
    raw = b"x" * (5 * 1024 * 1024)
    stream = Stream(raw, 200, "invented")
    stream.headers = {"Content-Length": str(len(raw))}
    result = m._read_window_bounded(stream, 200)
    assert result.body == raw and result.body_complete
    assert m.legacy.MAX_BODY_BYTES == 4 * 1024 * 1024


def test_fake_identity_cannot_reach_real_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("provider"))
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        m.run_continuation(CAMPAIGN, HEAD, Path("/invented"), owner_acknowledged_rotated_token=True,
            root=tmp_path, identity=lambda *a, **k: IDENTITY)
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        run(tmp_path, transport=m._default_transport)
