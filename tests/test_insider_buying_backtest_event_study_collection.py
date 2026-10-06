"""Genuine invented-source collection factories; no real history or outcomes."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import weakref
from zoneinfo import ZoneInfo

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying import backtest_event_study_collection as module
from research.insider_buying import backtest_event_study_manifest as causal
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying.backtest_source_stream import build_stream_source_evidence
from test_insider_buying_backtest_source_stream import make_stream_fixture, _record, _edit_manifest
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture
from test_insider_buying_backtest_registered_analysis import fixture as analysis_fixture


def enc(value):
    return canonical_json(value).encode("utf-8")


def _period(day):
    return f"{day[:4]}Q{(int(day[5:7])-1)//3+1}"


def make_children(windows=(("2023-01-03", "2023-01-04"), ("2023-01-05", "2023-01-06")),
                  *, zero_windows=(), changed_quarter_child=None, epoch_child=None,
                  duplicate_cross_quarter_accession=False):
    calendar = {"schema": "insider-backtest-calendar-v1", "trust_scope": "fixture", "sessions": []}
    current, eastern = date(2020, 1, 1), ZoneInfo("America/New_York")
    while len(calendar["sessions"]) < 1_100:
        if current.weekday() < 5:
            calendar["sessions"].append({"session": current.isoformat(), **{key + "_utc": datetime.combine(current, datetime.min.time()).replace(
                hour=9 if key == "open" else 16, minute=30 if key == "open" else 0, tzinfo=eastern).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                for key in ("open", "close")}})
        current += timedelta(days=1)
    dates = [row["session"] for row in calendar["sessions"]]
    master = json.loads(make_pipeline_fixture()["security_master"])
    for mapping in master["mappings"]:
        mapping.update(mapping_first_session="2020-01-01", mapping_last_session="2025-01-01", knowledge_at_utc="2020-01-01T00:00:00Z")
    dictionary = {"schema": "insider-common-equity-exceptions-v2", "trust_scope": "fixture", "exceptions": []}
    specifications = {}
    for first, last in windows:
        for day in dates:
            if first <= day <= last:
                specifications.setdefault(_period(day), []).append(day)
    specifications = {period: tuple(sorted(set(days))) for period, days in specifications.items()}
    quarter_ordinals = {period: index for index, period in enumerate(sorted(specifications))}
    child_records, child_kwargs = [], []
    for child_index, (first, last) in enumerate(windows):
        periods = tuple(period for period in sorted(specifications) if _period(first) <= period <= _period(last))
        specs_by_period = {period: tuple(("4", day, "123456", f"0000123456-{int(day[:4])%100:02d}-{(0 if duplicate_cross_quarter_accession else quarter_ordinals[period])*1000+offset+1:06d}",
            day.replace("-", "") + "090000") for offset, day in enumerate(specifications[period])) for period in periods}
        stream, ordered_specs = make_stream_fixture(periods=periods, specs_by_period=specs_by_period, lookback=first, decision=last)
        def transform(raw):
            if child_index in zero_windows:
                raw = raw.replace(b"<transactionShares><value>500</value>", b"<transactionShares><value>250</value>")
            if child_index == changed_quarter_child:
                raw = raw.replace(b"<sharesOwnedFollowingTransaction><value>10000</value>", b"<sharesOwnedFollowingTransaction><value>10001</value>")
            return raw
        records = [_record(period, spec, raw_change=transform) for period, spec in ordered_specs]
        digests = {}
        for period in periods:
            digest = hashlib.sha256()
            for (record_period, _), record in zip(ordered_specs, records, strict=True):
                if record_period == period:
                    digest.update(record.entry_bytes + b"\n")
            digests[period] = digest.hexdigest()
        stream = _edit_manifest(stream, lambda b: [row.update(ordered_parent_inventory_sha256=digests[row["period"]]) for row in b["quarters"]])
        stream["parent_records"] = iter(records)
        source = build_stream_source_evidence(**stream)
        reference = {"schema": "insider-event-entry-pit-reference-v1", "trust_scope": "fixture",
            "calendar_sha256": hash_bytes(enc(calendar)), "security_master_sha256": hash_bytes(enc(master)),
            "event_population_policy": causal.EVENT_POPULATION_POLICY,
            "eligible_control_security_ids": [mapping["qc_symbol_id"] for mapping in master["mappings"]], "entries": []}
        for day in dates:
            if not first <= day <= last:
                continue
            index = dates.index(day); knowledge = calendar["sessions"][index-1]["close_utc"]
            context = {"schema": "insider-stock-context-v2", "trust_scope": "fixture", "calendar_sha256": hash_bytes(enc(calendar)),
                "decision_session": day, "rows": [{"qc_symbol_id": mapping["qc_symbol_id"], "history": [
                    {"session": bar["session"], "raw_close_usd": "10", "volume_shares": "200000", "knowledge_at_utc": bar["close_utc"]}
                    for bar in calendar["sessions"][index-60:index]]} for mapping in master["mappings"]]}
            reference["entries"].append({"entry_session": day, "knowledge_at_utc": knowledge, "regime": "bull",
                "stock_context": context, "stock_context_sha256": hash_bytes(enc(context)), "earnings_rows": [
                    {"qc_symbol_id": mapping["qc_symbol_id"], "known_earnings_sessions": [dates[index+10]], "knowledge_at_utc": knowledge}
                    for mapping in master["mappings"]]})
        registered = analysis_fixture()["registration"]
        registered.update(source_manifest_sha256=stream["population_sha256"], security_master_sha256=hash_bytes(enc(master)),
            calendar_sha256=hash_bytes(analysis.canonical_bytes(calendar["sessions"])), registered_at_utc="2021-11-01T00:00:00Z",
            first_outcome_access_utc="2024-01-01T00:00:00Z", policy=analysis.frozen_analysis_policy(),
            analysis_plan=analysis.analysis_plan_descriptors(implementation_sha256="a"*64))
        if child_index == epoch_child:
            registered["registered_look_id"] = "different-fixture-look"
        kwargs = dict(source_evidence=source, security_master=enc(master), calendar=enc(calendar), common_equity_exceptions=enc(dictionary),
            entry_reference=analysis.canonical_bytes(reference), registration=analysis.canonical_bytes(registered),
            event_first_session=first, event_last_session=last, allow_zero_event_window=child_index in zero_windows)
        kwargs["trust_roots"] = causal.EventStudyManifestTrustRoots("fixture", stream["population_sha256"],
            *(hash_bytes(kwargs[name]) for name in ("security_master", "calendar", "common_equity_exceptions", "entry_reference", "registration")), "a"*64)
        child_records.append(module.CausalStudyChildRecord(causal.build_source_event_study_manifest(**kwargs), source, kwargs["registration"]))
        child_kwargs.append(kwargs)
    return tuple(child_records), tuple(child_kwargs)


def collection_inputs(records, *, windows=None):
    descriptors = [module.describe_causal_child(record) for record in records]
    first = descriptors[0]["event_first_session"]
    last = descriptors[-1]["event_last_session"]
    if windows is not None:
        first, last = windows
    inventory = analysis.canonical_bytes({"schema": module.INVENTORY_SCHEMA, "trust_scope": "fixture",
        "origin": "invented-sealed-causal-window-collection", "event_first_session": first, "event_last_session": last,
        "children": descriptors})
    registration = json.loads(records[0].registration_raw)
    registration.update(source_manifest_sha256=hash_bytes(inventory), registered_at_utc="2021-12-01T00:00:00Z")
    parent = analysis.canonical_bytes(registration)
    return dict(child_records=iter(records), collection_inventory=inventory, parent_registration=parent,
        trust_roots=module.EventStudyCollectionTrustRoots("fixture", hash_bytes(inventory), hash_bytes(parent), "a"*64))


@pytest.fixture(scope="module")
def small():
    return make_children()


def test_genuine_adjacent_causal_children_compose_one_preoutcome_parent_and_unique_quarter_counts(small):
    records, _ = small
    result = module.build_source_event_study_collection(**collection_inputs(records))
    summary = result.to_payload()
    assert type(result) is causal.SourceEventStudyManifest and summary["kind"] == module.VERSION
    assert summary["event_count"] == summary["event_date_count"] == summary["economic_lot_count"] == 4
    assert summary["unique_source_quarter_count"] == 1 and summary["repeated_source_quarter_receipts_not_recounted"] == 1
    assert summary["source_submission_count"] == summary["stream_corroborated_form4_count"] == 4
    assert summary["preceding_quarantined_count"] == 4 and summary["preceding_corroborated_count"] == 0
    assert summary["backtesting_ready"] is summary["look_authority"] is summary["historical_publication_promoted"] is False
    assert summary["qc_jobs"] == summary["research_looks"] == summary["outcome_rows_read"] == 0
    assert len(result.entry_reference_facts()) == len(result.event_lineage()) == 4
    assert result.to_payload()["entry_reference_profile"].startswith("immutable-causal-child")


def test_genuine_collection_can_exceed_three_hundred_twenty_entry_dates_without_forged_seals():
    windows = (("2022-01-03", "2022-03-31"), ("2022-04-01", "2022-06-30"),
               ("2022-07-01", "2022-09-30"), ("2022-10-03", "2022-12-30"),
               ("2023-01-02", "2023-03-31"), ("2023-04-03", "2023-06-30"))
    records, _ = make_children(windows)
    kwargs = collection_inputs(records)
    result = module.build_source_event_study_collection(**kwargs)
    assert result.to_payload()["event_date_count"] == result.to_payload()["event_count"] == 390
    assert result.to_payload()["unique_source_quarter_count"] == 6
    assert result.to_payload()["source_submission_count"] == 390
    assert all(type(record.event_manifest) is causal.SourceEventStudyManifest for record in records)
    checked = analysis.verify_registered_analysis_manifest(registration_raw=kwargs["parent_registration"], manifest_raw=result.manifest_bytes(),
        expected_registration_sha256=hash_bytes(kwargs["parent_registration"]), expected_manifest_sha256=hash_bytes(result.manifest_bytes()),
        expected_implementation_sha256="a"*64)
    assert checked["canonical_event_clock_verified"] is True
    # This tests engineering representability, not statistical adequacy: the
    # invented fixture deliberately has one issuer and consumes no outcomes.
    assert len({event["issuer_id"] for event in result.events()}) == 1


@pytest.mark.parametrize("mutation", ["missing", "extra", "reordered", "duplicate", "list"])
def test_child_population_count_order_and_onepass_inventory_are_exact(small, mutation):
    records, _ = small; kwargs = collection_inputs(records)
    candidates = {"missing": records[:1], "extra": records+(records[0],), "reordered": records[::-1], "duplicate": (records[0],records[0])}
    kwargs["child_records"] = list(records) if mutation == "list" else iter(candidates[mutation])
    with pytest.raises(module.EventStudyCollectionError): module.build_source_event_study_collection(**kwargs)


@pytest.mark.parametrize("windows", [(("2023-01-03", "2023-01-04"), ("2023-01-06", "2023-01-09")),
    (("2023-01-03", "2023-01-05"), ("2023-01-05", "2023-01-06"))])
def test_reanchored_collection_cannot_hide_window_gap_or_overlap(windows):
    records, _ = make_children(windows)
    with pytest.raises(module.EventStudyCollectionError, match="gap, overlap"): module.build_source_event_study_collection(**collection_inputs(records))


def test_repeated_quarter_original_inventory_must_be_identical_not_just_counts():
    records, _ = make_children(changed_quarter_child=1)
    with pytest.raises(module.EventStudyCollectionError, match="repeated quarter"):
        module.build_source_event_study_collection(**collection_inputs(records))


def test_reanchored_child_cannot_change_fixed_permanent_look_epoch():
    records, _ = make_children(epoch_child=1)
    with pytest.raises(module.EventStudyCollectionError, match="look/epoch"):
        module.build_source_event_study_collection(**collection_inputs(records))


def test_duplicate_accession_across_genuine_distinct_quarter_receipts_is_not_counted_twice():
    records, _ = make_children((("2023-03-31", "2023-03-31"), ("2023-04-03", "2023-04-03")),
                              duplicate_cross_quarter_accession=True)
    with pytest.raises(module.EventStudyCollectionError, match="cross-quarter source accession"):
        module.build_source_event_study_collection(**collection_inputs(records))


def test_true_below_threshold_window_is_kept_for_continuity_without_empty_ready_population():
    # Adjacent small windows in the same quarter must share exactly the same
    # source images; use a whole zero quarter between nonempty quarters instead.
    windows = (("2022-10-03", "2022-12-30"), ("2023-01-02", "2023-03-31"), ("2023-04-03", "2023-06-30"))
    records, _ = make_children(windows, zero_windows=(1,))
    assert records[1].event_manifest.to_payload()["kind"] == causal.ZERO_WINDOW_VERSION
    assert records[1].event_manifest.events() == []
    result = module.build_source_event_study_collection(**collection_inputs(records))
    assert result.to_payload()["zero_event_window_count"] == 1
    assert result.to_payload()["source_submission_count"] == 195
    assert result.to_payload()["event_count"] == 130
    assert len(result.entry_reference_facts()) == 195


def test_zero_window_requires_every_actual_reference_session_and_explicit_mode(small):
    # Below-threshold raw images must be newly bound to genuine source first.
    records, rows = make_children(zero_windows=(0,1))
    values = dict(rows[0]); values["allow_zero_event_window"] = False
    with pytest.raises(causal.EventStudyManifestError, match="nonempty"):
        causal.build_source_event_study_manifest(**values)
    values = dict(rows[0]); body = json.loads(values["entry_reference"]); body["entries"].pop()
    values["entry_reference"] = analysis.canonical_bytes(body)
    values["trust_roots"] = replace(values["trust_roots"], entry_reference_sha256=hash_bytes(values["entry_reference"]))
    with pytest.raises(causal.EventStudyManifestError, match="complete per-session"):
        causal.build_source_event_study_manifest(**values)
    with pytest.raises(module.EventStudyCollectionError, match="no nonempty"):
        module.build_source_event_study_collection(**collection_inputs(records))


def test_external_inventory_registration_and_factory_identity_cannot_be_resealed(small):
    records, _ = small
    for role in ("collection_inventory", "parent_registration"):
        kwargs = collection_inputs(records); kwargs[role] += b" "
        with pytest.raises(ValueError): module.build_source_event_study_collection(**kwargs)
    bad = module.CausalStudyChildRecord(replace(records[0].event_manifest), records[0].source_evidence, records[0].registration_raw)
    kwargs = collection_inputs(records); kwargs["child_records"] = iter((bad,records[1]))
    with pytest.raises(ValueError): module.build_source_event_study_collection(**kwargs)


def test_wrong_genuine_source_cutoff_receipt_cannot_replace_exact_child_producer(small):
    records, _ = small
    bad = module.CausalStudyChildRecord(records[0].event_manifest, records[1].source_evidence, records[0].registration_raw)
    kwargs = collection_inputs(records); kwargs["child_records"] = iter((bad,records[1]))
    with pytest.raises(module.EventStudyCollectionError, match="source receipt/epoch"):
        module.build_source_event_study_collection(**kwargs)


def test_original_child_accounting_and_unique_quarter_provenance_are_detached_not_recounted(small):
    records, _ = small
    result=module.build_source_event_study_collection(**collection_inputs(records))
    proof=module.collection_provenance(result)
    assert len(proof["child_receipts"]) == 2 and len(proof["unique_source_quarter_receipts"]) == 1
    assert proof["child_receipts"][0]["original_source_receipt_counts"]["as_of_parent_count"] == 2
    assert proof["child_receipts"][1]["original_source_receipt_counts"]["as_of_parent_count"] == 4
    assert proof["unique_source_quarter_receipts"][0]["preceding_quarantined_count"] == 4
    assert proof["unique_source_quarter_receipts"][0]["preceding_quarantine_reason_counts"] == {
        "complete_parent_corroboration_missing": 4, "complete_parent_identity_conflict": 0,
        "unsupported_parent_corroboration_form": 0}
    proof["child_receipts"].clear()
    assert len(module.collection_provenance(result)["child_receipts"]) == 2
    with pytest.raises(module.EventStudyCollectionError): module.collection_provenance(records[0].event_manifest)


def test_child_records_are_released_before_advancing_onepass_collection(small):
    records, _ = small
    class CheckingIterator:
        def __init__(self): self.index=0; self.previous=None
        def __iter__(self): return self
        def __next__(self):
            assert self.previous is None or self.previous() is None
            if self.index == len(records): raise StopIteration
            original=records[self.index]; self.index+=1
            record=module.CausalStudyChildRecord(original.event_manifest, original.source_evidence, original.registration_raw)
            self.previous=weakref.ref(record)
            return record
    stream=CheckingIterator(); kwargs=collection_inputs(records); kwargs["child_records"]=stream
    result=module.build_source_event_study_collection(**kwargs)
    assert stream.previous() is None and result.to_payload()["raw_child_objects_retained"] == 0


@pytest.mark.parametrize("role", ["inventory", "parent-registration", "descriptor", "final-window"])
def test_reanchored_collection_does_not_change_exact_root_or_declared_window_contract(small, role):
    records, _ = small; kwargs=collection_inputs(records)
    if role == "parent-registration":
        parent=json.loads(kwargs["parent_registration"]); parent["registered_at_utc"]="2021-10-01T00:00:00Z"
        kwargs["parent_registration"]=analysis.canonical_bytes(parent)
    else:
        inventory=json.loads(kwargs["collection_inventory"])
        if role == "inventory": inventory["origin"]="wrong-origin"
        elif role == "descriptor": inventory["children"][0]["source_population_sha256"]="f"*64
        else: inventory["event_last_session"]="2023-01-09"
        kwargs["collection_inventory"]=analysis.canonical_bytes(inventory)
        parent=json.loads(kwargs["parent_registration"]); parent["source_manifest_sha256"]=hash_bytes(kwargs["collection_inventory"])
        kwargs["parent_registration"]=analysis.canonical_bytes(parent)
    kwargs["trust_roots"]=module.EventStudyCollectionTrustRoots("fixture",hash_bytes(kwargs["collection_inventory"]),
        hash_bytes(kwargs["parent_registration"]),"a"*64)
    with pytest.raises(module.EventStudyCollectionError): module.build_source_event_study_collection(**kwargs)


def test_composed_factory_integrates_frozen_default_disabled_qc_plan(small):
    from pathlib import Path
    from research.insider_buying.backtest_qc_canonical_candidate import build_canonical_qc_batch_plan
    records, children = small; kwargs=collection_inputs(records)
    result=module.build_source_event_study_collection(**kwargs)
    plan=build_canonical_qc_batch_plan(source_events=result,
        legacy_source=Path("research/insider_buying_qc_stock_order_study.py").read_bytes(),
        security_master=children[0]["security_master"], entry_reference=kwargs["collection_inventory"],
        registration=kwargs["parent_registration"], parent_study_id="fixture-composed-parent")
    assert plan.to_payload()["event_count"] == 4 and plan.to_payload()["candidate_enabled"] is False
