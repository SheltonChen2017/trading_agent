"""Invented partial-control custody; OS process-tree network denial required."""
import errno
import io
import json
import os
from pathlib import Path
import ssl

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX Calendar custody; Windows port deferred")
from research import insider_buying_eodhd_earnings_continuation4 as m
from test_insider_buying_eodhd_earnings_continuation3 import prior_fixture as v2_fixture

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
    "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64}
TOKEN = "invented_continuation4_calendar_token_1234"
CAMPAIGN = "ib-eodhd-campaign-v4-invented"
WINDOWS = m.REGISTERED_WINDOWS[:2]
ROW = {"code": "FIXA.US", "report_date": "2019-03-01", "date": "2018-12-31",
    "before_after_market": "AfterMarket", "actual": 1.234567, "estimate": 2,
    "difference": -0.765433, "percent": -38.27165, "currency": "nonessential-unknown"}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return m._sha(raw)


def response(window=WINDOWS[0], *, raw=None, status=200, complete=True, disposition=None):
    body = {"type": "Earnings", "description": "Historical and upcoming Earnings", "from": window[0],
        "to": window[1], "earnings": [{**ROW, "report_date": window[0]}]}
    return m.ProviderMetadataResponse(status, encoded(body) if raw is None else raw, complete, disposition)


def artifact(tmp_path, campaign_id=CAMPAIGN):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, "campaigns", campaign_id)


def witness_path(tmp_path):
    return tmp_path.joinpath(*m.WITNESS_PARTS, "witness.json")


def partial_root(tmp_path):
    return tmp_path.joinpath(*m.predecessor.ARTIFACT_PARTS, "campaigns", m.PARTIAL_CAMPAIGN_ID)


