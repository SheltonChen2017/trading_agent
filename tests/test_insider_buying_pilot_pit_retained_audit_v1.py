"""Invented retained metadata only: current corroboration never grants PIT.

No actual archive, account, credential, provider, USB or QC operation occurs.
The caller must enforce native process-tree denial and test isolation.
"""
from copy import deepcopy
import hashlib
import json

import pytest

from research import insider_buying_pilot_fmp_eod_projection_v1 as projection
from research import insider_buying_pilot_pit_retained_audit_v1 as m


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _pin(raw):
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _cases():
    return [
        {"case_id": "PRIVATE-CONTROL-1", "cik": "0000001234", "accession": "000000123420000001",
         "form_type": "4", "filing_date": "2020-10-02", "acceptance_digits": "20201002160102",
         "source_symbol": "PRIVATE-SYMBOL-ONE", "body_sha256": "a" * 64},
        {"case_id": "PRIVATE-CONTROL-2", "cik": "0000005678", "accession": "000000567821000002",
         "form_type": "4", "filing_date": "2021-06-01", "acceptance_digits": "20210601160102",
         "source_symbol": "PRIVATE-SYMBOL-TWO", "body_sha256": "b" * 64},
    ]


def _sec_row(case):
    day = case["filing_date"]
    digits = case["acceptance_digits"]
    accepted = day + " " + digits[8:10] + ":" + digits[10:12] + ":" + digits[12:14]
    link = "https://www.sec.gov/Archives/edgar/data/9999999/" + case["accession"] + "/ownership.xml"
    return {"symbol": case["source_symbol"], "cik": case["cik"], "filingDate": day,
            "acceptedDate": accepted, "formType": case["form_type"], "link": link, "finalLink": link}


def _complete(cases, *, sec_rows=None, include_refusal=True):
    receipts = []
    for case in cases:
        rows = [_sec_row(case)] if sec_rows is None else sec_rows
        value = projection.public_payload(projection.project_sec_search(
            _raw(rows), [case], queried_cik=case["cik"], from_date=case["filing_date"],
            to_date=case["filing_date"], limit=100))
        receipts.append({"request_index": len(receipts), "family": "fmp_sec", "attempted": True,
                         "code": "metadata_projected", "projection": value})
    for case in cases:
        value = projection.public_payload(projection.project_eod_mapping(
            _raw({"data": [{"symbol": case["source_symbol"] + ".US", "cik": case["cik"],
                            "isin": "PRIVATE-ISIN", "cusip": "PRIVATE-CUSIP", "figi": "PRIVATE-FIGI",
                            "lei": "PRIVATE-LEI"}],
                  "meta": {"total": 1, "offset": 0, "limit": 100}, "links": {"next": None}}),
            [case], requested_ciks=[case["cik"]], limit=100))
        receipts.append({"request_index": len(receipts), "family": "eod_mapping", "attempted": True,
                         "code": "metadata_projected", "projection": value})
    if include_refusal:
        case = cases[0]
        row = {"symbol": "PRIVATE-WRONG-DAY", "companyCik": case["cik"], "reportingCik": "9876",
               "filingDate": "2020-10-05", "transactionDate": "2020-10-04", "formType": "4",
               "url": _sec_row(case)["link"], "price": 9876543.125}
        value = projection.public_payload(projection.project_insider_latest(
            _raw([row]), [case], requested_date=case["filing_date"], limit=100))
        assert value["scoped"] is False
        receipts.append({"request_index": len(receipts), "family": "fmp_insider", "attempted": True,
                         "code": "provider_scope_refused", "projection": value})
        # This is the real v2 unattempted shape: no projection key is present.
        receipts.append({"request_index": len(receipts), "family": "fmp_insider", "attempted": False,
                         "code": "prior_provider_or_family_refusal"})
    projections = [r["projection"] for r in receipts if r.get("projection") is not None]
    return {"schema": "insider-pilot-fmp-eod-stable-qualification-v2/complete", "fixture_only": True,
            "receipts": receipts, "authority": m.authority(), "planned_requests": len(receipts),
            "transport_invocation_count": sum(r["attempted"] for r in receipts),
            "unattempted_requests": sum(not r["attempted"] for r in receipts),
            "projected_responses": len(projections),
            "scoped_responses": sum(r["scoped"] for r in projections),
            "clean_scoped_responses": sum(r["scoped"] and r["metadata_clean"] for r in projections),
            "raw_response_retained": False, "remote_request_count_measured": False}


