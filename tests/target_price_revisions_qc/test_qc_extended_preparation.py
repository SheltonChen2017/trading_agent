"""Synthetic-only focused preparation custody and packet parity tests.

The always-on firewall forbids actual lane/private leaves, subprocesses,
credentials and provider connections. Only the public frozen calendar is read
at collection; fixtures build FAILED synthetic74-Massive + completed2-Sharadar sources.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_preparation as p
from research.target_price_revisions_qc import extended_preparation_driver as driver

ACTUAL_LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
ORIGINAL_OPEN, ORIGINAL_READ = p.capture._open_directory, p._read_private
CALENDAR = Path("research/target_price_revisions_qc/extended_calendar.json").read_bytes()
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
CREATED, EXPIRES = "2026-10-10T00:00:00+00:00", "2026-10-11T00:00:00+00:00"
PIN, OWNER = "c" * 40, "b" * 64


@pytest.fixture(autouse=True)
def real_io_firewall(monkeypatch):
    def guarded_open(path):
        selected = Path(path)
        if selected == ACTUAL_LANE_ROOT or selected.is_relative_to(ACTUAL_LANE_ROOT):
            pytest.fail("actual lane/private leaf forbidden in preparation fixtures")
        return ORIGINAL_OPEN(selected)
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credentials, network or subprocess forbidden in preparation fixtures")
    monkeypatch.setattr(p.capture, "_open_directory", guarded_open)
    monkeypatch.setattr(p.capture.probe, "_open_directory", guarded_open)
    monkeypatch.setattr(p.capture.helper, "_production_credential", forbidden)
    monkeypatch.setattr(p.capture, "_https_get", forbidden)
    monkeypatch.setattr(p.capture.probe, "_https_get", forbidden)
    monkeypatch.setattr(p.capture.http.client, "HTTPSConnection", forbidden)
    monkeypatch.setattr(p.repair, "_FIXED_RESOLVER", forbidden)
    monkeypatch.setattr(p.repair, "_FIXED_TRANSPORT", forbidden)
    monkeypatch.setattr(p.subprocess, "run", forbidden)
    return guarded_open, forbidden


def inventory():
    return {key: p.repair.PUBLIC_HASHES.get(key, "a" * 64) for key in p.SOURCE_PATHS}


def revision(window, **changes):
    return {"benzinga_id": "EVENT-" + window[0], "benzinga_firm_id": "FIRM-1", "ticker": "SYNABC",
        "date": window[0], "last_updated": window[0] + "T12:00:00Z", "currency": "USD",
        "price_target_action": "raises", "price_target": "101.0000000000000000001",
        "previous_price_target": "100.0000000000000000000", **changes}


def response(payload, kind):
    return p.capture.CaptureResponse(200, (("content-type", kind), ("content-length", str(len(payload)))), payload)


def transport(provider, dataset, query, _credential, _seconds):
    if provider == "massive":
        values = dict(query)
        window = values["date.gte"], values["date.lte"]
        return response(p._canonical({"status": "OK", "results": [revision(window)]}), "application/json")
    text = ("ticker,permaticker,figi,category,exchange,isdelisted\nSYNABC,1,BBGABCDEF123,Domestic Common Stock,NASDAQ,N\n"
        if dataset == "tickers" else "ticker,date,action,contraticker\nSYNABC,1999-01-02,listed,\n")
    return response(text.encode(), "text/csv")


def capture_plan():
    return p.capture.freeze_capture_plan(source_hashes={key: inventory()[key] for key in p.capture.SOURCE_PATHS},
        git_sha=PIN, owner_instruction_sha256=OWNER, created_utc=CREATED, expires_utc=EXPIRES,
        mode="offline-fixture")


@pytest.fixture
def leaves(tmp_path):
    source, output, repaired = tmp_path / "synthetic_capture", tmp_path / "synthetic_inputs", tmp_path / "synthetic_repair"
    source.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    repaired.mkdir(mode=0o700)
    def failed_transport(provider, dataset, query, credential, seconds):
        if provider == "sharadar":
            wire = b"ticker,permaticker,figi,category,exchange,isdelisted\nSYNZZZ,2,BBGABCDEF234,Domestic Common Stock,NASDAQ,N\nSYNABC,1,BBGABCDEF123,Domestic Common Stock,NASDAQ,N\n"
            return response(wire, "text/csv")
        return transport(provider, dataset, query, credential, seconds)
    result = p.capture._execute_fixture_capture(capture_plan(), source, now=NOW,
        credential_resolver=lambda _: "SYNTHETIC_TOKEN_abcdef", transport=failed_transport)
    assert json.loads(result.payload)["status"] == "FAILED"
    selected = p.repair.freeze_repair_plan(source_hashes={key: inventory()[key] for key in p.repair.SOURCE_PATHS},
        git_sha=PIN, owner_instruction_sha256=OWNER, created_utc=CREATED, expires_utc=EXPIRES, mode="offline-fixture")
    result = p.repair._execute_fixture_repair(selected, repaired, now=NOW,
        credential_resolver=lambda _: "SYNTHETIC_TOKEN_abcdef", transport=transport)
    assert json.loads(result.payload)["status"] == "COMPLETED"
    return source, output


def plan(source, **changes):
    repaired = source.parent / "synthetic_repair"
    arguments = dict(source_hashes=inventory(), git_sha=PIN, owner_instruction_sha256=OWNER,
        created_utc=CREATED, expires_utc=EXPIRES, mode="offline-fixture", capture_git_sha=PIN,
        capture_index_sha256=p._sha((source / p.capture.INDEX_NAME).read_bytes()),
        capture_plan_sha256=p._sha((source / (p.capture.OPERATION_ID + ".plan.json")).read_bytes()),
        capture_report_sha256=p._sha((source / (p.capture.OPERATION_ID + ".aggregate.json")).read_bytes()),
        repair_git_sha=PIN, repair_index_sha256=p._sha((repaired / p.repair.INDEX_NAME).read_bytes()),
        repair_plan_sha256=p._sha((repaired / (p.repair.OPERATION_ID + ".plan.json")).read_bytes()),
        repair_report_sha256=p._sha((repaired / (p.repair.OPERATION_ID + ".aggregate.json")).read_bytes()))
    if changes.get("mode") == "production":
        arguments.update({"capture_" + key: value for key, value in p.ORIGINAL_CAPTURE.items()})
    arguments.update(changes)
    return p.freeze_preparation_plan(**arguments)


def execute(leaves, *, selected=None, now=NOW, monotonic=lambda: 0.0):
    source, output = leaves
    return p._execute_fixture_preparation(selected or plan(source), source, output,
        repair_root=source.parent / "synthetic_repair", calendar_payload=CALENDAR, now=now, monotonic=monotonic)


def report(result):
    return json.loads(result.payload)


def update_json(path, mutate):
    body = json.loads(path.read_bytes())
    mutate(body)
    path.write_bytes(p._canonical(body))
    path.chmod(0o600)
    return body


def rebind_index(source, mutate):
    index_path = source / p.capture.INDEX_NAME
    index = update_json(index_path, mutate)
    digest = p._sha(index_path.read_bytes())
    update_json(source / (p.capture.OPERATION_ID + ".terminal.json"), lambda body: body.update(index_sha256=digest))
    return index


def test_fixed_plan_complete_source_closure_and_limits(leaves):
    body = plan(leaves[0]).body()
    assert p.SOURCE_RELATIVE in body["source_hashes"] and p.DRIVER_RELATIVE in body["source_hashes"]
    assert p.SCORER_RELATIVE in body["source_hashes"] and p.RAW_RELATIVE in body["source_hashes"]
    assert body["limits"] == p.LIMITS
    assert body["limits"]["max_elapsed_seconds"] == 5400
    assert body["old_receipts_renewed"] is body["outcome_access"] is body["quantconnect"] is False
    assert body["capture_operation_id"] == p.capture.OPERATION_ID
    assert body["calendar_sha256"] == p._sha(CALENDAR)


def test_complete_capture_replay_preserves_every_native_row(leaves):
    selected = plan(leaves[0])
    directory = ORIGINAL_OPEN(leaves[0])
    try:
        index, rows, counts, semantic = p._replay_capture(directory, selected.body(), lambda: None)
        assert len(rows["ratings"]) == 74
        assert rows["tickers"] == rows["actions"] == []
        assert counts["source_rows"] == index["report"]["source_rows"] == 74
        repaired = ORIGINAL_OPEN(leaves[0].parent / "synthetic_repair")
        try:
            repaired_index, repaired_rows, repaired_counts, repaired_semantic = p._replay_capture(repaired, selected.body(), lambda: None, repaired=True)
            for key in rows: rows[key].extend(repaired_rows[key])
            assert len(rows["tickers"]) == len(rows["actions"]) == 1
            assert repaired_counts["source_rows"] == repaired_index["report"]["source_rows"] == 2
        finally:
            os.close(repaired)
        result = p._BUILD_FRAMES(rows["ratings"], rows["tickers"], rows["actions"],
            calendar_payload=CALENDAR, capture_utc=index["ended_utc"])
        payloads = p._packet_payloads(result, json.loads(CALENDAR), index["ended_utc"], lambda: None)
        assert len(payloads) == 71
    finally:
        os.close(directory)


@pytest.mark.parametrize("changes", [{"source_hashes": {}}, {"source_hashes": {**inventory(), "extra": "a"*64}},
    {"source_hashes": {**inventory(), p.CALENDAR_RELATIVE: "0"*64}}, {"git_sha": "Z"*40},
    {"capture_git_sha": "Z"*40}, {"capture_index_sha256": "Z"*64}, {"owner_instruction_sha256": None},
    {"mode": "fixture"}, {"created_utc": "2026-10-10T00:00:00"}, {"expires_utc": CREATED},
    {"expires_utc": "2026-10-13T00:00:00Z"}])
def test_bad_plan_refused_before_private_reads(leaves, changes):
    with pytest.raises(p.PreparationError):
        plan(leaves[0], **changes)
    assert not list(leaves[1].iterdir())


@pytest.mark.parametrize("key,value", [("private_root", "/tmp/unowned"), ("lane_branch", "main"),
    ("capture_operation_id", "old-capture"), ("outcome_access", True), ("old_receipts_renewed", True)])
def test_rehashed_widened_plan_refused(leaves, key, value):
    body = plan(leaves[0]).body()
    body[key] = value
    payload = p._canonical(body)
    with pytest.raises(p.PreparationError):
        p.PreparationPlan(payload, p._sha(payload)).body()


def test_plan_byte_tamper_refused(leaves):
    selected = plan(leaves[0])
    with pytest.raises(p.PreparationError):
        replace(selected, payload=selected.payload+b" ").body()


def test_claim_precedes_every_capture_read_and_second_access_is_refused(leaves, monkeypatch):
    source, output = leaves
    calls = []
    def claimed_read(directory, name, *arguments, **keywords):
        assert (output / (p.OPERATION_ID + ".access.spent.json")).is_file()
        calls.append(name)
        return ORIGINAL_READ(directory, name, *arguments, **keywords)
    monkeypatch.setattr(p, "_read_private", claimed_read)
    result = execute(leaves)
    assert report(result)["status"] == "COMPLETED"
    assert len(calls) > 300
    calls.clear()
    with pytest.raises(ValueError):
        execute(leaves)
    assert not calls


def test_private_payload_and_public_receipt_end_to_end_no_hash_cycle(leaves):
    source, output = leaves
    result = execute(leaves)
    observed = report(result)
    assert set(observed) == p.PUBLIC_KEYS
    assert driver._safe_result(result) == observed
    assert observed["status"] == "COMPLETED" and observed["source_input_prepared"] is True
    assert observed["source_rows"] == 76
    assert observed["decision_count"] == 301 and observed["monthly_shards"] == 70
    assert observed["payload_count"] == 72
    receipt_wire = (output / "preparation.json").read_bytes()
    receipt = json.loads(receipt_wire)
    assert p._sha(receipt_wire) == observed["preparation_sha256"]
    assert b"SYNABC" not in receipt_wire and b"SHARADAR:1" not in receipt_wire and b"101.000" not in receipt_wire
    assert receipt["signal_source_census"]["pre_warmup_actions_audit_only"] == 1
    assert receipt["signal_source_census"]["signal_window_actions"] == 0
    assert receipt["capture_census"]["terminated_massive_windows"] == 74
    assert receipt["capture_census"]["terminated_sharadar_datasets"] == 0
    assert receipt["capture_census"]["status"] == "FAILED"
    assert receipt["repair_census"]["terminated_sharadar_datasets"] == 2
    assert receipt["repair_census"]["status"] == "COMPLETED"
    assert receipt["schema"] == "tpr-ext26-preparation-v2"
    assert receipt["original_failed_sharadar_wire_used_for_inputs"] is False
    manifest_wire = (output / (observed["manifest_sha256"] + ".json")).read_bytes()
    assert p._sha(manifest_wire) == observed["manifest_sha256"]
    manifest = json.loads(manifest_wire)
    prefix = "tpr-ext26/inputs/" + p.STUDY_ID + "/" + observed["preparation_sha256"] + "/"
    assert manifest["identity_key"] == prefix + manifest["identity_sha256"] + ".json"
    assert [day for shard in manifest["shards"] for day in shard["sessions"]] == [r["session"] for r in json.loads(CALENDAR)["decisions"]]
    for row in receipt["payloads"]:
        wire = (output / (row["sha256"] + ".json")).read_bytes()
        assert p._sha(wire) == row["sha256"] and len(wire) == row["bytes"]
        body = json.loads(wire)
        if row["kind"] == "signal-month":
            assert body["sessions"] == row["sessions"]
            assert body["identity_sha256"] == manifest["identity_sha256"]
            assert all(len(frame["states"]) == observed["identity_count"] for frame in body["frames"])
            assert all(frame["states"][0]["state"] in {"scored", "no_admissible_event", "unknown_input"} for frame in body["frames"])
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())
    assert observed["outcome_reads"] == observed["development_looks"] == observed["quantconnect_attempts"] == 0


@pytest.mark.parametrize("key,value", [("status", "COMPLETED"), ("capture_complete", True),
    ("terminated_massive_windows", 73), ("terminated_sharadar_datasets", 1),
    ("outcome_reads", 1), ("source_rows", 75), ("row_refusals", 1),
    ("reserved_requests", 77), ("point_in_time_data", True)])
def test_incomplete_or_drifted_capture_report_is_spent_failure(leaves, key, value):
    rebind_index(leaves[0], lambda body: body["report"].update({key: value}))
    result = execute(leaves)
    assert report(result)["status"] == "FAILED"
    assert (leaves[1] / (p.OPERATION_ID + ".access.spent.json")).exists()
    assert not (leaves[1] / "preparation.json").exists()


@pytest.mark.parametrize("mutation", [
    lambda body: body["census"][0].update(terminated=False),
    lambda body: body["census"].pop(),
    lambda body: body["census"][0].update(pages=2),
    lambda body: body["pages"][0].update(wire_file="../bad"),
    lambda body: body["pages"][0].update(projection_file="another.json"),
    lambda body: body["pages"][0].update(response_complete=False),
    lambda body: body["pages"][0].update(page=True),
    lambda body: body["pages"][0].update(fetch_utc="2026-10-12T00:00:00Z"),
    lambda body: body.update(source_hashes={}),
    lambda body: body.update(git_sha="d"*40),
])
def test_scope_page_binding_tamper_is_refused_without_projection(leaves, mutation):
    rebind_index(leaves[0], mutation)
    assert report(execute(leaves))["status"] == "FAILED"


def test_changed_index_digest_is_refused(leaves):
    selected = plan(leaves[0])
    update_json(leaves[0]/p.capture.INDEX_NAME, lambda body: body.update(failure="drift"))
    assert report(execute(leaves, selected=selected))["status"] == "FAILED"


def test_projection_hash_rebound_but_wire_disagrees_is_refused(leaves):
    source, _output = leaves
    index = json.loads((source / p.capture.INDEX_NAME).read_bytes())
    projection_path = source / index["pages"][0]["projection_file"]
    update_json(projection_path, lambda body: body["rows"][0]["source"].update(price_target="999"))
    wire = projection_path.read_bytes()
    rebind_index(source, lambda body: body["pages"][0].update(projection_sha256=p._sha(wire), projection_bytes=len(wire)))
    assert report(execute(leaves))["status"] == "FAILED"


@pytest.mark.parametrize("file_type", ["wire", "projection", "terminal", "claim"])
def test_missing_private_capture_component_refused(leaves, file_type):
    suffix = {"wire": ".wire.json", "projection": ".projection.json", "terminal": ".terminal.json", "claim": ".spent.json"}[file_type]
    (leaves[0] / ("request.0001" + suffix)).unlink()
    assert report(execute(leaves))["status"] == "FAILED"


@pytest.mark.parametrize("violation", ["public_mode", "symlink", "hardlink", "fifo", "truncated"])
def test_private_projection_custody_refuses_substitution(leaves, violation):
    path = leaves[0] / "request.0001.projection.json"
    if violation == "public_mode": path.chmod(0o644)
    elif violation == "truncated": path.write_bytes(b"{}\n")
    else:
        saved = path.with_name("saved-projection.json")
        path.rename(saved)
        if violation == "symlink": path.symlink_to(saved)
        elif violation == "hardlink": os.link(saved, path)
        else: os.mkfifo(path, 0o600)
    assert report(execute(leaves))["status"] == "FAILED"


def test_original_page_terminal_does_not_claim_projection_fields(leaves):
    source, _output = leaves
    update_json(source / "request.0001.terminal.json", lambda body: body.update(disposition="projected"))
    assert report(execute(leaves))["status"] == "FAILED"


def test_original_request_claim_binding_refused(leaves):
    update_json(leaves[0]/"request.0001.spent.json", lambda body: body.update(plan_sha256="0"*64))
    assert report(execute(leaves))["status"] == "FAILED"


@pytest.mark.parametrize("now", [datetime(2026,10,10), datetime(2026,10,9,tzinfo=timezone.utc),
    datetime(2026,10,11,tzinfo=timezone.utc)])
def test_bad_clock_before_claim_no_capture_access(leaves, now, monkeypatch):
    monkeypatch.setattr(p, "_read_private", lambda *_a, **_k: pytest.fail("capture read before valid claim"))
    with pytest.raises(p.PreparationError):
        execute(leaves, now=now)
    assert not list(leaves[1].iterdir())


def test_bad_calendar_before_claim(leaves):
    source, output = leaves
    with pytest.raises(p.PreparationError):
        p._execute_fixture_preparation(plan(source), source, output, repair_root=source.parent/"synthetic_repair",
            calendar_payload=CALENDAR+b" ", now=NOW)
    assert not list(output.iterdir())


def test_elapsed_bound_spends_but_does_not_read_capture(leaves, monkeypatch):
    ticks = iter((0.0, 5400.0))
    monkeypatch.setattr(p, "_read_private", lambda *_a, **_k: pytest.fail("read beyond processing budget"))
    assert report(execute(leaves, monotonic=lambda: next(ticks)))["status"] == "FAILED"
    assert (leaves[1] / (p.OPERATION_ID + ".access.spent.json")).exists()


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), "0"])
def test_bad_monotonic_clock_refused_before_claim(leaves, invalid):
    with pytest.raises(p.PreparationError):
        execute(leaves, monotonic=lambda: invalid)
    assert not list(leaves[1].iterdir())


def test_monotonic_rollback_spends_and_refuses_before_read(leaves, monkeypatch):
    ticks = iter((1.0, 0.5))
    monkeypatch.setattr(p, "_read_private", lambda *_a, **_k: pytest.fail("read after monotonic rollback"))
    assert report(execute(leaves, monotonic=lambda: next(ticks)))["status"] == "FAILED"


@pytest.mark.parametrize("limit", ["max_wire_bytes", "max_projection_bytes", "max_source_rows",
    "max_identity_bytes", "max_monthly_bytes", "max_payload_bytes", "max_manifest_bytes"])
def test_processing_or_payload_ceiling_refuses_without_dropping(leaves, monkeypatch, limit):
    monkeypatch.setitem(p.LIMITS, limit, 1)
    assert report(execute(leaves))["status"] == "FAILED"
    assert not (leaves[1]/"preparation.json").exists()


def test_scorer_refusal_preserved_without_filtering_source(leaves, monkeypatch):
    def scorer_refusal(ratings, identities, actions, **_keywords):
        assert len(ratings) == 74 and len(identities) == len(actions) == 1
        raise ValueError("SYNABC LICENSED 101.000 SHOULD NEVER LEAK")
    monkeypatch.setattr(p, "_BUILD_FRAMES", scorer_refusal)
    result = execute(leaves)
    assert report(result)["status"] == "FAILED"
    assert b"SYNABC" not in result.payload and b"LICENSED" not in result.payload


def test_scorer_omitted_frame_fails_before_payload_publication(leaves, monkeypatch):
    original = p._BUILD_FRAMES
    def omit(*args, **kwargs):
        result = original(*args, **kwargs)
        result["frames"].pop()
        return result
    monkeypatch.setattr(p, "_BUILD_FRAMES", omit)
    assert report(execute(leaves))["status"] == "FAILED"
    assert not (leaves[1]/"preparation.json").exists()


@pytest.mark.parametrize("mutate", [
    lambda result: result["frames"][0]["states"][0].update(state="unknown_input", score="0"),
    lambda result: result["frames"][0]["states"][0].update(score="NaN"),
    lambda result: result["frames"][0]["states"][0].update(security_id="SHARADAR:99"),
    lambda result: result["frames"][0].update(cutoff_utc="2021-01-04T14:20:00Z"),
    lambda result: result["source_census"].update(licensed_ticker="SYNABC"),
    lambda result: result["identities"][0].update(eligible=True, ticker=None),
    lambda result: result["normalization"][0]["refusal_counts"].update({"SYNABC": 1}),
])
def test_scorer_unknown_zero_or_malformed_complete_state_cannot_be_prepared(leaves, monkeypatch, mutate):
    original = p._BUILD_FRAMES
    def corrupt(*args, **kwargs):
        result = original(*args, **kwargs)
        mutate(result)
        return result
    monkeypatch.setattr(p, "_BUILD_FRAMES", corrupt)
    result = execute(leaves)
    assert report(result)["status"] == "FAILED"
    assert not (leaves[1]/"preparation.json").exists()
    assert b"SYNABC" not in result.payload


def test_same_sid_alias_stays_one_explicit_ineligible_state_not_chosen_ticker(monkeypatch):
    rows = [revision(("2020-12-01", "2020-12-31")),
            revision(("2020-12-01", "2020-12-31"), benzinga_id="OTHER", ticker="SYNDEF")]
    identities = [{"ticker": ticker, "permaticker": "1", "figi": "BBGABCDEF123",
        "category": "Domestic Common Stock", "exchange": "NASDAQ", "isdelisted": "N"}
        for ticker in ("SYNABC", "SYNDEF")]
    result = p._BUILD_FRAMES(rows, identities, [], calendar_payload=CALENDAR, capture_utc=NOW.isoformat())
    assert result["identities"] == [{"security_id": "SHARADAR:1", "ticker": None, "eligible": False,
                                      "reason": "ambiguous_snapshot_identity"}]
    assert result["source_census"]["native_identity_rows"] == 2
    assert result["source_census"]["ambiguous_alias_identity_count"] == 1
    payloads = p._packet_payloads(result, json.loads(CALENDAR), NOW.isoformat(), lambda: None)
    assert len(payloads) == 71
    for _kind, _hash, wire, _days in payloads[1:]:
        assert all(frame["states"] == [{"security_id": "SHARADAR:1", "state": "identity_ineligible", "score": None,
            "reasons": ["ambiguous_snapshot_identity"]}] for frame in json.loads(wire)["frames"])


def test_source_blank_optional_identity_is_ineligible_not_silently_none():
    native = [{"ticker": "SYNABC", "permaticker": "1", "figi": "", "category": "Domestic Common Stock",
               "exchange": "NASDAQ", "isdelisted": "N"}]
    result = p._BUILD_FRAMES([revision(("2020-12-01", "2020-12-31"))], native, [],
        calendar_payload=CALENDAR, capture_utc=NOW.isoformat())
    assert result["identities"][0]["eligible"] is False
    assert result["identities"][0]["reason"] == "invalid_snapshot_identity"
    assert all(frame["states"][0]["state"] == "identity_ineligible" and frame["states"][0]["score"] is None
               for frame in result["frames"])


def test_fixture_cannot_point_to_actual_leaf(leaves):
    selected = plan(leaves[0])
    with pytest.raises(p.PreparationError):
        p._execute_fixture_preparation(selected, p.capture.PRIVATE_ROOT, leaves[1],
            repair_root=leaves[0].parent/"synthetic_repair", calendar_payload=CALENDAR, now=NOW)
    with pytest.raises(p.PreparationError):
        p._execute_fixture_preparation(selected, leaves[0], p.PRIVATE_ROOT,
            repair_root=leaves[0].parent/"synthetic_repair", calendar_payload=CALENDAR, now=NOW)


def test_driver_uncommitted_source_refusal_precedes_private_preparation(monkeypatch):
    monkeypatch.setattr(driver, "_verify_imports", lambda: None)
    monkeypatch.setattr(driver, "_git_head", lambda: PIN)
    monkeypatch.setattr(p.capture, "_read_source", lambda _: b"not-the-committed-source")
    monkeypatch.setattr(driver.subprocess, "run", lambda *_a, **_k: SimpleNamespace(stdout=b"committed-source"))
    monkeypatch.setattr(driver, "_create_private_directory", lambda: pytest.fail("private leaf prepared before source custody"))
    with pytest.raises(driver.DriverError):
        driver.run_preparation(owner_instruction_sha256=OWNER, created_utc=CREATED, expires_utc=EXPIRES,
            capture_index_sha256="a"*64, capture_plan_sha256="a"*64, capture_report_sha256="a"*64, capture_git_sha=PIN,
            repair_index_sha256="a"*64, repair_plan_sha256="a"*64, repair_report_sha256="a"*64, repair_git_sha=PIN)


def test_driver_custody_then_leaf_then_actual_invocation_order(leaves, monkeypatch):
    selected = plan(leaves[0], mode="production")
    calls = []
    monkeypatch.setattr(driver, "_verify_imports", lambda: calls.append("imports"))
    monkeypatch.setattr(driver, "_git_head", lambda: PIN)
    monkeypatch.setattr(driver, "_bound_inventory", lambda _: inventory())
    monkeypatch.setattr(driver, "_now", lambda: NOW)
    monkeypatch.setattr(p, "_verify_execution_identity", lambda _: calls.append("committed"))
    monkeypatch.setattr(driver, "_create_private_directory", lambda: ORIGINAL_OPEN(leaves[1]))
    def invoke(given):
        calls.append("invoke")
        assert (leaves[1] / (p.OPERATION_ID + ".driver-plan.json")).is_file()
        assert given.body() == selected.body()
        return p.PreparationResult(p._canonical(p._report("FAILED")), p._sha(p._canonical(p._report("FAILED"))))
    monkeypatch.setattr(p, "execute_preparation", invoke)
    arguments = {key: selected.body()[key] for key in ("owner_instruction_sha256", "created_utc", "expires_utc",
        "capture_index_sha256", "capture_plan_sha256", "capture_report_sha256", "capture_git_sha",
        "repair_index_sha256", "repair_plan_sha256", "repair_report_sha256", "repair_git_sha")}
    assert driver.run_preparation(**arguments)["status"] == "FAILED"
    assert calls == ["imports", "committed", "invoke"]


@pytest.mark.parametrize("mutate", [lambda body: body.update(identity_count=True),
    lambda body: body.update(outcome_reads=1), lambda body: body.update(source_input_prepared=True),
    lambda body: body.update(preparation_sha256="0"*64), lambda body: body.update(point_in_time_data=True),
    lambda body: body.update(extra="hidden-row")])
def test_driver_result_closed_coherence_refuses(mutate):
    body = p._report("FAILED")
    mutate(body)
    encoded = p._canonical(body)
    with pytest.raises((ValueError, KeyError)):
        driver._safe_result(p.PreparationResult(encoded, p._sha(encoded)))


def test_driver_cli_unknown_failure_never_leaks_exception(capsys, monkeypatch):
    def fail(**_kwargs):
        raise ValueError("SYNABC LICENSED secret source row")
    monkeypatch.setattr(driver, "run_preparation", fail)
    arguments = []
    for name, value in (("owner-instruction-sha256", OWNER), ("created-utc", CREATED), ("expires-utc", EXPIRES),
        ("capture-index-sha256", "a"*64), ("capture-plan-sha256", "a"*64), ("capture-report-sha256", "a"*64),
        ("capture-git-sha", PIN), ("repair-index-sha256", "a"*64), ("repair-plan-sha256", "a"*64),
        ("repair-report-sha256", "a"*64), ("repair-git-sha", PIN)):
        arguments += ["--"+name, value]
    assert driver.main(arguments) == 1
    printed = capsys.readouterr().out
    assert "SYNABC" not in printed and "LICENSED" not in printed and "secret" not in printed
    body = json.loads(printed)
    assert body["status"] == "REFUSED_OR_FAILED_UNKNOWN" and body["scope_spent"] is None


def rebind_repair(source, mutate):
    repaired = source.parent / "synthetic_repair"
    selected = update_json(repaired / p.repair.INDEX_NAME, mutate)
    digest = p._sha((repaired / p.repair.INDEX_NAME).read_bytes())
    update_json(repaired / (p.repair.OPERATION_ID + ".terminal.json"), lambda body: body.update(index_sha256=digest))
    return selected


def test_composite_plan_has_two_fixed_source_operations_and_production_original_pin(leaves):
    selected = plan(leaves[0]).body()
    assert selected["schema"] == "tpr-ext26-preparation-plan-v2"
    assert selected["capture_status"] == "FAILED" and selected["capture_failure"] == "refused_or_bound_hit_no_retry"
    assert selected["capture_private_root"] == str(p.capture.PRIVATE_ROOT)
    assert selected["repair_private_root"] == str(p.repair.PRIVATE_ROOT)
    assert selected["repair_operation_id"] == p.repair.OPERATION_ID
    assert selected["repair_freeze_sha256"] == p.repair.FREEZE_SHA256
    assert p.repair.SOURCE_RELATIVE in selected["source_hashes"] and p.repair.DRIVER_RELATIVE in selected["source_hashes"]
    assert plan(leaves[0], mode="production").body()["capture_index_sha256"] == p.ORIGINAL_CAPTURE["index_sha256"]
    with pytest.raises(p.PreparationError):
        plan(leaves[0], mode="production", capture_index_sha256="a" * 64)


@pytest.mark.parametrize("key,value", [("repair_operation_id", "old-repair"), ("repair_private_root", "/tmp/other"),
    ("repair_freeze_sha256", "0"*64), ("capture_status", "COMPLETED"), ("capture_failure", None),
    ("source_composition", "pretend-single-completed-capture")])
def test_composite_widened_or_false_complete_plan_refuses(leaves, key, value):
    body = plan(leaves[0]).body()
    body[key] = value
    payload = p._canonical(body)
    with pytest.raises(p.PreparationError):
        p.PreparationPlan(payload, p._sha(payload)).body()


def test_failed_original_sharadar_wire_is_never_read_and_missing_audit_wire_does_not_become_input(leaves, monkeypatch):
    index = json.loads((leaves[0] / p.capture.INDEX_NAME).read_bytes())
    ignored = index["pages"][-1]["wire_file"]
    (leaves[0] / ignored).unlink()  # Synthetic audit-only wire, not a required admitted input.
    def read(directory, name, *args, **kwargs):
        assert name != ignored
        return ORIGINAL_READ(directory, name, *args, **kwargs)
    monkeypatch.setattr(p, "_read_private", read)
    assert report(execute(leaves))["status"] == "COMPLETED"


@pytest.mark.parametrize("mutation", [lambda index: index.update(failure="unknown"),
    lambda index: index["pages"][-1].update(projection_file="fake-projection.json"),
    lambda index: index["census"][74].update(terminated=True),
    lambda index: index["pages"].append(index["pages"][-1])])
def test_original_failed_tail_cannot_silently_become_admitted_or_extended(leaves, mutation):
    rebind_index(leaves[0], mutation)
    result = report(execute(leaves))
    assert result["status"] == "FAILED" and result["source_refusal_census"]["massive"] is None


@pytest.mark.parametrize("mutation", [lambda index: index.update(original_capture_modified=True),
    lambda index: index.update(ticker_python_collation_asserted=True),
    lambda index: index.update(freeze_sha256="0"*64),
    lambda index: index["report"].update(status="FAILED"),
    lambda index: index["census"][1].update(terminated=False),
    lambda index: index["pages"][0].update(window=None),
    lambda index: index["pages"][0].update(wire_file="../other"),
    lambda index: index["pages"][0].update(response_complete=False),
    lambda index: index["pages"].pop()])
def test_repair_incomplete_or_tampered_source_is_spent_failure_not_zero(leaves, mutation):
    rebind_repair(leaves[0], mutation)
    result = report(execute(leaves))
    assert result["status"] == "FAILED" and result["source_refusal_census"]["massive"] is not None
    assert result["source_refusal_census"]["sharadar"] is None
    assert not (leaves[1] / "preparation.json").exists()


@pytest.mark.parametrize("basename", ["request.0001.spent.json", "request.0001.terminal.json"])
def test_repair_request_claim_and_terminal_bind_exact_new_operation(leaves, basename):
    repaired = leaves[0].parent / "synthetic_repair"
    update_json(repaired / basename, lambda body: body.update(operation_id="old-capture") if "spent" in basename
                else body.update(disposition="projected"))
    assert report(execute(leaves))["status"] == "FAILED"


def test_composite_joint_budget_not_two_independent_renewed_allowances(leaves, monkeypatch):
    source = json.loads((leaves[0] / p.capture.INDEX_NAME).read_bytes())
    massive_bytes = source["report"]["response_bytes"] - source["pages"][-1]["wire_bytes"]
    monkeypatch.setitem(p.LIMITS, "max_wire_bytes", massive_bytes + 1)
    result = report(execute(leaves))
    assert result["status"] == "FAILED" and result["source_input_prepared"] is False


def test_repair_provider_ticker_order_descents_are_retained_with_cross_page_census(leaves, tmp_path):
    root = tmp_path / "other_synthetic_repair"
    root.mkdir(mode=0o700)
    def pages(provider, dataset, query, credential, seconds):
        if dataset == "actions": return transport(provider, dataset, query, credential, seconds)
        header = "ticker,permaticker,category,exchange,isdelisted\n"
        if dict(query)["skip"] == "0":
            rows = [f"B{number:05},{number+1},Domestic Common Stock,NASDAQ,N\n" for number in range(10000)]
        else:
            rows = ["AAB,10001,Domestic Common Stock,NASDAQ,N\n", "AAA,10002,Domestic Common Stock,NASDAQ,N\n"]
        return response((header + "".join(rows)).encode(), "text/csv")
    selected = p.repair.freeze_repair_plan(source_hashes={key: inventory()[key] for key in p.repair.SOURCE_PATHS},
        git_sha=PIN, owner_instruction_sha256=OWNER, created_utc=CREATED, expires_utc=EXPIRES, mode="offline-fixture")
    outcome = p.repair._execute_fixture_repair(selected, root, now=NOW,
        credential_resolver=lambda _: "SYNTHETIC_TOKEN_abcdef", transport=pages)
    assert report(outcome)["status"] == "COMPLETED"
    selected = plan(leaves[0], repair_index_sha256=p._sha((root/p.repair.INDEX_NAME).read_bytes()),
        repair_plan_sha256=p._sha((root/(p.repair.OPERATION_ID+".plan.json")).read_bytes()),
        repair_report_sha256=p._sha((root/(p.repair.OPERATION_ID+".aggregate.json")).read_bytes()))
    directory = ORIGINAL_OPEN(root)
    try:
        index, rows, counts, semantic = p._replay_capture(directory, selected.body(), lambda: None, repaired=True)
        assert len(rows["tickers"]) == 10002 and rows["tickers"][-1]["ticker"] == "AAA"
        assert counts["ticker_python_lexical_descents"] == index["report"]["ticker_python_lexical_descents"] == 2
        assert counts["row_refusals"] == 0 and not any(semantic.values())
    finally:
        os.close(directory)


def test_refusal_census_is_durable_before_scorer_failure_and_unknown_not_zero(leaves, monkeypatch):
    def refuse(*_args, **_kwargs):
        census_file = leaves[1] / (p.OPERATION_ID + ".source-refusal-census.json")
        assert census_file.is_file()
        census = json.loads(census_file.read_bytes())
        assert census["capture_index_sha256"] == plan(leaves[0]).body()["capture_index_sha256"]
        assert census["repair_index_sha256"] == plan(leaves[0]).body()["repair_index_sha256"]
        assert set(census["source_refusal_census"]) == {"massive", "sharadar"}
        raise p.scorer.SignalError("closed synthetic refusal")
    monkeypatch.setattr(p, "_BUILD_FRAMES", refuse)
    result = report(execute(leaves))
    assert result["status"] == "FAILED" and all(value is not None for value in result["source_refusal_census"].values())
    assert all(set(value) == p.SEMANTIC_KEYS for value in result["source_refusal_census"].values())
    initial = p._report("FAILED")
    assert initial["source_refusal_census"] == {"massive": None, "sharadar": None}


@pytest.mark.parametrize("mutate", [lambda body: body.update(source_refusal_census={"massive": None}),
    lambda body: body["source_refusal_census"].update(massive={"SECRET": 1}),
    lambda body: body["source_refusal_census"].update(massive={key: True for key in p.SEMANTIC_KEYS})])
def test_refusal_public_census_is_closed_counts_not_strings_rows_or_unknown_as_zero(mutate):
    body = p._report("FAILED")
    mutate(body)
    raw = p._canonical(body)
    with pytest.raises(driver.DriverError):
        driver._safe_result(p.PreparationResult(raw, p._sha(raw)))


@pytest.mark.parametrize("changes,reason,fatal", [({"benzinga_id": None}, "invalid_event_id", True),
    ({"benzinga_firm_id": None}, "invalid_firm_id", False),
    ({"ticker": "bad"}, "invalid_native_ticker", False),
    ({"last_updated": None}, "invalid_native_touch_clock", False)])
def test_retained_native_semantic_refusals_not_dropped_or_zeroed(leaves, tmp_path, changes, reason, fatal):
    source = tmp_path / "semantic_capture"
    source.mkdir(mode=0o700)
    def selected_transport(provider, dataset, query, credential, seconds):
        if provider == "massive":
            values = dict(query)
            window = values["date.gte"], values["date.lte"]
            row = revision(window, **(changes if window[0] == "2020-12-01" else {}))
            return response(p._canonical({"status": "OK", "results": [row]}), "application/json")
        return response(b"ticker,permaticker,category,exchange,isdelisted\nZZZ,2,Domestic Common Stock,NASDAQ,N\nAAA,1,Domestic Common Stock,NASDAQ,N\n", "text/csv")
    result = p.capture._execute_fixture_capture(capture_plan(), source, now=NOW,
        credential_resolver=lambda _: "SYNTHETIC_TOKEN_abcdef", transport=selected_transport)
    assert report(result)["status"] == "FAILED"
    output = leaves[1]
    result = report(execute((source, output)))
    assert result["status"] == ("FAILED" if fatal else "COMPLETED")
    assert result["source_refusal_census"]["massive"][reason] == 1
    census = json.loads((output / (p.OPERATION_ID + ".source-refusal-census.json")).read_bytes())
    assert census["source_refusal_census"] == result["source_refusal_census"]
    if not fatal:
        receipt = json.loads((output / "preparation.json").read_bytes())
        assert receipt["capture_replayed_counts"]["source_rows"] == 74
        assert receipt["signal_source_census"]["ratings"] == 74
        assert sum(receipt["normalization_refusal_occurrences_across_decisions"].values()) > 0
        assert receipt["replayed_counts"]["row_refusals"] == 1
    else:
        assert not (output / "preparation.json").exists()  # Native global-ID policy unchanged.
