"""Synthetic projections only; no real retained page/index or private opener."""
import ast
from copy import deepcopy
from datetime import date, datetime, time, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import pytest
from research.target_price_revisions_qc import comparison_20261028_events as e

CAPTURE="2026-10-10T20:00:00Z"
WINDOW=["2020-12-01","2020-12-31"]


def rating(event="E1",firm="F1",day="2020-12-29",**changes):
    return {"benzinga_id":event,"benzinga_firm_id":firm,"ticker":"A","date":day,
        "last_updated":day+"T12:00:00Z","currency":"USD","price_target_action":"raises",
        "price_target":"11","previous_price_target":"10",**changes}


def wrapped(source,*,conflict=False):
    reasons=[]
    if not e.raw_revision._native_id(source["benzinga_id"]) or not e.raw_revision._native_id(source["benzinga_firm_id"]):
        reasons.append("invalid_native_id")
    if not e.raw_revision._ticker(source["ticker"]):reasons.append("invalid_native_ticker")
    try:
        touched=e.raw_revision._utc(source["last_updated"])
        if touched.date()<date.fromisoformat(source["date"]) or touched>e.raw_revision._utc(CAPTURE):reasons.append("invalid_native_touch_order")
    except e.raw_revision.RawRevisionError:reasons.append("invalid_native_touch_clock")
    if conflict:reasons.append("conflicting_native_event_id")
    nominal=e._capture_nominal(source["price_target"]) and e._capture_nominal(source["previous_price_target"])
    return {"source":source,"refusals":reasons,"nominal_disposition":"nominal_pair_present" if nominal else "nominal_pair_unavailable"}


def page(rows,*,window=WINDOW,duplicates=0):
    rows=[row if "source" in row else wrapped(row) for row in rows]
    return {"schema":"tpr-extended-massive-native-page-v1","window":list(window),"rows":rows,
        "source_rows":len(rows),"row_refusals":sum(bool(row["refusals"]) for row in rows),
        "identical_duplicate_rows":duplicates,"conflicting_duplicate_rows":sum("conflicting_native_event_id" in row["refusals"] for row in rows)}


def arguments(body,*,request=1,window=WINDOW):
    payload=e.canonical(body);digest=hashlib.sha256(payload).hexdigest()
    descriptor={"request_index":request,"page":0,"name":f"request.{request:04}.projection.json",
        "bytes":len(payload),"sha256":digest,"fetch_utc":CAPTURE,"row_count":None}
    return dict(payload=payload,expected_sha256=digest,expected_bytes=len(payload),window=list(window),descriptor=descriptor)


def project(rows,**kwargs):
    return e.project_page(**arguments(page(rows,**kwargs),window=kwargs.get("window",WINDOW)))


@pytest.fixture(scope="module")
def sessions():
    calendar=json.loads(Path("research/target_price_revisions_qc/extended_calendar.json").read_bytes())
    return [{"session_date":day,"open_utc":datetime.combine(date.fromisoformat(day),time(9,30),
        ZoneInfo("America/New_York")).isoformat()} for day in calendar["warmup_sessions"]+calendar["valuation_sessions"]]


def score(events,sessions,*,decision="2021-01-04",bound=True,inventory=("NATIVE-A",),**kwargs):
    days=[row["session_date"] for row in sessions];index=days.index(decision)
    cutoff=datetime.combine(date.fromisoformat(days[index-1]),time(18),ZoneInfo("America/New_York")).isoformat()
    return e.score_bound_events(events,sessions=sessions,decision_session=decision,cutoff_utc=kwargs.pop("cutoff_utc",cutoff),
        security_id_by_event=kwargs.pop("security_id_by_event",{row["event_key"]:"NATIVE-A" for row in events} if bound else {}),
        security_ids=inventory,**kwargs)


def test_exact_projection_derives_ratio_and_measured_zero_without_target_prices_or_early_identity_binding():
    result=project([rating(),rating("E2",price_target="10",price_target_action="maintains"),rating("E3",price_target="100")])
    assert [row["contribution"] for row in result["events"]]==[
        {"numerator":"1","denominator":"10"},{"numerator":"0","denominator":"1"},{"numerator":"1","denominator":"1"}]
    assert result["events"][-1]["contribution_was_clipped"] is True
    assert result["census"]["derived_rows"]==result["census"]["unbound_identity_rows"]==3
    wire=e.canonical(result)
    assert b'"price_target"' not in wire and b'"previous_price_target"' not in wire and b'"company"' not in wire
    assert all(row["historical_identity_proven"] is False and row["raw_share_basis_unproven"] is True for row in result["events"])
    assert result["source_inputs_admitted"] is result["point_in_time_data"] is False


