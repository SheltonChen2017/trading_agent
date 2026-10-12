"""Synthetic fixed-job frontier diagnosis; actual credentials/network/private denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_frontier_diagnostic as f

e, N = f.e, f.e.JsonNumber
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in f.SOURCE_PATHS}


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("actual private/credentials/network/subprocess forbidden")
    monkeypatch.setattr(f.ops, "credential", denied)
    monkeypatch.setattr(f.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(f.subprocess, "run", denied)
    original = f._directory
    def directory(path, *, private):
        if private and path.is_relative_to(f.LANE):
            denied()
        return original(path, private=private)
    monkeypatch.setattr(f, "_directory", directory)


def fixture(tmp_path, action="logs", *, terminal_hashes=None):
    now = datetime.now(timezone.utc)
    root = tmp_path / "synthetic-frontier"
    root.mkdir(mode=0o700)
    plan = f._plan(action=action,
        operation_id=("TPR-EXT26-FRONTIER-" if action == "terminals" else "TPR-EXT26-ENGINE-LOG-") + "SYNTHETIC-001",
        source_hashes={name: f._sha(raw) for name, raw in SOURCES.items()}, git_head="c" * 40,
        owner_instruction_sha256="d" * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=3)).isoformat(), mode="offline-fixture")
    return plan, deepcopy(SOURCES), root, now


def execute(values, transport, **kwargs):
    plan, sources, root, now = values
    return e.parse_json(f._execute_fixture(plan, sources, root,
        clock=kwargs.pop("clock", lambda: now), transport=transport, **kwargs))


def transport_for(total=401, *, identity=True, alter=None):
    calls = []
    def transport(payload):
        calls.append(deepcopy(payload))
        length = min(f.PAGE_LINES, max(0, total - payload["start"]))
        response = {"success": True, "length": total, "logs": [
            "2024-07-12 Runtime Error in main.py line 1028; save_bytes; SYNTHETIC-PRIVATE-TICKER"
            for _ in range(length)]}
        if identity:
            response.update(projectId=f.PROJECT, backtestId=payload["backtestId"])
        if alter:
            alter(response, payload)
        return e.canonical(response), 200, "SYNTHETIC-USER", "SYNTHETIC-TOKEN"
    return transport, calls


def test_fixed_production_terminal_and_scope_constants():
    assert f.TERMINALS == (
        (2, "f79d3ff02644ec81f20da5cc6ca7440a", 1299525,
         "11d6db1fbdf381653897c317d80a083527d9e925a57ba591486c673dc2697173"),
        (3, "d7c76b7c4936c814f125a2b9a8cc2896", 1301513,
         "b5f7788177d117dd4dc95ae53c84cf6b60a15fc7410f5877b332743e618e7417"))
    assert f.PROJECT == 37650980 and f.MAX_PAGES == 20 and f.PAGE_LINES == 200
    assert f.MAX_REQUESTS == 40


@pytest.mark.parametrize("total", [0, 1, 200, 201, 401, 4000])
def test_unfiltered_pagination_total_is_not_page_count_and_no_cause_claim(tmp_path, total):
    values = fixture(tmp_path)
    transport, calls = transport_for(total)
    result = execute(values, transport)
    pages = max(1, (total + 199) // 200)
    assert result["status"] == "COMPLETED" and result["all_log_pages_observed"] is True
    assert len(calls) == pages * 2 and len(result["requests"]) == pages * 2
    assert {row["backtestId"] for row in calls} == {row[1] for row in f.TERMINALS}
    assert all(row["projectId"] == f.PROJECT and row["query"] == "" and row["end"] - row["start"] == 200 for row in calls)
    for job in result["jobs"]:
        assert job["total_matching_lines"].fraction() == job["observed_lines"].fraction() == total
        assert job["pages"].fraction() == pages and job["coverage_complete"] is True
        assert job["bounded_incomplete"] is False
        for diagnostic in job["diagnostics"]:
            assert diagnostic["cause_proved"] is False and diagnostic["raw_text_returned"] is False
    raw = e.canonical(result)
    assert b"SYNTHETIC-PRIVATE-TICKER" not in raw
    assert b"152710.74" not in raw
    assert result["new_looks"].fraction() == result["quantconnect_attempts"].fraction() == 0
    assert result["candidate_changed"] is result["cause_proved"] is result["performance_accepted"] is False
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError):
        execute(values, transport)
    assert len(calls) == pages * 2


def test_more_than_4000_lines_is_bounded_incomplete_not_new_scope(tmp_path):
    values = fixture(tmp_path)
    transport, calls = transport_for(4001)
    result = execute(values, transport)
    assert result["status"] == "BOUNDED_INCOMPLETE" and result["all_log_pages_observed"] is False
    assert len(calls) == 40
    assert all(row["observed_lines"].fraction() == 4000 and row["bounded_incomplete"] is True for row in result["jobs"])
    assert not any(row["start"] >= 4000 for row in calls)


def test_missing_returned_identity_stays_request_bound_not_provider_attested(tmp_path):
    transport, _ = transport_for(1, identity=False)
    result = execute(fixture(tmp_path), transport)
    assert result["status"] == "COMPLETED"
    for job in result["jobs"]:
        identity = job["request_response_identity"][0]
        assert identity["request_bound_to_fixed_job"] is True
        assert identity["returned_project_present_and_matching"] is False
        assert identity["returned_job_present_and_matching"] is False
        assert identity["provider_authenticity_attested"] is False


@pytest.mark.parametrize("fault", ["project", "job", "short_page", "total_drift", "unknown_length", "failed", "wrong_lines"])
def test_foreign_incomplete_or_drifting_log_response_retains_failed_claim_no_retry(tmp_path, fault):
    def alter(response, payload):
        if fault == "project": response["projectId"] = 1
        if fault == "job": response["backtestId"] = "foreign-job"
        if fault == "short_page": response["logs"].pop()
        if fault == "total_drift" and payload["start"]: response["length"] += 1
        if fault == "unknown_length": response.pop("length")
        if fault == "failed": response["success"] = False
        if fault == "wrong_lines": response["logs"][0] = {"private": "row"}
    values = fixture(tmp_path)
    transport, calls = transport_for(401, alter=alter)
    result = execute(values, transport)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["all_log_pages_observed"] is False
    assert len(calls) == (2 if fault == "total_drift" else 1)
    assert (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()
    terminal = values[2] / (values[0]["operation_id"] + ".attempt2.page" + ("01" if fault == "total_drift" else "00") + ".terminal.json")
    assert e.parse_json(terminal.read_bytes())["status"] == "failed_or_unknown"
    assert result["automatic_retry"] is False


@pytest.mark.parametrize("fault", ["secret", "user", "oversized", "interrupted"])
def test_wire_secret_size_and_uncertain_transport_refuse_before_projection_retention(tmp_path, fault):
    values = fixture(tmp_path)
    calls = []
    def transport(payload):
        calls.append(payload)
        if fault == "interrupted": raise KeyboardInterrupt()
        if fault == "oversized": return b"x" * (f.MAX_RESPONSE + 1), 200, "U-SYNTHETIC", "T-SYNTHETIC"
        return e.canonical({"success": True, "length": 1,
            "logs": ["T-SYNTHETIC" if fault == "secret" else "U-SYNTHETIC"]}), 200, "U-SYNTHETIC", "T-SYNTHETIC"
    result = execute(values, transport)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert not list(values[2].glob("*.projection.json"))
    assert list(values[2].glob("*.request.spent.json")) and list(values[2].glob("*.terminal.json"))
    assert b"T-SYNTHETIC" not in e.canonical(result) and b"U-SYNTHETIC" not in e.canonical(result)


def test_claim_is_durable_before_transport_and_shared_controller_lock_is_honored(tmp_path):
    values = fixture(tmp_path)
    seen = []
    transport, _ = transport_for(1)
    def guarded(payload):
        assert (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()
        assert (values[2] / (values[0]["operation_id"] + ".attempt2.page00.request.spent.json")).exists() if not seen else True
        seen.append(payload)
        return transport(payload)
    assert execute(values, guarded)["status"] == "COMPLETED" and len(seen) == 2


def test_existing_controller_lock_is_preserved_without_transport(tmp_path):
    values = fixture(tmp_path)
    locked = values[2] / "controller.lock"
    locked.write_bytes(b"synthetic other lane-owned controller")
    locked.chmod(0o600)
    def denied(_): raise AssertionError("transport must not be called")
    result = execute(values, denied)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and not result["requests"]
    assert locked.read_bytes() == b"synthetic other lane-owned controller"


def terminal_fixture(tmp_path, monkeypatch, *, field_change=False, status="Runtime Error"):
    tuples, payloads = [], []
    for attempt, job, _, _ in f.TERMINALS:
        statistics = {"End Equity": "152710.74", "Total Orders": "3076", "Total Fees": "192.26", "Drawdown": "15.0%"}
        if field_change and attempt == 3:
            statistics["Total Fees"] = "192.27"
        body = {"schema": "tpr-ext26-request-response-v1", "endpoint": "backtests/read", "stage": "backtest_status",
            "request": {"projectId": f.PROJECT, "backtestId": job}, "response": {"success": True,
            "backtest": {"backtestId": job, "projectId": f.PROJECT, "completed": True, "status": status,
                "error": "2024-07-12 00:00:00 ValueError in extended_core.py line 587; main.py line 1028; save_bytes; SYNTHETIC-TICKER",
                "rollingWindow": {"M6_20240131": {}, "M6_20240712": {}}, "tradeableDates": 1449, "statistics": statistics}}}
        raw = e.canonical(body)
        tuples.append((attempt, job, len(raw), f._sha(raw))); payloads.append(raw)
    monkeypatch.setattr(f, "TERMINALS", tuple(tuples))
    values = fixture(tmp_path, "terminals")
    for row, raw in zip(values[0]["terminals"], payloads):
        path = values[2] / row["name"]
        path.write_bytes(raw); path.chmod(0o600)
    return values


def test_exact_synthetic_terminals_date_frames_rolling_and_statistic_equality_no_values(tmp_path, monkeypatch):
    values = terminal_fixture(tmp_path, monkeypatch, field_change=True)
    def denied(_): raise AssertionError("terminal action must not call network")
    result = execute(values, denied)
    assert result["status"] == "COMPLETED" and not result["requests"]
    assert result["read_attempts"].fraction() == 2
    assert result["statistic_equality"]["End Equity"]["equal"] is True
    assert result["statistic_equality"]["Total Fees"]["equal"] is False
    assert result["statistic_equality"]["Start Equity"] == {"present_in_both": False, "equal": None}
    for row in result["jobs"]:
        assert row["schema_and_stage_match"] is True
        assert row["rolling_key_census"]["last_date_token"] == "2024-07-12"
        assert row["rolling_key_census"]["frontier_proves_engine_end_or_cause"] is False
        assert row["error_diagnostic"]["known_error_types"] == ["ValueError"]
        assert row["error_diagnostic"]["date_token_census"]["tokens"] == ["2024-07-12"]
    raw = e.canonical(result)
    assert b"152710.74" not in raw and b"192.26" not in raw and b"SYNTHETIC-TICKER" not in raw
    assert result["read_bytes"].fraction() == sum(row["bytes"] for row in values[0]["terminals"])


@pytest.mark.parametrize("fault", ["hash", "size", "mode", "symlink", "hardlink"])
def test_exact_descriptor_prebody_refusal_preserves_claim_and_no_later_terminal(tmp_path, monkeypatch, fault):
    values = terminal_fixture(tmp_path, monkeypatch)
    path = values[2] / values[0]["terminals"][0]["name"]
    if fault == "hash": path.write_bytes(b"x" * path.stat().st_size); path.chmod(0o600)
    if fault == "size": path.write_bytes(b"x"); path.chmod(0o600)
    if fault == "mode": path.chmod(0o644)
    if fault == "symlink":
        actual = path.with_name("synthetic-target"); path.rename(actual); path.symlink_to(actual)
    if fault == "hardlink": os.link(path, path.with_name("synthetic-link"))
    count = []
    original = f.os.read
    def observed(fd, size): count.append(size); return original(fd, size)
    monkeypatch.setattr(f.os, "read", observed)
    result = execute(values, lambda _: pytest.fail("no network"))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["read_attempts"].fraction() == 1
    assert not result["jobs"]
    assert len(list(values[2].glob("*.read.spent.json"))) == 1
    if fault != "hash": assert not count


@pytest.mark.parametrize("fault", ["scope", "source", "prefix", "unknown", "production_seam"])
def test_source_time_closed_plan_or_production_seam_refuses_before_claim(tmp_path, fault):
    values = fixture(tmp_path)
    plan, sources, root, now = values
    if fault == "scope":
        plan["expires_utc"] = (now + timedelta(hours=5)).isoformat()
    if fault == "source": sources[f.SOURCE_RELATIVE] += b"# uncommitted change\n"
    if fault == "prefix": plan["operation_id"] = "TPR-EXT26-FRONTIER-WRONG-ACTION"
    if fault == "unknown": plan["surprise"] = True
    if fault == "production_seam": plan["mode"] = "production"
    with pytest.raises((f.Refusal, KeyError)):
        execute(values, lambda _: pytest.fail("no network"))
    assert not list(root.iterdir())


def test_public_output_keywords_are_evidence_not_causal_or_performance_classification():
    output = f._text_diagnostic(["2024-07-12 end of data; cancelled; time limit; MemoryError; save_bytes; main.py:1028"])
    assert output["keyword_line_counts"]["data_exhaustion"] == 1
    assert output["keyword_line_counts"]["stop_or_cancel"] == 1
    assert output["keyword_line_counts"]["time_limit"] == 1
    assert output["keyword_line_counts"]["audit_export"] == 1
    assert output["cause_proved"] is output["raw_text_returned"] is False


def test_private_projection_sanitizes_known_profile_fields_and_emails():
    raw = e.canonical({"success": True, "length": 1, "logs": ["contact synthetic@example.invalid"],
        "ownerId": "synthetic-owner", "collaborators": [{"publicId": "synthetic-public", "profileImage": "synthetic-image", "bio": "synthetic-bio"}]})
    output = f._secret_free(raw, "synthetic-user", "synthetic-token")
    projected = output["projection"]
    assert projected["ownerId"] == "[redacted]"
    assert projected["collaborators"][0] == {"publicId": "[redacted]", "profileImage": "[redacted]", "bio": "[redacted]"}
    assert projected["logs"] == ["contact [redacted-email]"]
    assert output["projection_sha256"] == f._sha(e.canonical(projected))


# TPR-CR24-001 regressions: live guards that the received suite never exercised.
# Each is red when the named guard is removed from the producer.


def test_non_200_status_with_a_well_formed_body_is_refused_before_diagnosis(tmp_path):
    """`http_status != 200` guard: a 502 carrying a plausible body spends the request and stops."""
    values = fixture(tmp_path)
    transport, calls = transport_for(1)
    def proxied(payload):
        raw, _status, user, token = transport(payload)
        return raw, 502, user, token
    result = execute(values, proxied)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["all_log_pages_observed"] is False
    assert result["requests"][0]["status"] == "failed_or_unknown"
    assert result["jobs"][0]["diagnostics"] == [] and result["jobs"][0]["observed_lines"].fraction() == 0
    assert result["automatic_retry"] is False


def test_expired_plan_refuses_before_any_claim_or_transport(tmp_path):
    """Clock-window guard: a clock at the expiry instant refuses before the claim exists."""
    plan, sources, root, now = fixture(tmp_path)
    expired = f._clock(plan["expires_utc"])
    with pytest.raises(f.Refusal):
        execute((plan, sources, root, now), lambda _: pytest.fail("no network"), clock=lambda: expired)
    assert not list(root.iterdir())


def test_expiry_during_pagination_stops_further_requests_and_keeps_the_claim(tmp_path):
    """Clock-window guard inside the loop: expiry after the first body stops the second job."""
    plan, sources, root, now = fixture(tmp_path)
    transport, calls = transport_for(1)
    expired = f._clock(plan["expires_utc"])
    result = execute((plan, sources, root, now), transport, clock=lambda: expired if calls else now)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert (root / (plan["operation_id"] + ".claim.spent.json")).exists()
    assert not list(root.glob("*.projection.json"))
    terminal = root / (plan["operation_id"] + ".attempt2.page00.terminal.json")
    assert e.parse_json(terminal.read_bytes())["status"] == "failed_or_unknown"


def test_monotonic_budget_exhaustion_stops_further_requests(tmp_path):
    """`max_seconds` guard: once the elapsed budget is spent no further request is made."""
    values = fixture(tmp_path)
    transport, calls = transport_for(1)
    budget = float(values[0]["max_seconds"])
    result = execute(values, transport, monotonic=lambda: budget * len(calls))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["all_log_pages_observed"] is False and result["automatic_retry"] is False


def test_well_formed_substitute_terminal_with_a_different_hash_is_refused(tmp_path, monkeypatch):
    """Exact-SHA guard: a same-size, parseable terminal whose bytes differ is not read as evidence."""
    values = terminal_fixture(tmp_path, monkeypatch)
    row = values[0]["terminals"][0]
    path = values[2] / row["name"]
    raw = path.read_bytes()
    assert raw.count(b"3076") == 1
    substitute = raw.replace(b"3076", b"3075")
    assert len(substitute) == row["bytes"] and f._sha(substitute) != row["sha256"]
    path.write_bytes(substitute); path.chmod(0o600)
    result = execute(values, lambda _: pytest.fail("no network"))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["read_attempts"].fraction() == 1
    assert not result["jobs"] and result["statistic_equality"] is None


def test_completed_rather_than_failed_terminal_is_outside_the_fixed_scope(tmp_path, monkeypatch):
    """Scope guard: only `Runtime Error` terminals of the two fixed jobs are diagnosable."""
    values = terminal_fixture(tmp_path, monkeypatch, status="Completed")
    result = execute(values, lambda _: pytest.fail("no network"))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["read_attempts"].fraction() == 1
    assert not result["jobs"]
