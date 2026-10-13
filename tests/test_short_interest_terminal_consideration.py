"""Fabricated archives only: merger amount is not cash availability."""
from __future__ import annotations

import csv
import io
import zipfile
import pytest

from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.sharadar_terminal_consideration as terminal

CLOCK = "2026-10-14T00:00:00Z"
ACTION_HEADERS = ["date", "action", "ticker", "name", "value", "contraticker", "contraname"]
DICT_HEADERS = ["table", "indicator", "title", "description", "unittype", "isprimarykey", "isfilter"]


def archive(table, headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr(table + ".csv", stream.getvalue())
    return master.CapturedSharadarMasterArchive(table, buffer.getvalue(), master.request_sha256("download-" + table))


def action(code="acquisitioncash", value="12.50", **changes):
    row = dict(zip(ACTION_HEADERS, ["2023-03-01", code, "SYN", "Synthetic target", value, "BUYER", "Synthetic buyer"]))
    row.update(changes)
    return [row[key] for key in ACTION_HEADERS]


def dictionary(code="acquisitioncash", **changes):
    stock = code == "acquisitionstock"
    row = dict(zip(DICT_HEADERS, ["actiontypes", code, "Acquisition Stock" if stock else "Acquisition Cash",
        "Number of stock shares received per acquired share." if stock else "Amount of cash received per acquired share in USD.",
        "shares/share" if stock else "USD/share", "N", "N"]))
    row.update(changes)
    return [row[key] for key in DICT_HEADERS]


def qualify(rows=None, dictionaries=None, *, action_headers=ACTION_HEADERS, dict_headers=DICT_HEADERS, clock=CLOCK):
    return terminal.qualify_sharadar_terminal_consideration(
        archive("actions", action_headers, rows if rows is not None else [action()]),
        archive("descriptions", dict_headers, dictionaries if dictionaries is not None else [dictionary()]),
        retrieved_at=clock)


def events(result):
    return result.to_payload()["terminal_events"]


def test_policy_frozen_and_all_execution_authority_closed():
    protocol = terminal.consideration_protocol()
    assert hash_payload(protocol) == terminal.PROTOCOL_SHA256
    assert protocol["new_provider_requests"] == protocol["credential_reads"] == 0
    authority = qualify().to_payload()["authority"]
    assert not any(value is True for key, value in authority.items() if key != "source_only")
    assert authority["actual_outcome_looks"] == authority["qc_attempts"] == authority["allocated_alpha"] == 0


@pytest.mark.parametrize("token,numerator,denominator", [
    ("12.50", 25, 2), ("1e-3", 1, 1000), ("9007199254740993", 9007199254740993, 1),
    ("0.3333333333333333333333333333", 3333333333333333333333333333, 10**28)])
def test_exact_lexical_money_never_binary_float(token, numerator, denominator):
    evidence = events(qualify([action(value=token)]))[0]["consideration_source_evidence"]
    assert evidence["per_target_unit"] == {"numerator": numerator, "denominator": denominator}
    assert evidence["currency"] == "USD" and evidence["unit"] == "acquired_share"
    assert evidence["actual_shareholder_payment_verified"] is False


@pytest.mark.parametrize("token", ["", "0", "-1", "NaN", "Infinity", "1/2", " 12", "1e999", "true"])
def test_missing_negative_nonfinite_or_unbounded_amount_not_zero(token):
    row = events(qualify([action(value=token)]))[0]
    assert row["consideration_source_evidence"] is None
    assert row["raw_cells"][4] == token and row["field_refusal_reasons"]


def test_source_date_never_becomes_payment_timestamp_or_admission():
    row = events(qualify())[0]
    assert row["consideration_source_evidence"]["source_action_date"] == "2023-03-01"
    assert row["payment_date"] is row["payment_timestamp"] is None
    assert row["terminal_economics_admitted"] is False
    assert "source_action_date_not_authenticated_holder_payment" in row["payment_refusal_reasons"]


def test_unique_cash_and_stock_are_separate_additive_candidates_not_summed():
    result = qualify([action(), action("acquisitionstock", "0.25")], [dictionary(), dictionary("acquisitionstock")]).to_payload()
    assert [event["consideration_source_evidence"]["kind"] for event in result["terminal_events"]] == ["cash", "received_stock"]
    assert result["packages"][0]["additive_cash_and_stock_field_candidates"] is True
    assert result["packages"][0]["economic_package_admitted"] is False
    assert result["packages"][0]["payment_date"] is None


@pytest.mark.parametrize("code", ["acquisitionelectcash", "acquisitionelectstock", "acquisitionalternativecommon", "acquisitioncohortcashusd", "acquisitioncvr"])
def test_election_cohort_and_CVR_never_additive(code):
    result = qualify([action(), action("acquisitionstock", "0.25"), action(code)],
                     [dictionary(), dictionary("acquisitionstock"), dictionary(code)]).to_payload()
    assert result["terminal_events"][2]["consideration_source_evidence"] is None
    assert result["packages"][0]["additive_cash_and_stock_field_candidates"] is False
    assert result["packages"][0]["package_refusal_reason"] == "election_cohort_or_CVR_routes_not_additive"


def test_acquisitionby_final_marketcap_not_cash_per_share():
    row = events(qualify([action("acquisitionby", "900000000")],
                        [dictionary("acquisitionby", description="Final market cap of acquired company.")]))[0]
    assert row["consideration_source_evidence"] is None
    assert row["normalized"]["value"] == {"numerator": 900000000, "denominator": 1}
    assert row["field_refusal_reasons"]


def test_ancillary_marketcap_never_added_but_does_not_replace_valid_components():
    result = qualify([action(), action("acquisitionstock", "0.25"), action("acquisitionby", "999999")],
        [dictionary(), dictionary("acquisitionstock"), dictionary("acquisitionby", description="Final market cap.")]).to_payload()
    assert result["terminal_events"][2]["consideration_source_evidence"] is None
    assert result["packages"][0]["additive_cash_and_stock_field_candidates"] is True


def test_future_warehouse_action_cannot_claim_completed_received_amount():
    row = events(qualify([action(date="2027-03-01")]))[0]
    assert row["consideration_source_evidence"] is None
    assert "future_action_not_completed_consideration" in row["field_refusal_reasons"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "malformed_peer", "wrong_unit", "marketcap", "wrong_flags", "wrong_title"])
