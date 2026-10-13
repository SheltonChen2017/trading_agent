"""Invented source bytes and credentials; OS process-tree network denied."""
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
from urllib import error

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX Calendar custody; Windows port deferred")

from research import insider_buying_eodhd_earnings_campaign as m

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD,
            "source_sha256": {"invented.py": "b" * 64},
            "source_inventory_sha256": "c" * 64, "clean": True}
TOKEN = "invented_monthly_calendar_token_1234"
CAMPAIGN = "ib-eodhd-campaign-invented"
WINDOWS = (("2006-01-01", "2006-01-31"), ("2006-02-01", "2006-02-28"),
           ("2006-03-01", "2006-03-31"))
ROW = {"code": "AAPL.US", "report_date": "2006-01-08", "date": "2005-12-31",
       "before_after_market": "AfterMarket", "currency": "USD",
       "actual": 1.234567, "estimate": 2, "difference": -0.765433, "percent": -38.27165}


def payload(window=WINDOWS[0], rows=None):
    return {"type": "Earnings", "description": "Historical and upcoming Earnings",
            "from": window[0], "to": window[1], "earnings":
            [{**ROW, "report_date": window[0]}] if rows is None else rows}


def encoded(body):
    return json.dumps(body, separators=(",", ":")).encode()


def response(window=WINDOWS[0], raw=None, status=200, complete=True, disposition=None):
    return m.ProviderMetadataResponse(status, encoded(payload(window)) if raw is None else raw,
                                      complete, disposition)


def token_file(tmp_path):
    path = tmp_path / "invented-token"
    path.write_bytes(TOKEN.encode())
    path.chmod(0o600)
    return path


def run(tmp_path, *, windows=WINDOWS, transport=None, identity=None, campaign_id=CAMPAIGN, **kwargs):
    return m.run_campaign(campaign_id, HEAD, token_file(tmp_path), windows=windows,
        owner_acknowledged_rotated_token=True, root=tmp_path,
        identity=identity or (lambda head, root: dict(IDENTITY)),
        transport=transport or (lambda window: response(window)),
        clock=lambda: "2026-10-13T00:00:00Z", **kwargs)


def artifact(tmp_path, campaign_id=CAMPAIGN):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, "campaigns", campaign_id)


def test_frozen_248_monthly_support_windows_not_study_promotion():
    assert m.registered_windows() == m.REGISTERED_WINDOWS
    assert len(m.REGISTERED_WINDOWS) == 248
    assert m.REGISTERED_WINDOWS[0] == ("2005-12-01", "2005-12-31")
    assert m.REGISTERED_WINDOWS[-1] == ("2026-07-01", "2026-07-31")
    assert ("2008-02-01", "2008-02-29") in m.REGISTERED_WINDOWS
    assert m._windows(m.REGISTERED_WINDOWS) == m.REGISTERED_WINDOWS


def test_every_start_is_fsynced_and_scope_reserved_before_single_dispatch(tmp_path, monkeypatch):
    calls, fsyncs = [], []
    real_fsync = m.os.fsync
    monkeypatch.setattr(m.os, "fsync", lambda fd: (fsyncs.append(fd), real_fsync(fd))[1])
    def transport(window):
        index = len(calls)
        directory = artifact(tmp_path)
        assert (directory / "manifest.json").exists()
        assert (directory / f"window-{index:04d}-started.json").exists()
        assert not (directory / f"window-{index:04d}-complete.json").exists()
        scope = directory.parent.parent / "scopes" / (m._fingerprint(window) + ".json")
        assert json.loads(scope.read_bytes())["maximum_attempts"] == 1
        assert len(fsyncs) >= 8 + index * 8
        calls.append(window)
        return response(window)
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS)
    assert result["transport_invocation_count"] == result["observed_windows"] == 3
    assert result["refused_or_ambiguous_windows"] == result["unattempted_windows_count"] == 0
    assert result["all_registered_windows_observed"] is True
    assert result["source_rows"] == 3
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert result["fixture_only"] is True
    assert hashlib.sha256((artifact(tmp_path) / "complete.json").read_bytes()).hexdigest() == result["complete_sha256"]
    manifest = json.loads((artifact(tmp_path) / "manifest.json").read_bytes())
    assert manifest["windows"] == [list(window) for window in WINDOWS]
    assert manifest["window_scope_sha256"] == [m._fingerprint(window) for window in WINDOWS]
    assert manifest["owner_direction"] == m.OWNER_DIRECTION
    assert manifest["retry_resume_permitted"] is False
    assert manifest["credential_or_path_or_hash_retained"] is False
    assert artifact(tmp_path).stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in artifact(tmp_path).iterdir())
    assert TOKEN not in json.dumps(result)
    assert "1.234567" not in json.dumps(result)
    assert ROW["report_date"] not in json.dumps(result)
    metadata = json.loads((artifact(tmp_path) / "window-0000-metadata.json").read_bytes())
    assert metadata["rows"] == [{"source_row_ordinal": 0, "code": "AAPL.US", "report_date": WINDOWS[0][0],
        "fiscal_date": ROW["date"], "before_after_market": "AfterMarket",
        "current_provider_reported_status": "reported"}]
    assert not m._FINANCIAL.intersection(metadata["rows"][0])


