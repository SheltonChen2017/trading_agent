"""Independent root audit of fabricated receipt contracts; no actual I/O."""
import pytest
import test_short_interest_native_parallel_count_registry as f


def test_known_200_discarded_body_remains_missing_not_invented_provider_capture():
    source, captures, receipts, inventory = f.example()
    receipts = receipts[:2]
    receipts[1].update(body_observed=False, raw_path=None, raw_sha256=None,
                       raw_bytes=None, content_type=None, code="material_request_refused")
    retained = f.m.parallel.seal_parallel_inventory(inventory._plan, tuple(receipts),
                started_at=f.START, completed_at=f.END, halted=True)
    result = f.m.qualify_parallel_reported_counts(source, captures[:1], inventory=retained)
    rows = list(result.iter_cells())
    assert rows[0]["same_class_count"] is not None
    assert all(row["same_class_count"] is None and row["refusal_reasons"] for row in rows[1:])
    assert result.to_payload()["complete_frozen_request_sequence"] is False


def test_known_HTTP_status_cannot_be_claimed_without_HTTP_invocation():
    source, captures, receipts, inventory = f.example()
    receipts = receipts[:1]
    receipts[0].update(http_attempted=False, http_status=403, body_observed=False,
                       raw_path=None, raw_sha256=None, raw_bytes=None,
                       content_type=None, code="material_request_refused")
    with pytest.raises(f.m.parallel.ParallelCountRefusal, match="HTTP_status_without_invocation"):
        f.m.parallel.seal_parallel_inventory(inventory._plan, tuple(receipts),
                     started_at=f.START, completed_at=f.END, halted=True)


def test_parallel_replay_proves_whole_page_reservation_at_every_START():
    source, captures, receipts, inventory = f.example()
    one_page = f.m.parallel.freeze_parallel_count_plan(source.query_plan,
                   maximum_total_response_bytes=f.m.parallel.MAXIMUM_RESPONSE_BYTES)
    with pytest.raises(f.m.parallel.ParallelCountRefusal, match="whole_page_reservation"):
        f.m.parallel.seal_parallel_inventory(one_page, tuple(receipts),
                     started_at=f.START, completed_at=f.END, halted=False)
