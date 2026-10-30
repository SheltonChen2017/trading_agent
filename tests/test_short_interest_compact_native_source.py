"""Fabricated source-only compiler regressions, never source files or keys."""
from pathlib import Path
import importlib.util
import json
import sys

import pytest
from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_population_class_matrix as matrices

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE))



def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


fixtures = _module("compiler_anchor_test_fixtures", HERE / "test_short_interest_native_reported_anchor_plan.py")
calendar_fixtures = _module("compiler_calendar_test_fixtures", HERE / "test_short_interest_nominal_publication_calendar.py")

import research.short_interest_etf.compact_native_source as compiler
import research.short_interest_etf.native_grouped_market_source as grouped
from test_short_interest_native_grouped_market_source import ROW, envelope, local_midnight_milliseconds

DATES = ("2022-01-04", "2022-01-17", "2022-02-03", "2022-02-17")


def source_pages(rows, *, pages_count=33):
    pages, records = [], []
    for ordinal in range(1, pages_count + 1):
        url = matrices.INITIAL_URL if ordinal == 1 else matrices.ENDPOINT + "?cursor=fabricated-" + str(ordinal)
        next_url = None if ordinal == pages_count else matrices.ENDPOINT + "?cursor=fabricated-" + str(ordinal + 1)
        selected = rows if ordinal == 1 else []
        raw = canonical_json({"status": "OK", "results": selected, "next_url": next_url}).encode()
        descriptor = {"method": "GET", "url": url, "authentication": "Bearer_header_not_recorded"}
        receipt = {"request_sha256": hash_payload(descriptor), "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
                   "received_at": fixtures.NOW, "http_status": 200, "content_type": "application/json", "raw_path": f"p{ordinal}.raw"}
        segment = "parent" if ordinal <= 32 else "child"
        records.append({"ordinal": ordinal, "segment": segment, "request": descriptor, "receipt": receipt,
                        "row_count": len(selected), "next_url": next_url})
        pages.append(matrices.capture_native_population_page(ordinal=ordinal, segment=segment, descriptor=descriptor,
             request_sha256=receipt["request_sha256"], raw=raw, raw_sha256=receipt["raw_sha256"], received_at=fixtures.NOW,
             http_status=200, content_type="application/json"))
    report = {"schema": matrices.REPORT_SCHEMA, "parent_source": {"run": "fabricated-parent", "head": "a"*40,
              "protocol_sha256": "b"*64, "inventory_sha256": "c"*64, "budget_bytes_sha256": "d"*64,
              "last_next_url_sha256": hash_bytes(records[31]["next_url"].encode())},
              "child_source": {"run": "fabricated-child", "head": "e"*40, "protocol_sha256": "f"*64,
                               "code_identity_sha256": "0"*64}, "pages": records, "retrieved_at": fixtures.NOW,
              "outcome_looks": 0, "qc_attempts": 0}
    report["report_sha256"] = hash_payload(report)
    raw = canonical_json(report).encode()
    matrix = matrices.freeze_native_population_class_matrix(matrices.bind_native_population_manifest(raw, hash_bytes(raw)), iter(pages))
    return matrix, tuple(pages)


def inputs(dates=DATES, *, rows=None, reports=None, count_failure=(), count_classes=None, pages_count=33):
    rows = rows if rows is not None else [{"ticker": "SYN", "settlement_date": at,
                                         "short_interest": (index + 1) * 9007199254740993}
                                        for index, at in enumerate(dates)]
    matrix, pages = source_pages(rows, pages_count=pages_count)
    plan = fixtures.draft.build_native_reported_anchor_plan(matrix,
             reports or tuple(fixtures.identity(at) for at in dates), fixtures.actions(), fixtures.dictionary())
    count_classes = count_classes or {}
    captures = [fixtures.response(query, class_id=count_classes.get(query.to_payload()["query_asof_date"]),
                                 status=404 if index in count_failure else 200)
                for index, query in enumerate(plan.query_plan.iter_queries(), 1)]
    registry = fixtures.draft.qualify_native_reported_counts(plan, iter(captures))
    calendar = calendar_fixtures.qualified(settlements=dates)
    return matrix, registry, pages, calendar


def build(values):
    return compiler.compile_native_source(*values)


