"""Invented SEC control trees only; no actual source rows or provider calls."""
from __future__ import annotations

from dataclasses import replace
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from research import insider_buying_pilot_sec_exposure as m


def _file(root,name,raw):
    path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    current=path.parent
    while current!=root.parent:
        current.chmod(0o700);current=current.parent
    path.write_bytes(raw);path.chmod(0o600)
    return m._sha(raw)


def _request(number=1):
    accession=f"0000000123-22-{number:06d}"
    return {"accession_number":accession,"period":"2022Q4","filing_date":"2022-10-03","form_type":"4",
        "issuer_cik":"0000000123","url":"https://www.sec.gov/Archives/edgar/data/123/"+accession+".txt"}


def _chain(tmp_path,*,requests=None,events=None,root_id="invented-chain",profile="event-chain",reuse=None,body=b"INVENTED OPAQUE NON-JSON FINANCIAL BODY"):
    root=tmp_path/root_id;root.mkdir(mode=0o700)
    requests=[_request()] if requests is None else requests;digest=m._sha(body)
    if events is None:
        accession=requests[0]["accession_number"]
        events=[{"kind":"attempt-start","accession_number":accession,"url":requests[0]["url"],"ordinal":1,"started_utc":"2026-10-01T00:00:00Z"},
            {"kind":"attempt-finish","accession_number":accession,"ordinal":1,"outcome":"valid_response","status":200,
             "body_sha256":digest,"body_size_bytes":len(body),"finished_utc":"2026-10-01T00:00:01Z"},
            {"kind":"item-complete","accession_number":accession,"source":"acquired","object_sha256":digest,
             "object_size_bytes":len(body),"prior_report_sha256":None}]
    inventory={"requests":requests,"reuses":[] if reuse is None else reuse}
    raw=m._raw(inventory);tail=_file(root,"inventory.json",raw);pieces=[]
    for index,event in enumerate(events,1):
        raw=m._raw({**event,"prev_sha256":tail})+b"\n";tail=m._sha(raw);pieces.append(raw)
        _file(root,f"event-{index:06d}-{tail}.json",raw)
    journal=b"".join(pieces);_file(root,"attempts.jsonl",journal)
    report=m._raw({"invented":True});_file(root,"report.json",report)
    _file(root,"commit.json",m._raw({"report_name":"report.json","report_sha256":m._sha(report),
        "attempt_journal_sha256":m._sha(journal),"inventory_sha256":m._sha(m._raw(inventory))}))
    _file(root,"objects/"+digest+".bin",body)
    return m.bootstrap.RootSpec(root_id,root,profile)


def _observe(specs):
    return m.observe_exposures(tuple(specs),fixture_only=True)


def test_complete_candidate_is_only_metadata_until_opaque_hash_and_never_parsed(tmp_path,monkeypatch):
    spec=_chain(tmp_path);old=m.bootstrap._json
    def metadata_only(raw,**kw):
        assert b"INVENTED OPAQUE" not in raw
        return old(raw,**kw)
    monkeypatch.setattr(m.bootstrap,"_json",metadata_only)
    holds,exposure,snapshot,candidates=_observe([spec])
    try:
        before=m._json(candidates);row=before["records"][0]["candidates"][0]
        assert row["body_currently_hash_verified"] is row["complete_parent_parsed_here"] is False
        assert row["retained_target"]=={k:_request()[k] for k in m._TARGET_KEYS}
        assert row["request_sha256"]==m._sha(m._raw(row["request"]))
        assert m._json(exposure)["records"][0]["accession_number"]==_request()["accession_number"]
        result=m._json(m.hash_candidate_bodies(holds,candidates))
        row=result["records"][0]["candidates"][0]
        assert row["body_currently_hash_verified"] is True and row["complete_parent_parsed_here"] is False
        assert result["authority"]==m.authority()
        assert m._json(snapshot)["body_files_opened_here"] is False
        assert b"INVENTED OPAQUE" not in m._raw(result)
        holds[0].recheck()
    finally:m.close_holds(holds)


