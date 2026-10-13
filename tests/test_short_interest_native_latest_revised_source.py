"""Fabricated native/rational assembly, never actual market or look evidence."""
from __future__ import annotations

import base64
from decimal import localcontext

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_latest_revised_source as source
from research.short_interest_etf.latest_revised_protocol import PROTOCOL_SHA256 as ECONOMIC_SHA
from research.short_interest_etf.latest_revised_source import LatestRevisedBundle
from research.short_interest_etf.sharadar_class_reference import qualify_sharadar_class_reference
from research.short_interest_etf.sharadar_native_master_index import build_sharadar_native_master_index
from research.short_interest_etf.sharadar_native_observations import bind_sharadar_native_observations
from test_short_interest_class_reference import class_source, source_row, LATER
from test_short_interest_sharadar_companion_qualification import report as companion_report
from test_short_interest_sharadar_securities_master import documents, report as master_report, ticker

DATES = ("2022-10-14", "2023-02-28", "2023-05-15")


def inputs(changes=None, extra=None):
    docs = documents()
    docs["tickers"] = [ticker("AAPL"), ticker("AAPL", table="fundamentals"),
                       ticker("GONE", "12346", delisted="Y")]
    docs["tickers"][2]["figi"] = "BBG000000003"
    if extra:
        docs["tickers"].extend(extra)
    qualification = master_report(docs)
    native = bind_sharadar_native_observations(companion_report(), build_sharadar_native_master_index(qualification))
    classes = qualify_sharadar_class_reference(qualification.captures[0], class_source(changes), retrieved_at=LATER)
    plan = source.freeze_native_assembly_plan(settlement_dates=DATES,
                                              native_observations=native, class_reference=classes)
    return plan, native, classes


def si_row(at=DATES[0], ticker="AAPL", quantity=12):
    return {"ticker": ticker, "settlement_date": at, "short_interest": quantity}


def page(plan, rows=None, *, url=None, next_url=None, raw=None, status=200):
    url = source.native_si_request(plan)["url"] if url is None else url
    if raw is None:
        raw = canonical_json({"status": "OK", "results": rows or [], "next_url": next_url}).encode()
    return source.CapturedNativeShortInterestPage(url, hash_payload({"method": "GET", "url": url,
                                                                    "authentication": "Bearer_header_not_recorded"}),
                                                 raw, hash_bytes(raw), LATER, status)


def assemble(rows=None, **kwargs):
    plan, native, classes = inputs(**kwargs)
    rows = [si_row(at) for at in DATES] if rows is None else rows
    return source.assemble_native_latest_revised_source(plan, native, classes, (page(plan, rows),))


def bindings(result):
    return result.to_payload()["native_SI_source_bindings"]


def test_actual_native_version_not_fixture_and_all_execution_authority_closed():
    obj = assemble()
    payload = obj.to_payload()
    assert type(obj) is source.NativeLatestRevisedSource
    assert not isinstance(obj, LatestRevisedBundle)
    assert payload["economic_protocol_sha256"] == ECONOMIC_SHA
    assert payload["signals_computed"] is payload["price_signal_or_outcome_join_performed"] is False
    assert payload["authority"]["actual_outcome_looks"] == 0
    assert payload["authority"]["source_admitted"] is False
    assert payload["authority"]["actual_input_execution_admitted"] is False
    assert payload["authority"]["qc_authorized"] is False
    with pytest.raises(source.NativeLatestRevisedSourceError, match="not_actual_execution_admission"):
        obj.execution_inputs()


def test_exact_native_and_rational_prices_volume_without_context_rounding():
    with localcontext() as ctx:
        ctx.prec = 2
        result = assemble().to_payload()
    bar = result["native_rational_bar_candidates"][0]
    assert bar["provider_security_id"] == "sharadar:permaticker:12345"
    assert bar["raw_open"] == {"numerator": 20, "denominator": 3}
    assert bar["raw_volume"] == {"numerator": 21, "denominator": 2}
    assert bar["origin"]["source_file_sha256"]
    assert result["original_native_observations"]
    assert result["original_native_source_tables"]


