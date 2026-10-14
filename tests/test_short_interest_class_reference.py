"""Fabricated native/class source bridges, never historical or market evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.massive_class_denominator as classes
import research.short_interest_etf.sharadar_class_reference as bridge
import research.short_interest_etf.sharadar_securities_master as master
import scripts.build_short_interest_class_reference as offline
from test_short_interest_sharadar_securities_master import ticker, archives


CLOCK = "2026-10-13T23:00:00Z"
LATER = "2026-10-13T23:01:00Z"
HEAD, REMOTE = "a" * 40, "b" * 40
POSIX = pytest.mark.skipif(not hasattr(__import__("os"), "getuid"), reason="protected test filesystem is POSIX-only")


def tickers(rows=None):
    return archives({"tickers": [ticker()] if rows is None else rows,
                     "actions": [], "descriptions": []})[0]


def source_row(symbol="AAPL", *, composite="BBG000000001", class_figi="BBG000000002", shares=123):
    return {"ticker": symbol, "composite_figi": composite, "share_class_figi": class_figi,
            "share_class_shares_outstanding": shares, "active": True, "primary_exchange": "XNAS",
            "type": "CS", "locale": "us", "market": "stocks", "currency_name": "usd"}


def class_source(changes=None):
    changes = changes or {}
    values=[]
    for rid in classes.REQUEST_IDS:
        symbol=classes.massive_request(rid)["url"].rsplit("/",1)[1]
        row=changes.get(rid,source_row(symbol) if symbol=="AAPL" else None)
        if row is None:
            raw=b"";status=404;observed=False;media=""
        else:
            raw=canonical_json({"status":"OK","results":row}).encode();status=200;observed=True;media="application/json"
        values.append(classes.CapturedMassiveClassResponse(rid,classes.request_sha256(rid),raw,CLOCK,
                                                          hash_bytes(raw),status,media,observed))
    return classes.qualify_massive_class_denominator(tuple(values),retrieved_at=CLOCK)


def qualify(rows=None,changes=None):
    return bridge.qualify_sharadar_class_reference(tickers(rows),class_source(changes),retrieved_at=LATER)


def relations(value):
    return value.to_payload()["relations"]


def positive(value):
    return [row for row in relations(value) if row["status"]=="query_date_source_relation_candidate"]


def test_policy_pin_and_separate_literal_authorities_remain_closed():
    policy=bridge.class_reference_protocol()
    assert hash_payload(policy)==bridge.PROTOCOL_SHA256
    assert policy["collision_axes"]==["native_permaticker","composite_FIGI"]
    assert policy["authority"]["source_only"] is True
    assert policy["authority"]["historical_identity_admitted"] is False
    assert policy["authority"]["same_class_denominator_admitted"] is False


def test_exact_composite_observation_matches_distinct_class_not_raw_ticker_alias():
    result=qualify();rows=positive(result)
    assert len(rows)==3
    assert all(row["provider_security_id"]=="sharadar:permaticker:12345" for row in rows)
    assert all(row["source_composite_figi"]=="BBG000000001" and row["source_share_class_figi"]=="BBG000000002" for row in rows)
    assert all(row["historical_effective_intervals"]==[] for row in rows)
    assert all(row["denominator_source_evidence"]["numerator"]==123 for row in rows)
    assert all(row["denominator_source_evidence"]["source_field"]=="share_class_shares_outstanding" for row in rows)
    assert all(row["authority"]["same_class_denominator_admitted"] is False for row in rows)
    assert result.to_payload()["master_rows"][0]["normalized"]["ticker"]=="FAKE"
    assert result.to_payload()["class_responses"][0]["normalized"]["ticker"]=="AAPL"


@pytest.mark.parametrize("axis",["native","composite"])
@pytest.mark.parametrize("malformed",[False,True])
def test_all_identifiable_master_collision_peers_quarantine_positive_candidate(axis,malformed):
    first=ticker();second=ticker("OTHER","12345" if axis=="native" else "12346")
    if axis=="native":second["figi"]="BBG000000003"
    if malformed:second["isdelisted"]="wrong"
    result=qualify([first,second])
    assert not positive(result)
    assert len(result.to_payload()["master_rows"])==2
    assert all(row["denominator_source_evidence"] is None for row in relations(result))


def test_identical_primary_key_copies_both_retained_and_neither_promoted():
    result=qualify([ticker(),ticker()])
    assert not positive(result)
    assert [row["parser_refusal_reason"] for row in result.to_payload()["master_rows"]]==[
        "duplicate_primary_key_all_copies_quarantined"]*2


@pytest.mark.parametrize("change",["native_leading_zero","native_trim","group_trim","composite_trim"])
def test_refusal_normalization_identifies_malformed_master_peer_without_positive_alias(change):
    peer=ticker("OTHER","12346")
    if change=="native_leading_zero":peer.update(permaticker="0012345",figi="BBG000000003")
    elif change=="native_trim":peer.update(permaticker=" 12345 ",figi="BBG000000003")
    elif change=="group_trim":peer["table"]="stocks "
    else:peer["figi"]=" BBG000000001 "
    result=qualify([ticker(),peer])
    assert not positive(result)
    assert result.to_payload()["master_rows"][1]["normalized"] is None
    assert all(row["provider_security_id"] is None for row in relations(result))


@pytest.mark.parametrize("field",["composite_figi","share_class_figi"])
def test_refusal_normalization_identifies_malformed_class_peer_without_positive_alias(field):
    peer=source_row(class_figi="BBG000000003")
    peer[field]=" "+peer[field]+" "
    result=qualify(changes={classes.REQUEST_IDS[1]:peer})
    assert not positive(result)
    assert result.to_payload()["class_responses"][1]["status"]=="malformed"


def test_competing_table_fund_row_is_retained_but_not_stock_owner():
    other=ticker("FUND","12345",table="funds",category="Domestic ETF")
    result=qualify([ticker(),other])
    assert len(result.to_payload()["master_rows"])==2 and len(positive(result))==3


@pytest.mark.parametrize("field,value",[("figi",""),("figi","BBG000000003"),
    ("category","Domestic ETF"),("permaticker","00123"),("isdelisted","wrong")])
def test_missing_unmatched_nonstock_or_malformed_master_never_becomes_class(field,value):
    row=ticker();row[field]=value
    result=qualify([row])
    assert not positive(result)
    assert result.to_payload()["master_rows"][0]["raw_cells"]


@pytest.mark.parametrize("malformed",[False,True])
def test_conflicting_composite_to_class_across_dates_refuses_every_candidate(malformed):
    change=source_row(class_figi="BBG000000003")
    if malformed:change["share_class_shares_outstanding"]="not-a-JSON-number"
    result=qualify(changes={classes.REQUEST_IDS[1]:change})
    assert not positive(result)
    assert any(row["reason"]=="conflicting_composite_to_class_assertions" for row in relations(result))


def test_one_class_cannot_move_between_native_owners_for_different_composites():
    second=ticker("OTHER","12346");second["figi"]="BBG000000003"
    changes={rid:source_row("BRK.A",composite="BBG000000003") for rid in classes.REQUEST_IDS[3:6]}
    result=qualify([ticker(),second],changes)
    assert not positive(result)
    assert any(row["reason"]=="class_to_native_missing_or_ambiguous" for row in relations(result))


def test_composite_equals_class_is_preserved_as_ambiguous_not_cast():
    changes={rid:source_row(class_figi="BBG000000001") for rid in classes.REQUEST_IDS[:3]}
    result=qualify(changes=changes)
    assert not positive(result)
    assert all(row["denominator_source_evidence"] is None for row in relations(result))


@pytest.mark.parametrize("change",["missing","weighted_only","incomplete","fractional","string"])
def test_no_issuer_weighted_fractional_or_incomplete_denominator_transfer(change):
    row=source_row()
    if change in {"missing","weighted_only"}:row.pop("share_class_shares_outstanding")
    if change=="weighted_only":row["weighted_shares_outstanding"]=999999
    if change=="incomplete":row.pop("primary_exchange")
    if change=="fractional":row["share_class_shares_outstanding"]=123.25
    if change=="string":row["share_class_shares_outstanding"]="123"
    result=qualify(changes={classes.REQUEST_IDS[0]:row})
    assert relations(result)[0]["denominator_source_evidence"] is None
    assert relations(result)[0]["authority"]["same_class_denominator_admitted"] is False


@pytest.mark.parametrize("peer",["conflicting_count","malformed_count","incomplete_reference"])
def test_same_class_date_identifiable_peer_blocks_count_promotion(peer):
    row=source_row("BRK.A",shares=999)
    if peer=="malformed_count":row["share_class_shares_outstanding"]="999"
    if peer=="incomplete_reference":row.pop("primary_exchange")
    result=qualify(changes={classes.REQUEST_IDS[3]:row})
    first=relations(result)[0]
    assert first["status"]=="query_date_source_relation_candidate"
    assert first["denominator_source_evidence"] is None
    assert first["denominator_refusal"]=="same_class_date_count_missing_or_conflicting"


def test_all_master_origins_and_thirty_source_responses_remain_private():
    result=qualify([ticker(),ticker("OTHER","12346",table="funds")]).to_payload()
    assert result["all_master_rows_retained"] is True
    assert len(result["master_rows"])==2 and len(result["class_responses"])==30 and len(result["relations"])==30
    assert [row["origin"]["row_index"] for row in result["master_rows"]]==[0,1]
    assert result["authority"]["actual_outcome_looks"]==result["authority"]["qc_attempts"]==0


def test_parser_called_once_and_saved_lookups_never_reparse_archive(monkeypatch):
    calls=[];original=master._parsed
    def parsed(value):calls.append(value.table);return original(value)
    monkeypatch.setattr(master,"_parsed",parsed)
    result=qualify()
    monkeypatch.setattr(master,"_parsed",lambda *args:pytest.fail("no repeated archive parse"))
    result.to_payload();result.to_bytes();result.sha256
    assert calls==["tickers"]


def test_caller_archive_and_returned_dict_mutation_cannot_change_snapshot():
    archive=tickers();result=bridge.qualify_sharadar_class_reference(archive,class_source(),retrieved_at=LATER)
    before=result.to_bytes();object.__setattr__(archive,"raw",b"caller mutation")
    payload=result.to_payload();payload["authority"]["ready_for_empirical_backtest"]=True
    payload["master_rows"][0]["raw_cells"][1]="999"
    assert result.to_bytes()==before


@pytest.mark.parametrize("field,value",[("_report_bytes",b"{}"),("_class_bytes",b"{}"),
    ("_report_sha256","e"*64),("_source_identity","e"*64)])
def test_retained_source_or_report_mutation_cannot_reseal(field,value):
    result=qualify();object.__setattr__(result,field,value)
    with pytest.raises(bridge.SharadarClassReferenceError,match="sealed_class_reference_changed"):
        result.to_bytes()


def test_exact_bound_factory_and_source_types_required():
    with pytest.raises(bridge.SharadarClassReferenceError):bridge.SharadarClassReference()
    with pytest.raises(bridge.SharadarClassReferenceError):
        bridge.qualify_sharadar_class_reference(tickers(),{"source_admitted":True},retrieved_at=LATER)
    with pytest.raises(bridge.SharadarClassReferenceError):
        bridge.qualify_sharadar_class_reference(archives()[1],class_source(),retrieved_at=LATER)


def test_mutated_class_source_seal_refuses_before_master_parse(monkeypatch):
    source=class_source();object.__setattr__(source,"_report_bytes",b"{}")
    monkeypatch.setattr(master,"_parsed",lambda *args:pytest.fail("must reject source before parsing"))
    with pytest.raises(classes.MassiveClassDenominatorError):
        bridge.qualify_sharadar_class_reference(tickers(),source,retrieved_at=LATER)


@pytest.mark.parametrize("clock",["2026-10-13T22:59:59Z","2026-10-13","2026-10-13T23:01:00+00:00"])
def test_new_bridge_clock_never_backdates_class_source(clock):
    with pytest.raises(bridge.SharadarClassReferenceError,match="chronology"):
        bridge.qualify_sharadar_class_reference(tickers(),class_source(),retrieved_at=clock)


@pytest.mark.parametrize("entry",["_class_source","_sources","_build","main"])
def test_unsupported_host_refuses_before_any_source_or_output(monkeypatch,entry):
    def deny():raise offline.CapturePlatformRefusal()
    monkeypatch.setattr(offline,"_require_capture_platform",deny)
    for name in ("_guard","_protected_bytes","_prepare_capture_directory","_publish"):
        monkeypatch.setattr(offline,name,lambda *args:pytest.fail("sensitive action reached"))
    if entry=="main":assert offline.main(["--expected-head",HEAD,"--expected-remote",REMOTE])==2
    else:
        with pytest.raises(offline.CapturePlatformRefusal):
            getattr(offline,entry)(None,**({"head":HEAD,"remote":REMOTE} if entry=="_build" else {}))


@pytest.fixture
def runtime(tmp_path,monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(offline,"_guard",lambda *args:None)
    monkeypatch.setattr(offline,"_git",lambda root,command,target:target)
    monkeypatch.setattr(offline,"_code_identity",lambda *args:"c"*64)
    source=class_source();archive=tickers()
    monkeypatch.setattr(offline,"_sources",lambda *args:(archive,source))
    monkeypatch.setattr(offline,"_utc_now",lambda:LATER)
    return tmp_path,archive,source


@POSIX
def test_offline_publication_is_protected_exclusive_and_source_only(runtime):
    root,_,_=runtime;result=offline._build(root,head=HEAD,remote=REMOTE)
    output=root/offline.OUTPUT
    assert set(path.name for path in output.iterdir())=={"protocol.json","started.json","reference.private.json","completed.json"}
    assert output.stat().st_mode&0o777==0o700
    assert all(path.stat().st_mode&0o777==0o600 for path in output.iterdir())
    assert result["provider_requests"]==result["credential_reads"]==result["outcome_looks"]==result["qc_attempts"]==0
    assert result["backtest_result_exists"] is False
    assert result["private_report_bytes_sha256"]==hash_bytes((output/"reference.private.json").read_bytes())
    assert "relations" not in result and "master_rows" not in result


@POSIX
@pytest.mark.parametrize("early_failure",[False,True])
def test_rerun_or_early_refusal_never_changes_existing_output(runtime,monkeypatch,early_failure):
    root,_,_=runtime;offline._build(root,head=HEAD,remote=REMOTE)
    output=root/offline.OUTPUT;before={path.name:path.read_bytes() for path in output.iterdir()}
    if early_failure:
        def failed(*args):raise offline.CaptureRefusal("test_guard_refusal")
        monkeypatch.setattr(offline,"_guard",failed)
    with pytest.raises(offline.CaptureRefusal):offline._build(root,head=HEAD,remote=REMOTE)
    assert {path.name:path.read_bytes() for path in output.iterdir()}==before


@POSIX
def test_private_report_size_or_reverse_completion_retains_refusal_not_success(runtime,monkeypatch):
    root,_,_=runtime
    monkeypatch.setattr(offline,"MAXIMUM_REPORT_BYTES",1)
    with pytest.raises(offline.CaptureRefusal,match="report_size"):
        offline._build(root,head=HEAD,remote=REMOTE)
    output=root/offline.OUTPUT
    assert (output/"refused.json").exists() and not (output/"completed.json").exists()


@POSIX
def test_reverse_completion_clock_cannot_mint_success(runtime,monkeypatch):
    root,_,_=runtime;clocks=iter([LATER,CLOCK,LATER])
    monkeypatch.setattr(offline,"_utc_now",lambda:next(clocks))
    with pytest.raises(offline.CaptureRefusal,match="completion_chronology"):
        offline._build(root,head=HEAD,remote=REMOTE)
    output=root/offline.OUTPUT
    assert (output/"reference.private.json").exists() and (output/"refused.json").exists()
    assert not (output/"completed.json").exists()


@POSIX
@pytest.mark.parametrize("guard_position",[1,2,3,4,5,6])
def test_every_creation_and_publication_rechecks_exact_lane_before_write(runtime,monkeypatch,guard_position):
    root,_,_=runtime;calls=[]
    def guard(root_arg,head_arg,remote_arg):
        assert (root_arg,head_arg,remote_arg)==(root,HEAD,REMOTE)
        calls.append(1)
        if len(calls)>=guard_position:raise offline.CaptureRefusal("fabricated_lane_changed")
    monkeypatch.setattr(offline,"_guard",guard)
    with pytest.raises(offline.CaptureRefusal,match="fabricated_lane_changed"):
        offline._build(root,head=HEAD,remote=REMOTE)
    output=root/offline.OUTPUT
    expected=set()
    if guard_position>=4:expected.add("protocol.json")
    if guard_position>=5:expected.add("started.json")
    if guard_position>=6:expected.add("reference.private.json")
    assert ({p.name for p in output.iterdir()} if output.exists() else set())==expected


def test_known_class_pin_change_refuses_before_protected_source_read(monkeypatch):
    monkeypatch.setattr(offline.terminal_reader,"CLASS_HEAD","e"*40)
    monkeypatch.setattr(offline.terminal_reader,"_source",lambda *args:pytest.fail("source must not be read"))
    with pytest.raises(offline.CaptureRefusal,match="fixed_class_source_pins_changed"):
        offline._class_source(Path("/fabricated-source"))


@POSIX
def test_typed_class_reconstruction_must_byte_match_original_report(tmp_path,monkeypatch):
    source=class_source();directory=tmp_path/offline.CLASS_SOURCE
    directory.mkdir(parents=True,mode=0o700)
    monkeypatch.setattr(offline.terminal_reader,"_source",lambda *args:source.to_payload())
    monkeypatch.setattr(offline,"CLASS_REPORT_SHA256",source.sha256)
    monkeypatch.setattr(offline,"CLASS_REPORT_BYTES_SHA256",hash_bytes(source.to_bytes()))
    monkeypatch.setattr(offline.terminal_reader,"CLASS_REPORT_SHA256",source.sha256)
    monkeypatch.setattr(offline.terminal_reader,"CLASS_REPORT_BYTES_SHA256",hash_bytes(source.to_bytes()))
    for number,cap in enumerate(source._captures,1):
        prefix=f"attempt-{number:02d}"
        receipt={"body_observed":cap.body_observed,"request_id":cap.request_id,
                 "request_sha256":cap.request_sha256,"received_at":cap.received_at,
                 "http_status":cap.http_status,"content_type":cap.content_type or None,
                 "raw_sha256":cap.raw_sha256 if cap.body_observed else None}
        path=directory/(prefix+".received.json");path.write_bytes(canonical_json(receipt).encode());path.chmod(0o600)
        if cap.body_observed:
            path=directory/(prefix+".raw");path.write_bytes(cap.raw);path.chmod(0o600)
    assert offline._class_source(tmp_path).to_bytes()==source.to_bytes()
    path=directory/"attempt-01.raw";path.write_bytes(b"{}")
    with pytest.raises(offline.CaptureRefusal,match="reconstruction_bytes"):
        offline._class_source(tmp_path)
