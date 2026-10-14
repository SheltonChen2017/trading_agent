"""Invented nonfinancial metadata; run under process-tree network denial."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from research import insider_buying_sharadar_reference_cohort as m


def enc(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory():
    forms = ("3", "3/A", "4", "4/A", "5", "5/A")
    specifications = [("0000000001", "ABC", "4"), ("0000000001", "abc", "4/A"),
                      ("0000000002", "ABC", "3"), ("0000000003", "OLD", "4")]
    rows, issuers = [], {}
    for ordinal, (cik, label, form) in enumerate(specifications, 1):
        rows.append({"source_record_ordinal": ordinal, "accession_number": f"0000000001-06-{ordinal:06d}",
            "form_type": form, "raw_issuer_cik": str(int(cik)), "issuer_cik": cik,
            "raw_symbol_label": label, "raw_filing_date": "03-JAN-2006", "filing_date": "2006-01-03",
            "relevant_form4_or_amendment": form in {"4", "4/A"}, "accession_year_mismatch": False})
        item = issuers.setdefault(cik, {"issuer_cik": cik, "symbol_labels": [], "filing_count": 0,
            "first_filing_date": "2006-01-03", "last_filing_date": "2006-01-03", "form_counts": dict.fromkeys(forms, 0)})
        if label not in item["symbol_labels"]:
            item["symbol_labels"].append(label)
        item["symbol_labels"].sort(); item["filing_count"] += 1; item["form_counts"][form] += 1
    return {"schema": "insider-2006q1-earnings-issuer-label-inventory-v1", "period": "2006Q1",
        "scope": "complete_submission_metadata_only", "filings": rows, "all_form_issuers": list(issuers.values()),
        "accounting": {"filings": 4, "form_counts": {"3": 1, "3/A": 0, "4": 2, "4/A": 1, "5": 0, "5/A": 0},
                       "all_form_issuers": 3}}


def ticker(*, ticker="ABC", perma="1", cik="1", table="stocks", **changes):
    result = dict.fromkeys(m.TICKER_COLUMNS, "")
    result.update(table=table, permaticker=perma, ticker=ticker, name="PRIVATE FIXTURE NAME", exchange="NYSE",
        isdelisted="N", category="Domestic Common Stock", firstpricedate="2000-01-01", lastpricedate="2026-09-13",
        firstadded="2013-01-01", lastupdated="2026-09-13",
        secfilings=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}" if cik else "")
    result.update(changes)
    return result


def action(*, ticker="ABC", contra="XYZ", day="2001-01-01", label="fixture-counterparty", **changes):
    result = {"date": day, "action": label, "ticker": ticker, "name": "PRIVATE FIXTURE NAME",
              "contraticker": contra, "contraname": "PRIVATE CONTRA NAME"}
    result.update(changes)
    return result


def fixture(*, tickers=None, actions=None):
    tickers = [ticker(), ticker(table="fundamentals"), ticker(ticker="NEW", perma="3", cik="3"),
               ticker(ticker="UNRELATED", perma="9", cik="9"), ticker(ticker="", perma="", cik="", table="holdings_investor")] if tickers is None else tickers
    actions = [action(), action(ticker="OLD", contra="NEW", day="2020-01-01"),
               action(ticker="UNRELATED", contra="", day=""), action(ticker="", contra="", label="")] if actions is None else actions
    manifest = {"schema": "arv2-sharadar-source-capture-artifact-v2", "capture_started_at": "2026-09-14T00:33:29Z",
        "capture_completed_at": "2026-09-14T00:35:00Z", "archives": [], **dict.fromkeys(("api_key_persisted",
        "redirect_url_persisted", "outcome_access_performed", "quantconnect_io_performed", "pit_security_master_constructed",
        "backtest_input_constructed", "terminal_payoff_constructed"), False)}
    for index, (dataset, rows, columns) in enumerate((("tickers", tickers, m.TICKER_COLUMNS), ("actions", actions, m.ACTION_COLUMNS),
                                                   ("fundamentals", [None], ("dimension",))), 1):
        manifest["archives"].append({"dataset": dataset, "archive_file": f"0{index}-{dataset}-years-full.zip",
            "archive_sha256": str(index) * 64, "row_count": len(rows), "members": [{"name": dataset + ".csv",
            "content_sha256": str(index + 3) * 64, "row_count": len(rows), "columns": list(columns)}]})
    data = {"inventory": inventory(), "manifest": manifest, "tickers": tickers, "actions": actions}
    return data


def arguments(data=None, *, pretty_manifest=False):
    data = fixture() if data is None else data
    manifest_raw = json.dumps(data["manifest"], indent=2).encode() if pretty_manifest else enc(data["manifest"])
    inventory_raw = enc(data["inventory"])
    result = {"inventory_raw": inventory_raw, "inventory_sha256": sha(inventory_raw),
              "capture_manifest_raw": manifest_raw, "capture_manifest_sha256": sha(manifest_raw)}
    for index, (dataset, columns, schema) in enumerate((("tickers", m.TICKER_COLUMNS, m.TICKERS_SCHEMA),
                                                     ("actions", m.ACTION_COLUMNS, m.ACTIONS_SCHEMA))):
        entry = data["manifest"]["archives"][index]
        projection = {"schema": schema, "capture_manifest_sha256": sha(manifest_raw), "archive_sha256": entry["archive_sha256"],
            "member_sha256": entry["members"][0]["content_sha256"], "columns": list(columns),
            "rows": [{"source_row_ordinal": ordinal, **row} for ordinal, row in enumerate(data[dataset], 1)]}
        raw = enc(projection); result[dataset + "_projection_raw"] = raw; result[dataset + "_projection_sha256"] = sha(raw)
    return result


def payload(data=None):
    return m.assess_sharadar_cohort(**arguments(data)).to_payload()


def mutate_projection(args, dataset, update):
    result = dict(args); body = json.loads(result[dataset + "_projection_raw"])
    update(body); raw = enc(body)
    result[dataset + "_projection_raw"] = raw; result[dataset + "_projection_sha256"] = sha(raw)
    return result


def test_complete_all_form_accounting_is_not_admission():
    result = payload()
    assert result["source_filings"] == 4 and result["all_form_issuer_count"] == 3 and result["relevant_issuer_count"] == 2
    assert result["source_form_counts"]["3"] == 1
    assert result["ticker_rows_accounted"] == result["source_ticker_rows"] == 5
    assert result["action_rows_accounted"] == result["source_action_rows"] == 4
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert all(item["historical_mapping_admitted"] is False for item in result["issuer_relations"])
    assert all(item["same_security_alias_admitted"] is False for item in result["retrospective_action_rows"])


def test_current_table_repetitions_are_one_candidate_security():
    result = payload(); issuer = result["issuer_relations"][0]
    assert issuer["current_cik_candidate_permatickers"] == ["1"]
    assert issuer["candidate_disposition"] == "one_current_cik_candidate"
    assert result["provider_share_class_candidate_groups"][0]["source_ordinals"] == [1, 2]


def test_casefolded_multicik_label_remains_nonadmitted():
    result = payload()
    assert result["issuer_relations"][1]["candidate_disposition"] == "label_only_candidates"
    assert result["issuer_relations"][0]["candidate_label_relations"][0]["source_label_issuer_ciks"] == ["0000000001", "0000000002"]


def test_exact_and_casefold_only_candidates_are_not_silently_equivalent():
    result = payload(fixture(tickers=[ticker(ticker="ABC", perma="1"), ticker(ticker="abc", perma="2")]))
    labels = result["issuer_relations"][0]["candidate_label_relations"]
    assert labels[0]["exact_candidate_permatickers"] == ["1"]
    assert labels[0]["casefold_only_candidate_permatickers"] == ["2"]
    assert labels[1]["exact_candidate_permatickers"] == ["2"]
    assert labels[1]["casefold_only_candidate_permatickers"] == ["1"]
    assert all(row["historical_mapping_admitted"] is False for row in labels)


def test_future_counterparty_does_not_union_security_ids():
    result = payload(); issuer = result["issuer_relations"][2]
    assert issuer["candidate_action_source_ordinals"] == [2]
    assert issuer["current_cik_candidate_permatickers"] == ["3"]
    assert result["future_action_context_is_historical_selection_information"] is False
    assert result["qc_identifier_observation_is_economic_knowledge"] is False


def test_names_are_not_keys_and_unknown_rows_remain_accounted():
    result = payload(fixture(tickers=[ticker(ticker="NOTMATCH", perma="7", cik="7")], actions=[action(ticker="", contra="", label="", day="")]))
    assert all(item["candidate_disposition"] == "no_current_reference_candidate" for item in result["issuer_relations"])
    assert result["action_quarantined_rows"] == 1 and result["unreferenced_action_rows"] == 1
    assert result["names_used_as_join_keys"] is False


def test_multiple_share_classes_and_competing_ciks_are_retained():
    data = fixture(tickers=[ticker(), ticker(perma="2"), ticker(perma="8", cik="3", ticker="OLD"), ticker(perma="8", cik="2", ticker="OLD")])
    result = payload(data)
    assert result["issuer_relations"][0]["candidate_disposition"] == "multiple_current_share_class_candidates"
    assert result["issuer_relations"][2]["candidate_disposition"] == "conflicting_current_cik_candidates"
    assert result["provider_share_class_candidate_groups"][2]["issuer_cik_candidates"] == ["0000000002", "0000000003"]


def test_duplicate_keys_retain_every_nonfinancial_row():
    data = fixture(tickers=[ticker(), ticker(exchange="NASDAQ")], actions=[action(), action()])
    result = payload(data)
    assert result["duplicate_ticker_primary_keys"] == [{"source_ordinals": [1, 2], "conflicting_nonfinancial_projection": True}]
    assert result["duplicate_action_nonfinancial_keys"] == [[1, 2]]
    assert result["cohort_referenced_unique_action_rows"] == 2
    assert result["cohort_action_relation_count"] == 4


def test_noncanonical_original_manifest_remains_hash_bound():
    result = m.assess_sharadar_cohort(**arguments(pretty_manifest=True)).to_payload()
    assert result["source_ticker_rows"] == 5


@pytest.mark.parametrize("dataset", ["tickers", "actions"])
@pytest.mark.parametrize("update", [lambda body: body["rows"].pop(), lambda body: body["rows"][0].update(source_row_ordinal=True),
    lambda body: body["rows"][0].update(source_row_ordinal=2), lambda body: body["rows"][0].update(value="LICENSED NUMERIC FORBIDDEN"),
    lambda body: body.update(member_sha256="f" * 64), lambda body: body.update(archive_sha256="f" * 64),
    lambda body: body.update(capture_manifest_sha256="f" * 64), lambda body: body["columns"].reverse(),
    lambda body: body.update(schema=[]), lambda body: body["rows"][0].update(ticker=None),
    lambda body: body["rows"][0].update(ticker="\x00"), lambda body: body["rows"][0].update(ticker="A" * 16385)])
def test_projection_mutations_refuse_without_dropping(dataset, update):
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**mutate_projection(arguments(), dataset, update))


@pytest.mark.parametrize("update", [lambda body: body.update(capture_started_at=None), lambda body: body.update(capture_started_at="2027-01-01T00:00:00Z"),
    lambda body: body.update(capture_started_at="2026-09-14T00:33:29"), lambda body: body.update(outcome_access_performed=True),
    lambda body: body["archives"][0].update(row_count=True), lambda body: body["archives"][0]["members"][0].update(row_count=True),
    lambda body: body["archives"][0]["members"][0].update(columns=[]), lambda body: body["archives"].reverse(),
    lambda body: body["archives"][0].update(archive_sha256=None)])
def test_bad_manifest_refuses(update):
    data = fixture(); update(data["manifest"])
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**arguments(data))


@pytest.mark.parametrize("field", ["inventory_sha256", "capture_manifest_sha256", "tickers_projection_sha256", "actions_projection_sha256"])
def test_external_digest_is_not_self_attested(field):
    args = arguments(); args[field] = "e" * 64
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**args)


@pytest.mark.parametrize("raw", [b'{"schema":NaN}', b'{"schema":1,"schema":2}', b'[]', b'\xff'])
def test_bad_projection_json_is_sanitized(raw):
    args = arguments(); args["tickers_projection_raw"] = raw; args["tickers_projection_sha256"] = sha(raw)
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**args)


def test_inventory_cannot_skip_context_issuer():
    data = fixture(); data["inventory"]["all_form_issuers"].pop(1)
    with pytest.raises(m.SharadarReferenceCohortError, match="source_inventory_refused"):
        m.assess_sharadar_cohort(**arguments(data))


def test_unknown_dates_urls_and_flags_are_not_dropped():
    data = fixture(tickers=[ticker(secfilings="https://evil.example/?CIK=1", firstpricedate="2006-02-31", isdelisted="?")],
                   actions=[action(day="2006-02-31", contra="NOT VALID")])
    result = payload(data)
    assert result["ticker_quarantined_rows"] == result["action_quarantined_rows"] == 1
    assert result["ticker_quarantine_reason_counts"]["sec_filings_url_not_canonical"] == 1
    assert result["action_quarantine_reason_counts"]["action_date_unknown"] == 1


def test_boolean_member_count_cannot_impersonate_single_row():
    data = fixture(tickers=[ticker()]); data["manifest"]["archives"][0]["members"][0]["row_count"] = True
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**arguments(data))


def test_invalid_unicode_projection_is_sanitized():
    args = mutate_projection(arguments(), "tickers", lambda body: body["rows"][0].update(name="\ud800"))
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**args)


def test_invalid_unicode_source_inventory_is_sanitized():
    data = fixture(); data["inventory"]["filings"][0]["raw_symbol_label"] = "\ud800"
    with pytest.raises(m.SharadarReferenceCohortError):
        m.assess_sharadar_cohort(**arguments(data))


def test_canonical_output_is_deterministic_and_factory_bound():
    first = m.assess_sharadar_cohort(**arguments()); second = m.assess_sharadar_cohort(**arguments())
    assert first.canonical_bytes() == second.canonical_bytes() and first.sha256 == sha(first.canonical_bytes())
    for forged in (m.SharadarReferenceCohortAssessment(first.canonical_bytes()), replace(first), replace(first, _raw=b"{}")):
        with pytest.raises(m.SharadarReferenceCohortError):
            forged.canonical_bytes()
    object.__setattr__(first, "_raw", b"{}")
    with pytest.raises(m.SharadarReferenceCohortError):
        first.to_payload()
