"""Invented full census + genuinely parsed tiny per-decision original streams.

The upstream census fixture creates invented ZIP images under an outside-lane
temporary root. No retained artifact, provider, credential, QC or outcome input
is used. Production rejects these fixture seals rather than relabeling them.
"""
from dataclasses import replace
import hashlib
import json

import pytest

from data.hashing import hash_bytes, hash_payload

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_production_composition as m
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot, ParsedSecBulkAccession, _source_row_id,
)
from research.insider_buying.sec_ib1c_identity_v2 import assess_ib1c_v2_quarter_identity
from research.insider_buying.sec_ib1c_v2_downstream import build_v2_quarter_coverage, compose_v2_scope_coverage
from test_insider_buying_pilot_2021_2025 import _calendar, _entry
from test_insider_buying_pilot_sec_roster import corpus as roster_corpus, _args
from test_insider_buying_backtest_source_stream import _source_snapshot, _record
from test_insider_buying_sec_ib1c_v2_downstream import _binding


@pytest.fixture(scope="module")
def ingredients(roster_corpus):
    rows = []
    census = m.roster.derive_pilot_sec_roster(**_args(roster_corpus, rows.append))
    calendar = m._raw(_calendar())
    plan = m.pilot.freeze_pilot_2021_2025(calendar_raw=calendar, expected_calendar_sha256=hash_bytes(calendar))
    earnings = m._raw(m.pilot_earnings_contract(trust_scope="fixture", archive_inventory_sha256="a" * 64,
        source_semantics_sha256="b" * 64, exact_utc_implementation_sha256="c" * 64,
        interval_implementation_sha256="d" * 64))
    roots = m.PilotProductionTrustRoots("fixture", plan.sha256, census.sha256, hash_bytes(calendar),
        hash_bytes(earnings), "0" * 64, "0" * 64, "e" * 64, "f" * 64, "1" * 64)
    return {"pilot_plan": plan, "full_census": census, "calendar_raw": calendar,
            "earnings_contract_raw": earnings, "trust_roots": roots}, rows


def _registration_inputs(ingredients, *, edit_registration=None, edit_claim=None, **changes):
    arguments = {**ingredients[0], **changes}
    roots = arguments["trust_roots"]
    subject = m.describe_pilot_registration_subject(**arguments)
    claim = {"schema": m.LOOK_SCHEMA, "trust_scope": roots.trust_scope,
        "origin": "invented-permanent-pilot-look", "candidate_id": "invented-pilot", "registered_look_id": "invented-look",
        "subject_sha256": hash_payload(subject), "reserved_at_utc": "2026-10-24T00:00:00Z",
        "first_outcome_access_utc": "2026-10-26T00:00:00Z", "maximum_outcome_looks": 1,
        "consumed_outcome_looks": 0, "all_pilot_entries_share_this_look": True}
    if edit_claim:
        edit_claim(claim)
    claim_raw = m._raw(claim)
    registration = {"schema": m.REGISTRATION_SCHEMA, "trust_scope": roots.trust_scope,
        "candidate_id": "invented-pilot", "registered_look_id": "invented-look", "subject_sha256": hash_payload(subject),
        "permanent_look_claim_sha256": hash_bytes(claim_raw), "registered_at_utc": "2026-10-25T00:00:00Z",
        "first_outcome_access_utc": "2026-10-26T00:00:00Z"}
    if edit_registration:
        edit_registration(registration)
    registration_raw = m._raw(registration)
    arguments.update(registration_raw=registration_raw, permanent_look_claim_raw=claim_raw,
        trust_roots=replace(roots, registration_sha256=hash_bytes(registration_raw),
                            permanent_look_claim_sha256=hash_bytes(claim_raw)))
    return arguments


@pytest.fixture(scope="module")
def registered(ingredients):
    return m.bind_pilot_production_registration(**_registration_inputs(ingredients))