def test_same_date_class_count_and_immediate_prior_origins_no_S1_or_share_transfer():
    rows = bindings(assemble())
    assert rows[0]["prior_settlement_date"] is None
    assert "first_schedule_row_no_prior_settlement" in rows[0]["refusal_reasons"]
    assert rows[1]["status"] == "source_binding_candidate"
    assert rows[1]["provider_security_id"] == "sharadar:permaticker:12345"
    assert rows[1]["share_class_figi"] == "BBG000000002"
    assert rows[1]["same_class_count_evidence"]["source_field"] == "share_class_shares_outstanding"
    assert rows[1]["same_class_count_evidence"]["numerator"] == 123
    assert rows[1]["same_class_count_evidence"]["query_date"] == DATES[1]
    assert rows[1]["prior_source_origins"] == [rows[0]["SI_origin"]]
    assert "S1" not in canonical_json(rows)
    assert "sharesbas" not in canonical_json(rows)


def test_missing_immediate_prior_never_leapfrogs_to_earlier_settlement():
    result = assemble([si_row(DATES[0]), si_row(DATES[2])])
    row = bindings(result)[1]
    assert row["prior_settlement_date"] == DATES[1]
    assert row["prior_source_origins"] == []
    assert "immediate_prior_same_native_class_count_evidence_missing_or_ambiguous" in row["refusal_reasons"]
    assert result.to_payload()["coverage"]["SI_missing_scheduled_settlements"] == [DATES[1]]


def test_full_captured_master_inventory_retains_delisted_and_refused_not_sentinel_population():
    peer = ticker("BAD", "00012347")
    result = assemble(extra=[peer]).to_payload()
    assert len(result["native_master_rows"]) == 4
    assert any(row["isdelisted_assertion"] is True for row in result["native_master_rows"])
    assert any(row["source_refusal_reason"] for row in result["native_master_rows"])
    assert "not_full_US_market_or_study_coverage" in result["population_scope"]
    assert "not_full_study" in result["coverage"]["native_observation_population_scope"]


@pytest.mark.parametrize("mutation", ["duplicate", "bad_quantity", "whitespace_ticker"])
def test_identifiable_bad_SI_peer_quarantines_good_copy(mutation):
    bad = si_row()
    if mutation == "bad_quantity":
        bad["short_interest"] = True
    elif mutation == "whitespace_ticker":
        bad["ticker"] = " AAPL "
    result = assemble([si_row(), bad]).to_payload()
    assert len(result["SI_rows"]) == 2
    assert all(row["normalized"] is None for row in result["SI_rows"])
    assert all("duplicate_raw_ticker_settlement_all_copies_quarantined" in row["refusal_reasons"]
               for row in result["SI_rows"])


def test_native_collision_across_two_raw_market_tokens_does_not_select_alias():
    import research.short_interest_etf.massive_class_denominator as classes
    changes = {rid: source_row("BRK.A") for rid in classes.REQUEST_IDS if "BRK.A" in rid}
    result = assemble([si_row(DATES[1]), si_row(DATES[1], "BRK.A")], changes=changes)
    assert all("duplicate_native_settlement_all_copies_quarantined" in row["refusal_reasons"] for row in bindings(result))
    assert all(row["status"] == "source_binding_refused" for row in bindings(result))


@pytest.mark.parametrize("row", [si_row(quantity=True), si_row(quantity=1.5),
                                 {**si_row(), "short_volume": 100}, si_row(ticker=" AAPL "),
                                 si_row("2020-02-01"), {"ticker": "AAPL"}])
def test_malformed_or_wrong_semantic_rows_retained_without_positive_join(row):
    result = assemble([row]).to_payload()
    assert result["SI_rows"][0]["raw_record"]
    assert result["SI_rows"][0]["normalized"] is None
    assert bindings(assemble([row]))[0]["provider_security_id"] is None


