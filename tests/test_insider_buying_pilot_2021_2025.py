"""Invented weekday calendar/context metadata only, NOT an exchange calendar.

Holidays are intentionally not asserted or authenticated. No market source,
financial values, provider/credential, original corpus or QC is accessed.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import ast
import json
from zoneinfo import ZoneInfo

import pytest

from data.hashing import hash_bytes, hash_payload
from research import insider_buying_pilot_2021_2025 as module


def _calendar():
    rows=[];day=date(2019,10,1);zone=ZoneInfo("America/New_York")
    while day <= date(2026,6,30):
        if day.weekday() < 5:
            rows.append({"session":day.isoformat(), **{field:datetime.combine(day,clock,zone).astimezone(timezone.utc)
                .isoformat().replace("+00:00","Z") for field,clock in (("open_utc",time(9,30)),("close_utc",time(16)))}})
        day+=timedelta(days=1)
    return {"schema":module.CALENDAR_SCHEMA,"sessions":rows}


@pytest.fixture(scope="module")
def calendar():return _calendar()


def _freeze(calendar):
    raw=module._raw(calendar)
    return module.freeze_pilot_2021_2025(calendar_raw=raw,expected_calendar_sha256=hash_bytes(raw))


@pytest.fixture
def plan(calendar):return _freeze(calendar)


def _entry(plan,*,entry="2022-06-15",prior_listing=None):
    body=plan.to_payload();rows=body["calendar_sessions"];dates=[row["session"] for row in rows];i=dates.index(entry)
    listed=0 if prior_listing is None else i-prior_listing
    listing_day="2010-01-04" if prior_listing is None else dates[listed]
    lower=max(listed,i-253)
    return {"schema":module.ENTRY_SCHEMA,"pilot_plan_sha256":plan.sha256,"entry_session":entry,"security_id":"INVENTED-SID",
        "first_listing_session":listing_day,"listing_known_at_utc":"2010-01-01T00:00:00Z" if prior_listing is None else rows[listed]["open_utc"]
            .replace("14:30:00","14:00:00").replace("13:30:00","13:00:00"),
        "listing_evidence_sha256":"a"*64,"prior_listed_sessions":dates[lower:i],
        "open_intervals":[{"start_session":dates[j-1],"end_session":dates[j],"knowledge_at_utc":rows[j]["open_utc"],
            "source_record_sha256":hash_payload({"invented-date":dates[j]})} for j in range(lower+1,i)],
        "stock_context_sessions":dates[max(listed,i-60):i],"signal_context_sessions":dates[i-30:i+1],
        "context_known_at_utc":rows[i-1]["close_utc"]}


def _assess(plan,body):
    raw=module._raw(body)
    return module.assess_entry_context(plan=plan,metadata_raw=raw,expected_metadata_sha256=hash_bytes(raw))


def test_new_pilot_is_separate_exploratory_inert_and_preserves_original_study(plan,calendar):
    body=plan.to_payload()
    assert body["entry_window"] == ["2021-01-01","2025-12-31"]
    assert body["padded_calendar_price_request_window"] == ["2019-10-01","2026-06-30"]
    assert body["source_quarters"] == [f"{y}Q{q}" for y in range(2020,2027) for q in range(1,5) if(y,q)<=(2026,1)]
    assert len(body["source_quarters"]) == 25
    assert body["sec_context_only_quarters"] == ["2020Q1","2020Q2","2020Q3","2020Q4","2026Q1"]
    assert body["original_study"]["source_window"] == ["2006-01-01","2026-06-30"]
    assert body["original_study"]["quarter_count"] == 82
    assert body["original_study"]["original_policy_or_artifacts_modified"] is False
    assert body["original_study"]["pilot_replaces_or_completes_original_study"] is False
    assert body["original_study"]["canonical_confirmation_overlap"] == body["entry_window"]
    assert body["original_study"]["canonical_confirmation_remains_untouched_after_future_pilot_outcome_use"] is False
    assert body["frozen_parent_policy"] == module.analysis.frozen_analysis_policy_v2()
    assert body["frozen_parent_policy_sha256"] == module.FROZEN_PARENT_POLICY_SHA256
    assert body["multiplicity"]["alpha_spent"] == body["multiplicity"]["alpha_allocated_this_pilot"] == [0,1]
    assert body["multiplicity"]["registered_look_id"] is None
    assert body["multiplicity"]["authorized_outcome_looks"] == body["multiplicity"]["consumed_outcome_looks"] == 0
    assert body["calendar_sha256"] == hash_bytes(module._raw(calendar))
    assert all(value is False or type(value) is int and value == 0 for value in body["readiness"].values())


def test_warmup_factor_tail_signal_liquidity_and_both_earnings_buffers_are_calendar_derived(plan):
    body=plan.to_payload();rows=body["calendar_sessions"];dates=[row["session"] for row in rows]
    context=body["context"];first=dates.index(context["first_entry_session"]);last=dates.index(context["last_entry_session"])
    assert context["required_first_preentry_open_session"] == dates[first-253]
    assert context["required_last_outcome_open_session"] == dates[last+60]
    assert context["signal_max_age_sessions"] == 30 and context["signal_window_inclusive_session_labels"] == 31
    assert context["liquidity_prior_sessions"] == context["outcome_tail_sessions"] == 60
    assert context["minimum_prior_regular_listing_sessions"] == 253 and context["factor_prior_actual_open_intervals"] == 252
    assert context["earnings_windows_sessions"] == [2,5] and context["earnings_windows_inclusive"] is True
    assert context["required_earnings_first_close_utc"] == rows[first-6]["close_utc"]
    assert context["required_earnings_last_close_utc"] == rows[last+5]["close_utc"]
    assert context["required_earnings_first_civil_date"] == dates[first-6]
    assert context["required_earnings_last_civil_date"] == dates[last+5]
    assert context["earnings_used_for_primary_selection_or_clock"] is False
    assert context["moo_prerequisite_cutoff_minutes_before_open"]==2 and context["moo_prerequisite_cutoff_inclusive"] is True


def test_253_prior_regular_session_boundary_is_not_inferred_from_calendar_endpoint_span(calendar):
    rows=calendar["sessions"];first=next(i for i,row in enumerate(rows) if row["session"]>=module.ENTRY_FIRST)
    for count in (252,253):
        remove=first-count;body={"schema":module.CALENDAR_SCHEMA,"sessions":[rows[0],*rows[1+remove:]]}
        if count==252:
            with pytest.raises(module.PilotMetadataError,match="pilot_warmup_or_outcome_tail_missing"):_freeze(body)
        else:assert _freeze(body).to_payload()["context"]["required_first_preentry_open_session"]==rows[0]["session"]


def test_full60_session_tail_is_not_inferred_from_final_calendar_date(calendar):
    rows=calendar["sessions"];last=max(i for i,row in enumerate(rows) if row["session"]<=module.ENTRY_LAST)
    # Leave only59 later records, including the required last padded date.
    body={"schema":module.CALENDAR_SCHEMA,"sessions":[*rows[:last+59],rows[-1]]}
    with pytest.raises(module.PilotMetadataError,match="pilot_warmup_or_outcome_tail_missing"):_freeze(body)


def test_split_labels_purge_and_embargo_are_fixed_before_outcomes(plan):
    body=plan.to_payload();rows=body["scheduled_entries"];dates=[row["entry_session"] for row in rows]
    for boundary in ("2024-01-01","2025-01-01"):
        b=next(i for i,day in enumerate(dates) if day>=boundary)
        assert all("purged_label_crosses_next_phase" in row["schedule_exclusion_reasons"] for row in rows[b-60:b])
        assert "purged_label_crosses_next_phase" not in rows[b-61]["schedule_exclusion_reasons"]
        assert all("embargo_first60_phase_sessions" in row["schedule_exclusion_reasons"] for row in rows[b:b+60])
        assert "embargo_first60_phase_sessions" not in rows[b+60]["schedule_exclusion_reasons"]
    assert rows[-1]["schedule_disposition"] == "INCLUDED"  # paid-for +60 tail, no silent late2025 censoring
    for phase,counts in body["schedule_counts"].items():
        selected=[row for row in rows if row["phase"]==phase]
        assert counts["declared_entry_sessions"] == len(selected)
        assert counts["included_entry_sessions"]+counts["excluded_entry_sessions"] == len(selected)
    assert body["split_policy"]["future_returns_read_for_split"] is False


@pytest.mark.parametrize("mutation", ["extra","missing","nonlist","empty","reverse","duplicate","nonstrdate","bad_date","weekend",
    "bad_open","bad_close","wrong_dst","pre_scope","post_scope","missing_pad","missing_tail","nan","unknown_schema"])
def test_canonical_calendar_scope_types_order_clocks_and_bounds_refuse(calendar,mutation):
    body=deepcopy(calendar)
    if mutation == "extra":body["credential"]="not-a-key"
    elif mutation == "missing":body.pop("sessions")
    elif mutation == "nonlist":body["sessions"]=True
    elif mutation == "empty":body["sessions"]=[]
    elif mutation == "reverse":body["sessions"].reverse()
    elif mutation == "duplicate":body["sessions"][1]=deepcopy(body["sessions"][0])
    elif mutation == "nonstrdate":body["sessions"][0]["session"]=True
    elif mutation == "bad_date":body["sessions"][0]["session"]="2019-10-32"
    elif mutation == "weekend":body["sessions"][0]["session"]="2019-10-05"
    elif mutation == "bad_open":body["sessions"][0]["open_utc"]="2019-10-01T13:31:00Z"
    elif mutation == "bad_close":body["sessions"][0]["close_utc"]="2019-10-01T20:00:01Z"
    elif mutation == "wrong_dst":body["sessions"][0]["open_utc"]="2019-10-01T14:30:00Z"
    elif mutation == "pre_scope":body["sessions"][0]["session"]="2019-09-30"
    elif mutation == "post_scope":body["sessions"][-1]["session"]="2026-07-01"
    elif mutation == "missing_pad":body["sessions"].pop(0)
    elif mutation == "missing_tail":body["sessions"]=body["sessions"][:-100]
    elif mutation == "nan":
        raw=b'{"schema":NaN,"sessions":[]}'
        with pytest.raises(module.PilotMetadataError):module.freeze_pilot_2021_2025(calendar_raw=raw,expected_calendar_sha256=hash_bytes(raw))
        return
    else:body["schema"]="unregistered"
    with pytest.raises(module.PilotMetadataError):_freeze(body)


def test_external_root_bad_json_bounds_and_duplicate_fields_refuse(calendar,monkeypatch):
    raw=module._raw(calendar)
    for data,root in ((raw,"0"*64),(raw,True),(bytearray(raw),hash_bytes(raw)),(b"\xff",hash_bytes(b"\xff")),
        (b'{"schema":1,"schema":2}',hash_bytes(b'{"schema":1,"schema":2}'))):
        with pytest.raises(module.PilotMetadataError):module.freeze_pilot_2021_2025(calendar_raw=data,expected_calendar_sha256=root)
    monkeypatch.setattr(module,"MAX_BYTES",16)
    with pytest.raises(module.PilotMetadataError):module.freeze_pilot_2021_2025(calendar_raw=raw,expected_calendar_sha256=hash_bytes(raw))


@pytest.mark.parametrize("number",[b"100",b"1.25",b"1e999999",b"9"*5000])
def test_input_numeric_tokens_refuse_before_any_int_float_or_unknown_price_value_decode(number):
    raw=b'{"schema":"'+module.CALENDAR_SCHEMA.encode()+b'","sessions":[],"price":'+number+b'}'
    with pytest.raises(module.PilotMetadataError,match="numeric_json_input_refused"):
        module.freeze_pilot_2021_2025(calendar_raw=raw,expected_calendar_sha256=hash_bytes(raw))


def test_dst_transition_and_early_close_are_accepted_only_at_qualified_regular_clocks(calendar):
    body=deepcopy(calendar);row=next(row for row in body["sessions"] if row["session"]=="2023-11-24")
    row["close_utc"]="2023-11-24T18:00:00Z"
    result=_freeze(body).to_payload()
    byday={row["session"]:row for row in result["calendar_sessions"]}
    assert byday["2023-03-10"]["open_utc"].endswith("14:30:00Z")
    assert byday["2023-03-13"]["open_utc"].endswith("13:30:00Z")
    assert byday["2023-11-03"]["open_utc"].endswith("13:30:00Z")
    assert byday["2023-11-06"]["open_utc"].endswith("14:30:00Z")


def test_plan_factory_reconstruction_mutation_and_detached_payload_fail_closed(plan):
    payload=plan.to_payload();payload["readiness"]["backtesting_ready"]=True
    assert plan.to_payload()["readiness"]["backtesting_ready"] is False
    for forged in (replace(plan),module.PilotMetadataResult(plan.canonical_bytes(),object())):
        with pytest.raises(module.PilotMetadataError):module._plan(forged)
    object.__setattr__(plan,"_bytes",b"{}")
    with pytest.raises(module.PilotMetadataError):plan.to_payload()


def test_frozen_parent_policy_drift_cannot_be_silently_absorbed(calendar,monkeypatch):
    parent=module.analysis.frozen_analysis_policy_v2();parent["costs_bps_per_side"]=[0,1,2]
    monkeypatch.setattr(module.analysis,"frozen_analysis_policy_v2",lambda:parent)
    with pytest.raises(module.PilotMetadataError,match="frozen_parent_economics_drifted"):_freeze(calendar)


def test_exact253_prior_listing_sessions_and252_real_declared_intervals_do_not_promote_readiness(plan):
    body=_entry(plan);result=_assess(plan,body).to_payload()
    assert result["metadata_disposition"] == "CONTEXT_METADATA_COMPLETE"
    assert result["declared_prior_listing_sessions"]==253 and result["declared_prior_open_intervals"]==252
    assert result["declared_liquidity_context_sessions"]==60 and result["declared_signal_context_session_labels"]==31
    assert result["real_primary_eligibility_established"] is False
    assert result["metadata_is_not_actual_price_or_listing_evidence"] is True
    assert all(value is False or type(value) is int and value==0 for value in result["readiness"].values())


@pytest.mark.parametrize("prior",[0,1,19,59,60,252,253])
def test_young_listing_retains_every_existing_prior_session_without_imputation(plan,prior):
    body=_entry(plan,prior_listing=prior);result=_assess(plan,body).to_payload()
    assert result["declared_prior_listing_sessions"]==prior
    assert result["declared_prior_open_intervals"]==max(0,prior-1)
    assert result["declared_liquidity_context_sessions"]==min(60,prior)
    assert result["source_row_must_remain_in_accounting"] is True
    reason="primary_factor_calibration_listing_seasoning_below_253_sessions"
    assert (reason in result["exclusion_reasons"]) is (prior<253)
    assert result["metadata_disposition"] == ("EXCLUDED_METADATA" if prior<253 else "CONTEXT_METADATA_COMPLETE")


@pytest.mark.parametrize("mutation",["schema","plan_hash","extra_price","listing_future","known_equal_open","known_future",
    "listed_gap","listed_reverse","interval_gap","interval_reverse","interval_future","interval_early","interval_extra",
    "interval_hash","liquidity_gap","signal30_not31","signal_future","context_future","context_too_early","security_id",
    "nonregular_listing","outside_window","wrong_interval_clock"])
def test_mature_history_missing_future_and_numeric_or_other_unknown_context_refuses(plan,mutation):
    body=_entry(plan);entry=body["entry_session"]
    opened=next(row["open_utc"] for row in plan.to_payload()["calendar_sessions"] if row["session"]==entry)
    if mutation=="schema":body["schema"]="old-epoch"
    elif mutation=="plan_hash":body["pilot_plan_sha256"]="b"*64
    elif mutation=="extra_price":body["close_price"]="100"
    elif mutation=="listing_future":body["first_listing_session"]="2026-01-01"
    elif mutation=="known_equal_open":body["listing_known_at_utc"]=opened
    elif mutation=="known_future":body["listing_known_at_utc"]="2026-01-01T00:00:00Z"
    elif mutation=="listed_gap":body["prior_listed_sessions"].pop(20)
    elif mutation=="listed_reverse":body["prior_listed_sessions"].reverse()
    elif mutation=="interval_gap":body["open_intervals"].pop(20)
    elif mutation=="interval_reverse":body["open_intervals"].reverse()
    elif mutation=="interval_future":body["open_intervals"][-1]["knowledge_at_utc"]=opened
    elif mutation=="interval_early":body["open_intervals"][-1]["knowledge_at_utc"]="2000-01-01T00:00:00Z"
    elif mutation=="interval_extra":body["open_intervals"][-1]["return"]="0.1"
    elif mutation=="interval_hash":body["open_intervals"][-1]["source_record_sha256"]=True
    elif mutation=="liquidity_gap":body["stock_context_sessions"].pop()
    elif mutation=="signal30_not31":body["signal_context_sessions"].pop(0)
    elif mutation=="signal_future":body["signal_context_sessions"][-1]="2026-01-01"
    elif mutation=="context_future":body["context_known_at_utc"]=opened
    elif mutation=="context_too_early":body["context_known_at_utc"]="2000-01-01T00:00:00Z"
    elif mutation=="security_id":body["security_id"]=True
    elif mutation=="nonregular_listing":body["first_listing_session"]="2021-06-05"
    elif mutation=="outside_window":body["entry_session"]="2026-01-05"
    else:body["open_intervals"][-1]["end_session"]=entry
    with pytest.raises(module.PilotMetadataError):_assess(plan,body)


def test_purged_and_embargoed_security_context_is_retained_with_named_exclusions(plan):
    for entry,reason in (("2023-12-15","purged_label_crosses_next_phase"),("2024-01-15","embargo_first60_phase_sessions")):
        result=_assess(plan,_entry(plan,entry=entry)).to_payload()
        assert result["metadata_disposition"]=="EXCLUDED_METADATA" and reason in result["exclusion_reasons"]
        assert result["source_row_must_remain_in_accounting"] is True


def test_context_root_and_plan_type_are_external_boundaries(plan):
    body=_entry(plan);raw=module._raw(body)
    with pytest.raises(module.PilotMetadataError):module.assess_entry_context(plan=plan,metadata_raw=raw,expected_metadata_sha256="0"*64)
    with pytest.raises(module.PilotMetadataError):module.assess_entry_context(plan=plan.to_payload(),metadata_raw=raw,expected_metadata_sha256=hash_bytes(raw))
    result=_assess(plan,body)
    with pytest.raises(module.PilotMetadataError):module.assess_entry_context(plan=result,metadata_raw=raw,expected_metadata_sha256=hash_bytes(raw))


@pytest.mark.parametrize("field",["listing","context","interval"])
def test_last_second_prerequisite_is_too_late_for_frozen_two_minute_moo_cutoff(plan,field):
    body=_entry(plan);opened=next(row["open_utc"] for row in plan.to_payload()["calendar_sessions"]
        if row["session"]==body["entry_session"])
    late=(datetime.fromisoformat(opened.replace("Z","+00:00"))-timedelta(seconds=1)).isoformat().replace("+00:00","Z")
    if field=="listing":body["listing_known_at_utc"]=late
    elif field=="context":body["context_known_at_utc"]=late
    else:body["open_intervals"][-1]["knowledge_at_utc"]=late
    with pytest.raises(module.PilotMetadataError):_assess(plan,body)


@pytest.mark.parametrize("field",["listing","context","interval"])
def test_exact_two_minute_moo_cutoff_is_inclusive_positive_control(plan,field):
    body=_entry(plan);opened=next(row["open_utc"] for row in plan.to_payload()["calendar_sessions"]
        if row["session"]==body["entry_session"])
    cutoff=(datetime.fromisoformat(opened.replace("Z","+00:00"))-timedelta(minutes=2)).isoformat().replace("+00:00","Z")
    if field=="listing":body["listing_known_at_utc"]=cutoff
    elif field=="context":body["context_known_at_utc"]=cutoff
    else:body["open_intervals"][-1]["knowledge_at_utc"]=cutoff
    assert _assess(plan,body).to_payload()["metadata_disposition"]=="CONTEXT_METADATA_COMPLETE"


def test_business_io_network_credential_or_qc_entry_points_are_absent():
    source=Path(module.__file__).read_text();tree=ast.parse(source)
    forbidden={"os","pathlib","subprocess","socket","urllib","requests","keyring","quantconnect","AlgorithmImports"}
    imported={node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module}
    imported|={item.name.split(".")[0] for node in ast.walk(tree) if isinstance(node,ast.Import) for item in node.names}
    assert not imported&forbidden
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {"open","exec","eval","__import__"}
        for node in ast.walk(tree))