def test_current_immediate_prior_exact_large_quantities_and_same_class_refs():
    source = build(inputs())
    rows = list(source.iter_cells())
    assert [row["source_short_quantity"] for row in rows] == [9007199254740993 * index for index in range(1, 5)]
    assert [row["immediate_prior_cell_ordinal"] for row in rows] == [None, 1, 2, 3]
    assert [row["immediate_prior_source_short_quantity"] for row in rows] == [None, 9007199254740993, 18014398509481986, 27021597764222979]
    assert rows[0]["pair_refusal_reasons"] == ["first_bound_schedule_date_no_prior"]
    assert all(not row["pair_refusal_reasons"] for row in rows[1:])
    assert rows[1]["same_class_denominator_reference"]["source_count"]["numerator"] == 100
    assert rows[1]["immediate_prior_denominator_reference"]["source_count"]["numerator"] == 100
    assert rows[1]["SI_origin"]["row_index"] == 1
    assert source.to_payload()["bound_original_page_count"] == 33
    assert len(source._cells) == compiler._CELL.size * 4
    assert source.header()["quantity_arithmetic_performed"] is False
    with pytest.raises(compiler.CompactSourceError, match="not_execution_admission"):
        source.execution_inputs()


def test_no_leapfrog_when_prior_scheduled_slot_missing():
    rows = [{"ticker": "SYN", "settlement_date": at, "short_interest": 10} for at in (DATES[0], DATES[2])]
    matrix, registry, pages, _ = inputs((DATES[0], DATES[2]), rows=rows)
    source = build((matrix, registry, pages, calendar_fixtures.qualified(settlements=DATES[:3])))
    current = list(source.iter_cells())[1]
    assert current["immediate_prior_cell_ordinal"] is None
    assert "immediate_prior_same_native_class_source_missing_or_ambiguous" in current["pair_refusal_reasons"]


def test_class_switch_never_inherits_prior_other_class():
    dates = DATES[:2]
    reports = (fixtures.identity(dates[0]), fixtures.identity(dates[1], class_id=fixtures.NEXT_CLASS))
    source = build(inputs(dates, reports=reports, count_classes={dates[1]: fixtures.NEXT_CLASS}))
    rows = list(source.iter_cells())
    assert rows[0]["share_class_figi"] != rows[1]["share_class_figi"]
    assert rows[1]["immediate_prior_cell_ordinal"] is None
    assert "immediate_prior_same_native_class_source_missing_or_ambiguous" in rows[1]["pair_refusal_reasons"]


def test_rename_same_class_pairs_by_bound_identity_not_current_symbol():
    dates = DATES[:2]
    raw = [{"ticker": "SYN", "settlement_date": dates[0], "short_interest": 5},
           {"ticker": "NEW", "settlement_date": dates[1], "short_interest": 6}]
    reports = (fixtures.identity(dates[0]), fixtures.identity(dates[1], ticker="NEW"))
    rows = list(build(inputs(dates, rows=raw, reports=reports)).iter_cells())
    # Matrix slots are ticker/date sorted, not source-page or temporal sorted.
    assert rows[0]["ticker"] == "NEW" and rows[0]["source_short_quantity"] == 6
    assert rows[1]["ticker"] == "SYN" and rows[1]["source_short_quantity"] == 5
    assert rows[0]["immediate_prior_cell_ordinal"] == 2
    assert rows[0]["SI_origin"]["row_index"] == 1


def test_duplicate_and_malformed_raw_peers_retained_not_zero_repaired():
    dates = DATES[:3]
    raw = [{"ticker": "SYN", "settlement_date": dates[0], "short_interest": 0},
           {"ticker": "SYN", "settlement_date": dates[1], "short_interest": 10},
           {"ticker": "SYN", "settlement_date": dates[1], "short_interest": "11"},
           {"ticker": "SYN", "settlement_date": dates[2], "short_interest": 12}, None]
    source = build(inputs(dates, rows=raw))
    assert [row["source_short_quantity"] for row in source.iter_cells()] == [0, 12]
    refusals = list(source.iter_refusals())
    assert len(refusals) == 3
    assert [row["source_origin"]["row_index"] for row in refusals] == [1, 2, 4]
    assert "duplicate_identifiable_ticker_settlement_all_copies_quarantined" in refusals[0]["refusal_reasons"]
    assert "invalid_exact_open_short_quantity" in refusals[1]["refusal_reasons"]
    assert list(source.iter_cells())[1]["immediate_prior_cell_ordinal"] is None