@pytest.mark.parametrize("raw", [b'{"status":"OK","status":"OK","results":[]}',
                                  b'{"status":"OK","results":[NaN]}', b"\xff", b"PRIVATE-BODY"])
def test_refused_raw_body_retained_exactly_and_error_never_discloses_it(raw):
    plan, native, classes = inputs()
    result = source.assemble_native_latest_revised_source(plan, native, classes, (page(plan, raw=raw),)).to_payload()
    receipt = result["SI_pages"][0]
    assert base64.b64decode(receipt["raw_body_base64"]) == raw
    assert receipt["status"] == "refused"
    assert result["coverage"]["SI_page_chain_complete"] is False
    assert "PRIVATE-BODY" not in receipt["refusal_reason"]


def test_complete_page_chain_bound_exactly_and_incomplete_next_url_is_not_followed():
    plan, native, classes = inputs()
    cursor = "https://api.massive.com/stocks/v1/short-interest?cursor=fabricated"
    first = page(plan, [si_row()], next_url=cursor)
    incomplete = source.assemble_native_latest_revised_source(plan, native, classes, (first,)).to_payload()
    assert incomplete["coverage"]["page_refusals"] == ["short_interest_page_chain_incomplete"]
    second = page(plan, [si_row(DATES[1])], url=cursor)
    complete = source.assemble_native_latest_revised_source(plan, native, classes, (first, second)).to_payload()
    assert complete["coverage"]["SI_page_chain_complete"] is True
    assert len(complete["SI_rows"]) == 2
    with pytest.raises(source.NativeLatestRevisedSourceError, match="page_chain"):
        source.assemble_native_latest_revised_source(plan, native, classes, (second,))


@pytest.mark.parametrize("url", ["https://evil.example/stocks/v1/short-interest", "http://api.massive.com/stocks/v1/short-interest",
                                  "https://api.massive.com/stocks/v1/short-interest?apiKey=PRIVATE",
                                  "https://api.massive.com/stocks/v1/short-interest?ticker=AAPL",
                                  "https://u:p@api.massive.com/stocks/v1/short-interest",
                                  "https://api.massive.com/stocks/v1/short-interest?cursor=a&cursor=b"])
def test_foreign_or_secret_or_survivor_population_routes_refused_without_echo(url):
    plan, _, _ = inputs()
    with pytest.raises(source.NativeLatestRevisedSourceError) as exc:
        page(plan, url=url)
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.parametrize("dates", [[], (), (DATES[0],), (DATES[1], DATES[0]), (DATES[0], DATES[0]),
                                    (DATES[0], "2023-2-28")])
def test_frozen_schedule_requires_prior_and_exact_order(dates):
    _, native, classes = inputs()
    with pytest.raises(source.NativeLatestRevisedSourceError):
        source.freeze_native_assembly_plan(settlement_dates=dates, native_observations=native, class_reference=classes)


def test_no_arbitrary_dict_or_admission_flag_and_no_unanchored_constructor():
    plan, native, classes = inputs()
    with pytest.raises(source.NativeLatestRevisedSourceError, match="exact_sealed"):
        source.freeze_native_assembly_plan(settlement_dates=DATES, native_observations={"rights_verified": True},
                                          class_reference=classes)
    for constructor in (source.NativeLatestRevisedSource, source.NativeAssemblyPlan):
        with pytest.raises(source.NativeLatestRevisedSourceError, match="factory"):
            constructor()
    with pytest.raises(TypeError):
        source.assemble_native_latest_revised_source(plan, native, classes, (), source_admitted=True)


def test_source_master_pin_change_cannot_cross_native_and_class_archives():
    _, native, _ = inputs()
    qualification = master_report(documents())
    classes = qualify_sharadar_class_reference(qualification.captures[0], class_source(), retrieved_at=LATER)
    with pytest.raises(source.NativeLatestRevisedSourceError, match="archive_mismatch"):
        source.freeze_native_assembly_plan(settlement_dates=DATES, native_observations=native, class_reference=classes)


