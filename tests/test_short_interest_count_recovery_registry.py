"""Small fabricated lineage union; no provider rows, sockets or Keychain."""
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import socket
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_count_recovery_registry as recovery

SPEC = importlib.util.spec_from_file_location("count_recovery_registry_fabricated_sources",
    Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
fixtures = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fixtures
SPEC.loader.exec_module(fixtures)


def stamp(second):
    return (datetime(2026, 10, 24, tzinfo=timezone.utc) + timedelta(seconds=second)).isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("fabricated count registry must not use network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def receipt(query, raw, ordinal, start, *, negative=False, missing=False):
    observed = not negative and not missing
    return {"query_ordinal": ordinal, "request_sha256": query.to_payload()["request_sha256"],
        "started_at": stamp(start), "received_at": stamp(start + 1),
        "http_attempted": not negative, "http_status": None if negative else 404 if missing else 200,
        "body_observed": observed, "raw_path": f"query-{ordinal:08d}.raw" if observed else None,
        "raw_sha256": hash_bytes(raw) if observed else None, "raw_bytes": len(raw) if observed else None,
        "content_type": "application/json" if observed else None,
        "code": "material_request_refused" if negative else "HTTP_404_body_unobserved" if missing else "received"}


def example(monkeypatch, *, missing=False, child_halted=False):
    # Only the test domain is reduced: production has no policy override or
    # PENDING pins and always requires all 81,875 original positions.
    dates = tuple((date(2023, 1, 1) + timedelta(days=i)).isoformat() for i in range(50))
    class_ids = tuple(fixtures.CLASS if i % 2 else fixtures.NEXT_CLASS for i in range(49))
    class_ids += (class_ids[-1],)  # One later cell carries the last real child anchor.
    source = fixtures.plan(dates, reports=tuple(fixtures.identity(at, class_id=class_id)
        for at, class_id in zip(dates, class_ids)))
    queries = tuple(source.query_plan.iter_queries())
    assert len(queries) == 49
    mapping = ((47, 47), (49, 49))
    monkeypatch.setattr(recovery, "ORIGINAL_COUNT", 49)
    monkeypatch.setattr(recovery, "ANCHOR_PLAN_SHA256", source.sha256)
    monkeypatch.setattr(recovery, "MAPPING_SHA256", hash_payload(mapping))
    protocol_raw = b'{"schema":"fabricated-count-recovery-protocol"}'
    monkeypatch.setattr(recovery, "RECOVERY_PROTOCOL_SHA256", hash_bytes(protocol_raw))
    parent_raw, parent_receipts = {}, []
    for ordinal, query in enumerate(queries[:48], 1):
        negative = ordinal == 47
        raw = b"" if negative else fixtures.response(query, class_id=class_ids[ordinal - 1])._raw
        entry = receipt(query, raw, ordinal, ordinal * 2, negative=negative)
        parent_receipts.append(entry)
        if not negative:
            parent_raw[entry["raw_path"]] = raw
    charged = sum(len(raw) for raw in parent_raw.values()) + recovery.parallel.MAXIMUM_RESPONSE_BYTES
    maximum = charged + 2 * recovery.parallel.MAXIMUM_RESPONSE_BYTES
    monkeypatch.setattr(recovery, "PARENT_CHARGED_BYTES", charged)
    monkeypatch.setattr(recovery, "MAXIMUM_CUMULATIVE_BYTES", maximum)
    parent_plan = recovery.parallel.freeze_parallel_count_plan(source.query_plan,
        maximum_total_response_bytes=maximum)
    monkeypatch.setattr(recovery, "PARENT_PLAN_SHA256", parent_plan.sha256)
    parent = recovery.parallel.seal_parallel_inventory(parent_plan, tuple(parent_receipts),
        started_at=stamp(0), completed_at=stamp(100), halted=True)
    for ordinal, entry in enumerate(parent_receipts, 1):
        parent_raw[f"query-{ordinal:08d}.started.json"] = b"{}"
        parent_raw[f"query-{ordinal:08d}.received.json"] = canonical_json(entry).encode()
    for name in ("protocol.private.json", "started.json", "run.refused.json"):
        parent_raw[name] = b"{}"
    child_queries = recovery.references.freeze_native_class_query_plan(source._matrix,
        mode="explicit_anchors", selected_query_ordinals=(47, 49))
    child_plan = recovery.parallel.freeze_parallel_count_plan(child_queries,
        maximum_total_response_bytes=maximum - charged)
    child_raw, child_receipts = {}, []
    for ordinal, query in enumerate(child_queries.iter_queries(), 1):
        raw = fixtures.response(query, class_id=class_ids[mapping[ordinal - 1][0] - 1])._raw
        entry = receipt(query, raw, ordinal, 102 + ordinal * 2, missing=missing and ordinal == 1)
        child_receipts.append(entry)
        if entry["body_observed"]:
            child_raw[entry["raw_path"]] = raw
    if child_halted:
        child_receipts = child_receipts[:1]
    child = recovery.parallel.seal_parallel_inventory(child_plan, tuple(child_receipts),
        started_at=stamp(101), completed_at=stamp(110), halted=child_halted)
    marker = {"schema": "si-manual-count-recovery-child-completed-v1", "completed_at": stamp(110),
        "child_inventory_sha256": child.sha256, "child_starts": len(child_receipts),
        "cumulative_starts": 48 + len(child_receipts), "parent_inventory_sha256": parent.sha256,
        "original_position_47_negative_retained": True, "child_complete_source_only": True,
        "original_round_complete": False, "provisional_until_postpublication_remote_check": True,
        "authority": recovery._driver_authority()}
    closure = {"schema": "si-manual-count-recovery-observed-closure-v1",
        "protocol_sha256": recovery.RECOVERY_PROTOCOL_SHA256,
        "audit_started_at": stamp(111), "audit_ended_at": stamp(112),
        "matching_remote_observed_equal": True, "child_marker_sha256": hash_payload(marker),
        "child_inventory_sha256": child.sha256, "original_round_complete": False,
        "source_admitted": False, "ready_for_backtest": False, "authority": recovery._driver_authority()}
    child_raw["protocol.private.json"] = protocol_raw
    child_raw["child.inventory.private.json"] = canonical_json(child.to_payload()).encode()
    child_raw["started.json"] = canonical_json({"schema": "si-manual-count-recovery-start-v1",
        "started_at": stamp(101), "parent_inventory_sha256": parent.sha256,
        "child_plan_sha256": child_plan.sha256, "code_head": "a" * 40,
        "code_identity_sha256": "b" * 64, "protocol_sha256": recovery.RECOVERY_PROTOCOL_SHA256,
        "authority": recovery._driver_authority()}).encode()
    diagnostics = []
    for ordinal, (entry, query) in enumerate(zip(child_receipts, child_queries.iter_queries()), 1):
        ticket = query.to_payload()
        prefix = f"query-{ordinal:08d}"
        child_raw[prefix + ".started.json"] = canonical_json({
            "schema": "si-manual-count-recovery-request-start-v1", "query_ordinal": ordinal,
            "original_count_position": mapping[ordinal - 1][0], "request": ticket["request"],
            "request_sha256": ticket["request_sha256"], "started_at": entry["started_at"],
            "child_plan_sha256": child_plan.sha256, "code_head": "a" * 40,
            "whole_page_bytes_reserved": recovery.parallel.MAXIMUM_RESPONSE_BYTES}).encode()
        child_raw[prefix + ".received.json"] = canonical_json(entry).encode()
        if not entry["body_observed"]:
            diagnostic = {"query_ordinal": ordinal, "failure_stage": "transport", "http_attempted": True,
                "http_status": 404, "observed_receipt_at": entry["received_at"],
                "protocol_sha256": recovery.RECOVERY_PROTOCOL_SHA256}
            child_raw[prefix + ".diagnostic.private.json"] = canonical_json(diagnostic).encode()
            diagnostics.append(diagnostic)
    child_raw["diagnostics.inventory.private.json"] = canonical_json(diagnostics).encode()
    reads, checks = [], []
    def read(segment, values):
        def bound(name, maximum_bytes):
            assert 0 < maximum_bytes <= 64 * 1024 * 1024
            reads.append((segment, name))
            return values[name]
        return bound
    args = {"source": source, "parent_inventory": parent, "child_inventory": child,
        "original_to_matrix_mapping": mapping, "parent_read": read("parent", parent_raw),
        "child_read": read("child", child_raw), "custody": lambda: checks.append(True)}
    def controls():
        child_raw["child.completed.json"] = canonical_json(marker).encode()
        child_raw["round.closed.qualified.json"] = canonical_json(closure).encode()
        def manifest(values):
            return canonical_json([{"name": name, "sha256": hash_bytes(raw), "bytes": len(raw)}
                for name, raw in sorted(values.items())]).encode()
        old_manifest, new_manifest = manifest(parent_raw), manifest(child_raw)
        monkeypatch.setattr(recovery, "PARENT_MANIFEST_SHA256", hash_bytes(old_manifest))
        return {"child_marker_raw": canonical_json(marker).encode(),
            "expected_child_marker_sha256": hash_payload(marker),
            "child_closure_raw": canonical_json(closure).encode(),
            "expected_child_closure_sha256": hash_payload(closure),
            "parent_manifest_raw": old_manifest, "child_manifest_raw": new_manifest,
            "expected_child_manifest_sha256": hash_bytes(new_manifest),
            "child_names": lambda: tuple(sorted(child_raw))}
    return args, controls, marker, closure, parent_raw, child_raw, reads, checks


def test_complete_union_preserves_parent_negative_and_new_real_clock(monkeypatch):
    args, controls, marker, closure, parent_raw, child_raw, reads, checks = example(monkeypatch)
    result = recovery.qualify_count_recovery(**args, **controls())
    rows, cells, header = list(result.iter_records()), list(result.iter_cells()), result.to_payload()
    assert len(rows) == 49 and len(cells) == 50 and sum(name.endswith(".raw") for _, name in reads) == 49
    assert [row["original_count_position"] for row in rows] == list(range(1, 50))
    assert rows[46]["source_segment"] == "child" and rows[46]["segment_query_ordinal"] == 1
    assert rows[47]["source_segment"] == "parent" and rows[48]["segment_query_ordinal"] == 2
    assert rows[46]["actual_receipt_UTC"] == stamp(105)
    assert header["original_negative_receipt"]["http_status"] is None
    assert header["original_negative_receipt"]["http_attempted"] is False
    assert header["original_round_complete"] is False and header["complete_composite_source_sequence"] is True
    assert header["cumulative_starts"] == 50 and header["cumulative_http_invocations"] == 49
    assert all(cell["same_class_count"]["numerator"] == 100 and not cell["refusal_reasons"] for cell in cells)
    assert not header["full_provider_coverage_admitted"] and not header["authority"]["ready_for_backtest"]
    assert len(set(reads)) == len(reads) and checks


@pytest.mark.parametrize("mutation", ["omit", "duplicate", "reorder", "matrix_ordinal", "bool"])
def test_mapping_cannot_omit_duplicate_or_rebind_originals(monkeypatch, mutation):
    args, controls, *_ = example(monkeypatch)
    mapping = args["original_to_matrix_mapping"]
    args["original_to_matrix_mapping"] = {"omit": mapping[:1], "duplicate": (mapping[0], mapping[0]),
        "reorder": mapping[::-1], "matrix_ordinal": ((47, 48), mapping[1]), "bool": ((True, 47), mapping[1])}[mutation]
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="mapping"):
        recovery.qualify_count_recovery(**args, **controls())


@pytest.mark.parametrize("field,value", [("original_round_complete", True),
    ("child_complete_source_only", False), ("parent_inventory_sha256", "0" * 64)])
def test_rehashed_marker_still_must_match_exact_typed_lineage(monkeypatch, field, value):
    args, controls, marker, closure, *_ = example(monkeypatch)
    marker[field] = value
    closure["child_marker_sha256"] = hash_payload(marker)
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="marker"):
        recovery.qualify_count_recovery(**args, **controls())


