"""Synthetic-only append-only continuation; no provider or private-data access."""
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import csv
import io
import json
import os
import socket
import stat
from zoneinfo import ZoneInfo

import pytest

from research.target_price_revisions_development import raw_market_resume as resume
from research.target_price_revisions_development import raw_candidate

market, source = resume.market, resume.source
NOW = datetime(2026, 10, 8, 8, tzinfo=timezone.utc)
KEY = "SYNTHETIC_RESUME_KEY"
TICKERS = tuple("ZZ" + str(i).zfill(3) for i in range(43))
PROBE_SHA = "ad8382777e8821a2b094ccc48dfa0f17e33e18046bbc65d8340b130248e3133d"
PROBE_CODE = "3b81176c47fd8ce5c6dd4d6c00dac5c23a8396b6d8a08c7b501fc32ab81752fb"
canonical, digest = source._canonical, source._digest


def structure():
    eastern, axis, day = ZoneInfo("America/New_York"), [], date(2024, 12, 20)
    while day <= date(2025, 3, 31):
        if day.weekday() < 5 and day not in {date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17)}:
            axis.append({"session_date": day.isoformat(),
                "open_utc": datetime.combine(day, time(9, 30), eastern).astimezone(timezone.utc).isoformat(),
                "close_utc": datetime.combine(day, time(16), eastern).astimezone(timezone.utc).isoformat()})
        day += timedelta(days=1)
    weeks, ratings, next_id = set(), [], 0
    for index, session in enumerate(axis):
        day = date.fromisoformat(session["session_date"])
        week = day.isocalendar()[:2]
        if day < date(2025, 1, 2) or week in weeks:
            continue
        weeks.add(week)
        issue = axis[index - 3]["session_date"]
        for _ in range(4 if next_id == 0 else 3):
            ratings.append({"benzinga_id": "fixture-event-" + str(next_id), "benzinga_firm_id": 12,
                "ticker": TICKERS[next_id], "date": issue, "last_updated": issue + "T15:00:00Z",
                "currency": "USD", "price_target_action": "raises", "price_target": "110", "previous_price_target": "100"})
            next_id += 1
    assert next_id == 43
    return {"schema": "tpr-raw-structure-v1", "capture_utc": "2026-10-07T10:00:00Z", "calendar": axis,
        "identities": [{"ticker": ticker, "security_id": "SHARADAR:" + str(1000 + i), "permaticker": 1000 + i,
            "figi": None, "category": "Domestic Common Stock", "exchange": "NYSE", "isdelisted": False}
            for i, ticker in enumerate(TICKERS)], "ratings": ratings, "actions": [], "action_inventory_complete": True}


def waiver():
    return {"schema": "tpr-raw-owner-waiver-v1", "candidate_id": market.CANDIDATE_ID, "owner_decision": "TPR-OWN-36",
        "owner_instruction_sha256": market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        "personal_only": True, "quantconnect": False, "canonical_admission": False,
        "contractual_rights_verified": False, "datasets": list(market.raw_run._RIGHTS_DATASETS)}


def write(root, filename, body):
    payload = body if type(body) is bytes else canonical(body)
    path = root / filename
    path.write_bytes(payload)
    path.chmod(0o600)
    return digest(payload)


