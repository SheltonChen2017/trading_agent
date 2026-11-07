"""Fabricated metadata-index contracts, not source fitness or performance."""
from __future__ import annotations

import copy

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.sharadar_native_master_index import (
    INTERFACE_SCHEMA,
    PROTOCOL_SHA256,
    SCHEMA,
    SharadarNativeMasterIndex,
    SharadarNativeMasterIndexError,
    build_sharadar_native_master_index,
    index_protocol,
    resolve_rewritten_provider_key,
)
from research.short_interest_etf.sharadar_securities_master import (
    SharadarSecuritiesMasterQualification,
)
from test_short_interest_sharadar_securities_master import documents, report, ticker


def master_index(docs=None):
    return build_sharadar_native_master_index(report(docs))


def with_fundamentals(*, token="FAKE", permaticker="12345", role="Primary Class", table="fundamentals"):
    docs = documents()
    category = "Domestic Common Stock" + (" " + role if role else "")
    docs["tickers"].append(ticker(token, permaticker, category=category, table=table))
    return docs


def test_prospective_protocol_is_pinned_and_detached():
    payload = index_protocol()
    assert hash_payload(payload) == PROTOCOL_SHA256
    assert payload["interface_schema"] == INTERFACE_SCHEMA
    assert "raw_market_alias" in payload["key_semantic"]
    assert payload["rewiring_documentation"] == "https://sharadar.com/docs/faqs"
    assert payload["public_source_semantic_evidence_id"] == "SI-SOURCE-20261012-REWRITTEN-DATASET-KEY-01"
    assert "public_document_sha256" not in payload
    payload["provider_table_groups"]["SF1"] = "stocks"
    payload["authority"]["source_admitted"] = True
    assert hash_payload(index_protocol()) == PROTOCOL_SHA256


def test_small_private_index_retains_every_original_master_row_origin():
    source = report()
    index = build_sharadar_native_master_index(source)
    payload = index.to_payload()
    original = source.to_payload()
    assert payload["schema"] == SCHEMA
    assert payload["interface_schema"] == INTERFACE_SCHEMA
    assert payload["source_report_sha256"] == original["report_sha256"]
    assert payload["source_capture_identity_sha256"] == original["capture_identity_sha256"]
    assert len(payload["rows"]) == len(original["tables"][0]["rows"])
    assert [row["origin"] for row in payload["rows"]] == [
        row["origin"] for row in original["tables"][0]["rows"]
    ]
    assert not any("raw_cells" in row or "current_exchange" in row or "sicsector" in row
                   for row in payload["rows"])
    assert payload["publication_scope"] == "private_only_not_data_usability_publication"
    assert payload["rows"][-1]["index_disposition"] == "outside_dataset_groups"
    digest = payload.pop("index_sha256")
    assert digest == hash_payload(payload) == index.sha256


def test_source_rewritten_dataset_key_resolves_native_ID_without_raw_alias_or_FIGI():
    index = master_index()
    row = resolve_rewritten_provider_key(index, "FAKE")
    assert row["status"] == "bound_provider_dataset_key"
    assert row["provider_dataset_key_bound"] is True
    assert row["provider_security_id"] == "sharadar:permaticker:12345"
    assert row["current_class_role_assertion"] == "Primary Class"
    assert row["same_share_class_denominator"] is None
    assert row["historical_effective_intervals"] == []
    assert row["authority"]["historical_raw_ticker_alias_admitted"] is False
    assert row["authority"]["point_in_time_data"] is False
    assert "share_class_figi" not in row
    assert row == index.resolve_rewritten_provider_key("FAKE", "stocks")
    assert row["resolution_sha256"] == hash_payload({key: value for key, value in row.items()
                                                   if key != "resolution_sha256"})


def test_delisted_secondary_and_excluded_categories_are_retained_without_survivor_selection():
    index = master_index()
    gone = index.resolve_rewritten_provider_key("GONE")
    secondary = index.resolve_rewritten_provider_key("FAKE.B")
    excluded = index.resolve_rewritten_provider_key("FUND")
    assert gone["provider_dataset_key_bound"] and gone["current_isdelisted_assertion"] is True
    assert secondary["provider_dataset_key_bound"] and secondary["current_class_role_assertion"] == "Secondary Class"
    assert excluded["provider_dataset_key_bound"] and excluded["current_common_stock_candidate"] is False
    assert index.resolve_rewritten_provider_key("OTHER")["provider_dataset_key_bound"] is False


