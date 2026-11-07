"""Fabricated ignored prototype tests, never actual source observations."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import urllib.parse
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_population_class_matrix as matrices
import research.short_interest_etf.native_dated_identity as identities
import research.short_interest_etf.native_dated_class_reference as references
import research.short_interest_etf.sharadar_securities_master as master

import research.short_interest_etf.native_reported_anchor_plan as draft
NOW = "2026-10-14T01:00:00Z"
COMPOSITE, CLASS, NEXT_CLASS = "BBG000000001", "BBG000000002", "BBG000000003"


def archive(table, content):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr(zipfile.ZipInfo(table + ".csv", date_time=(2023, 1, 1, 0, 0, 0)), content)
    return master.CapturedSharadarMasterArchive(table, stream.getvalue(), master.request_sha256("download-" + table))


def tickers():
    return archive("tickers", "table,permaticker,ticker,exchange,isdelisted,category,figi\n"
                   f"stocks,1,SYN,XNYS,N,Domestic Common Stock,{COMPOSITE}\n"
                   "stocks,2,ALT,XNYS,N,Domestic Common Stock,BBG000000004\n")


def actions(rows=()):
    return archive("actions", "date,action,ticker,name,value,contraticker,contraname\n" + "".join(rows))


def dictionary():
    return archive("descriptions", "table,indicator,title,description,unittype,isprimarykey,isfilter\n"
                   "actiontypes,split,Stock split,Stock split ratio,ratio,Y,N\n")


def identity(at, *, class_id=CLASS, malformed=False, alt=False, ticker="SYN", venue="XNYS"):
    row = {"ticker": ticker, "composite_figi": COMPOSITE, "share_class_figi": class_id,
           "locale": "us", "market": "stocks", "type": "CS", "active": True}
    if venue is not None:
        row["primary_exchange"] = venue
    if malformed:
        row["share_class_figi"] = None
    rows = [row]
    if alt:
        rows.append({**row, "ticker": "ALT", "composite_figi": "BBG000000004", "share_class_figi": "BBG000000005"})
    pages = []
    for active, selected in ((True, rows), (False, [])):
        url = identities.ENDPOINT + "?" + urllib.parse.urlencode(identities.request_descriptor(at, active)["params"])
        raw = canonical_json({"status": "OK", "results": selected}).encode()
        pages.append(identities.CapturedDatedIdentityPage(at, active, 1, url, raw, NOW, NOW, 200, "application/json"))
    return identities.qualify_dated_identity(tuple(pages), identities.build_composite_native_index(tickers()),
                 query_date=at, started_at=NOW, retrieved_at=NOW)


def matrix(cells):
    pages, records = [], []
    for ordinal in range(1, 34):
        url = matrices.INITIAL_URL if ordinal == 1 else matrices.ENDPOINT + "?cursor=fabricated-" + str(ordinal)
        next_url = None if ordinal == 33 else matrices.ENDPOINT + "?cursor=fabricated-" + str(ordinal + 1)
        rows = [{"ticker": ticker, "settlement_date": at, "short_interest": 1} for ticker, at in cells] if ordinal == 1 else []
        raw = canonical_json({"status": "OK", "results": rows, "next_url": next_url}).encode()
        descriptor = {"method": "GET", "url": url, "authentication": "Bearer_header_not_recorded"}
        receipt = {"request_sha256": hash_payload(descriptor), "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
                   "received_at": NOW, "http_status": 200, "content_type": "application/json", "raw_path": f"p{ordinal}.raw"}
        segment = "parent" if ordinal <= 32 else "child"
        records.append({"ordinal": ordinal, "segment": segment, "request": descriptor, "receipt": receipt,
                        "row_count": len(rows), "next_url": next_url})
        pages.append(matrices.capture_native_population_page(ordinal=ordinal, segment=segment, descriptor=descriptor,
             request_sha256=receipt["request_sha256"], raw=raw, raw_sha256=receipt["raw_sha256"], received_at=NOW,
             http_status=200, content_type="application/json"))
    report = {"schema": matrices.REPORT_SCHEMA, "parent_source": {"run": "fabricated-parent", "head": "a"*40,
              "protocol_sha256": "b"*64, "inventory_sha256": "c"*64, "budget_bytes_sha256": "d"*64,
              "last_next_url_sha256": hash_bytes(records[31]["next_url"].encode())},
              "child_source": {"run": "fabricated-child", "head": "e"*40, "protocol_sha256": "f"*64,
                               "code_identity_sha256": "0"*64}, "pages": records,
              "retrieved_at": NOW, "outcome_looks": 0, "qc_attempts": 0}
    report["report_sha256"] = hash_payload(report)
    raw = canonical_json(report).encode()
    return matrices.freeze_native_population_class_matrix(
        matrices.bind_native_population_manifest(raw, hash_bytes(raw)), iter(pages))


def plan(dates, *, reports=None, events=(), cells=None):
    return draft.build_native_reported_anchor_plan(matrix(cells or [("SYN", at) for at in dates]),
          reports or tuple(identity(at) for at in dates), actions(events), dictionary())


def response(query, *, class_id=None, composite=None, count=100, status=200, receipt=NOW):
    ticket = query.to_payload()
    raw = canonical_json({"status": "OK", "results": {"ticker": ticket["ticker"],
          "composite_figi": composite or COMPOSITE, "share_class_figi": class_id or CLASS,
          "share_class_shares_outstanding": count, "type": "CS", "locale": "us", "market": "stocks"}}).encode()
    return references.capture_native_dated_class_response(query, raw=raw, raw_sha256=hash_bytes(raw),
              request_sha256=ticket["request_sha256"], received_at=receipt, http_status=status,
              content_type="application/json", body_observed=True)


def registry(source, *, failure=(), classes=None):
    classes = classes or {}
    captures = [response(query, class_id=classes.get(query.to_payload()["query_asof_date"]),
                status=404 if index in failure else 200)
                for index, query in enumerate(source.query_plan.iter_queries(), 1)]
    return details(draft.qualify_native_reported_counts(source, captures))


def details(source):
    """Test-only expansion of small fabricated samples; production stays lazy."""
    payload = source.to_payload()
    payload["cells"] = sorted(source.iter_cells(), key=lambda row: (row["settlement_date"], row["ticker"]))
    if type(source) is draft.NativeReportedAnchorPlan:
        assert source.to_payload()["cell_count"] <= 10000
        payload["anchors"] = sorted(source.iter_anchors(), key=lambda row: row["original_query_ordinal"])
        payload["selected_query_ordinals"] = source.query_plan.to_payload()["selected_query_ordinals"]
        payload["source_split_fences"] = list(source.iter_split_fences())
    else:
        payload["records"] = list(source.iter_records())
    return payload


def test_quarter_first_no_every_settlement_request_and_no_execution_authority():
    result = plan(("2023-01-13", "2023-01-31", "2023-04-14", "2023-04-28"))
    payload = details(result)
    assert payload["selected_query_ordinals"] == [1, 3]
    assert payload["exact_request_budget"] == 2
    assert [cell["anchor_original_query_ordinal"] for cell in payload["cells"]] == [1, 1, 3, 3]
    assert payload["authority"]["outcome_looks"] == payload["authority"]["qc_attempts"] == 0
    assert payload["authority"]["actual_input_execution_admitted"] is False
    assert len(result.sha256) == 64


def test_first_seen_new_class_within_quarter_is_queried_without_price_screen():
    dates = ("2023-01-13", "2023-01-31")
    result = plan(dates, reports=(identity(dates[0]), identity(dates[1], alt=True)),
                  cells=[("SYN", dates[0]), ("SYN", dates[1]), ("ALT", dates[1])])
    result = details(result)
    assert result["exact_request_budget"] == 2
    assert {(row["ticker"], row["query_asof_date"]) for row in result["anchors"]} == {("SYN", dates[0]), ("ALT", dates[1])}


def test_same_native_class_rename_does_not_create_redundant_count_query():
    dates = ("2023-01-13", "2023-01-31")
    source = plan(dates, reports=(identity(dates[0]), identity(dates[1], ticker="NEW")),
                  cells=[("SYN", dates[0]), ("NEW", dates[1])])
    assert source.to_payload()["exact_request_budget"] == 1
    assert all(not cell["refusal_reasons"] for cell in source.iter_cells())


def test_observed_class_transition_refresh_preserves_past_cell_and_exact_counts():
    dates = ("2023-01-13", "2023-01-31", "2023-02-15")
    source = plan(dates, reports=(identity(dates[0]), identity(dates[1], class_id=NEXT_CLASS), identity(dates[2], class_id=NEXT_CLASS)))
    result = registry(source, classes={dates[1]: NEXT_CLASS})
    assert source.query_plan.to_payload()["selected_query_ordinals"] == [1, 2]
    assert all(not cell["refusal_reasons"] for cell in result["cells"])
    assert result["cells"][0]["share_class_figi"] == CLASS
    assert result["cells"][1]["share_class_figi"] == NEXT_CLASS


def test_failed_refresh_fences_forward_without_retrospective_rejection_or_fallback():
    dates = ("2023-01-13", "2023-01-31", "2023-04-14", "2023-04-28")
    result = registry(plan(dates), failure=(2,))
    assert [bool(cell["refusal_reasons"]) for cell in result["cells"]] == [False, False, True, True]
    assert result["cells"][0]["same_class_count"]["numerator"] == 100
    assert result["cells"][0]["same_class_count"]["denominator"] == 1
    assert result["cells"][0]["same_class_count"]["source_number_token"] == "100"
    assert result["cells"][2]["same_class_count"] is None


def test_future_failed_count_cannot_change_past_prefix():
    earlier = registry(plan(("2023-01-13", "2023-01-31")))["cells"]
    later = registry(plan(("2023-01-13", "2023-01-31", "2023-04-14")), failure=(2,))["cells"]
    assert [{key: value for key, value in row.items() if key != "source_origin"} for row in later[:2]] \
        == [{key: value for key, value in row.items() if key != "source_origin"} for row in earlier]


def test_missing_identity_gap_refuses_cell_then_forces_fresh_count_forward():
    dates = ("2023-01-13", "2023-01-31", "2023-02-15")
    source = plan(dates, reports=(identity(dates[0]), identity(dates[1], malformed=True), identity(dates[2])))
    result = registry(source, failure=(2,))
    assert source.query_plan.to_payload()["selected_query_ordinals"] == [1, 3]
    assert [bool(cell["refusal_reasons"]) for cell in result["cells"]] == [False, True, True]
    assert "first_valid_identity_after_gap" in list(source.iter_anchors())[1]["refresh_reasons"]


@pytest.mark.parametrize("age,expected", [(0, True), (95, True), (96, False), (-1, False)])
def test_95_day_carry_boundary_and_no_future_anchor(age, expected):
    from datetime import timedelta
    beginning = draft.date(2023, 1, 1)
    assert draft.reported_anchor_age_ok(beginning.isoformat(), (beginning + timedelta(days=age)).isoformat()) is expected


def test_exact_same_day_source_split_requests_refresh_without_ratio_adjustment():
    dates = ("2023-01-13", "2023-01-31", "2023-02-15")
    source = plan(dates, events=("2023-01-31,split,SYN,Synthetic,2,,\n",))
    payload = details(source)
    assert payload["selected_query_ordinals"] == [1, 2]
    assert payload["source_split_fences"][0]["same_date_native_class"] == ["sharadar:permaticker:1", CLASS]
    assert "source_split_refresh" in payload["anchors"][1]["refresh_reasons"]
    assert all(cell["same_class_count"]["numerator"] == 100 for cell in registry(source)["cells"])


def test_between_settlement_split_is_unresolved_refresh_not_invented_native_event():
    source = plan(("2023-01-13", "2023-01-31"), events=("2023-01-20,split,SYN,Synthetic,2,,\n",))
    payload = details(source)
    assert payload["selected_query_ordinals"] == [1, 2]
    event = payload["source_split_fences"][0]
    assert event["same_date_native_class"] is None and event["economic_event_admitted"] is False
    assert "split_native_class_not_authenticated_on_action_date" in event["refusal_reasons"]
    assert "unresolved_source_split_refresh_fence" in payload["anchors"][1]["refresh_reasons"]


def test_unresolved_split_on_previously_observed_token_fences_same_class_rename():
    dates = ("2023-01-13", "2023-01-31")
    source = plan(dates, reports=(identity(dates[0]), identity(dates[1], ticker="NEW")),
                  events=("2023-01-20,split,SYN,Synthetic,2,,\n",),
                  cells=[("SYN", dates[0]), ("NEW", dates[1])])
    assert source.to_payload()["exact_request_budget"] == 2
    assert "unresolved_source_split_refresh_fence" in sorted(source.iter_anchors(), key=lambda row: row["original_query_ordinal"])[0]["refresh_reasons"]


def test_future_split_does_not_refresh_or_remove_earlier_cells():
    earlier = details(plan(("2023-01-13", "2023-01-31")))
    later = details(plan(("2023-01-13", "2023-01-31"), events=("2023-05-01,split,SYN,Synthetic,2,,\n",)))
    assert earlier["cells"] == later["cells"] and earlier["anchors"] == later["anchors"]


@pytest.mark.parametrize("changes", [{"class_id": NEXT_CLASS}, {"composite": "BBG000000009"}, {"count": True}, {"count": "100"}, {"count": 0}])
def test_wrong_identity_or_nonparticular_integral_count_cannot_enter_registry(changes):
    source = plan(("2023-01-13",))
    capture = response(next(source.query_plan.iter_queries()), **changes)
    result = details(draft.qualify_native_reported_counts(source, [capture]))
    assert result["cells"][0]["same_class_count"] is None
    assert result["cells"][0]["refusal_reasons"]


def test_original_archives_and_plan_are_immutable_after_construction():
    source = plan(("2023-01-13",))
    object.__setattr__(source._archives[0][0], "request_sha256", "0"*64)
    with pytest.raises(draft.AnchorError, match="dictionary_changed"):
        source.to_payload()


def test_caller_dict_identity_and_source_flags_cannot_make_plan():
    with pytest.raises(draft.AnchorError, match="exact_dated_identity"):
        plan(("2023-01-13",), reports=({"source_admitted": True},))


def test_outside_scope_refused_source_date_does_not_demand_future_identity_request():
    source = draft.build_native_reported_anchor_plan(
        matrix([("SYN", "2023-01-13"), ("SYN", "2030-01-01")]),
        (identity("2023-01-13"),), actions(), dictionary())
    assert source.to_payload()["exact_request_budget"] == 1
    assert source.to_payload()["source_matrix_refusal_count"] == 1


def test_capture_response_clock_order_and_plan_budget_remain_bound():
    source = plan(("2023-01-13", "2023-04-14"))
    tickets = list(source.query_plan.iter_queries())
    with pytest.raises(draft.AnchorError, match="chronology"):
        draft.qualify_native_reported_counts(source, [response(tickets[0], receipt="2026-10-14T02:00:00Z"), response(tickets[1])])
    with pytest.raises(draft.AnchorError, match="budget"):
        draft.qualify_native_reported_counts(source, [response(tickets[0]), response(tickets[1]), response(tickets[1])])


def test_summary_and_packed_parts_never_expand_source_cells_or_retain_date_maps():
    dates = ("2023-01-13", "2023-01-31", "2023-04-14")
    def sources():
        for at in dates:
            source = identity(at)
            yield source
            # The consumed sealed snapshot has been pinned and released, not
            # retained as a mutable source dependency or decoded date map.
            object.__setattr__(source, "_bytes", b"fabricated_consumed_source_changed")
    result = draft.build_native_reported_anchor_plan(matrix([("SYN", at) for at in dates]),
                                                    sources(), actions(), dictionary())
    summary = result.to_payload()
    assert "cells" not in summary and "anchors" not in summary
    assert summary["packed_cell_bytes"] == len(dates) * 12
    assert summary["packed_anchor_bytes"] == summary["exact_request_budget"] * 28
    assert not hasattr(result, "_sources")
    assert all(not row["refusal_reasons"] for row in result.iter_cells())


def test_count_capture_stream_releases_raw_bodies_without_changing_registry_facts():
    source = plan(("2023-01-13", "2023-04-14"))
    def captures():
        for query in source.query_plan.iter_queries():
            capture = response(query)
            yield capture
            object.__setattr__(capture, "_raw", b"fabricated_consumed_capture_changed")
    result = draft.qualify_native_reported_counts(source, captures())
    assert "cells" not in result.to_payload() and "records" not in result.to_payload()
    assert not hasattr(result, "_captures")
    assert all(row["same_class_count"]["numerator"] == 100 for row in result.iter_cells())


def test_archive_change_during_identity_stream_cannot_replace_original_pins():
    action_source = actions()
    def sources():
        yield identity("2023-01-13")
        object.__setattr__(action_source, "request_sha256", "0" * 64)
    with pytest.raises(draft.AnchorError, match="dictionary_changed"):
        draft.build_native_reported_anchor_plan(matrix([("SYN", "2023-01-13")]),
                                                sources(), action_source, dictionary())


def test_large_fabricated_inventory_is_packed_and_query_plan_decoded_once(monkeypatch):
    from datetime import timedelta
    count, days = 120, 12
    dates = tuple((draft.date(2023, 1, 13) + timedelta(days=15 * index)).isoformat() for index in range(days))
    tokens = [f"SYN{index:04d}" for index in range(count)]
    comps = [f"BBG{index + 1:09d}" for index in range(count)]
    classes = [f"BBG{index + 10001:09d}" for index in range(count)]
    original = archive("tickers", "table,permaticker,ticker,exchange,isdelisted,category,figi\n"
        + "".join(f"stocks,{index + 1},{token},XNYS,N,Domestic Common Stock,{comps[index]}\n"
                  for index, token in enumerate(tokens)))
    native_index = identities.build_composite_native_index(original)
    def reports():
        for at in dates:
            rows = [{"ticker": token, "composite_figi": comps[index], "share_class_figi": classes[index],
                     "locale": "us", "market": "stocks", "type": "CS", "active": True,
                     "primary_exchange": "XNYS"}
                    for index, token in enumerate(tokens)]
            pages = []
            for active, selected in ((True, rows), (False, [])):
                url = identities.ENDPOINT + "?" + urllib.parse.urlencode(identities.request_descriptor(at, active)["params"])
                pages.append(identities.CapturedDatedIdentityPage(at, active, 1, url,
                    canonical_json({"status": "OK", "results": selected}).encode(), NOW, NOW, 200, "application/json"))
            yield identities.qualify_dated_identity(tuple(pages), native_index, query_date=at,
                                                   started_at=NOW, retrieved_at=NOW)
    result = draft.build_native_reported_anchor_plan(matrix([(token, at) for token in tokens for at in dates]),
                                                    reports(), actions(), dictionary())
    summary = result.to_payload()
    assert summary["cell_count"] == count * days
    assert summary["exact_request_budget"] == count * 2
    assert summary["packed_cell_bytes"] == count * days * 12
    assert summary["packed_anchor_bytes"] == count * 2 * 28
    assert summary["class_label_count"] == count
    assert sum(1 for _ in result.iter_cells()) == count * days
    calls = [0]
    original_method = references.NativeClassQueryPlan.to_payload
    def once(self):
        calls[0] += 1
        return original_method(self)
    monkeypatch.setattr(references.NativeClassQueryPlan, "to_payload", once)
    def captures():
        for query in result.query_plan.iter_queries():
            token = query.to_payload()["ticker"]
            index = int(token[3:])
            yield response(query, composite=comps[index], class_id=classes[index])
    counts = draft.qualify_native_reported_counts(result, captures())
    # One decoding for registry, one for its externally supplied ticket stream;
    # never one full selected-ordinal JSON decoding per response.
    assert calls[0] == 2
    assert all(row["same_class_count"]["numerator"] == 100 for row in counts.iter_cells())


def test_ambiguous_old_symbol_fences_renamed_same_class_until_fresh_anchor():
    dates = ("2023-01-13", "2023-01-31", "2023-02-15")
    source = plan(dates, reports=(identity(dates[0]), identity(dates[1], malformed=True),
                                  identity(dates[2], ticker="NEW")),
                  cells=[("SYN", dates[0]), ("SYN", dates[1]), ("NEW", dates[2])])
    anchors = list(source.iter_anchors())
    assert source.to_payload()["exact_request_budget"] == 2
    assert {row["query_asof_date"] for row in anchors} == {dates[0], dates[2]}
    assert "first_valid_identity_after_gap" in next(row for row in anchors
        if row["query_asof_date"] == dates[2])["refresh_reasons"]


@pytest.mark.parametrize("method", ["iter_cells", "iter_records", "iter_parts"])
def test_count_iterator_rechecks_seal_after_first_yield(method):
    source = plan(("2023-01-13", "2023-04-14"))
    captures = [response(query) for query in source.query_plan.iter_queries()]
    registry = draft.qualify_native_reported_counts(source, captures)
    values = getattr(registry, method)()
    next(values)
    altered = list(registry._records)
    changed = json.loads(altered[1])
    changed["same_class_count"]["numerator"] = 999
    altered[1] = canonical_json(changed).encode()
    object.__setattr__(registry, "_records", tuple(altered))
    with pytest.raises(draft.AnchorError, match="sealed_count_registry_changed"):
        next(values)
