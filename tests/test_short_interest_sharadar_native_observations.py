"""Fabricated rewritten-key/rational joins, never actual study observations."""
from __future__ import annotations

import copy
from decimal import localcontext

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.latest_revised_source import LatestRevisedBundle
from research.short_interest_etf.sharadar_native_master_index import build_sharadar_native_master_index
from research.short_interest_etf.sharadar_native_observations import (
    PROTOCOL_SHA256, SCHEMA, SharadarNativeObservationError, SharadarNativeObservations,
    bind_sharadar_native_observations, observation_protocol,
)
from test_short_interest_sharadar_companion_qualification import documents, report
from test_short_interest_sharadar_securities_master import (
    documents as master_documents, report as master_report, ticker,
)


def native_index(*, include_fund=True, stock_role="Primary Class", master_docs=None):
    docs = master_documents() if master_docs is None else master_docs
    if master_docs is None:
        docs["tickers"] = [ticker("AAPL", "12345", category="Domestic Common Stock " + stock_role)]
        if include_fund:
            docs["tickers"].append(ticker("AAPL", "12345", table="fundamentals",
                                         category="Domestic Common Stock"))
    return build_sharadar_native_master_index(master_report(docs))


def binding(docs=None, **kwargs):
    return bind_sharadar_native_observations(report(docs), native_index(**kwargs))


def observation(payload, table):
    return next(row for row in payload["observations"] if row["table"] == table)


def test_pinned_detached_protocol_and_distinct_v3_consumer():
    protocol = observation_protocol()
    assert hash_payload(protocol) == PROTOCOL_SHA256
    protocol["tables"]["fundamentals"] = "stocks"
    protocol["authority"]["source_admitted"] = True
    assert hash_payload(observation_protocol()) == PROTOCOL_SHA256
    obj = binding()
    assert type(obj) is SharadarNativeObservations
    assert not isinstance(obj, LatestRevisedBundle)
    assert obj.to_payload()["schema"] == SCHEMA


def test_native_namespace_positive_join_is_only_provider_rewritten_key():
    payload = binding().to_payload()
    for table in ("stocks", "daily", "fundamentals"):
        row = observation(payload, table)
        assert row["status"] == "bound_rewritten_provider_observation"
        assert row["provider_security_id"] == "sharadar:permaticker:12345"
        assert row["provider_dataset_key_bound"] is True
        assert row["same_share_class_denominator"] is None
        assert row["historical_effective_intervals"] == []
        assert "raw_market_alias" in row["lookup_semantic"]
    assert "FIGI" not in canonical_json([row["provider_security_id"] for row in payload["observations"]])


def test_rational_raw_prices_and_volume_preserved_in_low_decimal_precision():
    source = report()
    with localcontext() as context:
        context.prec = 2
        payload = bind_sharadar_native_observations(source, native_index()).to_payload()
    stock = observation(payload, "stocks")["source_observation"]["normalized"]
    assert stock["raw_open"] == {"numerator": 20, "denominator": 3}
    assert stock["raw_volume"] == {"numerator": 21, "denominator": 2}
    assert payload["source_tables"] == source.to_payload()["tables"]


def test_primary_membership_does_not_turn_entity_shares_into_a_class_denominator():
    row = observation(binding().to_payload(), "fundamentals")
    assert row["provider_dataset_key_bound"] is True
    assert row["source_observation"]["normalized"]["sharesbas"] == {"numerator": 100000, "denominator": 1}
    assert row["same_share_class_denominator"] is None
    assert row["native_resolution"]["authority"]["denominator_admitted"] is False


@pytest.mark.parametrize("role", ["Secondary Class", ""])
def test_fundamentals_never_transfer_to_secondary_or_unstated_class(role):
    row = observation(binding(stock_role=role).to_payload(), "fundamentals")
    assert row["provider_dataset_key_bound"] is False
    assert row["provider_security_id"] is None


def test_missing_fundamental_membership_is_not_joined_by_ticker_alone():
    payload = binding(include_fund=False).to_payload()
    assert observation(payload, "stocks")["provider_dataset_key_bound"] is True
    assert observation(payload, "fundamentals")["provider_dataset_key_bound"] is False


@pytest.mark.parametrize("invalid", [False, True])
def test_prior_current_master_conflicts_and_identifiable_refused_peers_block_binding(invalid):
    docs = documents()
    peer = copy.deepcopy(docs["rows-tickers"]["data"][0])
    peer["permaticker"] = 67890
    if invalid:
        peer["isdelisted"] = "UNKNOWN"
    docs["rows-tickers"]["data"].append(peer)
    docs["rows-tickers"]["count"] = 2
    row = observation(binding(docs).to_payload(), "stocks")
    assert row["provider_dataset_key_bound"] is False
    assert row["provider_security_id"] is None
    assert row["refusal_reasons"]


