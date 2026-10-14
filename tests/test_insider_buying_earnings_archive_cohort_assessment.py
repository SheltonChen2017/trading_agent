"""Invented metadata only; parent must deny process-tree network."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import json

import pytest

from research import insider_buying_earnings_archive_cohort_assessment as m


def enc(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory():
    rows = []
    specifications = [("0000000001", "ABC", "4"), ("0000000001", "abc", "4/A"),
                      ("0000000002", "ABC", "3"), ("0000000003", "OLD", "4")]
    issuers = {}
    for number, (cik, label, form) in enumerate(specifications, 1):
        rows.append({"source_record_ordinal": number, "accession_number": f"0000000001-06-{number:06d}",
            "form_type": form, "raw_issuer_cik": str(int(cik)), "issuer_cik": cik,
            "raw_symbol_label": label, "raw_filing_date": "03-JAN-2006", "filing_date": "2006-01-03",
            "relevant_form4_or_amendment": form in {"4", "4/A"}, "accession_year_mismatch": False})
        item = issuers.setdefault(cik, {"issuer_cik": cik, "symbol_labels": [], "filing_count": 0,
            "first_filing_date": "2006-01-03", "last_filing_date": "2006-01-03",
            "form_counts": dict.fromkeys(m.FORMS, 0)})
        if label not in item["symbol_labels"]:
            item["symbol_labels"].append(label)
        item["symbol_labels"].sort(); item["filing_count"] += 1; item["form_counts"][form] += 1
    return {"schema": m.INVENTORY_SCHEMA, "period": "2006Q1", "scope": "complete_submission_metadata_only",
        "filings": rows, "all_form_issuers": list(issuers.values()),
        "accounting": {"filings": 4, "form_counts": {"3": 1, "3/A": 0, "4": 2, "4/A": 1, "5": 0, "5/A": 0},
                       "all_form_issuers": 3}}


def row(code, report, *, ordinal=0, fiscal="2005-09-30", timing="AfterMarket", status="reported"):
    return {"source_row_ordinal": ordinal, "code": code, "report_date": report, "fiscal_date": fiscal,
            "before_after_market": timing, "current_provider_reported_status": status}


def campaign(windows=m.SUPPORT_WINDOWS, *, schema="insider-eodhd-date-window-earnings-campaign-v1",
             name="ib-eodhd-campaign-invented-v1", rows=None, refusal=None, registered="2026-10-13T00:00:00Z"):
    rows = rows or {}
    observed_at = (datetime.fromisoformat(registered.replace("Z", "+00:00")) + timedelta(minutes=1)).isoformat()
    completed_at = (datetime.fromisoformat(registered.replace("Z", "+00:00")) + timedelta(minutes=2)).isoformat()
    manifest = {"schema": schema, "campaign_id": name, "windows": [list(window) for window in windows],
                "registered_at_utc": registered, "identity": {"head": "a" * 40}, "fixture_only": True}
    manifest_raw = enc(manifest); manifest_sha = sha(manifest_raw)
    results, evidence = [], []
    count = len(windows) if refusal is None else refusal + 1
    for index, window in enumerate(windows[:count]):
        v2 = type(schema) is str and schema in m.QUARANTINED_SCHEMAS
        projected = rows.get(window[0], []) if v2 else sorted(rows.get(window[0], []), key=lambda item: (item["report_date"], item["code"], item["fiscal_date"], item["source_row_ordinal"]))
        if v2:
            converted = []
            for item in projected:
                reasons = item.get("quarantine_reasons", [])
                if "metadata_accepted" not in item:
                    reasons = (["source_timing_unknown"] if item["before_after_market"] is None else [])
                    if item["current_provider_reported_status"] == "unknown":
                        reasons.append("current_provider_reported_status_unknown")
                converted.append({**item, "quarantine_reasons": reasons, "metadata_accepted": not reasons})
            projected = converted
        success = index != refusal
        receipt = {"calendar_window_observed": success, "transport_invocation_count": 1,
            "http_status": 200, "empty_result_is_coverage_evidence": False,
            "financial_values_evaluated_or_projected": False, "response_body_retained": success,
            "disposition": "calendar_window_observed" if success else "source_currency_schema_refused",
            "body_sha256": "b" * 64 if success else None, "body_size_bytes": 100 if success else None,
            "sample_rows": len(projected) if success else None,
            "reported_rows": sum(item["current_provider_reported_status"] == "reported" for item in projected) if success else None,
            "unknown_status_rows": sum(item["current_provider_reported_status"] == "unknown" for item in projected) if success else None,
            "timing_unknown_rows": sum(item["before_after_market"] is None for item in projected) if success else None}
        if v2:
            receipt.update(metadata_accepted_rows=sum(item["metadata_accepted"] for item in projected) if success else None,
                quarantined_rows=sum(not item["metadata_accepted"] for item in projected) if success else None,
                all_rows_retained_in_source_order=success)
        metadata = {"schema": schema, "body_sha256": "b" * 64, "rows": projected}
        if v2:
            metadata["metadata_acceptance_is_source_coverage_or_identity_admission"] = False
        metadata_raw = enc(metadata) if success else None
        if v2:
            receipt["metadata_sha256"] = sha(metadata_raw) if metadata_raw else None
        child = {"schema": schema, "window": list(window), "index": index, "completed_at_utc": observed_at,
            "manifest_sha256": manifest_sha, "started_sha256": "c" * 64, "scope_reservation_sha256": "d" * 64, "receipt": receipt}
        child_raw = enc(child); child_sha = sha(child_raw)
        evidence.append(m.ArchiveWindowMetadata(child_raw, child_sha, metadata_raw, sha(metadata_raw) if metadata_raw else None))
        results.append({"index": index, "window": list(window), "receipt": receipt, "complete_sha256": child_sha})
    observed = count - (refusal is not None)
    complete = {"schema": schema, "campaign_id": name, "completed_at_utc": completed_at,
        "manifest_sha256": manifest_sha, "identity": manifest["identity"], "fixture_only": True,
        "planned_windows": len(windows), "transport_invocation_count": count,
        "observed_windows": observed, "refused_or_ambiguous_windows": int(refusal is not None),
        "unattempted_windows": [list(window) for window in windows[count:]],
        "all_registered_windows_observed": observed == len(windows), "window_results": results}
    complete_raw = enc(complete)
    return m.ArchiveCampaignMetadata(manifest_raw, manifest_sha, complete_raw, sha(complete_raw), tuple(evidence))


def assess(campaigns=None, body=None):
    raw = enc(inventory() if body is None else body)
    return m.assess_earnings_archive_cohort(inventory_raw=raw, inventory_sha256=sha(raw),
                                          campaigns=(campaign(),) if campaigns is None else campaigns)


def patch_complete(item, update):
    body = json.loads(item.complete_raw)
    update(body)
    raw = enc(body)
    return replace(item, complete_raw=raw, complete_sha256=sha(raw))


def patch_window(item, index, update):
    body = json.loads(item.windows[index].complete_raw)
    update(body)
    raw = enc(body); digest = sha(raw)
    evidence = list(item.windows)
    evidence[index] = replace(evidence[index], complete_raw=raw, complete_sha256=digest)
    complete = json.loads(item.complete_raw)
    complete["window_results"][index]["receipt"] = body["receipt"]
    complete["window_results"][index]["complete_sha256"] = digest
    finished = enc(complete)
    return replace(item, windows=tuple(evidence), complete_raw=finished, complete_sha256=sha(finished))


def test_full_empty_acquisition_never_certifies_empty_issuer_coverage():
    result = assess().to_payload()
    assert result["all_planned_acquisition_windows_observed"] is True
    assert result["source_metadata_rows"] == 0
    assert result["all_form_issuer_count"] == 3 and result["relevant_issuer_count"] == 2
    assert result["source_filings"] == 4 and result["source_form_counts"]["3"] == 1
    assert all(item["coverage_disposition"] == "UNKNOWN" for item in result["issuer_relations"])
    assert all(item["no_observed_rows_means_no_earnings"] is False for item in result["issuer_relations"])
    assert not any(result["authority"].values())
    assert result["earnings_diagnostic_windows_sessions"] == [2, 5]
    assert result["earnings_used_for_execution_clock"] is False


def three_campaigns(*, third_rows=None, third_refusal=None):
    first = campaign(name="ib-eodhd-campaign-invented-v1", refusal=1,
                     rows={"2005-12-01": [row("ABC.US", "2005-12-15")]})
    second = campaign(m.SUPPORT_WINDOWS[2:], schema=m.CONTINUATION_SCHEMA,
        name="ib-eodhd-campaign-invented-v2", registered="2026-10-13T00:02:00Z", refusal=150,
        rows={"2006-02-01": [row("ABC.US", "2006-02-15")]})
    third = campaign(m.V3_SUPPORT_WINDOWS, schema=m.CONTINUATION3_SCHEMA,
        name="ib-eodhd-campaign-invented-v3", registered="2026-10-13T00:04:00Z", rows=third_rows, refusal=third_refusal)
    return first, second, third


def test_three_epochs_never_repair_two_attempted_refusals():
    result = assess(three_campaigns(third_rows={"2018-09-01": [row("ABC.US", "2018-09-15", ordinal=0)]})).to_payload()
    assert result["unavailable_windows"] == [["2006-01-01", "2006-01-31"], ["2018-08-01", "2018-08-31"]]
    assert len(result["window_accounting"]) == 248
    assert sum(item["status"] == "OBSERVED" for item in result["window_accounting"]) == 246
    assert result["source_metadata_rows"] == 3 and len(result["campaigns"]) == 3
    assert result["all_planned_acquisition_windows_observed"] is False
    assert all(value is False for value in result["authority"].values())
    assert result["earnings_diagnostic_windows_sessions"] == [2, 5]


def test_v3_nullable_quarantine_and_fiscal_conflict_are_retained():
    projected = row(None, None, ordinal=0, fiscal=None, timing=None, status="unknown")
    projected.update(metadata_accepted=False, quarantine_reasons=["source_code_unknown", "source_report_date_unknown",
        "source_fiscal_date_unknown", "source_timing_unknown", "current_provider_reported_status_unknown"])
    result = assess(three_campaigns(third_rows={"2018-09-01": [projected,
        row("ABC.US", "2018-09-15", ordinal=1)]})).to_payload()
    assert result["quarantined_metadata_rows"] == result["rows_missing_provider_code"] == 1
    assert result["source_metadata_rows"] == 4
    assert result["cross_archive_conflicting_fiscal_periods"] == 1


def test_v3_producer_metadata_hash_is_binding():
    first, second, third = three_campaigns()
    third = patch_window(third, 0, lambda body: body["receipt"].update(metadata_sha256="f" * 64))
    with pytest.raises(m.EarningsArchiveAssessmentError, match="producer_metadata_hash"):
        assess((first, second, third))


def test_v3_scope_cannot_redispatch_prior_refusal_or_unattempted_context():
    first, second, _ = three_campaigns()
    third = campaign(m.SUPPORT_WINDOWS[152:], schema=m.CONTINUATION3_SCHEMA,
        name="ib-eodhd-campaign-invented-v3", registered="2026-10-13T00:04:00Z")
    with pytest.raises(m.EarningsArchiveAssessmentError, match="continuation3_exact_unattempted_scope"):
        assess((first, second, third))


def test_v3_global_campaign_observation_order_is_binding():
    first, second, third = three_campaigns()
    raw = json.loads(third.manifest_raw); raw["registered_at_utc"] = "2026-10-13T00:01:00Z"
    altered = enc(raw)
    third = replace(third, manifest_raw=altered, manifest_sha256=sha(altered))
    complete = json.loads(third.complete_raw); complete["manifest_sha256"] = sha(altered)
    third = replace(third, complete_raw=enc(complete), complete_sha256=sha(enc(complete)))
    with pytest.raises(m.EarningsArchiveAssessmentError, match="campaign_observation_order"):
        assess((first, second, third))


def test_v3_partial_transport_refusal_preserves_remaining_unattempted():
    result = assess(three_campaigns(third_refusal=0)).to_payload()
    assert len(result["unavailable_windows"]) == 97
    assert result["window_accounting"][153]["status"] == "REFUSED_OR_AMBIGUOUS"
    assert result["window_accounting"][154]["status"] == "UNATTEMPTED"


def test_v3_limits_do_not_broaden_old_profiles():
    assert m.MAX_WINDOW_ROWS == 50_000 and m.MAX_JOURNAL_BYTES == 16 * 1024 * 1024
    assert m.metadata_byte_cap(m.CONTINUATION_SCHEMA) == 16 * 1024 * 1024
    assert m.body_byte_cap(m.CONTINUATION_SCHEMA) == 4 * 1024 * 1024
    assert m.metadata_byte_cap(m.CONTINUATION3_SCHEMA) == 256 * 1024 * 1024
    assert m.body_byte_cap(m.CONTINUATION3_SCHEMA) == 16 * 1024 * 1024
    assert m.control_byte_cap(m.CONTINUATION3_SCHEMA) == 1024 * 1024


def test_v3_row_limit_is_separate_and_old_row_limit_still_refuses():
    rows = [{**row("ABC.US", "2018-09-15", ordinal=ordinal), "metadata_accepted": True, "quarantine_reasons": []}
            for ordinal in range(50_001)]
    receipt = {"body_sha256": "b" * 64, "sample_rows": len(rows), "reported_rows": len(rows),
        "unknown_status_rows": 0, "timing_unknown_rows": 0, "metadata_accepted_rows": len(rows),
        "quarantined_rows": 0, "all_rows_retained_in_source_order": True}
    metadata = {"schema": m.CONTINUATION3_SCHEMA, "body_sha256": "b" * 64, "rows": rows,
                "metadata_acceptance_is_source_coverage_or_identity_admission": False}
    assert len(m._rows(metadata, receipt, m.V3_SUPPORT_WINDOWS[0])[0]) == 50_001
    metadata["schema"] = m.CONTINUATION_SCHEMA
    with pytest.raises(m.EarningsArchiveAssessmentError, match="metadata_row_accounting"):
        m._rows(metadata, receipt, m.V3_SUPPORT_WINDOWS[0])


def test_partial_first_campaign_continuation_cannot_fill_refused_january():
    first = campaign(refusal=1, rows={"2005-12-01": [row("ABC.US", "2005-12-15")]})
    second = campaign(m.SUPPORT_WINDOWS[2:], schema=m.CONTINUATION_SCHEMA,
                      name="ib-eodhd-campaign-invented-v2", registered="2026-10-13T00:02:00Z")
    result = assess((first, second)).to_payload()
    assert result["all_planned_acquisition_windows_observed"] is False
    assert result["unavailable_windows"] == [["2006-01-01", "2006-01-31"]]
    assert len(result["window_accounting"]) == 248
    assert result["window_accounting"][1]["status"] == "REFUSED_OR_AMBIGUOUS"
    assert result["window_accounting"][2]["status"] == "OBSERVED"
    assert result["source_metadata_rows"] == 1


def test_partial_campaign_keeps_every_unattempted_month():
    result = assess((campaign(refusal=1),)).to_payload()
    assert len(result["unavailable_windows"]) == 247
    assert sum(item["status"] == "UNATTEMPTED" for item in result["window_accounting"]) == 246


def test_exact_casefold_multiple_exchange_and_shared_labels_are_candidates_only():
    data = {"2006-02-01": [row("ABC.US", "2006-02-01", ordinal=0), row("ABC.TO", "2006-02-02", ordinal=1),
                          row("Abc.LSE", "2006-02-03", ordinal=2)]}
    result = assess((campaign(rows=data),)).to_payload()
    first, context, absent = result["issuer_relations"]
    relation = first["candidate_label_relations"][0]
    assert relation["exact_observed_basename_codes"] == ["ABC.TO", "ABC.US"]
    assert relation["casefold_only_observed_basename_codes"] == ["Abc.LSE"]
    assert relation["source_label_issuer_ciks"] == ["0000000001", "0000000002"]
    assert first["candidate_rows_in_2006q1"] == 2
    assert context["form_counts"]["3"] == 1
    assert absent["exact_candidate_codes"] == []
    assert all(item["historical_mapping_admitted"] is False for item in result["issuer_relations"])


def test_cross_month_same_period_conflicts_retain_both_source_ordinals():
    first = campaign(refusal=1, rows={"2005-12-01": [row("ABC.US", "2005-12-15")]})
    second = campaign(m.SUPPORT_WINDOWS[2:], schema=m.CONTINUATION_SCHEMA,
        name="ib-eodhd-campaign-invented-v2", registered="2026-10-13T00:02:00Z",
        rows={"2006-02-01": [row("ABC.US", "2006-02-10", timing=None)]})
    result = assess((first, second)).to_payload()
    assert result["source_metadata_rows"] == 2
    assert result["cross_archive_conflicting_fiscal_periods"] == 1
    conflict = result["cross_archive_duplicate_fiscal_periods"][0]
    assert conflict["metadata_conflict"] is True and len(conflict["source_references"]) == 2
    assert conflict["vendor_revision_history_verified"] is False
    assert result["source_rows_deduplicated"] is False


def test_same_metadata_duplicate_does_not_become_vendor_revision_history():
    rows = {"2006-02-01": [row("ABC.US", "2006-02-10", ordinal=0), row("ABC.US", "2006-02-10", ordinal=1)]}
    result = assess((campaign(rows=rows),)).to_payload()
    assert result["cross_archive_conflicting_fiscal_periods"] == 0
    assert result["cross_archive_duplicate_fiscal_periods"][0]["rows"] == 2


def test_v2_quarantined_rows_with_missing_keys_are_fully_accounted():
    missing = {"source_row_ordinal": 0, "metadata_accepted": False,
        "quarantine_reasons": ["source_row_not_object"], "code": None, "report_date": None,
        "fiscal_date": None, "before_after_market": None, "current_provider_reported_status": "unknown"}
    context = {**row("ABC.US", "2006-02-10", ordinal=1, timing=None),
               "metadata_accepted": False, "quarantine_reasons": ["source_timing_unknown"]}
    first = campaign(refusal=1)
    second = campaign(m.SUPPORT_WINDOWS[2:], schema=m.CONTINUATION_SCHEMA,
        name="ib-eodhd-campaign-quarantines", registered="2026-10-13T00:02:00Z",
        rows={"2006-02-01": [missing, context]})
    result = assess((first, second)).to_payload()
    assert result["source_metadata_rows"] == result["quarantined_metadata_rows"] == 2
    assert result["metadata_accepted_rows"] == 0
    assert result["rows_missing_provider_code"] == result["rows_without_code_fiscal_period_key"] == 1
    assert result["quarantine_reason_counts"] == {"source_row_not_object": 1, "source_timing_unknown": 1}
    assert result["provider_code_metadata"][0]["rows"] == result["provider_code_metadata"][0]["quarantined_rows"] == 1
    assert result["issuer_relations"][0]["candidate_rows_in_2006q1"] == 1
    assert result["window_accounting"][2]["quarantined_rows"] == 2
    assert result["unavailable_windows"] == [["2006-01-01", "2006-01-31"]]
    assert not any(result["authority"].values())


@pytest.mark.parametrize("schema", [[], {}, 1, True])
def test_invalid_campaign_schema_has_typed_sanitized_refusal(schema):
    with pytest.raises(m.EarningsArchiveAssessmentError, match="campaign_identity"):
        assess((campaign(schema=schema),))


@pytest.mark.parametrize("field", ["reported_rows", "unknown_status_rows", "timing_unknown_rows"])
def test_missing_status_receipt_has_typed_refusal(field):
    with pytest.raises(m.EarningsArchiveAssessmentError, match="receipt_schema"):
        assess((patch_window(campaign(), 0, lambda body: body["receipt"].pop(field)),))


@pytest.mark.parametrize("index", [0, 1])
def test_attempted_or_refused_windows_cannot_be_replaced(index):
    first = campaign(refusal=1)
    repeated = campaign(m.SUPPORT_WINDOWS[index:], name="ib-eodhd-campaign-repeat",
                        registered="2026-10-13T00:02:00Z")
    with pytest.raises(m.EarningsArchiveAssessmentError, match="duplicate_or_reordered"):
        assess((first, repeated))


def test_missing_declared_full_envelope_refuses_not_narrows_cohort():
    with pytest.raises(m.EarningsArchiveAssessmentError, match="complete_planned_support"):
        assess((campaign(m.SUPPORT_WINDOWS[2:]),))


@pytest.mark.parametrize("update,match", [
    (lambda body: body.update(transport_invocation_count=True), "unattempted_accounting"),
    (lambda body: body.update(observed_windows=True), "completion_accounting"),
    (lambda body: body.update(unattempted_windows=[]), "unattempted_accounting"),
    (lambda body: body.update(all_registered_windows_observed=True), "completion_accounting"),
    (lambda body: body.update(manifest_sha256="f" * 64), "source_binding"),
    (lambda body: body.update(fixture_only=False), "fixture_binding"),
    (lambda body: body.update(completed_at_utc="2006-01-01T00:00:00Z"), "observation_order"),
])
def test_partial_summary_refuses_false_counts_and_lineage(update, match):
    with pytest.raises(m.EarningsArchiveAssessmentError, match=match):
        assess((patch_complete(campaign(refusal=1), update),))


@pytest.mark.parametrize("update,match", [
    (lambda body: body.update(index=True), "receipt_binding"),
    (lambda body: body.update(manifest_sha256="f" * 64), "receipt_binding"),
    (lambda body: body.update(started_sha256="invalid"), "digest_schema"),
    (lambda body: body.update(completed_at_utc="2006-01-01T00:00:00Z"), "observation_order"),
    (lambda body: body["receipt"].update(sample_rows=True), "count_schema"),
    (lambda body: body["receipt"].update(empty_result_is_coverage_evidence=True), "receipt_schema"),
    (lambda body: body["receipt"].update(financial_values_evaluated_or_projected=True), "receipt_schema"),
    (lambda body: body["receipt"].update(body_sha256="f" * 64), "body_binding"),
])
def test_window_receipt_controls(update, match):
    with pytest.raises(m.EarningsArchiveAssessmentError, match=match):
        assess((patch_window(campaign(), 0, update),))


def test_refused_january_cannot_carry_selectively_retained_rows():
    item = campaign(refusal=1)
    evidence = list(item.windows)
    raw = enc({"schema": "ignored", "rows": []})
    evidence[1] = replace(evidence[1], metadata_raw=raw, metadata_sha256=sha(raw))
    with pytest.raises(m.EarningsArchiveAssessmentError, match="refused_window"):
        assess((replace(item, windows=tuple(evidence)),))


@pytest.mark.parametrize("update,match", [
    (lambda body: body["filings"][0].update(source_record_ordinal=True), "filing_ordinals"),
    (lambda body: body["filings"][0].update(issuer_cik="1"), "filing_identity"),
    (lambda body: body["filings"][0].update(form_type="8-K"), "filing_identity"),
    (lambda body: body["filings"][0].update(filing_date="2006-04-01"), "filing_quarter"),
    (lambda body: body["filings"][0].update(relevant_form4_or_amendment=False), "filing_relevance"),
    (lambda body: body["all_form_issuers"].pop(), "issuer_inventory_accounting"),
    (lambda body: body["accounting"].update(filings=True), "count_schema"),
    (lambda body: body["accounting"]["form_counts"].update({"3": True}), "source_count_types"),
])
def test_full_source_population_cannot_be_narrowed_or_coerced(update, match):
    body = inventory(); update(body)
    with pytest.raises(m.EarningsArchiveAssessmentError, match=match):
        assess(body=body)


@pytest.mark.parametrize("update,match", [
    (lambda item: item.update(source_row_ordinal=True), "row_ordinals"),
    (lambda item: item.update(code="ABC"), "code_schema"),
    (lambda item: item.update(report_date="2006-01-01"), "row_dates"),
    (lambda item: item.update(fiscal_date="2007-01-01"), "row_dates"),
    (lambda item: item.update(before_after_market=[]), "projected_timing"),
    (lambda item: item.update(current_provider_reported_status="actual_release_authenticated"), "projected_status"),
    (lambda item: item.update(actual="1.23"), "projected_row_schema"),
])
def test_projected_metadata_never_admits_financial_fields_or_foreign_rows(update, match):
    item = row("ABC.US", "2006-02-01"); update(item)
    with pytest.raises(m.EarningsArchiveAssessmentError, match=match):
        assess((campaign(rows={"2006-02-01": [item]}),))


def test_changed_metadata_bytes_require_new_external_hash():
    item = campaign()
    evidence = list(item.windows)
    evidence[0] = replace(evidence[0], metadata_raw=evidence[0].metadata_raw + b" ")
    with pytest.raises(m.EarningsArchiveAssessmentError, match="hash_mismatch"):
        assess((replace(item, windows=tuple(evidence)),))


def test_v2_caller_selfhash_cannot_replace_producer_metadata_binding():
    first = campaign(refusal=1)
    second = campaign(m.SUPPORT_WINDOWS[2:], schema=m.CONTINUATION_SCHEMA,
        name="ib-eodhd-campaign-bound-metadata", registered="2026-10-13T00:02:00Z",
        rows={"2006-02-01": [row("ABC.US", "2006-02-10")]})
    evidence = list(second.windows)
    changed = json.loads(evidence[0].metadata_raw)
    changed["rows"][0]["code"] = "DIFFERENT.US"
    raw = enc(changed)
    evidence[0] = replace(evidence[0], metadata_raw=raw, metadata_sha256=sha(raw))
    with pytest.raises(m.EarningsArchiveAssessmentError, match="producer_metadata_hash_binding"):
        assess((first, replace(second, windows=tuple(evidence))))


def test_caller_mutation_does_not_change_sealed_result():
    result = assess(); before = result.canonical_bytes()
    payload = result.to_payload(); payload["authority"]["backtesting_ready"] = True
    assert result.canonical_bytes() == before
    assert result.to_payload()["authority"]["backtesting_ready"] is False
    object.__setattr__(result, "_raw", b"{}")
    with pytest.raises(m.EarningsArchiveAssessmentError, match="unchanged_assessment"):
        result.canonical_bytes()


def test_import_boundary_has_no_io_provider_or_outcome_imports():
    import ast
    from pathlib import Path
    source = Path(m.__file__).read_text()
    tree = ast.parse(source)
    allowed = {"__future__", "collections", "dataclasses", "datetime", "calendar", "hashlib", "json", "re"}
    roots = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    roots |= {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert roots <= allowed
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open" for node in ast.walk(tree))
