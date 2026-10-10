"""Synthetic private fixtures; one look is reserved before any market read."""
from dataclasses import replace
from decimal import localcontext, ROUND_UP, ROUND_DOWN
from fractions import Fraction
from datetime import date, datetime, time, timedelta, timezone
import csv
import hashlib
import io
import json
import os
import socket
import stat
from zoneinfo import ZoneInfo

import pytest

from research.target_price_revisions_development import raw_market_capture as market
from research.target_price_revisions_development import raw_candidate

NOW = datetime(2026, 10, 8, 8, tzinfo=timezone.utc)
KEY = "SYNTHETIC_RAW_MARKET_KEY"
STOCK = {"ticker": "ZZTEST", "date": "2025-01-02", "open": "10", "close": "11", "closeunadj": "11", "volume": "100000"}
ACTION = {"ticker": "ZZTEST", "date": "2025-02-03", "action": "dividend", "value": "0.1", "contraticker": ""}


def canonical(body):
    return market.source._canonical(body)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def structure():
    eastern = ZoneInfo("America/New_York")
    axis = []
    day = date(2024, 12, 27)
    while day <= date(2025, 3, 31):
        if day.weekday() < 5 and day not in {date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17)}:
            axis.append({"session_date": day.isoformat(),
                "open_utc": datetime.combine(day, time(9, 30), eastern).astimezone(timezone.utc).isoformat(),
                "close_utc": datetime.combine(day, time(16), eastern).astimezone(timezone.utc).isoformat()})
        day += timedelta(days=1)
    return {"schema": "tpr-raw-structure-v1", "capture_utc": "2026-10-07T10:00:00Z", "calendar": axis,
        "identities": [{"ticker": "ZZTEST", "security_id": "SHARADAR:1000", "permaticker": 1000,
            "figi": None, "category": "Domestic Common Stock", "exchange": "NYSE", "isdelisted": False}],
        "ratings": [{"benzinga_id": "fixture-event", "benzinga_firm_id": 12, "ticker": "ZZTEST", "date": "2024-12-27",
            "last_updated": "2024-12-27T15:00:00Z", "currency": "USD", "price_target_action": "raises",
            "price_target": "110", "previous_price_target": "100"}], "actions": [], "action_inventory_complete": True}