def original_plan():
    return market.freeze_capture_plan(structure_sha256=digest(canonical(structure())), waiver_sha256=digest(canonical(waiver())),
        tickers=TICKERS, code_hashes={name: "a" * 64 for name in market.CODE_FILES},
        candidate_policy_sha256=digest(canonical(raw_candidate.policy())), git_sha="b" * 40,
        owner_instruction_sha256=market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        created_utc=(NOW - timedelta(minutes=10)).isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")


def probe_report(original, detail_sha, request_mode="three"):
    variants = [{"variant": resume.VARIANTS[0], "ticker_count": 43, "http_status": 200 if request_mode == "all" else 400,
        "error_response_bytes": 0 if request_mode == "all" else 181, "error_detail": None}]
    if request_mode == "three":
        variants.append({"variant": resume.VARIANTS[1], "ticker_count": 3, "http_status": 200,
            "error_response_bytes": 0, "error_detail": None})
    return {"schema": "tpr-raw-market-request-probe-report-v1", "probe_id": resume.PROBE_ID, "plan_sha256": "f" * 64,
        "market_plan_sha256": original.sha256, "detail_report_sha256": detail_sha, "mode": "offline-fixture", "status": "PROBED",
        "failure_stage": None, "variants": variants, "maximum_ticker_limit_established": False,
        "provider_requests": 0, "fixture_transport_calls": len(variants), "raw_error_retained": False,
        "raw_error_identity_retained": False, "successful_body_reads": 0, "existing_development_look_spent": 0,
        "additional_development_looks": 0, "outcome_reads": 0, "quantconnect_attempts": 0, "trading": False}


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential/network access in synthetic resume proof")
    monkeypatch.setattr(resume, "_FIXED_RESOLVER", forbidden)
    monkeypatch.setattr(resume, "_FIXED_TRANSPORT", forbidden)
    monkeypatch.setattr(source, "_FIXED_RESOLVER", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "synthetic-resume"
    root.mkdir(mode=0o700)
    write(root, "rights.json", waiver())
    write(root, "structure.json", structure())
    prepared = raw_candidate.plan_target_frames(structure())
    assert len(prepared["proposed_security_ids"]) == 43
    original = original_plan()
    failed = market._execute_fixture_capture(original, root, now=NOW,
        credential_resolver=lambda _: KEY,
        transport=lambda *_: source.CaptureResponse(400, (), b"", False))
    assert json.loads(failed.payload)["failure_stage"] == "response"
    detail_report = {"schema": "tpr-raw-market-error-detail-report-v1", "mode": "offline-fixture",
        "market_plan_sha256": original.sha256, "status": "EXPLAINED", "http_status": 400, "plan_sha256": "e" * 64,
        "additional_development_looks": 0, "outcome_reads": 0, "successful_body_reads": 0, "quantconnect_attempts": 0}
    detail_sha = digest(canonical(detail_report))
    write(root, resume.detail.DETAIL_ID + "." + detail_sha + ".aggregate.json", detail_report)
    write(root, resume.detail.DETAIL_ID + ".spent.json", {"detail_id": resume.detail.DETAIL_ID, "plan_sha256": "e" * 64})
    return {"root": root, "original": original, "failed_sha": failed.sha256, "detail_sha": detail_sha}


def plan(bundle, *, request_mode="three", mutate_probe=None, **changes):
    report = probe_report(bundle["original"], bundle["detail_sha"], request_mode)
    if mutate_probe:
        mutate_probe(report)
    probe_sha = digest(canonical(report))
    write(bundle["root"], resume.PROBE_ID + "." + probe_sha + ".aggregate.json", report)
    write(bundle["root"], resume.PROBE_ID + ".spent.json", {"probe_id": resume.PROBE_ID, "plan_sha256": report["plan_sha256"]})
    args = dict(probe_report_sha256=probe_sha, probe_code_sha256="e" * 64, request_mode=request_mode, code_sha256="d" * 64,
        git_sha="b" * 40, owner_instruction_sha256=resume.detail.OWNER, created_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(hours=23)).isoformat(), mode="offline-fixture",
        failed_capture_report_sha256=bundle["failed_sha"], detail_report_sha256=bundle["detail_sha"])
    args.update(changes)
    return resume.freeze_resume_plan(bundle["original"], **args)


def response(dataset, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=market.FIELDS[dataset])
    writer.writeheader()
    writer.writerows(rows)
    payload = stream.getvalue().encode()
    return source.CaptureResponse(200, (("content-type", "text/csv"), ("content-length", str(len(payload)))), payload)


def transport(dataset, tickers, _key, _budget):
    rows = [] if dataset == "actions" else [{"ticker": ticker, "date": session["session_date"],
        "open": "10", "close": "10", "closeunadj": "10", "volume": "100000000"}
        for ticker in tickers for session in structure()["calendar"] if session["session_date"] >= "2024-12-31"]
    return response(dataset, rows)


def capture(bundle, frozen=None, *, fetch=transport, resolver=None):
    return resume._execute_fixture_capture(frozen or plan(bundle), bundle["root"], now=NOW,
        resolver=resolver or (lambda _: KEY), transport=fetch)


def test_fixed_batches_cover_every_original_ticker_once_and_keep_query_controls(bundle):
    frozen = plan(bundle)
    batches = resume._batches(frozen.body())
    assert len(batches) == 15 and tuple(t for batch in batches for t in batch) == TICKERS
    assert all(len(batch) == 3 for batch in batches[:-1]) and len(batches[-1]) == 1
    path = resume.request_path("stocks", batches[0], KEY)
    assert "ticker=ZZ000,ZZ001,ZZ002&" in path
    assert "fields=ticker%2Cdate%2Copen%2Cclose%2Ccloseunadj%2Cvolume" in path
    assert "api_key=" + KEY in path and "skip=0" in path
    with pytest.raises(ValueError, match="credential"):
        resume.request_path("stocks", batches[0], "SYNTHETIC_a+b&c")


def test_capture_retains_original_spend_claims_before_credentials_and_is_not_simulation(bundle, capsys):
    root, frozen = bundle["root"], plan(bundle)
    spent = root / (market.CANDIDATE_ID + ".spent.json")
    prior = spent.read_bytes()
    calls = []
    def resolver(provider):
        assert provider == "sharadar" and spent.read_bytes() == prior
        claim = json.loads((root / (resume.RESUME_ID + ".spent.json")).read_bytes())
        assert claim["resume_plan_sha256"] == frozen.sha256
        return KEY
    def tracked(*args):
        calls.append(args[:2])
        return transport(*args)
    result = capture(bundle, frozen, fetch=tracked, resolver=resolver)
    report = json.loads(result.payload)
    assert report["status"] == "CAPTURED" and report["fixture_transport_calls"] == 30
    assert report["page_counts"] == {"stocks": 15, "actions": 15}
    assert report["unique_row_counts"] == {"stocks": 2623, "actions": 0}
    assert report["unique_price_ticker_count"] == 43
    assert report["backtest_completed"] is report["real_backtest_ready"] is False
    assert report["provider_requests"] == report["additional_development_looks"] == report["quantconnect_attempts"] == 0
    assert all(report[key] is False for key in ("canonical_admission", "rights_verified", "trading"))
    assert tuple(t for dataset, batch in calls if dataset == "stocks" for t in batch) == TICKERS
    projection = json.loads(result.projection_path.read_bytes())
    assert {row["ticker"] for row in projection["prices"]} == set(TICKERS)
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in root.iterdir())
    assert spent.read_bytes() == prior and all(s not in result.payload for s in (b"ZZ000", KEY.encode(), b"SHARADAR:"))
    assert b"ZZ000" not in resume.public_plan_summary(frozen)
    with pytest.raises(ValueError, match="already spent"):
        capture(bundle, frozen, resolver=lambda _: pytest.fail("resume rearmed"))
    assert capsys.readouterr() == ("", "")