def prior_fixture(tmp_path, monkeypatch, *, reported_real=False):
    """Fresh invented predecessor trees; never supplies real source rows."""
    v2_fixture(tmp_path, monkeypatch, reported_real=reported_real)
    gp = tmp_path.joinpath(*m.genesis.ARTIFACT_PARTS)
    vp = tmp_path.joinpath(*m.legacy.ARTIFACT_PARTS)
    gl, vl = os.open(gp / "campaign.lock", os.O_RDONLY), os.open(vp / "campaign.lock", os.O_RDONLY)
    try:
        anchor = m.predecessor._previous_anchor(tmp_path, m.REGISTERED_WINDOWS, vl, gl, fixture_only=not reported_real)
    finally:
        os.close(gl); os.close(vl)
    parent = tmp_path.joinpath(*m.predecessor.ARTIFACT_PARTS)
    parent.mkdir(mode=0o700)
    (parent / "scopes").mkdir(mode=0o700); (parent / "campaigns").mkdir(mode=0o700)
    (parent / "campaign.lock").write_bytes(b""); (parent / "campaign.lock").chmod(0o600)
    directory = partial_root(tmp_path); directory.mkdir(mode=0o700)
    leaves, scopes, counts = {}, {}, []
    def publish(path, value, *, raw=False):
        data = value if raw else encoded(value)
        path.write_bytes(data); path.chmod(0o600)
        if path.parent == directory:
            leaves[path.name] = {"bytes": len(data), "sha256": sha(data)}
        return sha(data)
    manifest = {"schema": m.predecessor.SCHEMA, "profile": m.predecessor.PROFILE,
        "campaign_id": m.PARTIAL_CAMPAIGN_ID, "identity": IDENTITY, "previous_campaign_anchor": anchor,
        "windows": [list(w) for w in m.predecessor.REGISTERED_WINDOWS],
        "window_scope_sha256": [m.predecessor._fingerprint(w) for w in m.predecessor.REGISTERED_WINDOWS],
        "fixture_only": not reported_real, "maximum_attempts_per_window": 1, "retry_resume_permitted": False,
        **{name: False for name in m.FALSE_FLAGS}}
    manifest_sha = publish(directory / "manifest.json", manifest)
    for index, window in enumerate(m.predecessor.REGISTERED_WINDOWS[:6]):
        prefix = f"window-{index:04d}"
        scope_name = m.predecessor._fingerprint(window) + ".json"
        scope_sha = publish(parent / "scopes" / scope_name, {"schema": m.predecessor.SCHEMA,
            "scope": m.predecessor._scope(window), "campaign_id": m.PARTIAL_CAMPAIGN_ID,
            "reserved_at_utc": "2026-10-13T00:00:00Z", "maximum_attempts": 1})
        scopes[scope_name] = scope_sha
        started_sha = publish(directory / (prefix + "-started.json"), {"schema": m.predecessor.SCHEMA,
            "index": index, "window": list(window), "manifest_sha256": manifest_sha,
            "scope_reservation_sha256": scope_sha, "maximum_attempts": 1})
        # Invalid JSON demonstrates this custody validator does not parse old
        # paid bodies or metadata; their exact external hashes alone bind them.
        raw = b"INVENTED-OLD-RESPONSE-NOT-DECODED"
        body_sha = publish(directory / (prefix + "-response.json"), raw, raw=True)
        metadata_sha = publish(directory / (prefix + "-metadata.json"), b"INVENTED-OLD-METADATA-NOT-DECODED", raw=True)
        if index < 5:
            receipt = {"http_status": 200, "transport_invocation_count": 1, "calendar_window_observed": True,
                "response_body_retained": True, "body_sha256": body_sha, "body_size_bytes": len(raw),
                "metadata_sha256": metadata_sha, "sample_rows": 1, "metadata_accepted_rows": 1,
                "quarantined_rows": 0, **{name: False for name in m.FALSE_FLAGS}}
            done_sha = publish(directory / (prefix + "-complete.json"), {"schema": m.predecessor.SCHEMA,
                "index": index, "window": list(window), "manifest_sha256": manifest_sha,
                "started_sha256": started_sha, "scope_reservation_sha256": scope_sha, "receipt": receipt})
            counts.append({"index": index, "window": list(window), "complete_sha256": done_sha,
                "sample_rows": 1, "metadata_accepted_rows": 1, "quarantined_rows": 0})
    witness = {"schema": m.WITNESS_SCHEMA, "observed_at_utc": "2026-10-13T00:00:00Z",
        "execution_head": HEAD, "manifest_sha256": manifest_sha, "campaign_id": m.PARTIAL_CAMPAIGN_ID,
        "journal_leaf_count": 24, "consumed_scope_count": 6, "sealed_window_count": 5,
        "unsealed_started_window_count": 1, "campaign_completion_present": False,
        "unattempted_suffix_windows": 89, "next_unattempted_window": list(m.REGISTERED_WINDOWS[0]),
        "last_unattempted_window": list(m.REGISTERED_WINDOWS[-1]), "source_inventory_sha256": IDENTITY["source_inventory_sha256"],
        "previous_v2_complete_sha256": m.predecessor.PREVIOUS_COMPLETE_SHA256,
        "previous_v2_manifest_sha256": m.predecessor.PREVIOUS_MANIFEST_SHA256,
        "genesis_complete_sha256": m.legacy.PREVIOUS_COMPLETE_SHA256,
        "journal_leaf_sha256_and_bytes": leaves, "consumed_scope_sha256": scopes, "sealed_window_counts": counts,
        "raw_financial_bodies_decoded": False, "paid_metadata_rows_decoded": False, "credential_read": False,
        "network_write_fork_denied": True, "locks_shared_read_only": True,
        "observed_failure_cause": "not_established_by_retained_controls", "aggregate_completion_manufactured": False}
    wp = witness_path(tmp_path); wp.parent.mkdir(mode=0o700, parents=True)
    wp.parent.parent.chmod(0o700)
    witness_sha = publish(wp, witness)
    monkeypatch.setattr(m, "PARTIAL_EXECUTION_HEAD", HEAD)
    monkeypatch.setattr(m, "PARTIAL_SOURCE_INVENTORY_SHA256", IDENTITY["source_inventory_sha256"])
    monkeypatch.setattr(m, "PARTIAL_MANIFEST_SHA256", manifest_sha)
    return witness_sha


def run(tmp_path, witness_sha, *, windows=WINDOWS, transport=None, campaign_id=CAMPAIGN, **kwargs):
    token = tmp_path / "invented-token4"; token.write_bytes(TOKEN.encode()); token.chmod(0o600)
    return m.run_continuation(campaign_id, HEAD, token, windows=windows,
        expected_partial_witness_sha256=witness_sha, owner_acknowledged_rotated_token=True,
        root=tmp_path, identity=lambda *a, **k: dict(IDENTITY),
        transport=transport or (lambda window: response(window)), **kwargs)