def test_missing_count_is_a_refusal_not_zero_or_old_count_fallback():
    dates = ("2022-01-04", "2022-04-14", "2022-04-28")
    rows = list(build(inputs(dates, count_failure=(2,))).iter_cells())
    assert rows[0]["same_class_denominator_reference"] is not None
    assert rows[1]["same_class_denominator_reference"] is rows[2]["same_class_denominator_reference"] is None
    assert rows[1]["registry_refusal_reasons"]
    assert "immediate_prior_native_class_or_count_source_refused" in rows[2]["pair_refusal_reasons"]


def test_ambiguous_native_composite_aliases_refused_before_compiler():
    import urllib.parse
    dates = DATES[:2]
    second_composite = "BBG000000004"
    master = fixtures.archive("tickers", "table,permaticker,ticker,exchange,isdelisted,category,figi\n"
                  f"stocks,1,SYN,XNYS,N,Domestic Common Stock,{fixtures.COMPOSITE}\n"
                  f"stocks,1,ALT,XNYS,N,Domestic Common Stock,{second_composite}\n")
    native_index = fixtures.identities.build_composite_native_index(master)
    reports = []
    for at in dates:
        pages = []
        rows = [{"ticker": token, "composite_figi": composite, "share_class_figi": fixtures.CLASS,
                 "locale": "us", "market": "stocks", "type": "CS", "active": True}
                for token, composite in (("SYN", fixtures.COMPOSITE), ("ALT", second_composite))]
        for active, selected in ((True, rows), (False, [])):
            url = fixtures.identities.ENDPOINT + "?" + urllib.parse.urlencode(fixtures.identities.request_descriptor(at, active)["params"])
            raw = canonical_json({"status": "OK", "results": selected}).encode()
            pages.append(fixtures.identities.CapturedDatedIdentityPage(at, active, 1, url, raw,
                         fixtures.NOW, fixtures.NOW, 200, "application/json"))
        reports.append(fixtures.identities.qualify_dated_identity(tuple(pages), native_index,
                       query_date=at, started_at=fixtures.NOW, retrieved_at=fixtures.NOW))
    raw = [{"ticker": token, "settlement_date": at, "short_interest": 10}
           for at in dates for token in ("ALT", "SYN")]
    matrix, original_pages = source_pages(raw)
    # The earlier source factory already refuses this ambiguous native/master
    # fixture. Do not forge an admitted registry to make a compiler test pass.
    with pytest.raises(fixtures.draft.AnchorError, match="no_source_qualified_anchor_candidates"):
        fixtures.draft.build_native_reported_anchor_plan(matrix, tuple(reports), fixtures.actions(), fixtures.dictionary())


@pytest.mark.parametrize("kind", ["missing", "extra", "reorder", "unsealed", "different_bytes", "changed_ordinal"])
def test_original_page_lineage_refused(kind):
    matrix, registry, pages, calendar = inputs()
    if kind == "missing":
        bad = pages[:-1]
    elif kind == "extra":
        bad = pages + pages[-1:]
    elif kind == "reorder":
        bad = pages[1:2] + pages[:1] + pages[2:]
    elif kind == "unsealed":
        bad = (pages[0].raw_bytes(),) + pages[1:]
    else:
        meta = pages[0].metadata()
        raw = pages[0].raw_bytes().replace(b"9007199254740993", b"9007199254740994") if kind == "different_bytes" else pages[0].raw_bytes()
        changed = matrices.capture_native_population_page(ordinal=2 if kind == "changed_ordinal" else 1,
          segment=meta["segment"], descriptor=meta["request"], request_sha256=meta["request_sha256"], raw=raw,
          raw_sha256=hash_bytes(raw), received_at=meta["received_at"], http_status=200, content_type="application/json")
        bad = (changed,) + pages[1:]
    with pytest.raises(compiler.CompactSourceError):
        build((matrix, registry, iter(bad), calendar))


def test_more_than_legacy_32_pages_supported_and_original_chain_complete():
    assert build(inputs(pages_count=40)).to_payload()["bound_original_page_count"] == 40