@pytest.mark.parametrize("table", ["stocks", "SEP"])
def test_current_provider_STOCKS_table_aliases_do_not_create_historical_market_aliases(table):
    docs = documents()
    docs["tickers"][0]["table"] = table
    row = master_index(docs).resolve_rewritten_provider_key("FAKE")
    assert row["provider_security_id"] == "sharadar:permaticker:12345"
    assert row["historical_effective_intervals"] == []


@pytest.mark.parametrize("competing_table", ["stocks", "SEP"])
@pytest.mark.parametrize("malformed", [False, True])
def test_same_ticker_native_reuse_includes_malformed_and_cross_alias_table_competitors(competing_table, malformed):
    docs = documents()
    peer = ticker("FAKE", "67890", table=competing_table)
    if malformed:
        peer["isdelisted"] = "UNKNOWN"
    docs["tickers"].append(peer)
    index = master_index(docs)
    row = index.resolve_rewritten_provider_key("FAKE")
    assert row["provider_security_id"] is None
    assert "ambiguous_provider_dataset_key" in row["refusal_reasons"]
    assert len(row["source_row_origins"]) == 2
    assert len(index.to_payload()["rows"]) == len(docs["tickers"])


@pytest.mark.parametrize("malformed", [False, True])
def test_native_permaticker_has_unique_dataset_ticker_axis_even_when_competitor_refused(malformed):
    docs = documents()
    peer = ticker("OTHERFAKE", "12345")
    if malformed:
        peer["category"] = " invalid "
    docs["tickers"].append(peer)
    row = master_index(docs).resolve_rewritten_provider_key("FAKE")
    assert row["provider_dataset_key_bound"] is False
    assert "ambiguous_native_identifier_or_dataset_key" in row["refusal_reasons"]
    assert len(row["source_row_origins"]) == 2


@pytest.mark.parametrize("changes", [
    {"ticker": "FAKE " , "permaticker": "67890"},
    {"ticker": "OTHERFAKE", "permaticker": "0012345"},
    {"ticker": "FAKE", "permaticker": "12345", "table": " stocks "},
])
def test_noncanonical_identifiable_peers_only_weaken_uniqueness_never_become_aliases(changes):
    docs = documents()
    peer = ticker()
    peer.update(changes)
    docs["tickers"].append(peer)
    row = master_index(docs).resolve_rewritten_provider_key("FAKE")
    assert row["provider_security_id"] is None
    assert row["provider_dataset_key_bound"] is False


def test_exact_duplicate_master_rows_are_all_quarantined_not_collapsed():
    docs = documents()
    docs["tickers"].append(copy.deepcopy(docs["tickers"][0]))
    index = master_index(docs)
    row = index.resolve_rewritten_provider_key("FAKE")
    assert row["provider_dataset_key_bound"] is False
    retained = [item for item in index.to_payload()["rows"] if item["collision_ticker_token"] == "FAKE"]
    assert len(retained) == 2
    assert all(item["index_disposition"] == "refused_master_row" for item in retained)


@pytest.mark.parametrize("table", ["fundamentals", "SF1"])
@pytest.mark.parametrize("role", ["Primary Class", None])
def test_SF1_membership_requires_same_native_ID_and_explicit_STOCKS_primary_class(table, role):
    index = master_index(with_fundamentals(table=table, role=role))
    row = index.resolve_rewritten_provider_key("FAKE", "fundamentals")
    assert row["provider_dataset_key_bound"] is True
    assert row["provider_security_id"] == "sharadar:permaticker:12345"
    assert row["same_share_class_denominator"] is None
    assert row["authority"]["denominator_admitted"] is False
    assert len(row["source_row_origins"]) == 2


def test_SF1_provider_key_can_differ_between_datasets_but_does_not_become_a_market_alias():
    index = master_index(with_fundamentals(token="SF1KEY"))
    fund = index.resolve_rewritten_provider_key("SF1KEY", "fundamentals")
    assert fund["provider_dataset_key_bound"] is True
    assert fund["current_STOCKS_key_assertion"] == "FAKE"
    assert index.resolve_rewritten_provider_key("SF1KEY", "stocks")["provider_dataset_key_bound"] is False
    assert fund["authority"]["historical_raw_ticker_alias_admitted"] is False


