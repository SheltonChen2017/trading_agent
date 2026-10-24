"""Fabricated source-only v2 bindings, never market or outcome evidence."""
from __future__ import annotations

import copy
from decimal import localcontext

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.latest_revised_runner import (
    LatestRevisedRunError,
    _require_public_fixture,
)
from research.short_interest_etf.latest_revised_source import (
    LatestRevisedBundle,
    LatestRevisedSourceError,
)
from research.short_interest_etf.sharadar_actual_input_binding import (
    INTERFACE_SCHEMA,
    PROTOCOL_SHA256,
    SCHEMA,
    SharadarActualInputBinding,
    SharadarActualInputBindingError,
    _rational,
    bind_sharadar_companion,
    binding_protocol,
)
from research.short_interest_etf.sharadar_companion_qualification import SYMBOLS
from test_short_interest_sharadar_companion_qualification import (
    documents,
    report,
)


def table(payload, name):
    return next(row for row in payload["source_tables"] if row["table"] == name)


def candidate(payload, name):
    return next(row for row in payload["candidate_bindings"] if row["table"] == name)


def supplement(*, conflicting_reference=False, dividend=False):
    from research.short_interest_etf.massive_action_supplement import (
        REQUEST_IDS,
        CapturedMassiveActionResponse,
        massive_request,
        qualify_massive_action_supplement,
        request_sha256,
    )
    captures = []
    for request_id in REQUEST_IDS:
        params = massive_request(request_id)["params"]
        rows = []
        if request_id.startswith("reference-") and params["ticker"] == "AAPL" and params["date"] == "2023-02-28":
            active = params["active"] == "true"
            if active or conflicting_reference:
                rows = [{"ticker": "AAPL", "active": active,
                         "composite_figi": "BBG000000001",
                         "share_class_figi": "BBG000000002" if active else "BBG000000003",
                         "primary_exchange": "XNAS", "type": "CS",
                         "locale": "us", "market": "stocks"}]
        elif request_id == "rows-dividends" and dividend:
            rows = [{"id": "fabricated-dividend", "ticker": "AAPL",
                     "ex_dividend_date": "2023-03-01", "pay_date": "2023-03-15",
                     "cash_amount": 1, "currency": "USD"}]
        raw = canonical_json({"status": "OK", "results": rows}).encode("utf-8")
        captures.append(CapturedMassiveActionResponse(request_id, request_sha256(request_id), raw))
    return qualify_massive_action_supplement(tuple(captures), retrieved_at="2026-10-11T13:00:00Z")


def test_versioned_protocol_is_independently_pinned_and_detached():
    payload = binding_protocol()
    assert hash_payload(payload) == PROTOCOL_SHA256
    assert payload["interface_schema"] == INTERFACE_SCHEMA
    payload["authority"]["source_admitted"] = True
    payload["public_known_contract_gaps"].clear()
    assert hash_payload(binding_protocol()) == PROTOCOL_SHA256


def test_provider_namespace_and_composite_FIGI_never_become_share_class_identity():
    payload = bind_sharadar_companion(report()).to_payload()
    assert payload["schema"] == SCHEMA
    assert payload["requested_raw_tokens"] == list(SYMBOLS)
    identity = payload["provider_identity_assertions"][0]["normalized"]
    assert identity["provider_security_id"] == "sharadar:permaticker:12345"
    assert identity["share_class_figi"] is None
    assert identity["composite_figi_assertion"] == "BBG000000001"
    assert identity["effective_historical_mapping_admitted"] is False
    assert identity["current_reference_assertions"]["firstpricedate"] == "2000-01-03"
    for row in payload["candidate_bindings"]:
        assert row["binding_status"] == "unadmitted_source_only_candidate"
        assert row["historical_ticker_permaticker_link"] is None
        assert "security_id" not in row
        assert "effective_from" not in row and "effective_to" not in row
        assert "historical_ticker_to_permaticker_link_not_established" in row["refusal_reasons"]


def test_exact_rational_price_and_volume_observations_are_preserved_without_rounding():
    source = report()
    with localcontext() as context:
        context.prec = 2
        payload = bind_sharadar_companion(source).to_payload()
    stock = candidate(payload, "stocks")["source_observation"]["normalized"]
    assert stock["raw_open"] == {"numerator": 20, "denominator": 3}
    assert stock["raw_volume"] == {"numerator": 21, "denominator": 2}
    assert stock["raw_close"] == {"numerator": 6, "denominator": 1}
    assert payload["source_tables"] == source.to_payload()["tables"]


