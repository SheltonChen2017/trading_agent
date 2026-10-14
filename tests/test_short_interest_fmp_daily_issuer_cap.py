"""Fabricated full daily inventory/company caps; no captured source input."""
import pytest
from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_daily_active_reference as daily
from test_short_interest_native_daily_active_reference import plan,index,row,BEGIN,END
import research.short_interest_etf.fmp_company_context as context
import research.short_interest_etf.fmp_daily_issuer_cap as module

def reports(frozen,native):
    for ordinal,at in enumerate(frozen.sessions(),1):
        rows=[row(ticker="OLDALIAS" if ordinal==1 else "SYN")] if ordinal<=2 else []
        raw=canonical_json({"status":"OK","results":rows}).encode()
        page=daily.CapturedDailyActiveReferencePage(at,1,daily.first_url(frozen,ordinal),raw,BEGIN,END,200,"application/json")
        yield daily.qualify_daily_active_reference(frozen,ordinal,(page,),native,started_at=BEGIN,retrieved_at=END)

def build():
    frozen=plan(); native=index()
    return module.build_daily_issuer_index(frozen,reports(frozen,native))

@pytest.fixture(scope="module")
def compiled():
    return build()

def company_cap(frozen):
    ticket=frozen.base_context_plan().tickets()[0]
    raw=canonical_json([{"symbol":"SYN","cik":"0000000001","companyName":"Fabricated"}]).encode()
    company=context.qualify_context(ticket,raw=raw,raw_sha256=hash_bytes(raw),
        request_sha256=hash_payload(context.request_descriptor(ticket,"lookup")),started_at=BEGIN,received_at=END)
    raw=b'[{"symbol":"SYN","date":"2022-01-03","marketCap":9.25},{"symbol":"SYN","date":"2022-01-04","marketCap":10}]'
    return context.qualify_company_cap(company,raw=raw,raw_sha256=hash_bytes(raw),
        request_sha256=hash_payload(context.request_descriptor(ticket,"cap")),started_at=END,received_at=END)

def test_latest_dated_target_not_current_or_primary_class_guess(compiled):
    assert compiled.selected()==(("0000000001",2,"SYN","BBG000000002","sharadar:permaticker:1",1,0),)
    assert [item[5] for item in compiled.iter_cik_rows("1")]==["OLDALIAS","SYN"]
    assert compiled.header()["cell_count"]==2 and len(compiled.header()["source_days"])==1169

def test_explicit_new_three_GiB_claim_and_no_old_runtime_authority(compiled):
    value=module.freeze_indexed_company_plan(compiled).to_payload()
    assert value["maximum_requests"]==2 and value["maximum_total_bytes"]==3*1024**3
    assert value["old_runtime_cannot_use_this_type_or_budget"] is True
    assert value["authority"]["market_cap_admitted"] is False

def test_old_alias_CIK_does_not_invent_same_date_target_USD(compiled):
    cap=company_cap(module.freeze_indexed_company_plan(compiled))
    rows=list(module.iter_indexed_company_cap_bindings(compiled,cap))
    assert rows[0]["status"]=="refused"
    assert rows[0]["refusal_reasons"]==["same_date_request_target_USD_not_independently_observed"]
    assert rows[1]["status"]=="dated_issuer_USD_cap_source_candidate"
    assert all(item["same_class_shares"] is None and item["authority"]["qc_attempts"]==0 for item in rows)

def test_partial_inventory_cannot_be_complete():
    frozen=plan(); native=index()
    with pytest.raises(context.FmpContextError,match="all_1169"):
        module.build_daily_issuer_index(frozen,iter([next(reports(frozen,native))]))

def test_per_row_budget_never_scans_all_companies_dictionary(monkeypatch):
    scans=[]
    monkeypatch.setattr(module,"sum",lambda values: scans.append(True) or sum(values),raising=False)
    build()
    assert scans==[]

def test_each_indexed_yield_guard_without_source_rehash():
    separate=build(); stream=separate.iter_cik_rows("1"); next(stream)
    object.__setattr__(separate,"_cells",b"")
    with pytest.raises(context.FmpContextError,match="sealed_daily_issuer"):
        next(stream)

def test_budget_exhaustion_refuses_not_truncates(monkeypatch):
    monkeypatch.setattr(module,"MAXIMUM_INDEX_BYTES",1)
    with pytest.raises(context.FmpContextError,match="bounded_compact"):
        build()
