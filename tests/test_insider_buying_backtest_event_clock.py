"""Invented content controls only; no market/outcome data or authority."""
import json
from copy import deepcopy
from datetime import datetime, timezone, timedelta

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying import backtest_event_clock as m
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture


def enc(value):
    return canonical_json(value).encode("utf-8")


def clock_args(instant="2023-01-13T13:00:00Z"):
    raw = make_pipeline_fixture()["calendar"]
    return dict(available_at_utc=instant, calendar_raw=raw, calendar_sha256=hash_bytes(raw), trust_scope="fixture")


@pytest.mark.parametrize("available,entry", [
    ("2023-01-13T13:00:00Z", "2023-01-13"),
    ("2023-01-13T14:30:00Z", "2023-01-16"),
    ("2023-01-13T15:00:00Z", "2023-01-16"),
    ("2023-01-13T22:00:00Z", "2023-01-16"),
    ("2023-01-14T15:00:00Z", "2023-01-16"),
])
def test_literal_first_open_not_daily_close_delay(available, entry):
    result = m.schedule_first_open(**clock_args(available))
    assert result["entry_session"] == entry
    assert result["literal_first_open_after_acceptance"] is True
    assert result["research_looks"] == result["qc_jobs"] == 0
    cal = json.loads(clock_args()["calendar_raw"])["sessions"]
    i = [r["session"] for r in cal].index(entry)
    assert result["exit_opens"]["20"]["session"] == cal[i + 20]["session"]


@pytest.mark.parametrize("instant", ["2023-01-13", "2023-01-13T13:00:00", "2023-01-13T13:00:00+00:00", "2023-01-13T13:00:00.123Z", "2023-13-13T13:00:00Z"])
def test_imprecise_invalid_timing_refused(instant):
    with pytest.raises(ValueError):
        m.schedule_first_open(**clock_args(instant))


def test_equal_open_guard_and_complete_horizon():
    args = clock_args("2023-05-01T13:00:00Z")
    with pytest.raises(ValueError, match="horizons"):
        m.schedule_first_open(**args)
    args = clock_args("2022-11-28T12:00:00Z")
    with pytest.raises(ValueError, match="context"):
        m.schedule_first_open(**args)


def classification_args(title="Ordinary Shares"):
    mapping = {"issuer_cik": "0000123456", "qc_symbol_id": "SID0", "security_title": title,
               "share_class": "ordinary-A", "security_class": "common_stock", "country": "US", "venue": "XNAS",
               "mapping_first_session": "2022-01-01", "mapping_last_session": "2024-01-01", "knowledge_at_utc": "2022-01-01T00:00:00Z"}
    exception = {k: mapping[k] for k in ("issuer_cik", "qc_symbol_id", "security_title", "share_class", "security_class", "knowledge_at_utc")}
    exception.update(first_session="2022-01-01", last_session="2024-01-01")
    raw = enc({"schema": "insider-common-equity-exceptions-v2", "trust_scope": "fixture", "exceptions": [exception]})
    return dict(transaction={"event_id": "e" * 64, "issuer_cik": mapping["issuer_cik"], "security_title_raw": title,
                             "transaction_date": "2023-01-12", "outcomes": ["exclude_non_common_stock"]},
                mapping=mapping, exception_dictionary_raw=raw, exception_dictionary_sha256=hash_bytes(raw), trust_scope="fixture",
                available_at_utc="2023-01-13T15:00:00Z")


@pytest.mark.parametrize("title", ["Ordinary Shares", "Class A Ordinary Shares", "Common Shares", "Class B Common Shares"])
def test_exact_pit_ordinary_share_exception_only(title):
    result = m.classify_pit_common_equity(**classification_args(title))
    assert result["eligible_for_lot_aggregation"] is True
    assert result["ordinary_share_exception_applied"] is True
    assert result["original_outcomes"] == ["exclude_non_common_stock"]


@pytest.mark.parametrize("reason", ["exclude_sale", "exclude_derivative", "exclude_price_range", "exclude_indirect_ownership", "exclude_multiple_reporting_owners", "exclude_amended_filing"])
def test_exception_cannot_clear_another_economic_filter(reason):
    args = classification_args()
    args["transaction"]["outcomes"].append(reason)
    result = m.classify_pit_common_equity(**args)
    assert result["eligible_for_lot_aggregation"] is False
    assert result["ordinary_share_exception_applied"] is False


@pytest.mark.parametrize("title", ["Restricted Ordinary Shares", "Preferred Shares", "ADR Ordinary Shares", "Phantom Units", "Ordinary Shares RSU"])
def test_manual_dictionary_cannot_promote_forbidden_titles(title):
    with pytest.raises(ValueError, match="title"):
        m.classify_pit_common_equity(**classification_args(title))