def waiver():
    return {"schema": "tpr-raw-owner-waiver-v1", "candidate_id": market.CANDIDATE_ID, "owner_decision": "TPR-OWN-36",
        "owner_instruction_sha256": market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        "personal_only": True, "quantconnect": False, "canonical_admission": False,
        "contractual_rights_verified": False, "datasets": list(market.raw_run._RIGHTS_DATASETS)}


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential/socket access in market fixtures")
    monkeypatch.setattr(market, "_production_credential", forbidden)
    monkeypatch.setattr(market, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "market"
    directory.mkdir(mode=0o700)
    for filename, body in (("rights.json", waiver()), ("structure.json", structure())):
        path = directory / filename
        path.write_bytes(canonical(body))
        path.chmod(0o600)
    return directory


def plan(**changes):
    args = dict(structure_sha256=digest(canonical(structure())), waiver_sha256=digest(canonical(waiver())),
        tickers=("ZZTEST",), code_hashes={name: "a" * 64 for name in market.CODE_FILES},
        candidate_policy_sha256=digest(canonical(raw_candidate.policy())), git_sha="b" * 40,
        owner_instruction_sha256=market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")
    args.update(changes)
    return market.freeze_capture_plan(**args)


def csv_bytes(dataset, rows, *, optional_missing=False):
    fields = tuple(v for v in market.FIELDS[dataset] if not optional_missing or v != "contraticker")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def response(dataset, rows):
    payload = csv_bytes(dataset, rows)
    return market.source.CaptureResponse(200, (("content-type", "text/csv"), ("content-length", str(len(payload)))), payload)


def execute(root, *, frozen=None, resolver=None, fetch=None, now=NOW):
    return market._execute_fixture_capture(frozen or plan(), root, now=now,
        credential_resolver=resolver or (lambda _: KEY),
        transport=fetch or (lambda dataset, *_: response(dataset, [STOCK] if dataset == "stocks" else [ACTION])))


def test_connected_capture_reservation_precedes_credential_and_market_reads(root, capsys):
    def resolver(provider):
        assert provider == "sharadar"
        reservation = json.loads((root / (market.CANDIDATE_ID + ".spent.json")).read_bytes())
        assert reservation["market_plan_sha256"] == plan().sha256
        assert reservation["fixture_runs"] == 1 and reservation["development_look_reserved"] == 0
        assert not list(root.glob("*.csv"))
        return KEY
    result = execute(root, resolver=resolver)
    report = json.loads(result.payload)
    assert report["status"] == "CAPTURED" and report["development_look_spent"] == 0 and report["fixture_runs"] == 1
    assert report["backtest_completed"] is report["real_backtest_ready"] is False
    assert report["canonical_admission"] is report["trading"] is False
    assert report["fixture_transport_calls"] == 2 and report["provider_requests"] == report["quantconnect_attempts"] == 0
    assert report["outcome_access_before_reservation"] is False
    projection = json.loads(result.projection_path.read_bytes())
    assert projection["prices"] == [STOCK] and projection["actions"] == [ACTION]
    assert projection["transactional_snapshot"] is False
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in root.iterdir())
    assert all(v not in result.payload for v in (b"ZZTEST", KEY.encode(), b"0.1"))
    assert json.loads(result.terminal_path.read_bytes())["status"] == "CAPTURED"
    assert capsys.readouterr() == ("", "")


def test_public_summary_never_contains_exact_native_ticker_inventory():
    summary = json.loads(market.public_plan_summary(plan()))
    assert summary["ticker_count"] == 1 and summary["native_ticker_list_published"] is False
    assert "tickers" not in summary and b"ZZTEST" not in market.public_plan_summary(plan())
    assert summary["market_plan_sha256"] == plan().sha256


@pytest.mark.parametrize("changes", [{"tickers": ("ZZTEST", "ZZTEST")}, {"tickers": ("Z", "A")},
    {"tickers": ()}, {"tickers": ["ZZTEST"]}, {"code_hashes": {"raw_run.py": "a" * 64}},
    {"owner_instruction_sha256": "e" * 64}, {"mode": True}, {"expires_utc": NOW.isoformat()},
    {"expires_utc": (NOW + timedelta(hours=49)).isoformat()}])
def test_invalid_plan_refuses(changes):
    with pytest.raises(ValueError):
        plan(**changes)


@pytest.mark.parametrize("mutate", [lambda b: b.update(extra="SYNTHETIC_PRIVATE"),
    lambda b: b["price_dates"].update(to="2027-12-31"), lambda b: b["limits"].update(retries=1),
    lambda b: b.update(outcome_read_before_reservation=True), lambda b: b.update(empirical_looks=2)])
def test_rehashed_policy_changes_do_not_reserve(root, mutate):
    frozen = plan()
    body = frozen.body()
    mutate(body)
    payload = canonical(body)
    forged = replace(frozen, payload=payload, sha256=digest(payload))
    with pytest.raises(market.MarketCaptureError):
        execute(root, frozen=forged)
    assert not (root / (market.CANDIDATE_ID + ".spent.json")).exists()


def test_source_target_inventory_mismatch_and_bad_policy_refuse_before_look(root):
    for frozen in (plan(tickers=("OTHER",)), plan(candidate_policy_sha256="b" * 64)):
        with pytest.raises(market.MarketCaptureError, match="source preparation"):
            execute(root, frozen=frozen, resolver=lambda _: pytest.fail("credential before source accepted"))
    assert not (root / (market.CANDIDATE_ID + ".spent.json")).exists()


def test_source_hash_mismatch_never_spends_or_reads_market(root):
    with pytest.raises(market.MarketCaptureError, match="source preparation"):
        execute(root, frozen=plan(structure_sha256="b" * 64), fetch=lambda *_: pytest.fail("market before source identity"))
    assert not (root / (market.CANDIDATE_ID + ".spent.json")).exists()


def test_source_capture_cannot_postdate_the_frozen_plan_or_current_look(root):
    body = structure()
    body["capture_utc"] = "2026-10-10T08:00:00Z"
    payload = canonical(body)
    (root / "structure.json").write_bytes(payload)
    with pytest.raises(market.MarketCaptureError, match="source preparation"):
        execute(root, frozen=plan(structure_sha256=digest(payload)),
            resolver=lambda _: pytest.fail("credential after future source clock"))
    assert not (root / (market.CANDIDATE_ID + ".spent.json")).exists()


def test_non_native_decimal_spelling_is_not_silently_accepted():
    with pytest.raises(market.MarketCaptureError):
        market.parse_source_csv(csv_bytes("stocks", [dict(STOCK, open="1_000")]), "stocks", ("ZZTEST",))


def test_same_candidate_filename_blocks_changed_plan_and_old_executor(root):
    execute(root)
    with pytest.raises(market.MarketCaptureError, match="already spent"):
        execute(root, frozen=plan(code_hashes={name: "b" * 64 for name in market.CODE_FILES}), resolver=lambda _: pytest.fail("rearm"))
    spec_bytes = market.raw_run.freeze_run_spec(structure_sha256="a" * 64, outcomes_sha256="a" * 64,
        rights_sha256="a" * 64, code_hashes={name: "a" * 64 for name in market.raw_run.CODE_FILES},
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(market.raw_run.RawRunError, match="already spent"):
            market.raw_run._reserve(fd, market.raw_run._spec(spec_bytes), digest(spec_bytes), NOW.isoformat(),
                {"basis": "explicit-owner-waiver", "owner_decision": "TPR-OWN-36", "contractual_rights_verified": False})
    finally:
        os.close(fd)


@pytest.mark.parametrize("row", [dict(STOCK, ticker="UNPLANNED"), dict(STOCK, date="2027-01-02"),
    dict(STOCK, open="0"), dict(STOCK, close="NaN"), dict(STOCK, closeunadj="Infinity"), dict(STOCK, volume="-1")])
def test_invalid_market_price_rows_refuse_whole_native_page(row):
    with pytest.raises(market.MarketCaptureError):
        market.parse_source_csv(csv_bytes("stocks", [row]), "stocks", ("ZZTEST",))


def test_action_optional_counterparty_null_and_no_fake_blank_payoff():
    native = market.parse_source_csv(csv_bytes("actions", [ACTION], optional_missing=True), "actions", ("ZZTEST",))
    assert native[0]["contraticker"] is None and native[0]["value"] == "0.1"
    with pytest.raises(market.MarketCaptureError):
        market.parse_source_csv(csv_bytes("actions", [dict(ACTION, value="")]), "actions", ("ZZTEST",))
    native = market.parse_source_csv(csv_bytes("actions", [dict(ACTION, action="listed", value="")]), "actions", ("ZZTEST",))
    assert native[0]["value"] == ""


def test_duplicate_exact_rows_counted_without_double_cashflow(root):
    result = execute(root, fetch=lambda dataset, *_:
        response(dataset, [STOCK, STOCK] if dataset == "stocks" else [ACTION, ACTION]))
    report = json.loads(result.payload)
    assert report["exact_duplicate_rows"] == {"stocks": 1, "actions": 1}
    assert report["unique_row_counts"] == {"stocks": 1, "actions": 1}
    assert len(json.loads(result.projection_path.read_bytes())["actions"]) == 1


@pytest.mark.parametrize("dataset", ["stocks", "actions"])
def test_conflicting_native_key_fails_after_reservation(root, dataset):
    def fetch(kind, *_):
        if kind == dataset:
            rows = [STOCK, dict(STOCK, close="12")] if kind == "stocks" else [ACTION, dict(ACTION, value="0.2")]
        else:
            rows = [STOCK] if kind == "stocks" else [ACTION]
        return response(kind, rows)
    result = execute(root, fetch=fetch)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "pagination"
    assert result.projection_path is None
    assert (root / (market.CANDIDATE_ID + ".spent.json")).exists()


def test_opaque_schema_failure_raw_retained_private_after_look(root):
    raw = b"ticker,date,open,close,closeunadj,volume,unknown\nZZTEST,2025-01-02,10,11,11,10000,PRIVATE\n"
    result = execute(root, fetch=lambda *_:
        market.source.CaptureResponse(200, (("content-type", "text/csv"),), raw))
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "csv_schema"
    assert b"PRIVATE" not in result.payload
    assert (root / (market.CAPTURE_ID + ".stocks.000.csv")).read_bytes() == raw


def test_secret_echo_not_retained_even_inside_payoff_data(root):
    result = execute(root, fetch=lambda dataset, *_:
        response(dataset, [dict(STOCK, close=KEY.replace("_", "%5f"))]))
    assert json.loads(result.payload)["failure_stage"] == "response"
    assert not list(root.glob("*.csv"))


def test_partial_reservation_failure_is_spent_terminal_not_credential(root, monkeypatch):
    def failed(fd, _payload):
        os.write(fd, b"{")
        raise OSError(KEY)
    monkeypatch.setattr(market.source, "_write_fd", failed)
    result = execute(root, resolver=lambda _: pytest.fail("credential after incomplete reservation"))
    assert json.loads(result.payload)["failure_stage"] == "reservation"
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"
    assert (root / (market.CANDIDATE_ID + ".spent.json")).read_bytes() == b"{"


def test_expiry_between_requests_refuses_without_reading_later_market(root, monkeypatch):
    clocks = iter((NOW, NOW, NOW, NOW + timedelta(days=2)))
    monkeypatch.setattr(market, "_now", lambda: next(clocks))
    calls = []
    def fetch(dataset, page, *_):
        calls.append((dataset, page))
        return response(dataset, [STOCK])
    result = execute(root, now=None, fetch=fetch)
    assert calls == [("stocks", 0)]
    assert json.loads(result.payload)["failure_stage"] == "expiry"


def test_public_fixture_route_refuses_before_private_root(root):
    with pytest.raises(market.MarketCaptureError, match="production-only"):
        market.execute_capture(plan(), root)
    assert not (root / (market.CANDIDATE_ID + ".spent.json")).exists()


def test_interrupt_retains_spent_terminal(root):
    def interrupted(*_):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt, match="look remains spent"):
        execute(root, fetch=interrupted)
    assert json.loads((root / (market.CAPTURE_ID + ".terminal.json")).read_bytes())["status"] == "INTERRUPTED"


def test_synthetic_production_policy_retains_one_spent_look_on_acquisition_failure(root, monkeypatch):
    # Isolated proof of production accounting; every external/custody boundary
    # is synthetic. It is NOT an actual provider operation or empirical look.
    monkeypatch.setattr(market, "PRODUCTION_ROOT", root)
    monkeypatch.setattr(market.raw_run, "PRODUCTION_ROOT", root)
    monkeypatch.setattr(market.raw_run, "_verify_lane", lambda: None)
    monkeypatch.setattr(market.source, "_verify_identity", lambda _: None)
    monkeypatch.setattr(market, "_verify_code", lambda _: None)
    monkeypatch.setattr(market, "_now", lambda: NOW)
    def resolver(_):
        assert (root / (market.CANDIDATE_ID + ".spent.json")).exists()
        return KEY
    def refused(*_):
        return market.source.CaptureResponse(403, (("content-type", "text/csv"),), b"", False)
    monkeypatch.setattr(market, "_production_credential", resolver)
    monkeypatch.setattr(market, "_https_get", refused)
    result = market.execute_capture(plan(mode="production"), root)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["development_look_spent"] == 1
    assert report["provider_requests"] == 1 and report["fixture_transport_calls"] == 0
    assert report["last_http_status"] == 403
    assert json.loads(result.terminal_path.read_bytes())["development_look_spent"] == 1
    assert json.loads((root / (market.CANDIDATE_ID + ".spent.json")).read_bytes())["development_look_reserved"] == 1


def test_production_code_inventory_checks_all_seven_and_pinned_helpers(monkeypatch):
    paths = []
    monkeypatch.setattr(market.source, "_verify_code", lambda path, sha: paths.append((path.name, sha)))
    market._verify_code(plan().body())
    assert set(filename for filename, _ in paths) == set(market.CODE_FILES) | {"source_audit.py", "raw_sharadar_source.py"}
    assert len(paths) == 9


def test_owned_market_https_cap_refuses_declared_oversize_without_body(monkeypatch):
    calls = []
    class Reply:
        status = 200
        def getheaders(self):
            return [("content-type", "text/csv"), ("content-length", "20")]
        def read(self, _budget):
            pytest.fail("market transport exceeded remaining byte cap")
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            calls.append((host, port, timeout, context.keylog_filename))
        def set_debuglevel(self, value):
            assert value == 0
        def request(self, method, path, headers):
            assert method == "GET" and path.startswith("/v1.0/data/stocks?")
            assert "ticker=ZZTEST" in path and "from=2024-12-31" in path
            assert headers["Accept-Encoding"] == "identity"
        def getresponse(self):
            return Reply()
        def close(self):
            calls.append("closed")
    monkeypatch.setattr(market.http.client, "HTTPSConnection", Connection)
    result = market._FIXED_TRANSPORT("stocks", 0, ("ZZTEST",), KEY, 10)
    assert result.status == 200 and result.body == b"" and result.complete is False
    assert calls == [("api.sharadar.com", 443, 30, None), "closed"]


def test_fixed_market_query_binds_tickers_dates_and_payoff_fields():
    stocks = dict(market.request_query("stocks", 1, ("ZZTEST",)))
    actions = dict(market.request_query("actions", 0, ("ZZTEST",)))
    assert stocks["skip"] == "10000" and stocks["from"] == "2024-12-31" and stocks["to"] == "2025-03-31"
    assert actions["from"] == "2025-01-02" and actions["fields"] == "ticker,date,action,value,contraticker"
    assert stocks["fields"] == "ticker,date,open,close,closeunadj,volume"
    for page in (True, -1, 5):
        with pytest.raises(market.MarketCaptureError):
            market.request_query("stocks", page, ("ZZTEST",))


def test_scientific_plus_numeric_capture_is_converter_compatible_without_changing_raw_csv(root):
    row = dict(STOCK, open="1e1", close="+11", closeunadj="1.1e1", volume="1e5")
    result = execute(root, fetch=lambda dataset, *_:
        response(dataset, [row] if dataset == "stocks" else [dict(ACTION, value="+1e-1")]))
    private = json.loads(result.projection_path.read_bytes())
    assert private["prices"] == [STOCK] and private["actions"] == [ACTION]
    assert (root / (market.CAPTURE_ID + ".stocks.000.csv")).read_bytes() == csv_bytes("stocks", [row])
    from research.target_price_revisions_development.raw_market_inputs import _number
    for field in ("open", "close", "closeunadj", "volume"):
        assert _number(private["prices"][0][field]) == Fraction(STOCK[field])


def capture_full_fixture(root):
    rows = [dict(STOCK, date=session["session_date"], open="10", close="10", closeunadj="10")
        for session in structure()["calendar"] if session["session_date"] >= "2024-12-31"]
    return execute(root, fetch=lambda dataset, *_: response(dataset, rows if dataset == "stocks" else []))


def test_connected_exact_once_simulation_binds_acquisition_and_emits_only_aggregate(root, capsys, monkeypatch):
    acquired = capture_full_fixture(root)
    original_read = market.raw_run._read_file
    def guarded_read(directory_fd, filename, limit, identity):
        if filename.endswith(".projection.json"):
            assert (root / (market.CANDIDATE_ID + ".simulation.spent.json")).exists()
        return original_read(directory_fd, filename, limit, identity)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded_read)
    result = market._execute_fixture_backtest(plan(), acquired.sha256, root, now=NOW)
    public = json.loads(result.payload)
    assert public["status"] == "SIMULATED" and public["additional_development_looks"] == 0
    summary = public["summary"]
    assert summary["study_sessions"] == summary["expected_study_sessions"] == 60
    assert summary["valuation_complete"] is summary["frozen_window_complete"] is True
    assert summary["corporate_action_accounting_complete"] is True
    assert summary["orders"] and summary["fills"]
    assert summary["return_pct"] is not None and summary["max_drawdown_pct"] is not None
    assert summary["canonical_admission"] is summary["market_edge_proven"] is summary["trading"] is False
    assert all(value not in result.payload for value in (b"ZZTEST", b"SHARADAR:1000", KEY.encode()))
    assert result.report_path.is_file() and json.loads(result.terminal_path.read_bytes())["status"] == "SIMULATED"
    with pytest.raises(market.MarketCaptureError, match="simulation already spent"):
        market._execute_fixture_backtest(plan(), acquired.sha256, root, now=NOW)
    assert capsys.readouterr() == ("", "")


