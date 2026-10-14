"""Invented partial-control custody; OS process-tree network denial required."""
import errno
import io
import json
import os
from pathlib import Path
import ssl
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX Calendar custody; Windows port deferred")
from research import insider_buying_eodhd_earnings_continuation5 as m
from test_insider_buying_eodhd_earnings_continuation4 import prior_fixture as v4_fixture

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
    "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64}
TOKEN = "invented_continuation5_calendar_token_1234"
CAMPAIGN = "ib-eodhd-campaign-v5-invented"
WINDOWS = m.REGISTERED_WINDOWS[:2]
ROW = {"code": "FIXA.US", "report_date": "2020-03-01", "date": "2019-12-31",
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
    """All four invented predecessor generations; no real paid source rows."""
    v3_pin=v4_fixture(tmp_path,monkeypatch,reported_real=reported_real)
    monkeypatch.setattr(m.predecessor,"OBSERVED_PARTIAL_WITNESS_SHA256",v3_pin)
    gp=tmp_path.joinpath(*m.genesis.ARTIFACT_PARTS)
    vp=tmp_path.joinpath(*m.legacy.ARTIFACT_PARTS)
    ap=tmp_path.joinpath(*m.ancestor.ARTIFACT_PARTS)
    gl,vl,al=(os.open(p/"campaign.lock",os.O_RDONLY) for p in (gp,vp,ap))
    wd=m.predecessor._witness_directory(tmp_path)
    try:
        anchor=m.predecessor._previous_anchor(tmp_path,m.REGISTERED_WINDOWS,vl,gl,al,wd,v3_pin,fixture_only=not reported_real)
    finally:
        for fd in (gl,vl,al,wd):os.close(fd)
    parent=tmp_path.joinpath(*m.predecessor.ARTIFACT_PARTS);parent.mkdir(mode=0o700)
    (parent/"scopes").mkdir(mode=0o700);(parent/"campaigns").mkdir(mode=0o700)
    (parent/"campaign.lock").write_bytes(b"");(parent/"campaign.lock").chmod(0o600)
    directory=partial_root(tmp_path);directory.mkdir(mode=0o700)
    leaves,scopes,counts={}, {}, []
    def publish(path,value,*,raw=False):
        data=value if raw else encoded(value)
        path.write_bytes(data);path.chmod(0o600)
        if path.parent==directory:
            info=path.stat()
            leaves[path.name]={"bytes":len(data),"sha256":sha(data),"version":{name:str(getattr(info,name)) for name in
                ("st_dev","st_ino","st_mode","st_nlink","st_size","st_mtime_ns","st_ctime_ns")}}
        return sha(data)
    manifest={"schema":m.predecessor.SCHEMA,"profile":m.predecessor.PROFILE,"campaign_id":m.PARTIAL_CAMPAIGN_ID,
        "identity":IDENTITY,"previous_campaign_anchor":anchor,
        "windows":[list(w) for w in m.predecessor.REGISTERED_WINDOWS],
        "window_scope_sha256":[m.predecessor._fingerprint(w) for w in m.predecessor.REGISTERED_WINDOWS],
        "fixture_only":not reported_real,"maximum_attempts_per_window":1,"retry_resume_permitted":False,
        **{name:False for name in m.FALSE_FLAGS}}
    manifest_sha=publish(directory/"manifest.json",manifest)
    for index,window in enumerate(m.predecessor.REGISTERED_WINDOWS[:12]):
        prefix=f"window-{index:04d}";scope_name=m.predecessor._fingerprint(window)+".json"
        scope_sha=publish(parent/"scopes"/scope_name,{"schema":m.predecessor.SCHEMA,
            "scope":m.predecessor._scope(window),"campaign_id":m.PARTIAL_CAMPAIGN_ID,
            "reserved_at_utc":"2026-10-14T00:00:00Z","maximum_attempts":1})
        scopes[scope_name]=scope_sha
        start_sha=publish(directory/(prefix+"-started.json"),{"schema":m.predecessor.SCHEMA,
            "index":index,"window":list(window),"manifest_sha256":manifest_sha,
            "scope_reservation_sha256":scope_sha,"maximum_attempts":1})
        raw=b"INVENTED-OLD-RESPONSE-NOT-DECODED"
        body_sha=publish(directory/(prefix+"-response.json"),raw,raw=True)
        metadata_sha=publish(directory/(prefix+"-metadata.json"),b"INVENTED-OLD-METADATA-NOT-DECODED",raw=True)
        if index<11:
            receipt={"http_status":200,"transport_invocation_count":1,"calendar_window_observed":True,
                "response_body_retained":True,"body_sha256":body_sha,"body_size_bytes":len(raw),
                "metadata_sha256":metadata_sha,"sample_rows":1,"metadata_accepted_rows":1,
                "quarantined_rows":0,**{name:False for name in m.FALSE_FLAGS}}
            done_sha=publish(directory/(prefix+"-complete.json"),{"schema":m.predecessor.SCHEMA,
                "index":index,"window":list(window),"manifest_sha256":manifest_sha,
                "started_sha256":start_sha,"scope_reservation_sha256":scope_sha,"receipt":receipt})
            counts.append({"index":index,"window":list(window),"complete_sha256":done_sha,
                "sample_rows":1,"metadata_accepted_rows":1,"quarantined_rows":0})
    details={"active_window_index":11,"consumed_scope_count":12,"errno_class":None,"exception_class":"custody_helper_error",
        "fixed_code":"custody_leaf_changed","stage":"current_journal_check","window_completions":11}
    failure_sha=publish(directory/"failure.json",{"schema":m.predecessor.SCHEMA,"kind":"sanitized_stage_failure",
        "campaign_id":m.PARTIAL_CAMPAIGN_ID,"manifest_sha256":manifest_sha,**details,
        "aggregate_completion_manufactured":False,"exception_text_retained":False,
        "credential_path_body_or_values_retained":False,**{name:False for name in m.FALSE_FLAGS}})
    witness={"schema":m.WITNESS_SCHEMA,"observed_at_utc":"2026-10-14T00:00:00Z",
        "execution_head":HEAD,"manifest_sha256":manifest_sha,"campaign_id":m.PARTIAL_CAMPAIGN_ID,
        "journal_leaf_count":49,"consumed_scope_count":12,"sealed_window_count":11,
        "unsealed_started_window_count":1,"campaign_completion_present":False,
        "unattempted_suffix_windows":77,"next_unattempted_window":list(m.REGISTERED_WINDOWS[0]),
        "last_unattempted_window":list(m.REGISTERED_WINDOWS[-1]),"source_inventory_sha256":IDENTITY["source_inventory_sha256"],
        "previous_v2_complete_sha256":m.ancestor.PREVIOUS_COMPLETE_SHA256,
        "previous_partial_v3_witness_sha256":v3_pin,"failure_details":details,"failure_sha256":failure_sha,
        "journal_leaf_sha256_bytes_versions":leaves,"consumed_scope_sha256":scopes,"sealed_window_counts":counts,
        "raw_financial_bodies_decoded":False,"paid_metadata_rows_decoded":False,"credential_read":False,
        "network_write_fork_denied":True,"locks_shared_read_only":True,"all_readiness_authority_false":True,
        "current_leaf_versions_unchanged_during_observation":True,"current_named_journal_reattach_passed_twice":True,
        "previous_anchor_replay_passed_twice":True,"historical_custody_change_cause_established":False,
        "aggregate_completion_manufactured":False,"sealed_metadata_accepted_rows":11,"sealed_quarantined_rows":0,
        "sealed_source_rows":11,"sealed_raw_body_bytes":11*len(raw),
        "unsealed_started_windows":[{"index":11,"window":list(m.predecessor.REGISTERED_WINDOWS[11]),"raw_present":True,"metadata_present":True}]}
    wp=witness_path(tmp_path);wp.parent.mkdir(mode=0o700,parents=True);wp.parent.parent.chmod(0o700)
    pin=publish(wp,witness)
    monkeypatch.setattr(m,"PARTIAL_EXECUTION_HEAD",HEAD)
    monkeypatch.setattr(m,"PARTIAL_SOURCE_INVENTORY_SHA256",IDENTITY["source_inventory_sha256"])
    monkeypatch.setattr(m,"PARTIAL_MANIFEST_SHA256",manifest_sha)
    monkeypatch.setattr(m,"PARTIAL_FAILURE_SHA256",failure_sha)
    return pin


def run(tmp_path, witness_sha, *, windows=WINDOWS, transport=None, campaign_id=CAMPAIGN, **kwargs):
    token = tmp_path / "invented-token5"; token.write_bytes(TOKEN.encode()); token.chmod(0o600)
    return m.run_continuation(campaign_id, HEAD, token, windows=windows,
        expected_partial_witness_sha256=witness_sha, owner_acknowledged_rotated_token=True,
        root=tmp_path, identity=lambda *a, **k: dict(IDENTITY),
        transport=transport or (lambda window: response(window)), **kwargs)


def test_exact77_never_started_suffix_caps_and_new_schema():
    assert len(m.REGISTERED_WINDOWS) == 77 and m.REGISTERED_WINDOWS == m.predecessor.REGISTERED_WINDOWS[12:]
    assert m.REGISTERED_WINDOWS[0] == ("2020-03-01", "2020-03-31")
    assert m.REGISTERED_WINDOWS[-1] == ("2026-07-01", "2026-07-31")
    assert m.MAX_BODY_BYTES == 16 * 1024**2 and m.MAX_METADATA_BYTES == 256 * 1024**2
    assert m.MAX_CONTROL_BYTES == 1024**2 and m.MAX_ROWS == 200_000 and m.MAX_WITNESS_BYTES == 32768
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
        assert anchor["consumed_window_starts"] == 12 and anchor["sealed_windows"] == 11
        assert anchor["unsealed_started_windows"] == 1 and anchor["aggregate_completion_present"] is False
        assert anchor["historical_custody_change_cause_established"] is False
        assert (artifact(tmp_path) / f"window-{len(calls):04d}-started.json").exists()
        calls.append(window); return response(window)
    result = run(tmp_path, pin, transport=fake)
    assert calls == list(WINDOWS) and result["all_registered_windows_observed"] is True
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert all(sha(Path(p).read_bytes()) == h for p, h in before.items())
    assert not (partial_root(tmp_path) / "complete.json").exists()
    assert not (partial_root(tmp_path) / "window-0011-complete.json").exists()
    done = json.loads((artifact(tmp_path) / "window-0000-complete.json").read_bytes())
    assert done["receipt"]["metadata_sha256"] == sha((artifact(tmp_path) / "window-0000-metadata.json").read_bytes())


@pytest.mark.parametrize("window", [m.genesis.REGISTERED_WINDOWS[1], m.legacy.REGISTERED_WINDOWS[150],
    *m.ancestor.REGISTERED_WINDOWS[:6], *m.predecessor.REGISTERED_WINDOWS[:12], ("2020-02-29", "2020-03-01"), ("2026-08-01", "2026-08-01")])
def test_all_completed_refused_and_unsealed_months_refused_before_credentials(tmp_path, window):
    with pytest.raises(m.EarningsCampaignError, match="outside_frozen_support_envelope"):
        run(tmp_path, "a" * 64, windows=(window,))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("leaf", ["manifest.json", "window-0000-complete.json", "window-0011-response.json",
    "window-0011-metadata.json", "window-0011-started.json", "failure.json", "scope", "witness"])
def test_tampered_partial_witness_or_any_consumed_leaf_refuses_before_new_root(tmp_path, monkeypatch, leaf):
    pin = prior_fixture(tmp_path, monkeypatch)
    path = partial_root(tmp_path) / leaf
    if leaf == "scope":
        path = partial_root(tmp_path).parent.parent / "scopes" / (m.predecessor._fingerprint(m.predecessor.REGISTERED_WINDOWS[11]) + ".json")
    elif leaf == "witness": path = witness_path(tmp_path)
    path.write_bytes(b"private corrupt body")
    with pytest.raises(m.EarningsCampaignError) as exc:
        run(tmp_path, pin, transport=lambda w: pytest.fail("provider"))
    assert exc.value.failure["stage"] == "previous_anchor_preflight"
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()
    assert "private corrupt" not in json.dumps(exc.value.failure)


@pytest.mark.parametrize("fabricated", ["complete.json", "window-0011-complete.json"])
def test_fabricated_partial_aggregate_or_twelfth_seal_refused(tmp_path, monkeypatch, fabricated):
    pin = prior_fixture(tmp_path, monkeypatch)
    (partial_root(tmp_path) / fabricated).write_bytes(b"{}")
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
        run(tmp_path, pin, campaign_id="ib-eodhd-campaign-v5-repeat", transport=lambda w: pytest.fail("provider"))


def test_old_exception_classes_are_distinct_and_never_stringified():
    class Unsafe(Exception):
        def __str__(self): raise AssertionError("must never stringify")
    for exc, expected in [(m.predecessor.EarningsCampaignError(TOKEN), "continuation4_error"),
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
        f_bavail = m.MIN_FREE_BYTES + 77 * (m.MAX_BODY_BYTES + m.MAX_METADATA_BYTES + 3 * m.MAX_CONTROL_BYTES) + 3 * m.MAX_CONTROL_BYTES
    monkeypatch.setattr(m.os, "fstatvfs", lambda fd: Info())
    assert m._disk_reserve(-1, 77)["available_bytes_at_preflight"] == Info.f_bavail
    assert m._disk_reserve(-1, 77)["campaign_control_headroom_bytes"] == 3 * m.MAX_CONTROL_BYTES
    Info.f_bavail -= 1
    with pytest.raises(m.EarningsCampaignError, match="disk_reserve_insufficient"): m._disk_reserve(-1, 77)
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


@pytest.mark.parametrize("generation", ["genesis", "legacy", "ancestor", "predecessor", "current"])
def test_five_generation_locks_all_held_before_any_new_transport(tmp_path, monkeypatch, generation):
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
            tick[0] += 0.25  # Finite transport time is not part of cooldown.
            streams.append(stream); return stream
    def build(*handlers):
        assert handlers[0].proxies == {} and isinstance(handlers[1], m._DenyRedirect)
        assert handlers[2]._context.verify_mode == ssl.CERT_REQUIRED
        return Opener()
    # Install the genuine transport seam patch before the live code reference.
    monkeypatch.setattr(m.request, "build_opener", build)
    token = tmp_path / "invented-token5"; token.write_bytes(TOKEN.encode()); token.chmod(0o600)
    result = m.run_continuation(CAMPAIGN, HEAD, token, expected_partial_witness_sha256=pin,
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)
    assert len(calls) == 2 and calls[0][0] == 0.0 and calls[1][0] == 1.25
    assert result["observed_windows"] == 1 and result["unattempted_windows_count"] == 75
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


def reader_fixture(tmp_path):
    leaf = tmp_path / "leaf.json"
    raw = b"invented fixed custody bytes"
    leaf.write_bytes(raw); leaf.chmod(0o600)
    return leaf, raw, os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)


def test_reader_allows_one_metadata_change_only_after_complete_hash_bound_reattach(tmp_path, monkeypatch):
    leaf, raw, fd = reader_fixture(tmp_path)
    original = m._version; calls, opened, attachments = [0], [0], []
    real_open = m.os.open
    def version(info):
        calls[0] += 1
        result = original(info)
        return (*result[:-1], result[-1] + 1) if calls[0] == 2 else result
    def counted(name, *args, **kwargs):
        if name == "leaf.json": opened[0] += 1
        return real_open(name, *args, **kwargs)
    monkeypatch.setattr(m, "_version", version); monkeypatch.setattr(m.os, "open", counted)
    try:
        result = m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw),
            expected_bytes=len(raw), attached=lambda: attachments.append(True))
        assert result == raw and opened[0] == 2 and len(attachments) >= 4
        assert leaf.read_bytes() == raw
    finally: os.close(fd)