def test_duplicate_completed_roots_remain_separate_body_lineage_not_double_unique_accessions(tmp_path):
    specs=[_chain(tmp_path,root_id="first"),_chain(tmp_path,root_id="second")]
    holds,exposure,snapshot,candidates=_observe(specs)
    try:
        value=m._json(candidates)
        assert len(value["records"])==1 and len(value["records"][0]["candidates"])==2
        assert len(m._json(exposure)["records"])==1
        assert len({row["root_id"] for row in value["records"][0]["candidates"]})==2
    finally:m.close_holds(holds)


def test_consumed_ambiguity_and_later_complete_body_are_independent_axes(tmp_path):
    request=_request()
    pending=_chain(tmp_path,root_id="pending",events=[{"kind":"attempt-start","accession_number":request["accession_number"],
        "url":request["url"],"ordinal":1,"started_utc":"2026-10-01T00:00:00Z"}])
    completed=_chain(tmp_path,root_id="completed")
    holds,exposure,snapshot,candidates=_observe([pending,completed])
    try:
        assert {row["state"] for row in m._json(exposure)["records"][0]["evidence"]}>={"started","completed","ambiguous"}
        assert len(m._json(candidates)["records"][0]["candidates"])==1
        ambiguity=[row for row in m._json(snapshot)["dispatch_records"] if row["state"]=="ambiguous"]
        assert len(ambiguity)==1 and ambiguity[0]["root_id"]=="pending"
        assert ambiguity[0]["control_name"].startswith("event-")  # Real start, not a made-up digest.
    finally:m.close_holds(holds)


def test_refusal_is_consumed_no_candidate_and_plan_alone_is_not_dispatch(tmp_path):
    request=_request()
    refused=_chain(tmp_path,root_id="refused",events=[
        {"kind":"attempt-start","accession_number":request["accession_number"],"url":request["url"],"ordinal":1},
        {"kind":"attempt-finish","accession_number":request["accession_number"],"ordinal":1,"outcome":"http_error","status":403}])
    planned=_chain(tmp_path,root_id="planned",requests=[_request(2)],events=[])
    holds,exposure,snapshot,candidates=_observe([refused,planned])
    try:
        assert len(m._json(exposure)["records"])==1 and m._json(candidates)["records"]==[]
        assert any(row["state"]=="consumed_refusal" for row in m._json(snapshot)["dispatch_records"])
    finally:m.close_holds(holds)


def test_auxiliary_xml_request_never_becomes_original_complete_candidate(tmp_path):
    request=_request();url="https://www.sec.gov/Archives/edgar/data/123/000000012322000001/index.json"
    spec=_chain(tmp_path,requests=[request],events=[{"kind":"attempt-start","url":url,"ordinal":1},
        {"kind":"attempt-finish","ordinal":1,"outcome":"http_status","status":200,"body_sha256":"a"*64,"body_size_bytes":5}])
    holds,exposure,snapshot,candidates=_observe([spec])
    try:
        assert len(m._json(exposure)["records"])==1 and m._json(candidates)["records"]==[]
        assert m._json(snapshot)["dispatch_records"][0]["url"]==url
    finally:m.close_holds(holds)


@pytest.mark.parametrize("kind",["body","symlink","hardlink","mode","extra","latebody"])
def test_body_hash_custody_inventory_and_final_recheck_are_binding(tmp_path,kind):
    spec=_chain(tmp_path);holds,_,_,candidates=_observe([spec])
    try:
        value=m._json(candidates);row=value["records"][0]["candidates"][0];path=spec.path/row["raw_object"]["relative_path"]
        if kind=="body":path.write_bytes(b"X"*path.stat().st_size)
        elif kind=="symlink":
            target=tmp_path/"invented-target";target.write_bytes(path.read_bytes());target.chmod(0o600);path.unlink();path.symlink_to(target)
        elif kind=="hardlink":os.link(path,tmp_path/"alias")
        elif kind=="mode":path.chmod(0o644)
        elif kind=="extra":_file(spec.path,"objects/unexpected.bin",b"x")
        elif kind=="latebody":
            m.hash_candidate_bodies(holds,candidates);stamp=path.stat();raw=path.read_bytes();path.write_bytes(b"X"+raw[1:])
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with pytest.raises((m.PilotSecExposureError,m.bootstrap.ParentBootstrapError)):holds[0].recheck()
            return
        with pytest.raises((m.PilotSecExposureError,m.bootstrap.ParentBootstrapError)):m.hash_candidate_bodies(holds,candidates)
    finally:m.close_holds(holds)