def _source(ingredients, entry="2023-02-24", *, cutoff=None, lower=None, raw_hash=None, future=False):
    """Use real upstream factories; no source seal or registration is forged."""
    plan = ingredients[0]["pilot_plan"]
    context = _entry(plan, entry=entry)
    assessment = m.pilot.assess_entry_context(plan=plan, metadata_raw=m._raw(context),
        expected_metadata_sha256=hash_bytes(m._raw(context))).to_payload()
    dates = [row["session"] for row in plan.to_payload()["calendar_sessions"]]
    lower = lower or dates[dates.index(entry) - 30]
    first = f"{lower[:4]}Q{(int(lower[5:7]) - 1) // 3 + 1}"
    last = f"{entry[:4]}Q{(int(entry[5:7]) - 1) // 3 + 1}"
    periods = tuple(p for p in m.roster.CONTEXT_PERIODS if first <= p <= last)
    census_rows = {row["period"]: row for row in ingredients[0]["full_census"].to_payload()["quarters"]}
    coverages, declarations, records = [], [], []
    for period in periods:
        public_rows = [row for row in ingredients[1] if row["period"] == period]
        specs = tuple((row["form_type"], row["filing_date"], row["raw_issuer_cik"], row["accession_number"],
                       row["filing_date"].replace("-", "") + "101112") for row in public_rows)
        if future:
            specs = tuple((form, "2023-03-01", issuer, accession, "20230301101112")
                          if form == "4" else (form, day, issuer, accession, accepted)
                          for form, day, issuer, accession, accepted in specs)
        snapshot, quarter = _source_snapshot(period, specs)
        original = census_rows[period]
        archive_hash = raw_hash or original["zip_sha256"]
        member_hash = original["submission_member_sha256"]
        rows = tuple(replace(row, row_id=_source_row_id(raw_snapshot_id=snapshot.identity.raw_snapshot_id,
            raw_lineage_hash=snapshot.identity.raw_lineage_hash, raw_archive_sha256=archive_hash,
            table_name="SUBMISSION.tsv", raw_member_sha256=member_hash, source_record_ordinal=row.source_record_ordinal,
            values=row.values, source_row_key=())) for row in snapshot.rows)
        table = replace(snapshot.identity.tables[0], raw_member_sha256=member_hash,
                        row_ids_hash=hash_payload([row.row_id for row in rows]))
        identity = replace(snapshot.identity, raw_archive_sha256=archive_hash,
            tables=(table, *snapshot.identity.tables[1:]), lineage_hash="", snapshot_id="")
        lineage = hash_payload(identity.lineage_payload())
        identity = replace(identity, lineage_hash=lineage, snapshot_id=f"sec-insider-parsed-{period.lower()}-{lineage[:16]}")
        accessions = tuple(ParsedSecBulkAccession(row.accession_number, row.values[3], row.row_id,
                          (("SUBMISSION.tsv", (row.row_id,)),)) for row in rows)
        snapshot = LoadedSecBulkParsedSnapshot(identity, rows, accessions)
        quarter = replace(quarter, zip_sha256=archive_hash, submission_member_sha256=member_hash)
        assessed = assess_ib1c_v2_quarter_identity(snapshot, quarter, ())
        coverage = build_v2_quarter_coverage(assessed, _binding(snapshot, assessed))
        coverages.append(coverage)
        relevant = [_record(period, spec) for spec in specs if spec[0] in {"4", "4/A"}]
        digest = hashlib.sha256()
        for record in relevant:
            digest.update(record.entry_bytes + b"\n")
        records.extend(relevant)
        declarations.append({"period": period, "coverage_sha256": coverage.sha256, "parent_count": len(relevant),
                             "ordered_parent_inventory_sha256": digest.hexdigest()})
    coverages = tuple(coverages)
    scope = compose_v2_scope_coverage(coverages, periods)
    population = m._raw({"schema": "insider-backtest-source-population-v2", "trust_scope": "fixture",
        "origin": "invented-complete-submission", "scope_sha256": scope.sha256,
        "expected_periods": list(periods), "quarters": declarations})
    source = m.stream.build_stream_source_evidence(coverages=coverages, expected_periods=periods,
        parent_records=iter(records), population_manifest=population, population_sha256=hash_bytes(population),
        trust_scope="fixture", lookback_start_session=lower, decision_session=entry,
        decision_cutoff_utc=cutoff or assessment["moo_prerequisite_cutoff_utc"])
    return {"source_evidence": source, "window_coverages": coverages, "entry_context_raw": m._raw(context),
            "expected_entry_context_sha256": hash_bytes(m._raw(context))}