def test_reader_refuses_perpetual_metadata_churn_on_exact_third_local_read(tmp_path, monkeypatch):
    _, raw, fd = reader_fixture(tmp_path)
    original = m._version; calls, opened = [0], [0]
    real_open = m.os.open
    def version(info):
        calls[0] += 1
        result = original(info)
        return (*result[:-1], result[-1] + calls[0])
    def counted(name, *args, **kwargs):
        if name == "leaf.json": opened[0] += 1
        return real_open(name, *args, **kwargs)
    monkeypatch.setattr(m, "_version", version); monkeypatch.setattr(m.os, "open", counted)
    try:
        with pytest.raises(m.EodhdDemoError, match="custody_leaf_changed"):
            m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw), attached=lambda: None)
        assert opened[0] == 3 and m.LOCAL_REATTACH_ATTEMPTS == 3
    finally: os.close(fd)


@pytest.mark.parametrize("change", ["inode", "mode", "size", "link"])
def test_reader_never_accepts_structural_change_between_local_attempts(tmp_path, monkeypatch, change):
    leaf, raw, fd = reader_fixture(tmp_path)
    original = m._version; calls, attachments = [0], [0]
    def version(info):
        calls[0] += 1
        result = original(info)
        return (*result[:-1], result[-1] + 1) if calls[0] == 2 else result
    def attach():
        attachments[0] += 1
        if attachments[0] == 3:
            if change == "inode":
                other = tmp_path / "replace.json"; other.write_bytes(raw); other.chmod(0o600); other.replace(leaf)
            elif change == "mode": leaf.chmod(0o640)
            elif change == "size": leaf.write_bytes(raw + b"x")
            else: os.link(leaf, tmp_path / "extra-link")
    monkeypatch.setattr(m, "_version", version)
    try:
        with pytest.raises((m.EarningsCampaignError, m.EodhdDemoError)):
            m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw), attached=attach)
        assert attachments[0] == 3
    finally: os.close(fd)