def test_every_provenance_hash_is_retained_without_new_price_or_shares_arithmetic():
    source = report()
    payload = bind_sharadar_companion(source).to_payload()
    original = source.to_payload()
    assert payload["source_report_sha256"] == original["report_sha256"]
    assert payload["source_capture_identity_sha256"] == original["capture_identity_sha256"]
    assert payload["source_protocol_sha256"] == original["protocol_sha256"]
    for row in payload["candidate_bindings"]:
        observation = row["source_observation"]
        assert observation in table(payload, row["table"])["rows"]
        assert hash_payload(observation["normalized"]) == observation["normalized_record_sha256"]
    fundamental = candidate(payload, "fundamentals")
    assert fundamental["same_share_class_denominator"] is None
    assert "primary_class_only_no_secondary_denominator_transfer" in fundamental["refusal_reasons"]
    assert fundamental["source_observation"]["normalized"]["sharesbas"] == {
        "numerator": 100000, "denominator": 1,
    }


@pytest.mark.parametrize("table_name", ["stocks", "daily", "actions", "fundamentals", "tickers"])
def test_missing_pages_and_requested_raw_names_are_not_dropped(table_name):
    docs = documents()
    docs["rows-" + table_name] = {"count": 0, "data": []}
    payload = bind_sharadar_companion(report(docs)).to_payload()
    empty = table(payload, table_name)
    assert empty["rows"] == []
    assert [row["ticker"] for row in empty["requested_symbol_cells"]] == list(SYMBOLS)
    assert {row["status"] for row in empty["requested_symbol_cells"]} == {"missing"}
    if table_name == "tickers":
        assert all("missing_current_provider_identity_assertion" in row["refusal_reasons"]
                   for row in payload["candidate_bindings"])


def test_malformed_duplicate_and_all_original_refusals_remain_present():
    docs = documents()
    good = docs["rows-stocks"]["data"][0]
    bad = copy.deepcopy(good)
    bad["open"] = True
    docs["rows-stocks"] = {"count": 2, "data": [bad, good]}
    source = report(docs)
    payload = bind_sharadar_companion(source).to_payload()
    assert payload["source_tables"] == source.to_payload()["tables"]
    assert len(table(payload, "stocks")["refusals"]) == 2
    assert not any(row["table"] == "stocks" for row in payload["candidate_bindings"])


def test_multiple_permatickers_do_not_select_a_current_or_historical_winner():
    docs = documents()
    additional = copy.deepcopy(docs["rows-tickers"]["data"][0])
    additional["permaticker"] = 67890
    docs["rows-tickers"]["data"].append(additional)
    docs["rows-tickers"]["count"] = 2
    payload = bind_sharadar_companion(report(docs)).to_payload()
    stock = candidate(payload, "stocks")
    assert len(stock["current_provider_identity_candidates"]) == 2
    assert "ambiguous_current_provider_identity_assertions" in stock["refusal_reasons"]
    assert stock["historical_ticker_permaticker_link"] is None


def test_primary_class_shares_never_transfer_to_another_class_or_use_sharefactor():
    docs = documents()
    docs["rows-fundamentals"]["data"][0].update(ticker="BRK.B", sharesbas=999, sharefactor=1500)
    payload = bind_sharadar_companion(report(docs)).to_payload()
    row = candidate(payload, "fundamentals")
    assert row["same_share_class_denominator"] is None
    assert row["source_observation"]["normalized"]["sharesbas"]["numerator"] == 999
    assert row["source_observation"]["normalized"]["sharefactor"]["numerator"] == 1500
    assert "same_share_class_denominator_not_admitted" in row["refusal_reasons"]


def test_missing_cashflows_do_not_become_payment_clocks_or_terminal_zero():
    docs = documents()
    docs["rows-actions"]["data"][0].update(action="delisted", value=None)
    payload = bind_sharadar_companion(report(docs)).to_payload()
    row = candidate(payload, "actions")
    action = row["source_observation"]["normalized"]
    assert action["value"] is None and action["payment_timestamp"] is None
    assert action["effective_instant_admitted"] is False
    assert action["terminal_economics_admitted"] is False
    assert "date_only_action_has_no_admitted_effective_payment_or_terminal_clock" in row["refusal_reasons"]