def test_whole_pilot_registration_is_not_82quarter_completion_or_outcome_permission(registered, ingredients):
    body = registered.to_payload()
    assert body["subject"]["source_context_periods"] == list(m.roster.CONTEXT_PERIODS)
    assert len(body["subject"]["source_context_periods"]) == 25
    assert len(body["subject"]["pilot_periods"]) == 20
    assert body["full_census_counts"]["pilot_form4_or_4a_rows"] == 40  # Genuine INVENTED census.
    policy = body["subject"]["policy"]
    assert policy["pilot_phases"] == ingredients[0]["pilot_plan"].to_payload()["phases"]
    assert policy["alpha_allocated_this_pilot"] == [0, 1]
    assert policy["frozen_parent_economics"] == m.pilot.analysis.frozen_analysis_policy_v2()
    assert policy["original_study_replaced_or_completed"] is False
    assert body["backtesting_ready"] is body["permanent_look_authenticated_here"] is False
    assert body["research_looks_consumed"] == body["qc_jobs"] == body["backtests"] == 0


def test_actual_callable_genuine_window_parent_transaction_bridge_conserves_source_and_amendments(registered, ingredients):
    arguments = _source(ingredients)
    source = arguments["source_evidence"]
    assert source.transaction_rows()[0]["purchase_value_usd"] == "50000"
    result = m.compose_pilot_entry_source(registration=registered, **arguments)
    body = result.to_payload()
    assert result.source_evidence() is source
    assert body["source_periods"] == ["2023Q1"]  # Never force a 25-quarter source stream.
    assert body["window_source_submission_count"] == 6
    assert body["window_relevant_originals_verified"] == 2
    assert body["as_of_transaction_count"] == body["as_of_amendment_eligibility_not_evaluated_count"] == 1
    assert body["entry_context_assessment"]["metadata_disposition"] == "CONTEXT_METADATA_COMPLETE"
    assert body["genuine_window_original_source_bound"] is True
    for key in ("full_pilot_original_admission_complete", "causal_lots_and_events_composed", "actual_price_listing_context_verified",
                "earnings_evaluated", "interval_production_analyzer_enabled", "backtesting_ready", "outcome_access_authorized_here"):
        assert body[key] is False


def test_quarter_crossing_and_future_source_facts_are_not_backdated(registered, ingredients):
    arguments = _source(ingredients, entry="2023-01-05")
    assert m.compose_pilot_entry_source(registration=registered, **arguments).to_payload()["source_periods"] == ["2022Q4", "2023Q1"]
    later = _source(ingredients, future=True)
    result = m.compose_pilot_entry_source(registration=registered, **later)
    assert result.to_payload()["future_parent_count"] == 1
    assert result.to_payload()["as_of_transaction_count"] == 0
    assert result.source_evidence().transaction_rows() == []


@pytest.mark.parametrize("cutoff", ["2023-02-24T14:27:59Z", "2023-02-24T14:28:01Z", "2023-02-24T14:30:00Z"])
def test_exact_moo_cutoff_not_just_before_open(registered, ingredients, cutoff):
    with pytest.raises(m.PilotCompositionError, match="exact_causal_window_and_moo_cutoff_required"):
        m.compose_pilot_entry_source(registration=registered, **_source(ingredients, cutoff=cutoff))