@pytest.mark.parametrize("new,prior,action,expected",[("9","10","lowers",Fraction(-1,10)),("0.00000001","1000000","lowers",Fraction("-0.99999999999999")),
    (11,10,"raises",Fraction(1,10)),("10.000000000000000001","10","raises",Fraction(1,10**19))])
def test_exact_represented_numbers_never_round_through_float(new,prior,action,expected):
    event=project([rating(price_target=new,previous_price_target=prior,price_target_action=action)])["events"][0]
    assert e._ratio(event["contribution"])==expected


@pytest.mark.parametrize("changes,reason",[({"price_target":None},"invalid_positive_target"),({"price_target":True},"invalid_positive_target"),
    ({"price_target":"1e2"},"invalid_positive_target"),({"price_target":"0"},"invalid_positive_target"),
    ({"price_target":"-1"},"invalid_positive_target"),({"price_target":"9"*65},"target_resource_bound"),
    ({"currency":"EUR"},"unsupported_currency"),({"price_target_action":"sets"},"initiation_not_revision"),
    ({"price_target_action":"withdraws"},"withdrawal_not_revision"),({"price_target_action":"raises","price_target":"9"},"action_direction_conflict"),
    ({"benzinga_firm_id":None},"invalid_firm_id"),({"benzinga_id":None},"invalid_native_event_id"),
    ({"ticker":"bad ticker"},"invalid_rating_ticker"),({"last_updated":"invalid"},"invalid_touch_clock"),
    ({"last_updated":"2020-01-01T00:00:00Z"},"touch_precedes_issue_date"),({"last_updated":"2026-10-11T00:00:00Z"},"touch_after_capture")])
def test_every_unknown_row_is_preserved_with_null_contribution_and_full_reason(changes,reason):
    result=project([rating(**changes)])
    row=result["events"][0]
    assert row["state"]=="unavailable" and row["contribution"] is None and reason in row["refusals"]
    assert result["census"]["source_rows"]==result["census"]["unavailable_rows"]==1
    assert result["census"]["refusal_counts"][reason]==1


def test_hash_and_byte_descriptor_gate_precedes_any_json_parse(monkeypatch):
    args=arguments(page([rating()]))
    monkeypatch.setattr(e,"_json",lambda *_:pytest.fail("hash refusal must precede parse"))
    for change in ({"expected_sha256":"a"*64},{"expected_bytes":len(args["payload"])+1}, {"payload":bytearray(args["payload"])}):
        with pytest.raises(e.EventBridgeError):e.project_page(**{**args,**change})


@pytest.mark.parametrize("field,value",[("name","../../private.json"),("request_index",0),("request_index",True),("page",64),("bytes",True),
    ("sha256","a"*64),("fetch_utc","2026-10-10T20:00:00"),("row_count",2)])
def test_descriptor_is_exact_bounded_inventory_metadata_without_path_opener(field,value):
    args=arguments(page([rating()]));args["descriptor"][field]=value
    with pytest.raises(e.EventBridgeError):e.project_page(**args)


@pytest.mark.parametrize("mode",["unknown_page","unknown_row","unknown_source","rows_count","refusal_count","false_nominal","forged_refusal","future_window","sorting","over_rows"])
def test_closed_projection_wrapper_and_producer_counts_are_verified(mode):
    body=page([rating()])
    if mode=="unknown_page":body["secret"]="SYNTHETIC-PRIVATE-SENTINEL"
    elif mode=="unknown_row":body["rows"][0]["company"]="SYNTHETIC-PRIVATE-SENTINEL"
    elif mode=="unknown_source":body["rows"][0]["source"]["company"]="SYNTHETIC-PRIVATE-SENTINEL"
    elif mode=="rows_count":body["source_rows"]=2
    elif mode=="refusal_count":body["row_refusals"]=1
    elif mode=="false_nominal":body["rows"][0]["nominal_disposition"]="nominal_pair_unavailable"
    elif mode=="forged_refusal":body["rows"][0]["refusals"]=["invalid_native_ticker"];body["row_refusals"]=1
    elif mode=="future_window":body["rows"][0]["source"]["date"]="2021-01-01"
    elif mode=="sorting":body=page([rating(day="2020-12-30"),rating("E2",day="2020-12-29")])
    else:body=page([rating()]*1001)
    with pytest.raises(e.EventBridgeError) as caught:e.project_page(**arguments(body))
    assert "SYNTHETIC-PRIVATE-SENTINEL" not in str(caught.value)


@pytest.mark.parametrize("payload",[b"{",b"null",b"[]",b'{"x":NaN}',b'{"x":1.1}',b'{"x":1,"x":2}',b'\xff'])
def test_duplicate_nonfinite_float_or_malformed_json_body_fails_closed(payload):
    args=arguments(page([]));args.update(payload=payload,expected_bytes=len(payload),expected_sha256=hashlib.sha256(payload).hexdigest())
    args["descriptor"].update(bytes=len(payload),sha256=args["expected_sha256"])
    with pytest.raises(e.EventBridgeError):e.project_page(**args)