@pytest.mark.parametrize("changes", [
    {"permaticker": "99999"}, {"category": "Domestic Common Stock Secondary Class"},
    {"category": "Canadian Common Stock Primary Class"}, {"category": "Domestic ETF"},
    {"isdelisted": "UNKNOWN"},
])
def test_fundamental_rows_cannot_join_by_issuer_or_composite_FIGI_or_incompatible_class(changes):
    docs = with_fundamentals()
    docs["tickers"][-1].update(changes)
    row = master_index(docs).resolve_rewritten_provider_key("FAKE", "fundamentals")
    assert row["provider_security_id"] is None
    assert row["provider_dataset_key_bound"] is False
    assert row["same_share_class_denominator"] is None


@pytest.mark.parametrize("category", ["Domestic Common Stock", "Domestic Common Stock Secondary Class", "Domestic ETF"])
def test_STOCKS_primary_class_role_cannot_be_manufactured_from_SF1_or_generic_category(category):
    docs = with_fundamentals()
    docs["tickers"][0]["category"] = category
    row = master_index(docs).resolve_rewritten_provider_key("FAKE", "fundamentals")
    assert row["provider_dataset_key_bound"] is False
    assert "primary_class_native_table_membership_not_established" in row["refusal_reasons"]


def test_fundamental_permaticker_axis_refuses_even_valid_primary_peer_with_different_key():
    docs = with_fundamentals()
    docs["tickers"].append(ticker("OTHERFUNDKEY", "12345", table="SF1", category="Domestic Common Stock Primary Class"))
    row = master_index(docs).resolve_rewritten_provider_key("FAKE", "fundamentals")
    assert row["provider_dataset_key_bound"] is False
    assert "ambiguous_native_identifier_or_dataset_key" in row["refusal_reasons"]


def test_unique_current_metadata_lookup_is_not_a_default_for_raw_symbols_or_case_aliases():
    index = master_index()
    assert index.resolve_rewritten_provider_key("fake")["provider_dataset_key_bound"] is False
    assert index.resolve_rewritten_provider_key("MISSING")["provider_dataset_key_bound"] is False
    assert index.resolve_rewritten_provider_key("FAKE-B")["provider_dataset_key_bound"] is False


@pytest.mark.parametrize("ticker_value", [None, True, 1, {}, "", " FAKE", "FAKE ", "FAKE\n", "X" * 129])
def test_selector_requires_exact_bounded_current_provider_key(ticker_value):
    with pytest.raises(SharadarNativeMasterIndexError, match="provider_key_required"):
        master_index().resolve_rewritten_provider_key(ticker_value)


@pytest.mark.parametrize("table_value", [None, True, "SF1", "SEP", "raw_FINRA", "prices", "STOCKS"])
def test_callers_cannot_claim_a_raw_market_route_or_change_provider_table_semantic(table_value):
    with pytest.raises(SharadarNativeMasterIndexError, match="dataset_table_required"):
        master_index().resolve_rewritten_provider_key("FAKE", table_value)


def test_batched_lookup_validates_master_once_never_reparses_per_security(monkeypatch):
    source = report()
    calls = []
    original = SharadarSecuritiesMasterQualification.to_payload

    def counted(self):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(SharadarSecuritiesMasterQualification, "to_payload", counted)
    index = build_sharadar_native_master_index(source)
    for _ in range(100):
        assert index.resolve_rewritten_provider_key("FAKE")["provider_dataset_key_bound"] is True
        assert index.resolve_rewritten_provider_key("GONE")["provider_dataset_key_bound"] is True
    assert len(calls) == 1
    index.to_payload()
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["raw", "retrieved_at", "capture_identity", "cached_payload", "captures", "request_sha256"])
def test_source_identity_seal_detects_mutation_without_reparse(change):
    source = report()
    index = build_sharadar_native_master_index(source)
    if change == "raw":
        object.__setattr__(source.captures[0], "raw", b"changed fabricated archive")
    elif change == "request_sha256":
        object.__setattr__(source.captures[0], "request_sha256", "0" * 64)
    elif change == "retrieved_at":
        object.__setattr__(source, "retrieved_at", "2026-10-11T21:00:00Z")
    elif change == "capture_identity":
        object.__setattr__(source, "_capture_identity_sha256", "0" * 64)
    elif change == "cached_payload":
        object.__setattr__(source, "_payload_json", "{}")
    else:
        object.__setattr__(source, "captures", tuple(list(source.captures)))
    with pytest.raises(SharadarNativeMasterIndexError, match="master_source_changed"):
        index.resolve_rewritten_provider_key("FAKE")
    with pytest.raises(SharadarNativeMasterIndexError, match="master_source_changed"):
        index.to_payload()