def test_swapping_candidate_descriptor_under_same_held_control_is_not_permitted(tmp_path):
    spec=_chain(tmp_path);holds,_,_,candidates=_observe([spec])
    try:
        value=m._json(candidates);row=value["records"][0]["candidates"][0]
        row["request"]["issuer_cik"]="456";row["retained_target"]["issuer_cik"]="456"
        row["request_sha256"]=m._sha(m._raw(row["request"]))
        with pytest.raises(m.PilotSecExposureError,match="exact_observed"):m.hash_candidate_bodies(holds,m._raw(value))
    finally:m.close_holds(holds)


@pytest.mark.parametrize("change",[lambda row:row.update(object_sha256="f"*64),lambda row:row.update(object_size_bytes=1),
    lambda row:row.update(source="unknown")])
def test_item_complete_requires_exact_response_link(tmp_path,change):
    request=_request();raw=b"INVENTED OPAQUE";digest=m._sha(raw)
    events=[{"kind":"attempt-start","accession_number":request["accession_number"],"url":request["url"],"ordinal":1},
        {"kind":"attempt-finish","accession_number":request["accession_number"],"ordinal":1,"outcome":"valid_response","status":200,
         "body_sha256":digest,"body_size_bytes":len(raw)},
        {"kind":"item-complete","accession_number":request["accession_number"],"source":"acquired","object_sha256":digest,
         "object_size_bytes":len(raw),"prior_report_sha256":None}]
    change(events[-1]);spec=_chain(tmp_path,events=events,body=raw)
    with pytest.raises((m.PilotSecExposureError,m.bootstrap.ParentBootstrapError)):_observe([spec])


def _claims(tmp_path,*,complete=True,result=True):
    root=tmp_path/"invented-claims";root.mkdir(mode=0o700);request=_request();body=b"INVENTED OPAQUE ORIGINAL"
    row={"request":request,"request_sha256":m._sha(m._raw(request)),"global_index":1}
    selection={"requests":[row]};selection_sha=m._sha(m._raw(selection))
    reservation={"selection":selection,"selection_sha256":selection_sha,"reserved_utc":"2026-10-01T00:00:00Z"}
    reservation_raw=m._raw(reservation);reservation_sha=_file(root,"runs/ib-invented/reservation.json",reservation_raw)
    claim={"request":row,"capture_id":"ib-invented","reservation_sha256":reservation_sha,"selection_sha256":selection_sha}
    claim_sha=_file(root,"claims/"+m.bootstrap.locators.accession_key(request["accession_number"])+".json",m._raw(claim))
    start={"claim_sha256":claim_sha,"request_sha256":row["request_sha256"],"reservation_sha256":reservation_sha,
        "ordinal":0,"started_utc":"2026-10-01T00:00:01Z"}
    start_sha=_file(root,"runs/ib-invented/request-000-start.json",m._raw(start))
    result_value={"start_sha256":start_sha,"request_sha256":row["request_sha256"],"ordinal":0,"status":200,
        "body_retained":True,"body_sha256":m._sha(body),"body_size_bytes":len(body),"disposition":"request-bound-parent-retained",
        "finished_utc":"2026-10-01T00:00:02Z"}
    if result:
        result_sha=_file(root,"runs/ib-invented/request-000-result.json",m._raw(result_value))
        if complete:_file(root,"runs/ib-invented/complete.json",m._raw({"reservation_sha256":reservation_sha,"selection_sha256":selection_sha,
            "results":[{"result_name":"request-000-result.json","result_sha256":result_sha}]}))
    _file(root,"runs/ib-invented/objects/"+m._sha(body)+".bin",body);_file(root,"capture.lock",b"INVENTED CLAIM LOCK")
    return m.bootstrap.RootSpec("invented-claims",root,"global-claims")