def test_claimed_provisional_eligibility_cannot_promote_a_restricted_title():
    args = classification_args("Restricted Stock Units")
    args["transaction"]["outcomes"] = ["eligible_for_lot_aggregation"]
    args["exception_dictionary_raw"] = enc({"schema": "insider-common-equity-exceptions-v2", "trust_scope": "fixture", "exceptions": []})
    args["exception_dictionary_sha256"] = hash_bytes(args["exception_dictionary_raw"])
    assert m.classify_pit_common_equity(**args)["eligible_for_lot_aggregation"] is False


@pytest.mark.parametrize("field,value", [("knowledge_at_utc", "2023-01-14T00:00:00Z"), ("first_session", "2023-01-13"), ("qc_symbol_id", "OTHER"), ("share_class", "ordinary-B")])
def test_future_wrong_exception_refused(field, value):
    args = classification_args()
    body = json.loads(args["exception_dictionary_raw"])
    body["exceptions"][0][field] = value
    args.update(exception_dictionary_raw=enc(body), exception_dictionary_sha256=hash_bytes(enc(body)))
    with pytest.raises(ValueError, match="unique PIT"):
        m.classify_pit_common_equity(**args)


def context_args():
    fixture = make_pipeline_fixture()
    calendar = fixture["calendar"]
    days = json.loads(calendar)["sessions"]
    index = 70
    body = {"schema": "insider-stock-context-v2", "trust_scope": "fixture", "calendar_sha256": hash_bytes(calendar),
            "decision_session": days[index]["session"], "rows": [{"qc_symbol_id": sid, "history": [
                {"session": day["session"], "raw_close_usd": "5", "volume_shares": "400000", "knowledge_at_utc": day["close_utc"]}
                for day in days[index - 60:index]]} for sid in ("SID0", "SID1")]}
    raw = enc(body)
    return dict(context_raw=raw, context_sha256=hash_bytes(raw), trust_scope="fixture", calendar_raw=calendar,
                calendar_sha256=hash_bytes(calendar), decision_session=body["decision_session"], decision_cutoff_utc=days[index]["open_utc"],
                expected_security_ids=("SID0", "SID1"))


def edit_context(args, edit):
    body = json.loads(args["context_raw"])
    edit(body)
    raw = enc(body)
    return {**args, "context_raw": raw, "context_sha256": hash_bytes(raw)}


def test_complete_context_includes_no_filing_stocks_exact_thresholds():
    result = m.verify_pit_stock_context(**context_args())
    assert len(result["rows"]) == 2
    assert all(r["eligible"] for r in result["rows"])
    assert result["rows"][0]["adv20_usd"] == "2000000"


def test_liquidity_exclusion_is_named_not_missing_as_zero():
    args = edit_context(context_args(), lambda b: b["rows"][1]["history"][-1].update(raw_close_usd="4.99"))
    result = m.verify_pit_stock_context(**args)
    assert result["rows"][0]["eligible"] is True
    assert result["rows"][1]["eligible"] is False
    assert len(result["rows"][1]["exclusion_reasons"]) == 2


@pytest.mark.parametrize("edit", [
    lambda b: b["rows"].pop(),
    lambda b: b["rows"].reverse(),
    lambda b: b["rows"][0]["history"].pop(),
    lambda b: b["rows"][0]["history"].reverse(),
    lambda b: b["rows"][0]["history"][0].update(knowledge_at_utc="2024-01-01T00:00:00Z"),
    lambda b: b["rows"][0]["history"][0].update(knowledge_at_utc="2020-01-01T00:00:00Z"),
    lambda b: b["rows"][0]["history"][0].update(raw_close_usd="NaN"),
    lambda b: b["rows"][0]["history"][0].update(volume_shares=True),
    lambda b: b.update(calendar_sha256="0" * 64),
    lambda b: b.update(decision_session="2023-02-24"),
    lambda b: b.update(readiness=True),
])
def test_context_missing_corrupt_future_unknown_refused(edit):
    with pytest.raises(ValueError):
        m.verify_pit_stock_context(**edit_context(context_args(), edit))


def test_external_roots_scope_and_duplicate_json_are_not_self_authenticating():
    args = context_args()
    with pytest.raises(ValueError, match="root"):
        m.verify_pit_stock_context(**{**args, "context_sha256": "0" * 64})
    with pytest.raises(ValueError, match="scope"):
        m.verify_pit_stock_context(**{**args, "trust_scope": "production"})
    body = args["context_raw"][:-1] + b',"schema":"insider-stock-context-v2"}'
    with pytest.raises(ValueError, match="duplicate"):
        m.verify_pit_stock_context(**{**args, "context_raw": body, "context_sha256": hash_bytes(body)})