def test_registry_from_different_matrix_refused_even_same_bytes():
    matrix, registry, pages, calendar = inputs()
    other = inputs()[1]
    with pytest.raises(compiler.CompactSourceError, match="matrix_lineage_changed"):
        build((matrix, other, pages, calendar))


def test_reflective_state_change_after_yield_refused_and_payload_detached():
    source = build(inputs())
    detached = source.header()
    detached["authority"]["source_admitted"] = True
    assert source.header()["authority"]["source_admitted"] is False
    iterator = source.iter_cells()
    next(iterator)
    object.__setattr__(source, "_cells", source._cells + b" ")
    with pytest.raises(compiler.CompactSourceError, match="sealed_compact_source_changed"):
        next(iterator)


def test_registry_mutation_during_page_replay_refused():
    matrix, registry, pages, calendar = inputs()
    def changed():
        yield pages[0]
        object.__setattr__(registry, "_flags", registry._flags + b"x")
        yield from pages[1:]
    with pytest.raises(fixtures.draft.AnchorError, match="sealed_count_registry_changed"):
        build((matrix, registry, changed(), calendar))


def test_lazy_cells_do_not_reparse_or_rebuild_calendar_report_per_cell(monkeypatch):
    source = build(inputs())
    def refuse_reparse(value):
        raise AssertionError("per_cell_calendar_materialization_forbidden")
    monkeypatch.setattr(type(source._calendar), "to_bytes", refuse_reparse)
    assert len(list(source.iter_cells())) == 4


def test_calendar_field_change_after_yield_is_still_refused():
    source = build(inputs())
    rows = source.iter_cells()
    next(rows)
    object.__setattr__(source._calendar, "_raw", source._calendar._raw + b" ")
    with pytest.raises(compiler.CompactSourceError, match="bound_nominal_calendar_changed"):
        next(rows)


def test_source_factories_grant_no_admission_or_outcome_authority():
    source = build(inputs())
    payload = source.to_payload()
    for flag, value in payload["authority"].items():
        if flag not in {"source_only", "latest_revised_only"}:
            assert value in (False, 0)
    assert "rows" not in payload and "cells" not in payload
    parts = list(source.iter_private_parts())
    assert len(parts) == 3 and all(type(item) is bytes for item in parts)


def daily_report(plan, ordinal):
    timestamp = local_midnight_milliseconds(plan.sessions()[ordinal - 1] + "T00:00:00")
    raw = envelope(ROW.replace("1641254400000", str(timestamp)))
    return grouped.qualify_grouped_response(plan, ordinal, raw=raw, raw_sha256=hash_bytes(raw),
        request_sha256=hash_payload(grouped.request_descriptor(plan, ordinal)),
        started_at="2026-10-14T01:00:00Z", received_at="2026-10-14T01:00:01Z")


def test_daily_report_side_stream_is_lazy_not_a_native_or_USD_join():
    plan = grouped.freeze_grouped_session_plan(("2022-01-03", "2022-01-04"), calendar_sha256="a" * 64)
    seen = []
    def reports():
        for ordinal in (1, 2):
            seen.append(ordinal)
            yield daily_report(plan, ordinal)
    result = compiler.iter_daily_grouped_source_reports(plan, reports())
    first = next(result)
    assert seen == [1]
    assert first["native_price_binding"] is first["USD_currency_binding"] is None
    assert first["authority"]["actual_input_execution_admitted"] is False
    assert len(list(result)) == 1 and seen == [1, 2]


@pytest.mark.parametrize("kind", ["missing", "extra", "wrong_order", "wrong_plan"])
def test_daily_stream_custody_and_order_refused(kind):
    plan = grouped.freeze_grouped_session_plan(("2022-01-03", "2022-01-04"), calendar_sha256="a" * 64)
    first, second = daily_report(plan, 1), daily_report(plan, 2)
    if kind == "missing":
        reports = (first,)
    elif kind == "extra":
        reports = (first, second, second)
    elif kind == "wrong_order":
        reports = (second, first)
    else:
        other = grouped.freeze_grouped_session_plan(plan.sessions(), calendar_sha256="a" * 64)
        reports = (daily_report(other, 1), second)
    with pytest.raises(compiler.CompactSourceError):
        list(compiler.iter_daily_grouped_source_reports(plan, reports))