def test_end_to_end_frozen_converter_candidate_and_order_engine_claim_before_projection(bundle, monkeypatch):
    frozen, root = plan(bundle), bundle["root"]
    acquired = capture(bundle, frozen)
    original_read = market.raw_run._read_file
    def guarded(fd, name, *args):
        if name.endswith(".projection.json"):
            assert (root / (market.CANDIDATE_ID + ".simulation.spent.json")).is_file()
        return original_read(fd, name, *args)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded)
    result = resume._execute_fixture_backtest(frozen, acquired.sha256, root, now=NOW)
    report = json.loads(result.payload)
    assert report["status"] == "SIMULATED", report
    summary = report["summary"]
    assert summary["study_sessions"] == summary["expected_study_sessions"] == 60
    assert summary["valuation_complete"] is summary["frozen_window_complete"] is True
    assert summary["corporate_action_accounting_complete"] is True
    assert summary["orders"] > 0 and summary["fills"] > 0 and summary["return_pct"] is not None
    assert summary["canonical_admission"] is summary["market_edge_proven"] is summary["trading"] is False
    assert report["additional_development_looks"] == report["quantconnect_attempts"] == 0
    assert all(s not in result.payload for s in (b"ZZ000", b"SHARADAR:", KEY.encode()))
    assert result.report_path.is_file() and json.loads(result.terminal_path.read_bytes())["status"] == "SIMULATED"
    with pytest.raises(ValueError, match="already spent"):
        resume._execute_fixture_backtest(frozen, acquired.sha256, root, now=NOW)