def test_detached_payload_and_immutable_plan_body_capture_source_seals():
    obj = assemble()
    digest = obj.sha256
    detached = obj.to_payload()
    detached["authority"]["actual_input_execution_admitted"] = True
    assert obj.sha256 == digest
    assert obj.to_payload()["authority"]["actual_input_execution_admitted"] is False
    object.__setattr__(obj, "_bytes", b"{}")
    with pytest.raises(source.NativeLatestRevisedSourceError, match="sealed_native_source"):
        obj.to_payload()


@pytest.mark.parametrize("field", ["raw", "request_sha256", "source_file_sha256", "received_at", "http_status"])
def test_capture_mutation_rechecked_on_every_source_access(field):
    obj = assemble()
    capture = obj._pages[0]
    replacements = {"raw": b"{}", "request_sha256": "0"*64, "source_file_sha256": "0"*64,
                    "received_at": "invalid", "http_status": True}
    object.__setattr__(capture, field, replacements[field])
    with pytest.raises(source.NativeLatestRevisedSourceError):
        obj.to_bytes()


def test_class_source_missing_count_does_not_use_sharadar_entity_shares():
    import research.short_interest_etf.massive_class_denominator as classes
    changes = {rid: source_row(shares=None) for rid in classes.REQUEST_IDS if "AAPL" in rid}
    result = assemble(changes=changes)
    assert all(row["same_class_count_evidence"] is None for row in bindings(result))
    assert all(row["status"] == "source_binding_refused" for row in bindings(result))


def test_full_range_and_pending_calendar_retain_all_observed_dates_without_leapfrog():
    _, native, classes = inputs()
    plan = source.freeze_native_assembly_plan(settlement_dates=(), requested_range=("2022-01-01", "2026-08-31"),
                                              native_observations=native, class_reference=classes)
    rows = [si_row("2023-02-01"), si_row("2025-12-31")]
    result = source.assemble_native_latest_revised_source(plan, native, classes, (page(plan, rows),)).to_payload()
    assert result["observed_settlement_dates"] == ["2023-02-01", "2025-12-31"]
    assert all(row["normalized"] is not None for row in result["SI_rows"])
    assert result["coverage"]["calendar_qualification_pending"] is True
    assert all(row["prior_settlement_date"] is None for row in result["native_SI_source_bindings"])
    assert all("observed_settlement_calendar_relation_not_qualified" in row["refusal_reasons"]
               for row in result["native_SI_source_bindings"])
    request = plan.to_payload()["short_interest_request"]
    assert request["params"]["limit"] == 50000
    assert request["params"]["sort"] == "settlement_date.asc,ticker.asc"
    assert plan.to_payload()["maximum_pages"] == 32


def test_next_cursor_cycle_and_changed_request_scope_not_admitted():
    plan, native, classes = inputs()
    cursor = "https://api.massive.com/stocks/v1/short-interest?cursor=fabricated"
    first = page(plan, [], next_url=cursor)
    loop = page(plan, [], url=cursor, next_url=cursor)
    with pytest.raises(source.NativeLatestRevisedSourceError, match="page_chain"):
        source.assemble_native_latest_revised_source(plan, native, classes, (first, loop, loop))
    altered = cursor + "&settlement_date.gte=2000-01-01"
    result = source.assemble_native_latest_revised_source(plan, native, classes,
                                                         (page(plan, [], next_url=altered),)).to_payload()
    assert result["coverage"]["SI_page_chain_complete"] is False
    assert result["SI_pages"][0]["refusal_reason"] == "next_page_changed_frozen_population_or_sort"


def test_source_budget_never_accepts_an_extra_page():
    plan, native, classes = inputs()
    with pytest.raises(source.NativeLatestRevisedSourceError, match="page_budget"):
        source.assemble_native_latest_revised_source(plan, native, classes, (page(plan),) * 33)