@pytest.mark.parametrize("field,value", [("matching_remote_observed_equal", False),
    ("source_admitted", True), ("protocol_sha256", "0" * 64), ("unexpected", True),
    ("audit_started_at", stamp(109))])
def test_closed_hash_is_not_a_semantic_or_temporal_bypass(monkeypatch, field, value):
    args, controls, marker, closure, *_ = example(monkeypatch)
    closure[field] = value
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="closure"):
        recovery.qualify_count_recovery(**args, **controls())


def test_final_raw_tamper_refuses_before_any_registry_or_last_yield(monkeypatch):
    args, controls, marker, closure, parent_raw, child_raw, reads, checks = example(monkeypatch)
    child_raw["query-00000002.raw"] += b" "
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="original_response"):
        recovery.qualify_count_recovery(**args, **controls())
    assert reads[-1] == ("child", "query-00000002.raw")


@pytest.mark.parametrize("name", ["round.closed.refused.json", "run.refused.json", "unknown.private.json"])
def test_any_refused_or_unknown_sibling_blocks_even_qualified_marker(monkeypatch, name):
    args, controls, marker, closure, parent_raw, child_raw, *_ = example(monkeypatch)
    frozen = controls()
    child_raw[name] = b"{}"
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="membership"):
        recovery.qualify_count_recovery(**args, **frozen)