@pytest.mark.parametrize("changes", [{"resume_id": "OTHER"}, {"probe_report_sha256": "a" * 64},
    {"request_mode": "all"}, {"page_counts": {"stocks": 1, "actions": 15}}, {"additional_development_looks": 1},
    {"canonical_admission": True}, {"trading": True}])
def test_forged_captured_receipt_refuses_before_simulation_claim(bundle, changes):
    frozen, root = plan(bundle), bundle["root"]
    result = capture(bundle, frozen)
    report = json.loads(result.payload)
    report.update(changes)
    identity = digest(canonical(report))
    write(root, resume.RESUME_ID + "." + identity + ".aggregate.json", report)
    with pytest.raises(ValueError, match="capture"):
        resume._execute_fixture_backtest(frozen, identity, root, now=NOW)
    assert not (root / (market.CANDIDATE_ID + ".simulation.spent.json")).exists()


@pytest.mark.parametrize("mutate", [lambda b: b.update(successful_body_reads=1), lambda b: b.update(outcome_reads=1),
    lambda b: b.update(additional_development_looks=1), lambda b: b.update(quantconnect_attempts=1),
    lambda b: b.update(status="FAILED"), lambda b: b.update(maximum_ticker_limit_established=True),
    lambda b: b.update(market_plan_sha256="a" * 64), lambda b: b.update(raw_error_retained=True),
    lambda b: b.update(extra=True), lambda b: b["variants"][-1].update(http_status=400),
    lambda b: b["variants"][0].update(http_status=500), lambda b: b["variants"][-1].update(error_response_bytes=False),
    lambda b: b["variants"][-1].update(ticker_count=2)])
def test_inapplicable_or_outcome_read_probe_never_reserves_or_resolves(bundle, mutate):
    frozen = plan(bundle, mutate_probe=mutate)
    with pytest.raises(ValueError):
        capture(bundle, frozen, resolver=lambda _: pytest.fail("credential before valid probe"))
    assert not (bundle["root"] / (resume.RESUME_ID + ".spent.json")).exists()


def test_fixture_all_variant_is_bound_but_never_production_authority(bundle):
    frozen = plan(bundle, request_mode="all")
    result = capture(bundle, frozen)
    assert json.loads(result.payload)["fixture_transport_calls"] == 2
    assert json.loads(result.payload)["page_counts"] == {"stocks": 1, "actions": 1}
    with pytest.raises(ValueError, match="production-only"):
        resume.execute_resume_capture(frozen)
    with pytest.raises(ValueError, match="production-only"):
        resume.execute_resume_backtest(frozen, result.sha256)


def test_production_freezer_pins_exact_recorded_probe_and_only_observed_three_mode(monkeypatch):
    # Pure plan test: substitute only the *expected original identity* with a
    # synthetic production-framed plan. No executor/root/credential is invoked.
    old = original_plan().body()
    args = {key: old[key] for key in ("structure_sha256", "waiver_sha256", "code_hashes", "candidate_policy_sha256",
        "owner_instruction_sha256", "created_utc", "expires_utc")}
    original = market.freeze_capture_plan(**args, tickers=TICKERS, git_sha=resume.detail.HEAD)
    monkeypatch.setattr(resume.detail.prior, "ORIGINAL_PLAN_SHA256", original.sha256)
    args = dict(probe_report_sha256=PROBE_SHA, probe_code_sha256=PROBE_CODE, request_mode="three", code_sha256="d" * 64,
        git_sha=resume.detail.HEAD, owner_instruction_sha256=resume.detail.OWNER,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=23)).isoformat())
    accepted = resume.freeze_resume_plan(original, **args)
    assert accepted.body()["probe_report_sha256"] == PROBE_SHA
    assert accepted.body()["probe_code_sha256"] == PROBE_CODE
    for changes in ({"probe_report_sha256": "b" * 64}, {"probe_code_sha256": "b" * 64}, {"request_mode": "all"}):
        with pytest.raises(ValueError, match="exact recorded history"):
            resume.freeze_resume_plan(original, **dict(args, **changes))