def test_window_exact_inclusive30_and_raw_source_link_not_matching_counts(registered, ingredients):
    for changes, code in (({"lower": "2023-01-12"}, "exact_causal_window"), ({"raw_hash": "9" * 64}, "raw_source_differs")):
        with pytest.raises(m.PilotCompositionError, match=code):
            m.compose_pilot_entry_source(registration=registered, **_source(ingredients, **changes))


@pytest.mark.parametrize("field,value", [("maximum_outcome_looks", True), ("maximum_outcome_looks", 2),
    ("consumed_outcome_looks", False), ("consumed_outcome_looks", 1), ("all_pilot_entries_share_this_look", 1),
    ("subject_sha256", "2" * 64), ("registered_look_id", "different-look"), ("origin", "externally-anchored-permanent-pilot-look"),
    ("reserved_at_utc", "2026-10-25T00:00:01Z"), ("first_outcome_access_utc", "2026-10-25T00:00:00Z")])
def test_rehashed_claim_does_not_bypass_fixed_budget_subject_or_clocks(ingredients, field, value):
    with pytest.raises(m.PilotCompositionError):
        m.bind_pilot_production_registration(**_registration_inputs(ingredients, edit_claim=lambda x:x.update({field:value})))


@pytest.mark.parametrize("field,value", [("candidate_id", "different"), ("subject_sha256", "2" * 64),
    ("first_outcome_access_utc", "2026-10-25T00:00:00Z"), ("registered_at_utc", "2026-10-26T00:00:00Z"),
    ("registered_at_utc", "2026-10-25T00:00:00"), ("permanent_look_claim_sha256", "8" * 64),
    ("trust_scope", "production"), ("schema", "old-full-study-registration")])
def test_rehashed_registration_cannot_relabel_epoch_or_backdate(ingredients, field, value):
    with pytest.raises(m.PilotCompositionError):
        m.bind_pilot_production_registration(**_registration_inputs(ingredients, edit_registration=lambda x:x.update({field:value})))


@pytest.mark.parametrize("field,value", [("windows_sessions", [2]), ("windows_inclusive", 1),
    ("earnings_used_for_primary_selection", True), ("earnings_used_for_execution_clock", True),
    ("missing_coverage", "partial-is-fine"), ("source_version_policy", "require-universal-as-known-forecast"),
    ("processing_scope", "upload-to-qc"), ("archive_inventory_sha256", True), ("extra", "not-permitted")])
def test_both_local_earnings_contracts_remain_fixed_even_when_reanchored(ingredients, field, value):
    earnings = json.loads(ingredients[0]["earnings_contract_raw"])
    earnings[field] = value
    raw = m._raw(earnings)
    arguments = {**ingredients[0], "earnings_contract_raw": raw,
                 "trust_roots": replace(ingredients[0]["trust_roots"], earnings_contract_sha256=hash_bytes(raw))}
    with pytest.raises(m.PilotCompositionError):
        m.describe_pilot_registration_subject(**arguments)


def test_fixture_full_census_cannot_be_promoted_to_production(ingredients):
    earnings = json.loads(ingredients[0]["earnings_contract_raw"])
    earnings["trust_scope"] = "production"
    raw = m._raw(earnings)
    arguments = {**ingredients[0], "earnings_contract_raw": raw,
        "trust_roots": replace(ingredients[0]["trust_roots"], trust_scope="production", earnings_contract_sha256=hash_bytes(raw))}
    with pytest.raises(m.PilotCompositionError, match="fixture_production_scope_mismatch"):
        m.describe_pilot_registration_subject(**arguments)


