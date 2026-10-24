"""Fabricated generalized class anchors; no actual rows, source calls or looks."""
from __future__ import annotations

import copy
import json

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_class_reference as refs
import research.short_interest_etf.native_population_class_matrix as matrices
from test_short_interest_native_population_class_matrix import fixture, bind, row
from test_short_interest_sharadar_securities_master import archives, ticker

NOW, END = "2026-10-14T02:00:00Z", "2026-10-14T02:01:00Z"


def matrix(rows=None):
    report, pages = fixture({1: [row("FAKE", "2023-02-28"), row("FAKE", "2023-05-15")]
                                    if rows is None else rows})
    return matrices.freeze_native_population_class_matrix(bind(report), iter(pages))


def plan(*, mode="exact_cells", **kwargs):
    return refs.freeze_native_class_query_plan(matrix(), mode=mode, **kwargs)


def master(rows=None):
    return archives({"tickers": [ticker()] if rows is None else rows, "actions": [], "descriptions": []})[0]


def result(symbol="FAKE", **changes):
    value = {"ticker": symbol, "composite_figi": "BBG000000001", "share_class_figi": "BBG000000002",
             "share_class_shares_outstanding": 123, "type": "CS", "locale": "us", "market": "stocks",
             "primary_exchange": "XNYS"}
    value.update(changes)
    return value


def capture(query, value=None, *, raw=None, status=200, observed=True, media="application/json", at=NOW):
    if raw is None:
        raw = b"" if not observed else canonical_json({"status": "OK", "results": result() if value is None else value}).encode()
    return refs.capture_native_dated_class_response(query, raw=raw, raw_sha256=hash_bytes(raw),
        request_sha256=query.to_payload()["request_sha256"], received_at=at, http_status=status,
        content_type=media, body_observed=observed)


def qualify(values=None, *, selected=None, master_rows=None):
    selected = plan() if selected is None else selected
    tickets = list(selected.iter_queries())
    values = [result()] * len(tickets) if values is None else values
    captures = (capture(ticket, value) for ticket, value in zip(tickets, values))
    return refs.qualify_native_dated_class_reference(selected, master(master_rows), captures, retrieved_at=END)


def relations(value):
    return list(value.iter_relations())


def test_untyped_archive_is_refused_before_its_attributes_are_read():
    class UntrustedArchive:
        @property
        def raw(self):
            pytest.fail("untyped source attribute was read")
    with pytest.raises(refs.NativeDatedClassError, match="exact_original_TICKERS_archive_required"):
        refs.qualify_native_dated_class_reference(plan(), UntrustedArchive(), (), retrieved_at=END)


def test_exact_matrix_source_tickets_have_no_caller_symbol_or_actual_permission():
    selected = plan()
    tickets = [ticket.to_payload() for ticket in selected.iter_queries()]
    assert [(q["ticker"], q["query_asof_date"]) for q in tickets] == [("FAKE", "2023-02-28"), ("FAKE", "2023-05-15")]
    assert all(q["request_sha256"] == hash_payload(q["request"]) for q in tickets)
    assert selected.to_payload()["anchor_dates"] is None
    assert selected.to_payload()["authority"]["actual_outcome_looks"] == 0
    with pytest.raises(TypeError):
        refs.freeze_native_class_query_plan(matrix(), mode="exact_cells", ticker="WINNER")


def test_explicit_global_anchors_do_not_pick_frequency_or_require_exact_settlement():
    selected = plan(mode="explicit_anchors", anchor_dates=("2022-12-31", "2023-03-31"))
    facts = relations(qualify(selected=selected))
    assert [fact["query_asof_date"] for fact in facts] == ["2022-12-31", "2023-03-31"]
    assert all(fact["status"] == "dated_native_class_source_candidate" for fact in facts)
    assert all(fact["actual_observation_at"] == NOW and fact["historical_available_date"] is None for fact in facts)
    assert all(fact["historical_effective_intervals"] == [] for fact in facts)
    assert refs.reference_policy()["anchor_frequency_selected"] is None


def test_explicit_selected_source_cells_for_later_concrete_anchor_builder():
    selected = plan(mode="explicit_anchors", selected_query_ordinals=(2,))
    tickets = list(selected.iter_queries())
    assert len(tickets) == 1 and tickets[0].to_payload()["query_asof_date"] == "2023-05-15"
    assert selected.to_payload()["selected_query_ordinals"] == [2]
    assert selected.to_payload()["anchor_dates"] is None


@pytest.mark.parametrize("options", [{}, {"anchor_dates": []}, {"anchor_dates": ("2023-03-31", "2023-03-31")},
    {"anchor_dates": ("2026-09-01",)}, {"selected_query_ordinals": (True,)}, {"selected_query_ordinals": (3,)},
    {"selected_query_ordinals": (2, 1)}, {"selected_query_ordinals": (1,), "anchor_dates": ("2023-03-31",)}])
