"""Invented journals/rows/tokens only; enforce OS process-tree network denial."""
import hashlib
import io
import json
import os
from pathlib import Path
import ssl

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX Calendar custody; Windows port deferred")

from research import insider_buying_eodhd_earnings_continuation as m
from research import insider_buying_eodhd_earnings_campaign as old

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
            "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64}
TOKEN = "invented_continuation_calendar_token_1234"
CAMPAIGN = "ib-eodhd-campaign-continuation-invented"
WINDOWS = (("2006-02-01", "2006-02-28"), ("2006-03-01", "2006-03-31"), ("2006-04-01", "2006-04-30"))
ROW = {"code": "AAPL.US", "report_date": "2006-02-08", "date": "2005-12-31",
       "before_after_market": "AfterMarket", "currency": "USD",
       "actual": 1.234567, "estimate": 2, "difference": -0.765433, "percent": -38.27165}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def payload(window=WINDOWS[0], rows=None):
    return {"type": "Earnings", "description": "Historical and upcoming Earnings",
            "from": window[0], "to": window[1], "earnings":
            [{**ROW, "report_date": window[0]}] if rows is None else rows}


def response(window=WINDOWS[0], raw=None, status=200, complete=True, disposition=None):
    return m.ProviderMetadataResponse(status, encoded(payload(window)) if raw is None else raw, complete, disposition)


def token_file(tmp_path):
    path = tmp_path / "invented-token"
    path.write_bytes(TOKEN.encode())
    path.chmod(0o600)
    return path


def old_artifact(tmp_path):
    return tmp_path.joinpath(*old.ARTIFACT_PARTS, "campaigns", m.PREVIOUS_CAMPAIGN_ID)


def artifact(tmp_path, campaign_id=CAMPAIGN):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, "campaigns", campaign_id)


def prior_fixture(tmp_path, monkeypatch, *, reported_real=False):
    def transport(window):
        row = {**ROW, "report_date": window[0], "date": "2005-09-30"}
        if window == old.REGISTERED_WINDOWS[1]:
            row["currency"] = "invented-nonessential-variant"
        return response(window, raw=encoded(payload(window, [row])))
    old.run_campaign(m.PREVIOUS_CAMPAIGN_ID, HEAD, token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=lambda *a, **k: IDENTITY,
        transport=transport, clock=lambda: "2026-10-13T00:00:00Z")
    directory = old_artifact(tmp_path)
    if reported_real:
        # Explicitly invented control-image fixture, never a real provider run.
        manifest = json.loads((directory / "manifest.json").read_bytes())
        manifest["fixture_only"] = False
        (directory / "manifest.json").write_bytes(encoded(manifest))
        manifest_sha = hashlib.sha256(encoded(manifest)).hexdigest()
        complete = json.loads((directory / "complete.json").read_bytes())
        complete["fixture_only"] = False
        complete["manifest_sha256"] = manifest_sha
        for index in range(2):
            prefix = f"window-{index:04d}"
            started = json.loads((directory / (prefix + "-started.json")).read_bytes())
            started["manifest_sha256"] = manifest_sha
            (directory / (prefix + "-started.json")).write_bytes(encoded(started))
            done = json.loads((directory / (prefix + "-complete.json")).read_bytes())
            done["manifest_sha256"] = manifest_sha
            done["started_sha256"] = hashlib.sha256(encoded(started)).hexdigest()
            (directory / (prefix + "-complete.json")).write_bytes(encoded(done))
            complete["window_results"][index]["complete_sha256"] = hashlib.sha256(encoded(done)).hexdigest()
        (directory / "complete.json").write_bytes(encoded(complete))
    monkeypatch.setattr(m, "PREVIOUS_COMPLETE_SHA256", hashlib.sha256((directory / "complete.json").read_bytes()).hexdigest())
    monkeypatch.setattr(m, "PREVIOUS_MANIFEST_SHA256", hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest())
    monkeypatch.setattr(m, "PREVIOUS_EXECUTION_HEAD", HEAD)
    monkeypatch.setattr(m, "PREVIOUS_SOURCE_INVENTORY_SHA256", IDENTITY["source_inventory_sha256"])
    monkeypatch.setattr(m, "PREVIOUS_METADATA_SHA256", hashlib.sha256((directory / "window-0000-metadata.json").read_bytes()).hexdigest())
    return {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.joinpath(*old.ARTIFACT_PARTS).rglob("*") if path.is_file()}