def test_bad_acquisition_plan_or_unclaimed_look_cannot_open_projection(root, monkeypatch):
    acquired = capture_full_fixture(root)
    (root / (market.CANDIDATE_ID + ".spent.json")).write_bytes(canonical({"schema": "not-a-look"}))
    original = market.raw_run._read_file
    def no_outcomes(fd, filename, *args):
        if filename.endswith(".projection.json"):
            pytest.fail("projection opened before look validation")
        return original(fd, filename, *args)
    monkeypatch.setattr(market.raw_run, "_read_file", no_outcomes)
    with pytest.raises(market.MarketCaptureError, match="reservation"):
        market._execute_fixture_backtest(plan(), acquired.sha256, root, now=NOW)
    assert not (root / (market.CANDIDATE_ID + ".simulation.spent.json")).exists()


def test_failed_simulation_keeps_look_and_computation_spent(root, monkeypatch):
    acquired = capture_full_fixture(root)
    def bad(*_):
        raise RuntimeError("PRIVATE_SECRET_" + KEY)
    monkeypatch.setattr(market, "_compute", bad)
    result = market._execute_fixture_backtest(plan(), acquired.sha256, root, now=NOW)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "simulation"
    assert report["summary"] is None and result.report_path is None
    assert b"PRIVATE_SECRET" not in result.payload
    with pytest.raises(market.MarketCaptureError, match="already spent"):
        market._execute_fixture_backtest(plan(), acquired.sha256, root, now=NOW)