@pytest.mark.parametrize("mutate", [lambda b: b.update(extra=True), lambda b: b["limits"].update(retries=1),
    lambda b: b.update(original_look_renewed=True), lambda b: b.update(simulation_spent_file="other.spent.json"),
    lambda b: b["original_plan"]["price_dates"].update(to="2026-03-31")])
def test_rehashed_plan_cannot_expand_scope(bundle, mutate):
    frozen = plan(bundle)
    body = frozen.body()
    mutate(body)
    payload = canonical(body)
    with pytest.raises(ValueError):
        capture(bundle, replace(frozen, payload=payload, sha256=digest(payload)))
    assert not (bundle["root"] / (resume.RESUME_ID + ".spent.json")).exists()


def test_invalid_expiry_or_changed_structure_does_not_reserve(bundle):
    with pytest.raises(ValueError, match="scope"):
        plan(bundle, expires_utc=(NOW + timedelta(hours=25)).isoformat())
    frozen = plan(bundle)
    with pytest.raises(ValueError, match="expired"):
        resume._execute_fixture_capture(frozen, bundle["root"], now=NOW + timedelta(days=1), resolver=lambda _: KEY, transport=transport)
    write(bundle["root"], "structure.json", {"schema": "incorrect-source"})
    with pytest.raises(ValueError, match="source preparation"):
        capture(bundle, frozen)
    assert not (bundle["root"] / (resume.RESUME_ID + ".spent.json")).exists()


@pytest.mark.parametrize("case", ["conflict", "foreign-ticker", "future-date", "invalid-price", "exact-limit", "credential-echo"])
def test_bad_native_page_is_retained_privately_but_never_projected_or_retried(bundle, case):
    calls = []
    def bad(dataset, tickers, *_):
        calls.append(dataset)
        row = {"ticker": tickers[0], "date": "2025-01-02", "open": "10", "close": "10", "closeunadj": "10", "volume": "100"}
        rows = [row]
        if case == "conflict": rows.append(dict(row, close="12"))
        elif case == "foreign-ticker": row["ticker"] = "NOTPLANNED"
        elif case == "future-date": row["date"] = "2026-01-02"
        elif case == "invalid-price": row["open"] = "0"
        elif case == "exact-limit": rows = [row] * 10000
        elif case == "credential-echo": row["ticker"] = KEY
        return response(dataset, rows)
    frozen = plan(bundle)
    result = capture(bundle, frozen, fetch=bad)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["projection_sha256"] is None and report["fixture_transport_calls"] == 1
    assert result.projection_path is None and json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"
    assert calls == ["stocks"] and KEY.encode() not in result.payload
    with pytest.raises(ValueError, match="already spent"):
        capture(bundle, frozen, fetch=lambda *_: pytest.fail("retry"))


def test_exact_duplicates_are_counted_not_double_stored(bundle):
    def duplicated(dataset, batch, *_):
        row = {"ticker": batch[0], "date": "2025-01-02", "open": "10", "close": "10", "closeunadj": "10", "volume": "100"}
        return response(dataset, [row, row] if dataset == "stocks" else [])
    result = capture(bundle, fetch=duplicated)
    report = json.loads(result.payload)
    assert report["status"] == "CAPTURED"
    assert report["exact_duplicate_rows"] == {"stocks": 15, "actions": 0}
    assert report["unique_row_counts"] == {"stocks": 15, "actions": 0}
    assert report["unique_price_ticker_count"] == 15
    assert len(json.loads(result.projection_path.read_bytes())["prices"]) == 15


def test_empty_prices_preserve_missing_quotes_and_cannot_report_a_completed_engine(bundle):
    frozen = plan(bundle)
    acquired = capture(bundle, frozen, fetch=lambda dataset, *_: response(dataset, []))
    assert json.loads(acquired.payload)["status"] == "CAPTURED"
    assert json.loads(acquired.payload)["unique_price_ticker_count"] == 0
    result = resume._execute_fixture_backtest(frozen, acquired.sha256, bundle["root"], now=NOW)
    report = json.loads(result.payload)
    assert report["status"] == "SIMULATED", report
    assert report["summary"]["fills"] == 0 and report["summary"]["engine_complete"] is False