def test_final_membership_is_verified_before_constructor_returns(monkeypatch):
    args, controls, marker, closure, parent_raw, child_raw, *_ = example(monkeypatch)
    frozen, real = controls(), args["child_read"]
    def drift(name, maximum):
        raw = real(name, maximum)
        if name == "query-00000002.raw":
            child_raw["round.closed.refused.json"] = b"{}"
        return raw
    args["child_read"] = drift
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="membership"):
        recovery.qualify_count_recovery(**args, **frozen)


def test_closed404_is_negative_not_an_older_count_fallback(monkeypatch):
    args, controls, *_ = example(monkeypatch, missing=True)
    result = recovery.qualify_count_recovery(**args, **controls())
    rows, cells = list(result.iter_records()), list(result.iter_cells())
    assert rows[46]["source_origin"]["body_observed"] is False
    assert rows[46]["same_class_count"] is None and rows[46]["refusal_reasons"]
    assert cells[46]["same_class_count"] is None and cells[46]["refusal_reasons"]
    assert cells[45]["same_class_count"] is not None and cells[47]["same_class_count"] is not None


def test_refused_or_partial_child_does_not_become_complete(monkeypatch):
    args, controls, *_ = example(monkeypatch, child_halted=True)
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="incomplete"):
        recovery.qualify_count_recovery(**args, **controls())