@pytest.mark.parametrize("complete,result,candidate_count,ambiguous",[(True,True,1,False),(False,True,0,False),(False,False,0,True)])
def test_global_claim_result_and_aggregate_seals_remain_distinct(tmp_path,complete,result,candidate_count,ambiguous):
    spec=_claims(tmp_path,complete=complete,result=result);holds,exposure,snapshot,candidates=_observe([spec])
    try:
        assert len(m._json(candidates)["records"])==candidate_count
        states={row["state"] for row in m._json(exposure)["records"][0]["evidence"]}
        assert ("ambiguous" in states) is ambiguous and "reserved" in states
        if result and not complete:assert m._json(snapshot)["dispatch_records"][0]["state"]=="response_unsealed"
    finally:m.close_holds(holds)


def test_global_claim_result_external_completion_hash_is_binding(tmp_path):
    spec=_claims(tmp_path);path=spec.path/"runs/ib-invented/complete.json"
    value=json.loads(path.read_bytes());value["results"][0]["result_sha256"]="f"*64
    _file(spec.path,"runs/ib-invented/complete.json",m._raw(value))
    with pytest.raises(m.PilotSecExposureError,match="completion_binding"):_observe([spec])


def test_fixture_cannot_select_actual_roots_before_any_metadata(monkeypatch):
    monkeypatch.setattr(m.bootstrap,"bootstrap_exposures",lambda *_:pytest.fail("actual control read must not occur"))
    with pytest.raises((m.PilotSecExposureError,m.bootstrap.ParentBootstrapError)):
        m.observe_exposures(m.actual_roots(),fixture_only=True)


def test_production_requires_fixed_roster_and_native_guards_before_control_reads(tmp_path,monkeypatch):
    spec=_chain(tmp_path)
    monkeypatch.setattr(m.bootstrap,"bootstrap_exposures",lambda *_:pytest.fail("control read must not occur"))
    with pytest.raises(m.PilotSecExposureError,match="fixed_actual"):m.observe_exposures((spec,),fixture_only=False)


def test_target_issuer_raw_date_period_and_original_url_are_not_synthesized():
    for key,value in (("filing_date","2022-99-99"),("period","2021Q4"),("issuer_cik","0")):
        request=_request();request[key]=value
        with pytest.raises(m.PilotSecExposureError):m._target(request)
    with pytest.raises(m.PilotSecExposureError,match="original_parent_locator"):
        m._candidate("invented","source.json","a"*64,_request(),"https://www.sec.gov/Archives/edgar/data/999/other.txt",
                     {"relative_path":"objects/"+ "a"*64+".bin","sha256":"a"*64,"size_bytes":1})


def test_drain_all_cleanup_preserves_existing_primary():
    closed=[]
    def failing(label):
        def close():closed.append(label);raise OSError("private")
        return close
    holds=[SimpleNamespace(close=failing("first")),SimpleNamespace(close=failing("second"))]
    with pytest.raises(m.PilotSecExposureError,match="cleanup"):m.close_holds(holds)
    assert closed==["second","first"]
    with pytest.raises(ValueError,match="primary"):
        try:raise ValueError("primary")
        finally:m.close_holds(holds)
    assert closed==["second","first","second","first"]


def test_actual_roots_adds_2006_namespace_without_mutating_bootstrap():
    old=m.bootstrap.actual_roots();new=m.actual_roots()
    assert old==m.bootstrap.actual_roots() and len(new)==len(old)+1
    assert new[-1].root_id=="sec-2006q1-global-claims"
    assert any(spec.root_id=="sec-recovery-v4-global-claims" for spec in new)


def test_simple_missing_completion_preserves_start_and_never_mints_candidate(tmp_path):
    request=_request()
    spec=_chain(tmp_path,events=[{"kind":"attempt-start","url":request["url"],"ordinal":1}])
    (spec.path/"commit.json").unlink()
    spec=replace(spec,profile="simple-jsonl")
    holds,exposure,snapshot,candidates=_observe([spec])
    try:
        assert m._json(candidates)["records"]==[]
        assert "ambiguous" in {row["state"] for row in m._json(exposure)["records"][0]["evidence"]}
    finally:m.close_holds(holds)


