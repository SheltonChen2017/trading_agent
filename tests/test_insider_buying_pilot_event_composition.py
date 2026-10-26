"""Invented source/reference-only causal tests; no data, QC or outcomes.

The full census and both temporal sources are made by their real upstream
factories. Every original parent is reparsed; no evidence seal is reminted.
Weekday fixtures are not authenticated exchange-calendar evidence.
"""
from dataclasses import replace
from decimal import Decimal, localcontext
import csv
import hashlib
import io
import json
import zipfile

import pytest

from data.hashing import hash_bytes, hash_payload
from research import insider_buying_pilot_event_composition as m
from test_insider_buying_pilot_production_composition import (
    ingredients as original_ingredients, _registration_inputs, _source,
)
from test_insider_buying_pilot_sec_roster import corpus as roster_corpus, _manifest
from test_insider_buying_backtest_source_stream import _record
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture
from test_insider_buying_backtest_event_clock import listing_evidence


@pytest.fixture(scope="module")
def ingredients(original_ingredients, roster_corpus):
    _, images, _ = roster_corpus
    pure = m.pilot.roster.selector.pure
    changed = []
    for image in images:
        if image.period != "2023Q1":
            changed.append(image)
            continue
        sink = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(image.raw_bytes)) as old, zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as new:
            for name in old.namelist():
                raw = old.read(name)
                if name == "SUBMISSION.tsv":
                    headers = next(csv.reader(io.StringIO(raw.decode()), delimiter="\t"))
                    text = io.StringIO(newline="")
                    writer = csv.writer(text, delimiter="\t", lineterminator="\n")
                    writer.writerow(headers)
                    forms = ("3", "3/A", "4", "4", "4", "4", "4/A", "5", "5/A")
                    for ordinal, form in enumerate(forms, 1):
                        values = dict.fromkeys(headers, "")
                        values.update(ACCESSION_NUMBER=f"0000000001-23-{ordinal:06d}", DOCUMENT_TYPE=form,
                            FILING_DATE="18-JAN-2023" if ordinal == 6 else "13-JAN-2023",
                            ISSUERCIK="0000000003", ISSUERNAME="Invented Issuer", ISSUERTRADINGSYMBOL="T00")
                        writer.writerow([values[name] for name in headers])
                    raw = text.getvalue().encode()
                new.writestr(name, raw)
        changed.append(pure.QuarterArchive(image.period, sink.getvalue()))
    images = tuple(changed)
    manifest = _manifest(images)
    bindings = pure.census._manifest_bindings(manifest)
    profile = pure.build_retained_82q_schema_profile_candidate()
    quarters = tuple(pure.census._census_quarter(image.raw_bytes, binding)
                     for image, binding in zip(images, bindings, strict=True))
    headers = tuple(pure.headers._quarter_headers(image.raw_bytes, image.period, profile) for image in images)
    census = pure._census_receipt(quarters, hash_bytes(manifest), len(manifest), True)
    header = pure._header_receipt(headers, census.sha256, True)
    selected = pure.select_affected_quarters(intake_manifest_raw=manifest, expected_manifest_sha256=hash_bytes(manifest),
        quarter_inputs=iter(images), expected_census_sha256=census.sha256,
        expected_header_preflight_sha256=header.sha256, fixture_only=True).to_payload()
    selected["fixture_only"] = False  # Existing selector-control fixture shape, never a production roster.
    selection = m._raw(selected)
    rows = []
    roster = m.pilot.roster.derive_pilot_sec_roster(intake_manifest_raw=manifest,
        expected_manifest_sha256=hash_bytes(manifest), selection_raw=selection,
        expected_selection_sha256=hash_bytes(selection),
        quarter_inputs=iter(image for image in images if image.period in m.pilot.roster.CONTEXT_PERIODS),
        consume_row=rows.append, fixture_only=True)
    arguments = {**original_ingredients[0], "full_census": roster,
        "trust_roots": replace(original_ingredients[0]["trust_roots"], full_census_sha256=roster.sha256)}
    return arguments, rows


@pytest.fixture(scope="module")
def registered(ingredients):
    return m.pilot.bind_pilot_production_registration(**_registration_inputs(ingredients))


