"""Explicit invented originals and fixed fixture roots; no production relabeling."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
from zoneinfo import ZoneInfo

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying import backtest_evidence_pipeline as module
from research.insider_buying.sec_complete_submission import project_sec_complete_submission
from research.insider_buying.sec_ib1c_identity_v2 import assess_ib1c_v2_quarter_identity
from research.insider_buying.sec_ib1c_v2_downstream import build_v2_quarter_coverage
from test_insider_buying_sec_complete_submission import _complete, _header, _target
from test_insider_buying_sec_ib1c_identity_v2 import _inputs
from test_insider_buying_sec_ib1c_v2_downstream import _binding, _coverage
from test_insider_buying_qc_stock_order_study import study  # exact standalone QC parser, mocked LEAN only


def _bytes(value):
    return canonical_json(value).encode("utf-8")


def _reanchor(kwargs, **changed):
    result = dict(kwargs)
    result.update(changed)
    result["trust_roots"] = module.EvidenceTrustRoots("fixture", *(hash_bytes(result[name]) for name in (
        "source_manifest", "security_master", "calendar", "authorization")))
    return result


def _edit(kwargs, name, edit, *, crossbind=False):
    body = json.loads(kwargs[name])
    edit(body)
    result = _reanchor(kwargs, **{name: _bytes(body)})
    if crossbind and name in {"source_manifest", "security_master", "calendar"}:
        auth = json.loads(result["authorization"])
        if name == "calendar":
            auth["calendar_sha256"] = hash_bytes(json.dumps([r["session"] for r in body["sessions"]], separators=(",", ":")).encode())
        else:
            auth[name + "_sha256"] = hash_bytes(result[name])
        result = _reanchor(result, authorization=_bytes(auth))
    return result


def make_pipeline_fixture(overrides=None):
    """Public test-only helper returning genuine invented-byte build kwargs.

    Every coverage corroboration comes from these exact original parent images.
    The factory never labels a retained real input or an old fixture event as a
    source-authenticated production input. ``overrides`` changes invented XML
    source facts before the source assessment and trust artifacts are built.
    """
    options = {} if overrides is None else dict(overrides)
    count = options.get("stocks", 20)
    members = options.get("members", 2)
    forms = options.get("forms", {})
    filed = options.get("filed", {})
    specs = [(forms.get(index, "4"), filed.get(index, "2023-01-15"), str(123456 + index // members), "23")
             for index in range(count * members)]
    if options.get("all_six"):
        specs += [(form, "2023-01-15", "999999", "23") for form in ("3", "3/A", "5", "5/A")]
    snapshot, census = _inputs(tuple(specs))
    parents = []
    for index, row in enumerate(snapshot.rows[:count * members]):
        issuer = row.values[4].zfill(10)
        owner = options.get("owner", {}).get(index, f"{900000 + index % members:010d}")
        form, day = row.values[3], row.values[1]
        day_digits = day.replace("-", "")
        acceptance = options.get("acceptance", {}).get(index, day_digits + "101112")
        owners = (owner, "0000900999") if index in options.get("joint", ()) else (owner,)
        owner_xml = "".join(f"<reportingOwner><reportingOwnerId><rptOwnerCik>{cik}</rptOwnerCik><rptOwnerName>Invented Officer</rptOwnerName></reportingOwnerId><reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><isTenPercentOwner>0</isTenPercentOwner><isOther>0</isOther></reportingOwnerRelationship></reportingOwner>" for cik in owners)
        shares = options.get("shares", {}).get(index, "500")
        price = options.get("price", {}).get(index, str(100 + index // members * 10))
        transaction_day = options.get("transaction_day", {}).get(index, "2023-01-13")
        code = options.get("code", {}).get(index, "P")
        txn = f"<nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>{transaction_day}</value></transactionDate><transactionCoding><transactionCode>{code}</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>{shares}</value></transactionShares><transactionPricePerShare><value>{price}</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts><postTransactionAmounts><sharesOwnedFollowingTransaction><value>10000</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeTransaction></nonDerivativeTable>"
        if index in options.get("no_transactions", ()):
            txn = ""
        xml = f'<ownershipDocument><documentType>{form}</documentType><issuer><issuerCik>{issuer}</issuerCik><issuerName>Invented Issuer</issuerName><issuerTradingSymbol>T{index // members:02d}</issuerTradingSymbol></issuer>{owner_xml}{txn}</ownershipDocument>\n'.encode()
        header = (_header(owners).replace(b"0000999999-22-000001", row.accession_number.encode())
                  .replace(b"20221107101112", acceptance.encode()).replace(b"20221107", day_digits.encode())
                  .replace(b"<CIK>0000123456", b"<CIK>" + issuer.encode()).replace(b"<TYPE>4\n", f"<TYPE>{form}\n".encode()))
        raw = (_complete(header=header, xml=xml).replace(b"<TYPE>4\n", f"<TYPE>{form}\n".encode())
               .replace(b"0000999999-22-000001", row.accession_number.encode()).replace(b"20221107", day_digits.encode()))
        target = replace(_target(), period="2023Q1", accession_number=row.accession_number,
                         form_type=form, filing_date=day, issuer_cik=issuer,
                         complete_submission_url="https://www.sec.gov/Archives/edgar/data/888888/" + row.accession_number + ".txt")
        parents.append(project_sec_complete_submission(target, raw))
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census, tuple(parent for index, parent in enumerate(parents) if index not in options.get("omit_parents", ())))
    coverage = build_v2_quarter_coverage(assessment, _binding(snapshot, assessment))
    sessions = []
    current = date(2022, 11, 28)
    eastern = ZoneInfo("America/New_York")
    while len(sessions) < options.get("calendar_sessions", 140):
        if current.weekday() < 5:
            sessions.append({"session": current.isoformat(),
                "open_utc": datetime(current.year, current.month, current.day, 9, 30, tzinfo=eastern).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "close_utc": datetime(current.year, current.month, current.day, 16, tzinfo=eastern).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        current += timedelta(days=1)
    source = {"schema": "insider-backtest-source-manifest-v1", "trust_scope": "fixture",
        "coverage_sha256": coverage.sha256, "origin": "invented-complete-submission", "parents": []}
    for parent in parents:
        source["parents"].append({"target": parent.target.to_payload(), "projection_sha256": parent.sha256,
            "parent_sha256": hash_bytes(parent.raw_bytes), "header_sha256": hash_bytes(parent.header_bytes),
            "xml_sha256": hash_bytes(parent.xml_bytes), "official_acceptance_utc": datetime.strptime(parent.accepted_at_raw, "%Y%m%d%H%M%S").replace(tzinfo=eastern).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    mappings = [{"issuer_cik": f"{123456 + index:010d}", "qc_symbol_id": f"SID{index:02d}", "ticker": f"T{index:02d}",
        "security_title": "Common Stock", "share_class": "ordinary-A", "security_class": "common_stock",
        "country": "US", "venue": "XNAS", "mapping_first_session": "2023-01-01", "mapping_last_session": "2024-01-01",
        "knowledge_at_utc": "2023-01-01T00:00:00Z"} for index in range(options.get("universe", count))]
    security = {"schema": "insider-backtest-security-master-v1", "trust_scope": "fixture", "mappings": mappings, "source_exclusions": []}
    calendar = {"schema": "insider-backtest-calendar-v1", "trust_scope": "fixture", "sessions": sessions}
    auth = {"schema": "insider-backtest-authorization-v1", "trust_scope": "fixture", "scope": "single-research-backtest-only",
        "registered_look_id": "invented-study-1", "source_manifest_sha256": hash_bytes(_bytes(source)),
        "security_master_sha256": hash_bytes(_bytes(security)),
        "calendar_sha256": hash_bytes(json.dumps([r["session"] for r in sessions], separators=(",", ":")).encode()),
        "outcome_vintage_sha256": "1" * 64, "rights_record_sha256": "2" * 64,
        "rights_representation": "local-and-quantconnect", "decision_session": sessions[options["decision_index"]]["session"] if "decision_index" in options else "2023-02-24",
        "qc_entitlement_sha256": "3" * 64, "delisting_sha256": "4" * 64,
        "adjustments_sha256": "5" * 64, "protocol_sha256": "6" * 64}
    return _reanchor({"coverage": coverage, "parent_images": tuple(parent.raw_bytes for parent in parents),
        "source_manifest": _bytes(source), "security_master": _bytes(security), "calendar": _bytes(calendar), "authorization": _bytes(auth)})


def test_original_parent_positive_path_derives_real_nonzero_scores_and_frozen_qc_manifest(study):
    kwargs = make_pipeline_fixture()
    result = module.build_evidence_pipeline(**kwargs)
    summary = result.to_payload()
    assert summary["bounded_pipeline_complete"] is True and summary["complete_project_backtesting_readiness"] is False
    assert summary["production_evidence_scope"] is False and summary["trust_scope"] == "fixture"
    assert summary["source_submission_count"] == summary["admitted_event_count"] == 40
    assert summary["scored_stock_count"] == 20 and summary["signal_count"] == 20
    assert summary["qc_jobs"] == summary["research_looks"] == 0
    assert summary["timing_policy"] == "daily_regular_close_score_snapshot_then_next_session_open"
    assert summary["literal_first_open_after_each_acceptance"] is False
    assert all(Decimal(row["raw_stock_score"]) > 0 for row in result.scored_rows())
    expected = module.formula._event_formula(Decimal(50000), 29)
    assert result.admitted_events()[0]["event_score"] == str(expected[2])
    assert [row["ticker"] for row in result.scored_rows() if row["buyer_cluster_selected"]] == ["T18", "T19"]
    raw = result.signal_manifest_bytes()
    parsed = study.parse_study_manifest(raw, hash_bytes(raw))
    assert len(parsed.signals) == 20
    assert set(result.signals()[0]) == set(module.json.loads(raw)["signals"][0])


def test_all_six_denominator_with_unsupported_forms_retained_does_not_make_form4_path_impossible():
    kwargs = make_pipeline_fixture({"all_six": True})
    result = module.build_evidence_pipeline(**kwargs)
    body = result.to_payload()
    assert body["source_submission_count"] == 44 and body["relevant_form4_count"] == 40
    assert body["source_quarantined_count"] == 4 and body["whole_quarter_source_identity_sha256"] is None
    assert body["source_form_counts"] == {"3": 1, "3/A": 1, "4": 40, "4/A": 0, "5": 1, "5/A": 1}
    assert body["source_quarantine_reason_counts"]["unsupported_parent_corroboration_form"] == 4
    assert sum(body["source_quarantine_reason_counts"].values()) == 4
    assert body["signal_count"] == 20


def test_all_quarantined_handoff_never_evaluates_actual_financial_eligibility():
    coverage = _coverage(tuple((form, "2023-01-15", "123456", "23") for form in ("3", "3/A", "4", "4/A", "5", "5/A")), parents=False)
    body = module.analyze_v2_coverage(coverage)
    assert body["submission_count"] == body["quarantined_count"] == 6
    assert body["eligible_events_evaluated"] is False and body["admitted_event_count"] == 0
    assert body["backtesting_ready"] is False and len(body["missing_evidence"]) == 4
    assert body["source_identity_sha256"] is None and body["relevant_form4_identity_complete"] is False
    kwargs = make_pipeline_fixture()
    with pytest.raises(module.EvidencePipelineError, match="complete nonempty Form4"):
        module.build_evidence_pipeline(**{**kwargs, "coverage": coverage})


def test_sealed_output_is_detached_and_replacement_or_duck_type_cannot_bypass_admission():
    result = module.build_evidence_pipeline(**make_pipeline_fixture())
    summary = result.to_payload(); summary["trust_scope"] = "production"
    rows = result.signals(); rows[0]["ticker"] = "FORGED"
    assert result.to_payload()["trust_scope"] == "fixture" and result.signals()[0]["ticker"] != "FORGED"
    with pytest.raises(module.EvidencePipelineError):
        replace(result).to_payload()
    with pytest.raises(module.EvidencePipelineError):
        module.validate_evidence_pipeline(result.to_payload())
    # Alter both object-local seals: the independent factory registration still refuses.
    body = json.loads(result._bytes)
    body["manifest"]["signals"] = body["manifest"]["signals"][:1]
    altered = _bytes(body)
    object.__setattr__(result, "_bytes", altered)
    object.__setattr__(result, "_factory_bytes", altered)
    with pytest.raises(module.EvidencePipelineError):
        module.validate_evidence_pipeline(result)


@pytest.mark.parametrize("name", ["source_manifest", "security_master", "calendar", "authorization"])
def test_unchanged_external_roots_reject_any_artifact_byte_substitution(name):
    kwargs = make_pipeline_fixture()
    kwargs[name] += b" "
    with pytest.raises(module.EvidencePipelineError, match="external trust root"):
        module.build_evidence_pipeline(**kwargs)


@pytest.mark.parametrize("edit", [
    lambda b: b["parents"].pop(), lambda b: b["parents"].reverse(),
    lambda b: b["parents"].append(b["parents"][0]),
    lambda b: b.update(coverage_sha256="f" * 64),
    lambda b: b["parents"][0].update(header_sha256="f" * 64),
    lambda b: b["parents"][0].update(official_acceptance_utc="2023-01-15T15:11:13Z"),
    lambda b: b["parents"][0].pop("official_acceptance_utc"),
    lambda b: b["parents"][0]["target"].update(issuer_cik="0000999999"),
    lambda b: b.update(origin="sec-original-complete-submission"),
])
def test_reanchored_invented_manifest_still_requires_complete_original_source_semantics(edit):
    kwargs = _edit(make_pipeline_fixture(), "source_manifest", edit, crossbind=True)
    with pytest.raises(module.EvidencePipelineError):
        module.build_evidence_pipeline(**kwargs)


@pytest.mark.parametrize("edit", [
    lambda b: b["mappings"].pop(), lambda b: b["mappings"].reverse(),
    lambda b: b["mappings"][0].update(ticker="T01"),
    lambda b: b["mappings"][0].update(qc_symbol_id="SID01"),
    lambda b: b["mappings"][0].update(country="CA"),
    lambda b: b["mappings"][0].update(venue="XTSE"),
    lambda b: b["mappings"][0].update(security_class="preferred_stock"),
    lambda b: b["mappings"][0].update(security_title="Class B Common Stock"),
    lambda b: b["mappings"][0].update(knowledge_at_utc="2023-02-24T22:00:00Z"),
    lambda b: b["mappings"][0].update(knowledge_at_utc="2023-01-15T16:00:00Z"),
    lambda b: b["mappings"][0].update(mapping_last_session="2023-02-01"),
    lambda b: b["mappings"][0].update(mapping_first_session="2023-01-16"),
])
def test_reanchored_mapping_refuses_future_or_ambiguous_shareclass_ticker_country_horizon(edit):
    kwargs = _edit(make_pipeline_fixture(), "security_master", edit, crossbind=True)
    with pytest.raises(module.EvidencePipelineError):
        module.build_evidence_pipeline(**kwargs)


@pytest.mark.parametrize("edit", [
    lambda b: b["sessions"].reverse(), lambda b: b["sessions"].append(b["sessions"][-1]),
    lambda b: b["sessions"][0].update(open_utc="2023-01-16T14:29:00Z"),
    lambda b: b["sessions"][4].update(close_utc="2023-01-20T22:00:00Z"),
    lambda b: b["sessions"][0].update(open_utc="2023-01-17T14:30:00Z"),
    lambda b: b.update(sessions=b["sessions"][:21]),
])
def test_verified_calendar_refuses_future_date_cutoff_and_nonregular_sessions(edit):
    with pytest.raises(module.EvidencePipelineError):
        module.build_evidence_pipeline(**_edit(make_pipeline_fixture(), "calendar", edit, crossbind=True))


@pytest.mark.parametrize("edit", [
    lambda b: b.update(scope="paper-live"), lambda b: b.update(rights_representation="local-only"),
    lambda b: b.update(source_manifest_sha256="f" * 64), lambda b: b.update(calendar_sha256="f" * 64),
    lambda b: b.update(rights_record_sha256=True), lambda b: b.update(registered_look_id=""),
    lambda b: b.update(decision_session="2024-01-01"), lambda b: b.pop("protocol_sha256"),
    lambda b: b.update(qc_authorized=True), lambda b: b.update(trust_scope="production"),
])
def test_authorization_exact_content_not_flags_or_digest_names(edit):
    with pytest.raises(module.EvidencePipelineError):
        module.build_evidence_pipeline(**_edit(make_pipeline_fixture(), "authorization", edit))


def test_any_amendment_even_empty_excludes_whole_issuer_family_not_only_its_transaction_rows():
    kwargs = make_pipeline_fixture({"forms": {39: "4/A"}, "no_transactions": (39,)})
    result = module.build_evidence_pipeline(**kwargs)
    assert result.to_payload()["excluded_reason_counts"]["amended_issuer_family"] == 2
    assert not any(row["qc_symbol_id"] == "SID19" for row in result.admitted_events())
    assert next(row for row in result.scored_rows() if row["qc_symbol_id"] == "SID19")["structural_zero"] is True


def test_joint_owner_is_excluded_without_arbitrary_owner_choice():
    result = module.build_evidence_pipeline(**make_pipeline_fixture({"joint": (0,)}))
    assert result.to_payload()["excluded_reason_counts"]["joint_or_missing_reporting_owner"] == 1
    assert sum(event["qc_symbol_id"] == "SID00" for event in result.admitted_events()) == 1


def test_threshold_applies_after_exact_lot_aggregation_and_latest_public_member_activation():
    kwargs = make_pipeline_fixture({"shares": {0: "300", 1: "300"}, "price": {0: "100", 1: "100"},
                                    "filed": {1: "2023-01-18"}, "acceptance": {1: "20230118170000"}})
    # Independent owner lots below $50k are NOT combined across owners.
    result = module.build_evidence_pipeline(**kwargs)
    assert not any(event["qc_symbol_id"] == "SID00" for event in result.admitted_events())
    assert result.to_payload()["excluded_reason_counts"]["below_post_aggregation_threshold"] == 2


def test_future_acceptance_and_future_amendment_refuse_instead_of_altering_past_score():
    for forms in ({}, {39: "4/A"}):
        kwargs = make_pipeline_fixture({"forms": forms, "filed": {39: "2023-03-15"}})
        with pytest.raises(module.EvidencePipelineError, match="future acceptance"):
            module.build_evidence_pipeline(**kwargs)


def test_late_reported_member_freshness_uses_first_close_after_acceptance_not_transaction_date():
    kwargs = make_pipeline_fixture({"filed": {0: "2023-01-18"}, "acceptance": {0: "20230118170000"}})
    event = next(event for event in module.build_evidence_pipeline(**kwargs).admitted_events() if event["qc_symbol_id"] == "SID00" and event["owner_cik"] == "0000900000")
    assert event["activation_session"] == "2023-01-19" and event["age_trading_days"] == 26
    assert event["freshness"] == str(module.formula._event_formula(Decimal(50000), 26)[1])


@pytest.mark.parametrize("raw,official", [("20230312023000", "2023-03-12T07:30:00Z"), ("20231105013000", "2023-11-05T05:30:00Z"), ("20230115", "2023-01-15T00:00:00Z")])
def test_dateonly_nonexistent_and_ambiguous_eastern_times_refuse(raw, official):
    with pytest.raises(module.EvidencePipelineError):
        module._acceptance(raw, official)


def test_dst_regular_session_conversion_is_checked_not_fixed_utc_offset():
    kwargs = make_pipeline_fixture()
    body = json.loads(kwargs["calendar"])
    # The fixture spans March's DST change. Monday 13 March opens 13:30Z.
    record = next(row for row in body["sessions"] if row["session"] == "2023-03-13")
    assert record["open_utc"] == "2023-03-13T13:30:00Z"
    record["open_utc"] = "2023-03-13T14:30:00Z"
    with pytest.raises(module.EvidencePipelineError, match="regular US session"):
        module.build_evidence_pipeline(**_reanchor(kwargs, calendar=_bytes(body)))


def test_scalar_flags_fixture_roots_or_plain_payload_cannot_establish_production_evidence():
    kwargs = make_pipeline_fixture()
    kwargs["trust_roots"] = replace(kwargs["trust_roots"], trust_scope="production")
    with pytest.raises(module.EvidencePipelineError, match="trust scope"):
        module.build_evidence_pipeline(**kwargs)
    for roots in (True, kwargs["trust_roots"].to_payload(), "a" * 64):
        with pytest.raises(module.EvidencePipelineError):
            module.build_evidence_pipeline(**{**kwargs, "trust_roots": roots})


@pytest.mark.parametrize("change", ["parents", "json_duplicate", "bool_scope", "empty_cohort"])
def test_bounded_source_and_nonempty_real_seed_path_fail_closed(change):
    kwargs = make_pipeline_fixture()
    if change == "parents":
        kwargs["parent_images"] = kwargs["parent_images"] * 257
    elif change == "json_duplicate":
        raw = kwargs["authorization"].replace(b'"scope":', b'"scope":"wrong","scope":')
        kwargs = _reanchor(kwargs, authorization=raw)
    elif change == "bool_scope":
        with pytest.raises(module.EvidencePipelineError):
            module.EvidenceTrustRoots(True, *("a" * 64 for _ in range(4)))
        return
    elif change == "empty_cohort":
        kwargs = _edit(kwargs, "security_master", lambda b: b.update(mappings=[]), crossbind=True)
    with pytest.raises(module.EvidencePipelineError):
        module.build_evidence_pipeline(**kwargs)


def test_complete_eligible_universe_includes_eighteen_genuine_no_filing_structural_zeros():
    result = module.build_evidence_pipeline(**make_pipeline_fixture({"stocks": 2, "universe": 20}))
    assert result.to_payload()["signal_count"] == 2 and result.to_payload()["source_submission_count"] == 4
    assert sum(row["structural_zero"] for row in result.scored_rows()) == 18
    assert all(row["raw_stock_score"] == "0" for row in result.scored_rows()[2:])


def test_one_buyer_and_unavailable_seed_diagnostics_do_not_filter_the_stock_primary():
    result = module.build_evidence_pipeline(**make_pipeline_fixture({"members": 1, "stocks": 1, "universe": 20}))
    assert result.to_payload()["signal_count"] == 1
    assert result.to_payload()["seed_diagnostic_available"] is False
    assert result.to_payload()["buyer_cluster_diagnostic_available"] is False
    assert result.scored_rows()[0]["stock_primary_selected"] is True
    assert result.scored_rows()[0]["buyer_breadth"] == 1


def test_same_owner_lot_combines_below_threshold_members_without_backdating_latest_availability():
    kwargs = make_pipeline_fixture({"shares": {0: "300", 1: "300"}, "price": {0: "100", 1: "100"},
        "owner": {1: "0000900000"}, "filed": {1: "2023-01-18"}, "acceptance": {1: "20230118170000"}})
    result = module.build_evidence_pipeline(**kwargs)
    stock = [event for event in result.admitted_events() if event["qc_symbol_id"] == "SID00"]
    assert len(stock) == 1 and stock[0]["purchase_value_usd"] == "60000"
    assert len(stock[0]["member_event_ids"]) == 2
    assert stock[0]["activation_session"] == "2023-01-19" and stock[0]["age_trading_days"] == 26


def test_missing_predecision_calendar_context_cannot_reset_old_events_to_age_zero():
    kwargs = make_pipeline_fixture()
    body = json.loads(kwargs["calendar"])
    body["sessions"] = body["sessions"][35:]
    changed = _edit(kwargs, "calendar", lambda b: b.update(sessions=body["sessions"]), crossbind=True)
    with pytest.raises(module.EvidencePipelineError, match="pre-decision lookback context"):
        module.build_evidence_pipeline(**changed)


def test_none_reason_cannot_silently_exclude_an_ordinary_us_source_issuer():
    def edit(body):
        dropped = body["mappings"].pop(0)
        body["source_exclusions"].append({"issuer_cik": dropped["issuer_cik"],
            "security_class": "common_stock", "country": "US", "reason": None})
    with pytest.raises(module.EvidencePipelineError, match="ordinary US stock"):
        module.build_evidence_pipeline(**_edit(make_pipeline_fixture(), "security_master", edit, crossbind=True))


def test_complete_relevant_population_cannot_drop_one_missing_form4_parent():
    with pytest.raises(module.EvidencePipelineError, match="complete nonempty Form4"):
        module.build_evidence_pipeline(**make_pipeline_fixture({"omit_parents": (0,)}))


def test_valid_externally_bound_foreign_source_exclusion_is_named_not_silent():
    def edit(body):
        dropped = body["mappings"].pop(0)
        body["source_exclusions"].append({"issuer_cik": dropped["issuer_cik"],
            "country": "CA", "security_class": "common_stock", "reason": "non_us_security"})
    result = module.build_evidence_pipeline(**_edit(make_pipeline_fixture(), "security_master", edit, crossbind=True))
    assert result.to_payload()["excluded_reason_counts"]["noneligible_source_security"] == 2
    assert result.to_payload()["source_submission_count"] == 40
    assert result.to_payload()["signal_count"] == 19


def test_pre2006_and_openfuture_reference_mapping_dates_do_not_extend_source_event_window():
    def edit(body):
        for mapping in body["mappings"]:
            mapping["mapping_first_session"] = "1990-01-01"
            mapping["mapping_last_session"] = "9999-12-31"
    result = module.build_evidence_pipeline(**_edit(make_pipeline_fixture(), "security_master", edit, crossbind=True))
    assert result.to_payload()["source_submission_count"] == 40
    assert all(row["mapping_first_session"] == "1990-01-01" for row in result.signals())


def test_verified_31_session_age_has_no_event_or_primary_signal_even_with_old_transaction():
    kwargs = make_pipeline_fixture()
    sessions = json.loads(kwargs["calendar"])["sessions"]
    activation = next(index for index, row in enumerate(sessions) if row["session"] == "2023-01-16")
    target = sessions[activation + 31]["session"]
    changed = _edit(kwargs, "authorization", lambda body: body.update(decision_session=target))
    with pytest.raises(module.EvidencePipelineError, match="nonempty stock primary"):
        module.build_evidence_pipeline(**changed)


def test_nonempty_primary_capacity_is_refused_not_truncated_or_reseeded():
    with pytest.raises(module.EvidencePipelineError, match="QC capacity"):
        module.build_evidence_pipeline(**make_pipeline_fixture({"stocks": 21}))


@pytest.mark.parametrize("field,value", [("venue", []), ("security_title", "Common Stock\x00"),
    ("security_title", "Ｃommon Stock"), ("mapping_first_session", True)])
def test_nested_mapping_shapes_and_titles_have_named_refusal(field, value):
    with pytest.raises(module.EvidencePipelineError):
        module.build_evidence_pipeline(**_edit(make_pipeline_fixture(), "security_master",
            lambda body: body["mappings"][0].update({field: value}), crossbind=True))


def test_previous_quarter_lookback_inventory_cannot_be_inferred_from_calendar_history():
    kwargs = _edit(make_pipeline_fixture(), "authorization", lambda body: body.update(decision_session="2023-01-20"))
    with pytest.raises(module.EvidencePipelineError, match="complete 30-session source window"):
        module.build_evidence_pipeline(**kwargs)


def test_after_quarter_decision_cannot_infer_next_quarter_source_inventory():
    kwargs = make_pipeline_fixture({"calendar_sessions": 140,
        "filed": dict.fromkeys(range(40), "2023-03-30")})
    kwargs = _edit(kwargs, "authorization", lambda body: body.update(decision_session="2023-04-28"))
    with pytest.raises(module.EvidencePipelineError, match="complete 30-session source window"):
        module.build_evidence_pipeline(**kwargs)


def test_math_is_ambient_context_independent_and_frozen_policy_drift_refuses(monkeypatch):
    kwargs = make_pipeline_fixture()
    baseline = module.build_evidence_pipeline(**kwargs)
    with localcontext() as context:
        context.prec = 7
        assert module.build_evidence_pipeline(**kwargs).sha256 == baseline.sha256
    monkeypatch.setattr(module.seed, "FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR", 5)
    with pytest.raises(ValueError, match="frozen"):
        module.build_evidence_pipeline(**kwargs)
