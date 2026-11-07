"""Fabricated compact source matrices only; no real source, signal or API."""
from __future__ import annotations

import copy
import json
import struct

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_population_class_matrix as matrix

NOW = "2026-10-14T01:00:00Z"
REPORT_AT = "2026-10-14T01:01:00Z"


def row(ticker="FAKE", settlement="2023-02-28", quantity=1):
    return {"ticker": ticker, "settlement_date": settlement, "short_interest": quantity}


def fixture(changes=None, *, incomplete=False, page_count=33):
    changes = changes or {}
    entries, pages = [], []
    for ordinal in range(1, page_count + 1):
        url = matrix.INITIAL_URL if ordinal == 1 else matrix.ENDPOINT + "?cursor=fabricated-" + str(ordinal)
        next_url = (None if ordinal == page_count and not incomplete
                    else matrix.ENDPOINT + "?cursor=fabricated-" + str(ordinal + 1))
        raw = canonical_json({"status": "OK", "results": changes.get(ordinal, []), "next_url": next_url}).encode()
        descriptor = {"method": "GET", "url": url, "authentication": "Bearer_header_not_recorded"}
        receipt = {"request_sha256": hash_payload(descriptor), "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
                   "received_at": NOW, "http_status": 200, "content_type": "application/json", "raw_path": f"page-{ordinal:02d}.raw"}
        segment = "parent" if ordinal <= 32 else "child"
        entries.append({"ordinal": ordinal, "segment": segment, "request": descriptor,
                        "receipt": receipt, "row_count": len(changes.get(ordinal, [])), "next_url": next_url})
        pages.append(matrix.capture_native_population_page(ordinal=ordinal, segment=segment, descriptor=descriptor,
                    request_sha256=receipt["request_sha256"], raw=raw, raw_sha256=receipt["raw_sha256"],
                    received_at=NOW, http_status=200, content_type="application/json"))
    report = {"schema": matrix.REPORT_SCHEMA, "parent_source": {"run": "fabricated-parent", "head": "a"*40,
              "protocol_sha256": "b"*64, "inventory_sha256": "c"*64, "budget_bytes_sha256": "d"*64,
              "last_next_url_sha256": hash_bytes(entries[31]["next_url"].encode())},
              "child_source": {"run": "fabricated-child", "head": "e"*40, "protocol_sha256": "f"*64,
                               "code_identity_sha256": "0"*64}, "pages": entries, "retrieved_at": REPORT_AT,
              "complete_advertised_page_chain": True, "outcome_looks": 0, "qc_attempts": 0}
    return report, pages


def bind(report):
    report = copy.deepcopy(report)
    report.pop("report_sha256", None)
    report["report_sha256"] = hash_payload(report)
    raw = canonical_json(report).encode()
    return matrix.bind_native_population_manifest(raw, hash_bytes(raw))


def assemble(changes=None, **kwargs):
    report, pages = fixture(changes, **kwargs)
    return matrix.freeze_native_population_class_matrix(bind(report), iter(pages))


def test_compact_native_matrix_has_no_signal_price_look_or_execution_authority():
    result = assemble({1: [row("OLD1")], 33: [row("NEW1", "2026-08-31")]})
    header = result.header()
    assert header["source_row_count"] == header["query_count"] == 2
    assert header["refusal_count"] == 0
    assert header["complete_advertised_page_chain_reconstructed"] is True
    assert header["authority"]["actual_outcome_looks"] == 0
    assert header["authority"]["source_admitted"] is False
    assert header["authority"]["actual_input_execution_admitted"] is False
    assert header["authority"]["qc_authorized"] is False
    hbytes, qbytes, rbytes = result.parts()
    assert len(qbytes) == 2 * 16 and not rbytes
    assert "raw_body" not in hbytes.decode() and "short_interest" not in hbytes.decode()
    assert matrix._matrix_digest(hbytes, qbytes, rbytes) == result.sha256


def test_exact_unique_ticker_dates_sorted_and_private_source_origins_preserved():
    result = assemble({1: [row("ZZZ", "2023-02-28"), row("a-a", "2022-10-14")], 33: [row("ZZZ", "2024-03-15")]})
    queries = list(result.iter_queries())
    assert [(q["ticker"], q["settlement_date"]) for q in queries] == [
        ("ZZZ", "2023-02-28"), ("ZZZ", "2024-03-15"), ("a-a", "2022-10-14")]
    assert queries[0]["source_origin"]["page_ordinal"] == 1
    assert queries[1]["source_origin"]["page_ordinal"] == 33
    assert queries[2]["request"]["url"].endswith("a-a")
    assert queries[2]["request"]["params"] == {"date": "2022-10-14"}
    assert all(q["request_sha256"] == hash_payload(q["request"]) for q in queries)


@pytest.mark.parametrize("peer", [row(), row(quantity=True), row(ticker=" FAKE "),
                                  row(settlement="2023-02-28 "), {**row(), "short_volume": 50}])