def test_missing_nav_suppresses_return_and_drawdown_without_erasing_cash():
    fake = {"backtest": {"sessions": [{"session_id": "2025-01-02", "close_equity": None}],
        "orders": [], "fills": [], "complete": False, "corporate_action_accounting_complete": False,
        "initial_cash": "100000", "final_cash": "90000", "final_dividend_receivable": "2",
        "total_commission": "1", "total_slippage": "2"}}
    summary = market._result_summary(fake)
    assert summary["valuation_complete"] is False
    assert summary["return_pct"] is summary["max_drawdown_pct"] is summary["final_nav"] is None
    assert summary["final_cash"] == "90000.00000000" and summary["final_dividend_receivable"] == "2.00000000"


@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP])
def test_summary_rounding_is_exact_half_even_not_caller_decimal_context(rounding):
    with localcontext() as context:
        context.prec, context.rounding, context.Emax = 2, rounding, 1
        assert market._round8(Fraction(1, 200000000)) == "0.00000000"
        assert market._round8(Fraction(3, 200000000)) == "0.00000002"
        assert market._round8(Fraction(-3, 200000000)) == "-0.00000002"
        assert market._round8("100000") == "100000.00000000"


def test_public_simulation_refuses_fixture_identity_before_actual_root_access():
    with pytest.raises(market.MarketCaptureError, match="production-only"):
        market.execute_backtest(plan(), "a" * 64)


def test_partial_simulation_reservation_does_not_open_projection(root, monkeypatch):
    acquired = capture_full_fixture(root)
    def bad_write(fd, _payload):
        os.write(fd, b"{")
        raise OSError(KEY)
    monkeypatch.setattr(market.source, "_write_fd", bad_write)
    original = market.raw_run._read_file
    def guarded(fd, filename, *args):
        if filename.endswith(".projection.json"):
            pytest.fail("projection after incomplete simulation reservation")
        return original(fd, filename, *args)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded)
    result = market._execute_fixture_backtest(plan(), acquired.sha256, root, now=NOW)
    assert json.loads(result.payload)["failure_stage"] == "reservation"
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"