def test_reader_hash_mismatch_is_immediate_without_local_retry(tmp_path, monkeypatch):
    _, raw, fd = reader_fixture(tmp_path); opened = [0]; real_open = m.os.open
    def counted(name, *args, **kwargs):
        if name == "leaf.json": opened[0] += 1
        return real_open(name, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", counted)
    try:
        with pytest.raises(m.EarningsCampaignError, match="custody_expected_hash_refused"):
            m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256="0" * 64, attached=lambda: None)
        assert opened[0] == 1
    finally: os.close(fd)


def test_reader_directory_detachment_never_reads_an_orphan_or_reattaches_by_guess(tmp_path):
    directory = tmp_path / "named"; directory.mkdir(mode=0o700)
    leaf, raw, fd = reader_fixture(directory)
    directory.rename(tmp_path / "detached"); directory.mkdir(mode=0o700)
    def attached():
        opened = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            named, held = os.fstat(opened), os.fstat(fd)
            m._require((named.st_dev, named.st_ino) == (held.st_dev, held.st_ino), "partial_named_root_detached")
        finally: os.close(opened)
    try:
        with pytest.raises(m.EarningsCampaignError, match="partial_named_root_detached"):
            m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw), attached=attached)
    finally: os.close(fd)


def test_reader_non_metadata_failure_does_not_retry_or_interpret_error_text(tmp_path, monkeypatch):
    _, raw, fd = reader_fixture(tmp_path); calls = [0]
    def refused(*args, **kwargs):
        calls[0] += 1
        raise m.EodhdDemoError("custody_leaf_refused")
    monkeypatch.setattr(m, "_regular_leaf", refused)
    try:
        with pytest.raises(m.EodhdDemoError, match="custody_leaf_refused"):
            m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw), attached=lambda: None)
        assert calls[0] == 1
    finally: os.close(fd)