def test_identifiable_malformed_peer_across_segments_quarantines_every_copy(peer):
    result = assemble({1: [row()], 33: [peer]})
    assert list(result.iter_queries()) == []
    refusals = list(result.iter_refusals())
    assert len(refusals) == 2
    assert all("duplicate_identifiable_ticker_settlement_all_copies_quarantined" in r["refusal_reasons"] for r in refusals)
    assert {r["source_origin"]["page_ordinal"] for r in refusals} == {1, 33}


@pytest.mark.parametrize("raw,reason", [(None, "unidentifiable"), ([], "unidentifiable"),
    ({"ticker": "FAKE"}, "noncanonical_settlement"), (row(quantity=1.5), "invalid_exact"),
    (row(quantity="10"), "invalid_exact"), (row(quantity=-1), "invalid_exact"),
    (row(ticker="BRK/B"), "raw_ticker"), (row("FAKE", "2030-01-01"), "outside_frozen"),
    ({**row(), "trade_date": "2023-02-28"}, "not_open_short")])
def test_all_malformed_out_of_range_and_unsupported_rows_retained_as_refusals(raw, reason):
    result = assemble({4: [raw]})
    assert not list(result.iter_queries())
    refused = list(result.iter_refusals())
    assert len(refused) == result.header()["source_row_count"] == 1
    assert any(reason in code for code in refused[0]["refusal_reasons"])
    assert refused[0]["source_origin"]["row_index"] == 0


def test_complete_boolean_never_admits_an_incomplete_raw_cursor_chain():
    report, pages = fixture(incomplete=True)
    assert report["complete_advertised_page_chain"] is True
    with pytest.raises(matrix.NativePopulationMatrixError, match="chain_incomplete"):
        matrix.freeze_native_population_class_matrix(bind(report), iter(pages))


@pytest.mark.parametrize("change", ["missing", "extra", "reordered", "segment", "descriptor", "receipt", "parent_cursor"])
def test_manifest_and_raw_page_inventory_mismatches_cannot_construct_matrix(change):
    report, pages = fixture({1: [row()]})
    if change == "missing":
        pages.pop()
    elif change == "extra":
        pages.append(pages[-1])
    elif change == "reordered":
        pages[0], pages[1] = pages[1], pages[0]
    elif change == "segment":
        report["pages"][32]["segment"] = "parent"
    elif change == "descriptor":
        report["pages"][1]["request"]["url"] = matrix.ENDPOINT + "?cursor=changed"
        report["pages"][1]["receipt"]["request_sha256"] = hash_payload(report["pages"][1]["request"])
    elif change == "receipt":
        report["pages"][0]["receipt"]["raw_sha256"] = "0"*64
    else:
        report["parent_source"]["last_next_url_sha256"] = "0"*64
    with pytest.raises(matrix.NativePopulationMatrixError):
        matrix.freeze_native_population_class_matrix(bind(report), iter(pages))


@pytest.mark.parametrize("bad_url", ["http://api.massive.com/stocks/v1/short-interest?cursor=x",
    "https://evil.invalid/stocks/v1/short-interest?cursor=x",
    matrix.ENDPOINT + "?cursor=x&apiKey=PRIVATE", matrix.ENDPOINT + "?cursor=x&ticker=ONLY",
    matrix.ENDPOINT + "?cursor=x&settlement_date.lte=2030-01-01",
    matrix.ENDPOINT + "?cursor=x&cursor=y", matrix.ENDPOINT + "?cursor="])
def test_endpoint_cursor_authentication_and_population_expansion_refused_without_echo(bad_url):
    report, _ = fixture()
    report["pages"][0]["next_url"] = bad_url
    with pytest.raises(matrix.NativePopulationMatrixError) as exc:
        bind(report)
    assert "PRIVATE" not in str(exc.value)


def test_manifest_original_payload_and_byte_digests_not_caller_flags():
    report, _ = fixture()
    report["report_sha256"] = "0"*64
    raw = canonical_json(report).encode()
    with pytest.raises(matrix.NativePopulationMatrixError, match="payload_digest"):
        matrix.bind_native_population_manifest(raw, hash_bytes(raw))
    with pytest.raises(matrix.NativePopulationMatrixError, match="raw_bytes"):
        matrix.bind_native_population_manifest(raw, "0"*64)
    with pytest.raises(matrix.NativePopulationMatrixError, match="exact_bound"):
        matrix.freeze_native_population_class_matrix({"complete": True}, ())


def test_page_constructed_once_then_raw_mutation_and_coherent_seal_replacement_refused():
    report, pages = fixture({1: [row()]})
    page = pages[0]
    object.__setattr__(page, "_raw", b"{}")
    object.__setattr__(page, "_anchor", (page._raw, page._meta))
    with pytest.raises(matrix.NativePopulationMatrixError, match="sealed_population_page"):
        matrix.freeze_native_population_class_matrix(bind(report), iter(pages))


def test_matrix_detached_header_mutation_and_coherent_component_reseal_refused():
    result = assemble({1: [row()]})
    original = result.sha256
    header = result.header()
    header["authority"]["source_admitted"] = True
    assert result.header()["authority"]["source_admitted"] is False and result.sha256 == original
    object.__setattr__(result, "_queries", b"")
    object.__setattr__(result, "_anchor", (result._header, result._queries, result._refusals, result._digest))
    with pytest.raises(matrix.NativePopulationMatrixError, match="sealed_class_matrix"):
        list(result.iter_queries())


