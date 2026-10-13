"""Synthetic component capture only; real roots/network/credentials denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_owner_mia_components as m

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*_args, **_kwargs): raise AssertionError("actual credential/network/private/subprocess forbidden")
    monkeypatch.setattr(m.ops, "credential", denied)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    original = m.files._directory
    def directory(path, *, private):
        if private and path.is_relative_to(m.LANE): denied()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", directory)


def fixture(tmp_path, *, count=2, batch_start=0):
    root = tmp_path / "synthetic-owner-components"; root.mkdir(mode=0o700)
    unknown = ["synthetic-owner-job-" + f"{index:03d}" for index in range(count)]
    sources = deepcopy(SOURCES)
    known = sorted(m.discovery._frozen({name: sources[name] for name in m.discovery.SOURCE_PATHS}))
    native_rows = [{"backtestId": identity, "created": (NOW - timedelta(minutes=count + len(known) - index)).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Completed.", "progress": 1, "snapshotId": index + 1, "projectId": m.PROJECT}
        for index, identity in enumerate(known + unknown)]
    projected = m.discovery._projection(e.canonical({"success": True, "count": len(native_rows), "backtests": native_rows}), "SYNTHETIC-TOKEN")
    projection_raw = e.canonical(projected)
    receipt = {"schema": "tpr-ext26-owner-mia-metadata-inspect-receipt-v1", "operation_id": m.DIAG_OPERATION,
        "status": "COMPLETED_DIAGNOSTIC_INSPECTION", "scope_spent": True, "api_requests": 0, "new_jobs": 0,
        "diagnostic": {"success": True, "count": len(native_rows), "returned_rows": len(native_rows),
            "projection_sha256": projected["projection_sha256"], "wire_sha256": projected["original_wire_sha256"],
            "wire_bytes": projected["original_wire_bytes"],
            "jobs": [{**row, "created_is_timezone_aware": False} for row in native_rows]}}
    raw = e.canonical(receipt)
    reference = {"operation_id": m.DIAG_OPERATION, "receipt_bytes": len(raw), "receipt_sha256": m._sha(raw),
        "projection_name": m.PROJECTION_NAME, "projection_bytes": len(projection_raw), "projection_sha256": m._sha(projection_raw)}
    ledger = e.parse_json(sources[m.LEDGER])
    ledger.update(owner_instruction_sha256="b" * 64, known_historical_jobs=known, newly_observed_jobs=count,
        diagnostic={"name": m.DIAG_OPERATION + ".result.json", "bytes": len(raw), "sha256": m._sha(raw)},
        projection={"name": m.PROJECTION_NAME, "bytes": len(projection_raw), "sha256": m._sha(projection_raw)},
        jobs=[{"look_ordinal": 21 + index, "backtest_id": row["backtestId"], "created_server_string": row["created"],
            "status": row["status"], "snapshot_id": row["snapshotId"], "creation_timezone_known": False,
            "retrospective": True, "origin_authenticated_as_mia": False, "compiled_source_proven": False,
            "accepted_metrics": None, "economics_accepted": False} for index, row in enumerate(native_rows[len(known):])])
    sources[m.LEDGER] = e.canonical(ledger)
    directory = m.files._directory(root, private=True)
    try:
        m.capture._publish(directory, m.DIAG_OPERATION + ".result.json", raw)
        m.capture._publish(directory, m.PROJECTION_NAME, projection_raw)
    finally: os.close(directory)
    plan = m._plan(operation_id="TPR-EXT26-OWNER-MIA-COMPONENTS-SYNTHETIC-001", git_head="a" * 40,
        source_hashes={name: m._sha(raw) for name, raw in sources.items()}, owner_instruction_sha256="b" * 64,
        created_utc=(NOW - timedelta(seconds=1)).isoformat(), expires_utc=(NOW + timedelta(minutes=30)).isoformat(),
        discovery_reference=reference,
        batch_start=batch_start, jobs=[{"backtest_id": identity, "retrospective_owner_look_ordinal": 21 + batch_start + index}
            for index, identity in enumerate(unknown[batch_start:batch_start + m.MAX_JOBS])], mode="offline-fixture")
    return plan, sources, root, {"unknown_job_ids": unknown}


def transport(*, fault=None, order_count=1, pending=False):
    calls = []
    def reading(plan, endpoint, payload, seconds, claim):
        assert 0 < seconds <= 30
        m._request_allowed(plan, endpoint, payload)
        root_claim = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": m._sha(e.canonical(plan))})
        assert claim == {"bytes": len(root_claim), "sha256": m._sha(root_claim)}
        calls.append((endpoint, deepcopy(payload)))
        identity = payload["backtestId"]
        if endpoint == "backtests/read":
            response = {"success": True, "backtest": {"backtestId": identity, "projectId": m.PROJECT,
                "completed": not pending, "status": "In Progress..." if pending else "Completed.",
                "error": None, "progress": e.JsonNumber("0.7500") if pending else 1,
                "user": {"id": "SYNTHETIC PRIVATE USER", "email": "SYNTHETIC PRIVATE EMAIL"}}}
        elif endpoint == "backtests/chart/read":
            response = {"success": True, "status": "loading", "progress": e.JsonNumber("0.2500")}
        elif endpoint == "backtests/orders/read":
            start, end = payload["start"], payload["end"]
            response = {"success": True, "length": order_count,
                "orders": [{"id": index + 1, "backtestId": identity, "quantity": e.JsonNumber("1.00000"),
                    "price": e.JsonNumber("100.010000"), "events": None} for index in range(start, min(end, order_count))]}
        else:
            response = {"success": True, "length": 1 if payload["query"] == "EXT26_SUMMARY" else 0,
                "logs": ['2026-10-09 EXT26_SUMMARY {"truncated":"'] if payload["query"] == "EXT26_SUMMARY" else []}
        if fault: fault(endpoint, payload, response, len(calls))
        return e.canonical(response), 200, "SYNTHETIC-TOKEN"
    return reading, calls


def execute(values, reading=None, **kwargs):
    plan, sources, root, _receipt = values
    if reading is None: reading = transport()[0]
    raw = m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW), transport=reading, **kwargs)
    return e.parse_json(raw), raw


def test_failed_compact_summary_keeps_index_charts_orders_and_all_unfamiliar_jobs(tmp_path):
    values = fixture(tmp_path); reading, calls = transport(); result, raw = execute(values, reading)
    assert result["status"] == "COMPLETED_CAPTURE" and len(calls) == 12
    assert [row["backtest_id"] for row in result["jobs"]] == values[3]["unknown_job_ids"]
    assert [row["retrospective_owner_look_ordinal"].fraction() for row in result["jobs"]] == [21, 22]
    assert result["discovery"]["server_string_order_verified"] is True
    assert result["discovery"]["creation_timezone_known"] is result["discovery"]["utc_chronology_attested"] is False
    for row in result["jobs"]:
        assert row["logs"]["EXT26_SUMMARY"]["classification"] == "diagnostic_compact_message_refused"
        assert row["logs"]["EXT26_EVIDENCE_INDEX"]["observed_matching_log_count"].fraction() == 0
        assert row["orders"]["classification"] == "complete_order_page_census_only"
        assert row["orders"]["order_count"].fraction() == 1
        assert row["orders"]["fees"] is row["orders"]["fills"] is None
        assert row["charts"]["EXT26 Account NAV"]["classification"] == "diagnostic_loading_chart"
        assert row["full_window_accounting_proven"] is row["economics_accepted"] is False
    assert result["accepted_metrics"] is None and result["compiled_source_proven"] is result["winner_selected"] is False
    assert result["parent_codex_attempt"].fraction() == result["codex_off_attempts_consumed"].fraction() == 3
    assert result["new_codex_attempts"].fraction() == result["new_jobs_launched"].fraction() == 0
    assert raw == (values[2] / (values[0]["operation_id"] + ".result.json")).read_bytes()
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values, reading)
    assert len(calls) == 12


def test_private_envelopes_retain_exact_numeric_tokens_and_contextual_redaction(tmp_path):
    values = fixture(tmp_path, count=1); result, _ = execute(values)
    order_request = next(row for row in result["requests"] if row["endpoint"] == "backtests/orders/read")
    raw = (values[2] / order_request["envelope"]["name"]).read_bytes()
    assert b'"price":100.010000' in raw and b'"quantity":1.00000' in raw
    terminal = (values[2] / result["requests"][0]["envelope"]["name"]).read_bytes()
    assert b"SYNTHETIC PRIVATE USER" not in terminal and b"SYNTHETIC PRIVATE EMAIL" not in terminal
    assert b"[redacted]" in terminal


@pytest.mark.parametrize("body,status,classification", [
    ({"success": False, "errors": ["SYNTHETIC FAILED RESPONSE"],
      "user": {"email": "SYNTHETIC PRIVATE EMAIL"}}, 200, "retained_native_shape_or_success_refusal"),
    ({"success": False, "status": "loading", "errors": ["SYNTHETIC HTTP FAILURE"]}, 503, "retained_http_failure"),
    (["SYNTHETIC UNFAMILIAR RESPONSE"], 200, "retained_native_shape_or_success_refusal"),
])
def test_safe_failed_or_unfamiliar_native_envelopes_are_retained_before_acceptance(tmp_path, body, status, classification):
    values = fixture(tmp_path, count=1)
    def reading(_plan, _endpoint, _payload, _seconds, _claim):
        return e.canonical(body), status, "SYNTHETIC-TOKEN"
    result, _ = execute(values, reading)
    item = result["requests"][0]
    assert result["status"] == "FAILED_OR_UNCERTAIN" and item["status"] == classification
    assert item["http_status"].fraction() == status and item["native_success_accepted"] is False
    raw = (values[2] / item["envelope"]["name"]).read_bytes()
    retained = e.parse_json(raw)
    assert retained["response"] is not None and b"SYNTHETIC PRIVATE EMAIL" not in raw
    assert retained["returned_identity_checks"] is None if type(body) is list else type(retained["returned_identity_checks"]) is dict
    assert result["request_attempts"].fraction() == 1 and result["accepted_metrics"] is None


def test_terminal_wire_capacity_is_frozen_prospectively_not_an_attempt_reset(tmp_path):
    plan = fixture(tmp_path, count=1)[0]
    assert plan["read_endpoints"]["backtests/read"] == 4 * 1024 * 1024
    assert plan["max_received_bytes"] == 64 * 1024 * 1024
    assert plan["parent_codex_attempt"] == 3 and plan["new_codex_attempts"] == plan["new_jobs_launched"] == 0


@pytest.mark.parametrize("fault", ["job", "project", "token", "escaped_token", "http", "oversize"])
def test_native_identity_secret_transport_bounds_refuse_with_no_following_request(tmp_path, fault):
    values = fixture(tmp_path, count=1)
    def reading(plan, endpoint, payload, seconds, claim):
        row = {"success": True, "backtest": {"backtestId": "foreign" if fault == "job" else payload["backtestId"],
            "projectId": 1 if fault == "project" else m.PROJECT, "completed": True, "status": "Completed.", "error": None, "progress": 1}}
        if fault in {"token", "escaped_token"}: row["secret"] = "SYNTHETIC-TOKEN"
        wire = e.canonical(row)
        if fault == "escaped_token": wire = wire.replace(b"SYNTHETIC-TOKEN", b"SYNTHETIC\\u002dTOKEN")
        if fault == "oversize": wire = b"x" * (m.READ_LIMITS[endpoint] + 1)
        return wire, 401 if fault == "http" else 200, "SYNTHETIC-TOKEN"
    result, _ = execute(values, reading)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["request_attempts"].fraction() == 1
    if fault == "http":
        assert result["requests"][0]["envelope"] is not None
        assert result["requests"][0]["status"] == "retained_http_failure"
        assert result["requests"][0]["native_success_accepted"] is False
    else: assert result["requests"][0]["envelope"] is None
    assert result["accepted_metrics"] is None and not (values[2] / "controller.lock").exists()


@pytest.mark.parametrize("fault", ["old_job", "wrong_ordinal", "gap_batch", "owner", "receipt_hash", "receipt_size", "source_hash", "naive_clock"])
def test_discovery_and_plan_scope_substitutions_refuse_before_native(tmp_path, fault):
    values = fixture(tmp_path, count=2); plan = values[0]
    reading, calls = transport()
    if fault == "old_job": plan["jobs"][0]["backtest_id"] = next(iter(m.discovery.PRIOR_JOBS))
    elif fault == "wrong_ordinal": plan["jobs"][0]["retrospective_owner_look_ordinal"] = 20
    elif fault == "gap_batch": plan["jobs"] = plan["jobs"][1:]; plan["jobs"][0]["retrospective_owner_look_ordinal"] = 21
    elif fault == "owner": plan["owner_instruction_sha256"] = "c" * 64
    elif fault == "receipt_hash": plan["discovery_reference"]["receipt_sha256"] = "c" * 64
    elif fault == "receipt_size": plan["discovery_reference"]["receipt_bytes"] -= 1
    elif fault == "source_hash": plan["source_hashes"][m.MODULE] = "c" * 64
    else: plan["created_utc"] = "2026-10-13T22:59:00"
    try: result, _ = execute(values, reading)
    except m.Refusal: result = {"status": "REFUSED"}
    assert result["status"] in {"REFUSED", "FAILED_OR_UNCERTAIN"} and calls == []


def test_later_chronological_batch_retains_all_unknown_ids_without_winner_selection(tmp_path):
    values = fixture(tmp_path, count=10, batch_start=8); result, _ = execute(values)
    assert result["status"] == "COMPLETED_CAPTURE"
    assert len(result["discovery"]["all_unfamiliar_job_ids"]) == 10
    assert result["discovery"]["batch_start"].fraction() == 8
    assert result["discovery"]["batch_end"].fraction() == 10
    assert [row["retrospective_owner_look_ordinal"].fraction() for row in result["jobs"]] == [29, 30]
    assert result["winner_selected"] is False


@pytest.mark.parametrize("mutation", ["count", "row_project", "row_duplicate", "mixed_clock", "aware_claim",
    "diagnostic_snapshot", "ledger_ordinal", "ledger_source_acceptance", "winner_pick"])
def test_diagnostic_projection_and_ledger_semantics_cannot_be_rebound_by_new_hashes(tmp_path, mutation):
    plan, sources, root, _ = fixture(tmp_path, count=2)
    diagnostic = e.parse_json((root / (m.DIAG_OPERATION + ".result.json")).read_bytes())
    projection = e.parse_json((root / m.PROJECTION_NAME).read_bytes())
    ledger = e.parse_json(sources[m.LEDGER])
    native = projection["projection"]["backtests"]
    if mutation == "count": projection["projection"]["count"] = 1
    elif mutation == "row_project": native[-1]["projectId"] = 1
    elif mutation == "row_duplicate": native[-1]["backtestId"] = native[-2]["backtestId"]
    elif mutation == "mixed_clock": native[-1]["created"] += "+00:00"
    elif mutation == "aware_claim": diagnostic["diagnostic"]["jobs"][-1]["created_is_timezone_aware"] = True
    elif mutation == "diagnostic_snapshot": diagnostic["diagnostic"]["jobs"][-1]["snapshotId"] = 999
    elif mutation == "ledger_ordinal": ledger["jobs"][-1]["look_ordinal"] = 29
    elif mutation == "ledger_source_acceptance": ledger["jobs"][-1]["compiled_source_proven"] = True
    else: plan["jobs"] = plan["jobs"][1:]
    projection["projection_sha256"] = m._sha(e.canonical(projection["projection"]))
    diagnostic["diagnostic"]["projection_sha256"] = projection["projection_sha256"]
    raw, projected_raw = e.canonical(diagnostic), e.canonical(projection)
    plan["discovery_reference"].update(receipt_bytes=len(raw), receipt_sha256=m._sha(raw),
        projection_bytes=len(projected_raw), projection_sha256=m._sha(projected_raw))
    ledger["diagnostic"].update(bytes=len(raw), sha256=m._sha(raw))
    ledger["projection"].update(bytes=len(projected_raw), sha256=m._sha(projected_raw))
    sources[m.LEDGER] = e.canonical(ledger)
    plan["source_hashes"][m.LEDGER] = m._sha(sources[m.LEDGER])
    with pytest.raises(m.Refusal): m._discovered(raw, projected_raw, plan, sources)


@pytest.mark.parametrize("count", [0, 1, 99, 100, 198, 199])
def test_order_page_census_has_exact_99_offsets_and_no_fill_fee_invention(tmp_path, count):
    values = fixture(tmp_path, count=1); reading, calls = transport(order_count=count); result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_CAPTURE"
    pages = [(payload["start"], payload["end"]) for endpoint, payload in calls if endpoint == "backtests/orders/read"]
    expected = max(1, (count + 98) // 99)
    assert pages == [(index * 99, (index + 1) * 99) for index in range(expected)]
    orders = result["jobs"][0]["orders"]
    assert orders["classification"] == "complete_order_page_census_only" and orders["order_count"].fraction() == count
    assert orders["fills"] is orders["fees"] is None


def test_pending_native_job_keeps_progress_not_a_terminal_or_metric(tmp_path):
    values = fixture(tmp_path, count=1); reading, calls = transport(pending=True); result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_CAPTURE" and len(calls) == 1
    job = result["jobs"][0]
    assert job["classification"] == "diagnostic_job_not_terminal" and job["terminal"]["progress"].lexeme == "0.7500"
    assert job["charts"] == {} and job["orders"] is None and job["logs"] == {}


@pytest.mark.parametrize("mutation", ["length", "duplicate"])
def test_inconsistent_order_census_is_never_accepted(tmp_path, mutation):
    values = fixture(tmp_path, count=1)
    def fault(endpoint, payload, body, _number):
        if endpoint == "backtests/orders/read" and payload["start"]:
            if mutation == "length": body["length"] = 101
            else: body["orders"][0]["id"] = 1
    reading, _ = transport(order_count=100, fault=fault); result, _ = execute(values, reading)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["accepted_metrics"] is None
    assert result["jobs"][0]["orders"]["classification"] != "complete_order_page_census_only"


@pytest.mark.parametrize("fault", ["missing_length", "wrong_shape", "duplicate_markers"])
def test_malformed_summary_does_not_prevent_independent_index(tmp_path, fault):
    values = fixture(tmp_path, count=1)
    def malformed(endpoint, payload, body, _number):
        if endpoint == "backtests/read/log" and payload["query"] == "EXT26_SUMMARY":
            if fault == "missing_length": body.pop("length")
            elif fault == "wrong_shape": body["logs"] = "bad shape"
            else: body.update(length=2, logs=["EXT26_SUMMARY {}", "EXT26_SUMMARY {}"])
    reading, calls = transport(fault=malformed); result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_CAPTURE" and calls[-1][1]["query"] == "EXT26_EVIDENCE_INDEX"
    assert result["jobs"][0]["logs"]["EXT26_SUMMARY"]["compact_validated"] is False


@pytest.mark.parametrize("clock", [lambda: NOW.replace(tzinfo=None), lambda: NOW + timedelta(hours=1),
    lambda: NOW.astimezone(timezone(timedelta(hours=1)))])
def test_aware_utc_actual_clock_required_before_private_or_native(tmp_path, clock):
    values = fixture(tmp_path, count=1); reading, calls = transport()
    with pytest.raises(m.Refusal): execute(values, reading, clock=clock)
    assert calls == [] and not (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()


@pytest.mark.parametrize("root", [m.LANE, m.PRIVATE_ROOT])
def test_fixture_cannot_point_at_actual_lane_or_private_root(tmp_path, root):
    values = fixture(tmp_path, count=1)
    with pytest.raises(m.Refusal): execute((values[0], values[1], root, values[3]))


@pytest.mark.parametrize("endpoint,payload", [("backtests/create", {"projectId": m.PROJECT}),
    ("backtests/read", {"projectId": 1, "backtestId": "synthetic-owner-job-000"}),
    ("backtests/read", {"projectId": m.PROJECT, "backtestId": "foreign"}),
    ("backtests/read/log", {"projectId": m.PROJECT, "backtestId": "synthetic-owner-job-000", "start": 0, "end": 100, "query": ""}),
    ("backtests/orders/read", {"projectId": m.PROJECT, "backtestId": "synthetic-owner-job-000", "start": 0, "end": 100})])
def test_only_exact_read_endpoints_and_payloads_are_allowed(tmp_path, endpoint, payload):
    plan = fixture(tmp_path, count=1)[0]
    with pytest.raises(m.Refusal): m._request_allowed(plan, endpoint, payload)


def test_request_claim_access_and_discovery_precede_each_transport(tmp_path):
    values = fixture(tmp_path, count=1); original, calls = transport()
    def reading(plan, endpoint, payload, seconds, claim):
        root = values[2]
        assert (root / (plan["operation_id"] + ".claim.spent.json")).exists()
        assert (root / (plan["operation_id"] + ".access.json")).exists()
        assert (root / (plan["operation_id"] + ".request." + claim["sha256"] + ".spent.json")).exists()
        return original(plan, endpoint, payload, seconds, claim)
    result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_CAPTURE" and len(calls) == 6


def test_final_guard_failure_is_retained_failed_not_clean_capture(tmp_path, monkeypatch):
    values = fixture(tmp_path, count=1); reading, calls = transport()
    reached = {"index_processed": False, "final_guard_refusals": 0}
    original = m._logs
    def processed_index(response, marker, identity, sources):
        result = original(response, marker, identity, sources)
        if marker == "EXT26_EVIDENCE_INDEX": reached["index_processed"] = True
        return result
    monkeypatch.setattr(m, "_logs", processed_index)
    def guard(_head):
        if reached["index_processed"]:
            reached["final_guard_refusals"] += 1
            raise m.Refusal("synthetic final drift")
    result, _ = execute(values, reading, guard=guard)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["accepted_metrics"] is None
    assert len(calls) == 6 and reached["final_guard_refusals"] == 1
    assert result["jobs"][0]["logs"]["EXT26_EVIDENCE_INDEX"]["classification"] == "diagnostic_missing_aggregate"
    assert result["jobs"][0]["orders"]["classification"] == "complete_order_page_census_only"
    assert len(result["jobs"][0]["charts"]) == 2
    assert not (values[2] / "controller.lock").exists()


def test_body_free_stdout_does_not_print_private_job_rows_or_native_error(monkeypatch, capsys):
    plan_raw = e.canonical({"mode": "production"})
    body = e.canonical({"operation_id": "SYNTHETIC", "status": "COMPLETED_CAPTURE", "request_attempts": 6,
        "jobs": [{"error": "SYNTHETIC PRIVATE ERROR", "rows": ["SYNTHETIC PRIVATE ORDER"]}]})
    monkeypatch.setattr(m, "execute_plan", lambda plan: body)
    assert m.main(["--plan-json", plan_raw.decode(), "--plan-sha256", m._sha(plan_raw)]) == 0
    output = capsys.readouterr().out
    assert "SYNTHETIC PRIVATE" not in output and "jobs" not in output
    assert e.parse_json(output.encode())["accepted_metrics"] is None
