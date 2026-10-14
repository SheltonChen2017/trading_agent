"""Fresh synthetic OFF list only; no account/credential/private/operator effects."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_owner_mia_discovery_successor as m
from tests.target_price_revisions_qc import test_qc_extended_owner_mia_discovery as previous

e = m.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name:(ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
NOW = datetime(2026,10,13,23,tzinfo=timezone.utc)
row, transport = previous.row, previous.transport


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kwargs): raise AssertionError("actual credential/network/private/subprocess forbidden")
    monkeypatch.setattr(m.ops,"credential",deny)
    monkeypatch.setattr(m.http.client,"HTTPSConnection",deny)
    monkeypatch.setattr(m.subprocess,"run",deny)
    original = m.files._directory
    def directory(path, *, private):
        if private and (path == m.PRIVATE_ROOT or path.is_relative_to(m.LANE)): deny()
        return original(path,private=private)
    monkeypatch.setattr(m.files,"_directory",directory)


def fixture(tmp_path):
    root = tmp_path / "synthetic-fresh-off-list"; root.mkdir(mode=0o700)
    plan = m._plan(operation_id="TPR-EXT26-OWNER-MIA-DISCOVERY-SUCCESSOR-SYNTHETIC-001",git_head="a"*40,
        source_hashes={name:m._sha(raw) for name,raw in SOURCES.items()},owner_instruction_sha256="b"*64,
        created_utc=(NOW-timedelta(seconds=1)).isoformat(),expires_utc=(NOW+timedelta(minutes=10)).isoformat(),mode="offline-fixture")
    return plan,dict(SOURCES),root


def execute(values, reading=None, **kwargs):
    plan,sources,root = values
    return e.parse_json(m.execute_fixture(plan,sources,root,clock=kwargs.pop("clock",lambda:NOW),
        transport=transport()[0] if reading is None else reading,**kwargs))


def test_pinned_original_and_all14_public_jobs_preserve_looks30_not_launch_allowance():
    known = m._frozen(SOURCES); ledger = e.parse_json(SOURCES[m.LEDGER])
    assert known == frozenset(ledger["known_historical_jobs"]) | frozenset(item["backtest_id"] for item in ledger["jobs"])
    assert len(known) == 14 and m._sha(SOURCES[m.original.MODULE]) == m.ORIGINAL_SHA256
    assert m._sha(SOURCES[m.LEDGER]) == m.LEDGER_SHA256
    assert len(m.SOURCE_PATHS) == len(set(m.SOURCE_PATHS))


def test_naive_server_times_are_retained_sorted_relatively_without_utc_invention(tmp_path):
    public = "7dacf829bda2cf1bbe6d75cac5ab5ca3"
    jobs = [row("synthetic-success","2026-10-13T21:20:00"),row(public,"2026-10-13T21:00:00","Runtime Error"),
        row("synthetic-failure","2026-10-13T21:10:00","Runtime Error")]
    with pytest.raises(ValueError): m.original._metadata(e.parse_json(e.canonical({"success":True,"count":3,"backtests":jobs})),m.original.PRIOR_JOBS)
    values = fixture(tmp_path); read,calls = transport(jobs); result = execute(values,read)
    assert result["status"] == "COMPLETED_METADATA" and len(calls) == 1
    assert [item["backtest_id"] for item in result["jobs"]] == [public,"synthetic-failure","synthetic-success"]
    assert [item["relative_creation_rank_in_clock_group"].fraction() for item in result["jobs"]] == [1,2,3]
    assert all(item["created_clock_basis"] == "server_unzoned" and item["created_is_timezone_aware"] is False
        and item["created_timezone_assumption"] is None and not item["created"].endswith("Z") for item in result["jobs"])
    assert result["creation_clock_groups_observed"] == ["server_unzoned"]
    assert result["cross_clock_group_chronology_proven"] is False and result["created_timezone_assumption"] is None
    assert result["known_job_ids"] == sorted(m._frozen(SOURCES)) and result["previously_recorded_looks"].fraction() == 30
    assert result["unknown_job_ids"] == ["synthetic-failure","synthetic-success"]
    assert result["newly_discovered_jobs_require_separate_attribution_and_retained_look_accounting"] is True
    assert result["codex_off_attempts_consumed"].fraction() == 3 and result["new_codex_attempts"].fraction() == 0
    assert result["look_registry_updates_performed"].fraction() == result["new_jobs_launched"].fraction() == 0
    assert result["attempt_reset"] is False and result["winner_selected"] is False and result["accepted_metrics"] is None
    assert "SYNTHETIC PRIVATE JOB NAME" not in e.canonical(result).decode()
    with pytest.raises(FileExistsError): execute(values,read)
    assert len(calls) == 1 and not (values[2]/"controller.lock").exists()


def test_offset_chronology_and_mixed_groups_never_assign_naive_utc(tmp_path):
    jobs = [row("synthetic-zoned-b","2026-10-13T22:00:00+01:00","Runtime Error"),
        row("synthetic-naive-early","2020-01-01T09:00:00"),row("synthetic-zoned-a","2026-10-13T21:00:00Z")]
    result = execute(fixture(tmp_path),transport(jobs)[0])
    assert [item["backtest_id"] for item in result["jobs"]] == ["synthetic-zoned-a","synthetic-zoned-b","synthetic-naive-early"]
    assert result["jobs"][1]["created"] == "2026-10-13T22:00:00+01:00"
    assert result["jobs"][2]["created"] == "2020-01-01T09:00:00" and result["jobs"][2]["created_clock_basis"] == "server_unzoned"
    assert result["jobs"][2]["relative_creation_rank_in_clock_group"].fraction() == 1
    assert result["creation_clock_groups_observed"] == ["explicit_offset","server_unzoned"]
    assert result["cross_clock_group_chronology_proven"] is False


@pytest.mark.parametrize("suffix", ["", "Z", "+01:00"])
def test_fractional_server_precision_is_preserved_for_relative_order(tmp_path,suffix):
    jobs = [row("synthetic-a-later","2026-10-13T21:00:00.123456789"+suffix),
        row("synthetic-z-earlier","2026-10-13T21:00:00.123456788"+suffix)]
    result = execute(fixture(tmp_path),transport(jobs)[0])
    assert [item["backtest_id"] for item in result["jobs"]] == ["synthetic-z-earlier","synthetic-a-later"]
    assert result["jobs"][0]["created"].endswith("123456788"+suffix)


def test_all14_known_ids_and_failure_statuses_are_retained_without_winner_picking(tmp_path):
    jobs = [row(identity,"2026-10-13 21:00:00","Runtime Error") for identity in sorted(m._frozen(SOURCES))]
    result = execute(fixture(tmp_path),transport(jobs)[0])
    assert len(result["jobs"]) == 14 and result["unknown_job_ids"] == []
    assert all(item["known_historical_job"] is True and item["status"] == "Runtime Error"
        and item["owner_reported_mia_attribution_verified"] is False for item in result["jobs"])
    assert result["compiled_source_proven"] is False and result["economics_accepted"] is False


def test_exact_tokens_and_contextual_scrub_never_retain_outcome_source_error_or_profile_bodies(tmp_path):
    def alter(body):
        body["backtests"][0].update(progress=e.JsonNumber("1.000000000000000000000"),userId=12345,
            profile={"id":12345,"email":"synthetic@example.invalid"},name="SYNTHETIC NAME",
            statistics={"Return":"SYNTHETIC PERFORMANCE"},parameters={"private":"SYNTHETIC PARAMETER"},
            source="SYNTHETIC SOURCE",error="SYNTHETIC ERROR")
        body.update(statistics={"private":"SYNTHETIC TOP OUTCOME"},errors=["SYNTHETIC ERROR BODY"])
    values = fixture(tmp_path); result = execute(values,transport(fault=alter)[0])
    assert result["status"] == "COMPLETED_METADATA" and result["jobs"][0]["progress"].lexeme == "1.000000000000000000000"
    assert result["unexpected_outcome_or_parameter_fields_present"] is True
    raw = (values[2]/(values[0]["operation_id"]+".read001.projection.json")).read_bytes()
    for marker in (b"12345",b"synthetic@example.invalid",b"SYNTHETIC NAME",b"SYNTHETIC PERFORMANCE",b"SYNTHETIC PARAMETER",
        b"SYNTHETIC SOURCE",b"SYNTHETIC ERROR",b"SYNTHETIC TOP OUTCOME"):
        assert marker not in raw and marker not in e.canonical(result)
    projected = e.parse_json(raw)
    assert projected["raw_wire_retained"] is False and projected["outcome_parameter_source_fields_retained"] is False


@pytest.mark.parametrize("count",[0,128])
def test_exact_closed_row_boundaries_accept_all_observations(tmp_path,count):
    result = execute(fixture(tmp_path),transport([row("synthetic-job-"+str(index)) for index in range(count)])[0])
    assert result["status"] == "COMPLETED_METADATA" and len(result["jobs"]) == count


@pytest.mark.parametrize("fault",["rows","count","duplicate","project","row_project","id","created","date_only","invalid_created",
    "long_created","bool_progress","progress","snapshot","status","name","success"])
def test_invalid_identity_metadata_never_succeeds_or_retries(tmp_path,fault):
    def alter(body):
        item = body["backtests"][0]
        if fault == "rows": body.update(count=129,backtests=[row("synthetic-job-"+str(index)) for index in range(129)])
        if fault == "count": body["count"] = 2
        if fault == "duplicate": body.update(count=2,backtests=[item,deepcopy(item)])
        if fault == "project": body["projectId"] = 999
        if fault == "row_project": item["projectId"] = 999
        if fault == "id": item.pop("backtestId")
        if fault == "created": item.pop("created")
        if fault == "date_only": item["created"] = "2026-10-13"
        if fault == "invalid_created": item["created"] = "2026-99-99T21:00:00"
        if fault == "long_created": item["created"] = "x"*65
        if fault == "bool_progress": item["progress"] = True
        if fault == "progress": item["progress"] = e.JsonNumber("1.0001")
        if fault == "snapshot": item["snapshotId"] = -1
        if fault == "status": item["status"] = "x"*81
        if fault == "name": item["name"] = "x"*1025
        if fault == "success": body["success"] = False
    values = fixture(tmp_path); read,calls = transport(fault=alter); result = execute(values,read)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["jobs"] is None and len(calls) == 1
    assert result["accepted_metrics"] is None and (values[2]/(values[0]["operation_id"]+".result.json")).exists()


def test_absent_provider_project_fields_remain_fixed_request_scope_not_attestation(tmp_path):
    def alter(body):
        body.pop("projectId")
        for item in body["backtests"]: item.pop("projectId")
    result = execute(fixture(tmp_path),transport(fault=alter)[0])
    assert result["observed_returned_project_fields"].fraction() == 0 and result["request_bound_to_fixed_project"] is True
    assert result["provider_authenticity_attested"] is False


@pytest.mark.parametrize("suffix", ["Z", "+00:00", "-00:00"])
def test_known_utc_zero_offset_encodings_preserve_text_without_local_zone_claim(tmp_path,suffix):
    # RFC3339/9557: UTC time is known even when the local offset is unknown.
    # Neither this metadata parser nor this assertion attests a local zone.
    created = "2026-10-13T21:00:00" + suffix
    result = execute(fixture(tmp_path),transport([row("synthetic-zero-offset",created)])[0])
    assert result["status"] == "COMPLETED_METADATA"
    item = result["jobs"][0]
    assert item["created"] == created and item["created_is_timezone_aware"] is True
    assert item["created_timezone_assumption"] is None
    assert result["cross_clock_group_chronology_proven"] is False


@pytest.mark.parametrize("fault",["timeout","http","oversize","malformed","echo","escaped_echo","elapsed"])
def test_unsuccessful_response_retains_spent_failure_and_body_free_uncertainty(tmp_path,fault):
    values = fixture(tmp_path); read,calls = transport(status=503 if fault=="http" else 200); elapsed = [0.0]
    def reading(*args):
        if fault == "timeout": calls.append(True); raise TimeoutError("SYNTHETIC PRIVATE FAILURE")
        raw,status,token = read(*args)
        if fault == "oversize": raw = b"x"*(m.MAX_RESPONSE+1)
        if fault == "malformed": raw = b"{"
        if fault == "echo": raw = raw.replace(b'"errors":[]',b'"errors":["SYNTHETIC-TOKEN"]')
        if fault == "escaped_echo": raw = raw.replace(b'"errors":[]',b'"errors":["SYNTHETIC-\\u0054OKEN"]')
        if fault == "elapsed": elapsed[0] = 30.0
        return raw,status,token
    result = execute(values,reading,monotonic=lambda:elapsed[0])
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["failed_response_bytes_unknown"] is (fault=="timeout")
    if fault in {"echo","escaped_echo","malformed","oversize","elapsed"}: assert result["request"]["wire_sha256"] is None
    assert "SYNTHETIC-TOKEN" not in e.canonical(result).decode() and "SYNTHETIC PRIVATE FAILURE" not in e.canonical(result).decode()
    with pytest.raises(FileExistsError): execute(values,reading)
    assert len(calls) == 1


def test_exclusive_claim_access_request_and_controller_precede_transport(tmp_path):
    values = fixture(tmp_path); read,calls = transport()
    def reading(*args):
        root,operation = values[2],values[0]["operation_id"]
        for suffix in (".claim.spent.json",".access.json",".read001.request.spent.json"):
            target = root/(operation+suffix)
            assert target.read_bytes() and target.stat().st_mode&0o777 == 0o600
        assert (root/"controller.lock").exists()
        return read(*args)
    assert execute(values,reading)["status"] == "COMPLETED_METADATA" and len(calls) == 1


def test_existing_controller_is_preserved_without_network_and_scope_is_spent(tmp_path):
    values = fixture(tmp_path); fd = os.open(values[2]/"controller.lock",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try: os.write(fd,b"synthetic other owner")
    finally: os.close(fd)
    read,calls = transport(); result = execute(values,read)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and not calls
    assert (values[2]/"controller.lock").read_bytes() == b"synthetic other owner"
    assert (values[2]/(values[0]["operation_id"]+".claim.spent.json")).exists()


@pytest.mark.parametrize("fault",["expired","clock_naive","clock_offset","source","original","ledger","look","extra","payload","duration"])
def test_fresh_frozen_source_head_time_scope_refusals_precede_claims(tmp_path,fault):
    values = fixture(tmp_path); read,calls = transport(); clock = lambda:NOW
    if fault == "expired": clock = lambda:NOW+timedelta(hours=1)
    if fault == "clock_naive": clock = lambda:NOW.replace(tzinfo=None)
    if fault == "clock_offset": clock = lambda:NOW.astimezone(timezone(timedelta(hours=5)))
    paths = {"source":m.MODULE,"original":m.original.MODULE,"ledger":m.LEDGER,"look":m.original.LOOK}
    if fault in paths: values[1][paths[fault]] += b" "
    if fault == "extra": values[0]["launch_authorized"] = True
    if fault == "payload": values[0]["payload"]["includeStatistics"] = True
    if fault == "duration": values[0]["expires_utc"] = (NOW+timedelta(hours=1)).isoformat()
    with pytest.raises((ValueError,KeyError)): execute(values,read,clock=clock)
    assert not calls and not (values[2]/(values[0]["operation_id"]+".claim.spent.json")).exists()


@pytest.mark.parametrize("fault",["root","guard","clock","monotonic","transport"])
def test_production_refuses_all_injected_seams_before_private_open(tmp_path,monkeypatch,fault):
    old,sources,root = fixture(tmp_path); args = {name:old[name] for name in m.ARGS}; args["mode"] = "production"
    plan = m._plan(**args)
    # Keep the clock valid so an injected guard cannot hide behind expiry.
    monkeypatch.setattr(m, "_production_clock", lambda: NOW)
    kwargs = {"guard":m._guard,"clock":m._production_clock,"monotonic":m.time.monotonic,"transport":m._native_request}
    if fault != "root": root = m.PRIVATE_ROOT
    if fault in kwargs: kwargs[fault] = lambda *_:None
    with pytest.raises(ValueError): m._execute(plan,sources,root,**kwargs)


@pytest.mark.parametrize("root",[m.PRIVATE_ROOT,m.LANE/"never-created-fixture"])
def test_fixture_refuses_actual_private_and_lane_roots(tmp_path,root):
    plan,sources,_ = fixture(tmp_path); read,calls = transport()
    with pytest.raises(ValueError): m.execute_fixture(plan,sources,root,clock=lambda:NOW,transport=read)
    assert not calls


def test_native_signer_missing_exact_claim_refuses_before_credentials(tmp_path):
    old,_,_ = fixture(tmp_path); args = {name:old[name] for name in m.ARGS}; args["mode"] = "production"
    with pytest.raises(ValueError): m._native_request(m._plan(**args),30,None)


def test_final_check_after_metadata_remains_load_bearing(tmp_path,monkeypatch):
    values = fixture(tmp_path); read,calls = transport(); original = m._metadata; reached = []
    def parsed(*args):
        result = original(*args); reached.append(True); return result
    monkeypatch.setattr(m,"_metadata",parsed)
    def refuse(_):
        if reached: raise ValueError("synthetic final refusal")
    result = execute(values,read,guard=refuse)
    assert reached == [True] and len(calls) == 1 and result["jobs"] is not None
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["request"]["status"] == "failed_or_unknown"


def test_cli_wrong_hash_and_old_operation_never_execute(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(m,"execute_plan",lambda *_:pytest.fail("bad hash cannot execute"))
    assert m.main(["--plan-json","{}","--plan-sha256","a"*64]) == 1
    assert e.parse_json(capsys.readouterr().out.encode())["raw_text_returned"] is False
    plan = fixture(tmp_path)[0]; args = {name:plan[name] for name in m.ARGS}
    args["operation_id"] = "TPR-EXT26-OWNER-MIA-DISCOVERY-20261013-001"
    with pytest.raises(ValueError): m._plan(**args)