def test_custody_metadata_retry_does_not_add_any_provider_attempt(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch); original = m._version; calls, dispatches = [0], []
    def version(info):
        calls[0] += 1
        result = original(info)
        return (*result[:-1], result[-1] + 1) if calls[0] == 2 else result
    monkeypatch.setattr(m, "_version", version)
    def transport(window): dispatches.append(window); return response(window)
    result = run(tmp_path, pin, windows=WINDOWS[:1], transport=transport)
    assert dispatches == list(WINDOWS[:1]) and result["transport_invocation_count"] == 1
    manifest = json.loads((artifact(tmp_path) / "manifest.json").read_bytes())
    assert manifest["maximum_local_custody_read_reattachments"] == 3
    assert manifest["local_read_reattachment_is_provider_retry"] is False


def test_current_journal_uses_exact_registered_caps_for_every_leaf_kind(tmp_path, monkeypatch):
    pin = prior_fixture(tmp_path, monkeypatch)
    run(tmp_path, pin, windows=WINDOWS[:1])
    parent = m._root_directory(tmp_path, create=False)
    scopes = m._directory(parent, "scopes", create=False)
    campaigns = m._directory(parent, "campaigns", create=False)
    directory = m._directory(campaigns, CAMPAIGN, create=False)
    lock = os.open("campaign.lock", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    published = {name: sha((artifact(tmp_path) / name).read_bytes()) for name in os.listdir(directory)}
    reserved = {name: sha((tmp_path.joinpath(*m.ARTIFACT_PARTS, "scopes", name)).read_bytes())
                for name in os.listdir(scopes)}
    original, observed = m._read_expected_leaf, {}
    def bounded(fd, name, **kwargs):
        observed[name] = kwargs["limit"]
        return original(fd, name, **kwargs)
    monkeypatch.setattr(m, "_read_expected_leaf", bounded)
    try:
        m._check_journal(tmp_path, parent, scopes, campaigns, directory, CAMPAIGN,
                         published, reserved, lock)
        assert observed["window-0000-metadata.json"] == m.MAX_METADATA_BYTES
        assert observed["window-0000-response.json"] == m.MAX_BODY_BYTES
        assert all(limit == m.MAX_CONTROL_BYTES for name, limit in observed.items()
                   if not name.endswith(("-metadata.json", "-response.json")))
    finally:
        for fd in (lock, directory, campaigns, scopes, parent): os.close(fd)


@pytest.mark.parametrize("private", [True, False])
def test_private_expected_read_refuses_wrong_uid_but_public_source_read_does_not(tmp_path, monkeypatch, private):
    _, raw, fd = reader_fixture(tmp_path)
    actual_stat = m.os.stat
    def altered(name, *args, **kwargs):
        info = actual_stat(name, *args, **kwargs)
        if name == "leaf.json":
            fields = {field: getattr(info, field) for field in (
                "st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_uid", "st_mtime_ns", "st_ctime_ns")}
            fields["st_uid"] = os.geteuid() + 1
            return SimpleNamespace(**fields)
        return info
    monkeypatch.setattr(m.os, "stat", altered)
    try:
        if private:
            with pytest.raises(m.EarningsCampaignError, match="private_custody_owner_refused"):
                m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw),
                    attached=lambda: None, private=True)
        else:
            assert m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw),
                attached=lambda: None, private=False) == raw
    finally: os.close(fd)