@pytest.mark.parametrize("failure", ["http", "timeout", "schema", "exception", "partial"])
@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_first_failure_stops_and_accounts_all_remaining_unattempted(tmp_path, failure, failed_index):
    calls = []
    def transport(window):
        index = len(calls)
        calls.append(window)
        if index != failed_index:
            return response(window)
        if failure == "http":
            return response(window, raw=(TOKEN + " private").encode(), status=403)
        if failure == "timeout":
            return response(window, raw=b"", status=None, complete=False, disposition="transport-timeout")
        if failure == "schema":
            return response(window, raw=b'{"error":"private"}')
        if failure == "partial":
            return response(window, complete=False)
        raise OSError(TOKEN + " private")
    result = run(tmp_path, transport=transport)
    assert calls == list(WINDOWS[:failed_index + 1])
    assert result["transport_invocation_count"] == failed_index + 1
    assert result["observed_windows"] == failed_index
    assert result["refused_or_ambiguous_windows"] == 1
    assert result["unattempted_windows_count"] == 2 - failed_index
    assert not result["all_registered_windows_observed"]
    complete = json.loads((artifact(tmp_path) / "complete.json").read_bytes())
    assert complete["unattempted_windows"] == [list(window) for window in WINDOWS[failed_index + 1:]]
    assert len(complete["window_results"]) == failed_index + 1
    failed = complete["window_results"][-1]["receipt"]
    assert failed["body_sha256"] is failed["body_size_bytes"] is None
    assert failed["response_body_retained"] is False
    assert not (artifact(tmp_path) / f"window-{failed_index:04d}-response.json").exists()
    assert TOKEN.encode() not in b"".join(path.read_bytes() for path in artifact(tmp_path).iterdir())
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("second", [WINDOWS[:1], (("2006-01-15", "2006-02-14"),),
                                     (("2006-01-02", "2006-01-02"),)])
def test_completed_or_ambiguous_interval_overlap_cannot_repeat_other_id(tmp_path, second):
    run(tmp_path, windows=WINDOWS[:1], transport=lambda window: response(window, status=403))
    calls = []
    with pytest.raises(m.EarningsCampaignError, match="completed_or_ambiguous_window_cannot_repeat"):
        run(tmp_path, windows=second, campaign_id="ib-eodhd-campaign-other",
            transport=lambda window: calls.append(window))
    assert not calls
    assert not artifact(tmp_path, "ib-eodhd-campaign-other").exists()


def test_explicitly_unattempted_windows_can_be_separately_registered_without_repeating_failed_one(tmp_path):
    run(tmp_path, transport=lambda window: response(window, status=403))
    later = run(tmp_path, windows=WINDOWS[1:], campaign_id="ib-eodhd-campaign-later")
    assert later["transport_invocation_count"] == 2
    assert len(tuple(tmp_path.joinpath(*m.ARTIFACT_PARTS, "scopes").iterdir())) == 3


