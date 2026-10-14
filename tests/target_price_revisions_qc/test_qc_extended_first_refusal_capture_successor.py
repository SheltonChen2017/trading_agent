"""Synthetic-only look31 plans/replies; never native/provider/private I/O."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import subprocess

import pytest

from research.target_price_revisions_qc import extended_first_refusal_capture_successor as m

e = m.e
ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "research" / "target_price_revisions_qc"
NOW = datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*_args, **_kwargs): raise AssertionError("native/private/operator effect forbidden")
    monkeypatch.setattr(m.ops, "credential", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(http.client, "HTTPSConnection", denied)


def descriptor(name, size=100):
    return {"name": name, "bytes": size, "sha256": "d" * 64}


def arguments(action="collect-native"):
    post = "TPR-EXT26-MIA-SOURCE-POST-20261014-999"
    return {"action": action, "capture_operation_id": "TPR-EXT26-MIA-FIRST-REFUSAL-RESULT-20261014-999",
        "git_head": "b" * 40, "owner_instruction_sha256": "c" * 64,
        "created_utc": NOW.isoformat(), "expires_utc": (NOW + timedelta(minutes=10)).isoformat(),
        "source_inventory": {name: {"bytes": size, "sha256": sha} for name, size, sha in m.SOURCES},
        "preflight": {"operation_id": post, "ended_utc": (NOW - timedelta(seconds=2)).isoformat(),
            "receipt": descriptor(post + ".result.json"), "sources": descriptor(post + ".read2.sources.json"),
            "diff": descriptor(post + ".diff.json")},
        "mia": {"operation_id": m.OPERATION, "actor": m.ACTOR, "compile_id": "synthetic-mia-compile",
            "backtest_id": "a" * 32, "legacy_attempt": 3, "codex_attempts_consumed": 3,
            "observed_looks_before": 30, "look_ordinal": 31,
            "ui_ledger": descriptor(m.OPERATION + ".ui-ledger.json"),
            "look_receipt": descriptor(m.OPERATION + ".look.json")}}


def plan(action="collect-native"):
    return m.build_plan(**arguments(action))


def base(p):
    return {"projectId": m.PROJECT, "backtestId": p["mia"]["backtest_id"]}


def payload(p, endpoint, *, start=0, query="EXT26_SUMMARY", chart="EXT26 Account NAV"):
    result = base(p)
    if endpoint == "backtests/read/log": result.update(start=0, end=100, query=query)
    if endpoint == "backtests/orders/read": result.update(start=start, end=start + m.PAGE_SIZE)
    if endpoint == "backtests/chart/read":
        result.update(name=chart, count=2000, start=1609718400, end=1791590400)
    return result


def envelope(p, endpoint, response, **kwargs):
    return m.retain_response(p, endpoint, payload(p, endpoint, **kwargs), e.canonical(response), 200, credential="SYNTHETIC-TOKEN")


def terminal(p, status="Completed", **changes):
    row = {**base(p), "compileId": p["mia"]["compile_id"], "completed": True,
           "progress": 1, "status": status, "error": None}
    row.update(changes)
    return {"success": True, **base(p), "backtest": row}


def test_plan_is_prospective_no_look_reset_and_copies_caller_sources():
    args = arguments()
    p = m.build_plan(**args)
    assert p["mia_look_counted_externally"] == 31
    assert p["new_looks"] == p["new_codex_attempts"] == 0
    assert p["config_sha256"] == m.CONFIG and p["freeze_sha256"] == m.FREEZE
    assert p["calendar_sha256"] == m.CALENDAR and len(p["source_inventory"]) == 16
    args["mia"]["ui_ledger"]["bytes"] = 900
    args["source_inventory"]["main.py"]["bytes"] = 1
    assert p["mia"]["ui_ledger"]["bytes"] == 100 and p["source_inventory"]["main.py"]["bytes"] == 60658
    assert m.validate_plan(e.parse_json(e.canonical(p))) == p
    receipt = m.initial_receipt(p)
    for key in ("terminal", "summary_count", "index_count", "order_count", "fill_count", "fee_values", "accepted_metrics"):
        assert receipt[key] is None
    for key in ("full_window_verified", "native_accounting_verified", "compiled_source_proven", "strategy_accepted"):
        assert receipt[key] is False


@pytest.mark.parametrize("field,value", [
    ("operation_id", "TPR-EXT26-MIA-RECOVERY-20261012-001"), ("actor", "codex-generic-agent"),
    ("legacy_attempt", 4), ("codex_attempts_consumed", 0), ("observed_looks_before", 19), ("look_ordinal", 20),
    ("look_ordinal", True), ("compile_id", ""), ("backtest_id", "synthetic-old-job")])
def test_mia_binding_refuses_old_labels_reset_and_unbound_job(field, value):
    args = arguments(); args["mia"][field] = value
    with pytest.raises(ValueError): m.build_plan(**args)


@pytest.mark.parametrize("job", sorted(m.PRIOR_JOBS))
def test_every_known_historical_job_cannot_be_relabelled_as_31(job):
    args = arguments(); args["mia"]["backtest_id"] = job
    with pytest.raises(ValueError): m.build_plan(**args)


@pytest.mark.parametrize("fault", ["remove", "extra", "main", "context", "writer", "notebook", "clock", "descriptor"])
def test_inventory_and_fresh_preflight_fail_closed(fault):
    args = arguments()
    if fault == "remove": args["source_inventory"].pop("mia.ipynb")
    if fault == "extra": args["source_inventory"]["extra.py"] = {"bytes": 1, "sha256": "1" * 64}
    if fault in {"main", "context", "writer", "notebook"}:
        key = {"main": "main.py", "context": "extended_refusal_witness_context_successor.py",
               "writer": "extended_compressed_store.py", "notebook": "mia.ipynb"}[fault]
        args["source_inventory"][key]["sha256"] = "1" * 64
    if fault == "clock": args["preflight"]["ended_utc"] = (NOW - timedelta(minutes=15, microseconds=1)).isoformat()
    if fault == "descriptor": args["preflight"]["sources"]["name"] = "other.private.json"
    with pytest.raises(ValueError): m.build_plan(**args)


@pytest.mark.parametrize("field,value", [
    ("accepted_metrics", {"return": "1"}), ("strategy_accepted", True), ("new_looks", 1),
    ("max_order_pages", 129), ("config_sha256", "1" * 64), ("extra", None)])
def test_rebound_or_widened_plan_is_not_a_capture_grant(field, value):
    p = plan(); p[field] = value
    with pytest.raises(ValueError): m.validate_plan(p)


def test_scope_inclusive_start_exclusive_expiry_total_time_and_preflight_age():
    p = plan(); m.check_scope(p, NOW, 0, 0)
    m.check_scope(p, NOW + timedelta(seconds=599), 599.9, m.MAX_TOTAL)
    for now, elapsed, received in ((NOW - timedelta(seconds=1), 0, 0),
            (NOW + timedelta(seconds=600), 599, 0), (NOW, 600, 0),
            (NOW, float("nan"), 0), (NOW, True, 0), (NOW, 0, m.MAX_TOTAL + 1)):
        with pytest.raises(ValueError): m.check_scope(p, now, elapsed, received)
    args = arguments(); args["preflight"]["ended_utc"] = (NOW - timedelta(minutes=15)).isoformat()
    with pytest.raises(ValueError): m.check_scope(m.build_plan(**args), NOW + timedelta(seconds=1), 1, 0)


@pytest.mark.parametrize("endpoint", [name for name, _ in m.READ_LIMITS])
def test_exact_read_templates_and_status_only_boundary(endpoint):
    p = plan(); supplied = payload(p, endpoint)
    assert m.request_allowed(p, endpoint, supplied) == supplied
    for fault in ({**supplied, "projectId": 37650453}, {**supplied, "retry": True}, {**supplied, "backtestId": "f" * 32}):
        with pytest.raises(ValueError): m.request_allowed(p, endpoint, fault)
    if endpoint != "backtests/read":
        with pytest.raises(ValueError): m.request_allowed(plan("status"), endpoint, payload(plan("status"), endpoint))


@pytest.mark.parametrize("endpoint", ["object/read", "object/get", "object/list", "files/update", "backtests/create", "compile/create"])
def test_no_export_enumeration_write_or_launch_request(endpoint):
    with pytest.raises(ValueError): m.request_allowed(plan(), endpoint, base(plan()))


def test_log_query_chart_window_and_order_page_refusals():
    p = plan()
    for endpoint, bad in [
        ("backtests/read/log", payload(p, "backtests/read/log", query="RAW_WITNESS")),
        ("backtests/chart/read", payload(p, "backtests/chart/read", chart="Other")),
        ("backtests/orders/read", payload(p, "backtests/orders/read", start=1)),
        ("backtests/orders/read", payload(p, "backtests/orders/read", start=m.MAX_PAGES * m.PAGE_SIZE))]:
        with pytest.raises(ValueError): m.request_allowed(p, endpoint, bad)
    m.request_allowed(p, "backtests/orders/read", payload(p, "backtests/orders/read", start=127 * 99))


def test_full_private_projection_keeps_numeric_tokens_and_raw_descriptor_before_schema_refusal():
    p = plan(); endpoint = "backtests/read"
    wire = b'{"success":false,"user":{"email":"SYNTHETIC"},"measurement":1.2300,"detail":"SYNTHETIC ERROR"}'
    desc = m.wire_descriptor(p, endpoint, base(p), wire, 500)
    assert desc["sha256"] == hashlib.sha256(wire).hexdigest()
    raw = m.retain_response(p, endpoint, base(p), wire, 500, credential="SYNTHETIC-TOKEN")
    body = e.parse_json(raw)
    assert body["response"]["measurement"].lexeme == "1.2300"
    assert body["response"]["user"]["email"] == "[redacted]"
    assert body["response"]["detail"] == "SYNTHETIC ERROR"
    with pytest.raises(ValueError): m.response_from_envelope(p, raw)
    malformed = b'{"success":true,"success":false}'
    assert m.wire_descriptor(p, endpoint, base(p), malformed, 200)["bytes"] == len(malformed)
    with pytest.raises(ValueError): m.retain_response(p, endpoint, base(p), malformed, 200, credential="SYNTHETIC-TOKEN")


def test_oversize_refusal_byte_descriptor_and_credential_echo():
    p = plan(); endpoint = "backtests/read/log"; request = payload(p, endpoint)
    wire = b"x" * (dict(m.READ_LIMITS)[endpoint] + 1)
    assert m.wire_descriptor(p, endpoint, request, wire, 200)["bytes"] == len(wire)
    with pytest.raises(ValueError): m.retain_response(p, endpoint, request, wire, 200, credential="SYNTHETIC-TOKEN")
    with pytest.raises(ValueError): m.wire_descriptor(p, endpoint, request, wire + b"x", 200)
    with pytest.raises(ValueError):
        m.retain_response(p, endpoint, request, b'{"success":true,"message":"SYNTHETIC-TOKEN"}', 200, credential="SYNTHETIC-TOKEN")


def test_request_attempt_total_budget_and_refusal_byte_reserved_before_transport():
    p = plan(); endpoint = "backtests/orders/read"
    reserve = dict(m.READ_LIMITS)[endpoint] + 1
    m.request_budget(p, endpoint, 132, m.MAX_TOTAL - reserve)
    for attempts, received in ((133, 0), (0, m.MAX_TOTAL - reserve + 1), (True, 0), (-1, 0)):
        with pytest.raises(ValueError): m.request_budget(p, endpoint, attempts, received)
    m.request_budget(plan("status"), "backtests/read", 0, 0)
    with pytest.raises(ValueError): m.request_budget(plan("status"), "backtests/read", 1, 0)


@pytest.mark.parametrize("changes", [
    {"compileId": "foreign"}, {"backtestId": "f" * 32}, {"projectId": 37650453},
    {"progress": 0}, {"error": "unexpected"}, {"status": "Runtime Error", "error": None}])
def test_terminal_returned_identity_or_completed_claim_never_bypasses(changes):
    p = plan(); raw = envelope(p, "backtests/read", terminal(p, **changes))
    with pytest.raises(ValueError): m.terminal_observation(p, raw)


def test_completed_error_and_running_remain_diagnostic_and_preserve_error_nulls():
    p = plan()
    for response in (terminal(p), terminal(p, "Runtime Error", error="SYNTHETIC PRIVATE ERROR"),
                     terminal(p, "Running", completed=False, progress=0)):
        result = m.terminal_observation(p, envelope(p, "backtests/read", response))
        assert result["accepted_metrics"] is None and result["native_accounting_verified"] is False
        assert result["strategy_accepted"] is False
        assert result["terminal"] is (response["backtest"]["status"] != "Running")
        assert "SYNTHETIC PRIVATE ERROR" not in e.canonical(result).decode()


@pytest.mark.parametrize("missing", [True, False])
def test_native_compile_id_unobserved_stays_false_null_not_a_collection_blocker(missing):
    p = plan(); response = terminal(p)
    if missing: response["backtest"].pop("compileId")
    else: response["backtest"]["compileId"] = None
    result = m.terminal_observation(p, envelope(p, "backtests/read", response))
    assert result["terminal"] is True
    assert result["compile_id_returned_and_matching"] is False
    assert result["native_compile_id"] is None
    assert result["compiled_source_proven"] is False
    assert result["native_accounting_verified"] is False and result["accepted_metrics"] is None
    response["backtest"]["compileId"] = p["mia"]["compile_id"]
    observed = m.terminal_observation(p, envelope(p, "backtests/read", response))
    assert observed["compile_id_returned_and_matching"] is True
    assert observed["native_compile_id"] == p["mia"]["compile_id"]
    assert observed["compiled_source_proven"] is False
    response["backtest"].pop("backtestId")
    with pytest.raises(ValueError): m.terminal_observation(p, envelope(p, "backtests/read", response))


def test_missing_compact_logs_are_measured_zero_but_not_accepted():
    p = plan()
    result = m.compact_observation(p, envelope(p, "backtests/read/log", {"success": True, "logs": [], "length": 0}))
    assert result["count"] == 0 and result["aggregate"] is None
    assert result["accepted_metrics"] is None


@pytest.mark.parametrize("logs,length", [
    (["EXT26_SUMMARY {\"candidate_id\":\"unfinished"], 1), (["a", "b"], 2), ([], 1)])
def test_truncated_duplicate_or_missing_log_refuses_without_repair(logs, length):
    p = plan(); raw = envelope(p, "backtests/read/log", {"success": True, "logs": logs, "length": length})
    assert b"logs" in raw  # retained exact projected reply is available before refusal
    with pytest.raises(ValueError): m.compact_observation(p, raw)


def orders(p, total, start, ids):
    return envelope(p, "backtests/orders/read", {"success": True, "length": total,
        "orders": [{"id": value, "quantity": 10, "price": None} for value in ids]}, start=start)


def test_unique_bounded_order_census_not_fill_fee_or_independent_sleeve_pnl():
    p = plan(); state = m.append_order_page(p, m.OrderCensus(), orders(p, 100, 0, range(99)))
    assert len(state.ids) == 99 and state.total == 100
    final = m.append_order_page(p, state, orders(p, 100, 99, [99]))
    assert len(final.ids) == 100 and len(final.page_descriptors) == 2
    with pytest.raises(ValueError): m.append_order_page(p, final, orders(p, 100, 198, []))
    empty = m.append_order_page(p, m.OrderCensus(), orders(p, 0, 0, []))
    assert empty.total == 0 and empty.ids == ()  # actually observed, not unreached/null


@pytest.mark.parametrize("fault", ["duplicate", "total", "page", "missing", "foreign_plan", "cap"])
def test_order_duplicates_changed_total_gap_missing_and_caps_refuse(fault):
    p = plan(); state = m.append_order_page(p, m.OrderCensus(), orders(p, 100, 0, range(99)))
    if fault == "foreign_plan":
        p = deepcopy(p); p["capture_operation_id"] = "TPR-EXT26-MIA-FIRST-REFUSAL-RESULT-20261014-998"
    if fault == "cap":
        state = replace(state, page_descriptors=((1, "a" * 64),) * 128)
    raw = orders(p, 101 if fault == "total" else 100, 198 if fault == "page" else 99,
                 [] if fault == "missing" else [98 if fault == "duplicate" else 99])
    with pytest.raises(ValueError): m.append_order_page(p, state, raw)


def test_account_nav_loading_missing_clock_census_and_exact_frozen_calendar():
    p = plan(); calendar = (PUBLIC / "extended_calendar.json").read_bytes()
    raw = envelope(p, "backtests/chart/read", {"success": True, "status": "loading"})
    result, normalized = m.account_nav_observation(p, raw, calendar)
    assert result["classification"] == "diagnostic_loading_chart" and normalized is None
    assert result["complete_daily_account_nav"] is False and result["private_journal_replay_verified"] is False
    with pytest.raises(ValueError): m.account_nav_observation(p, raw, calendar + b" ")
    with pytest.raises(ValueError):
        m.account_nav_observation(p, envelope(p, "backtests/chart/read", {"success": True}, chart="Strategy Equity"), calendar)


def test_inventory_nine_original_modules_match_public_immutable_bundle_and_successor():
    bundle = json.loads((PUBLIC / "extended_source_bundle_completion.json").read_bytes())
    frozen = next(row for row in bundle["candidates"] if row["candidate_id"] == m.CANDIDATE)["files"]
    identities = {name: (size, sha) for name, size, sha in m.SOURCES}
    assert set(frozen) - {"main.py"} <= identities.keys()
    for name in set(frozen) - {"main.py"}:
        raw = frozen[name].encode()
        assert identities[name] == (len(raw), hashlib.sha256(raw).hexdigest())
    raw = (PUBLIC / "extended_refusal_witness_context_successor.py").read_bytes()
    assert identities["extended_refusal_witness_context_successor.py"] == (len(raw), hashlib.sha256(raw).hexdigest())
    assert len(m.PRIOR_JOBS) == 14
    history = json.loads((PUBLIC / "extended_owner_recovery_observations30.json").read_bytes())
    observed = set(history["known_historical_jobs"]) | {row["backtest_id"] for row in history["jobs"]}
    assert m.PRIOR_JOBS == observed
    for job in observed:
        args = arguments(); args["mia"]["backtest_id"] = job
        with pytest.raises(ValueError): m.build_plan(**args)


def test_valid_closed_index_and_cancel_propagation(monkeypatch):
    p = plan(); job = p["mia"]["backtest_id"]
    aggregate = {"index_key": "tpr-ext26/evidence/" + m.CANDIDATE + "/" + m.CONFIG
        + "/attempt-3/" + str(m.PROJECT) + "/" + job + "/index.json",
        "index_sha256": "e" * 64, "chunks": 1, "records": 1, "bytes": 10,
        "candidate_id": m.CANDIDATE, "attempt": 3, "config_sha256": m.CONFIG,
        "freeze_sha256": m.FREEZE, "project_id": m.PROJECT, "job_id": job,
        "record_kind_counts": {"SUMMARY": 1}, "internally_meaningful_execution": False,
        "strategy_accepted": False, "canonical_admission": False}
    response = {"success": True, "length": 1,
        "logs": ["EXT26_EVIDENCE_INDEX " + e.canonical(aggregate).decode()]}
    raw = envelope(p, "backtests/read/log", response, query="EXT26_EVIDENCE_INDEX")
    observed = m.compact_observation(p, raw)
    assert observed["count"] == 1 and observed["accepted_metrics"] is None
    assert observed["full_journal_replay_verified"] is False
    def cancelled(*_args, **_kwargs): raise KeyboardInterrupt
    monkeypatch.setattr(m.ops, "_returned_identity", cancelled)
    with pytest.raises(KeyboardInterrupt): m.compact_observation(p, raw)


# TPR-CR27 regression: the credential-echo guard cannot be switched off by omission.


def test_retain_response_requires_the_credential_keyword():
    """A caller that forgets the credential gets a TypeError, not a silently unguarded envelope."""
    p = plan()
    endpoint = "backtests/read"
    with pytest.raises(TypeError):
        m.retain_response(p, endpoint, base(p), b'{"success":true,"message":"SYNTHETIC-TOKEN"}', 200)
    with pytest.raises(ValueError):
        m.retain_response(p, endpoint, base(p), b'{"success":true,"message":"SYNTHETIC-TOKEN"}', 200, credential="SYNTHETIC-TOKEN")