def test_no_implicit_anchor_frequency_arbitrary_cells_or_protected_period(options):
    with pytest.raises(refs.NativeDatedClassError):
        plan(mode="explicit_anchors", **options)


def test_exact_native_permaticker_and_particular_class_count_no_comp_cast_or_country_fabrication():
    facts = relations(qualify())
    assert all(f["provider_security_id"] == "sharadar:permaticker:12345" for f in facts)
    assert all(f["normalized"]["composite_figi"] == "BBG000000001" and f["normalized"]["share_class_figi"] == "BBG000000002" for f in facts)
    assert all(f["normalized"]["same_class_count"]["numerator"] == 123 for f in facts)
    assert all(f["normalized"]["same_class_count"]["source_field"] == "share_class_shares_outstanding" for f in facts)
    assert all(f["normalized"]["country_domicile_assertion"] is None for f in facts)
    assert all(f["authority"]["denominator_admitted"] is False and f["authority"]["qc_authorized"] is False for f in facts)


def test_dated_source_type_is_not_replaced_by_current_master_category():
    current = ticker(category="Domestic ETF")
    assert relations(qualify(master_rows=[current]))[0]["status"] == "dated_native_class_source_candidate"
    assert relations(qualify([result(type="ETF"), result(type="ETF")]))[0]["status"] == "source_reference_refused"


@pytest.mark.parametrize("changes", [{"share_class_shares_outstanding": None, "weighted_shares_outstanding": 123},
    {"share_class_shares_outstanding": True}, {"share_class_shares_outstanding": "123"},
    {"share_class_shares_outstanding": 1.5}, {"share_class_shares_outstanding": 0},
    {"share_class_figi": "BBG000000001"}, {"locale": "global"}, {"market": "crypto"}, {"type": None}])
def test_missing_invalid_wrong_class_or_issuer_counts_never_promoted(changes):
    facts = relations(qualify([result(**changes), result(**changes)]))
    assert all(f["status"] == "source_reference_refused" and f["provider_security_id"] is None for f in facts)


@pytest.mark.parametrize("mutation", ["native_zero", "native_trim", "composite_trim", "group_trim", "duplicate"])
def test_all_identifiable_malformed_master_collision_peers_quarantine_candidates(mutation):
    first, peer = ticker(), ticker("OTHER", "12346")
    if mutation == "native_zero":
        peer.update(permaticker="0012345", figi="BBG000000003")
    elif mutation == "native_trim":
        peer.update(permaticker=" 12345 ", figi="BBG000000003")
    elif mutation == "composite_trim":
        peer["figi"] = " BBG000000001 "
    elif mutation == "group_trim":
        peer["table"] = "stocks "
    else:
        peer = copy.deepcopy(first)
    assert all(f["status"] == "source_reference_refused" for f in relations(qualify(master_rows=[first, peer])))


def test_conflicting_class_across_dates_quarantines_all_not_current_winner():
    facts = relations(qualify([result(), result(share_class_figi="BBG000000003")]))
    assert all("composite_to_class_conflict_across_source_dates" in f["refusal_reasons"] for f in facts)


def test_malformed_identifiable_ID_peer_blocks_valid_class_count_on_same_asof():
    source_matrix = matrix([row("FAKE"), row("OTHER")])
    selected = refs.freeze_native_class_query_plan(source_matrix, mode="exact_cells")
    facts = relations(qualify([result(), result("OTHER", composite_figi=" BBG000000003 ", share_class_shares_outstanding=True)], selected=selected))
    assert "same_class_asof_count_missing_malformed_or_conflicting_peer" in facts[0]["refusal_reasons"]


def test_duplicate_JSON_identifiers_retain_every_negative_ID_and_block_good_peer():
    source_matrix = matrix([row("FAKE"), row("OTHER")])
    selected = refs.freeze_native_class_query_plan(source_matrix, mode="exact_cells")
    tickets = list(selected.iter_queries())
    raw = b'{"status":"OK","results":{"ticker":"OTHER","composite_figi":"BBG000000003","composite_figi":"BBG000000004","share_class_figi":"BBG000000002","share_class_shares_outstanding":123,"type":"CS","locale":"us","market":"stocks"}}'
    captures = [capture(tickets[0]), capture(tickets[1], raw=raw)]
    reference = refs.qualify_native_dated_class_reference(selected, master(), iter(captures), retrieved_at=END)
    facts = relations(reference)
    assert facts[0]["status"] == "source_reference_refused"
    assert facts[1]["source_composites"] == ["BBG000000003", "BBG000000004"]
    assert "duplicate_response_JSON_key" in facts[1]["refusal_reasons"]


