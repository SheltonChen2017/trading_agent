"""Only synthetic terminal/accounting evidence; actual effects denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_owner_mia_terminal_successor as m

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)
TOKEN = "SYNTHETIC-TOKEN"


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*_args, **_kwargs): raise AssertionError("actual credential/network/private/subprocess forbidden")
    monkeypatch.setattr(m.ops, "credential", denied)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    directory = m.files._directory
    def bounded(path, *, private):
        if private and path.is_relative_to(m.LANE): denied()
        return directory(path, private=private)
    monkeypatch.setattr(m.files, "_directory", bounded)


def wire(*, points=0, error="SYNTHETIC PRIVATE ERROR OnEndOfAlgorithm", runtime=True):
    body = {"success": True, "backtest": {"backtestId": m.JOB, "projectId": m.PROJECT,
        "status": "RuntimeError" if runtime else "Completed.", "completed": True,
        "error": error if runtime else None, "progress": 1, "statistics": [0] * points}}
    return json.dumps(body, separators=(",", ":")).encode()


def fixture(tmp_path):
    root = tmp_path / "synthetic-terminal"; root.mkdir(mode=0o700)
    sources = deepcopy(SOURCES)
    known = sorted(m.discovery._frozen({name: sources[name] for name in m.discovery.SOURCE_PATHS}))
    unknown = ["synthetic-external-job-" + f"{number:02d}" for number in range(9)] + [m.JOB]
    rows = [{"backtestId": identity, "created": (NOW - timedelta(minutes=20 - index)).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "RuntimeError" if identity == m.JOB else "Completed.", "progress": 1,
        "snapshotId": index + 1, "projectId": m.PROJECT} for index, identity in enumerate(known + unknown)]
    projected = m.discovery._projection(e.canonical({"success": True, "count": len(rows), "backtests": rows}), TOKEN)
    projected_raw = e.canonical(projected)
    diagnostic = {"schema": "tpr-ext26-owner-mia-metadata-inspect-receipt-v1", "operation_id": m.original.DIAG_OPERATION,
        "status": "COMPLETED_DIAGNOSTIC_INSPECTION", "scope_spent": True, "api_requests": 0, "new_jobs": 0,
        "diagnostic": {"success": True, "count": len(rows), "returned_rows": len(rows),
            "projection_sha256": projected["projection_sha256"], "wire_sha256": projected["original_wire_sha256"],
            "wire_bytes": projected["original_wire_bytes"], "jobs": [{**row, "created_is_timezone_aware": False} for row in rows]}}
    diagnostic_raw = e.canonical(diagnostic)
    ref = {"operation_id": m.original.DIAG_OPERATION, "receipt_bytes": len(diagnostic_raw), "receipt_sha256": m._sha(diagnostic_raw),
        "projection_name": m.original.PROJECTION_NAME, "projection_bytes": len(projected_raw), "projection_sha256": m._sha(projected_raw)}
    ledger = e.parse_json(sources[m.original.LEDGER])
    ledger.update(owner_instruction_sha256="b" * 64, known_historical_jobs=known, newly_observed_jobs=10,
        diagnostic={"name": m.original.DIAG_OPERATION + ".result.json", "bytes": len(diagnostic_raw), "sha256": m._sha(diagnostic_raw)},
        projection={"name": m.original.PROJECTION_NAME, "bytes": len(projected_raw), "sha256": m._sha(projected_raw)},
        jobs=[{"look_ordinal": 21 + index, "backtest_id": row["backtestId"], "created_server_string": row["created"],
            "status": row["status"], "snapshot_id": row["snapshotId"], "creation_timezone_known": False,
            "retrospective": True, "origin_authenticated_as_mia": False, "compiled_source_proven": False,
            "accepted_metrics": None, "economics_accepted": False} for index, row in enumerate(rows[len(known):])])
    sources[m.original.LEDGER] = e.canonical(ledger)
    parent = {"schema": "tpr-ext26-owner-mia-components-receipt-v1", "operation_id": m.PARENT_NAME[:-12],
        "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "new_jobs_launched": 0,
        "new_codex_attempts": 0, "new_looks": 0, "parent_codex_attempt": 3, "project_id": m.PROJECT,
        "declared_candidate_id": m.CANDIDATE, "accepted_metrics": None, "compiled_source_proven": False,
        "economics_accepted": False, "source_hashes": {m.original.MODULE: m.ORIGINAL_SHA256},
        "discovery_reference": ref, "jobs": [{"backtest_id": unknown[-2], "retrospective_owner_look_ordinal": 29},
            {"backtest_id": m.JOB, "retrospective_owner_look_ordinal": 30, "terminal": None}],
        "requests": [{} for _ in range(6)] + [{"backtest_id": m.JOB, "endpoint": "backtests/read",
            "status": "failed_or_unknown", "envelope": None}]}
    parent_raw = e.canonical(parent)
    directory = m.files._directory(root, private=True)
    try:
        for name, raw in ((m.PARENT_NAME, parent_raw), (m.original.DIAG_OPERATION + ".result.json", diagnostic_raw),
                (m.original.PROJECTION_NAME, projected_raw)):
            m.capture._publish(directory, name, raw)
    finally: os.close(directory)
    plan = m._plan(operation_id="TPR-EXT26-OWNER-MIA-TERMINAL-SYNTHETIC-001", git_head="a" * 40,
        source_hashes={name: m._sha(raw) for name, raw in sources.items()}, owner_instruction_sha256="b" * 64,
        created_utc=(NOW - timedelta(seconds=1)).isoformat(), expires_utc=(NOW + timedelta(minutes=30)).isoformat(),
        parent_reference={"name": m.PARENT_NAME, "bytes": len(parent_raw), "sha256": m._sha(parent_raw)}, mode="offline-fixture")
    return plan, sources, root


def transport(*, terminal=None, order_fault=False):
    calls = []
    def reading(plan, endpoint, payload, seconds, claim):
        assert 0 < seconds <= 30 and payload["projectId"] == m.PROJECT and payload["backtestId"] == m.JOB
        m._request_allowed(endpoint, payload)
        raw_claim = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": m._sha(e.canonical(plan))})
        assert claim == {"bytes": len(raw_claim), "sha256": m._sha(raw_claim)}
        calls.append((endpoint, deepcopy(payload)))
        if endpoint == "backtests/read": return terminal if terminal is not None else wire(points=110000), 200, TOKEN
        if endpoint == "backtests/chart/read":
            if payload["name"] == "EXT26 Account NAV":
                response = {"success": True, "chart": {"name": "EXT26 Account NAV", "series": {
                    "NAV": {"name": "NAV", "unit": "$", "seriesType": 0, "values": [[1609794060, 100]] * 12}}}}
            else: response = {"success": True, "status": "loading"}
        elif endpoint == "backtests/orders/read":
            response = {"success": True, "length": 1, "orders": [] if order_fault else [{"id": 1, "price": e.JsonNumber("1.0000100")}]}
        else:
            response = {"success": True, "length": 1 if payload["query"] == "EXT26_SUMMARY" else 0,
                "logs": ['EXT26_SUMMARY {"truncated":"'] if payload["query"] == "EXT26_SUMMARY" else []}
        return e.canonical(response), 200, TOKEN
    return reading, calls


def execute(values, reading=None, **kwargs):
    if reading is None: reading = transport()[0]
    raw = m.execute_fixture(*values, clock=lambda: NOW, transport=reading, **kwargs)
    return e.parse_json(raw), raw


def test_selective_terminal_crosses_original_node_budget_without_repair_or_raw_error():
    raw = wire(points=110000)
    with pytest.raises(e.EvidenceError): e.project_wire(raw, credential=TOKEN)
    result = m.terminal_projection(raw, credential=TOKEN)
    assert result["current_response_exceeds_original_100k_node_bound"] is True
    assert result["earlier_original_refusal_cause_proven"] is False
    assert result["json_value_nodes_scanned"] > e.MAX_NODES and e.MAX_NODES == 100000
    assert result["projection"]["backtest"]["native_status"] == "RuntimeError"
    assert result["projection"]["backtest"]["terminal"]["status"] == "Runtime Error"
    assert result["projection"]["backtest"]["error_stage_marker_observations"] == ["end_callback_marker"]
    assert b"SYNTHETIC PRIVATE ERROR" not in e.canonical(result) and b"statistics" not in e.canonical(result["projection"])
    assert result["raw_wire_retained"] is result["raw_error_retained"] is result["compiled_source_proven"] is False


@pytest.mark.parametrize("nodes,exceeds", [(100000, False), (100001, True)])
def test_exact_legacy_node_boundary_counts_values_and_containers_not_keys(nodes, exceeds):
    baseline = m.SelectiveTerminalParser(wire(), TOKEN); baseline.parse()
    raw = wire(points=nodes - baseline.nodes)
    result = m.terminal_projection(raw, credential=TOKEN)
    assert result["json_value_nodes_scanned"] == nodes and result["current_response_exceeds_original_100k_node_bound"] is exceeds
    if exceeds:
        with pytest.raises(e.EvidenceError): e.project_wire(raw, credential=TOKEN)
    else: assert e.project_wire(raw, credential=TOKEN)["original_wire_bytes"] == len(raw)


@pytest.mark.parametrize("tail,code", [
    (b'"late":"SYNTHETIC-TOKEN"', "credential_echo_refused"),
    (b'"late":"SYNTHETIC\\u002dTOKEN"', "credential_echo_refused"),
    (b'"SYNTHETIC\\u002dTOKEN":0', "credential_echo_refused"),
    (b'"a":0,"\\u0061":1', "duplicate_key_refused"),
    (b'"late":01', "syntax_refused"), (b'"late":NaN', "syntax_refused"),
    (b'"late":1e129', "numeric_token_refused"), (b'"late":' + b"1" * 129, "numeric_token_refused"),
    (b'"late":' + b"[" * 33 + b"0" + b"]" * 33, "depth_bound_refused"),
])
def test_late_ignored_statistics_are_completely_scanned_before_hash_or_metadata(tail, code):
    raw = wire().replace(b'"statistics":[]', b'"statistics":{' + tail + b"}")
    with pytest.raises(m.ParseRefusal) as caught: m.terminal_projection(raw, credential=TOKEN)
    assert caught.value.code == code


@pytest.mark.parametrize("raw,code", [(b"\xff", "utf8_refused"), (wire() + b" true", "syntax_refused"),
    (wire().replace(b'"success":true', b'"success":true,"success":true'), "duplicate_key_refused"),
    (wire(points=m.MAX_TERMINAL_NODES), "node_bound_refused"),
    (wire().replace(m.JOB.encode(), b"foreign-job"), "foreign_identity_refused"),
    (wire().replace(b'"status":"RuntimeError"', b'"status":"SYNTHETIC PRIVATE STATUS"'), "terminal_shape_refused")])
def test_closed_parser_refusals_never_return_partial_terminal_metadata(raw, code):
    with pytest.raises(m.ParseRefusal) as caught: m.terminal_projection(raw, credential=TOKEN)
    assert caught.value.code == code and "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("identity", [
    b'"projectId":1,', b'"project\\u0049d":1,', b'"backtestId":"foreign-job",', b'"backtest\\u0049d":"foreign-job",',
    b'"projectId":{},', b'"backtestId":[],'])
def test_explicit_foreign_root_identities_are_not_dropped_by_selective_projection(identity):
    raw = wire().replace(b'{"success":', b"{" + identity + b'"success":')
    with pytest.raises(m.ParseRefusal) as caught: m.terminal_projection(raw, credential=TOKEN)
    assert caught.value.code == "foreign_identity_refused"


@pytest.mark.parametrize("channel", ["chart", "orders"])
def test_unexpected_root_identity_containers_are_refused_without_retaining_market_rows(channel):
    raw = wire().replace(b'{"success":', b'{"' + channel.encode() + b'":{"projectId":1},"success":')
    with pytest.raises(m.ParseRefusal) as caught: m.terminal_projection(raw, credential=TOKEN)
    assert caught.value.code == "unexpected_identity_container_refused"


def test_valid_explicit_root_identities_remain_observed_not_inferred():
    raw = wire().replace(b'{"success":', b'{"projectId":37650980,"backtestId":"' + m.JOB.encode() + b'","success":')
    result = m.terminal_projection(raw, credential=TOKEN)
    checks = result["projection"]["returned_identity_checks"]
    assert checks["observed_project_id_fields"] == checks["observed_backtest_id_fields"] == 2
    assert checks["absent_identifiers_inferred"] is False


@pytest.mark.parametrize("field", ["error", "projectId", "progress"])
def test_composite_selected_terminal_fields_are_not_silently_replaced_with_null(field):
    body = json.loads(wire(runtime=False)); body["backtest"][field] = {}
    with pytest.raises(m.ParseRefusal): m.terminal_projection(json.dumps(body).encode(), credential=TOKEN)


def test_independent_components_retained_after_original_projection_refusal(tmp_path):
    values = fixture(tmp_path); reading, calls = transport(); result, raw = execute(values, reading)
    assert result["status"] == "COMPLETED_DIAGNOSTIC_CAPTURE" and len(calls) == 6
    assert result["terminal"]["native_status"] == "RuntimeError"
    assert result["charts"]["EXT26 Account NAV"]["observations"].fraction() == 12
    assert result["charts"]["EXT26 Account NAV"]["expected_observations"].fraction() == 1449
    assert result["charts"]["EXT26 Account NAV"]["classification"] == "diagnostic_incomplete_daily_census"
    assert result["charts"]["Strategy Equity"]["classification"] == "diagnostic_loading_chart"
    assert result["orders"]["classification"] == "complete_order_page_census_only"
    assert result["orders"]["fees"] is result["orders"]["fills"] is None
    assert result["logs"]["EXT26_SUMMARY"]["compact_validated"] is False
    assert result["logs"]["EXT26_EVIDENCE_INDEX"]["observed_matching_log_count"].fraction() == 0
    assert all(payload["backtestId"] == m.JOB for _endpoint, payload in calls)
    assert result["new_jobs_launched"].fraction() == result["new_codex_attempts"].fraction() == result["new_looks"].fraction() == 0
    assert result["retrospective_parent_look29_replayed"] is result["full_window_accounting_proven"] is False
    assert raw == (values[2] / (values[0]["operation_id"] + ".result.json")).read_bytes()
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values, reading)
    assert len(calls) == 6


def test_terminal_safety_refusal_keeps_http_but_no_hash_or_error_or_metadata_and_no_suppressed_components(tmp_path):
    unsafe = wire(points=110000).replace(b'"statistics":[', b'"late":"SYNTHETIC\\u002dTOKEN","statistics":[')
    values = fixture(tmp_path); reading, calls = transport(terminal=unsafe); result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_DIAGNOSTIC_CAPTURE" and len(calls) == 6
    item = result["requests"][0]
    assert item["http_status"].fraction() == 200 and item["wire_bytes"].fraction() == len(unsafe)
    assert item["refusal_classification"] == "credential_echo_refused"
    assert item["envelope"] is item["wire_sha256"] is result["terminal"] is None
    assert result["accepted_metrics"] is None and result["logs"]["EXT26_EVIDENCE_INDEX"] is not None


def test_invalid_order_census_does_not_suppress_summary_or_index(tmp_path):
    values = fixture(tmp_path); reading, calls = transport(order_fault=True); result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_DIAGNOSTIC_CAPTURE"
    assert result["component_refusals"] == ["order_census_shape_refused"]
    assert [payload["query"] for endpoint, payload in calls if endpoint == "backtests/read/log"] == ["EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"]


@pytest.mark.parametrize("mutation", ["job", "look", "parent_hash", "source_hash", "owner", "expired"])
def test_closed_look30_parent_and_source_scope_refuses_before_effect(tmp_path, mutation):
    values = fixture(tmp_path); plan = values[0]; reading, calls = transport()
    if mutation == "job": plan["backtest_id"] = "other"
    elif mutation == "look": plan["retrospective_owner_look_ordinal"] = 29
    elif mutation == "parent_hash": plan["parent_reference"]["sha256"] = "c" * 64
    elif mutation == "source_hash": plan["source_hashes"][m.MODULE] = "c" * 64
    elif mutation == "owner": plan["owner_instruction_sha256"] = "c" * 64
    else: plan["expires_utc"] = (NOW - timedelta(seconds=1)).isoformat()
    try: result, _ = execute(values, reading)
    except m.Refusal: result = {"status": "REFUSED"}
    assert result["status"] in {"REFUSED", "FAILED_OR_UNCERTAIN"} and calls == []


def test_claim_access_parent_and_request_are_durable_before_transport(tmp_path):
    values = fixture(tmp_path); original_transport, calls = transport()
    def reading(plan, endpoint, payload, seconds, claim):
        root = values[2]
        assert (root / (plan["operation_id"] + ".claim.spent.json")).exists()
        assert (root / (plan["operation_id"] + ".access.json")).exists()
        assert (root / (plan["operation_id"] + ".request." + claim["sha256"] + ".spent.json")).exists()
        return original_transport(plan, endpoint, payload, seconds, claim)
    result, _ = execute(values, reading)
    assert result["status"] == "COMPLETED_DIAGNOSTIC_CAPTURE" and len(calls) == 6


def test_post_transport_guard_failure_has_known_http_no_stage_inference(tmp_path):
    values = fixture(tmp_path); reading, calls = transport()
    def guard(_head):
        if calls: raise m.Refusal("synthetic concurrent drift")
    result, _ = execute(values, reading, guard=guard)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["requests"][0]["http_status"].fraction() == 200 and result["terminal"] is None
    assert result["requests"][0]["pipeline_phase"] == "post_transport_source_time_guard"
    assert result["requests"][0]["envelope"] is result["requests"][0]["wire_sha256"] is None


def test_final_guard_is_after_all_independent_index_processing(tmp_path, monkeypatch):
    values = fixture(tmp_path); reading, calls = transport(); reached = {"index": False}
    original_logs = m.original._logs
    def logs(response, marker, identity, sources):
        result = original_logs(response, marker, identity, sources)
        if marker == "EXT26_EVIDENCE_INDEX": reached["index"] = True
        return result
    monkeypatch.setattr(m.original, "_logs", logs)
    def guard(_head):
        if reached["index"]: raise m.Refusal("synthetic final drift")
    result, _ = execute(values, reading, guard=guard)
    assert len(calls) == 6 and result["status"] == "FAILED_OR_UNCERTAIN"
    assert result["logs"]["EXT26_EVIDENCE_INDEX"]["classification"] == "diagnostic_missing_aggregate"


@pytest.mark.parametrize("root", [m.LANE, m.PRIVATE_ROOT])
def test_fixtures_cannot_open_actual_root(tmp_path, root):
    plan, sources, _ = fixture(tmp_path)
    with pytest.raises(m.Refusal): execute((plan, sources, root))


def test_stdout_is_body_free_and_no_metric_or_stage_acceptance(monkeypatch, capsys):
    body = e.canonical({"operation_id": "SYNTHETIC", "status": "COMPLETED_DIAGNOSTIC_CAPTURE", "request_attempts": 6,
        "terminal": {"error": "SYNTHETIC PRIVATE ERROR", "statistics": [999]}})
    monkeypatch.setattr(m, "execute_plan", lambda _plan: body)
    plan_raw = e.canonical({"mode": "production"})
    assert m.main(["--plan-json", plan_raw.decode(), "--plan-sha256", m._sha(plan_raw)]) == 0
    printed = capsys.readouterr().out
    assert "PRIVATE" not in printed and "terminal" not in printed and "statistics" not in printed
    assert e.parse_json(printed.encode())["accepted_metrics"] is None


# TPR-CR27 regression: an interrupt during one request ends the scope, it does not continue the read loop.


def test_interrupt_during_a_request_stops_further_reads_and_fails_the_scope(tmp_path):
    values = fixture(tmp_path); calls = []
    def interrupted(plan, endpoint, payload, seconds, claim):
        calls.append(endpoint); raise KeyboardInterrupt()
    result, _raw = execute(values, interrupted)
    assert calls == ["backtests/read"] and result["status"] == "FAILED_OR_UNCERTAIN"
    assert result["requests"][0]["status"] == "failed_or_unknown" and result["terminal"] is None
