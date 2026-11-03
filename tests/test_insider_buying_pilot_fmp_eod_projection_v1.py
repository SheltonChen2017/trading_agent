"""Invented in-memory provider metadata; no source/provider/QC operation."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from research import insider_buying_pilot_fmp_eod_projection_v1 as m


def _cases():
    return [{"case_id": "control-1", "cik": "0000001234", "accession": "000000123420000001",
        "form_type": "4", "filing_date": "2020-10-02", "acceptance_digits": "20201002160102",
        "source_symbol": "INVENTED-SYMBOL", "body_sha256": "a" * 64}]


def _url(accession="000000123420000001", issuer="9999999"):
    # Directory CIK is intentionally NOT assumed to equal the issuer control.
    return "https://www.sec.gov/Archives/edgar/data/" + issuer + "/" + accession + "/ownership.xml"


def _sec():
    return {"symbol": "INVENTED-SYMBOL", "cik": "1234", "filingDate": "2020-10-02",
        "acceptedDate": "2020-10-02 16:01:02", "formType": "4", "link": _url(), "finalLink": _url()}


def _insider():
    return {"symbol": "INVENTED-SYMBOL", "companyCik": "1234", "reportingCik": "9876",
        "filingDate": "2020-10-02", "transactionDate": "2020-09-30", "formType": "4", "url": _url(),
        "reportingName": "PRIVATE REPORTING NAME", "price": 9876543.125, "securitiesOwned": 123456789,
        "securitiesTransacted": -1000, "transactionType": "P-Purchase", "securityName": "PRIVATE SECURITY NAME"}


def _eod(rows=None, *, total=1, limit=1000, offset=0, next_link=None):
    return {"data": rows if rows is not None else [{"symbol": "INVENTED-SYMBOL", "cik": "0000001234",
        "isin": "PRIVATE-ISIN", "cusip": "PRIVATE-CUSIP", "figi": "PRIVATE-FIGI", "lei": "PRIVATE-LEI"}],
        "meta": {"total": total, "limit": limit, "offset": offset}, "links": {"next": next_link}}


def _raw(value):
    return json.dumps(value, separators=(",", ":")).encode()


def _sec_project(raw=None, cases=None, **kwargs):
    return m.project_sec_search(_raw([_sec()]) if raw is None else raw, _cases() if cases is None else cases,
        queried_cik="0000001234", from_date="2020-10-01", to_date="2020-10-31", **kwargs)


def _payload(result):
    return m.public_payload(result)


def test_sec_accession_cik_and_naive_acceptance_are_comparisons_not_availability():
    raw = _raw([_sec()]); result = _sec_project(raw); value = _payload(result)
    check = value["case_checks"]["control-1"]
    assert check["joint_cik_accession_rows"] == check["filing_date_equal_rows"] == 1
    assert check["form_type_equal_rows"] == check["source_symbol_equal_rows"] == 1
    assert check["naive_acceptance_comparable_rows"] == check["naive_acceptance_lexical_equal_rows"] == 1
    assert check["acceptance_timezone_verified"] is False
    assert check["public_known_by_verified"] is False
    assert check["source_body_equivalence_verified"] is False
    assert value["body_pin"] == {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    assert value["filing_date_bounds"] == ["2020-10-02", "2020-10-02"]
    assert value["naive_acceptance_is_publication_or_timezone_evidence"] is False
    assert value["response_rows_retained"] is value["response_body_retained"] is False
    assert value["metadata_evidence_can_independently_reparse_response"] is False


def test_financial_numeric_lexemes_are_opaque_including_huge_finite_exponent():
    raw = _raw([_insider()]).replace(b"9876543.125", b"1e999999999999999999999999999999")
    value = _payload(m.project_insider_latest(raw, _cases(), requested_date="2020-10-02"))
    assert value["counts"]["matched_control_rows"] == 1
    assert value["financial_values_interpreted"] is False
    assert value["counts"]["metadata_field_presence"]["price"] == 1
    wire = m._raw(value)
    for private in (b"9876543", b"123456789", b"999999999999999999999999999999", b"PRIVATE REPORTING", b"PRIVATE SECURITY", b"INVENTED-SYMBOL"):
        assert private not in wire


def test_latest_date_semantics_compare_both_fields_and_keep_older_transaction():
    value = _payload(m.project_insider_latest(_raw([_insider()]), _cases(), requested_date="2020-10-02"))
    assert value["scoped"] is True and value["body_pin"] is not None
    assert value["counts"]["requested_date_filing_matches"] == 1
    assert value["counts"]["requested_date_transaction_matches"] == 0
    assert value["counts"]["transaction_date_outside_window_rows"] == 1
    assert value["latest_date_filter_semantics_verified"] is False
    row = _insider(); row["transactionDate"] = "2020-10-03"
    value = _payload(m.project_insider_latest(_raw([row]), _cases(), requested_date="2020-10-03"))
    assert value["scoped"] is True
    assert value["counts"]["requested_date_filing_matches"] == 0
    assert value["counts"]["requested_date_transaction_matches"] == 1


@pytest.mark.parametrize("field,value", (("filingDate", "2020-09-30"), ("filingDate", None),
    ("filingDate", "2020-02-30"), ("filingDate", ["2020-10-02"]), ("cik", "999"), ("cik", [])))
def test_unscoped_sec_response_suppresses_case_metadata_and_body_pin(field, value):
    row = _sec(); row[field] = value
    payload = _payload(_sec_project(_raw([row])))
    assert payload["scoped"] is False
    assert payload["body_pin"] is None and payload["filing_date_bounds"] is None
    assert payload["case_checks"] == {}
    assert payload["counts"]["response_rows"] == 1


def test_requested_sec_interval_is_binding_even_inside_global_window():
    row = _sec(); row["filingDate"] = "2020-11-01"
    value = _payload(_sec_project(_raw([row])))
    assert value["scoped"] is False and value["body_pin"] is None
    assert value["counts"]["requested_interval_outside_rows"] == 1


@pytest.mark.parametrize("accepted", ("2020-10-02T16:01:02Z", "2020-10-02 16:01:02-04:00", "2020-10-02 99:01:02", None))
def test_unsupported_or_missing_acceptance_is_not_silently_normalized(accepted):
    row = _sec(); row["acceptedDate"] = accepted
    value = _payload(_sec_project(_raw([row])))
    assert value["case_checks"]["control-1"]["naive_acceptance_comparable_rows"] == 0
    assert value["case_checks"]["control-1"]["naive_acceptance_lexical_equal_rows"] == 0


def test_conflicting_link_accessions_quarantine_without_selecting_favorable_link():
    row = _sec(); row["finalLink"] = _url("000000123420000002")
    value = _payload(_sec_project(_raw([row])))
    assert value["counts"]["accession_conflict_rows"] == 1
    assert value["counts"]["metadata_quarantined_rows"] == 1
    assert value["case_checks"]["control-1"]["joint_cik_accession_rows"] == 0
    assert value["body_pin"] is None


@pytest.mark.parametrize("url", ("http://www.sec.gov/Archives/edgar/data/1234/000000123420000001/x.xml",
    "https://www.sec.gov.evil.invalid/Archives/edgar/data/1234/000000123420000001/x.xml",
    "https://account@www.sec.gov/Archives/edgar/data/1234/000000123420000001/x.xml",
    "https://www.sec.gov:443/Archives/edgar/data/1234/000000123420000001/x.xml",
    "https://www.sec.gov/Archives/edgar/data/1234/../000000123420000001/x.xml",
    "https://www.sec.gov/Archives/edgar/data/1234/000000123420000001/x.xml?token=PRIVATE",
    "https://www.sec.gov/Archives/edgar/data/1234/%30%30%30%30/x.xml"))
def test_foreign_or_aliased_urls_never_supply_accession(url):
    row = _sec(); row["link"] = row["finalLink"] = url
    value = _payload(_sec_project(_raw([row])))
    assert value["counts"]["matched_control_rows"] == 0
    assert value["counts"]["accession_absent_rows"] == 1
    assert value["case_checks"]["control-1"]["exact_accession_rows"] == 0
    assert "PRIVATE" not in m._raw(value).decode()


def test_dashed_accession_in_sec_filename_is_supported_without_issuer_prefix_assumption():
    row = _sec(); row["link"] = "https://sec.gov/Archives/edgar/data/999/000000123420000001/0000001234-20-000001-index.html"
    row["finalLink"] = None
    value = _payload(_sec_project(_raw([row])))
    assert value["counts"]["matched_control_rows"] == 1


def test_direct_complete_submission_txt_supplies_only_accession_corroboration():
    row = _sec()
    row["link"] = "https://www.sec.gov/Archives/edgar/data/999/0000001234-20-000001.txt"
    row["finalLink"] = None
    value = _payload(_sec_project(_raw([row])))
    assert value["counts"]["matched_control_rows"] == 1
    assert value["case_checks"]["control-1"]["source_body_equivalence_verified"] is False
    assert value["authority"]["source_authenticated"] is False


def test_zero_locator_cik_does_not_supply_sec_accession_evidence():
    row = _sec(); row["link"] = row["finalLink"] = _url(issuer="0")
    value = _payload(_sec_project(_raw([row])))
    assert value["counts"]["matched_control_rows"] == 0
    assert value["counts"]["accession_absent_rows"] == 1


def test_empty_and_limit_hit_responses_do_not_establish_coverage_absence():
    empty = _payload(_sec_project(b"[]"))
    assert empty["counts"]["response_rows"] == 0 and empty["body_pin"] is not None
    assert empty["pagination"]["additional_pages_unknown"] is True
    assert empty["authority"]["full_population_complete"] is False
    value = _payload(_sec_project(limit=1))
    assert value["pagination"]["limit_reached"] is True
    assert value["pagination"]["all_pages_read"] is False


def test_multiple_same_day_controls_remain_ambiguous_without_accession():
    cases = _cases(); other = deepcopy(cases[0]); other.update(case_id="control-2", accession="000000123420000002")
    cases.append(other); row = _sec(); row["link"] = row["finalLink"] = None
    value = _payload(_sec_project(_raw([row]), cases))
    assert value["counts"]["ambiguous_control_candidate_rows"] == 1
    assert value["counts"]["matched_control_rows"] == 0
    assert all(v["candidate_rows"] == 1 and v["exact_accession_rows"] == 0 for v in value["case_checks"].values())


def test_eod_current_identifier_presence_never_becomes_historical_identity():
    value = _payload(m.project_eod_mapping(_raw(_eod()), _cases(), requested_ciks=("0000001234",)))
    check = value["case_checks"]["control-1"]
    assert check["cik_rows"] == check["current_symbol_equal_rows"] == 1
    assert check["identifier_presence_counts"] == {"isin": 1, "cusip": 1, "figi": 1, "lei": 1}
    assert check["historical_identity_verified"] is False
    assert value["current_label_agreement_is_historical_identity"] is False
    wire = m._raw(value)
    for private in (b"INVENTED-SYMBOL", b"PRIVATE-ISIN", b"PRIVATE-CUSIP", b"PRIVATE-FIGI", b"PRIVATE-LEI"):
        assert private not in wire


def test_eod_next_url_and_missing_identifiers_are_accounted_without_leakage():
    raw = _raw(_eod([{"symbol": None, "cik": 1234}], total=10, limit=1,
        next_link="https://eodhd.com/api/id-mapping?api_token=DO-NOT-EXPORT"))
    value = _payload(m.project_eod_mapping(raw, _cases(), requested_ciks=("0000001234",), limit=1))
    assert value["pagination"]["next_present"] is True and value["pagination"]["more_rows_indicated"] is True
    assert value["pagination"]["limit_reached"] is True and value["pagination"]["all_pages_read"] is False
    check = value["case_checks"]["control-1"]
    assert check["current_symbol_present_rows"] == 0
    assert check["identifier_presence_counts"] == {"isin": 0, "cusip": 0, "figi": 0, "lei": 0}
    assert "DO-NOT-EXPORT" not in m._raw(value).decode() and "eodhd.com" not in m._raw(value).decode()


@pytest.mark.parametrize("cik", (None, "0000000000", "12345678901", True, 1234.5, [], {}))
def test_invalid_eod_identity_does_not_mint_current_mapping(cik):
    value = _payload(m.project_eod_mapping(_raw(_eod([{"cik": cik, "symbol": "PRIVATE"}])), _cases(), requested_ciks=("0000001234",)))
    assert value["scoped"] is False and value["case_checks"] == {} and value["body_pin"] is None


def test_eod_conflicting_current_symbols_and_query_disagreement_are_explicit():
    response = _eod([{"cik": "1234", "symbol": "ONE"}, {"cik": "1234", "symbol": "TWO"}], total=2)
    value = _payload(m.project_eod_mapping(_raw(response), _cases(), requested_ciks=("0000001234",)))
    assert value["counts"]["current_symbol_conflicting_ciks"] == 0
    assert value["counts"]["issuer_ciks_with_multiple_symbols"] == 1
    response["data"][0]["cik"] = "999"
    value = _payload(m.project_eod_mapping(_raw(response), _cases(), requested_ciks=("0000001234",)))
    assert value["scoped"] is False and value["counts"]["requested_cik_disagreement_rows"] == 1
    assert value["body_pin"] is None and value["case_checks"] == {}


def test_eod_one_symbol_with_multiple_ciks_is_distinct_from_multiple_share_classes():
    cases = _cases(); other = deepcopy(cases[0])
    other.update(case_id="control-2", cik="0000009876", accession="000000987620000002")
    cases.append(other)
    response = _eod([{"cik": "1234", "symbol": "REUSED"}, {"cik": "9876", "symbol": "REUSED"}], total=2)
    value = _payload(m.project_eod_mapping(_raw(response), cases, requested_ciks=("0000001234", "0000009876")))
    assert value["counts"]["current_symbol_conflicting_ciks"] == 1
    assert value["counts"]["issuer_ciks_with_multiple_symbols"] == 0
    assert value["authority"]["historical_identity_verified"] is False


def test_eod_us_namespace_agreement_is_separate_from_literal_label_equality():
    response = _eod([{"cik": "1234", "symbol": "INVENTED-SYMBOL.US"}])
    value = _payload(m.project_eod_mapping(_raw(response), _cases(), requested_ciks=("0000001234",)))
    check = value["case_checks"]["control-1"]
    assert check["current_symbol_equal_rows"] == 0
    assert check["current_symbol_us_namespace_equal_rows"] == 1
    assert check["historical_identity_verified"] is False
    assert value["current_label_agreement_is_historical_identity"] is False


@pytest.mark.parametrize("raw,code", ((b'{"Error Message":"SECRET"}', "provider_error_response"),
    (b'[{"error":"SECRET"}]', "provider_error_response"),
    (b'[{"cik":"1","cik":"2"}]', "response_json_refused"), (b'[NaN]', "response_json_refused"),
    (b'[Infinity]', "response_json_refused"), (b'[-Infinity]', "response_json_refused"),
    (b'\xff', "response_json_refused"), (b'null', "response_shape_refused"),
    (b'[[]]', "response_shape_refused"), (b'[] trailing', "response_json_refused")))
def test_invalid_json_and_error_objects_have_only_finite_refusals(raw, code):
    with pytest.raises(m.ProjectionError, match="^" + code + "$") as caught: _sec_project(raw)
    assert m.safe_failure(caught.value) == code and "SECRET" not in str(caught.value)


@pytest.mark.parametrize("fault", ("body", "rows", "string", "depth", "number"))
def test_resource_limits_are_binding(fault):
    raw = b"x" * (m.MAX_BODY + 1)
    if fault == "rows": raw = _raw([{}] * 1001)
    if fault == "string": raw = _raw([{"unknown": "x" * 16385}])
    if fault == "depth": raw = b"[" * 14 + b"0" + b"]" * 14
    if fault == "number": raw = b'[{"unknown":' + b"1" * 129 + b"}]"
    with pytest.raises(m.ProjectionError): _sec_project(raw)


@pytest.mark.parametrize("fault", ("cik", "accession", "form", "acceptance", "date", "duplicate", "extra"))
def test_control_integrity_and_scope_are_binding(fault):
    cases = _cases()
    if fault == "cik": cases[0]["cik"] = "1234"
    if fault == "accession": cases[0]["accession"] = "../bad"
    if fault == "form": cases[0]["form_type"] = []
    if fault == "acceptance": cases[0]["acceptance_digits"] = "20201002999999"
    if fault == "date": cases[0]["filing_date"] = "2020-09-30"
    if fault == "duplicate": cases.append(deepcopy(cases[0]))
    if fault == "extra": cases[0]["unknown"] = "SECRET"
    with pytest.raises(m.ProjectionError, match="control_cases_refused"): _sec_project(cases=cases)


@pytest.mark.parametrize("status", (201, 206, 400, True))
def test_only_exact_successful_transport_status_can_pin_a_body(status):
    with pytest.raises(m.ProjectionError, match="response_status_refused"): _sec_project(status=status)


def test_unknown_fields_and_mutable_result_copies_cannot_add_authority_or_leak():
    row = _sec(); row["UNKNOWN-PRIVATE-KEY"] = {"SECRET": "UNKNOWN-PRIVATE-VALUE"}
    result = _sec_project(_raw([row])); payload = _payload(result)
    assert b"UNKNOWN-PRIVATE" not in result.canonical_bytes()
    payload["authority"]["backtesting_ready"] = True
    assert _payload(result)["authority"]["backtesting_ready"] is False
    assert all(v is False or type(v) is int and v == 0 for v in _payload(result)["authority"].values())
    for fake in (replace(result), SimpleNamespace(canonical_bytes=result.canonical_bytes),
        m.ProjectionResult(result.canonical_bytes(), object()), _payload(result)):
        with pytest.raises(m.ProjectionError, match="genuine_projection_required"): m.public_payload(fake)


def test_eod_error_and_pagination_shape_are_strict_and_tokens_never_exported():
    for response in ({"error": "SECRET"}, {"data": [], "error": "SECRET"},
        {"data": [], "status": "ERROR", "message": "SECRET"}):
        with pytest.raises(m.ProjectionError, match="provider_error_response"):
            m.project_eod_mapping(_raw(response), _cases(), requested_ciks=("0000001234",))
    response = _eod(); response["meta"]["total"] = True
    with pytest.raises(m.ProjectionError, match="response_shape_refused"):
        m.project_eod_mapping(_raw(response), _cases(), requested_ciks=("0000001234",))
    value = _payload(m.project_eod_mapping(_raw(_eod(limit=100)), _cases(), requested_ciks=("0000001234",)))
    assert value["scoped"] is False and value["body_pin"] is None


def test_bad_request_types_and_outside_window_refuse_before_body_projection():
    for kwargs in ({"requested_date": "2020-09-30"}, {"requested_date": "2020-10-02", "page": True},
        {"requested_date": "2020-10-02", "limit": 1001}):
        with pytest.raises(m.ProjectionError, match="request_scope_refused"):
            m.project_insider_latest(b"[]", _cases(), **kwargs)
    with pytest.raises(m.ProjectionError, match="request_scope_refused"):
        m.project_eod_mapping(b"{}", _cases(), requested_ciks=([],))