def test_mutation_inputs_do_not_mutate_returned_context():
    args = context_args()
    one = m.verify_pit_stock_context(**args)
    one["rows"][0]["eligible"] = False
    assert m.verify_pit_stock_context(**args)["rows"][0]["eligible"] is True


def listing_evidence(sid, first, *, knowledge="2022-01-01T00:00:00Z", published="2021-12-01T00:00:00Z"):
    invented_record = enc({"qc_symbol_id": sid, "first_listing_session": first, "complete_first_listing_history": True})
    return {"schema": "insider-pit-first-listing-evidence-v1", "trust_scope": "fixture", "qc_symbol_id": sid,
        "country": "US", "venue": "XNAS", "security_class": "common_stock", "first_listing_session": first,
        "source_authority": "invented-first-listing-record", "source_document_sha256": hash_bytes(b"invented-notice:"+invented_record),
        "source_record_id": "invented-listing:"+sid, "source_record_sha256": hash_bytes(invented_record),
        "source_vintage_sha256": hash_bytes(b"invented-preoutcome-listing-vintage"),
        "source_publication_utc": published, "knowledge_at_utc": knowledge, "listing_history_complete": True,
        "predecessor_listing_status": "verified-no-predecessor-listing"}


def context_v3_args(history_sessions=19):
    args = context_args(); body=json.loads(args["context_raw"]); days=json.loads(args["calendar_raw"])["sessions"]
    index=next(n for n,row in enumerate(days) if row["session"]==args["decision_session"])
    body["schema"]="insider-stock-context-v3"
    for offset, row in enumerate(body["rows"]):
        count=history_sessions if offset else 60
        first=days[index-count]["session"] if count<=index else "2020-01-01"
        evidence=listing_evidence(row["qc_symbol_id"],first)
        row["history"]=row["history"][-count:] if count else []
        row.update(first_listing_evidence=evidence,first_listing_evidence_sha256=hash_bytes(enc(evidence)))
    raw=enc(body)
    return {**args,"context_raw":raw,"context_sha256":hash_bytes(raw)}


def edit_listing(args, edit):
    def change(body):
        evidence=body["rows"][1]["first_listing_evidence"]; edit(evidence)
        body["rows"][1]["first_listing_evidence_sha256"]=hash_bytes(enc(evidence))
    return edit_context(args,change)


@pytest.mark.parametrize("count",[0,19,59,60])
def test_v3_genuine_first_listing_history_is_complete_and_young_exclusion_is_not_missing_zero(count):
    result=m.verify_pit_stock_context_v3(**context_v3_args(count)); mature,young=result["rows"]
    assert mature["eligible"] is True
    assert young["history_sessions"]==count and young["eligible"]==(count==60)
    assert young["exclusion_reasons"]==([] if count==60 else ["insufficient_60_session_history"])
    assert young["price_usd"]==("5" if count else None)
    assert young["adv20_usd"]==("2000000" if count>=20 else None)
    assert result["first_listing_provenance_authenticated_here"] is result["source_authenticated_here"] is result["look_authority"] is False
    assert result["qc_jobs"]==result["research_looks"]==0


def test_v2_still_refuses_short_history_without_a_new_first_listing_contract():
    args=edit_context(context_args(),lambda body:body["rows"][1].update(history=body["rows"][1]["history"][-19:]))
    with pytest.raises(m.EventClockError,match="history count"):
        m.verify_pit_stock_context(**args)


@pytest.mark.parametrize("count",[19,59,60])
@pytest.mark.parametrize("change",["missing","reordered","extra","duplicate"])
def test_v3_never_excludes_missing_or_corrupt_actual_history_as_if_it_were_young(count,change):
    def edit(body):
        history=body["rows"][1]["history"]
        if change=="missing":history.pop()
        elif change=="reordered":history.reverse()
        elif change=="extra":history.append(history[-1])
        else:history[-1]=history[-2]
    with pytest.raises(m.EventClockError): m.verify_pit_stock_context_v3(**edit_context(context_v3_args(count),edit))