def _ticker(case, ordinal, **changes):
    row = {key: "" for key in m.TICKER_COLUMNS}
    row.update(source_row_ordinal=ordinal, table="stocks", permaticker=str(1000 + ordinal),
               ticker=case["source_symbol"], name="PRIVATE COMPANY NAME", exchange="NYSE", isdelisted="N",
               category="Domestic Common Stock", firstpricedate="2000-01-03", lastpricedate="2026-01-02",
               firstadded="2001-01-01", lastupdated="2026-01-02",
               secfilings="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + case["cik"])
    row.update(changes)
    return row


def _action(case, ordinal=1, **changes):
    row = {key: "" for key in m.ACTION_COLUMNS}
    row.update(source_row_ordinal=ordinal, date="2020-10-01", action="tickerchange",
               ticker=case["source_symbol"], name="PRIVATE ACTION NAME",
               contraticker="PRIVATE-OLD-SYMBOL", contraname="PRIVATE OLD COMPANY")
    row.update(changes)
    return row


def _inputs(*, cases=None, ticker_rows=None, action_rows=None, complete=None):
    cases = _cases() if cases is None else cases
    complete = _complete(cases) if complete is None else complete
    ticker_rows = [_ticker(c, i + 1) for i, c in enumerate(cases)] if ticker_rows is None else ticker_rows
    action_rows = [_action(cases[0])] if action_rows is None else action_rows
    pins = {"controls.json": _pin(_raw(cases)), "provider-complete.json": _pin(_raw(complete)),
            "tickers.csv": _pin(b"invented ticker projection"), "actions.csv": _pin(b"invented action projection")}
    return cases, complete, ticker_rows, action_rows, pins


def _build(**kwargs):
    return m.build_audit(*_inputs(**kwargs))


def _all_false(authority):
    assert authority == m.authority()
    assert all(value is False if type(value) is bool else type(value) is int and value == 0
               for value in authority.values())


def test_all_controls_survive_as_current_candidates_without_pit_or_public_identity_values():
    result = _build()
    counts = result["counts"]
    assert counts["controls"] == counts["issuers"] == 2
    assert counts["controls_one_current_candidate"] == counts["controls_source_symbol_agreement"] == 2
    assert counts["fmp_joint_controls"] == counts["eod_current_mapping_agreement_controls"] == 2
    assert len(result["controls"]) == 2
    for row in result["controls"]:
        assert row["effective_interval"] is row["public_known_by"] is None
        assert row["counts"]["current_candidate_rows"] == row["counts"]["current_candidate_permatickers"] == 1
        _all_false(row["authority"])
    _all_false(result["authority"])
    summary = m.public_summary(result)
    assert summary["counts"] == counts and summary["result_sha256"] == hashlib.sha256(_raw(result)).hexdigest()
    wire = _raw(result) + _raw(summary)
    for private in (b"PRIVATE-", b"PRIVATE COMPANY", b"PRIVATE ACTION", b"9876543", b"ownership.xml"):
        assert private not in wire


def test_original_refused_empty_and_unattempted_dispositions_are_not_erased():
    counts = _build()["counts"]
    assert counts["provider_planned_requests"] == 6
    assert counts["provider_transport_invocations"] == counts["provider_projected_responses"] == 5
    assert counts["provider_scoped_responses"] == counts["provider_clean_scoped_responses"] == 4
    assert counts["provider_unattempted_requests"] == counts["provider_refused_attempts"] == 1
    assert counts["fmp_sec_attempts"] == counts["eod_mapping_attempts"] == 2
    assert counts["fmp_insider_attempts"] == 1


@pytest.mark.parametrize("url", ("", "https://www.sec.gov.example/cgi-bin/browse-edgar?CIK=0000001234",
    "https://example.invalid/?CIK=0000001234", "https://www.sec.gov/cgi-bin/browse-edgar?CIK=0000001234&CIK=0000005678"))
def test_name_symbol_or_untrusted_sec_url_cannot_join_an_issuer(url):
    cases = _cases()[:1]
    result = _build(cases=cases, ticker_rows=[_ticker(cases[0], 1, secfilings=url)])
    assert result["counts"]["controls_no_current_candidate"] == 1
    assert result["controls"][0]["counts"]["current_candidate_rows"] == 0
    assert result["controls"][0]["effective_interval"] is None


def test_nonsecurity_table_cannot_supply_a_control_candidate():
    cases = _cases()[:1]
    result = _build(cases=cases, ticker_rows=[_ticker(cases[0], 1, table="holdings")])
    assert result["counts"]["controls_no_current_candidate"] == 1
    assert result["controls"][0]["counts"]["current_candidate_rows"] == 0


def test_multiple_current_share_classes_and_reused_symbols_stay_ambiguous():
    cases = _cases()
    rows = [_ticker(cases[0], 1, ticker="PRIVATE-REUSED", permaticker="1001"),
            _ticker(cases[0], 2, ticker="PRIVATE-REUSED", permaticker="1002"),
            _ticker(cases[1], 3, ticker="PRIVATE-REUSED", permaticker="1003")]
    result = _build(cases=cases, ticker_rows=rows)
    assert result["counts"]["controls_multiple_current_candidates"] >= 1
    assert result["counts"]["global_label_reuse_groups"] >= 1
    assert result["controls"][0]["counts"]["current_candidate_permatickers"] == 2
    assert all(c["public_known_by"] is c["effective_interval"] is None for c in result["controls"])
    _all_false(result["authority"])


def test_one_permaticker_claiming_two_ciks_is_a_conflict_not_a_merge():
    cases = _cases()
    rows = [_ticker(cases[0], 1, permaticker="1001"), _ticker(cases[1], 2, permaticker="1001")]
    result = _build(cases=cases, ticker_rows=rows)
    assert result["counts"]["global_permaticker_cik_conflicts"] == 1
    assert result["counts"]["controls_conflicting_current_candidates"] >= 1
    assert len(result["controls"]) == 2
    _all_false(result["authority"])


def test_repeated_exact_ticker_rows_are_counted_without_silent_deduplication():
    cases = _cases()[:1]
    first = _ticker(cases[0], 1)
    second = dict(first, source_row_ordinal=2)
    result = _build(cases=cases, ticker_rows=[first, second])
    assert result["counts"]["ticker_rows"] == 2
    assert result["counts"]["ticker_exact_duplicate_rows"] == 1


def test_action_labels_are_only_discovery_and_same_day_is_not_proven_preentry():
    cases = _cases()[:1]
    result = _build(cases=cases, action_rows=[_action(cases[0], 1),
        _action(cases[0], 2, date=cases[0]["filing_date"]),
        _action(cases[0], 3, ticker="UNRELATED", contraticker=cases[0]["source_symbol"])])
    assert result["counts"]["action_rows"] == 3
    assert result["counts"]["action_candidate_rows"] == 3
    assert result["controls"][0]["counts"]["action_rows_before_filing"] == 2
    assert result["controls"][0]["counts"]["current_candidate_rows"] == 1
    assert result["controls"][0]["counts"]["current_candidate_permatickers"] == 1
    assert result["controls"][0]["effective_interval"] is result["controls"][0]["public_known_by"] is None
    _all_false(result["authority"])


def test_original_sec_symbol_still_discovers_actions_after_a_current_label_change():
    cases = _cases()[:1]
    result = _build(cases=cases,
        ticker_rows=[_ticker(cases[0], 1, ticker="CURRENT-RENAMED")],
        action_rows=[_action(cases[0], 1, contraticker="UNRELATED")])
    assert result["counts"]["controls_one_current_candidate"] == 1
    assert result["counts"]["controls_source_symbol_agreement"] == 0
    assert result["counts"]["action_candidate_rows"] == 1
    assert result["controls"][0]["counts"]["action_candidate_rows"] == 1
    assert result["controls"][0]["effective_interval"] is result["controls"][0]["public_known_by"] is None
    _all_false(result["authority"])


def test_action_contra_label_discovers_a_current_candidate_without_merging_issuers():
    cases = _cases()
    rows = [_ticker(cases[0], 1, ticker="CURRENT-ONE"),
            _ticker(cases[1], 2, ticker="CURRENT-TWO")]
    result = _build(cases=cases, ticker_rows=rows,
        action_rows=[_action(cases[0], 1, ticker="UNMAPPED-PRIMARY", contraticker="CURRENT-ONE")])
    assert result["counts"]["controls"] == result["counts"]["issuers"] == 2
    assert result["counts"]["controls_one_current_candidate"] == 2
    assert result["counts"]["action_candidate_rows"] == result["counts"]["action_candidate_relations"] == 1
    assert [row["counts"]["action_candidate_rows"] for row in result["controls"]] == [1, 0]
    assert all(row["counts"]["current_candidate_permatickers"] == 1 for row in result["controls"])
    assert all(row["effective_interval"] is row["public_known_by"] is None for row in result["controls"])
    _all_false(result["authority"])


def test_source_symbol_action_discovery_survives_without_a_current_cik_candidate():
    cases = _cases()[:1]
    foreign = _ticker(cases[0], 1,
        secfilings="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000009999")
    result = _build(cases=cases, ticker_rows=[foreign], action_rows=[_action(cases[0])])
    assert result["counts"]["controls_no_current_candidate"] == 1
    assert result["controls"][0]["counts"]["current_candidate_rows"] == 0
    assert result["counts"]["action_candidate_rows"] == result["counts"]["action_candidate_relations"] == 1
    assert result["controls"][0]["counts"]["action_candidate_rows"] == 1
    assert result["controls"][0]["effective_interval"] is result["controls"][0]["public_known_by"] is None
    _all_false(result["authority"])


def test_primary_and_contra_labels_for_one_control_do_not_double_count_an_action():
    cases = _cases()[:1]
    result = _build(cases=cases,
        action_rows=[_action(cases[0], 1, contraticker=cases[0]["source_symbol"])])
    assert result["counts"]["action_rows"] == result["counts"]["action_candidate_rows"] == 1
    assert result["counts"]["action_candidate_relations"] == 1
    assert result["counts"]["action_primary_label_relations"] == 1
    assert result["counts"]["action_counterparty_label_relations"] == 1
    row = result["controls"][0]
    assert row["counts"]["action_candidate_rows"] == row["counts"]["action_rows_before_filing"] == 1
    assert row["counts"]["action_primary_label_rows"] == row["counts"]["action_counterparty_label_rows"] == 1
    assert row["counts"]["current_candidate_permatickers"] == 1
    assert row["effective_interval"] is row["public_known_by"] is None
    _all_false(row["authority"])
    _all_false(result["authority"])


def test_action_sides_can_discover_two_controls_without_aliasing_their_identities():
    cases = _cases()
    result = _build(cases=cases, action_rows=[_action(cases[0], 1, contraticker=cases[1]["source_symbol"])])
    assert result["counts"]["action_rows"] == result["counts"]["action_candidate_rows"] == 1
    assert result["counts"]["action_candidate_relations"] == 2
    assert result["counts"]["controls"] == result["counts"]["issuers"] == 2
    assert result["counts"]["controls_one_current_candidate"] == 2
    assert [row["counts"]["action_primary_label_rows"] for row in result["controls"]] == [1, 0]
    assert [row["counts"]["action_counterparty_label_rows"] for row in result["controls"]] == [0, 1]
    assert all(row["counts"]["action_candidate_rows"] == row["counts"]["current_candidate_permatickers"] == 1
               for row in result["controls"])
    assert all(row["effective_interval"] is row["public_known_by"] is None for row in result["controls"])
    _all_false(result["authority"])


def test_aggregate_agreement_guarantees_one_joint_row_not_every_joint_row():
    cases = _cases()[:1]
    good = _sec_row(cases[0])
    exact_wrong = dict(good, formType="4/A", acceptedDate="2020-10-02 16:02:03")
    other = dict(good, link="https://www.sec.gov/Archives/edgar/data/9999999/000000123420999999/a.xml",
                 finalLink="https://www.sec.gov/Archives/edgar/data/9999999/000000123420999999/a.xml")
    complete = _complete(cases, sec_rows=[good, exact_wrong, other])
    row = _build(cases=cases, complete=complete)["controls"][0]
    assert row["counts"]["fmp_candidate_rows"] == 3
    assert row["counts"]["fmp_joint_rows"] == row["counts"]["fmp_form_agreeing_rows"] == 2
    assert row["counts"]["fmp_naive_acceptance_agreeing_rows"] == 2
    assert row["fmp_form_exact_row_guaranteed"] is row["fmp_naive_acceptance_exact_row_guaranteed"] is True
    assert row["public_known_by"] is None


def test_nonexact_agreeing_rows_cannot_supply_an_exact_row_guarantee():
    cases = _cases()[:1]
    good = _sec_row(cases[0])
    wrong = dict(good, formType="4/A", acceptedDate="2020-10-02 16:02:03")
    other = dict(good, link="https://www.sec.gov/Archives/edgar/data/9999999/000000123420999999/a.xml",
                 finalLink="https://www.sec.gov/Archives/edgar/data/9999999/000000123420999999/a.xml")
    row = _build(cases=cases, complete=_complete(cases, sec_rows=[wrong, other]))["controls"][0]
    assert row["counts"]["fmp_candidate_rows"] == 2 and row["counts"]["fmp_joint_rows"] == 1
    assert row["fmp_form_exact_row_guaranteed"] is row["fmp_naive_acceptance_exact_row_guaranteed"] is False


def test_a_missing_control_cannot_disappear_behind_a_successful_prefix():
    cases = _cases()
    with pytest.raises(ValueError):
        _build(cases=cases, complete=_complete(cases[:1]))


@pytest.mark.parametrize("fault", ("ordinal-bool", "ordinal-gap", "unknown-financial-field", "nontext-field", "late-bad-row"))
def test_every_ticker_row_is_checked_including_the_tail(fault):
    values = list(_inputs())
    rows = deepcopy(values[2])
    if fault == "ordinal-bool": rows[-1]["source_row_ordinal"] = True
    elif fault == "ordinal-gap": rows[-1]["source_row_ordinal"] = 99
    elif fault == "unknown-financial-field": rows[-1]["marketcap"] = "9876543"
    elif fault == "nontext-field": rows[-1]["ticker"] = None
    else: rows.append({**rows[-1], "source_row_ordinal": 3, "unexpected": "PRIVATE TAIL"})
    values[2] = iter(rows)
    with pytest.raises(ValueError): m.build_audit(*values)


@pytest.mark.parametrize("fault", ("authority", "counter-bool", "counter-mismatch", "receipt-gap", "unattempted-projection"))
def test_provider_receipts_cannot_assert_authority_or_rewrite_accounting(fault):
    values = list(_inputs())
    complete = values[1]
    if fault == "authority": complete["authority"]["point_in_time_data"] = True
    elif fault == "counter-bool": complete["planned_requests"] = True
    elif fault == "counter-mismatch": complete["transport_invocation_count"] += 1
    elif fault == "receipt-gap": complete["receipts"][-1]["request_index"] = 99
    else: complete["receipts"][-1]["projection"] = deepcopy(complete["receipts"][0]["projection"])
    with pytest.raises(ValueError): m.build_audit(*values)


@pytest.mark.parametrize("fault", ("absolute-name", "traversal-name", "digest", "bytes-bool", "bytes-zero"))
def test_source_pins_are_exact_metadata_not_private_paths_or_assertions(fault):
    values = list(_inputs())
    pins = values[4]
    if fault == "absolute-name": pins["/private/account/source.json"] = pins.pop("controls.json")
    elif fault == "traversal-name": pins["../controls.json"] = pins.pop("controls.json")
    elif fault == "digest": pins["controls.json"]["sha256"] = "not-a-hash"
    elif fault == "bytes-bool": pins["controls.json"]["bytes"] = True
    else: pins["controls.json"]["bytes"] = 0
    with pytest.raises(ValueError): m.build_audit(*values)


@pytest.mark.parametrize("flag", (1, None, "false"))
def test_fixture_marker_is_an_exact_boolean(flag):
    with pytest.raises(ValueError): m.build_audit(*_inputs(), fixture_only=flag)


def test_two_invented_controls_cannot_claim_the_actual_twelve_control_scope():
    with pytest.raises(ValueError): m.build_audit(*_inputs(), fixture_only=False)


def test_input_mutation_cannot_change_an_already_built_audit():
    values = list(_inputs())
    result = m.build_audit(*values)
    before = _raw(result)
    values[0][0]["source_symbol"] = "CHANGED"
    values[1]["authority"]["point_in_time_data"] = True
    values[2][0]["permaticker"] = "CHANGED"
    values[4]["controls.json"]["sha256"] = "0" * 64
    assert _raw(result) == before
    assert m.public_summary(result)["result_sha256"] == hashlib.sha256(before).hexdigest()


@pytest.mark.parametrize("fault", ("clone", "authority", "counts", "nested"))
def test_detached_or_mutated_audit_never_becomes_genuine_public_evidence(fault):
    result = _build()
    if fault == "clone": result = deepcopy(result)
    elif fault == "authority": result["authority"]["point_in_time_data"] = True
    elif fault == "counts": result["counts"]["controls"] = 0
    else: result["controls"][0]["effective_interval"] = ["2020-01-01", "2021-01-01"]
    with pytest.raises(ValueError): m.public_summary(result)


def test_live_check_failure_stops_streaming_instead_of_publishing_partial_success():
    calls = [0]
    def check():
        calls[0] += 1
        if calls[0] == 3: raise RuntimeError("invented memory check stop")
    with pytest.raises(RuntimeError, match="invented memory check stop"):
        m.build_audit(*_inputs(), check=check)