def test_dictionary_conflicts_or_identifiable_invalid_peers_block_legacy(change):
    rows = [dictionary()]
    if change == "missing": rows = []
    if change == "duplicate": rows.append(dictionary())
    if change == "malformed_peer": rows.append(dictionary(indicator=" acquisitioncash ", isfilter="invalid"))
    if change == "wrong_unit": rows = [dictionary(unittype="USD millions")]
    if change == "marketcap": rows = [dictionary(description="Cash share acquisition final market capitalization.")]
    if change == "wrong_flags": rows = [dictionary(isprimarykey="true")]
    if change == "wrong_title": rows = [dictionary(title="Acquisition Market Value")]
    result = qualify(dictionaries=rows).to_payload()
    assert result["terminal_events"][0]["consideration_source_evidence"] is None
    assert len(result["dictionary_entries"]) == len(rows)


@pytest.mark.parametrize("invalid_peer", [False, True])
def test_duplicate_action_primary_keys_refuse_all_copies_even_bad_numeric_peer(invalid_peer):
    result = qualify([action(), action(value="NaN" if invalid_peer else "99")]).to_payload()
    assert len(result["terminal_events"]) == 2
    assert all(event["consideration_source_evidence"] is None for event in result["terminal_events"])
    assert all("duplicate_terminal_primary_key_all_peers_refused" in event["field_refusal_reasons"] for event in result["terminal_events"])


def test_currency_specific_gross_units_separately_dictionary_bound():
    desc = dictionary("acquisitioncashhkd", title="Acquisition Cash HKD", unittype="HKD/target unit",
        description="Native cash consideration in HKD per historical target listing unit. Value is contractual gross cash. Date is warehouse acquisition date.")
    row = events(qualify([action("acquisitioncashhkd", "0.05")], [desc]))[0]
    evidence = row["consideration_source_evidence"]
    assert evidence["currency"] == "HKD" and evidence["unit"] == "historical_target_listing_unit"
    assert evidence["semantic_evidence_id"] == "captured_exact_ACTIONTYPES_dictionary"
    assert row["payment_date"] is None