@pytest.mark.parametrize("field,value",[
    ("listing_history_complete",False),("listing_history_complete",1),("listing_history_complete","true"),
    ("predecessor_listing_status","unknown"),("predecessor_listing_status","previous-listing-not-reviewed"),
    ("source_document_sha256",""),("source_record_sha256","not-a-digest"),("source_vintage_sha256",True),
    ("source_record_id","bad\nrecord"),("source_record_id"," "),("source_record_id","x"*129),
    ("source_authority","mapping-first-interval-inference"),("source_authority","official-exchange-first-listing-record"),
    ("country","CA"),("venue","OTC"),("security_class","preferred_stock"),("security_class","ADR"),
    ("qc_symbol_id","OTHER"),("trust_scope","production"),("schema","unknown-first-listing-proof"),
    ("first_listing_session","2025-01-01"),("first_listing_session",True),
    ("source_publication_utc","2025-01-01T00:00:00Z"),
])
def test_v3_reanchored_false_incomplete_unproven_or_nonordinary_listing_evidence_refuses(field,value):
    with pytest.raises(ValueError): m.verify_pit_stock_context_v3(**edit_listing(context_v3_args(19),lambda e:e.update({field:value})))


@pytest.mark.parametrize("offset",[0,1])
def test_v3_listing_knowledge_simultaneous_with_or_after_cutoff_refuses(offset):
    args=context_v3_args(19); cutoff=m._utc(args["decision_cutoff_utc"])+timedelta(seconds=offset)
    args=edit_listing(args,lambda e:e.update(knowledge_at_utc=cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")))
    with pytest.raises(m.EventClockError,match="knowledge"):
        m.verify_pit_stock_context_v3(**args)


def test_v3_old_listing_before_calendar_requires_full_actual_latest_sixty_and_keeps_provenance():
    args=edit_listing(context_v3_args(60),lambda e:e.update(first_listing_session="2000-01-03"))
    result=m.verify_pit_stock_context_v3(**args)
    assert result["rows"][1]["history_sessions"]==60 and result["rows"][1]["first_listing_session"]=="2000-01-03"
    bad=edit_context(args,lambda body:body["rows"][1]["history"].pop())
    with pytest.raises(m.EventClockError,match="history count"):m.verify_pit_stock_context_v3(**bad)


def test_v3_mapping_first_interval_is_not_first_listing_proof_and_row_hash_remains_external():
    def mapping_only(body):
        row=body["rows"][1]; row.pop("first_listing_evidence"); row["mapping_first_session"]=args["decision_session"]
    args=context_v3_args(0)
    with pytest.raises(m.EventClockError):m.verify_pit_stock_context_v3(**edit_context(args,mapping_only))
    bad=edit_context(args,lambda body:body["rows"][1]["first_listing_evidence"].update(source_record_id="changed-without-row-root"))
    with pytest.raises(m.EventClockError,match="pinned row hash"):m.verify_pit_stock_context_v3(**bad)


@pytest.mark.parametrize("edit",[
    lambda body:body["rows"][1]["history"][-1].update(raw_close_usd="4.99"),
    lambda body:body["rows"][1]["history"][-1].update(volume_shares="0"),
])
def test_v3_sixty_session_classification_uses_unchanged_v2_price_volume_boundaries(edit):
    result=m.verify_pit_stock_context_v3(**edit_context(context_v3_args(60),edit))
    assert result["rows"][0]["eligible"] is True and result["rows"][1]["eligible"] is False
    assert "insufficient_60_session_history" not in result["rows"][1]["exclusion_reasons"]


def test_v3_fixture_authority_is_not_accepted_as_production_first_listing_evidence():
    args=context_v3_args(0); body=json.loads(args["context_raw"]); calendar=json.loads(args["calendar_raw"])
    calendar["trust_scope"]="production"; args["calendar_raw"]=enc(calendar); args["calendar_sha256"]=hash_bytes(args["calendar_raw"])
    body.update(trust_scope="production",calendar_sha256=args["calendar_sha256"])
    for row in body["rows"]:
        row["first_listing_evidence"]["trust_scope"]="production"
        row["first_listing_evidence_sha256"]=hash_bytes(enc(row["first_listing_evidence"]))
    args.update(trust_scope="production",context_raw=enc(body),context_sha256=hash_bytes(enc(body)))
    with pytest.raises(m.EventClockError,match="fixture/production profile"):m.verify_pit_stock_context_v3(**args)


# Section 153 (Claude review): two point-in-time guards had no isolating control.
def test_mapping_known_after_public_availability_cannot_classify():
    args = classification_args()
    args["mapping"]["knowledge_at_utc"] = "2023-01-13T15:00:01Z"  # one second after availability
    with pytest.raises(m.EventClockError, match="mapping unavailable"):
        m.classify_pit_common_equity(**args)


def test_v3_history_bar_knowledge_simultaneous_with_cutoff_refuses():
    args = context_v3_args(60)
    cutoff = args["decision_cutoff_utc"]
    with pytest.raises(m.EventClockError, match="simultaneous or future"):
        m.verify_pit_stock_context_v3(**edit_context(args, lambda b: b["rows"][1]["history"][-1].update(knowledge_at_utc=cutoff)))