def run(tmp_path, *, windows=WINDOWS, transport=None, campaign_id=CAMPAIGN, **kwargs):
    return m.run_continuation(campaign_id, HEAD, token_file(tmp_path), windows=windows,
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=lambda *a, **k: dict(IDENTITY),
        transport=transport or (lambda window: response(window)), clock=lambda: "2026-10-13T00:00:00Z", **kwargs)


def test_exact_246_windows_omit_both_previous_starts_and_preserve_frozen_v1():
    assert len(m.REGISTERED_WINDOWS) == 246
    assert m.REGISTERED_WINDOWS == old.REGISTERED_WINDOWS[2:]
    assert m.REGISTERED_WINDOWS[0] == ("2006-02-01", "2006-02-28")
    assert m.REGISTERED_WINDOWS[-1] == ("2026-07-01", "2026-07-31")
    assert m.SCHEMA != old.SCHEMA and m.ARTIFACT_PARTS != old.ARTIFACT_PARTS
    assert "research/insider_buying_eodhd_earnings_campaign.py" in m.SOURCE_FILES


def test_hash_bound_prior_root_preserved_new_start_fsynced_before_transport(tmp_path, monkeypatch):
    previous = prior_fixture(tmp_path, monkeypatch)
    calls, fsyncs = [], []
    real_fsync = m.os.fsync
    monkeypatch.setattr(m.os, "fsync", lambda fd: (fsyncs.append(fd), real_fsync(fd))[1])
    def transport(window):
        directory = artifact(tmp_path)
        assert (directory / "manifest.json").exists()
        assert (directory / f"window-{len(calls):04d}-started.json").exists()
        assert not (directory / f"window-{len(calls):04d}-complete.json").exists()
        manifest = json.loads((directory / "manifest.json").read_bytes())
        assert manifest["previous_campaign_anchor"]["complete_sha256"] == m.PREVIOUS_COMPLETE_SHA256
        assert len(manifest["previous_campaign_anchor"]["scope_sha256"]) == 2
        assert len(fsyncs) >= 6
        calls.append(window)
        return response(window)
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS)
    assert result["source_rows"] == result["metadata_accepted_rows"] == 3
    assert result["quarantined_rows"] == 0
    assert result["all_registered_windows_observed"]
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert all((tmp_path / path).read_bytes() == raw for path, raw in previous.items())
    assert TOKEN not in json.dumps(result) and "1.234567" not in json.dumps(result)
    metadata = json.loads((artifact(tmp_path) / "window-0000-metadata.json").read_bytes())
    complete = json.loads((artifact(tmp_path) / "complete.json").read_bytes())
    assert complete["window_results"][0]["receipt"]["metadata_sha256"] == hashlib.sha256(
        (artifact(tmp_path) / "window-0000-metadata.json").read_bytes()).hexdigest()
    assert metadata["metadata_acceptance_is_source_coverage_or_identity_admission"] is False
    assert metadata["rows"][0]["source_row_ordinal"] == 0
    assert metadata["rows"][0]["metadata_accepted"] is True
    assert artifact(tmp_path).stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in artifact(tmp_path).iterdir())


@pytest.mark.parametrize("currency", [None, "GBX", "US Dollar", "UNKNOWN", "usd", [], {}, 17, True])
def test_nonessential_currency_never_discards_valid_raw_or_affects_projection(currency):
    raw = encoded(payload(rows=[{**ROW, "currency": currency}]))
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["calendar_window_observed"] and receipt["response_body_retained"]
    assert receipt["body_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["metadata_accepted_rows"] == 1 and receipt["quarantined_rows"] == 0
    assert projection[0]["metadata_accepted"] and "currency" not in projection[0]
    assert not m._FINANCIAL.intersection(projection[0])


@pytest.mark.parametrize("field,value,reason", [
    ("code", None, "source_code_unknown"), ("code", "AAPL", "source_code_unknown"),
    ("code", {}, "source_code_unknown"), ("report_date", None, "source_report_date_unknown"),
    ("report_date", "2006-02-30", "source_report_date_unknown"),
    ("report_date", "2006-03-01", "report_date_outside_registered_scope"),
    ("date", "2006-02-09", "fiscal_date_after_report_date"), ("date", {}, "source_fiscal_date_unknown"),
    ("before_after_market", None, "source_timing_unknown"), ("before_after_market", "AMC", "source_timing_unknown"),
    ("before_after_market", [], "source_timing_unknown"), ("actual", None, "current_provider_reported_status_unknown"),
    ("actual", "unknown", "source_financial_shape_unknown"), ("estimate", True, "source_financial_shape_unknown"),
    ("percent", {}, "source_financial_shape_unknown"),
])
def test_bad_row_field_quarantined_by_ordinal_not_dropped_or_inferred(field, value, reason):
    raw = encoded(payload(rows=[ROW, {**ROW, field: value}, ROW]))
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["calendar_window_observed"] and receipt["response_body_retained"]
    assert receipt["sample_rows"] == 3 and receipt["metadata_accepted_rows"] == 2 and receipt["quarantined_rows"] == 1
    assert [row["source_row_ordinal"] for row in projection] == [0, 1, 2]
    assert projection[1]["metadata_accepted"] is False
    assert reason in projection[1]["quarantine_reasons"]
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)


