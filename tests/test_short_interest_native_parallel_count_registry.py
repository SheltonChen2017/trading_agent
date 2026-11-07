"""Causal typed-clock regressions, fabricated source claims only."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from data.hashing import hash_bytes
from research.short_interest_etf import native_dated_class_reference as references
import research.short_interest_etf.native_parallel_reported_count_registry as m

SPEC = importlib.util.spec_from_file_location("parallel_registry_anchor_fixtures",
        Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
fixtures = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fixtures
SPEC.loader.exec_module(fixtures)
START = "2026-10-14T01:00:00Z"
END = "2026-10-14T01:01:00Z"
DATES = ("2023-01-13", "2023-04-14", "2023-07-14")


def plan(dates=DATES, *, classes=None):
    classes = classes or {}
    return m.reported.build_native_reported_anchor_plan(fixtures.matrix(tuple(("SYN", day) for day in dates)),
            tuple(fixtures.identity(day, class_id=classes.get(day, fixtures.CLASS)) for day in dates),
            fixtures.actions(), fixtures.dictionary())


def receipt(query, capture, *, ordinal, status=200, began=None, received=None):
    meta = json.loads(capture._meta) if capture is not None else None
    observed = status == 200
    return {"query_ordinal": ordinal, "request_sha256": query.to_payload()["request_sha256"],
            "started_at": began or f"2026-10-14T01:00:{ordinal:02d}Z",
            "received_at": received or meta["received_at"], "http_attempted": True,
            "http_status": status, "body_observed": observed,
            "raw_path": f"query-{ordinal:08d}.raw" if observed else None,
            "raw_sha256": meta["raw_sha256"] if observed else None,
            "raw_bytes": len(capture._raw) if observed else None,
            "content_type": "application/json" if observed else None,
            "code": "received" if observed else "HTTP_404_body_unobserved" if status == 404 else "material_request_refused"}


def example(*, inverted=True, dates=DATES, classes=None):
    source = plan(dates, classes=classes)
    captures, receipts = [], []
    tickets = tuple(source.query_plan.iter_queries())
    seconds = (10, 8, 9) if inverted else (8, 9, 10)
    for ordinal, query in enumerate(tickets, 1):
        at = query.to_payload()["query_asof_date"]
        capture = fixtures.response(query, class_id=(classes or {}).get(at),
                receipt=f"2026-10-14T01:00:{seconds[ordinal - 1]:02d}Z")
        captures.append(capture)
        receipts.append(receipt(query, capture, ordinal=ordinal))
    frozen = m.parallel.freeze_parallel_count_plan(source.query_plan,
            maximum_total_response_bytes=len(tickets) * m.parallel.MAXIMUM_RESPONSE_BYTES)
    inventory = m.parallel.seal_parallel_inventory(frozen, tuple(receipts), started_at=START, completed_at=END, halted=False)
    return source, captures, receipts, inventory


def test_valid_parallel_clock_inversion_stays_real_serial_branch_still_refuses():
    source, captures, receipts, inventory = example()
    with pytest.raises(m.reported.AnchorError, match="chronology"):
        m.reported.qualify_native_reported_counts(source, captures)
    result = m.qualify_parallel_reported_counts(source, captures, inventory=inventory)
    assert [record["actual_receipt_UTC"] for record in result.iter_records()] == [item["received_at"] for item in receipts]
    assert [record["parallel_request_started_at"] for record in result.iter_records()] == [item["started_at"] for item in receipts]
    assert all(not row["refusal_reasons"] for row in result.iter_cells())
    assert result.to_payload()["parallel_inventory_sha256"] == inventory.sha256
    assert result.to_payload()["full_provider_coverage_admitted"] is False
    assert all(value is False for key, value in result.to_payload()["authority"].items() if key.endswith("admitted"))


def test_monotone_parallel_facts_preserve_exact_serial_underlying_economics():
    source, captures, receipts, inventory = example(inverted=False)
    serial = m.reported.qualify_native_reported_counts(source, captures)
    result = m.qualify_parallel_reported_counts(source, captures, inventory=inventory)
    assert result._registry.sha256 == serial.sha256
    assert tuple(result._registry.iter_parts()) == tuple(serial.iter_parts())
    assert result.sha256 != serial.sha256  # Parallel transport provenance is additionally bound.


@pytest.mark.parametrize("invalid", [True, False, {}, "yes", None])
def test_no_clock_or_completion_boolean_can_bypass_serial_guard(invalid):
    source, captures, receipts, inventory = example()
    with pytest.raises(m.ParallelRegistryRefusal):
        m.qualify_parallel_reported_counts(source, captures, inventory=invalid)


def test_same_digest_foreign_plan_instance_cannot_rebind_observed_receipts():
    source, captures, receipts, inventory = example()
    foreign = plan()
    assert foreign.query_plan.sha256 == source.query_plan.sha256
    with pytest.raises(m.ParallelRegistryRefusal, match="instance"):
        m.qualify_parallel_reported_counts(foreign, captures, inventory=inventory)


@pytest.mark.parametrize("change", ["omit", "duplicate", "reorder", "body", "receipt_clock"])
def test_every_observed_capture_once_and_exact_body_clock_binding(change):
    source, captures, receipts, inventory = example()
    if change == "omit":
        captures.pop()
    elif change == "duplicate":
        captures.append(captures[-1])
    elif change == "reorder":
        captures.reverse()
    elif change == "body":
        captures[0] = fixtures.response(captures[0]._query, count=101, receipt=receipts[0]["received_at"])
    else:
        captures[0] = fixtures.response(captures[0]._query, receipt="2026-10-14T01:00:07Z")
    with pytest.raises((m.ParallelRegistryRefusal, m.parallel.ParallelCountRefusal)):
        m.qualify_parallel_reported_counts(source, captures, inventory=inventory)


def test_partial_unstarted_or_transport_slots_are_missing_not_synthetic_404_or_full_coverage():
    source, captures, receipts, inventory = example()
    receipts = receipts[:2]
    receipts[1].update(http_status=None, body_observed=False, raw_path=None, raw_sha256=None,
            raw_bytes=None, content_type=None, code="material_request_refused")
    partial = m.parallel.seal_parallel_inventory(inventory._plan, tuple(receipts), started_at=START, completed_at=END, halted=True)
    result = m.qualify_parallel_reported_counts(source, captures[:1], inventory=partial)
    header, cells = result.to_payload(), list(result.iter_cells())
    assert header["planned_anchor_count"] == 3 and header["captured_anchor_count"] == 1
    assert header["parallel_attempts_started"] == 2 and header["parallel_unstarted_tickets"] == 1
    assert header["complete_frozen_request_sequence"] is False and header["parallel_halted"] is True
    assert len(list(result.iter_records())) == 1
    assert cells[0]["same_class_count"] is not None
    assert all(cell["same_class_count"] is None and cell["refusal_reasons"] for cell in cells[1:])


def test_observed404_is_negative_source_receipt_not_provider_empty_body():
    source, captures, receipts, inventory = example()
    query = captures[1]._query
    captures[1] = references.capture_native_dated_class_response(query, raw=b"", raw_sha256=hash_bytes(b""),
            request_sha256=query.to_payload()["request_sha256"], received_at=receipts[1]["received_at"],
            http_status=404, content_type="", body_observed=False)
    receipts[1] = receipt(query, captures[1], ordinal=2, status=404)
    negative = m.parallel.seal_parallel_inventory(inventory._plan, tuple(receipts), started_at=START, completed_at=END, halted=False)
    result = m.qualify_parallel_reported_counts(source, captures, inventory=negative)
    records, cells = list(result.iter_records()), list(result.iter_cells())
    assert records[1]["source_origin"]["body_observed"] is False and records[1]["same_class_count"] is None
    assert records[1]["refusal_reasons"] and cells[1]["same_class_count"] is None


def test_class_transition_does_not_retroactively_poison_prior_dated_count():
    dates = ("2023-01-13", "2023-01-31")
    source, captures, receipts, inventory = example(dates=dates, classes={dates[1]: fixtures.NEXT_CLASS})
    result = m.qualify_parallel_reported_counts(source, captures, inventory=inventory)
    cells = list(result.iter_cells())
    assert all(not cell["refusal_reasons"] for cell in cells)
    assert cells[0]["share_class_figi"] == fixtures.CLASS and cells[1]["share_class_figi"] == fixtures.NEXT_CLASS


@pytest.mark.parametrize("field", ["_registry", "_inventory", "_digest", "_anchor"])
def test_parallel_registry_seal_cannot_be_reflected_into_clock_or_lineage_bypass(field):
    source, captures, receipts, inventory = example()
    result = m.qualify_parallel_reported_counts(source, captures, inventory=inventory)
    object.__setattr__(result, field, object())
    with pytest.raises(m.ParallelRegistryRefusal):
        result.to_payload()


def test_iterating_registry_does_not_rescan_every_receipt_per_record(monkeypatch):
    source, captures, receipts, inventory = example()
    result = m.qualify_parallel_reported_counts(source, captures, inventory=inventory)
    calls = []
    original = m.parallel.ParallelCountInventory.iter_receipts
    def counted(self):
        calls.append(True)
        yield from original(self)
    monkeypatch.setattr(m.parallel.ParallelCountInventory, "iter_receipts", counted)
    assert len(list(result.iter_records())) == 3
    assert len(calls) <= 1