def _pair(ingredients, registered, *, entry="2023-01-13", stamps=None, shares=None, transaction_days=None, reference_edit=None):
    stamps = stamps or {}
    shares = shares or {}
    transaction_days = transaction_days or {}
    initial = _source(ingredients, entry=entry)
    coverages = initial["window_coverages"]
    periods = tuple(coverage.to_payload()["period"] for coverage in coverages)
    declarations, records = [], []
    defaults = {3:"20230113080000", 4:"20230113090000", 5:"20230113091500", 6:"20230118101112", 7:"20230113170000"}
    for coverage in coverages:
        period = coverage.to_payload()["period"]
        digest = hashlib.sha256()
        count = 0
        for row in ingredients[1]:
            if row["period"] != period or row["form_type"] not in {"4", "4/A"}:
                continue
            ordinal = row["source_record_ordinal"]
            stamp = (stamps.get(ordinal, defaults.get(ordinal, row["filing_date"].replace("-", "") + "101112"))
                     if period == "2023Q1" else row["filing_date"].replace("-", "") + "101112")
            spec = row["form_type"], row["filing_date"], row["raw_issuer_cik"], row["accession_number"], stamp
            amount = str(shares.get(ordinal, 250)).encode()
            transaction_day = transaction_days.get(ordinal, "2023-01-13").encode()
            def change(raw, amount=amount, transaction_day=transaction_day):
                changed = raw.replace(b"<transactionShares><value>500</value>", b"<transactionShares><value>" + amount + b"</value>").replace(
                    b"<transactionDate><value>2023-01-18</value>", b"<transactionDate><value>2023-01-13</value>")
                return changed.replace(b"<transactionDate><value>2023-01-13</value>",
                    b"<transactionDate><value>" + transaction_day + b"</value>")
            record = _record(period, spec, raw_change=change)
            records.append(record)
            digest.update(record.entry_bytes + b"\n")
            count += 1
        declarations.append({"period": period, "coverage_sha256": coverage.sha256, "parent_count": count,
                             "ordered_parent_inventory_sha256": digest.hexdigest()})
    scope = m.pilot.compose_v2_scope_coverage(coverages, periods)
    population = m._raw({"schema":"insider-backtest-source-population-v2", "trust_scope":"fixture",
        "origin":"invented-complete-submission", "scope_sha256":scope.sha256,
        "expected_periods":list(periods), "quarters":declarations})
    plan = ingredients[0]["pilot_plan"].to_payload()
    days = [row["session"] for row in plan["calendar_sessions"]]
    index = days.index(entry)
    opening = plan["calendar_sessions"][index]["open_utc"]
    assessment = m.pilot.pilot.assess_entry_context(plan=ingredients[0]["pilot_plan"],
        metadata_raw=initial["entry_context_raw"], expected_metadata_sha256=initial["expected_entry_context_sha256"]).to_payload()
    source_args = dict(coverages=coverages, expected_periods=periods, population_manifest=population,
        population_sha256=hash_bytes(population), trust_scope="fixture",
        lookback_start_session=days[index-30], decision_session=entry)
    before_source = m.source_factory.build_stream_source_evidence(**source_args, parent_records=iter(records),
        decision_cutoff_utc=assessment["moo_prerequisite_cutoff_utc"])
    after_source = m.source_factory.build_stream_source_evidence(**source_args, parent_records=iter(records), decision_cutoff_utc=opening)
    entry_source = m.pilot.compose_pilot_entry_source(registration=registered, source_evidence=before_source,
        window_coverages=coverages, entry_context_raw=initial["entry_context_raw"],
        expected_entry_context_sha256=initial["expected_entry_context_sha256"])
    calendar = m._raw({"schema":"insider-backtest-calendar-v1", "trust_scope":"fixture", "sessions":plan["calendar_sessions"]})
    master = json.loads(make_pipeline_fixture({"stocks":4,"members":1})["security_master"])
    for offset, mapping in enumerate(master["mappings"]):
        mapping.update(issuer_cik="0000000003" if offset == 0 else f"{1000+offset:010d}",
            mapping_first_session="2010-01-04", mapping_last_session="2027-01-01", knowledge_at_utc="2010-01-01T00:00:00Z")
    master["source_exclusions"] = [{"issuer_cik":"0000000001", "security_class":"common_stock", "country":"CA", "reason":"non_us_security"}]
    master_raw = m._raw(master)
    context_rows = []
    for mapping in master["mappings"]:
        evidence = listing_evidence(mapping["qc_symbol_id"], "2010-01-04", published="2010-01-01T00:00:00Z", knowledge="2010-01-01T00:00:00Z")
        history = [{"session":day["session"], "raw_close_usd":"10", "volume_shares":"200000", "knowledge_at_utc":day["close_utc"]}
                   for day in plan["calendar_sessions"][index-60:index]]
        context_rows.append({"qc_symbol_id":mapping["qc_symbol_id"], "history":history,
            "first_listing_evidence":evidence, "first_listing_evidence_sha256":hash_payload(evidence)})
    context = {"schema":"insider-stock-context-v3", "trust_scope":"fixture", "calendar_sha256":hash_bytes(calendar),
               "decision_session":entry, "rows":context_rows}
    reference = {"schema":m.REFERENCE_SCHEMA, "trust_scope":"fixture", "calendar_sha256":hash_bytes(calendar),
        "security_master_sha256":hash_bytes(master_raw), "entry_session":entry,
        "knowledge_at_utc":plan["calendar_sessions"][index-1]["close_utc"], "regime":"bull",
        "eligible_control_security_ids":[row["qc_symbol_id"] for row in master["mappings"]],
        "stock_context":context, "stock_context_sha256":hash_payload(context)}
    if reference_edit:
        reference_edit(reference)
    reference_raw = m._raw(reference)
    exceptions = m._raw({"schema":"insider-common-equity-exceptions-v2", "trust_scope":"fixture", "exceptions":[]})
    roots = m.PilotEventTrustRoots("fixture", entry_source.sha256, after_source.sha256,
        hash_bytes(master_raw), hash_bytes(calendar), hash_bytes(exceptions), hash_bytes(reference_raw), "e"*64)
    return dict(entry_source=entry_source, first_open_source=after_source, security_master_raw=master_raw,
        calendar_raw=calendar, common_equity_exceptions_raw=exceptions, entry_reference_raw=reference_raw, trust_roots=roots)