def test_real_complete_text_simple_profile_matches_terminal_body_not_auxiliary(tmp_path):
    request=_request();body=b"INVENTED ORIGINAL TEXT";digest=m._sha(body)
    spec=_chain(tmp_path,events=[{"kind":"attempt-start","url":request["url"],"ordinal":1},
        {"kind":"attempt-finish","ordinal":1,"outcome":"http_status","status":200,"body_sha256":digest,"body_size_bytes":len(body)}],body=body)
    candidate={key:value for key,value in request.items() if key!="url"}
    _file(spec.path,"inventory.json",m._raw({"candidates":[candidate]}))
    report={"filings":[{"status":"acquired_noncanonical","candidate":candidate,"source_url":request["url"],
        "raw_object":{"relative_path":"objects/"+digest+".bin","sha256":digest,"size_bytes":len(body)}}]}
    report_sha=_file(spec.path,"report.json",m._raw(report))
    _file(spec.path,"commit.json",m._raw({"report_name":"report.json","report_sha256":report_sha,
        "attempt_journal_sha256":m._sha((spec.path/"attempts.jsonl").read_bytes())}))
    spec=replace(spec,profile="simple-jsonl")
    holds,_,_,candidates=_observe([spec])
    try:
        result=m._json(m.hash_candidate_bodies(holds,candidates))
        assert result["records"][0]["candidates"][0]["body_currently_hash_verified"] is True
        assert "url" not in result["records"][0]["candidates"][0]["request"]
    finally:m.close_holds(holds)


def _masters(tmp_path):
    body=b"INVENTED OPAQUE MASTER GZIP";digest=m._sha(body)
    periods=[f"{year}Q{quarter}" for year in range(2006,2027) for quarter in range(1,5) if (year,quarter)<=(2026,2)]
    events=[];rows=[];requests=[]
    receipt={"decoded_sha256":"b"*64,"decoded_size_bytes":100,"parser_version":"insider-buying-sec-quarter-master-idx-v1",
        "master_receipt_sha256":"c"*64,"all_filing_row_count":20,"form4_or_4a_path_rows":10}
    for index,period in enumerate(periods,1):
        url=f"https://www.sec.gov/Archives/edgar/full-index/{period[:4]}/QTR{period[-1]}/master.gz"
        requests.append({"period":period,"url":url})
        events.extend([{"kind":"attempt-start","period":period,"url":url,"ordinal":index},
            {"kind":"attempt-finish","period":period,"ordinal":index,"outcome":"valid_response","status":200,
             "body_sha256":digest,"body_size_bytes":len(body)},
            {"kind":"quarter-complete","period":period,"object_sha256":digest,"object_size_bytes":len(body),"summary":receipt}])
        rows.append({"period":period,"source_url":url,"status":"acquired_noncanonical","receipt":receipt,
            "raw_object":{"relative_path":"objects/"+digest+".bin","sha256":digest,"size_bytes":len(body)}})
    spec=_chain(tmp_path,root_id="masters-v3",requests=requests,events=events,body=body)
    report_sha=_file(spec.path,"report.json",m._raw({"complete_82_master_indexes_acquired":True,"master_indexes":rows}))
    _file(spec.path,"commit.json",m._raw({"report_name":"report.json","report_sha256":report_sha,
        "attempt_journal_sha256":m._sha((spec.path/"attempts.jsonl").read_bytes()),
        "inventory_sha256":m._sha((spec.path/"inventory.json").read_bytes())}))
    return spec


def test_all_25_context_master_descriptors_bound_to_82_terminals_without_gzip_decode(tmp_path):
    spec=_masters(tmp_path);holds,exposure,snapshot,candidates=_observe([spec])
    try:
        result=m._json(candidates)
        assert result["records"]==[] and m._json(exposure)["records"]==[]
        assert len(result["masters"])==25
        assert result["masters"][0]["period"]=="2020Q1" and result["masters"][-1]["period"]=="2026Q1"
        result=m._json(m.hash_candidate_bodies(holds,candidates))
        assert all(row["body_currently_hash_verified"] is True and row["master_decoded_here"] is False for row in result["masters"])
    finally:m.close_holds(holds)