@pytest.mark.parametrize("bad", [None, [], "unknown", 9])
def test_non_object_source_rows_retained_as_explicit_ordinal_quarantine(bad):
    receipt, projection = m._receipt(response(raw=encoded(payload(rows=[bad, ROW]))), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["sample_rows"] == 2 and receipt["quarantined_rows"] == 1
    assert projection[0]["source_row_ordinal"] == 0
    assert projection[0]["quarantine_reasons"] == ["source_row_not_object"]
    assert projection[0]["code"] is projection[0]["report_date"] is None


def test_unknown_extra_or_missing_row_field_is_quarantine_raw_kept():
    extra, missing = {**ROW, "extra": "invented-unknown-value"}, dict(ROW)
    del missing["estimate"]
    receipt, projection = m._receipt(response(raw=encoded(payload(rows=[extra, missing]))), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["quarantined_rows"] == 2 and receipt["response_body_retained"]
    assert all("source_row_field_shape_unknown" in row["quarantine_reasons"] for row in projection)
    assert all("extra" not in row for row in projection)


def test_row_quarantine_continues_later_windows_without_repeat(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    calls = []
    def transport(window):
        calls.append(window)
        return response(window, raw=encoded(payload(window, [{**ROW, "report_date": window[0], "code": None}])))
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS)
    assert result["all_registered_windows_observed"] and result["quarantined_rows"] == 3
    assert result["metadata_accepted_rows"] == 0 and not result["backtesting_ready"]


@pytest.mark.parametrize("failure", ["http", "timeout", "envelope", "echo", "exception", "partial"])
def test_transport_or_envelope_failure_stops_with_remaining_unattempted(tmp_path, monkeypatch, failure):
    prior_fixture(tmp_path, monkeypatch)
    calls = []
    def transport(window):
        calls.append(window)
        if window == WINDOWS[0]:
            return response(window)
        if failure == "http":
            return response(window, raw=TOKEN.encode(), status=403)
        if failure == "timeout":
            return response(window, raw=b"", status=None, complete=False, disposition="transport-timeout")
        if failure == "envelope":
            return response(window, raw=b'{"error":"private"}')
        if failure == "echo":
            body = payload(window)
            body["extra"] = TOKEN
            return response(window, raw=encoded(body))
        if failure == "partial":
            return response(window, complete=False)
        raise OSError(TOKEN)
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS[:2])
    assert result["unattempted_windows_count"] == result["refused_or_ambiguous_windows"] == 1
    assert not result["all_registered_windows_observed"]
    assert not (artifact(tmp_path) / "window-0001-response.json").exists()
    assert TOKEN.encode() not in b"".join(path.read_bytes() for path in artifact(tmp_path).iterdir())
    complete = json.loads((artifact(tmp_path) / "complete.json").read_bytes())
    assert complete["unattempted_windows"] == [list(WINDOWS[-1])]


@pytest.mark.parametrize("leaf", ["complete.json", "manifest.json", "window-0000-started.json", "window-0001-complete.json", "scope"])
def test_preexisting_prior_anchor_tamper_refuses_without_new_root_or_contact(tmp_path, monkeypatch, leaf):
    prior_fixture(tmp_path, monkeypatch)
    path = old_artifact(tmp_path) / leaf
    if leaf == "scope":
        path = old_artifact(tmp_path).parent.parent / "scopes" / (old._fingerprint(old.REGISTERED_WINDOWS[0]) + ".json")
    path.write_bytes(b"corrupt")
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, transport=lambda window: pytest.fail("provider"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_prior_mutation_after_dispatch_refuses_v2_completion(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    def transport(window):
        (old_artifact(tmp_path) / "complete.json").write_bytes(b"corrupt")
        return response(window)
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, transport=transport)
    assert (artifact(tmp_path) / "window-0000-started.json").exists()
    assert not (artifact(tmp_path) / "window-0000-response.json").exists()
    assert not (artifact(tmp_path) / "complete.json").exists()


def test_valid_json_prior_control_change_cannot_bypass_external_completion_anchor(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    path = old_artifact(tmp_path) / "complete.json"
    control = json.loads(path.read_bytes())
    control["invented_unbound_control"] = True
    path.write_bytes(encoded(control))
    calls = []
    with pytest.raises(m.EarningsCampaignError, match="previous_external_anchor_mismatch"):
        run(tmp_path, transport=lambda window: (calls.append(window), response(window))[1])
    assert not calls
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("window", [old.REGISTERED_WINDOWS[0], old.REGISTERED_WINDOWS[1],
    ("2006-01-31", "2006-02-01"), ("2026-08-01", "2026-08-01")])
def test_both_old_starts_and_outside_envelope_cannot_enter_continuation(tmp_path, window):
    with pytest.raises(m.EarningsCampaignError, match="outside_frozen_support_envelope"):
        run(tmp_path, windows=(window,))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_v2_ambiguous_scope_cannot_repeat_another_id(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    run(tmp_path, transport=lambda window: response(window, status=403))
    with pytest.raises(m.EarningsCampaignError, match="completed_or_ambiguous_window_cannot_repeat"):
        run(tmp_path, campaign_id="ib-eodhd-campaign-v2-other", transport=lambda window: pytest.fail("provider"))


def test_global_legacy_lock_blocks_parallel_old_or_new_caller(tmp_path, monkeypatch):
    prior_fixture(tmp_path, monkeypatch)
    def transport(window):
        with pytest.raises(old.EarningsCampaignError, match="concurrent_campaign_refused"):
            old.run_campaign("ib-eodhd-campaign-old-concurrent", HEAD, token_file(tmp_path),
                windows=old.REGISTERED_WINDOWS[2:3], owner_acknowledged_rotated_token=True,
                root=tmp_path, identity=lambda *a, **k: IDENTITY, transport=lambda window: pytest.fail("provider"))
        with pytest.raises(m.EarningsCampaignError, match="legacy_concurrent_campaign_refused"):
            run(tmp_path, windows=WINDOWS[1:], campaign_id="ib-eodhd-campaign-new-concurrent")
        return response(window)
    assert run(tmp_path, windows=WINDOWS[:1], transport=transport)["observed_windows"] == 1


@pytest.mark.parametrize("escaped", [False, True])
def test_secret_echo_in_unknown_row_or_currency_prevents_any_raw_hash(escaped):
    raw = encoded(payload(rows=[{**ROW, "currency": TOKEN}]))
    if escaped:
        raw = raw.replace(TOKEN.encode(), TOKEN.replace("_", "\\u005f").encode())
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert projection is None and receipt["disposition"] == "credential_echo_refused"
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None


def test_numeric_lexemes_not_evaluated_even_with_extreme_exponent():
    raw = encoded(payload()).replace(b'"actual":1.234567', b'"actual":1e999999')
    projection = m._projection(raw, WINDOWS[0], token=None)
    assert projection[0]["current_provider_reported_status"] == "reported"
    assert not m._FINANCIAL.intersection(projection[0])


@pytest.mark.parametrize("raw", [b'{"type":"Earnings","type":"Earnings"}', b'{"x":NaN}', b'\xff', b'{} {}'])
def test_invalid_json_or_duplicate_keys_not_retained_as_a_row_quarantine(raw):
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert projection is None and not receipt["response_body_retained"]
    assert receipt["body_sha256"] is None


def test_default_transport_requires_real_identity_and_exact_manifest_before_credential(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("provider"))
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        m.run_continuation(CAMPAIGN, HEAD, Path("/invented"), owner_acknowledged_rotated_token=True,
            root=tmp_path, identity=lambda *a, **k: IDENTITY)
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        run(tmp_path, transport=m._default_transport)
    monkeypatch.setattr(m, "_identity", lambda *a, **k: pytest.fail("identity"))
    with pytest.raises(m.EarningsCampaignError, match="exact_frozen_monthly_manifest"):
        m.run_continuation(CAMPAIGN, HEAD, Path("/invented"), windows=WINDOWS,
            owner_acknowledged_rotated_token=True, identity=m._identity)


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


@pytest.mark.parametrize("status", [200, 302, 403, 429, 500])
def test_default_exact_bounded_tls_and_non200_no_read(tmp_path, monkeypatch, status):
    prior_fixture(tmp_path, monkeypatch, reported_real=True)
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_identity", lambda head, root=None: IDENTITY)
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    calls, streams = [], []
    class Opener:
        def open(self, item, timeout):
            calls.append((item, timeout))
            window = m.REGISTERED_WINDOWS[len(streams)]
            effective_status = status if not streams else 403
            raw = encoded(payload(window)) if effective_status == 200 else TOKEN.encode()
            stream = Stream(raw, effective_status, item.full_url)
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
    assert len(calls) == (2 if status == 200 else 1)
    assert result["unattempted_windows_count"] == 246 - len(calls)
    first, timeout = calls[0]
    assert first.full_url == m._url(WINDOWS[0]).replace("<redacted>", TOKEN)
    assert "symbols=" not in first.full_url and first.get_method() == "GET" and timeout == 15
    assert all(stream.closed for stream in streams)
    assert all(stream.read_calls == 0 for stream in streams if stream.status != 200)
    assert TOKEN not in json.dumps(result)


@pytest.mark.parametrize("headers,raw,code", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"private", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Encoding": "gzip"}, b"private", "unsupported-content-encoding"),
    ({"Content-Length": "-1"}, b"private", "invalid-content-length"),
    ({"Content-Length": "9999"}, b"private", "truncated-response"),
])
def test_continuation_body_limits_do_not_promote_or_retain_unsafe_body(headers, raw, code):
    stream = Stream(raw, 200, "invented")
    stream.headers = headers
    result = m._read_window_bounded(stream, 200)
    assert result.disposition == code
    receipt, projection = m._receipt(result, WINDOWS[0], token=m._Token(TOKEN))
    assert projection is None and receipt["body_sha256"] is receipt["body_size_bytes"] is None


def test_child_and_parent_process_network_is_denied_not_only_stubbed():
    import errno
    import socket
    import subprocess
    import sys
    with socket.socket() as sock:
        with pytest.raises(OSError) as exc:
            sock.connect(("127.0.0.1", 9))
    assert exc.value.errno in {errno.EPERM, errno.EACCES}
    script = "import socket,errno; s=socket.socket();\ntry: s.connect(('127.0.0.1',9)); raise SystemExit(3)\nexcept OSError as e: raise SystemExit(0 if e.errno in (errno.EPERM,errno.EACCES) else 4)"
    result = subprocess.run((sys.executable, "-B", "-c", script), capture_output=True, timeout=10)
    assert result.returncode == 0 and result.stdout == result.stderr == b""


def test_cli_no_resume_or_dynamic_window_flags(monkeypatch, capsys):
    args = ["--campaign-id", CAMPAIGN, "--expected-head", HEAD, "--token-file", "/invented"]
    def refused(*a, **k):
        raise m.EarningsCampaignError("previous_external_anchor_mismatch")
    monkeypatch.setattr(m, "run_continuation", refused)
    assert m.main(args) == 2
    assert json.loads(capsys.readouterr().out) == {"campaign_refused": "previous_external_anchor_mismatch"}
    with pytest.raises(SystemExit):
        m.main(args + ["--window", "2006-01-01:2006-01-31"])


# Section 194 (Claude review): continuation5's fixture-root guard, added to this version.
def test_fixture_transport_cannot_target_the_real_lane_registry():
    with pytest.raises(m.EarningsCampaignError, match="^fixture_transport_actual_lane_root_refused$"):
        m.run_continuation("ib-eodhd-campaign-invented-lane", "a" * 40, Path("/invented-token-never-read"), owner_acknowledged_rotated_token=True, root=m.LANE_ROOT, identity=lambda *a, **k: pytest.fail("identity"), transport=lambda window: pytest.fail("provider"))