def test_new_master_conflict_refuses_native_binding_without_selecting_a_current_winner():
    docs = master_documents()
    docs["tickers"] = [ticker("AAPL", "12345"), ticker("AAPL", "99999")]
    row = observation(binding(master_docs=docs).to_payload(), "stocks")
    assert not row["provider_dataset_key_bound"]
    assert "ambiguous_provider_dataset_key" in row["refusal_reasons"]


def test_source_rewritten_stock_key_cannot_resolve_a_raw_symbol_or_provider_case_alias():
    docs = documents()
    docs["rows-stocks"]["data"][0]["ticker"] = "FB"
    row = observation(binding(docs).to_payload(), "stocks")
    assert row["provider_dataset_key_bound"] is False
    assert row["provider_security_id"] is None


@pytest.mark.parametrize("kind", ["stocks", "daily", "fundamentals", "actions", "tickers"])
def test_all_refusals_missing_requested_cells_and_source_origins_are_retained(kind):
    docs = documents()
    docs["rows-" + kind] = {"count": 0, "data": []}
    source = report(docs)
    result = bind_sharadar_native_observations(source, native_index()).to_payload()
    assert result["source_tables"] == source.to_payload()["tables"]
    assert "not_full_study" in result["population_scope"]


def test_duplicate_source_financial_rows_are_not_resurrected_by_current_master():
    docs = documents()
    original = docs["rows-stocks"]["data"][0]
    docs["rows-stocks"] = {"count": 2, "data": [original, copy.deepcopy(original)]}
    result = binding(docs).to_payload()
    assert not any(row["table"] == "stocks" for row in result["observations"])
    assert len(next(t for t in result["source_tables"] if t["table"] == "stocks")["refusals"]) == 2


def test_missing_prior_native_assertion_cannot_bind_older_rewritten_keys_through_new_master():
    docs = documents()
    docs["rows-tickers"] = {"count": 0, "data": []}
    payload = binding(docs).to_payload()
    for kind in ("stocks", "daily", "fundamentals"):
        row = observation(payload, kind)
        assert row["provider_dataset_key_bound"] is False
        assert row["provider_security_id"] is None
        assert "unique_prior_native_identity_assertion_required" in row["refusal_reasons"]


def test_actions_do_not_invent_rename_payment_timestamp_or_terminal_zero():
    row = observation(binding().to_payload(), "actions")
    assert row["provider_security_id"] is None
    assert row["native_resolution"] is None
    assert row["source_observation"]["normalized"]["payment_timestamp"] is None
    assert "date_only_action_semantics_not_admitted" in row["refusal_reasons"]


def test_sealed_payload_and_source_digests_are_exact_and_outputs_detach():
    source, index = report(), native_index()
    obj = bind_sharadar_native_observations(source, index)
    payload = obj.to_payload()
    assert payload["native_index_sha256"] == index.sha256
    assert payload["source_report_sha256"] == source.sha256
    digest = payload.pop("binding_sha256")
    assert digest == hash_payload(payload) == obj.sha256
    payload["authority"]["source_admitted"] = True
    payload["observations"].clear()
    assert obj.to_payload()["observations"]
    assert obj.to_payload()["authority"]["source_admitted"] is False


@pytest.mark.parametrize("attribute", ["_source_sha256", "_index_sha256", "_payload_json"])
def test_object_setattr_cannot_forge_cache_or_source_binding(attribute):
    obj = binding()
    object.__setattr__(obj, attribute, "f" * 64)
    with pytest.raises(SharadarNativeObservationError):
        obj.to_payload()


def test_source_capture_mutation_is_revalidated_not_trusted_from_old_digest():
    obj = binding()
    object.__setattr__(obj.qualification.captures[-1], "raw", b"{}")
    with pytest.raises(ValueError):
        obj.to_payload()


@pytest.mark.parametrize("value", [None, True, {}, [], object()])
def test_untyped_sources_or_owner_verified_flags_are_not_qualification(value):
    with pytest.raises(SharadarNativeObservationError, match="exact_companion"):
        bind_sharadar_native_observations(value, native_index())
    with pytest.raises(SharadarNativeObservationError, match="exact_native_index"):
        bind_sharadar_native_observations(report(), value)


def test_every_scope_gate_stays_closed_even_after_positive_native_key_binding():
    obj = binding()
    for key, value in obj.to_payload()["authority"].items():
        if key == "source_only":
            assert value is True
        elif key in {"actual_outcome_looks", "allocated_alpha", "qc_attempts"}:
            assert type(value) is int and value == 0
        else:
            assert value is False