def test_first_frame_matches_known_second_later_open_firm_session_median_and_firm_median(sessions):
    result=project([rating("E1",price_target="11"),rating("E2",price_target="13"),
        rating("E3",firm="F2",price_target="18")])
    report=score(result["events"],sessions)
    # All were issuedTue29; second later openThu31; prior cutoffThu31, age0.
    # F1 median(.1,.3)=.2; F2=.8; median firms=.5.
    assert Decimal(report["scores_by_sid"]["NATIVE-A"]["value"])==Decimal("0.5")
    assert report["census"]["dispositions"]["accepted_distinct_events"]==3
    assert report["historical_identity_proven"] is report["native_share_basis_proven"] is False


def test_update_censorship_prevents_later_touched_current_vintage_from_entering_past_score(sessions):
    result=project([rating(last_updated="2025-01-01T12:00:00Z")])
    report=score(result["events"],sessions)
    assert report["scores_by_sid"]["NATIVE-A"]=={"state":"unknown","value":None}
    assert report["census"]["dispositions"]["later_touch_censored"]==1


def test_second_later_open_is_not_one_business_day_or_preopen_permission(sessions):
    rows=project([rating(day="2020-12-30")])["events"]
    first=score(rows,sessions)
    # Wed30 -> Thu31 first later open, Mon04 second; Mon09:20 cannot use an
    # event that only becomes eligible at Mon09:30 after its Thu18:00 cutoff.
    assert first["scores_by_sid"]["NATIVE-A"]["value"] is None
    assert first["census"]["dispositions"]["not_yet_eligible"]==1
    later=score(rows,sessions,decision="2021-01-05")
    assert Decimal(later["scores_by_sid"]["NATIVE-A"]["value"])==Decimal("0.1")


def test_typed_native_ids_do_not_collide_and_identical_duplicates_contribute_once(sessions):
    rows=project([rating(1,firm=1),rating("1",firm="1",price_target="13"),rating(1,firm=1)],duplicates=1)["events"]
    report=score(rows,sessions)
    assert report["census"]["event_groups"]==2 and report["census"]["identical_duplicate_rows"]==1
    assert Decimal(report["scores_by_sid"]["NATIVE-A"]["value"])==Decimal("0.2")


def test_conflicts_across_pages_and_different_issued_years_invalidate_every_variant_not_only_last(sessions):
    first=project([rating()])["events"]
    second_args=arguments(page([wrapped(rating(day="2025-01-02",price_target="12"),conflict=True)],
        window=["2025-01-01","2025-01-31"]),request=2,window=["2025-01-01","2025-01-31"])
    second=e.project_page(**second_args)["events"]
    report=score(first+second,sessions)
    assert report["scores_by_sid"]["NATIVE-A"]["value"] is None
    assert report["census"]["conflicting_event_groups"]==1
    assert report["census"]["dispositions"]["conflicting_native_event_id"]==2


def test_unbound_identity_and_no_source_rows_remain_unknown_not_measured_zero(sessions):
    rows=project([rating()])["events"]
    report=score(rows,sessions,bound=False,inventory=("NATIVE-A","NATIVE-B"))
    assert all(row=={"state":"unknown","value":None} for row in report["scores_by_sid"].values())
    assert report["census"]["dispositions"]["unbound_native_identity"]==1
    zero=score(project([rating(price_target="10",price_target_action="maintains")])["events"],sessions)
    assert zero["scores_by_sid"]["NATIVE-A"]["state"]=="available"
    assert Decimal(zero["scores_by_sid"]["NATIVE-A"]["value"])==0


def test_fixed_twenty_session_half_life_and_eighty_inclusive_age_truncation(sessions):
    rows=project([rating(price_target="20")])["events"]
    days=[row["session_date"] for row in sessions]
    eligible=days.index("2020-12-31")
    for age in (0,20,80):
        report=score(rows,sessions,decision=days[eligible+age+1])
        with localcontext(Context(prec=48,rounding=ROUND_HALF_EVEN)):
            expected=Decimal(2)**(-Decimal(age)/Decimal(20))
        assert Decimal(report["scores_by_sid"]["NATIVE-A"]["value"])==expected
    expired=score(rows,sessions,decision=days[eligible+82])
    assert expired["scores_by_sid"]["NATIVE-A"]=={"state":"missing","value":None}
    assert expired["census"]["dispositions"]["outside_frozen_score_window"]==1