def test_real_causal_lot_threshold_snapshot_is_composed(ingredients, registered):
    arguments = _pair(ingredients, registered)
    result = m.compose_pilot_entry_events(**arguments)
    summary = result.to_payload()
    assert summary["disposition"] == "SOURCE_EVENTS_MOO_COMPATIBLE"
    assert summary["canonical_event_count"] == summary["canonical_counts"]["economic_lots_at_target"] == 1
    assert summary["source_submission_count"] == 15
    assert summary["all_six_form_source_counts"] == {"3":2,"3/A":2,"4":5,"4/A":2,"5":2,"5/A":2}
    assert summary["relevant_original_count"] == 7
    event = result.compatible_events()[0]
    assert event["entry_session"] == "2023-01-13" and event["available_at_utc"] == "2023-01-13T14:15:00Z"
    lot = result.event_lineage()[0]["payload"]["lots"][0]
    assert lot["purchase_value_usd"] == "75000" and len(lot["member_event_ids"]) == 3
    assert lot["first_threshold_at_utc"] == "2023-01-13T14:00:00Z"
    with localcontext(m.base.formula._new_decimal_context()):
        assert Decimal(event["score"]) == m.base.formula._event_formula(Decimal(75000), 0)[2]
    assert summary["asof_future_parent_count"] == summary["canonical_future_parent_count"] == 2
    assert summary["backtesting_ready"] is summary["old_full_study_manifest_seal_created"] is False
    assert summary["research_looks_consumed"] == summary["qc_jobs"] == summary["backtests"] == 0


def test_distinct_lots_merge_one_issuer_entry_with_sum_of_frozen_log_scores(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, shares={3:500}, transaction_days={3:"2023-01-12"}))
    assert result.to_payload()["canonical_event_count"] == 1
    assert result.to_payload()["canonical_counts"]["economic_lots_at_target"] == 2
    lots = result.event_lineage()[0]["payload"]["lots"]
    assert sorted(lot["transaction_date"] for lot in lots) == ["2023-01-12", "2023-01-13"]
    assert all(Decimal(lot["purchase_value_usd"]) == 50000 for lot in lots)
    with localcontext(m.base.formula._new_decimal_context()):
        expected = 2 * m.base.formula._event_formula(Decimal(50000), 0)[2]
        assert Decimal(result.compatible_events()[0]["score"]) == expected
        assert expected != m.base.formula._event_formula(Decimal(100000), 0)[2]


def test_ambient_decimal_context_cannot_change_causal_values_or_scores(ingredients, registered):
    arguments = _pair(ingredients, registered)
    expected = m.compose_pilot_entry_events(**arguments).canonical_events()
    with localcontext() as arithmetic:
        arithmetic.prec = 2
        observed = m.compose_pilot_entry_events(**arguments).canonical_events()
    assert observed == expected


@pytest.mark.parametrize("stamps,shares", [({5:"20230113092900"}, {}),
    ({5:"20230113092900"}, {3:240,4:240}), ({7:"20230113092900"}, {})])
