"""Synthetic metadata only: never opens the retained index or a licensed page."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261028_massive_inventory as m


def synthetic_index():
    # Deliberately synthetic metadata, not an imitation of the immutable hash.
    pages, scopes = [], []
    wire_base, wire_extra = divmod(255130379, 386)
    for window_index, window in enumerate(m.WINDOWS):
        count = 6 if window_index < 16 else 5
        rows = 0
        for page in range(count):
            number = len(pages) + 1
            rows += 904 + int(number <= 74)
            prefix = f"request.{number:04}"
            wire = wire_base + int(number <= wire_extra)
            pages.append({"request_index": number, "provider": "massive", "dataset": "ratings",
                "window": list(window), "page": page, "http_status": 200,
                "wire_file": prefix + ".wire.json", "wire_sha256": "a" * 64,
                "wire_bytes": wire, "received_bytes": wire,
                "projection_file": prefix + ".projection.json", "projection_sha256": "b" * 64,
                "projection_bytes": 4096, "response_complete": True, "disposition": "projected",
                "fetch_utc": "2026-10-11T01:15:00+00:00"})
        scopes.append({"provider": "massive", "dataset": "ratings", "window": list(window),
            "pages": count, "source_rows": rows, "terminated": True})
    pages.append({"request_index": 387, "provider": "sharadar", "dataset": "tickers", "window": None,
        "page": 0, "http_status": 200, "wire_file": "request.0387.wire.csv",
        "wire_sha256": "10e4412848bf6c917b2f22657a3203e204bf77925c2f422f50c4d4a983ecf45a",
        "wire_bytes": 451756, "received_bytes": 451756, "projection_file": None,
        "projection_sha256": None, "projection_bytes": 0, "response_complete": True,
        "disposition": "wire_accepted", "fetch_utc": "2026-10-11T01:16:00+00:00"})
    scopes.extend({"provider": "sharadar", "dataset": dataset, "window": None, "pages": 0,
        "source_rows": 0, "response_bytes": 451756 if dataset == "tickers" else 0,
        "terminated": False} for dataset in ("tickers", "actions"))
    return {"schema": "tpr-extended-source-index-v1", "operation_id": m.CAPTURE,
        "study_id": m.OLD_STUDY, "plan_sha256": m.CAPTURE_PLAN, "git_sha": m.CAPTURE_GIT,
        "source_hashes": {name: m.PUBLIC_PINS.get(name, "c" * 64) for name in m.SOURCE_PATHS},
        "started_utc": "2026-10-11T01:11:34.248700+00:00", "ended_utc": "2026-10-11T01:17:26.417335+00:00",
        "pages": pages, "census": scopes, "failure": "refused_or_bound_hit_no_retry",
        "report": json.loads(m.aggregate_bytes()), "point_in_time_data": False,
        "action_history_no_lower_bound": True, "current_vintage_identity": True,
        "count_semantics": dict(m._COUNT_SEMANTICS), "terminated_pagination_not_transaction_snapshot": True}


def test_public_receipt_reconstruction_has_exact_published669_byte_hash():
    assert len(m.aggregate_bytes()) == m.AGGREGATE_BYTES == 669
    assert hashlib.sha256(m.aggregate_bytes()).hexdigest() == m.AGGREGATE_SHA256
    assert m.INDEX_BYTES == 224765
    assert m.INDEX_SHA256 == "701ab0f2e9e61d1db1f53b7d274bf70429f84b565a9fff8c56d1ced13b73e82c"
    assert m.INDEX_NAME == m.CAPTURE + ".source-index.json"


def test_synthetic_schema_validation_extracts_only386_projections_grouped74_windows():
    body = synthetic_index()
    before = deepcopy(body)
    result = m._inventory(body)
    assert body == before
    assert result["window_count"] == 74 and len(result["windows"]) == 74
    descriptors = [page for scope in result["windows"] for page in scope["projections"]]
    assert len(descriptors) == result["projection_count"] == 386
    assert [page["name"] for page in descriptors] == [f"request.{n:04}.projection.json" for n in range(1, 387)]
    assert all(page["row_count"] is None for page in descriptors)
    assert result["projection_bytes"] == result["next_stage_max_bytes"] == 386 * 4096
    assert result["source_rows"] == 349018
    assert result["massive_wire_bytes_in_old_index"] == 255130379
    assert result["original_capture_status"] == "FAILED" and result["original_scope_remains_spent"] is True
    assert result["windows"][0]["window"] == ["2020-09-01", "2020-09-30"]
    assert result["windows"][-1]["window"] == ["2026-10-01", "2026-10-09"]
    assert all(result[key] is False for key in ("read_raw_wire", "read_sharadar", "read_old_d0",
        "provider_completeness_proven", "historical_identity_proven", "point_in_time_data", "rights_verified",
        "source_inputs_admitted", "native_acceptance", "canonical_admission"))
    assert result["accepted_performance"] is None
    assert result["fresh_claim_before_caller_index_read_required"] is True
    assert result["fresh_claim_before_page_read_required"] is True


@pytest.mark.parametrize("raw", [b"", b"{}", "{}", b"x" * 224765])
def test_public_entrypoint_requires_exact_raw_hash_and_size_before_parse(raw, monkeypatch):
    def forbidden(_): raise AssertionError("unbound bytes parsed")
    monkeypatch.setattr(m, "_object", forbidden)
    with pytest.raises(m.InventoryRefusal): m.project_index(raw)


def test_synthetic_index_cannot_satisfy_the_production_raw_hash_gate():
    with pytest.raises(m.InventoryRefusal): m.project_index(m.canonical(synthetic_index()))


@pytest.mark.parametrize("key,value", [("schema", "other"), ("operation_id", "old-D0"),
    ("study_id", m.STUDY), ("git_sha", "a" * 40), ("plan_sha256", "a" * 64),
    ("failure", None), ("point_in_time_data", True), ("current_vintage_identity", False),
    ("action_history_no_lower_bound", False), ("terminated_pagination_not_transaction_snapshot", False),
    ("started_utc", "2026-10-12T00:00:00+00:00"), ("ended_utc", "2026-10-11T01:17:26"),
    ("unexpected", "body")])
def test_wrong_capture_identity_flags_clocks_and_unknown_fields_refuse(key, value):
    body = synthetic_index(); body[key] = value
    with pytest.raises(m.InventoryRefusal): m._inventory(body)


@pytest.mark.parametrize("key,value", [("request_index", True), ("provider", "sharadar"), ("dataset", "actions"),
    ("window", ["2020-08-01", "2020-08-31"]), ("page", True), ("http_status", 201),
    ("wire_file", "../row.json"), ("wire_sha256", "a" * 63), ("wire_bytes", 0),
    ("received_bytes", 1), ("projection_file", "request.0387.wire.csv"), ("projection_sha256", "Z" * 64),
    ("projection_bytes", True), ("projection_bytes", 128 * 1024**2 + 1),
    ("response_complete", False), ("disposition", "wire_accepted"),
    ("fetch_utc", "2026-10-11T01:10:00+00:00"), ("extra", "body")])
def test_wrong_page_descriptor_or_escape_refuses(key, value):
    body = synthetic_index(); body["pages"][0][key] = value
    with pytest.raises(m.InventoryRefusal): m._inventory(body)


@pytest.mark.parametrize("key,value", [("provider", "sharadar"), ("dataset", "actions"),
    ("window", ["2020-09-01", "2026-10-09"]), ("pages", True), ("pages", 65),
    ("source_rows", 999999), ("source_rows", True), ("terminated", False), ("extra", "body")])
def test_wrong_census_scope_refuses(key, value):
    body = synthetic_index(); body["census"][0][key] = value
    with pytest.raises(m.InventoryRefusal): m._inventory(body)


def test_missing_and_added_pages_or_census_and_source_hashes_refuse():
    for key in ("pages", "census"):
        for delta in (-1, 1):
            body = synthetic_index()
            if delta == -1: body[key].pop()
            else: body[key].append(deepcopy(body[key][-1]))
            with pytest.raises(m.InventoryRefusal): m._inventory(body)
    body = synthetic_index(); body["source_hashes"].pop(m.SOURCE_PATHS[0])
    with pytest.raises(m.InventoryRefusal): m._inventory(body)
    body = synthetic_index(); body["source_hashes"][next(iter(m.PUBLIC_PINS))] = "a" * 64
    with pytest.raises(m.InventoryRefusal): m._inventory(body)


def test_report_status_and_ignored_sharadar_metadata_cannot_be_promoted_or_read():
    for path, value in (("report", True), ("ignored", "projected"), ("census", True)):
        body = synthetic_index()
        if path == "report": body["report"]["capture_complete"] = value
        elif path == "ignored": body["pages"][-1]["disposition"] = value
        else: body["census"][-1]["terminated"] = value
        with pytest.raises(m.InventoryRefusal): m._inventory(body)


def test_projection_total_and_wire_census_are_enforced():
    body = synthetic_index()
    body["pages"][0]["wire_bytes"] -= 1; body["pages"][0]["received_bytes"] -= 1
    with pytest.raises(m.InventoryRefusal): m._inventory(body)
    body = synthetic_index()
    for entry in body["pages"][:-1]: entry["projection_bytes"] = 128 * 1024**2
    with pytest.raises(m.InventoryRefusal): m._inventory(body)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}', b'[]'])
def test_strict_metadata_json_refuses_duplicates_float_and_nonobject(raw):
    with pytest.raises(m.InventoryRefusal): m._object(raw)


def test_pure_import_boundary_and_no_file_or_effect_calls():
    tree = ast.parse(Path(m.__file__).read_text())
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    modules |= {item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names}
    assert modules <= {"__future__", "calendar", "datetime", "hashlib", "json", "re"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "eval", "exec", "__import__"}