def test_detached_outputs_and_readonly_axes_cannot_mutate_index_or_source():
    index = master_index()
    digest = index.sha256
    detached = index.to_payload()
    detached["rows"][0]["origin"]["archive_sha256"] = "0" * 64
    detached["authority"]["source_admitted"] = True
    resolved = index.resolve_rewritten_provider_key("FAKE")
    resolved["source_row_origins"].clear()
    with pytest.raises(TypeError):
        index._ticker_axes[("stocks", "FAKE")] = ()
    assert index.sha256 == digest
    assert index.to_payload()["authority"]["source_admitted"] is False
    assert index.resolve_rewritten_provider_key("FAKE")["source_row_origins"]


@pytest.mark.parametrize("field", ["retrieved_at", "_capture_identity_sha256", "table", "request_sha256"])
def test_source_seal_refuses_changed_equality_spoofing_string_subclasses(field):
    class SpoofedString(str):
        def __eq__(self, other):
            return True
        def __ne__(self, other):
            return False
    index = master_index()
    target = index.qualification if field.startswith(("retrieved", "_capture")) else index.qualification.captures[0]
    object.__setattr__(target, field, SpoofedString("changed fabricated source assertion"))
    with pytest.raises(SharadarNativeMasterIndexError, match="master_source_changed"):
        index.resolve_rewritten_provider_key("FAKE")


@pytest.mark.parametrize("attribute", ["_payload_json", "_ticker_axes", "_native_axes", "_source_seal", "_identity_seal", "_identity_seal_anchor"])
def test_index_internal_mutations_cannot_forge_a_rehashed_native_resolution(attribute):
    index = master_index()
    if attribute == "_payload_json":
        payload = index.to_payload()
        payload["authority"]["source_admitted"] = True
        payload["index_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "index_sha256"})
        replacement = canonical_json(payload)
    elif attribute == "_identity_seal":
        replacement = None
    else:
        replacement = {}
    object.__setattr__(index, attribute, replacement)
    with pytest.raises(SharadarNativeMasterIndexError, match="native_index_changed"):
        index.resolve_rewritten_provider_key("FAKE")


def test_same_shaped_identity_seal_cannot_forge_index_digest_while_key_stays_bound():
    index = master_index()
    original = index.to_payload()
    changed = index._identity_seal[:4] + ("f" * 64,)
    assert changed[:4] == index._identity_seal[:4]
    assert changed[4] != original["index_sha256"]
    object.__setattr__(index, "_identity_seal", changed)
    for operation in (lambda: index.sha256, index.to_payload,
                      lambda: index.resolve_rewritten_provider_key("FAKE")):
        with pytest.raises(SharadarNativeMasterIndexError, match="native_index_changed"):
            operation()


@pytest.mark.parametrize("source", [None, {}, [], True, object()])
def test_untyped_sources_or_verified_flags_are_refused(source):
    with pytest.raises(SharadarNativeMasterIndexError, match="exact_master"):
        build_sharadar_native_master_index(source)


def test_exact_type_subclasses_cannot_override_source_validation_or_key_resolution():
    class IndexSubclass(SharadarNativeMasterIndex):
        pass
    with pytest.raises(SharadarNativeMasterIndexError, match="exact_native_index"):
        IndexSubclass(report())
    forged = object.__new__(IndexSubclass)
    with pytest.raises(SharadarNativeMasterIndexError, match="exact_native_index"):
        resolve_rewritten_provider_key(forged, "FAKE")


def test_no_selector_can_open_admission_denominators_outcomes_or_QC():
    index = master_index(with_fundamentals())
    for row in (index.to_payload(), index.resolve_rewritten_provider_key("FAKE"),
                index.resolve_rewritten_provider_key("FAKE", "fundamentals")):
        for key, value in row["authority"].items():
            if key == "source_only":
                assert value is True
            elif key in {"actual_outcome_looks", "allocated_alpha", "qc_attempts"}:
                assert type(value) is int and value == 0
            else:
                assert value is False
