"""Synthetic native rows only; authenticated first-page continuation proofs."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import json
import socket
import stat

import pytest

from research.target_price_revisions_development import raw_sharadar_continue as source

parent = source.parent
NOW = datetime(2026, 10, 7, 21, tzinfo=timezone.utc)
KEY = "SYNTHETIC_SHARADAR_CONTINUATION_KEY"
TICKER = {"ticker": "SYNTH", "permaticker": "123", "figi": "BBG000000001",
    "category": "Domestic Common Stock", "exchange": "NASDAQ", "isdelisted": "N"}
ACTION = {"ticker": "SYNTH", "date": "2025-02-03", "action": "dividend", "contraticker": ""}


def csv_bytes(dataset, rows, *, missing=False):
    columns = tuple(field for field in parent.FIELDS[dataset]
        if not missing or field != ("figi" if dataset == "tickers" else "contraticker"))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


FIRST = csv_bytes("tickers", [TICKER] * 10000, missing=True)


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential/socket access in continuation fixtures")
    monkeypatch.setattr(source, "_production_credential", forbidden)
    monkeypatch.setattr(source, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def roots(tmp_path):
    first, destination = tmp_path / "first", tmp_path / "continuation"
    first.mkdir(mode=0o700)
    destination.mkdir(mode=0o700)
    path = first / "tickers.000.csv"
    path.write_bytes(FIRST)
    path.chmod(0o600)
    return first, destination


def plan(mode="offline-fixture", **changes):
    arguments = dict(code_sha256="1" * 64, git_sha="2" * 40,
        owner_instruction_sha256=source.OWNER_SHA256, created_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode=mode)
    if mode == "offline-fixture":
        arguments.update(first_page_sha256=hashlib.sha256(FIRST).hexdigest(), first_page_bytes=len(FIRST))
    arguments.update(changes)
    return source.freeze_capture_plan(**arguments)


def response(dataset, rows, *, missing=False):
    payload = csv_bytes(dataset, rows, missing=missing)
    return parent.CaptureResponse(200, (("content-type", "text/csv"),
        ("content-length", str(len(payload)))), payload)


def execute(roots, *, frozen=None, resolver=None, fetch=None):
    first, destination = roots
    return source.execute_capture(frozen or plan(), destination, first_page_root=first, now=NOW,
        credential_resolver=resolver or (lambda _: KEY),
        transport=fetch or (lambda dataset, *_: response(dataset, [] if dataset == "tickers" else [ACTION], missing=True)))


def test_exact_missing_figi_or_counterparty_are_null_not_fabricated():
    result = source.parse_source_csv(csv_bytes("tickers", [TICKER], missing=True), "tickers")
    assert result.missing_optional_column is True and result.rows[0]["figi"] is None
    assert result.rows[0]["permaticker"] == "123" and result.refusals == ()
    result = source.parse_source_csv(csv_bytes("actions", [ACTION], missing=True), "actions")
    assert result.rows[0]["contraticker"] is None
    assert result.missing_optional_column is True


def test_full_native_columns_retained_without_relabelling():
    result = source.parse_source_csv(csv_bytes("tickers", [TICKER]), "tickers")
    assert result.rows == (TICKER,) and result.missing_optional_column is False


@pytest.mark.parametrize("row,reason", [(dict(TICKER, permaticker="NaN"), "invalid_native_permaticker"),
    (dict(TICKER, ticker="invalid?"), "invalid_native_ticker"),
    (dict(TICKER, figi="NOT_A_FIGI"), "invalid_native_figi"),
    (dict(TICKER, isdelisted="unknown"), "unknown_native_delisting_status"),
    (dict(TICKER, category="bad\ncell"), "invalid_native_cell")])
def test_invalid_identity_values_refuse_rows_not_entire_capture(row, reason):
    result = source.parse_source_csv(csv_bytes("tickers", [TICKER, row]), "tickers")
    assert result.rows == (TICKER,) and result.source_rows == 2
    assert result.refusals == ({"row_number": 2, "reason": reason},)


@pytest.mark.parametrize("row,reason", [(dict(ACTION, date="2025-02-30"), "invalid_native_date"),
    (dict(ACTION, date="2027-01-02"), "outside_frozen_source_dates"),
    (dict(ACTION, action=""), "missing_native_action"),
    (dict(ACTION, contraticker="invalid?"), "invalid_native_counterparty")])
def test_invalid_actions_have_named_dispositions(row, reason):
    result = source.parse_source_csv(csv_bytes("actions", [row]), "actions")
    assert result.rows == () and result.source_rows == 1
    assert result.refusals[0]["reason"] == reason


@pytest.mark.parametrize("dataset,payload", [("tickers", b"ticker,permaticker,category,exchange\n"),
    ("tickers", b"ticker,permaticker,category,exchange,isdelisted,unexpected\n"),
    ("actions", b"ticker,date,action,value\n"), ("actions", b"ticker,date,action,action\n"),
    ("tickers", b"ticker,permaticker,category,exchange,isdelisted\nSYNTH,123\n")])
def test_unknown_or_malformed_native_column_families_refuse(dataset, payload):
    with pytest.raises(source.ContinueError, match="structural"):
        source.parse_source_csv(payload, dataset)


def test_complete_run_reuses_first_page_no_refetch_or_facts_escalation(roots, capsys):
    calls = []
    def fetch(dataset, page, *_):
        calls.append((dataset, page))
        return response(dataset, [] if dataset == "tickers" else [ACTION], missing=True)
    result = execute(roots, fetch=fetch)
    report = json.loads(result.payload)
    assert calls == [("tickers", 1), ("actions", 0)]
    assert report["status"] == "COMPLETED" and report["first_page_reused"] is True
    assert report["first_page_refetches"] == report["provider_requests"] == 0
    assert report["fixture_transport_calls"] == 2
    assert report["source_row_counts"] == {"tickers": 10000, "actions": 1}
    assert report["missing_optional_column_pages"] == {"tickers": 2, "actions": 1}
    assert report["response_bytes_including_parent"] >= len(FIRST)
    assert report["historical_cross_provider_identity_proven"] is report["canonical_admission"] is False
    assert report["outcome_reads"] == report["development_looks"] == report["quantconnect_attempts"] == 0
    native = json.loads(result.source_path.read_bytes())
    assert native["tickers"][0]["figi"] is None and native["actions"][0]["contraticker"] is None
    assert (roots[1] / "tickers.000.csv").read_bytes() == roots[0].joinpath("tickers.000.csv").read_bytes() == FIRST
    assert report["source_caveats"]["global_source_completeness_proven"] is False
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in roots[1].iterdir())
    assert all(value not in result.payload for value in (KEY.encode(), b"SYNTH", b"BBG000000001"))
    assert capsys.readouterr() == ("", "")


def test_claim_precedes_first_read_and_credentials(roots, monkeypatch):
    actual = source._read_first
    def first_read(root, body):
        assert (roots[1] / (source.CAPTURE_ID + ".spent.json")).exists()
        return actual(root, body)
    monkeypatch.setattr(source, "_read_first", first_read)
    def resolver(_):
        assert (roots[1] / "tickers.000.csv").exists()
        return KEY
    execute(roots, resolver=resolver)
    with pytest.raises(source.ContinueError, match="already spent"):
        execute(roots, frozen=plan(code_sha256="a" * 64), resolver=lambda _:
            pytest.fail("changed spec renewed operation"))


def test_semantically_refused_full_page_still_advances_pagination(roots):
    calls = []
    def fetch(dataset, page, *_):
        calls.append((dataset, page))
        return response(dataset, [dict(TICKER, permaticker="NaN")] * 10000 if dataset == "tickers" and page == 1 else [], missing=True)
    report = json.loads(execute(roots, fetch=fetch).payload)
    assert report["status"] == "COMPLETED"
    assert calls == [("tickers", 1), ("tickers", 2), ("actions", 0)]
    assert report["source_row_counts"]["tickers"] == 20000
    assert report["admitted_row_counts"]["tickers"] == 10000
    assert report["row_refusal_counts"] == {"invalid_native_permaticker": 10000}


def test_repeated_parent_page_is_refused_not_treated_as_new_history(roots):
    report = json.loads(execute(roots, fetch=lambda *_:
        parent.CaptureResponse(200, (("content-type", "text/csv"),), FIRST)).payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "pagination"
    assert report["fixture_transport_calls"] == 1 and report["source_sha256"] is None


@pytest.mark.parametrize("mutation", [lambda b: b["limits"].update(first_page_refetches=1),
    lambda b: b.update(parent_capture_renewed=True), lambda b: b["queries"]["actions"].update(fields="ticker,date,action,value"),
    lambda b: b.update(canonical_admission=True), lambda b: b.update(extra="PRIVATE")])
def test_rehashed_scope_changes_refuse_before_claim(roots, mutation):
    frozen = plan()
    body = frozen.body()
    mutation(body)
    payload = parent._canonical(body)
    forged = replace(frozen, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(source.ContinueError):
        execute(roots, frozen=forged)
    assert list(roots[1].iterdir()) == []


@pytest.mark.parametrize("changes", [{"code_sha256": True}, {"git_sha": "a" * 39},
    {"first_page_bytes": True}, {"first_page_bytes": 0}, {"mode": True},
    {"expires_utc": NOW.isoformat()}, {"expires_utc": (NOW + timedelta(hours=49)).isoformat()}])
def test_invalid_plan_refuses(changes):
    with pytest.raises(parent.SourceAuditError):
        plan(**changes)


def test_production_parent_and_owner_binding_exact():
    body = plan("production").body()
    assert body["first_page_sha256"] == source.FIRST_PAGE_SHA256
    assert body["first_page_bytes"] == 451759
    assert body["parent_code_sha256"] == source.PARENT_SHA256
    assert body["limits"]["remaining_requests"] == 19
    for changes in ({"first_page_sha256": "a" * 64}, {"first_page_bytes": 10}, {"owner_instruction_sha256": "f" * 64}):
        with pytest.raises(source.ContinueError, match="binding"):
            plan("production", **changes)


def test_wrong_parent_bytes_never_resolve_credentials(roots):
    path = roots[0] / "tickers.000.csv"
    path.write_bytes(FIRST[:-1] + b"x")
    report = json.loads(execute(roots, resolver=lambda _: pytest.fail("credential after parent mismatch")).payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "parent_source"
    assert report["fixture_transport_calls"] == 0


def test_parent_symlink_and_custody_refuse(roots):
    path = roots[0] / "tickers.000.csv"
    path.chmod(0o644)
    report = json.loads(execute(roots, resolver=lambda _: pytest.fail("credential after unsafe parent")).payload)
    assert report["failure_stage"] == "parent_source" and report["fixture_transport_calls"] == 0


def test_credential_echo_refused_before_private_page_retention(roots):
    report = json.loads(execute(roots, fetch=lambda dataset, *_:
        response(dataset, [dict(TICKER, category=KEY.replace("_", "%5F"))])).payload)
    assert report["status"] == "FAILED" and report["failure_stage"] == "response"
    assert not (roots[1] / "tickers.001.csv").exists()


def test_new_unknown_schema_retained_private_for_offline_repair(roots):
    raw = b"ticker,permaticker,category,exchange,isdelisted,unknown\r\nPRIVATE,123,x,y,N,PRIVATE\r\n"
    report = json.loads(execute(roots, fetch=lambda *_:
        parent.CaptureResponse(200, (("content-type", "text/csv"),), raw)).payload)
    assert report["failure_stage"] == "csv_schema" and report["status"] == "FAILED"
    assert (roots[1] / "tickers.001.csv").read_bytes() == raw
    assert b"PRIVATE" not in parent._canonical(report)


def test_expiry_between_pages_prevents_later_request(roots, monkeypatch):
    clocks = iter((NOW, NOW, NOW, NOW + timedelta(days=2)))
    monkeypatch.setattr(source, "_now", lambda: next(clocks))
    calls = []
    def fetch(dataset, page, *_):
        calls.append((dataset, page))
        return response(dataset, [dict(TICKER, permaticker="124")] * 10000, missing=True)
    result = source.execute_capture(plan(), roots[1], first_page_root=roots[0],
        credential_resolver=lambda _: KEY, transport=fetch)
    assert calls == [("tickers", 1)]
    assert json.loads(result.payload)["failure_stage"] == "expiry"


def test_partial_claim_failure_retains_terminal_without_parent_read(roots, monkeypatch):
    def bad_write(fd, _payload):
        parent.os.write(fd, b"{")
        raise OSError(KEY)
    monkeypatch.setattr(parent, "_write_fd", bad_write)
    monkeypatch.setattr(source, "_read_first", lambda *_: pytest.fail("parent read after failed claim"))
    result = execute(roots)
    assert json.loads(result.payload)["failure_stage"] == "claim"
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_interrupt_durable_terminal_no_retry(roots):
    def interrupted(*_):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt, match="scope remains spent"):
        execute(roots, fetch=interrupted)
    terminal = roots[1] / (source.CAPTURE_ID + ".terminal.json")
    assert json.loads(terminal.read_bytes())["status"] == "INTERRUPTED"


def test_mode_cannot_consume_actual_parent_via_fixture(roots):
    with pytest.raises(source.ContinueError, match="synthetic"):
        source.execute_capture(plan(), roots[1], first_page_root=parent.PRIVATE_ROOT, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: pytest.fail("actual parent route"))
    with pytest.raises(source.ContinueError, match="injected"):
        source.execute_capture(plan("production"), source.PRIVATE_ROOT, now=NOW)
    assert list(roots[1].iterdir()) == []


def test_executed_parent_source_bytes_still_match_frozen_pin():
    path = parent.LANE_ROOT / "research/target_price_revisions_development/raw_sharadar_source.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source.PARENT_SHA256