def test_post_moo_addition_threshold_or_amendment_refuses_whole_window_without_dropping(ingredients, registered, stamps, shares):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, stamps=stamps, shares=shares))
    body = result.to_payload()
    assert body["disposition"] == "REFUSED_TEMPORAL_INCOMPATIBILITY"
    assert body["whole_window_refusal_reasons"] == ["canonical_lot_or_entry_changed_after_moo_cutoff"]
    assert body["events_silently_dropped_or_delayed"] is body["later_facts_admitted_as_tradeable_moo_features"] is False
    assert len(result.canonical_events()) == body["canonical_event_count"]
    with pytest.raises(m.PilotEventCompositionError, match="whole_window"):
        result.compatible_events()
    assert body["backtesting_ready"] is False


@pytest.mark.parametrize("ordinal", [5,7])
def test_exact_open_addition_or_amendment_cannot_rewrite_the_finalized_entry(ingredients, registered, ordinal):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, stamps={ordinal:"20230113093000"}))
    assert result.to_payload()["disposition"] == "SOURCE_EVENTS_MOO_COMPATIBLE"
    lot = result.event_lineage()[0]["payload"]["lots"][0]
    assert lot["purchase_value_usd"] == ("50000" if ordinal == 5 else "75000")
    assert len(lot["member_event_ids"]) == (2 if ordinal == 5 else 3)


def test_exact_moo_addition_is_allowed_but_not_one_second_later(ingredients, registered):
    exact = m.compose_pilot_entry_events(**_pair(ingredients, registered, stamps={5:"20230113092800"}))
    assert exact.to_payload()["disposition"] == "SOURCE_EVENTS_MOO_COMPATIBLE"
    assert exact.compatible_events()[0]["available_at_utc"] == "2023-01-13T14:28:00Z"
    late = m.compose_pilot_entry_events(**_pair(ingredients, registered, stamps={5:"20230113092801"}))
    assert late.to_payload()["disposition"] == "REFUSED_TEMPORAL_INCOMPATIBILITY"


def test_first_threshold_exactly_at_open_schedules_next_open_not_current_entry(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered,
        stamps={5:"20230113093000"}, shares={3:200,4:200}))
    body = result.to_payload()
    assert body["disposition"] == "SOURCE_EVENTS_MOO_COMPATIBLE"
    assert body["canonical_event_count"] == body["provisional_event_count"] == 0
    assert body["canonical_counts"]["pending_first_opens_after_target"] == 1
    assert body["provisional_counts"]["below_threshold_lots"] == 1


def test_amendment_known_before_moo_is_conserved_zero_not_false_empty_source(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, stamps={7:"20230113085900"}))
    body = result.to_payload()
    assert body["disposition"] == "SOURCE_EVENTS_MOO_COMPATIBLE" and body["canonical_event_count"] == 0
    assert body["canonical_exclusion_reason_counts"]["amendment_already_public_before_first_entry"] == 1
    assert body["canonical_exclusion_reason_counts"]["known_amendment_identity_retained_eligibility_not_evaluated"] == 2
    assert body["relevant_original_count"] == 7 and body["source_submission_count"] == 15


def test_under_threshold_never_invents_event_or_rounds_into_threshold(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, shares={3:"166.6666666666666666",4:"166.6666666666666666",5:"166.6666666666666666"}))
    assert result.to_payload()["canonical_event_count"] == 0
    assert result.to_payload()["canonical_counts"]["below_threshold_lots"] == 1
    assert result.compatible_events() == []


def test_later_filing_of_consumed_lot_is_not_reset_or_retraded(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, entry="2023-01-19"))
    body = result.to_payload()
    assert body["canonical_event_count"] == 0
    assert body["canonical_counts"]["late_members_not_reset_or_retraded"] == 1


def test_reference_known_at0929_refuses_whole_population_not_backdated(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered,
        reference_edit=lambda row:row.update(knowledge_at_utc="2023-01-13T14:29:00Z")))
    body = result.to_payload()
    assert body["canonical_event_count"] == 1 and body["disposition"] == "REFUSED_TEMPORAL_INCOMPATIBILITY"
    assert body["whole_window_refusal_reasons"] == ["required_prerequisite_after_moo_cutoff"]
    with pytest.raises(m.PilotEventCompositionError):
        result.compatible_events()


