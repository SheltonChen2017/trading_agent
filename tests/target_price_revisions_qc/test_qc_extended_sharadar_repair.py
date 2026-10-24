"""Synthetic-only Sharadar repair tests with an always-on real-I/O firewall."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from research.target_price_revisions_qc import extended_sharadar_repair as r
from research.target_price_revisions_qc import extended_sharadar_repair_driver as driver

ACTUAL_LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
ORIGINAL_OPEN, ORIGINAL_RESOLVER, ORIGINAL_TRANSPORT = r.capture._open_directory, r._FIXED_RESOLVER, r._FIXED_TRANSPORT
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
CREATED, EXPIRES = "2026-10-10T00:00:00+00:00", "2026-10-11T00:00:00+00:00"
PIN, OWNER, TOKEN = "c" * 40, "b" * 64, "SYNTHETIC_SHARADAR_SECRET_abcdef"


@pytest.fixture(autouse=True)
def real_io_firewall(monkeypatch):
    def guarded_open(path):
        selected = Path(path)
        if selected == ACTUAL_LANE_ROOT or selected.is_relative_to(ACTUAL_LANE_ROOT):
            pytest.fail("actual lane/old/private leaves forbidden in repair fixtures")
        return ORIGINAL_OPEN(selected)
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credentials, provider or subprocess forbidden in repair fixtures")
    monkeypatch.setattr(r.capture, "_open_directory", guarded_open)
    monkeypatch.setattr(r.capture.probe, "_open_directory", guarded_open)
    monkeypatch.setattr(r.capture.helper, "_production_credential", forbidden)
    monkeypatch.setattr(r.capture, "_https_get", forbidden)
    monkeypatch.setattr(r.capture.probe, "_https_get", forbidden)
    monkeypatch.setattr(r.capture.http.client, "HTTPSConnection", forbidden)
    monkeypatch.setattr(r.subprocess, "run", forbidden)
    return guarded_open, forbidden


def inventory():
    return {key: r.PUBLIC_HASHES.get(key, "a"*64) for key in r.SOURCE_PATHS}


def plan(**changes):
    args = dict(source_hashes=inventory(), git_sha=PIN, owner_instruction_sha256=OWNER,
        created_utc=CREATED, expires_utc=EXPIRES, mode="offline-fixture")
    args.update(changes)
    return r.freeze_repair_plan(**args)


@pytest.fixture
def private_root(tmp_path):
    root = tmp_path / "synthetic_sharadar_repair"
    root.mkdir(mode=0o700)
    return root


def csv_payload(dataset, rows=None, *, optional=False):
    if dataset == "tickers":
        header = "ticker,permaticker,category,exchange,isdelisted" + (",figi" if optional else "") + "\n"
        default = "ZZZ,2,Domestic Common Stock,NASDAQ,N" + (",BBGABCDEF123" if optional else "") + "\n"
        default += "AAA,1,Domestic Common Stock,NYSE,N" + (",BBGABCDEF124" if optional else "") + "\n"
    else:
        header = "ticker,date,action" + (",contraticker" if optional else "") + "\n"
        default = "AAA,1999-01-01,listed" + ("," if optional else "") + "\n"
    return (header + (default if rows is None else rows)).encode()


def response(payload, **changes):
    return replace(r.capture.CaptureResponse(200, (("content-type", "text/csv"),
        ("content-length", str(len(payload)))), payload), **changes)


def default_transport(provider, dataset, query, credential, seconds):
    assert provider == "sharadar" and dataset in ("tickers", "actions")
    assert query == r.capture._sharadar_query(dataset, int(dict(query)["skip"])//10000)
    assert credential.startswith("SYNTHETIC_") and 0 < seconds <= 30
    return response(csv_payload(dataset))


def execute(root, *, selected=None, resolver=None, transport=None, now=NOW, monotonic=lambda: 0.0):
    return r._execute_fixture_repair(selected or plan(), root, now=now,
        credential_resolver=resolver or (lambda _provider: TOKEN), transport=transport or default_transport,
        monotonic=monotonic)


def report(result):
    return json.loads(result.payload)


def index(root):
    return json.loads((root/r.INDEX_NAME).read_bytes())


def test_plan_scope_exact_queries_and_fresh_leaf():
    body = plan().body()
    assert body["freeze_sha256"] == r.FREEZE_SHA256
    assert body["scope"]["queries"] == r.capture.CSV_QUERY
    assert body["scope"]["limits"] == r.LIMITS
    assert body["scope"]["dataset_limits"] == r.DATASET_LIMITS
    assert body["scope"]["ticker_python_collation_asserted"] is False
    assert body["scope"]["actions_iso_order_and_end_required"] is True
    assert body["private_root"].endswith("/sharadar_repair")
    assert body["old_receipts_renewed"] is body["original_capture_modified"] is False
    assert r.SOURCE_RELATIVE in body["source_hashes"] and r.DRIVER_RELATIVE in body["source_hashes"]
    assert r.FREEZE_RELATIVE in body["source_hashes"] and r.capture.SOURCE_RELATIVE in body["source_hashes"]


@pytest.mark.parametrize("changes", [{"source_hashes": {}}, {"source_hashes": {**inventory(), "extra": "a"*64}},
    {"source_hashes": {**inventory(), r.FREEZE_RELATIVE: "a"*64}}, {"git_sha": "Z"*40},
    {"owner_instruction_sha256": None}, {"mode": "fixture"}, {"created_utc": "2026-10-10T00:00:00"},
    {"expires_utc": CREATED}, {"expires_utc": "2026-10-13T00:00:00Z"}])
def test_bad_plan_refused(changes):
    with pytest.raises(ValueError): plan(**changes)


@pytest.mark.parametrize("key,value", [("private_root", "/tmp/old"), ("lane_branch", "main"),
    ("original_capture_modified", True), ("old_receipts_renewed", True), ("outcome_access", True)])
def test_rehashed_widened_plan_refused(key, value):
    body = plan().body()
    body[key] = value
    encoded = r._canonical(body)
    with pytest.raises(ValueError): r.RepairPlan(encoded, r.capture.probe._digest(encoded)).body()


def test_plan_byte_tamper_refused():
    selected = plan()
    with pytest.raises(ValueError): replace(selected, payload=selected.payload+b" ").body()


def test_ticker_native_collation_kept_without_filter_or_inferred_optional():
    body = r.csv_projection(csv_payload("tickers"), "tickers", {})
    assert body["schema"] == "tpr-ext26-sharadar-repair-page-v1"
    assert [row["source"]["ticker"] for row in body["rows"]] == ["ZZZ", "AAA"]
    assert body["ticker_python_lexical_descents"] == 1 and body["source_rows"] == 2
    assert body["missing_optional_column"] is True
    assert all(row["source"]["figi"] is None and row["refusals"] == [] for row in body["rows"])
    with pytest.raises(ValueError): r.capture._csv_projection(csv_payload("tickers"), "tickers", {})


def test_sorted_ticker_projection_preserves_original_parser_fields_exactly():
    payload = csv_payload("tickers", "AAA,1,Domestic Common Stock,NYSE,N\nZZZ,2,Domestic Common Stock,NASDAQ,N\n")
    old = r.capture._csv_projection(payload, "tickers", {})
    new = r.csv_projection(payload, "tickers", {})
    assert {key: new[key] for key in old if key != "schema"} == {key: value for key,value in old.items() if key != "schema"}
    assert new["ticker_python_lexical_descents"] == 0


def test_present_blank_optional_stays_empty_not_inferred_none():
    body = r.csv_projection(csv_payload("tickers", "AAA,1,Domestic Common Stock,NYSE,N,\n", optional=True), "tickers", {})
    assert body["missing_optional_column"] is False
    assert body["rows"][0]["source"]["figi"] == ""


def test_duplicate_conflict_and_semantic_refusal_rows_all_retained():
    payload = csv_payload("tickers", "AAA,1,Domestic Common Stock,NYSE,N\nAAA,1,Domestic Common Stock,NYSE,N\nAAA,2,Domestic Common Stock,NYSE,N\nbad,0,Other,OTHER,?\n")
    body = r.csv_projection(payload, "tickers", {})
    assert len(body["rows"]) == body["source_rows"] == 4
    assert body["identical_duplicate_rows"] == body["conflicting_duplicate_rows"] == 1
    assert "conflicting_native_identity" in body["rows"][2]["refusals"]
    assert {"invalid_native_ticker", "invalid_native_permaticker", "unknown_native_delisting"} <= set(body["rows"][3]["refusals"])
    assert body["row_refusals"] == 2


@pytest.mark.parametrize("payload", [b"ticker,ticker,permaticker,category,exchange,isdelisted\n",
    b"ticker,permaticker\nAAA,1\n", b"ticker,permaticker,category,exchange,isdelisted\nAAA,1,X,Y\n",
    b"ticker,permaticker,category,exchange,isdelisted\nAAA,1,X,Y,N\x00\n", b"\xff\n", b""])
def test_structural_csv_is_not_truncated_or_filtered(payload):
    with pytest.raises(ValueError): r.csv_projection(payload, "tickers", {})


def test_10001_rows_refused_not_truncated():
    payload = csv_payload("tickers", "AAA,1,Domestic Common Stock,NYSE,N\n" * 10001)
    with pytest.raises(ValueError): r.csv_projection(payload, "tickers", {})


@pytest.mark.parametrize("dataset", [None, "ratings", [], True])
def test_no_other_dataset_projection(dataset):
    with pytest.raises(ValueError): r.csv_projection(csv_payload("tickers"), dataset, {})


def test_actions_within_page_chronology_still_refused():
    with pytest.raises(ValueError):
        r.csv_projection(csv_payload("actions", "AAA,2021-01-02,split\nAAA,2020-01-02,split\n"), "actions", {})


def test_global_and_request_claim_precede_credentials_and_only_two_routes(private_root):
    observed = []
    def resolver(provider):
        assert provider == "sharadar"
        assert (private_root/(r.OPERATION_ID+".access.spent.json")).is_file()
        assert (private_root/"request.0001.spent.json").is_file()
        observed.append("credential")
        return TOKEN
    def transport(provider, dataset, query, credential, seconds):
        index = sum(isinstance(value,tuple) for value in observed)+1
        assert (private_root/f"request.{index:04}.spent.json").is_file()
        observed.append((provider,dataset,query))
        return default_transport(provider,dataset,query,credential,seconds)
    result = execute(private_root, resolver=resolver, transport=transport)
    body = report(result)
    assert body["status"] == "COMPLETED" and body["capture_complete"] is True
    assert body["reserved_requests"] == body["attempted_requests"] == body["successful_requests"] == 2
    assert body["terminated_sharadar_datasets"] == 2 and body["source_rows"] == 3
    assert body["ticker_python_lexical_descents"] == 1
    assert observed == ["credential", ("sharadar","tickers",r.capture._sharadar_query("tickers",0)),
                        ("sharadar","actions",r.capture._sharadar_query("actions",0))]
    retained = index(private_root)
    assert retained["schema"] == "tpr-ext26-sharadar-repair-index-v1"
    assert retained["ticker_python_collation_asserted"] is retained["original_capture_modified"] is False
    assert len(retained["census"]) == 2 and all(row["terminated"] for row in retained["census"])
    for page in retained["pages"]:
        for prefix in ("wire","projection"):
            wire=(private_root/page[prefix+"_file"]).read_bytes()
            assert r.capture.probe._digest(wire)==page[prefix+"_sha256"] and len(wire)==page[prefix+"_bytes"]
        terminal=json.loads((private_root/f"request.{page['request_index']:04}.terminal.json").read_bytes())
        assert terminal["disposition"]=="wire_accepted" and terminal["projection_file"] is None
    assert TOKEN not in result.payload.decode() and "AAA" not in result.payload.decode()
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in private_root.iterdir())
    safe=driver._safe_result(replace(result,index_path=r.PRIVATE_ROOT/r.INDEX_NAME))
    assert safe["preparation_may_exist"] is True


def test_cross_page_ticker_descent_does_not_break_complete_offset_census(private_root):
    calls=[]
    def transport(provider,dataset,query,credential,seconds):
        calls.append((dataset,dict(query)["skip"]))
        if dataset=="tickers" and dict(query)["skip"]=="0":
            rows="".join(f"Z{i:05},{i+2},Domestic Common Stock,NASDAQ,N\n" for i in range(10000))
            return response(csv_payload("tickers",rows))
        if dataset=="tickers": return response(csv_payload("tickers","AAA,1,Domestic Common Stock,NYSE,N\n"))
        return default_transport(provider,dataset,query,credential,seconds)
    result=execute(private_root,transport=transport)
    assert report(result)["status"]=="COMPLETED"
    assert report(result)["ticker_python_lexical_descents"]==1
    assert report(result)["source_rows"]==10002
    assert calls==[("tickers","0"),("tickers","10000"),("actions","0")]


def test_actions_cross_page_date_order_still_refused(private_root):
    def transport(provider,dataset,query,credential,seconds):
        if dataset=="actions":
            rows="AAA,2020-01-02,split\n"*10000 if dict(query)["skip"]=="0" else "AAA,2020-01-01,split\n"
            return response(csv_payload("actions",rows))
        return default_transport(provider,dataset,query,credential,seconds)
    result=execute(private_root,transport=transport)
    assert report(result)["status"]=="FAILED" and report(result)["terminated_sharadar_datasets"]==1
    assert index(private_root)["census"][1]["terminated"] is False


@pytest.mark.parametrize("day", ["2026-10-10", "2026-99-01", "2026-1-2"])
def test_action_invalid_or_future_date_kept_but_not_completed(private_root,day):
    def transport(provider,dataset,query,credential,seconds):
        if dataset=="actions": return response(csv_payload("actions",f"AAA,{day},split\n"))
        return default_transport(provider,dataset,query,credential,seconds)
    result=execute(private_root,transport=transport)
    assert report(result)["status"]=="FAILED"
    retained=index(private_root)["pages"][-1]
    projection=json.loads((private_root/retained["projection_file"]).read_bytes())
    assert projection["rows"][0]["source"]["date"]==day and projection["row_refusals"]==1


def test_repeated_wire_page_is_incomplete_not_termination(private_root):
    rows="AAA,1,Domestic Common Stock,NYSE,N\n"*10000
    def transport(provider,dataset,query,credential,seconds):
        if dataset=="tickers": return response(csv_payload("tickers",rows))
        pytest.fail("ACTIONS launched after repeated TICKERS wire")
    result=execute(private_root,transport=transport)
    assert report(result)["status"]=="FAILED" and report(result)["attempted_requests"]==2
    assert report(result)["terminated_sharadar_datasets"]==0


def test_small_final_page_required_hitting_bound_is_failed(private_root,monkeypatch):
    monkeypatch.setitem(r.DATASET_LIMITS,"tickers",{"pages":1,"rows":640000,"bytes":256*1024**2})
    def transport(provider,dataset,query,credential,seconds):
        if dataset=="tickers": return response(csv_payload("tickers","AAA,1,Domestic Common Stock,NYSE,N\n"*10000))
        pytest.fail("ACTIONS launched after unclosed page ceiling")
    assert report(execute(private_root,transport=transport))["status"]=="FAILED"


def test_spent_operation_cannot_resolve_credentials_again(private_root):
    execute(private_root)
    with pytest.raises(ValueError):
        execute(private_root,resolver=lambda _: pytest.fail("spent operation resolved credentials"))


def test_fixture_refuses_actual_leaf_or_actual_adapters(private_root):
    for resolver,transport in ((ORIGINAL_RESOLVER,default_transport),(lambda _:TOKEN,ORIGINAL_TRANSPORT)):
        with pytest.raises(ValueError): execute(private_root,resolver=resolver,transport=transport)
    with pytest.raises(ValueError): execute(r.PRIVATE_ROOT)
    assert not list(private_root.iterdir())


@pytest.mark.parametrize("now", [datetime(2026,10,10), datetime(2026,10,9,tzinfo=timezone.utc),datetime(2026,10,11,tzinfo=timezone.utc)])
def test_bad_clock_before_claim(private_root,now):
    with pytest.raises(ValueError): execute(private_root,now=now)
    assert not list(private_root.iterdir())


@pytest.mark.parametrize("clock", [float("nan"),float("inf"),True,"0"])
def test_bad_monotonic_clock_before_claim(private_root,clock):
    with pytest.raises(ValueError): execute(private_root,monotonic=lambda:clock)
    assert not list(private_root.iterdir())


def test_resolver_consumes_same_elapsed_budget_no_http_after_limit(private_root):
    ticks=iter((0.0,0.0,5400.0))
    result=execute(private_root,monotonic=lambda:next(ticks),transport=lambda *_a:pytest.fail("HTTP after elapsed bound"))
    assert report(result)["reserved_requests"]==1 and report(result)["attempted_requests"]==0


def test_credential_failure_is_spent_unknown_no_http(private_root):
    result=execute(private_root,resolver=lambda _:None)
    assert report(result)["status"]=="FAILED"
    assert report(result)["reserved_requests"]==1 and report(result)["attempted_requests"]==0


@pytest.mark.parametrize("changed", [
    response(csv_payload("tickers"),status=302),response(csv_payload("tickers"),status=403),
    response(csv_payload("tickers"),complete=False),
    response(csv_payload("tickers"),headers=(("content-encoding","gzip"),)),
    response(csv_payload("tickers"),headers=(("content-length","10"),("content-length","11"))),
    response(csv_payload("tickers"),headers=(("content-length","-1"),)),
    response(csv_payload("tickers"),headers=(("content-type","text/html"),)),
    r.capture.CaptureResponse(200,(),b"bad csv")])
def test_bad_response_never_retried_or_admitted(private_root,changed):
    result=execute(private_root,transport=lambda *_a:changed)
    assert report(result)["status"]=="FAILED"
    assert report(result)["attempted_requests"]==1 and report(result)["capture_complete"] is False


@pytest.mark.parametrize("echo", [TOKEN,quote(TOKEN,safe=""),"".join("\\u%04x"%ord(c) for c in TOKEN),
    "".join("&#%d;"%ord(c) for c in TOKEN)])
def test_credential_echo_not_retained_or_hashed(private_root,echo):
    result=execute(private_root,transport=lambda *_a:response(csv_payload("tickers",echo+"\n")))
    assert report(result)["status"]=="FAILED" and TOKEN not in result.payload.decode()
    assert index(private_root)["pages"][0]["wire_sha256"] is None
    assert not list(private_root.glob("*.wire.csv"))


@pytest.mark.parametrize("limit", ["max_requests","max_response_bytes"])
def test_frozen_operation_ceiling_before_http(private_root,monkeypatch,limit):
    monkeypatch.setitem(r.LIMITS,limit,1)
    result=execute(private_root)
    assert report(result)["status"]=="FAILED" and report(result)["capture_complete"] is False


def test_driver_source_refusal_precedes_private_preparation(monkeypatch):
    monkeypatch.setattr(driver,"_verify_imports",lambda:None)
    monkeypatch.setattr(driver,"_git_head",lambda:PIN)
    monkeypatch.setattr(r.capture,"_read_source",lambda _:b"changedsource")
    monkeypatch.setattr(driver.subprocess,"run",lambda *_a,**_k:SimpleNamespace(stdout=b"committedsource"))
    monkeypatch.setattr(driver,"_create_private_directory",lambda:pytest.fail("private before exact committed source"))
    with pytest.raises(ValueError): driver.run_repair(owner_instruction_sha256=OWNER,created_utc=CREATED,expires_utc=EXPIRES)


def test_driver_source_custody_then_preparation_then_invocation(private_root,monkeypatch):
    calls=[]
    monkeypatch.setattr(driver,"_verify_imports",lambda:calls.append("imports"))
    monkeypatch.setattr(driver,"_git_head",lambda:PIN)
    monkeypatch.setattr(driver,"_bound_inventory",lambda _:inventory())
    monkeypatch.setattr(driver,"_now",lambda:NOW)
    monkeypatch.setattr(r,"_verify_execution_identity",lambda _:calls.append("committed"))
    monkeypatch.setattr(driver,"_create_private_directory",lambda:ORIGINAL_OPEN(private_root))
    def invoke(given):
        calls.append("invoke")
        assert (private_root/(r.OPERATION_ID+".driver-plan.json")).is_file()
        assert given.body()["mode"]=="production"
        body=driver._unknown_status("FAILED")
        body.pop("preparation_may_exist")
        body.update(scope_spent=True,reserved_requests=0,attempted_requests=0,successful_requests=0,response_bytes=0,
            source_rows=0,row_refusals=0,identical_duplicate_rows=0,conflicting_duplicate_rows=0,ticker_python_lexical_descents=0,
            terminated_sharadar_datasets=0)
        wire=r._canonical(body)
        return r.RepairResult(wire,r.capture.probe._digest(wire),r.PRIVATE_ROOT/r.INDEX_NAME)
    monkeypatch.setattr(r,"execute_repair",invoke)
    assert driver.run_repair(owner_instruction_sha256=OWNER,created_utc=CREATED,expires_utc=EXPIRES)["status"]=="FAILED"
    assert calls==["imports","committed","invoke"]


def test_driver_cli_closes_unknown_native_errors(capsys,monkeypatch):
    def fail(**_kwargs): raise ValueError("LICENSED AAA credential secret")
    monkeypatch.setattr(driver,"run_repair",fail)
    assert driver.main(["--owner-instruction-sha256",OWNER,"--created-utc",CREATED,"--expires-utc",EXPIRES])==1
    output=capsys.readouterr().out
    assert "LICENSED" not in output and "AAA" not in output and "secret" not in output
    assert json.loads(output)["scope_spent"] is None