@pytest.mark.parametrize("interrupted", [False, True])
def test_failed_or_interrupted_transport_has_immutable_terminal_and_no_rearm(bundle, interrupted):
    def fail(*_):
        if interrupted:
            raise KeyboardInterrupt(KEY)
        raise RuntimeError(KEY)
    frozen = plan(bundle)
    if interrupted:
        with pytest.raises(KeyboardInterrupt, match="remain spent"):
            capture(bundle, frozen, fetch=fail)
    else:
        result = capture(bundle, frozen, fetch=fail)
        assert KEY.encode() not in result.payload
    terminal = json.loads((bundle["root"] / (resume.RESUME_ID + ".terminal.json")).read_bytes())
    assert terminal["status"] == ("INTERRUPTED" if interrupted else "FAILED")
    with pytest.raises(ValueError, match="already spent"):
        capture(bundle, frozen)


def test_partial_reservation_never_resolves_credentials_and_keeps_failure_receipt(bundle, monkeypatch):
    frozen = plan(bundle)
    original_write = source._write_fd
    def partial(fd, payload):
        if b'"schema":"tpr-raw-resume-reservation-v1"' in payload:
            os.write(fd, b"{")
            raise OSError(KEY)
        return original_write(fd, payload)
    monkeypatch.setattr(source, "_write_fd", partial)
    result = capture(bundle, frozen, resolver=lambda _: pytest.fail("credential after partial reservation"))
    assert json.loads(result.payload)["failure_stage"] == "reservation"
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"
    with pytest.raises(ValueError, match="already spent"):
        capture(bundle, frozen)


def test_symlinked_history_file_and_shared_reservation_are_never_followed(bundle):
    frozen, root = plan(bundle), bundle["root"]
    target = root / (resume.RESUME_ID + ".spent.json")
    target.symlink_to(root / "rights.json")
    before = (root / "rights.json").read_bytes()
    with pytest.raises(ValueError, match="already spent"):
        capture(bundle, frozen)
    assert (root / "rights.json").read_bytes() == before


@pytest.mark.parametrize("corruption", ["tamper", "truncate"])
def test_projection_identity_failure_after_simulation_claim_is_terminal(bundle, corruption):
    frozen, root = plan(bundle), bundle["root"]
    acquired = capture(bundle, frozen)
    acquired.projection_path.write_bytes(b"{}\n" if corruption == "tamper" else b"")
    result = resume._execute_fixture_backtest(frozen, acquired.sha256, root, now=NOW)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "projection" and report["summary"] is None
    assert (root / (market.CANDIDATE_ID + ".simulation.spent.json")).exists()
    with pytest.raises(ValueError, match="already spent"):
        resume._execute_fixture_backtest(frozen, acquired.sha256, root, now=NOW)


def test_old_shared_simulation_claim_blocks_resume_before_projection_read(bundle, monkeypatch):
    frozen, root = plan(bundle), bundle["root"]
    acquired = capture(bundle, frozen)
    write(root, market.CANDIDATE_ID + ".simulation.spent.json", {"prior_simulation": True})
    original_read = market.raw_run._read_file
    def guarded(fd, name, *args):
        if name.endswith(".projection.json"):
            pytest.fail("projection after old shared simulation claim")
        return original_read(fd, name, *args)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded)
    with pytest.raises(ValueError, match="already spent"):
        resume._execute_fixture_backtest(frozen, acquired.sha256, root, now=NOW)


@pytest.mark.parametrize("status", [301, 400, 500])
def test_real_transport_never_reads_redirect_or_error_body(monkeypatch, status):
    class Response:
        def __init__(self): self.status = status
        def getheaders(self): return [("Content-Type", "text/csv")]
        def read(self, *_): pytest.fail("non-success body opened")
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert host == "api.sharadar.com" and port == 443 and timeout == 30 and context.check_hostname
        def set_debuglevel(self, level): assert level == 0
        def request(self, method, path, headers):
            assert method == "GET" and "ticker=ZZ000,ZZ001,ZZ002&" in path
            assert headers["Accept-Encoding"] == "identity"
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(resume.http.client, "HTTPSConnection", Connection)
    observed = resume._https_get("stocks", TICKERS[:3], KEY, 4194304)
    assert observed.status == status and observed.body == b"" and observed.complete is False