def test_conflicting_own_class_count_same_asof_refuses_all_alias_observations():
    selected = refs.freeze_native_class_query_plan(matrix([row("FAKE"), row("OTHER")]), mode="exact_cells")
    facts = relations(qualify([result(), result("OTHER", share_class_shares_outstanding=124)], selected=selected))
    assert all("same_class_asof_count_missing_malformed_or_conflicting_peer" in f["refusal_reasons"] for f in facts)


@pytest.mark.parametrize("status,observed,raw,media", [(404, False, b"", ""), (403, True, b"{}", "application/json"),
    (200, True, b'{"status":"OK","results":NaN}', "application/json"),
    (200, True, b"PRIVATE-BODY", "application/json"), (200, True, b"{}", "text/html")])
def test_refused_body_status_media_nonfinite_and_missing_receipts_retained(status, observed, raw, media):
    selected = plan()
    first = next(selected.iter_queries())
    reference = refs.qualify_native_dated_class_reference(selected, master(),
        iter([capture(first, raw=raw, status=status, observed=observed, media=media)]), retrieved_at=END)
    fact = relations(reference)[0]
    assert fact["status"] == "source_reference_refused" and fact["origin"]["http_status"] == status
    assert fact["origin"]["raw_sha256"] == hash_bytes(raw)
    assert "PRIVATE-BODY" not in canonical_json(fact)
    assert reference.header()["uncaptured_query_count"] == 1
    assert reference.header()["complete_planned_capture_inventory"] is False


def test_plan_order_source_origin_and_clock_mismatch_refuse_before_positive_report():
    selected = plan()
    tickets = list(selected.iter_queries())
    with pytest.raises(refs.NativeDatedClassError, match="order"):
        refs.qualify_native_dated_class_reference(selected, master(), [capture(tickets[1])], retrieved_at=END)
    with pytest.raises(refs.NativeDatedClassError, match="chronology"):
        refs.qualify_native_dated_class_reference(selected, master(), [capture(tickets[0], at="2026-10-14T03:00:00Z")], retrieved_at=END)
    with pytest.raises(refs.NativeDatedClassError, match="bound_response"):
        refs.capture_native_dated_class_response(tickets[0], raw=b"{}", raw_sha256="0"*64,
            request_sha256="0"*64, received_at=NOW, http_status=200, content_type="application/json", body_observed=True)


def test_strong_tickets_not_arbitrary_dict_approval_and_factories_only():
    with pytest.raises(refs.NativeDatedClassError, match="exact_source"):
        refs.freeze_native_class_query_plan({"complete": True}, mode="exact_cells")
    with pytest.raises(refs.NativeDatedClassError, match="exact_source_query"):
        refs.capture_native_dated_class_response({"source_admitted": True}, raw=b"{}", raw_sha256=hash_bytes(b"{}"),
            request_sha256="0"*64, received_at=NOW, http_status=200, content_type="application/json", body_observed=True)
    for cls in (refs.NativeClassQueryPlan, refs.NativeDatedClassQuery, refs.CapturedNativeDatedClassResponse, refs.NativeDatedClassReference):
        with pytest.raises(refs.NativeDatedClassError, match="factory"):
            cls()


def test_record_and_master_identity_seals_reject_coherent_replacement():
    value = qualify()
    old = value.sha256
    detached = relations(value)
    detached[0]["authority"]["denominator_admitted"] = True
    assert value.sha256 == old and relations(value)[0]["authority"]["denominator_admitted"] is False
    object.__setattr__(value, "_records", ())
    object.__setattr__(value, "_anchor", (value._plan, value._archive, value._archive.raw, value._header, value._records, value._digest))
    with pytest.raises(refs.NativeDatedClassError, match="sealed_dated_reference"):
        list(value.iter_relations())


def test_callback_master_mutation_refuses_original_provenance_claim():
    selected, archive = plan(), master()
    first = next(selected.iter_queries())
    def iterator():
        object.__setattr__(archive, "raw", b"changed-after-initial-parse")
        yield capture(first)
    with pytest.raises(refs.NativeDatedClassError, match="original_master_changed"):
        refs.qualify_native_dated_class_reference(selected, archive, iterator(), retrieved_at=END)


@pytest.mark.parametrize("field,value", [("table", "actions"), ("request_sha256", "0"*64)])
def test_source_archive_metadata_mutation_invalidates_qualified_snapshot(field, value):
    reference = qualify()
    object.__setattr__(reference._archive, field, value)
    with pytest.raises(refs.NativeDatedClassError, match="sealed_dated_reference"):
        reference.header()