def test_absent_supplement_and_entire_authority_stay_closed_with_zero_counters():
    payload = bind_sharadar_companion(report()).to_payload()
    assert payload["supplement_tables"] == []
    for key in ("supplement_report_sha256", "supplement_capture_identity_sha256",
                "supplement_protocol_sha256", "supplement_retrieved_at"):
        assert payload[key] is None
    authority = payload["authority"]
    assert authority["source_only"] is True
    for key, value in authority.items():
        if key == "source_only":
            continue
        assert value == 0 if key in {"actual_outcome_looks", "allocated_alpha", "qc_attempts"} else value is False
    assert payload["population_scope"] == "ten_distinct_raw_tokens_source_sample_not_full_study"
    assert len(payload["required_factual_qualifications"]) == 8
    assert payload["publication_scope"] == "private_only_not_data_usability_publication"


@pytest.mark.parametrize("value", [None, {}, [], True, object()])
def test_caller_payloads_and_verified_flags_are_not_source_objects(value):
    with pytest.raises(SharadarActualInputBindingError, match="exact_Sharadar"):
        bind_sharadar_companion(value)


def test_detached_nested_outputs_cannot_modify_the_source_or_inventory():
    source = report()
    binding = bind_sharadar_companion(source)
    payload = binding.to_payload()
    digest = binding.sha256
    payload["source_tables"][2]["rows"].clear()
    payload["candidate_bindings"][0]["current_provider_identity_candidates"].clear()
    payload["authority"]["ready_for_empirical_backtest"] = True
    assert binding.sha256 == digest
    assert binding.to_payload()["authority"]["ready_for_empirical_backtest"] is False
    assert binding.to_payload()["source_tables"] == source.to_payload()["tables"]


def test_rehashed_publication_mutation_cannot_open_authority():
    binding = bind_sharadar_companion(report())
    changed = binding.to_payload()
    changed["authority"]["source_admitted"] = True
    changed["binding_sha256"] = hash_payload({key: value for key, value in changed.items()
                                              if key != "binding_sha256"})
    object.__setattr__(binding, "_payload_json", canonical_json(changed))
    with pytest.raises(SharadarActualInputBindingError, match="inventory_changed"):
        binding.to_payload()


def test_source_replacement_or_raw_receipt_mutation_cannot_change_captured_binding():
    binding = bind_sharadar_companion(report())
    changed = documents()
    changed["rows-stocks"]["data"][0]["volume"] = 10
    object.__setattr__(binding, "qualification", report(changed))
    with pytest.raises(SharadarActualInputBindingError, match="source_identity_changed"):
        binding.to_payload()
    binding = bind_sharadar_companion(report())
    object.__setattr__(binding.qualification.captures[-1], "raw", b'{"count":0,"data":[]}')
    with pytest.raises(ValueError, match="identity_changed"):
        binding.to_payload()


def test_binding_subclass_cannot_override_revalidation():
    class Subclass(SharadarActualInputBinding):
        pass
    with pytest.raises(SharadarActualInputBindingError, match="exact_binding"):
        Subclass(report())


def test_binding_cannot_be_cast_to_v1_or_run_as_an_actual_input(tmp_path):
    binding = bind_sharadar_companion(report())
    with pytest.raises(LatestRevisedSourceError):
        LatestRevisedBundle(canonical_json(binding.to_payload()))
    path = tmp_path / "binding.json"
    path.write_text(canonical_json(binding.to_payload()), encoding="utf-8")
    with pytest.raises(LatestRevisedRunError, match="not the pinned public fabricated"):
        _require_public_fixture(path)


@pytest.mark.parametrize("value", [
    {"numerator": 1, "denominator": 0}, {"numerator": 2, "denominator": 4},
    {"numerator": True, "denominator": 1}, {"numerator": 1, "denominator": True},
    {"numerator": 1.5, "denominator": 1}, {"numerator": -1, "denominator": 1},
    {"numerator": 1, "denominator": -1}, {"numerator": 1, "denominator": 1, "verified": True},
    None, 1, "1",
])
def test_exact_canonical_rationals_reject_coercion_or_unknown_fields(value):
    with pytest.raises(SharadarActualInputBindingError):
        _rational(value)