def test_actual_context_bar_known_only_after_moo_is_not_backdated(ingredients, registered):
    def change(reference):
        reference["stock_context"]["rows"][0]["history"][-1]["knowledge_at_utc"] = "2023-01-13T14:29:00Z"
        reference["stock_context_sha256"] = hash_payload(reference["stock_context"])
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, reference_edit=change))
    assert result.to_payload()["disposition"] == "REFUSED_TEMPORAL_INCOMPATIBILITY"
    assert result.to_payload()["whole_window_refusal_reasons"] == ["required_prerequisite_after_moo_cutoff"]
    assert result.to_payload()["canonical_event_count"] == 1
    assert result.to_payload()["provisional_uses_same_canonical_reference_for_diagnostic_comparison"] is True
    assert result.to_payload()["later_facts_admitted_as_tradeable_moo_features"] is False
    assert "later_facts_used_as_moo_features" not in result.to_payload()
    with pytest.raises(m.PilotEventCompositionError, match="whole_window"):
        result.compatible_events()


def test_frozen_pilot_embargo_is_preserved_separately_from_source_compatibility(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered, entry="2024-01-02"))
    body = result.to_payload()
    assert body["disposition"] == "PILOT_SCHEDULE_EXCLUDED"
    assert body["whole_window_refusal_reasons"] == []
    assert "embargo_first60_phase_sessions" in body["pilot_schedule_exclusion_reasons"]
    assert body["source_submission_count"] == 12
    with pytest.raises(m.PilotEventCompositionError, match="whole_window"):
        result.compatible_events()


def test_missing_second_source_or_relabelled_cutoff_is_not_canonical_corroboration(ingredients, registered):
    arguments = _pair(ingredients, registered)
    for source in (None, arguments["entry_source"].source_evidence(), arguments["first_open_source"].to_payload()):
        changed = {**arguments, "first_open_source":source}
        if type(source) is m.source_factory.StreamSourceEvidence:
            changed["trust_roots"] = replace(arguments["trust_roots"], first_open_source_sha256=source.sha256)
        with pytest.raises(m.PilotEventCompositionError):
            m.compose_pilot_entry_events(**changed)


def test_different_real_parent_population_does_not_become_same_corpus_by_reanchoring(ingredients, registered):
    arguments = _pair(ingredients, registered)
    other = _pair(ingredients, registered, shares={3:251})["first_open_source"]
    changed = {**arguments, "first_open_source":other,
        "trust_roots":replace(arguments["trust_roots"], first_open_source_sha256=other.sha256)}
    with pytest.raises(m.PilotEventCompositionError, match="same_full_original_population"):
        m.compose_pilot_entry_events(**changed)


@pytest.mark.parametrize("edit", [lambda row:row.update(stock_context_sha256="f"*64),
    lambda row:row.update(eligible_control_security_ids=["SID00","SID01","SID02"]),
    lambda row:row["stock_context"]["rows"][0].update(history=[]),
    lambda row:row.update(knowledge_at_utc="2023-01-13T14:30:00Z"),
    lambda row:row.update(entry_session="2023-01-16"), lambda row:row.update(trust_scope="production")])
def test_missing_or_future_complete_reference_never_becomes_eligibility(ingredients, registered, edit):
    with pytest.raises(m.PilotEventCompositionError):
        m.compose_pilot_entry_events(**_pair(ingredients, registered, reference_edit=edit))


def test_no_old_manifest_seal_or_outcome_surface_is_called(monkeypatch, ingredients, registered):
    def forbidden(*args, **kwargs):
        raise AssertionError("old full-study factory is forbidden")
    monkeypatch.setattr(m.causal, "_seal_validated_manifest", forbidden)
    monkeypatch.setattr(m.causal, "build_source_event_study_manifest_v2", forbidden)
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered))
    assert result.to_payload()["final_parent_and_event_inventory_registered"] is False
    assert result.to_payload()["actual_252_open_factor_intervals_verified"] is False
    assert result.to_payload()["both_earnings_diagnostics_evaluated"] is False
    assert result.to_payload()["order_engine_parity_verified"] is False


def test_seals_detach_views_and_refuse_reconstruction(ingredients, registered):
    result = m.compose_pilot_entry_events(**_pair(ingredients, registered))
    events = result.canonical_events()
    events[0]["score"] = "999"
    assert result.canonical_events()[0]["score"] != "999"
    with pytest.raises(m.PilotEventCompositionError, match="genuine_pilot_event"):
        replace(result).canonical_bytes()
    summary = result.to_payload()
    assert '"lots":' not in m._raw(summary).decode() and "purchase_value_usd" not in m._raw(summary).decode()