def test_no_reconstructed_or_mutated_factories_and_detached_payloads(registered, ingredients):
    copied = replace(registered)
    with pytest.raises(m.PilotCompositionError, match="genuine_pilot_registration_required"):
        copied.to_payload()
    output = registered.to_payload()
    output["subject"]["policy"]["alpha_spent"] = [1, 1]
    assert registered.to_payload()["subject"]["policy"]["alpha_spent"] == [0, 1]
    arguments = _source(ingredients)
    result = m.compose_pilot_entry_source(registration=registered, **arguments)
    with pytest.raises(m.PilotCompositionError, match="genuine_pilot_entry_composition_required"):
        replace(result).to_payload()
    source = arguments["source_evidence"]
    changed = replace(source)
    with pytest.raises(m.PilotCompositionError, match="genuine_source"):
        m.compose_pilot_entry_source(registration=registered, **{**arguments, "source_evidence": changed})


def test_missing_or_dictionary_source_is_not_admission_and_coverages_are_genuine(registered, ingredients):
    arguments = _source(ingredients)
    for source in (None, arguments["source_evidence"].to_payload()):
        with pytest.raises(m.PilotCompositionError, match="genuine_source"):
            m.compose_pilot_entry_source(registration=registered, **{**arguments, "source_evidence": source})
    for coverages in (None, [], (), (arguments["window_coverages"][0].to_payload(),)):
        with pytest.raises(m.PilotCompositionError):
            m.compose_pilot_entry_source(registration=registered, **{**arguments, "window_coverages": coverages})


def test_another_genuine_contiguous_window_cannot_replace_exact_required_coverages(registered, ingredients):
    arguments = _source(ingredients)
    # Another genuinely built source window has an extra complete quarter. It
    # cannot replace this entry's exact source scope despite sharing Q1 bytes.
    wrong = _source(ingredients, entry="2023-01-05")["window_coverages"]
    with pytest.raises(m.PilotCompositionError, match="scope"):
        m.compose_pilot_entry_source(registration=registered, **{**arguments, "window_coverages": wrong})


def test_pilot_schedule_exclusions_remain_bookkeeping_not_silently_deleted(registered, ingredients):
    arguments = _source(ingredients, entry="2024-01-02")
    result = m.compose_pilot_entry_source(registration=registered, **arguments).to_payload()
    context = result["entry_context_assessment"]
    assert context["metadata_disposition"] == "EXCLUDED_METADATA"
    assert "embargo_first60_phase_sessions" in context["exclusion_reasons"]
    assert result["window_relevant_originals_verified"] == 4
    assert result["full_pilot_original_admission_complete"] is False


def test_missing_reference_metadata_and_out_of_pilot_context_refuse(registered, ingredients):
    arguments = _source(ingredients)
    for edit in (lambda row:row.pop("listing_evidence_sha256"), lambda row:row.update(prior_listed_sessions=[]),
                 lambda row:row.update(entry_session="2020-12-31"),
                 lambda row:row.update(context_known_at_utc="2023-02-24T14:28:01Z")):
        context = json.loads(arguments["entry_context_raw"])
        edit(context)
        raw = m._raw(context)
        with pytest.raises(m.PilotCompositionError, match="complete_entry_context"):
            m.compose_pilot_entry_source(registration=registered, **{**arguments, "entry_context_raw":raw,
                "expected_entry_context_sha256":hash_bytes(raw)})


def test_canonical_controls_duplicate_keys_bad_hashes_and_bounds_refuse():
    for raw in (b'{"a":1,"a":2}', b'{ "a": 1 }', b'{"a":NaN}', b'[]', b'{"a":Infinity}', b'\xff'):
        with pytest.raises(m.PilotCompositionError):
            m._decode(raw, hash_bytes(raw))
    with pytest.raises(m.PilotCompositionError):
        m._decode(b"{}", "0" * 64)
    with pytest.raises(m.PilotCompositionError):
        m._decode(b"x" * (m.MAX_CONTROL_BYTES + 1), "0" * 64)
