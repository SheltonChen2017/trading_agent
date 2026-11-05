"""Typed parallel compilation and unchanged serial control; fabricated only."""
import importlib.util
from pathlib import Path
import sys
import types

import pytest

from data.hashing import hash_bytes
import research.short_interest_etf.native_parallel_reported_count_registry as parallel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


fixtures = module("compact_parallel_compiler_fixtures", HERE / "test_short_interest_compact_native_source.py")


import research.short_interest_etf.compact_native_source as proposed

def serial_control():
    # Causal control removes only the new typed-parallel bridge. All original
    # serial formula bytes and canonical module types remain identical.
    path = HERE.parent / "research" / "short_interest_etf" / "compact_native_source.py"
    raw = path.read_text(encoding="utf-8")
    # The registry tuple gained recovery.CountRecoveryRegistry at 71c2e7a; the
    # control drops only the typed-parallel member and only its lineage block.
    before = ("and type(registry) in (anchors.NativeReportedCountRegistry, parallel.ParallelReportedCountRegistry,\n"
              "                                   recovery.CountRecoveryRegistry)")
    assert raw.count(before) == 1
    raw = raw.replace(before, "and type(registry) in (anchors.NativeReportedCountRegistry, recovery.CountRecoveryRegistry)")
    start = raw.index("    if type(registry) is parallel.ParallelReportedCountRegistry:\n")
    end = raw.index("    elif type(registry) is recovery.CountRecoveryRegistry:\n", start)
    raw = raw[:start] + "    if False:\n        pass\n" + raw[end:]
    value = types.ModuleType("serial_compiler_parallel_control")
    sys.modules[value.__name__] = value
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value

legacy = serial_control()

DATES = ("2022-01-04", "2022-04-14", "2022-07-14")


def inputs(*, inverted=True, partial=False):
    rows = [{"ticker": "SYN", "settlement_date": day, "short_interest": (index + 1) * 9007199254740993}
            for index, day in enumerate(DATES)]
    matrix, pages = fixtures.source_pages(rows)
    source = parallel.reported.build_native_reported_anchor_plan(matrix,
            tuple(fixtures.fixtures.identity(day) for day in DATES), fixtures.fixtures.actions(), fixtures.fixtures.dictionary())
    captures, receipts = [], []
    for ordinal, query in enumerate(source.query_plan.iter_queries(), 1):
        second = (10, 8, 9)[ordinal - 1] if inverted else 8 + ordinal
        received = f"2026-10-14T01:00:{second:02d}Z"
        capture = fixtures.fixtures.response(query, receipt=received)
        captures.append(capture)
        receipts.append({"query_ordinal": ordinal, "request_sha256": query.to_payload()["request_sha256"],
                "started_at": f"2026-10-14T01:00:{ordinal:02d}Z", "received_at": received,
                "http_attempted": True, "http_status": 200, "body_observed": True,
                "raw_path": f"query-{ordinal:08d}.raw", "raw_sha256": hash_bytes(capture._raw),
                "raw_bytes": len(capture._raw), "content_type": "application/json", "code": "received"})
    count_plan = parallel.parallel.freeze_parallel_count_plan(source.query_plan,
            maximum_total_response_bytes=3 * parallel.parallel.MAXIMUM_RESPONSE_BYTES)
    if partial:
        captures, receipts = captures[:1], receipts[:1]
    inventory = parallel.parallel.seal_parallel_inventory(count_plan, tuple(receipts),
            started_at="2026-10-14T01:00:00Z", completed_at="2026-10-14T01:01:00Z", halted=partial)
    registry = parallel.qualify_parallel_reported_counts(source, captures, inventory=inventory)
    return matrix, registry, pages, fixtures.calendar_fixtures.qualified(settlements=DATES)


def test_original_exact_serial_compiler_refuses_the_parallel_wrapper_until_explicit_extension():
    with pytest.raises(legacy.CompactSourceError, match="exact_sealed"):
        legacy.compile_native_source(*inputs())


def test_typed_parallel_compilation_retains_wrapper_digest_full_receipt_lineage_and_clocks():
    values = inputs()
    registry = values[1]
    result = proposed.compile_native_source(*values)
    header, cells = result.header(), list(result.iter_cells())
    assert result._registry is registry
    assert header["count_registry_sha256"] == registry.sha256 != registry._registry.sha256
    assert header["parallel_count_lineage"]["parallel_inventory_sha256"] == registry._inventory.sha256
    assert header["parallel_count_lineage"]["parallel_started_at"] == "2026-10-14T01:00:00Z"
    assert header["parallel_count_lineage"]["parallel_completed_at"] == "2026-10-14T01:01:00Z"
    assert header["parallel_count_lineage"]["full_provider_coverage_admitted"] is False
    assert [cell["same_class_denominator_reference"]["actual_receipt_UTC"] for cell in cells] == [
            "2026-10-14T01:00:10Z", "2026-10-14T01:00:08Z", "2026-10-14T01:00:09Z"]
    assert all(cell["same_class_denominator_reference"]["registry_sha256"] == registry.sha256 for cell in cells)
    assert [cell["source_short_quantity"] for cell in cells] == [9007199254740993 * n for n in (1, 2, 3)]
    with pytest.raises(proposed.CompactSourceError, match="not_execution_admission"):
        result.execution_inputs()


def test_serial_compiler_output_bytes_and_formulas_are_unchanged():
    matrix, parallel_registry, pages, calendar = inputs(inverted=False)
    serial = parallel_registry._registry
    expected = legacy.compile_native_source(matrix, serial, pages, calendar)
    actual = proposed.compile_native_source(matrix, serial, pages, calendar)
    assert expected.sha256 == actual.sha256
    assert tuple(expected.iter_private_parts()) == tuple(actual.iter_private_parts())
    assert list(expected.iter_cells()) == list(actual.iter_cells())
    assert "parallel_count_lineage" not in actual.header()


def test_partial_registry_compiles_missing_count_refusals_without_full_coverage_default():
    result = proposed.compile_native_source(*inputs(partial=True))
    cells, lineage = list(result.iter_cells()), result.header()["parallel_count_lineage"]
    assert lineage["parallel_unstarted_tickets"] == 2 and lineage["complete_frozen_request_sequence"] is False
    assert cells[0]["same_class_denominator_reference"] is not None
    assert all(cell["same_class_denominator_reference"] is None and cell["registry_refusal_reasons"] for cell in cells[1:])


@pytest.mark.parametrize("invalid", [True, False, {}, None, "parallel"])
def test_bool_dict_or_untyped_registry_cannot_enter_compiler(invalid):
    matrix, registry, pages, calendar = inputs()
    with pytest.raises(proposed.CompactSourceError, match="exact_sealed"):
        proposed.compile_native_source(matrix, invalid, pages, calendar)


def test_reflected_parallel_inventory_change_during_replay_refuses_before_compiled_output():
    matrix, registry, pages, calendar = inputs()
    def changed():
        yield pages[0]
        object.__setattr__(registry._inventory, "_json", "{}")
        yield from pages[1:]
    with pytest.raises(parallel.parallel.ParallelCountRefusal):
        proposed.compile_native_source(matrix, registry, changed(), calendar)


def test_parallel_compatibility_fields_are_guarded_immutable_read_only_projections():
    registry = inputs()[1]
    assert registry._plan is registry._registry._plan and registry._records is registry._registry._records
    assert registry._flags is registry._registry._flags
    registry._guard()
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(registry, "_records", ())