def test_canonical_zero_and_nullable_values_do_not_create_positive_observations():
    _rational({"numerator": 0, "denominator": 1})
    _rational(None, nullable=True)
    _rational({"numerator": -1, "denominator": 2}, signed=True)
    with pytest.raises(SharadarActualInputBindingError, match="sign"):
        _rational({"numerator": 0, "denominator": 1}, positive=True)


def test_exact_date_reference_candidates_do_not_admit_even_matching_composite_and_class():
    docs = documents()
    docs["rows-stocks"]["data"][0]["date"] = "2023-02-28"
    extra = supplement()
    binding = bind_sharadar_companion(report(docs), extra)
    payload = binding.to_payload()
    row = candidate(payload, "stocks")
    assert len(row["exact_date_reference_candidates"]) == 1
    reference = row["exact_date_reference_candidates"][0]["normalized"]
    assert reference["share_class_figi"] == "BBG000000002"
    assert reference["composite_figi"] == row["current_provider_identity_candidates"][0]["normalized"]["composite_figi_assertion"]
    assert row["historical_ticker_permaticker_link"] is None
    assert row["same_share_class_denominator"] is None
    assert row["binding_status"] == "unadmitted_source_only_candidate"
    assert payload["supplement_tables"] == extra.to_payload()["tables"]
    assert payload["supplement_report_sha256"] == extra.sha256
    assert payload["authority"]["ready_for_empirical_backtest"] is False


def test_wrong_date_or_ambiguous_dated_reference_never_backdates_or_selects_one():
    ordinary = bind_sharadar_companion(report(), supplement()).to_payload()
    assert candidate(ordinary, "stocks")["exact_date_reference_candidates"] == []
    docs = documents()
    docs["rows-stocks"]["data"][0]["date"] = "2023-02-28"
    ambiguous = bind_sharadar_companion(report(docs), supplement(conflicting_reference=True)).to_payload()
    row = candidate(ambiguous, "stocks")
    assert len(row["exact_date_reference_candidates"]) == 2
    assert "ambiguous_exact_date_reference_candidates" in row["refusal_reasons"]
    assert row["historical_ticker_permaticker_link"] is None


def test_date_only_payment_supplement_is_retained_without_cash_settlement_inference():
    extra = supplement(dividend=True)
    payload = bind_sharadar_companion(report(), extra).to_payload()
    dividends = next(row for row in payload["supplement_tables"] if row["table"] == "dividends")
    payment = dividends["rows"][0]["normalized"]
    assert payment["pay_date"] == "2023-03-15"
    assert payment["payment_timestamp"] is None
    assert payment["payment_cash_settlement_verified"] is False
    assert payment["terminal_economics_admitted"] is False
    assert payload["authority"]["outcome_access_authorized"] is False


@pytest.mark.parametrize("value", [{"verified": True}, [], True, object()])
def test_untyped_supplements_and_verified_flags_cannot_admit_sources(value):
    with pytest.raises(SharadarActualInputBindingError, match="exact_Massive"):
        bind_sharadar_companion(report(), value)


def test_supplement_replacement_and_nested_capture_mutation_are_revalidated():
    binding = bind_sharadar_companion(report(), supplement())
    object.__setattr__(binding, "supplement", None)
    with pytest.raises(SharadarActualInputBindingError, match="source_identity_changed"):
        binding.to_payload()
    binding = bind_sharadar_companion(report(), supplement())
    object.__setattr__(binding.supplement.captures[0], "raw", b'{"status":"OK","results":[],"count":0}')
    with pytest.raises(ValueError, match="identity_changed"):
        binding.to_payload()


def test_supplement_outputs_are_detached_without_missing_cell_or_refusal_loss():
    extra = supplement()
    binding = bind_sharadar_companion(report(), extra)
    payload = binding.to_payload()
    payload["supplement_tables"][0]["requested_symbol_cells"].clear()
    payload["supplement_tables"].clear()
    assert binding.to_payload()["supplement_tables"] == extra.to_payload()["tables"]