def test_master_report_alone_cannot_fabricate_quarter_terminal_body_link(tmp_path):
    spec=_masters(tmp_path);report=json.loads((spec.path/"report.json").read_bytes())
    report["master_indexes"][0]["raw_object"]["sha256"]="f"*64
    report["master_indexes"][0]["raw_object"]["relative_path"]="objects/"+"f"*64+".bin"
    digest=_file(spec.path,"report.json",m._raw(report))
    commit=json.loads((spec.path/"commit.json").read_bytes());commit["report_sha256"]=digest
    _file(spec.path,"commit.json",m._raw(commit))
    with pytest.raises(m.PilotSecExposureError,match="master_completed_event"):_observe([spec])


def test_separate_diagnostic_body_preserves_predecessor_ambiguous_start(tmp_path):
    request=_request()
    prior=_chain(tmp_path,root_id="pending-v3",events=[{"kind":"attempt-start","accession_number":request["accession_number"],
        "url":request["url"],"ordinal":1,"started_utc":"2026-10-01T00:00:00Z"}])
    root=tmp_path/"separate-diagnostic";root.mkdir(mode=0o700);body=b"INVENTED SEPARATE DIAGNOSTIC BODY";digest=m._sha(body)
    manifest=m._raw({"ambiguous_request_sha256":m._sha(m._raw(request))});_file(root,"manifest.json",manifest)
    start=m._raw({"manifest_sha256":m._sha(manifest),"started_utc":"2026-10-01T01:00:00Z"})
    _file(root,"attempt-start.json",start)
    _file(root,"response.json",m._raw({"status":200,"body_sha256":digest,"body_size_bytes":len(body),"headers_sha256":"a"*64}))
    report=m._raw({"manifest_sha256":m._sha(manifest),"attempt_start_sha256":m._sha(start),"body_sha256":digest,
        "body_size_bytes":len(body),"response_headers_sha256":"a"*64,"transport_outcome":"returned",
        "envelope_outcome":"accepted","finished_utc":"2026-10-01T01:00:01Z"})
    _file(root,"report.json",report)
    _file(root,"commit.json",m._raw({"report_name":"report.json","report_sha256":m._sha(report),"manifest_sha256":m._sha(manifest)}))
    _file(root,"objects/"+digest+".bin",body)
    holds,exposure,snapshot,candidates=_observe([prior,m.bootstrap.RootSpec("separate-diagnostic",root,"diagnostic")])
    try:
        assert "ambiguous" in {item["state"] for item in m._json(exposure)["records"][0]["evidence"]}
        result=m._json(m.hash_candidate_bodies(holds,candidates))
        assert result["records"][0]["candidates"][0]["root_id"]=="separate-diagnostic"
        assert result["records"][0]["candidates"][0]["complete_parent_parsed_here"] is False
    finally:m.close_holds(holds)


def test_unknown_private_request_fields_refused_before_export():
    request=_request();request["contact"]="DO NOT EXPORT"
    with pytest.raises(m.PilotSecExposureError,match="private_or_unknown"):m._target(request)


def test_genuine_shard_relative_objects_are_bound_and_hashable(tmp_path):
    root=tmp_path/"invented-campaign";root.mkdir(mode=0o700)
    _chain(root,root_id="shard-0000")
    spec=m.bootstrap.RootSpec("invented-campaign",root,"sharded-events")
    holds,exposure,snapshot,candidates=_observe([spec])
    try:
        row=m._json(candidates)["records"][0]["candidates"][0]
        assert row["raw_object"]["relative_path"].startswith("shard-0000/objects/")
        result=m._json(m.hash_candidate_bodies(holds,candidates))
        assert result["records"][0]["candidates"][0]["body_currently_hash_verified"] is True
    finally:m.close_holds(holds)