def test_keyboard_interrupt_preserves_manifest_and_started_no_resume(tmp_path):
    def interrupted(window):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, transport=interrupted)
    assert (artifact(tmp_path) / "manifest.json").exists()
    assert (artifact(tmp_path) / "window-0000-started.json").exists()
    assert not (artifact(tmp_path) / "complete.json").exists()
    with pytest.raises(m.EarningsCampaignError, match="completed_or_ambiguous"):
        run(tmp_path, campaign_id="ib-eodhd-campaign-other")


def test_process_lock_refuses_concurrent_campaign_before_any_second_start(tmp_path):
    calls = []
    def transport(window):
        with pytest.raises(m.EarningsCampaignError, match="concurrent_campaign_refused"):
            run(tmp_path, windows=WINDOWS[1:], campaign_id="ib-eodhd-campaign-concurrent",
                transport=lambda window: calls.append(window))
        return response(window)
    result = run(tmp_path, windows=WINDOWS[:1], transport=transport)
    assert result["observed_windows"] == 1 and not calls
    assert not artifact(tmp_path, "ib-eodhd-campaign-concurrent").exists()


@pytest.mark.parametrize("change_after", [1, 2, 3])
def test_identity_change_prevents_dispatch_or_completion(tmp_path, change_after):
    checks, calls = [], []
    def identity(head, root):
        checks.append(True)
        return IDENTITY if len(checks) <= change_after else {**IDENTITY, "source_inventory_sha256": "d" * 64}
    with pytest.raises(m.EarningsCampaignError, match="worktree_or_source_changed"):
        run(tmp_path, windows=WINDOWS[:1], identity=identity,
            transport=lambda window: (calls.append(window), response(window))[1])
    assert len(calls) == int(change_after == 3)
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("mutation", ["wrong-mode", "symlink", "hardlink", "missing"])
def test_private_credential_refused_before_any_window_reservation(tmp_path, mutation):
    path = token_file(tmp_path)
    if mutation == "wrong-mode":
        path.chmod(0o644)
    elif mutation == "missing":
        path.unlink()
    else:
        path.rename(tmp_path / "kept-token")
        path.symlink_to(tmp_path / "kept-token") if mutation == "symlink" else os.link(tmp_path / "kept-token", path)
    with pytest.raises(m.EarningsCampaignError, match="private_token_file_refused"):
        m.run_campaign(CAMPAIGN, HEAD, path, windows=WINDOWS,
            owner_acknowledged_rotated_token=True, root=tmp_path, identity=lambda *a, **k: IDENTITY,
            transport=lambda window: pytest.fail("provider"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_changed_credential_after_manifest_prevents_start(tmp_path):
    path, checks = token_file(tmp_path), []
    def identity(head, root):
        checks.append(True)
        if len(checks) == 2:
            path.write_bytes(b"changed_invented_calendar_token")
        return IDENTITY
    with pytest.raises(m.EarningsCampaignError, match="private_token_file_changed"):
        m.run_campaign(CAMPAIGN, HEAD, path, windows=WINDOWS,
            owner_acknowledged_rotated_token=True, root=tmp_path, identity=identity,
            transport=lambda window: pytest.fail("provider"))
    assert (artifact(tmp_path) / "manifest.json").exists()
    assert not (artifact(tmp_path) / "window-0000-started.json").exists()


@pytest.mark.parametrize("bad", [None, {}, (200, b""), m.ProviderMetadataResponse(True, b""),
    m.ProviderMetadataResponse(200, bytearray(b"")), m.ProviderMetadataResponse(200, b"", 1),
    m.ProviderMetadataResponse(200, b"", True, "private"), m.ProviderMetadataResponse(None, b"", False)])
def test_invalid_transport_preserves_started_without_manufactured_completion(tmp_path, bad):
    with pytest.raises(m.EarningsCampaignError, match="invalid_transport_result_started_preserved"):
        run(tmp_path, transport=lambda window: bad)
    assert (artifact(tmp_path) / "window-0000-started.json").exists()
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("windows,code", [
    ((), "explicit_finite"), (list(WINDOWS), "explicit_finite"), (WINDOWS * 100, "explicit_finite"),
    ((["2006-01-01", "2006-01-31"],), "window_schema"),
    ((("2006-01-01",),), "window_schema"), ((("2006-02-30", "2006-03-01"),), "window_date"),
    ((("2006-01-31", "2006-01-01"),), "window_order"),
    ((("2006-01-01", "2006-02-01"),), "31_day_limit"),
    ((("2005-11-30", "2005-11-30"),), "outside_frozen"),
    ((("2026-08-01", "2026-08-01"),), "outside_frozen"),
    ((WINDOWS[1], WINDOWS[0]), "unsorted_or_overlapping"),
    ((("2006-01-01", "2006-01-31"), ("2006-01-31", "2006-02-01")), "unsorted_or_overlapping"),
])
def test_malformed_or_broader_windows_refused_before_configuration_or_journal(tmp_path, windows, code):
    with pytest.raises(m.EarningsCampaignError, match=code):
        run(tmp_path, windows=windows)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("ack", [False, None, 1, "true"])
def test_ack_exact_boolean_without_identity_or_credential_read(tmp_path, ack):
    with pytest.raises(m.EarningsCampaignError, match="owner_rotated_token_acknowledgement_required"):
        m.run_campaign(CAMPAIGN, HEAD, Path("/invented"), windows=WINDOWS,
            owner_acknowledged_rotated_token=ack, root=tmp_path,
            identity=lambda *a, **k: pytest.fail("identity"), transport=lambda *a: pytest.fail("provider"))


def test_fixture_identity_cannot_use_default_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("provider"))
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        m.run_campaign(CAMPAIGN, HEAD, Path("/invented"), windows=WINDOWS,
            owner_acknowledged_rotated_token=True, root=tmp_path, identity=lambda *a, **k: IDENTITY)
    with pytest.raises(m.EarningsCampaignError, match="real_transport_requires_real_lane_identity"):
        run(tmp_path, transport=m._default_transport)


def test_real_transport_cannot_change_frozen_monthly_plan(monkeypatch):
    monkeypatch.setattr(m, "_identity", lambda *a, **k: pytest.fail("identity"))
    with pytest.raises(m.EarningsCampaignError, match="exact_frozen_monthly_manifest"):
        m.run_campaign(CAMPAIGN, HEAD, Path("/invented"), windows=WINDOWS,
            owner_acknowledged_rotated_token=True, identity=m._identity)


@pytest.mark.parametrize("field,value,code", [
    ("report_date", "2005-12-31", "report_date_outside"),
    ("report_date", "2006-02-01", "report_date_outside"),
    ("report_date", "2006-01-32", "source_date_schema"),
    ("date", "2006-01-31", "fiscal_date_after"),
    ("code", "AAPL", "source_row_schema"), ("code", "AAPL.US\n", "source_row_schema"),
    ("code", None, "source_row_schema"), ("before_after_market", [], "source_timing_schema"),
    ("before_after_market", {}, "source_timing_schema"), ("before_after_market", "AMC", "source_timing_schema"),
    ("currency", "usd", "source_currency_schema"), ("actual", True, "source_financial_type"),
    ("estimate", "2", "source_financial_type"), ("percent", {}, "source_financial_type"),
])
def test_all_rows_request_bound_strict_schema_not_admitted_from_dates_or_label(tmp_path, field, value, code):
    result = run(tmp_path, windows=WINDOWS[:1], transport=lambda window:
        response(window, raw=encoded(payload(window, [{**ROW, field: value}]))))
    receipt = json.loads((artifact(tmp_path) / "complete.json").read_bytes())["window_results"][0]["receipt"]
    assert code in receipt["disposition"]
    assert result["observed_windows"] == 0
    assert not (artifact(tmp_path) / "window-0000-response.json").exists()


def test_global_non_us_rows_and_multiple_tickers_retained_without_inferred_identity():
    rows = [{**ROW, "code": "ABC.LSE"}, {**ROW, "code": "AAPL.US"}]
    projection = m._projection(encoded(payload(rows=rows)), WINDOWS[0], token=None)
    assert [row["code"] for row in projection] == ["AAPL.US", "ABC.LSE"]
    assert not any("cik" in row or "sid" in row for row in projection)


def test_duplicate_ticker_fiscal_period_not_silently_dropped_or_merged():
    raw = encoded(payload(rows=[ROW, dict(ROW), {**ROW, "report_date": "2006-01-09"}]))
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["calendar_window_observed"] is True
    assert receipt["sample_rows"] == 3
    assert receipt["duplicate_fiscal_period_rows"] == 2
    assert receipt["metadata_conflicting_fiscal_periods"] == 1
    assert receipt["duplicate_or_conflicting_rows_deduplicated"] is False
    assert [row["source_row_ordinal"] for row in projection] == [0, 1, 2]
    assert not receipt["empty_result_is_coverage_evidence"]
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)