def test_exact89_never_started_suffix_caps_and_new_schema():
    assert len(m.REGISTERED_WINDOWS) == 89 and m.REGISTERED_WINDOWS == m.predecessor.REGISTERED_WINDOWS[6:]
    assert m.REGISTERED_WINDOWS[0] == ("2019-03-01", "2019-03-31")
    assert m.REGISTERED_WINDOWS[-1] == ("2026-07-01", "2026-07-31")
    assert m.MAX_BODY_BYTES == 16 * 1024**2 and m.MAX_METADATA_BYTES == 256 * 1024**2
    assert m.MAX_CONTROL_BYTES == 1024**2 and m.MAX_ROWS == 200_000 and m.MAX_WITNESS_BYTES == 8192
    assert m.SCHEMA not in {m.predecessor.SCHEMA, m.legacy.SCHEMA, m.genesis.SCHEMA}
    assert m.ARTIFACT_PARTS not in {m.predecessor.ARTIFACT_PARTS, m.legacy.ARTIFACT_PARTS, m.genesis.ARTIFACT_PARTS}


def test_all_partial_pins_bound_without_repair_decode_or_old_root_changes(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    before = {str(p): sha(p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()}
    calls = []
    def fake(window):
        manifest = json.loads((artifact(tmp_path) / "manifest.json").read_bytes())
        anchor = manifest["previous_campaign_anchor"]
        assert anchor["partial_witness_sha256"] == pin
        assert anchor["consumed_window_starts"] == 6 and anchor["sealed_windows"] == 5
        assert anchor["unsealed_started_windows"] == 1 and anchor["aggregate_completion_present"] is False
        assert anchor["historical_failure_cause_established"] is False
        assert (artifact(tmp_path) / f"window-{len(calls):04d}-started.json").exists()
        calls.append(window); return response(window)
    result = run(tmp_path, pin, transport=fake)
    assert calls == list(WINDOWS) and result["all_registered_windows_observed"] is True
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert all(sha(Path(p).read_bytes()) == h for p, h in before.items())
    assert not (partial_root(tmp_path) / "complete.json").exists()
    assert not (partial_root(tmp_path) / "window-0005-complete.json").exists()
    done = json.loads((artifact(tmp_path) / "window-0000-complete.json").read_bytes())
    assert done["receipt"]["metadata_sha256"] == sha((artifact(tmp_path) / "window-0000-metadata.json").read_bytes())


@pytest.mark.parametrize("window", [m.genesis.REGISTERED_WINDOWS[1], m.legacy.REGISTERED_WINDOWS[150],
    *m.predecessor.REGISTERED_WINDOWS[:6], ("2019-02-28", "2019-03-01"), ("2026-08-01", "2026-08-01")])
def test_all_completed_refused_and_unsealed_months_refused_before_credentials(tmp_path, window):
    with pytest.raises(m.EarningsCampaignError, match="outside_frozen_support_envelope"):
        run(tmp_path, "a" * 64, windows=(window,))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("leaf", ["manifest.json", "window-0000-complete.json", "window-0005-response.json",
    "window-0005-metadata.json", "window-0005-started.json", "scope", "witness"])
def test_tampered_partial_witness_or_any_consumed_leaf_refuses_before_new_root(tmp_path, monkeypatch, leaf):
    pin = prior_fixture(tmp_path, monkeypatch)
    path = partial_root(tmp_path) / leaf
    if leaf == "scope":
        path = partial_root(tmp_path).parent.parent / "scopes" / (m.predecessor._fingerprint(m.predecessor.REGISTERED_WINDOWS[5]) + ".json")
    elif leaf == "witness": path = witness_path(tmp_path)
    path.write_bytes(b"private corrupt body")
    with pytest.raises(m.EarningsCampaignError) as exc:
        run(tmp_path, pin, transport=lambda w: pytest.fail("provider"))
    assert exc.value.failure["stage"] == "previous_anchor_preflight"
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()
    assert "private corrupt" not in json.dumps(exc.value.failure)


def test_fabricated_partial_aggregate_or_sixth_seal_refused(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    (partial_root(tmp_path) / "window-0005-complete.json").write_bytes(b"{}")
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, pin, transport=lambda w: pytest.fail("provider"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_missing_wrong_and_arbitrary_witness_pins_cannot_self_authorize(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    with pytest.raises(m.EarningsCampaignError): run(tmp_path, "0" * 64)
    fd = m._witness_directory(tmp_path)
    try:
        with pytest.raises(m.EarningsCampaignError, match="observed_partial_witness_pin_mismatch"):
            m._witness(tmp_path, fd, pin, fixture_only=False)
    finally: os.close(fd)
    for invalid in (None, "", "wrong", True):
        with pytest.raises(m.EarningsCampaignError, match="external_partial_witness_pin_required"):
            run(tmp_path, invalid)


def test_extra_witness_leaf_and_symlink_refused(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    wp = witness_path(tmp_path)
    (wp.parent / "alternate.json").write_bytes(b"{}")
    with pytest.raises(m.EarningsCampaignError): run(tmp_path, pin)
    (wp.parent / "alternate.json").unlink()
    raw = wp.read_bytes(); wp.unlink()
    alternate = tmp_path / "alternate-witness"; alternate.write_bytes(raw); wp.symlink_to(alternate)
    with pytest.raises(m.EarningsCampaignError): run(tmp_path, pin)


def test_sanitized_failure_seals_stage_class_errno_without_exception_text(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    publish = m._publish
    def fail(directory, name, value):
        if name == "window-0000-complete.json":
            raise OSError(errno.ENOSPC, TOKEN + "/PRIVATE/PATH")
        return publish(directory, name, value)
    monkeypatch.setattr(m, "_publish", fail)
    with pytest.raises(m.EarningsCampaignError) as exc:
        run(tmp_path, pin)
    failure = exc.value.failure
    assert failure["stage"] == "window_seal_publication" and failure["exception_class"] == "os_error"
    assert failure["errno_class"] == "disk_full" and failure["fixed_code"] == "unclassified_failure"
    assert failure["failure_journal_sealed"] is True
    journal = (artifact(tmp_path) / "failure.json").read_bytes()
    assert TOKEN.encode() not in journal and b"PRIVATE/PATH" not in journal
    assert json.loads(journal)["consumed_scope_count"] == 1
    assert not (artifact(tmp_path) / "complete.json").exists()
    assert not (artifact(tmp_path) / "window-0000-complete.json").exists()
    assert (artifact(tmp_path) / "window-0000-started.json").exists()
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, pin, campaign_id="ib-eodhd-campaign-v4-repeat", transport=lambda w: pytest.fail("provider"))


def test_old_exception_classes_are_distinct_and_never_stringified():
    class Unsafe(Exception):
        def __str__(self): raise AssertionError("must never stringify")
    for exc, expected in [(m.predecessor.EarningsCampaignError(TOKEN), "continuation3_error"),
        (m.legacy.EarningsCampaignError(TOKEN), "continuation2_error"), (Unsafe(TOKEN), "unclassified_exception")]:
        result = m._failure_details(exc, "previous_anchor_check", 1)
        assert result["exception_class"] == expected and result["fixed_code"] == "unclassified_failure"
        assert TOKEN not in json.dumps(result)
    result = m._failure_details(OSError(9999, TOKEN), TOKEN, True)
    assert result["stage"] == "unclassified_stage" and result["active_window_index"] is None
    assert result["errno_class"] == "other_os_error"


def test_unsafe_current_journal_cannot_be_repaired_to_write_failure(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    def fake(window):
        (artifact(tmp_path) / "unexpected-private-leaf").write_bytes(TOKEN.encode())
        return response(window)
    with pytest.raises(m.EarningsCampaignError) as exc: run(tmp_path, pin, transport=fake)
    assert exc.value.failure["stage"] == "current_journal_check"
    assert exc.value.failure["failure_journal_sealed"] is False
    assert not (artifact(tmp_path) / "failure.json").exists()
    assert TOKEN not in json.dumps(exc.value.failure)


def test_current_disk_budget_accounts_full_finite_raw_metadata_and_control(tmp_path, monkeypatch):
    class Info:
        f_frsize = 1
        f_bavail = m.MIN_FREE_BYTES + 89 * (m.MAX_BODY_BYTES + m.MAX_METADATA_BYTES + 3 * m.MAX_CONTROL_BYTES) + 3 * m.MAX_CONTROL_BYTES
    monkeypatch.setattr(m.os, "fstatvfs", lambda fd: Info())
    assert m._disk_reserve(-1, 89)["available_bytes_at_preflight"] == Info.f_bavail
    assert m._disk_reserve(-1, 89)["campaign_control_headroom_bytes"] == 3 * m.MAX_CONTROL_BYTES
    Info.f_bavail -= 1
    with pytest.raises(m.EarningsCampaignError, match="disk_reserve_insufficient"): m._disk_reserve(-1, 89)
    pin = prior_fixture(tmp_path, monkeypatch)
    Info.f_bavail = m.MIN_FREE_BYTES
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, pin, transport=lambda w: pytest.fail("provider"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("failure", ["http", "timeout", "envelope", "oversize", "echo"])
def test_transport_or_envelope_failure_stops_without_retry_or_body_retention(tmp_path, monkeypatch, failure):
    pin = prior_fixture(tmp_path, monkeypatch); calls = []
    def fake(window):
        calls.append(window)
        if failure == "http": return response(window, raw=TOKEN.encode(), status=403)
        if failure == "timeout": return response(window, raw=b"", status=None, complete=False, disposition="transport-timeout")
        if failure == "envelope": return response(window, raw=b'{"error":"private"}')
        if failure == "oversize": return response(window, raw=b"", complete=False, disposition="oversized-response")
        return response(window, raw=response(window).body.replace(b"nonessential-unknown", TOKEN.encode()))
    result = run(tmp_path, pin, transport=fake)
    assert calls == list(WINDOWS[:1]) and result["unattempted_windows_count"] == 1
    assert not (artifact(tmp_path) / "window-0000-response.json").exists()
    assert TOKEN.encode() not in b"".join(p.read_bytes() for p in artifact(tmp_path).iterdir())


def test_opaque_financial_lexemes_and_quarantine_source_ordinals():
    raw = response().body.replace(b'"actual":1.234567', b'"actual":1e999999')
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["metadata_accepted_rows"] == 1 and projection[0]["source_row_ordinal"] == 0
    assert not m._FINANCIAL.intersection(projection[0]) and "currency" not in projection[0]
    assert receipt["metadata_sha256"] is None


def test_fake_identity_cannot_enable_real_transport_or_arbitrary_witness_path(tmp_path):
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        m.run_continuation(CAMPAIGN, HEAD, tmp_path / "no-token", expected_partial_witness_sha256="a" * 64,
            owner_acknowledged_rotated_token=True, root=tmp_path, identity=lambda *a, **k: IDENTITY)
    with pytest.raises(TypeError):
        m.run_continuation(CAMPAIGN, HEAD, tmp_path / "no-token", expected_partial_witness_sha256="a" * 64,
            owner_acknowledged_rotated_token=True, witness_path=tmp_path / "anything")


@pytest.mark.parametrize("generation", ["genesis", "legacy", "predecessor", "current"])
def test_four_generation_locks_all_held_before_any_new_transport(tmp_path, monkeypatch, generation):
    pin = prior_fixture(tmp_path, monkeypatch)
    def fake(window):
        module = m if generation == "current" else getattr(m, generation)
        fd = os.open(tmp_path.joinpath(*module.ARTIFACT_PARTS, "campaign.lock"), os.O_RDONLY)
        try:
            with pytest.raises(BlockingIOError): m.fcntl.flock(fd, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
        finally: os.close(fd)
        return response(window)
    assert run(tmp_path, pin, windows=WINDOWS[:1], transport=fake)["observed_windows"] == 1


def test_legacy_low_level_exception_after_metadata_gets_distinct_safe_stage_record(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    original = m._previous_anchor
    def broken(*args, **kwargs):
        if (artifact(tmp_path) / "window-0000-metadata.json").exists():
            raise m.legacy.EarningsCampaignError(TOKEN + "/PRIVATE")
        return original(*args, **kwargs)
    monkeypatch.setattr(m, "_previous_anchor", broken)
    with pytest.raises(m.EarningsCampaignError) as exc: run(tmp_path, pin)
    assert exc.value.failure["stage"] == "previous_anchor_check"
    assert exc.value.failure["exception_class"] == "continuation2_error"
    assert exc.value.failure["failure_journal_sealed"] is True
    assert TOKEN.encode() not in (artifact(tmp_path) / "failure.json").read_bytes()


class Stream(io.BytesIO):
    def __init__(self, raw, status, url):
        super().__init__(raw)
        self.status, self.url, self.headers, self.read_calls = status, url, {}, 0
    def getcode(self): return self.status
    def geturl(self): return self.url
    def read(self, *args):
        self.read_calls += 1
        return super().read(*args)


def test_default_transport_exact_tls_no_proxy_non200_no_read_and_full_cooldown(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch, reported_real=True)
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_identity", lambda head, root=None: dict(IDENTITY))
    monkeypatch.setattr(m, "OBSERVED_PARTIAL_WITNESS_SHA256", pin)
    tick, calls, streams = [0.0], [], []
    monkeypatch.setattr(m.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(m.time, "sleep", lambda delay: tick.__setitem__(0, tick[0] + delay))
    class Opener:
        def open(self, item, timeout):
            index = len(calls)
            calls.append((tick[0], item, timeout))
            stream = Stream(response(WINDOWS[0]).body if index == 0 else TOKEN.encode(),
                            200 if index == 0 else 403, item.full_url)
            streams.append(stream); return stream
    def build(*handlers):
        assert handlers[0].proxies == {} and isinstance(handlers[1], m._DenyRedirect)
        assert handlers[2]._context.verify_mode == ssl.CERT_REQUIRED
        return Opener()
    # Install the genuine transport seam patch before the live code reference.
    monkeypatch.setattr(m.request, "build_opener", build)
    token = tmp_path / "invented-token4"; token.write_bytes(TOKEN.encode()); token.chmod(0o600)
    result = m.run_continuation(CAMPAIGN, HEAD, token, expected_partial_witness_sha256=pin,
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)
    assert len(calls) == 2 and calls[1][0] - calls[0][0] >= 1.0
    assert result["observed_windows"] == 1 and result["unattempted_windows_count"] == 87
    assert calls[0][1].full_url == m._url(WINDOWS[0]).replace("<redacted>", TOKEN)
    assert "symbols=" not in calls[0][1].full_url and calls[0][1].get_method() == "GET" and calls[0][2] == 15
    assert streams[1].read_calls == 0 and all(stream.closed for stream in streams)


@pytest.mark.parametrize("headers,raw,code", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"private", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Encoding": "gzip"}, b"private", "unsupported-content-encoding"),
    ({"Content-Length": "-1"}, b"private", "invalid-content-length"),
])
def test_response_cap_and_encoding_fail_closed(headers, raw, code):
    stream = Stream(raw, 200, "invented"); stream.headers = headers
    assert m._read_window_bounded(stream, 200).disposition == code


def test_large_metadata_and_control_caps_do_not_reintroduce_four_mib_boundary(tmp_path):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        body = {"invented_metadata": "x" * (5 * 1024**2)}
        assert m._publish(fd, "window-0000-metadata.json", body) == sha(encoded(body))
        assert len(m._read_leaf(fd, "window-0000-metadata.json", limit=m.MAX_METADATA_BYTES)) > 4 * 1024**2
        with pytest.raises(m.EarningsCampaignError, match="immutable_json_byte_bound"):
            m._publish(fd, "control.json", body)
        assert not (tmp_path / "control.json").exists()
    finally: os.close(fd)


def test_whitelist_preserves_known_disk_code_but_rejects_untyped_stage():
    result = m._failure_details(m.EarningsCampaignError("worst_case_capture_disk_reserve_insufficient"), "window_disk_preflight", 0)
    assert result["fixed_code"] == "worst_case_capture_disk_reserve_insufficient"
    assert m._failure_details(ValueError(TOKEN), {}, 0)["stage"] == "unclassified_stage"


# Section 194 (Claude review): continuation5's fixture-root guard, added to this version.
def test_fixture_transport_cannot_target_the_real_lane_registry():
    with pytest.raises(m.EarningsCampaignError, match="^fixture_transport_actual_lane_root_refused$"):
        m.run_continuation("ib-eodhd-campaign-invented-lane", "a" * 40, Path("/invented-token-never-read"), owner_acknowledged_rotated_token=True, expected_partial_witness_sha256="0" * 64, root=m.LANE_ROOT, identity=lambda *a, **k: pytest.fail("identity"), transport=lambda window: pytest.fail("provider"))


# Section 194 (Claude review): the module's own late refusals keep their fixed code.
@pytest.mark.parametrize("code", ["completed_or_ambiguous_window_cannot_repeat", "concurrent_campaign_refused",
                                  "campaign_cannot_resume", "scope_registry_refused",
                                  "invalid_transport_result_started_preserved", "partial_scope_external_pin_mismatch"])
def test_own_fixed_refusal_codes_are_not_relabelled_unclassified(code):
    details = m._failure_details(m.EarningsCampaignError(code), "scope_reservation", 0)
    assert details["fixed_code"] == code and details["exception_class"].endswith("_error")