@pytest.mark.parametrize("mode",["wrong_cutoff_clock","wrong_prior_session","wrong_open","foreign_binding","duplicate_sid","event_acceptance","event_float_ratio"])
def test_scoring_requires_exact_clocks_and_closed_derived_values(sessions,mode):
    rows=project([rating()])["events"];axis=deepcopy(sessions);kwargs={}
    if mode=="wrong_cutoff_clock":kwargs["cutoff_utc"]="2020-12-31T22:59:00Z"
    elif mode=="wrong_prior_session":kwargs["cutoff_utc"]="2020-12-30T23:00:00Z"
    elif mode=="wrong_open":axis[0]["open_utc"]="2020-09-01T13:20:00Z"
    elif mode=="foreign_binding":kwargs["security_id_by_event"]={"a"*64:"NATIVE-A"}
    elif mode=="duplicate_sid":kwargs["inventory"]=("NATIVE-A","NATIVE-A")
    elif mode=="event_acceptance":rows[0]["historical_identity_proven"]=True
    else:rows[0]["contribution"]["numerator"]=0.1
    with pytest.raises(e.EventBridgeError):score(rows,axis,**kwargs)


def test_source_calendar_and_input_objects_are_not_mutated_and_context_is_fixed(sessions):
    rows=project([rating()])["events"];before=deepcopy((rows,sessions))
    with localcontext() as context:
        context.prec=2
        result=score(rows,sessions)
    assert (rows,sessions)==before and result==score(rows,sessions)


def test_pure_module_has_no_io_provider_qc_or_current_vintage_identity_filter_calls():
    tree=ast.parse(Path(e.__file__).read_text())
    calls={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    attrs={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
    assert not calls & {"open","eval","exec","compile","__import__"}
    assert not attrs & {"read_bytes","read_text","credential","_identity_map","_identity_reason","normalize_raw_revisions"}
    compile(Path(e.__file__).read_bytes(),"<pure-event-bridge>","exec")


def test_same_native_version_cannot_choose_last_mutated_derived_contribution_or_drop_its_unknown_census(sessions):
    original=project([rating()])["events"][0]
    forged=deepcopy(original);forged["source_ordinal"]=2
    forged["contribution"]={"numerator":"1","denominator":"1"}
    result=score([original,forged],sessions)
    assert result["scores_by_sid"]["NATIVE-A"]=={"state":"unknown","value":None}
    assert result["census"]["dispositions"]["inconsistent_derived_event_metadata"]==2


def test_all_static_refusals_and_unbound_versions_remain_counted(sessions):
    rows=project([rating(benzinga_firm_id=None,currency="EUR",price_target=None)])["events"]
    result=score(rows,sessions,bound=False)
    assert result["census"]["unbound_event_versions"]==1
    assert result["census"]["static_refusal_counts"]=={
        "invalid_firm_id":1,"invalid_positive_target":1,"unsupported_currency":1}


def test_event_row_and_mapping_permutations_do_not_change_signal_output(sessions):
    rows=project([rating("E3",firm="F2",price_target="18"),rating("E1"),rating("E2",price_target="13")])["events"]
    assert score(rows,sessions)==score(list(reversed(rows)),sessions)


@pytest.mark.parametrize("before,after,probe",[
    ('elif touched>cutoff:reason="later_touch_censored"','elif False:reason="later_touch_censored"','update'),
    ('eligible = bisect_right(dates,issued)+1','eligible = bisect_right(dates,issued)','eligibility'),
    ('value = min(Fraction(1), max(Fraction(-1), original))','value = original','clip'),
])
def test_in_memory_temporal_and_arithmetic_mutants_are_killed_without_source_edits(monkeypatch,sessions,before,after,probe):
    source=Path(e.__file__).read_text()
    assert source.count(before)==1
    mutant=ModuleType(e.__name__+"_synthetic_mutant");mutant.__package__=e.__package__
    exec(compile(source.replace(before,after),"<synthetic-events-mutant>","exec"),mutant.__dict__)
    original=e
    with monkeypatch.context() as scoped:
        scoped.setitem(globals(),"e",mutant)
        with pytest.raises((AssertionError,pytest.fail.Exception)):
            if probe=="update":test_update_censorship_prevents_later_touched_current_vintage_from_entering_past_score(sessions)
            elif probe=="eligibility":test_second_later_open_is_not_one_business_day_or_preopen_permission(sessions)
            else:test_exact_projection_derives_ratio_and_measured_zero_without_target_prices_or_early_identity_binding()
    assert e is original


def test_frozen_axis_cannot_drop_a_session_to_change_event_eligibility_or_decay(sessions):
    rows=project([rating()])["events"]
    altered=deepcopy(sessions)
    altered.pop(1)
    with pytest.raises(e.EventBridgeError):score(rows,altered)
    shifted=deepcopy(sessions);shifted[-1]["session_date"]="2026-10-12";shifted[-1]["open_utc"]="2026-10-12T13:30:00Z"
    with pytest.raises(e.EventBridgeError):score(rows,shifted)