def test_duplicate_context_raw_and_every_source_ordinal_survive_custody(tmp_path):
    raw = encoded(payload(rows=[ROW, {**ROW, "report_date": "2006-01-09"}]))
    result = run(tmp_path, windows=WINDOWS[:1], transport=lambda window: response(raw=raw))
    directory = artifact(tmp_path)
    assert result["source_rows"] == 2
    assert (directory / "window-0000-response.json").read_bytes() == raw
    rows = json.loads((directory / "window-0000-metadata.json").read_bytes())["rows"]
    assert [row["source_row_ordinal"] for row in rows] == [0, 1]
    assert all(not m._FINANCIAL.intersection(row) for row in rows)


@pytest.mark.parametrize("actual,timing", [(None, None), (0, "BeforeMarket"), (-1.0, "AfterMarket")])
def test_current_status_only_and_unknown_timing_retained(actual, timing):
    projection = m._projection(encoded(payload(rows=[{**ROW, "actual": actual, "before_after_market": timing}])),
                               WINDOWS[0], token=None)
    assert projection[0]["before_after_market"] == timing
    assert projection[0]["current_provider_reported_status"] == ("unknown" if actual is None else "reported")


@pytest.mark.parametrize("mutation", ["from", "to", "extra", "symbols", "missing", "list", "null", "limit"])
def test_exact_date_envelope_required(tmp_path, mutation, monkeypatch):
    body = payload()
    if mutation in {"from", "to"}:
        body[mutation] = "2006-02-01"
    elif mutation == "extra":
        body["private"] = "sentinel"
    elif mutation == "symbols":
        del body["from"]
        del body["to"]
        body["symbols"] = "AAPL.US"
    elif mutation == "missing":
        del body["description"]
    elif mutation == "limit":
        monkeypatch.setattr(m, "MAX_ROWS", 0)
    else:
        body = [] if mutation == "list" else None
    result = run(tmp_path, windows=WINDOWS[:1], transport=lambda window: response(raw=encoded(body)))
    assert result["observed_windows"] == 0
    assert not (artifact(tmp_path) / "window-0000-response.json").exists()