def test_private_uid_change_between_local_reattachments_refuses_immediately(tmp_path, monkeypatch):
    _, raw, fd = reader_fixture(tmp_path)
    actual_stat, original_version, stats, versions = m.os.stat, m._version, [0], [0]
    def altered(name, *args, **kwargs):
        info = actual_stat(name, *args, **kwargs)
        if name == "leaf.json":
            stats[0] += 1
            if stats[0] == 3:
                fields = {field: getattr(info, field) for field in (
                    "st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_uid", "st_mtime_ns", "st_ctime_ns")}
                fields["st_uid"] = os.geteuid() + 1
                return SimpleNamespace(**fields)
        return info
    def version(info):
        versions[0] += 1
        result = original_version(info)
        return (*result[:-1], result[-1] + 1) if versions[0] == 2 else result
    monkeypatch.setattr(m.os, "stat", altered); monkeypatch.setattr(m, "_version", version)
    try:
        with pytest.raises(m.EarningsCampaignError, match="private_custody_owner_refused"):
            m._read_expected_leaf(fd, "leaf.json", limit=1024, expected_sha256=sha(raw), attached=lambda: None)
        assert stats[0] == 3
    finally: os.close(fd)


@pytest.mark.parametrize("alias", ["literal", "symlink", "case"])
def test_fixture_transport_cannot_target_actual_lane_or_alias_before_any_identity_or_credential(tmp_path, alias):
    root = m.LANE_ROOT
    if alias == "symlink":
        root = tmp_path / "invented-lane-alias"
        root.symlink_to(m.LANE_ROOT, target_is_directory=True)
    elif alias == "case":
        root = m.LANE_ROOT.with_name(m.LANE_ROOT.name.upper())
        if not root.exists() or not root.samefile(m.LANE_ROOT):
            pytest.skip("case-alias exists only on a case-insensitive filesystem")
    with pytest.raises(m.EarningsCampaignError, match="fixture_transport_actual_lane_root_refused"):
        m.run_continuation(CAMPAIGN, HEAD, tmp_path / "never-read-invented-token",
            windows=WINDOWS, owner_acknowledged_rotated_token=True,
            expected_partial_witness_sha256="a" * 64, root=root,
            identity=lambda *args, **kwargs: pytest.fail("identity must not run at actual fixture root"),
            transport=lambda window: pytest.fail("provider must not run at actual fixture root"))
