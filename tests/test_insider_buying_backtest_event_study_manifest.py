"""Original-source causal manifest engineering fixtures; no real-data access."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import weakref
from zoneinfo import ZoneInfo

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying import backtest_event_study_manifest as module
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying.backtest_source_stream import build_stream_source_evidence
from test_insider_buying_backtest_source_stream import make_stream_fixture, _record, _specs, _edit_manifest
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture
from test_insider_buying_backtest_registered_analysis import fixture as analysis_fixture


def enc(value):
    return canonical_json(value).encode("utf-8")


def reference_enc(value):
    return analysis.canonical_bytes(value)


def _reanchor(kwargs):
    result = dict(kwargs)
    result["trust_roots"] = module.EventStudyManifestTrustRoots(
        "fixture", result["source_evidence"].to_payload()["population_manifest_sha256"],
        *(hash_bytes(result[name]) for name in ("security_master", "calendar", "common_equity_exceptions", "entry_reference", "registration")),
        "a" * 64)
    return result


def make_causal_fixture(*, specs=None, raw_changes=None, title="Common Stock"):
    specs = _specs(count=3) if specs is None else specs
    stream, ordered_specs = make_stream_fixture(specs_by_period={"2023Q1": specs}, title=title)
    records = [_record(*item, title=title, raw_change=None if raw_changes is None else raw_changes.get(index))
               for index, item in enumerate(ordered_specs)]
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.entry_bytes + b"\n")
    stream = _edit_manifest(stream, lambda body: body["quarters"][0].update(
        ordered_parent_inventory_sha256=digest.hexdigest()))
    stream["parent_records"] = iter(records)
    evidence = build_stream_source_evidence(**stream)
    old = make_pipeline_fixture()
    master = json.loads(old["security_master"])
    master["mappings"][0]["security_title"] = title
    calendar = {"schema": "insider-backtest-calendar-v1", "trust_scope": "fixture", "sessions": []}
    current, eastern = date(2021, 11, 29), ZoneInfo("America/New_York")
    while len(calendar["sessions"]) < 460:
        if current.weekday() < 5:
            calendar["sessions"].append({"session": current.isoformat(), **{key + "_utc": datetime.combine(current, datetime.min.time()).replace(
                hour=9 if key == "open" else 16, minute=30 if key == "open" else 0, tzinfo=eastern).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                for key in ("open", "close")}})
        current += timedelta(days=1)
    dates = [row["session"] for row in calendar["sessions"]]
    entry_dates = set()
    for fact in evidence.parent_facts():
        available = module.base._utc(fact["accepted_at_utc"])
        entry_dates.add(next(row["session"] for row in calendar["sessions"] if module.base._utc(row["open_utc"]) > available))
    dictionary = {"schema": "insider-common-equity-exceptions-v2", "trust_scope": "fixture", "exceptions": []}
    if title != "Common Stock":
        mapping = master["mappings"][0]
        item = {key: mapping[key] for key in ("issuer_cik", "qc_symbol_id", "security_title", "share_class", "security_class", "knowledge_at_utc")}
        item.update(first_session="2023-01-01", last_session="2024-01-01")
        dictionary["exceptions"].append(item)
    reference = {"schema": "insider-event-entry-pit-reference-v1", "trust_scope": "fixture",
        "calendar_sha256": hash_bytes(enc(calendar)), "security_master_sha256": hash_bytes(enc(master)),
        "event_population_policy": module.EVENT_POPULATION_POLICY,
        "eligible_control_security_ids": [row["qc_symbol_id"] for row in master["mappings"]], "entries": []}
    for entry_day in sorted(entry_dates):
        index = dates.index(entry_day)
        knowledge = calendar["sessions"][index - 1]["close_utc"]
        context = {"schema": "insider-stock-context-v2", "trust_scope": "fixture", "calendar_sha256": hash_bytes(enc(calendar)),
            "decision_session": entry_day, "rows": [{"qc_symbol_id": mapping["qc_symbol_id"], "history": [
                {"session": day["session"], "raw_close_usd": "10", "volume_shares": "200000", "knowledge_at_utc": day["close_utc"]}
                for day in calendar["sessions"][index - 60:index]]} for mapping in master["mappings"]]}
        reference["entries"].append({"entry_session": entry_day, "knowledge_at_utc": knowledge, "regime": "bull",
            "stock_context": context, "stock_context_sha256": hash_bytes(enc(context)), "earnings_rows": [
                {"qc_symbol_id": mapping["qc_symbol_id"], "known_earnings_sessions": [dates[index + 10]],
                 "knowledge_at_utc": knowledge} for mapping in master["mappings"]]})
    registered = analysis_fixture()["registration"]
    registered.update(source_manifest_sha256=stream["population_sha256"], security_master_sha256=hash_bytes(enc(master)),
        calendar_sha256=hash_bytes(analysis.canonical_bytes(calendar["sessions"])),
        policy=analysis.frozen_analysis_policy(), analysis_plan=analysis.analysis_plan_descriptors(implementation_sha256="a" * 64))
    kwargs = dict(source_evidence=evidence, security_master=enc(master), calendar=enc(calendar),
        common_equity_exceptions=enc(dictionary), entry_reference=reference_enc(reference),
        registration=analysis.canonical_bytes(registered), event_first_session="2023-01-03", event_last_session="2023-02-24")
    return _reanchor(kwargs)


def _edit(kwargs, role, edit, *, crossbind=False):
    result = dict(kwargs)
    body = json.loads(kwargs[role])
    edit(body)
    result[role] = reference_enc(body) if role in {"entry_reference", "registration"} else enc(body)
    if crossbind:
        reference = json.loads(result["entry_reference"])
        if role in {"security_master", "calendar"}:
            reference[role + "_sha256"] = hash_bytes(result[role])
            result["entry_reference"] = reference_enc(reference)
        registered = json.loads(result["registration"])
        if role == "security_master":
            registered["security_master_sha256"] = hash_bytes(result[role])
        if role == "calendar":
            registered["calendar_sha256"] = hash_bytes(analysis.canonical_bytes(body["sessions"]))
        result["registration"] = analysis.canonical_bytes(registered)
    return _reanchor(result)


def stream_reference_fixture(kwargs):
    result = dict(kwargs)
    body = json.loads(kwargs["entry_reference"])
    rows = tuple(analysis.canonical_bytes({"schema": "insider-event-entry-pit-reference-record-v2",
        "trust_scope": body["trust_scope"], **entry}) for entry in body["entries"])
    body["schema"] = "insider-event-entry-pit-reference-stream-v2"
    body["entries"] = [{"entry_session": json.loads(raw)["entry_session"], "reference_sha256": hash_bytes(raw),
                        "reference_bytes": len(raw)} for raw in rows]
    result["entry_reference"] = analysis.canonical_bytes(body)
    result["entry_reference_records"] = (module.EntryReferenceRecord(raw) for raw in rows)
    return _reanchor(result), rows


def test_sealed_original_sources_build_genuine_literal_firstopen_analysis_manifest():
    kwargs = make_causal_fixture()
    result = module.build_source_event_study_manifest(**kwargs)
    body = result.to_payload()
    assert body["event_count"] == body["economic_lot_count"] == 1
    assert body["literal_first_open_after_acceptance"] is True and body["daily_close_candidate_backdated"] is False
    assert body["backtesting_ready"] is False and body["research_looks"] == body["qc_jobs"] == body["outcome_rows_read"] == 0
    event = result.events()[0]
    assert event["entry_session"] == "2023-01-16" and event["exit_session"] == "2023-02-13"
    assert event["earnings_distance_sessions"] == 10 and event["buyer_ids"] == ["0000900000"]
    lot = result.event_lineage()[0]["payload"]["lots"][0]
    assert lot["purchase_value_usd"] == "150000" and len(lot["member_event_ids"]) == 3
    assert body["manifest_sha256"] == hash_bytes(result.manifest_bytes())
    checked = analysis.verify_registered_analysis_manifest(registration_raw=kwargs["registration"], manifest_raw=result.manifest_bytes(),
        expected_registration_sha256=hash_bytes(kwargs["registration"]), expected_manifest_sha256=hash_bytes(result.manifest_bytes()),
        expected_implementation_sha256="a" * 64)
    assert checked["canonical_event_clock_verified"] is True


def test_preopen_first_threshold_includes_only_preopen_additions_and_never_late_resets():
    specs = tuple(("4", day, "123456", f"0000123456-23-{i + 1:06d}", stamp) for i, (day, stamp) in enumerate((
        ("2023-01-13", "20230113080000"), ("2023-01-13", "20230113090000"),
        ("2023-01-13", "20230113091500"), ("2023-01-18", "20230118101112"))))
    def change(raw):
        return raw.replace(b"<transactionShares><value>500</value>", b"<transactionShares><value>250</value>").replace(
            b"<transactionDate><value>2023-01-18</value>", b"<transactionDate><value>2023-01-13</value>")
    result = module.build_source_event_study_manifest(**make_causal_fixture(specs=specs, raw_changes=dict.fromkeys(range(4), change)))
    assert result.events()[0]["entry_session"] == "2023-01-13"
    assert result.events()[0]["available_at_utc"] == "2023-01-13T14:15:00Z"
    lot = result.event_lineage()[0]["payload"]["lots"][0]
    assert lot["purchase_value_usd"] == "75000" and len(lot["member_event_ids"]) == 3
    assert lot["first_threshold_at_utc"] == "2023-01-13T14:00:00Z"
    assert result.to_payload()["late_members_not_reset_or_retraded"] == 1 and result.to_payload()["event_count"] == 1


def test_later_amendment_does_not_rewrite_earlier_emitted_event():
    specs = (("4", "2023-01-13", "123456", "0000123456-23-000001", "20230113080000"),
             ("4/A", "2023-01-20", "123456", "0000123456-23-000002", "20230120101112"))
    result = module.build_source_event_study_manifest(**make_causal_fixture(specs=specs))
    assert result.events()[0]["entry_session"] == "2023-01-13"
    assert result.to_payload()["event_count"] == 1
    assert result.to_payload()["excluded_reason_counts"]["known_amendment_identity_retained_eligibility_not_evaluated"] == 1


def test_already_public_preentry_amendment_excludes_pending_issuer_without_empty_ready_manifest():
    specs = (("4", "2023-01-13", "123456", "0000123456-23-000001", "20230113080000"),
             ("4/A", "2023-01-13", "123456", "0000123456-23-000002", "20230113090000"))
    with pytest.raises(module.EventStudyManifestError, match="nonempty"):
        module.build_source_event_study_manifest(**make_causal_fixture(specs=specs))


def test_ordinary_share_mapping_and_manual_dictionary_applies_without_original_parser_thaw():
    result = module.build_source_event_study_manifest(**make_causal_fixture(title="Ordinary Shares"))
    assert result.to_payload()["ordinary_share_exception_count"] == 3 and len(result.events()) == 1


@pytest.mark.parametrize("role", ["security_master", "calendar", "common_equity_exceptions", "entry_reference", "registration"])
def test_every_external_role_rejects_unanchored_bytes(role):
    kwargs = make_causal_fixture()
    with pytest.raises(ValueError):
        module.build_source_event_study_manifest(**{**kwargs, role: kwargs[role] + b" "})


@pytest.mark.parametrize("role,edit", [
    ("entry_reference", lambda body: body.update(event_population_policy="daily-close")),
    ("entry_reference", lambda body: body.update(eligible_control_security_ids=["SID01", "SID02"])),
    ("entry_reference", lambda body: body["entries"].clear()),
    ("entry_reference", lambda body: body["entries"][0].update(knowledge_at_utc="2023-01-16T14:30:00Z")),
    ("entry_reference", lambda body: body["entries"][0].update(regime="unknown")),
    ("entry_reference", lambda body: body["entries"][0]["earnings_rows"].pop()),
    ("entry_reference", lambda body: body["entries"][0]["earnings_rows"][0].update(known_earnings_sessions=[])),
    ("entry_reference", lambda body: body["entries"][0]["earnings_rows"][0].update(knowledge_at_utc="2024-01-01T00:00:00Z")),
    ("entry_reference", lambda body: body["entries"][0].update(stock_context_sha256="0" * 64)),
    ("registration", lambda body: body["policy"].update(event_population="invented-after-look")),
    ("registration", lambda body: body.update(calendar_sha256="0" * 64)),
    ("registration", lambda body: body.update(implementation_sha256="0" * 64)),
])
def test_reanchored_reference_or_registration_contents_do_not_disable_actual_gates(role, edit):
    kwargs = make_causal_fixture()
    with pytest.raises(ValueError):
        module.build_source_event_study_manifest(**_edit(kwargs, role, edit))


def test_potential_economic_lot_before_source_scope_requires_real_historical_context():
    kwargs = make_causal_fixture(raw_changes={0: lambda raw: raw.replace(
        b"<transactionDate><value>2023-01-15</value>", b"<transactionDate><value>2022-12-01</value>")})
    kwargs = _edit(kwargs, "security_master", lambda body: body["mappings"][0].update(
        mapping_first_session="2022-01-01", knowledge_at_utc="2022-01-01T00:00:00Z"), crossbind=True)
    with pytest.raises(module.EventStudyManifestError, match="economic lot.*source scope"):
        module.build_source_event_study_manifest(**kwargs)


def test_missing_no_filing_context_is_not_a_zero_or_an_event_exclusion():
    kwargs = make_causal_fixture()
    def edit(body):
        entry = body["entries"][0]
        entry["stock_context"]["rows"].pop()
        entry["stock_context_sha256"] = hash_bytes(enc(entry["stock_context"]))
    with pytest.raises(ValueError, match="context universe"):
        module.build_source_event_study_manifest(**_edit(kwargs, "entry_reference", edit))


def test_simultaneous_entry_context_fact_is_not_available_before_first_open():
    kwargs = make_causal_fixture()
    def edit(body):
        entry = body["entries"][0]
        entry["stock_context"]["rows"][0]["history"][-1]["knowledge_at_utc"] = "2023-01-16T14:30:00Z"
        entry["stock_context_sha256"] = hash_bytes(enc(entry["stock_context"]))
    with pytest.raises(module.EventStudyManifestError, match="simultaneous"):
        module.build_source_event_study_manifest(**_edit(kwargs, "entry_reference", edit))


def test_reconstructed_or_tampered_factory_result_cannot_supply_manifest():
    result = module.build_source_event_study_manifest(**make_causal_fixture())
    copy = replace(result)
    with pytest.raises(module.EventStudyManifestError):
        copy.manifest_bytes()
    output = result.events(); output[0]["entry_session"] = "2023-01-03"
    assert result.events()[0]["entry_session"] == "2023-01-16"
    with pytest.raises(module.EventStudyManifestError):
        module.validate_source_event_study_manifest(result.to_payload())
    object.__setattr__(result, "_bytes", b'{}')
    with pytest.raises(module.EventStudyManifestError):
        result.manifest_bytes()


@pytest.mark.parametrize("key,value", [("event_first_session", "2005-12-31"), ("event_last_session", "2023-03-01"),
    ("event_first_session", "2023-03-01"), ("event_last_session", "2023-02-30")])
def test_explicit_registered_event_window_cannot_widen_missing_source_or_future_cutoff(key, value):
    kwargs = make_causal_fixture()
    with pytest.raises(ValueError):
        module.build_source_event_study_manifest(**{**kwargs, key: value})


def test_streamed_entry_references_produce_same_economics_without_nested_context_retention():
    nested = make_causal_fixture()
    args, records = stream_reference_fixture(nested)
    streamed = module.build_source_event_study_manifest(**args)
    original = module.build_source_event_study_manifest(**nested)
    keys = ("entry_session", "exit_session", "available_at_utc", "buyer_ids", "score", "earnings_distance_sessions", "regime")
    assert {key: streamed.events()[0][key] for key in keys} == {key: original.events()[0][key] for key in keys}
    receipt = streamed.to_payload()["entry_reference_receipt"]
    assert receipt == {"mode": "streaming_entry_records", "entry_records_verified": len(records),
                       "total_reference_bytes": sum(map(len, records)), "raw_records_retained": 0}


def test_entry_record_is_released_before_next_record_is_requested():
    specs = (("4", "2023-01-13", "123456", "0000123456-23-000001", "20230113080000"),
             ("4", "2023-01-18", "123456", "0000123456-23-000002", "20230118101112"))
    args, raws = stream_reference_fixture(make_causal_fixture(specs=specs))
    class ReleaseCheckingIterator:
        def __init__(self):
            self.index, self.previous = 0, None
        def __iter__(self):
            return self
        def __next__(self):
            assert self.previous is None or self.previous() is None, "old context record retained"
            if self.index == len(raws):
                raise StopIteration
            record = module.EntryReferenceRecord(raws[self.index])
            self.index += 1
            self.previous = weakref.ref(record)
            return record
    iterator = ReleaseCheckingIterator()
    result = module.build_source_event_study_manifest(**{**args, "entry_reference_records": iterator})
    assert result.to_payload()["entry_reference_receipt"]["entry_records_verified"] == 2
    assert iterator.previous() is None


def test_streaming_reference_total_can_exceed_nested_artifact_bound_without_silent_cap_lift(monkeypatch):
    specs = (("4", "2023-01-13", "123456", "0000123456-23-000001", "20230113080000"),
             ("4", "2023-01-18", "123456", "0000123456-23-000002", "20230118101112"))
    nested = make_causal_fixture(specs=specs)
    args, raws = stream_reference_fixture(nested)
    simulated_nested_cap = len(nested["entry_reference"]) // 2
    monkeypatch.setattr(module, "MAX_REFERENCE_BYTES", simulated_nested_cap)
    with pytest.raises(module.EventStudyManifestError, match="finite bound"):
        module.build_source_event_study_manifest(**nested)
    result = module.build_source_event_study_manifest(**args)
    assert result.to_payload()["entry_reference_receipt"]["total_reference_bytes"] > simulated_nested_cap
    assert len(args["entry_reference"]) < simulated_nested_cap
    assert all(len(raw) < module.MAX_ENTRY_REFERENCE_BYTES for raw in raws)


@pytest.mark.parametrize("mode", ["missing", "extra", "list", "wrong_type", "tampered"])
def test_streamed_reference_requires_complete_exact_onepass_individually_hash_bound_records(mode):
    args, raws = stream_reference_fixture(make_causal_fixture())
    records = [module.EntryReferenceRecord(raw) for raw in raws]
    if mode == "missing":
        records.clear()
    elif mode == "extra":
        records.append(records[0])
    elif mode == "wrong_type":
        records[0] = raws[0]
    elif mode == "tampered":
        records[0] = module.EntryReferenceRecord(raws[0] + b" ")
    with pytest.raises(ValueError):
        module.build_source_event_study_manifest(**{**args, "entry_reference_records": records if mode == "list" else iter(records)})


@pytest.mark.parametrize("edit", [lambda body: body["entries"][0].update(reference_bytes=True),
    lambda body: body["entries"][0].update(reference_sha256="f" * 64),
    lambda body: body["entries"][0].update(reference_bytes=1),
    lambda body: body["entries"][0].update(entry_session="2023-01-13"),
    lambda body: body["entries"][0].update(ready=True)])
def test_reanchored_stream_reference_descriptor_contents_cannot_replace_loaded_evidence(edit):
    args, _ = stream_reference_fixture(make_causal_fixture())
    with pytest.raises(ValueError):
        module.build_source_event_study_manifest(**_edit(args, "entry_reference", edit))


@pytest.mark.parametrize("name", ["MAX_REFERENCE_MANIFEST_BYTES", "MAX_ENTRY_REFERENCE_BYTES", "MAX_TOTAL_REFERENCE_BYTES"])
def test_stream_reference_resource_caps_refuse_before_publication_not_truncate(monkeypatch, name):
    args, _ = stream_reference_fixture(make_causal_fixture())
    monkeypatch.setattr(module, name, 1)
    with pytest.raises(ValueError):
        module.build_source_event_study_manifest(**args)


def test_later_known_no_filing_security_is_not_required_in_earlier_entry_cohort():
    kwargs = _edit(make_causal_fixture(), "security_master", lambda body: body["mappings"][-1].update(
        knowledge_at_utc="2023-02-01T00:00:00Z", mapping_first_session="2023-02-01"), crossbind=True)
    def edit(body):
        body["eligible_control_security_ids"].pop()
        for entry in body["entries"]:
            entry["stock_context"]["rows"].pop()
            entry["stock_context_sha256"] = hash_bytes(enc(entry["stock_context"]))
            entry["earnings_rows"].pop()
    kwargs = _edit(kwargs, "entry_reference", edit)
    result = module.build_source_event_study_manifest(**kwargs)
    assert result.to_payload()["event_count"] == 1


def test_future_master_security_cannot_supply_historical_entry_context_even_if_caller_anchors_it():
    kwargs = _edit(make_causal_fixture(), "security_master", lambda body: body["mappings"][-1].update(
        knowledge_at_utc="2023-02-01T00:00:00Z", mapping_first_session="2023-02-01"), crossbind=True)
    with pytest.raises(ValueError, match="context universe"):
        module.build_source_event_study_manifest(**kwargs)


def test_arbitrary_favorable_three_control_subset_is_not_complete_pit_universe():
    kwargs = _edit(make_causal_fixture(), "entry_reference", lambda body: body.update(
        eligible_control_security_ids=["SID01", "SID02", "SID03"]))
    with pytest.raises(ValueError, match="complete per-entry eligible PIT universe"):
        module.build_source_event_study_manifest(**kwargs)


def test_cumulative_threshold_updates_are_linear_not_repeated_whole_lot_resums(monkeypatch):
    kwargs = make_causal_fixture(specs=_specs(count=300))
    observed_input_sizes = []
    original = module.exact_decimal_sum
    def count_inputs(values, **kwargs):
        values = tuple(values)
        observed_input_sizes.append(len(values))
        return original(values, **kwargs)
    monkeypatch.setattr(module, "exact_decimal_sum", count_inputs)
    result = module.build_source_event_study_manifest(**kwargs)
    assert result.event_lineage()[0]["payload"]["lots"][0]["purchase_value_usd"] == "15000000"
    assert observed_input_sizes and max(observed_input_sizes) <= 2


@pytest.mark.parametrize("streaming", [False, True])
def test_compact_entry_facts_preserve_latest_prerequisite_knowledge_without_raw_histories(streaming):
    kwargs = make_causal_fixture()
    def late_regime(body):
        body["entries"][0]["knowledge_at_utc"] = "2023-01-16T14:29:00Z"
    kwargs = _edit(kwargs, "entry_reference", late_regime)
    if streaming:
        kwargs, _ = stream_reference_fixture(kwargs)
    result = module.build_source_event_study_manifest(**kwargs)
    facts = result.entry_reference_facts()
    assert len(facts) == 1
    assert facts[0]["entry_session"] == "2023-01-16"
    assert facts[0]["latest_prerequisite_knowledge_at_utc"] == "2023-01-16T14:29:00Z"
    assert facts[0]["eligible_security_ids"] == [f"SID{i:02}" for i in range(20)]
    assert facts[0]["earnings_distance_sessions_by_security_id"]["SID00"] == 10
    assert facts[0]["regime"] == "bull"
    assert "stock_context" not in facts[0] and "history" not in str(facts[0])
    facts[0]["eligible_security_ids"].clear()
    assert len(result.entry_reference_facts()[0]["eligible_security_ids"]) == 20


def make_v3_causal_fixture(ages=None, *, listing_knowledge=None, empty_earnings=(), base_kwargs=None):
    from test_insider_buying_backtest_event_clock import listing_evidence
    kwargs=make_causal_fixture() if base_kwargs is None else base_kwargs
    calendar=json.loads(kwargs["calendar"]); days=[row["session"] for row in calendar["sessions"]]
    ages={"SID19":0} if ages is None else ages
    def edit(body):
        excluded=set()
        for entry in body["entries"]:
            index=days.index(entry["entry_session"]); entry["stock_context"]["schema"]="insider-stock-context-v3"
            for stock in entry["stock_context"]["rows"]:
                age=ages.get(stock["qc_symbol_id"],index)
                first=days[index-age] if age<=index else "2000-01-03"
                evidence=listing_evidence(stock["qc_symbol_id"],first)
                if listing_knowledge and stock["qc_symbol_id"] in ages:
                    evidence["knowledge_at_utc"]=listing_knowledge
                stock["history"]=stock["history"][-age:] if age else []
                stock.update(first_listing_evidence=evidence,first_listing_evidence_sha256=hash_bytes(enc(evidence)))
                if age<253:excluded.add(stock["qc_symbol_id"])
            entry["stock_context_sha256"]=hash_bytes(enc(entry["stock_context"]))
            for row in entry["earnings_rows"]:
                if row["qc_symbol_id"] in empty_earnings:row["known_earnings_sessions"]=[]
        body["eligible_control_security_ids"]=[sid for sid in body["eligible_control_security_ids"] if sid not in excluded]
    return _edit(kwargs,"entry_reference",edit)


@pytest.mark.parametrize("streaming",[False,True])
def test_v3_first_day_nonfiling_listing_with_empty_earnings_does_not_break_full_pit_primary_cohort(streaming):
    kwargs=make_v3_causal_fixture(empty_earnings=("SID19",))
    if streaming:kwargs,_=stream_reference_fixture(kwargs)
    result=module.build_source_event_study_manifest(**kwargs); fact=result.entry_reference_facts()[0]
    assert result.to_payload()["event_count"]==1 and result.to_payload()["source_submission_count"]==3
    assert fact["eligible_security_ids"]==[f"SID{i:02d}" for i in range(19)]
    assert fact["prior_listing_session_lower_bound_by_security_id"]["SID19"]==0
    assert fact["primary_seasoning_excluded_security_ids"]==["SID19"]
    assert fact["eligibility_exclusion_reason_counts"]["insufficient_60_session_history"]==1
    assert fact["eligibility_exclusion_reason_counts"][module.PRIMARY_SEASONING_EXCLUSION]==1
    assert fact["eligibility_exclusion_reason_counts"]["known_earnings_unavailable_for_excluded_security"]==1
    assert fact["earnings_distance_sessions_by_security_id"]["SID19"] is None


def test_v3_primary_seasoning_restriction_is_separate_from_sixty_session_context_and_retains_all_source_rows():
    ages={"SID13":0,"SID14":19,"SID15":59,"SID16":60,"SID17":251,"SID18":252,"SID19":253}
    result=module.build_source_event_study_manifest(**make_v3_causal_fixture(ages))
    fact=result.entry_reference_facts()[0]
    assert fact["eligible_security_ids"]==[f"SID{i:02d}" for i in range(13)]+["SID19"]
    assert fact["prior_listing_session_lower_bound_by_security_id"]["SID19"]==253
    assert fact["primary_seasoning_excluded_security_ids"]==[f"SID{i:02d}" for i in range(13,19)]
    assert fact["eligibility_exclusion_reason_counts"]["insufficient_60_session_history"]==3
    assert fact["eligibility_exclusion_reason_counts"][module.PRIMARY_SEASONING_EXCLUSION]==6
    assert result.to_payload()["source_submission_count"]==3 and result.to_payload()["minimum_prior_regular_listing_sessions"]==253
    assert result.to_payload()["fixture_v2_context_compatibility_not_listing_proof"] is False


@pytest.mark.parametrize("age,event_count",[(252,1),(253,2)])
def test_v3_actual_source_event_exclusion_boundary_preserves_original_population_and_named_disposition(age,event_count):
    specs=(("4","2023-01-15","123456","0000123456-23-000001","20230115090000"),
           ("4","2023-01-15","123475","0000123456-23-000002","20230115090000"))
    base=make_causal_fixture(specs=specs,raw_changes={1:lambda raw:raw.replace(b"<issuerTradingSymbol>T00",b"<issuerTradingSymbol>T19")})
    kwargs=make_v3_causal_fixture({"SID19":age},base_kwargs=base)
    result=module.build_source_event_study_manifest(**kwargs)
    assert result.to_payload()["source_submission_count"]==2 and len(kwargs["source_evidence"].transaction_rows())==2
    assert result.to_payload()["event_count"]==event_count
    assert result.to_payload()["excluded_reason_counts"].get(module.PRIMARY_SEASONING_EXCLUSION,0)==(1 if age==252 else 0)


def test_v3_listing_knowledge_remains_latest_prerequisite_even_for_excluded_young_security():
    kwargs=make_v3_causal_fixture(listing_knowledge="2023-01-16T14:29:00Z")
    result=module.build_source_event_study_manifest(**kwargs)
    assert result.entry_reference_facts()[0]["latest_prerequisite_knowledge_at_utc"]=="2023-01-16T14:29:00Z"
    # The frozen QC candidate's two-minute cutoff remains independently binding.
    from pathlib import Path
    from research.insider_buying.backtest_qc_canonical_candidate import build_canonical_qc_batch_plan, CanonicalQcCandidateError
    with pytest.raises(CanonicalQcCandidateError,match="prerequisite reference"):
        build_canonical_qc_batch_plan(source_events=result,legacy_source=Path("research/insider_buying_qc_stock_order_study.py").read_bytes(),
            security_master=kwargs["security_master"],entry_reference=kwargs["entry_reference"],registration=kwargs["registration"],parent_study_id="fixture-v3-first-listing")


def test_v3_old_primary_eligible_security_cannot_use_empty_known_earnings_calendar():
    kwargs=make_v3_causal_fixture(empty_earnings=("SID00",))
    with pytest.raises(module.EventStudyManifestError,match="earnings calendar missing"):
        module.build_source_event_study_manifest(**kwargs)


def test_fixture_v2_compatibility_does_not_relax_empty_earnings_or_claim_listing_proof():
    kwargs=_edit(make_causal_fixture(),"entry_reference",lambda body:body["entries"][0]["earnings_rows"][-1].update(known_earnings_sessions=[]))
    with pytest.raises(module.EventStudyManifestError,match="earnings calendar missing"):
        module.build_source_event_study_manifest(**kwargs)
    assert module.build_source_event_study_manifest(**make_causal_fixture()).to_payload()["fixture_v2_context_compatibility_not_listing_proof"] is True


def test_v3_empty_final_history_record_is_released_before_next_stream_record_request():
    kwargs,raws=stream_reference_fixture(make_v3_causal_fixture(empty_earnings=("SID19",)))
    class CheckingIterator:
        def __init__(self):self.index=0;self.previous=None
        def __iter__(self):return self
        def __next__(self):
            assert self.previous is None or self.previous() is None
            if self.index==len(raws):raise StopIteration
            result=module.EntryReferenceRecord(raws[self.index]);self.index+=1;self.previous=weakref.ref(result)
            return result
    iterator=CheckingIterator();kwargs["entry_reference_records"]=iterator
    result=module.build_source_event_study_manifest(**kwargs)
    assert iterator.previous() is None and result.to_payload()["entry_reference_receipt"]["raw_records_retained"]==0


def test_production_causal_context_cannot_silently_use_v2_fixture_listing_compatibility():
    kwargs=make_causal_fixture(); calendar=json.loads(kwargs["calendar"]); calendar["trust_scope"]="production"
    calendar_raw=enc(calendar); reference=json.loads(kwargs["entry_reference"])
    reference.update(trust_scope="production",calendar_sha256=hash_bytes(calendar_raw))
    roots=replace(kwargs["trust_roots"],trust_scope="production",calendar_sha256=hash_bytes(calendar_raw),entry_reference_sha256=hash_bytes(reference_enc(reference)))
    sessions,opens,closes,_=module.base._calendar(calendar)
    mappings=json.loads(kwargs["security_master"])["mappings"]
    with pytest.raises(module.EventStudyManifestError,match="production causal reference requires"):
        module._reference(reference_enc(reference),roots,mappings,calendar_raw,sessions,opens,closes,None)