def test_empty_response_not_positive_archive_coverage(tmp_path):
    result = run(tmp_path, windows=WINDOWS[:1], transport=lambda window:
        response(window, raw=encoded(payload(window, []))))
    assert result["all_registered_windows_observed"] and result["source_rows"] == 0
    complete = json.loads((artifact(tmp_path) / "complete.json").read_bytes())
    assert complete["window_results"][0]["receipt"]["empty_result_is_coverage_evidence"] is False
    assert all(result[name] is False for name in m.FALSE_FLAGS)


@pytest.mark.parametrize("escaped", [False, True])
def test_secret_echo_is_never_hashed_retained_or_printed(tmp_path, escaped):
    body = payload()
    body["extra"] = TOKEN
    raw = encoded(body)
    if escaped:
        raw = raw.replace(TOKEN.encode(), TOKEN.replace("_", "\\u005f").encode())
    run(tmp_path, windows=WINDOWS[:1], transport=lambda window: response(raw=raw))
    receipt = json.loads((artifact(tmp_path) / "complete.json").read_bytes())["window_results"][0]["receipt"]
    assert receipt["disposition"] == "credential_echo_refused"
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert TOKEN.encode() not in b"".join(path.read_bytes() for path in artifact(tmp_path).iterdir())


@pytest.mark.parametrize("raw,code", [
    (b'{"type":"Earnings","type":"Earnings"}', "duplicate_source_json_key"),
    (b'{"private":NaN}', "nonfinite_source_number_refused"),
    (b'\xff', "source_json_schema_refused"), (b'{} {}', "source_json_schema_refused"),
])
def test_json_duplicate_nonfinite_and_malformed_fail_without_retaining_body(raw, code):
    receipt, projection = m._receipt(response(raw=raw), WINDOWS[0], token=m._Token(TOKEN))
    assert receipt["disposition"] == code and projection is None and receipt["body_sha256"] is None