@pytest.mark.parametrize("field", ["_source", "_parent", "_child", "_mapping", "_records", "_header", "_digest", "_custody", "_anchor"])
def test_registry_binding_cannot_be_replaced_after_qualification(monkeypatch, field):
    args, controls, *_ = example(monkeypatch)
    result = recovery.qualify_count_recovery(**args, **controls())
    object.__setattr__(result, field, object())
    with pytest.raises(recovery.CountRecoveryRegistryRefusal, match="sealed"):
        result.to_payload()


def test_custody_drift_after_factory_stops_outward_iteration(monkeypatch):
    args, controls, *_ = example(monkeypatch)
    changed = False
    def custody():
        if changed:
            raise ValueError("fabricated custody drift")
    args["custody"] = custody
    result = recovery.qualify_count_recovery(**args, **controls())
    changed = True
    with pytest.raises(ValueError, match="custody drift"):
        next(result.iter_records())


def compiled_example(monkeypatch, *, missing=False):
    spec = importlib.util.spec_from_file_location("count_recovery_compiler_fabricated_sources",
        Path(__file__).with_name("test_short_interest_compact_native_source.py"))
    inputs = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = inputs
    spec.loader.exec_module(inputs)
    args, controls, *_ = example(monkeypatch, missing=missing)
    registry = recovery.qualify_count_recovery(**args, **controls())
    matrix = args["source"]._matrix
    dates = tuple(matrix.header()["settlements"])
    recreated, pages = inputs.source_pages([
        {"ticker": "SYN", "settlement_date": at, "short_interest": 1} for at in dates])
    assert recreated.sha256 == matrix.sha256  # Replay bytes, not a foreign matrix object.
    calendar = inputs.calendar_fixtures.qualified(settlements=dates)
    return inputs.compiler, matrix, registry, pages, calendar


def test_compiler_exhausts_current_and_prior_recovery_references_without_cast(monkeypatch):
    compiler, matrix, registry, pages, calendar = compiled_example(monkeypatch)
    source = compiler.compile_native_source(matrix, registry, iter(pages), calendar)
    rows, header = list(source.iter_cells()), source.header()
    assert len(rows) == 50 and header["count_registry_sha256"] == registry.sha256
    assert header["count_recovery_lineage"]["original_round_complete"] is False
    assert header["count_recovery_lineage"]["complete_composite_source_sequence"] is True
    assert "parallel_count_lineage" not in header
    last = rows[-1]
    for ref in (last["same_class_denominator_reference"], last["immediate_prior_denominator_reference"]):
        assert ref["source_count"]["numerator"] == 100
        assert ref["count_recovery_reference"] == {
            "original_count_position": 49, "source_segment": "child",
            "segment_query_ordinal": 2, "source_epoch": recovery.SOURCE_EPOCH}
    assert rows[46]["same_class_denominator_reference"]["count_recovery_reference"]["original_count_position"] == 47
    assert not header["authority"]["source_admitted"] and not header["authority"]["actual_input_execution_admitted"]
    with pytest.raises(compiler.CompactSourceError, match="not_execution_admission"):
        source.execution_inputs()


def test_compiler_preserves_recovery404_and_rejects_unsealed_or_foreign_matrix(monkeypatch):
    compiler, matrix, registry, pages, calendar = compiled_example(monkeypatch, missing=True)
    rows = list(compiler.compile_native_source(matrix, registry, pages, calendar).iter_cells())
    assert rows[46]["same_class_denominator_reference"] is None and rows[46]["registry_refusal_reasons"]
    assert rows[45]["same_class_denominator_reference"] is not None
    with pytest.raises(compiler.CompactSourceError, match="exact_sealed"):
        compiler.compile_native_source(matrix, registry.to_payload(), pages, calendar)
    other = fixtures.matrix([("SYN", at) for at in matrix.header()["settlements"]])
    assert other.sha256 == matrix.sha256
    with pytest.raises(compiler.CompactSourceError, match="matrix_lineage"):
        compiler.compile_native_source(other, registry, pages, calendar)