def test_callback_policy_changes_cannot_rewrite_prospective_scope(monkeypatch):
    report, pages = fixture({1: [row()]})
    def iterator():
        for ordinal, page in enumerate(pages):
            if ordinal == 1:
                monkeypatch.setitem(matrix.PARAMS, "settlement_date.lte", "2030-01-01")
            yield page
    with pytest.raises(matrix.NativePopulationMatrixError, match="policy_changed"):
        matrix.freeze_native_population_class_matrix(bind(report), iterator())


def test_generator_consumed_once_and_raw_financial_values_not_duplicated_in_matrix():
    report, pages = fixture({1: [row("A", quantity=987654321), row("B", quantity=0)]})
    consumed = []
    def iterator():
        for page in pages:
            consumed.append(page.metadata()["ordinal"])
            yield page
    result = matrix.freeze_native_population_class_matrix(bind(report), iterator())
    assert consumed == list(range(1, 34))
    assert result.header()["query_count"] == 2
    assert b"987654321" not in b"".join(result.parts())
    assert len(result.parts()[1]) == 32


def test_exact_96_cumulative_page_ceiling_and_factory_only_types():
    report, pages = fixture(page_count=96)
    assert matrix.freeze_native_population_class_matrix(bind(report), iter(pages)).header()["query_count"] == 0
    report, _ = fixture()
    report["pages"].append(copy.deepcopy(report["pages"][-1]))
    report["pages"][-1]["ordinal"] = 97
    with pytest.raises(matrix.NativePopulationMatrixError):
        bind(report)
    for cls in (matrix.CapturedNativePopulationPage, matrix.NativePopulationManifest, matrix.NativePopulationClassMatrix):
        with pytest.raises(matrix.NativePopulationMatrixError, match="factory"):
            cls()


def test_fixed_protected_parts_rebuild_without_original_source_pages():
    original = assemble({1: [row(), row("SECOND")], 33: [row(quantity=True), row("THIRD")]})
    h, q, r = original.parts()
    rebuilt = matrix.rebuild_native_population_class_matrix(h, q, r, original.sha256)
    assert type(rebuilt) is matrix.NativePopulationClassMatrix
    assert rebuilt.parts() == original.parts() and rebuilt.sha256 == original.sha256
    assert list(rebuilt.iter_queries()) == list(original.iter_queries())
    assert list(rebuilt.iter_refusals()) == list(original.iter_refusals())


@pytest.mark.parametrize("change", ["authority", "count", "bool_count", "query_duplicate", "query_origin_duplicate",
                                   "query_origin_gap", "refusal_collision", "refusal_code", "table", "date", "page"])
def test_coherently_rehashed_parts_with_dangerous_structure_still_refused(change):
    original = assemble({1: [row("AAA"), row("BBB"), row("DDD", quantity=True)]})
    h, q, r = original.parts()
    header = json.loads(h)
    query_records = list(matrix._QUERY.iter_unpack(q))
    refusal_records = list(matrix._REFUSAL.iter_unpack(r))
    if change == "authority":
        header["authority"]["source_admitted"] = True
    elif change == "count":
        header["source_row_count"] += 1
    elif change == "bool_count":
        header["query_count"] = True
    elif change == "query_duplicate":
        query_records[1] = (*query_records[0][:2], *query_records[1][2:])
    elif change == "query_origin_duplicate":
        query_records[1] = (*query_records[1][:2], *query_records[0][2:])
    elif change == "query_origin_gap":
        query_records[1] = (*query_records[1][:3], 99)
    elif change == "refusal_collision":
        refusal_records[0] = (*query_records[0][:2], *refusal_records[0][2:])
    elif change == "refusal_code":
        refusal_records[0] = (*refusal_records[0][:4], 7, 0)
    elif change == "table":
        header["symbols"] = ["BBB", "AAA", "DDD"]
    elif change == "date":
        header["settlements"] = ["2030-01-01"]
    else:
        header["page_origins"][0]["ordinal"] = 2
    q = b"".join(matrix._QUERY.pack(*record) for record in query_records)
    r = b"".join(matrix._REFUSAL.pack(*record) for record in refusal_records)
    header["queries_sha256"], header["refusals_sha256"] = hash_bytes(q), hash_bytes(r)
    h = canonical_json(header).encode()
    with pytest.raises(matrix.NativePopulationMatrixError):
        matrix.rebuild_native_population_class_matrix(h, q, r, matrix._matrix_digest(h, q, r))


def test_parts_require_literal_expected_pin_and_preserve_no_raw_chain_revalidation_claim():
    original = assemble({1: [row()]})
    with pytest.raises(matrix.NativePopulationMatrixError, match="digest_changed"):
        matrix.rebuild_native_population_class_matrix(*original.parts(), "0"*64)
    assert matrix.rebuild_native_population_class_matrix(*original.parts(), original.sha256).sha256 == original.sha256