def test_numeric_lexemes_are_discarded_without_float_overflow_or_outcome_projection():
    raw = encoded(payload()).replace(b'"actual":1.234567', b'"actual":1e999999')
    projection = m._projection(raw, WINDOWS[0], token=None)
    assert projection[0]["current_provider_reported_status"] == "reported"
    assert not m._FINANCIAL.intersection(projection[0])


@pytest.mark.parametrize("leaf", ["manifest.json", "window-0000-started.json", "scope", "lock"])
@pytest.mark.parametrize("mutation", ["bytes", "mode", "symlink", "hardlink", "missing"])
def test_post_dispatch_journal_tampering_cannot_complete(tmp_path, leaf, mutation):
    def transport(window):
        directory = artifact(tmp_path)
        path = directory / leaf
        if leaf == "scope":
            path = directory.parent.parent / "scopes" / (m._fingerprint(window) + ".json")
        elif leaf == "lock":
            path = directory.parent.parent / "campaign.lock"
        if mutation == "bytes":
            path.write_bytes(b"changed")
        elif mutation == "mode":
            path.chmod(0o644)
        elif mutation == "missing":
            path.unlink()
        else:
            kept = tmp_path / "kept"
            kept.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(kept) if mutation == "symlink" else os.link(kept, path)
        return response(window)
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, transport=transport)
    assert not (artifact(tmp_path) / "complete.json").exists()
    assert not (artifact(tmp_path) / "window-0000-response.json").exists()


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_renamed_ancestor_refuses_named_fd_reattachment(tmp_path, depth):
    def transport(window):
        parts = (*m.ARTIFACT_PARTS, "campaigns", CAMPAIGN)
        path = tmp_path.joinpath(*parts[:depth])
        path.rename(tmp_path / "displaced")
        path.mkdir(mode=0o700)
        return response(window)
    with pytest.raises(m.EarningsCampaignError):
        run(tmp_path, transport=transport)
    assert not tuple((tmp_path / "displaced").rglob("complete.json"))


@pytest.mark.parametrize("where", ["scope", "campaign"])
def test_unexpected_leaf_after_dispatch_refuses_completion(tmp_path, where):
    def transport(window):
        directory = artifact(tmp_path)
        (directory if where == "campaign" else directory.parent.parent / "scopes").joinpath("extra").write_bytes(b"invented")
        return response(window)
    with pytest.raises(m.EarningsCampaignError, match="custody"):
        run(tmp_path, transport=transport)
    assert not (artifact(tmp_path) / "complete.json").exists()


class Stream(io.BytesIO):
    def __init__(self, raw, *, status=200, url=None, headers=None):
        super().__init__(raw)
        self.status, self.url, self.headers = status, url, headers or {}
        self.read_calls = 0
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url
    def read(self, *args):
        self.read_calls += 1
        return super().read(*args)


def default_fixture(tmp_path, monkeypatch, stream=None, exc=None):
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "REGISTERED_WINDOWS", WINDOWS[:1])
    monkeypatch.setattr(m, "_identity", lambda head, root=None: dict(IDENTITY))
    calls = []
    class Opener:
        def open(self, item, timeout):
            calls.append((item, timeout))
            if exc is not None:
                raise exc
            return stream
    def build(*handlers):
        calls.append(handlers)
        return Opener()
    monkeypatch.setattr(m.request, "build_opener", build)
    result = m.run_campaign(CAMPAIGN, HEAD, token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)
    receipt = json.loads((artifact(tmp_path) / "complete.json").read_bytes())["window_results"][0]["receipt"]
    return result, receipt, calls