@pytest.mark.parametrize("field,value", [("unittype", "USD/target unit"), ("description", "Cash amount in HKD."), ("indicator", "acquisitioncashusd")])
def test_currency_claim_requires_matching_exact_dictionary(field, value):
    desc = dictionary("acquisitioncashhkd", title="Acquisition Cash HKD", unittype="HKD/target unit",
        description="Native cash consideration in HKD per historical target listing unit. Value is contractual gross cash.")
    desc[DICT_HEADERS.index(field)] = value
    assert events(qualify([action("acquisitioncashhkd")], [desc]))[0]["consideration_source_evidence"] is None


def test_delisted_missing_value_and_unsupported_terminal_rows_retained():
    result = qualify([action("delistedbankrupt", ""), action("liquidation", ""), action("unrecognized")],
                     [dictionary("unrecognized", description="A terminal merger action.")]).to_payload()
    assert len(result["terminal_events"]) == 3
    assert all(event["consideration_source_evidence"] is None for event in result["terminal_events"])
    assert [event["origin"]["row_index"] for event in result["terminal_events"]] == [0, 1, 2]


@pytest.mark.parametrize("kind", ["action", "dictionary"])
def test_unknown_columns_refuse_without_losing_rows(kind):
    if kind == "action": result = qualify([action() + ["extra"]], action_headers=ACTION_HEADERS + ["unknown"])
    else: result = qualify(dictionaries=[dictionary() + ["extra"]], dict_headers=DICT_HEADERS + ["unknown"])
    assert events(result)[0]["consideration_source_evidence"] is None


@pytest.mark.parametrize("headers", [ACTION_HEADERS + ["value"], ACTION_HEADERS[:-1]])
def test_duplicate_or_missing_headers_raise(headers):
    with pytest.raises(terminal.SharadarTerminalConsiderationError):
        qualify(rows=[], action_headers=headers)


@pytest.mark.parametrize("clock", ["2026-10-14", "2026-10-14T00:00:00+00:00", None])
def test_canonical_UTC_clock_required(clock):
    with pytest.raises(terminal.SharadarTerminalConsiderationError, match="clock"): qualify(clock=clock)


def test_caller_archive_and_payload_mutation_do_not_change_snapshot(monkeypatch):
    first, second = archive("actions", ACTION_HEADERS, [action()]), archive("descriptions", DICT_HEADERS, [dictionary()])
    result = terminal.qualify_sharadar_terminal_consideration(first, second, retrieved_at=CLOCK)
    before = result.to_bytes()
    object.__setattr__(first, "raw", b"changed source")
    payload = result.to_payload()
    payload["terminal_events"][0]["payment_date"] = "2023-03-01"
    monkeypatch.setattr(terminal, "_build", lambda *args, **kwargs: pytest.fail("no full source reparse"))
    assert result.to_bytes() == before


def test_report_mutation_cannot_be_coherently_resealed():
    result = qualify()
    payload = result.to_payload()
    payload["terminal_events"][0]["payment_date"] = "2023-03-01"
    payload.pop("report_sha256")
    payload["report_sha256"] = hash_payload(payload)
    object.__setattr__(result, "_report_bytes", canonical_json(payload).encode())
    object.__setattr__(result, "_report_sha256", payload["report_sha256"])
    with pytest.raises(terminal.SharadarTerminalConsiderationError, match="sealed"): result.to_bytes()


def test_exact_typed_factory_and_source_order():
    with pytest.raises(terminal.SharadarTerminalConsiderationError): terminal.SharadarTerminalConsideration()
    with pytest.raises(terminal.SharadarTerminalConsiderationError):
        terminal.qualify_sharadar_terminal_consideration(archive("descriptions", DICT_HEADERS, []), archive("actions", ACTION_HEADERS, []), retrieved_at=CLOCK)