def test_default_transport_exact_date_profile_no_symbols_proxy_retry_redirect(tmp_path, monkeypatch):
    url = m._url(WINDOWS[0]).replace("<redacted>", TOKEN)
    stream = Stream(encoded(payload()), url=url)
    result, receipt, calls = default_fixture(tmp_path, monkeypatch, stream)
    assert receipt["calendar_window_observed"] and not result["fixture_only"]
    assert len(calls) == 2
    handlers, (item, timeout) = calls
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], m._DenyRedirect)
    assert handlers[2]._context.verify_mode == ssl.CERT_REQUIRED
    assert handlers[2]._context.check_hostname is True
    assert item.full_url == url and "symbols=" not in item.full_url
    assert item.get_method() == "GET" and item.data is None and timeout == 15
    assert item.get_header("Accept-encoding") == "identity" and stream.closed


def test_rate_limit_waits_after_prior_transport_completion_before_next_start(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "REGISTERED_WINDOWS", WINDOWS[:2])
    monkeypatch.setattr(m, "_identity", lambda head, root=None: dict(IDENTITY))
    now, waits, starts = [100.0], [], []
    monkeypatch.setattr(m.time, "monotonic", lambda: now[0])
    def sleep(seconds):
        assert seconds >= 1.0
        waits.append(seconds)
        now[0] += seconds
    monkeypatch.setattr(m.time, "sleep", sleep)
    def default(window, **kwargs):
        starts.append(now[0])
        return response(window)
    monkeypatch.setattr(m, "_default_transport", default)
    result = m.run_campaign(CAMPAIGN, HEAD, token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)
    assert result["observed_windows"] == 2
    assert waits == [1.0] and starts == [100.0, 101.0]


def test_default_identity_failure_is_refusal_without_supplier_contact(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "REGISTERED_WINDOWS", WINDOWS[:1])
    calls = []
    def identity(head, root=None):
        calls.append(True)
        return IDENTITY if len(calls) != 4 else {**IDENTITY, "source_inventory_sha256": "d" * 64}
    monkeypatch.setattr(m, "_identity", identity)
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("provider"))
    result = m.run_campaign(CAMPAIGN, HEAD, token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)
    assert result["refused_or_ambiguous_windows"] == 1
    assert len(calls) >= 4


@pytest.mark.parametrize("status", [201, 204, 301, 307, 401, 403, 429, 500])
def test_default_never_consumes_non200_or_hashes_upstream_error(tmp_path, monkeypatch, status):
    stream = Stream(TOKEN.encode(), status=status, url=m._url(WINDOWS[0]).replace("<redacted>", TOKEN))
    result, receipt, calls = default_fixture(tmp_path, monkeypatch, stream)
    assert stream.read_calls == 0 and stream.closed and len(calls) == 2
    assert receipt["disposition"] in {"http-refused", "redirect-refused"}
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert TOKEN not in json.dumps(result)


def test_http_error_object_never_consumed(tmp_path, monkeypatch):
    url = m._url(WINDOWS[0]).replace("<redacted>", TOKEN)
    stream = Stream(TOKEN.encode(), status=403, url=url)
    _, receipt, calls = default_fixture(tmp_path, monkeypatch,
        exc=error.HTTPError(url, 403, TOKEN, {}, stream))
    assert receipt["disposition"] == "http-refused"
    assert len(calls) == 2 and stream.read_calls == 0 and stream.closed


@pytest.mark.parametrize("headers,raw,code", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"private", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Encoding": "gzip"}, b"private", "unsupported-content-encoding"),
    ({"Content-Length": "-1"}, b"private", "invalid-content-length"),
    ({"Content-Length": "9999"}, b"private", "truncated-response"),
])
def test_versioned_window_transport_bound_refuses_unsafe_headers_or_bytes(tmp_path, monkeypatch, headers, raw, code):
    stream = Stream(raw, headers=headers, url=m._url(WINDOWS[0]).replace("<redacted>", TOKEN))
    _, receipt, _ = default_fixture(tmp_path, monkeypatch, stream)
    assert receipt["disposition"] == code and receipt["body_sha256"] is None


def test_window_body_bound_accepts_more_than_old_one_shot_limit_without_changing_old_module():
    raw = b"x" * (2 * 1024 * 1024)
    stream = Stream(raw, headers={"Content-Length": str(len(raw))})
    assert m._read_window_bounded(stream, 200).body == raw
    from research import insider_buying_eodhd_calendar_qualification as old
    assert old.MAX_BODY_BYTES == 1024 * 1024


@pytest.mark.parametrize("exc,code", [(TimeoutError(TOKEN), "transport-timeout"),
    (error.URLError(TimeoutError(TOKEN)), "transport-timeout"),
    (error.URLError(TOKEN), "transport-error"), (OSError(TOKEN), "transport-error")])
def test_real_errors_sanitized_no_retry(tmp_path, monkeypatch, exc, code):
    result, receipt, calls = default_fixture(tmp_path, monkeypatch, exc=exc)
    assert receipt["disposition"] == code and len(calls) == 2
    assert TOKEN not in json.dumps(result)


def test_read_window_bounded_bad_read_type_partial_exception_and_ignored_size():
    class Bad(Stream):
        def read(self, size):
            return "not bytes"
    assert m._read_window_bounded(Bad(b""), 200).disposition == "partial-read"
    class Broken(Stream):
        def read(self, size):
            raise OSError(TOKEN)
    assert m._read_window_bounded(Broken(b""), 200).disposition == "partial-read"
    class Oversize(Stream):
        def read(self, size):
            return b"x" * (m.MAX_BODY_BYTES * 2)
    result = m._read_window_bounded(Oversize(b""), 200)
    assert result.disposition == "oversized-response" and len(result.body) == m.MAX_BODY_BYTES + 1


def test_source_identity_binds_all_reachable_current_helpers_and_clean_commit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "SOURCE_FILES", ("invented.py",))
    source = tmp_path / "invented.py"
    source.write_bytes(b"source")
    def git(root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path).encode()
        if args == ("branch", "--show-current"):
            return m.LANE_BRANCH.encode()
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        if args[0] == "status":
            return b""
        assert args == ("show", HEAD + ":invented.py")
        return b"source"
    monkeypatch.setattr(m, "_git", git)
    assert m._identity(HEAD, root=tmp_path)["source_sha256"] == {"invented.py": hashlib.sha256(b"source").hexdigest()}
    source.write_bytes(b"changed")
    with pytest.raises(m.EarningsCampaignError, match="tracked_source_bytes_mismatch"):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("head", [None, "A" * 40, "a" * 39, HEAD + "\n", 1])
def test_bad_head_no_git_access(head, monkeypatch):
    monkeypatch.setattr(m, "_git", lambda *a: pytest.fail("Git"))
    with pytest.raises(m.EarningsCampaignError, match="expected_head_format_refused"):
        m._identity(head)


def test_wrong_root_no_git_access(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_git", lambda *a: pytest.fail("Git"))
    with pytest.raises(m.EarningsCampaignError, match="designated_worktree_required"):
        m._identity(HEAD, root=tmp_path)


def test_finite_progress_is_counts_only_without_rows_dates_secrets_or_values(tmp_path):
    windows = tuple((f"2006-01-{day:02d}", f"2006-01-{day:02d}") for day in range(1, 12))
    progress = []
    result = run(tmp_path, windows=windows, progress=progress.append)
    assert progress == [{"completed_windows": 10, "observed_windows": 10, "source_rows": 10}]
    assert result["source_rows"] == 11
    assert TOKEN not in json.dumps(progress)


def test_cli_has_no_dynamic_broader_window_option_and_sanitized_output(monkeypatch, capsys):
    args = ["--campaign-id", CAMPAIGN, "--expected-head", HEAD, "--token-file", "/invented"]
    def refused(*a, **k):
        raise m.EarningsCampaignError("private_token_file_refused")
    monkeypatch.setattr(m, "run_campaign", refused)
    assert m.main(args) == 2
    assert json.loads(capsys.readouterr().out) == {"campaign_refused": "private_token_file_refused"}
    with pytest.raises(SystemExit):
        m.main(args + ["--window", "2006-01-01:2006-01-31"])
