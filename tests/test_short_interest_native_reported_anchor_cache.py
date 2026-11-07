"""Fabricated exact cache bytes; no actual cache/source/key/provider I/O."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from data.hashing import canonical_json, hash_bytes
import research.short_interest_etf.native_reported_anchor_cache as m

SPEC = importlib.util.spec_from_file_location("anchor_cache_source_fixtures",
        Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
DATES = ("2023-01-13", "2023-04-14", "2023-07-14")


def fixture(monkeypatch, *, reports=None, events=(), dates=DATES):
    matrix = f.matrix([("SYN", day) for day in dates])
    actions, dictionary = f.actions(events), f.dictionary()
    plan = m.reported.build_native_reported_anchor_plan(matrix,
            reports or tuple(f.identity(day) for day in dates), actions, dictionary)
    values = tuple(plan.iter_parts())
    known = {**m.KNOWN, "plan_sha256": plan.sha256, "matrix_sha256": matrix.sha256,
             "request_budget": plan.header()["exact_request_budget"], "date_count": len(dates)}
    monkeypatch.setattr(m, "KNOWN", known)
    names = ["header.private.json", "anchors.private.bin", "cells.private.bin"] + [
            f"event-{index:06d}.private.json" for index in range(1, len(values) - 2)]
    closure = {"schema": "si-exact-reported-anchor-cache-closure-v1", "observed_source": known,
            "parts": [{"name": name, "sha256": hash_bytes(raw), "bytes": len(raw)} for name, raw in zip(names, values)],
            "source_only": True, "source_admitted": False, "ready_for_empirical_backtest": False,
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
            "backtest_result_exists": False}
    raw = canonical_json(closure).encode()
    monkeypatch.setattr(m, "REGISTERED_CLOSURE_SHA256", hash_bytes(raw))
    proof = m.verify_closure(raw)
    return plan, matrix, values, actions, dictionary, raw, proof


def rebuild(value):
    plan, matrix, parts, actions, dictionary, raw, proof = value
    return m.rebuild_anchor_plan(matrix, *parts[:3], tuple(parts[3:]), actions, dictionary, closure=proof)


def repin(monkeypatch, value, parts):
    plan, matrix, old, actions, dictionary, raw, proof = value
    known = {**m.KNOWN, "plan_sha256": m.reported._packed_digest(*parts[:3], tuple(parts[3:]))}
    monkeypatch.setattr(m, "KNOWN", known)
    body = json.loads(raw)
    body["observed_source"] = known
    for descriptor, part in zip(body["parts"], parts):
        descriptor.update(sha256=hash_bytes(part), bytes=len(part))
    raw = canonical_json(body).encode()
    monkeypatch.setattr(m, "REGISTERED_CLOSURE_SHA256", hash_bytes(raw))
    return plan, matrix, tuple(parts), actions, dictionary, raw, m.verify_closure(raw)


def test_exact_cache_reconstruction_preserves_plan_tickets_cells_archive_and_every_fence(monkeypatch):
    value = fixture(monkeypatch, events=("2023-02-01,split,SYN,Source split,2,,\n",))
    old, new = value[0], rebuild(value)
    assert type(new) is m.reported.NativeReportedAnchorPlan and new.sha256 == old.sha256
    assert tuple(new.iter_parts()) == tuple(old.iter_parts())
    assert list(new.iter_cells()) == list(old.iter_cells())
    assert list(new.iter_anchors()) == list(old.iter_anchors())
    assert list(new.iter_split_fences()) == list(old.iter_split_fences())
    assert [q.to_payload() for q in new.query_plan.iter_queries()] == [q.to_payload() for q in old.query_plan.iter_queries()]
    assert new._matrix is value[1]
    assert new.header()["authority"]["actual_input_execution_admitted"] is False


@pytest.mark.parametrize("bad", [True, False, {}, None])
def test_no_completion_or_caller_flag_can_construct_cached_plan(monkeypatch, bad):
    plan, matrix, parts, actions, dictionary, raw, proof = fixture(monkeypatch)
    with pytest.raises(m.AnchorCacheRefusal):
        m.rebuild_anchor_plan(matrix, *parts[:3], tuple(parts[3:]), actions, dictionary, closure=bad)


def test_unregistered_or_modified_closure_refuses_before_any_part_reconstruction(monkeypatch):
    value = fixture(monkeypatch)
    with pytest.raises(m.AnchorCacheRefusal):
        m.verify_closure(value[5] + b" ")
    monkeypatch.setattr(m, "REGISTERED_CLOSURE_SHA256", "PENDING")
    with pytest.raises(m.AnchorCacheRefusal):
        m.verify_closure(value[5])


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_original_part_bytes_cannot_change_after_cache_closure_pin(monkeypatch, index):
    value = fixture(monkeypatch, events=("2023-02-01,split,SYN,Source split,2,,\n",))
    parts = list(value[2])
    parts[index] += b"x"
    with pytest.raises(m.AnchorCacheRefusal):
        rebuild((*value[:2], tuple(parts), *value[3:]))


@pytest.mark.parametrize("change", ["count", "authority", "policy", "dates", "class", "composite", "query_digest"])
def test_semantic_header_corruption_refuses_even_if_fake_registered_digest_recomputed(monkeypatch, change):
    value = fixture(monkeypatch)
    parts = list(value[2])
    header = json.loads(parts[0])
    if change == "count":
        header["cell_count"] += 1
    elif change == "authority":
        header["authority"]["source_admitted"] = True
    elif change == "policy":
        header["policy_sha256"] = "f" * 64
    elif change == "dates":
        header["identity_source_pins"].reverse()
    elif change == "class":
        header["class_labels"][0][0] = "BBG000000001"
    elif change == "composite":
        header["composites"][0] = "not-a-FIGI"
    else:
        header["underlying_query_plan_sha256"] = "a" * 64
    parts[0] = canonical_json(header).encode()
    with pytest.raises(m.AnchorCacheRefusal):
        rebuild(repin(monkeypatch, value, parts))


@pytest.mark.parametrize("change", ["ordinal", "day", "label", "refresh", "identity_origin", "cell_future", "cell_class", "cell_flags"])
def test_packed_anchor_and_cell_bounds_refuse_even_after_fake_repin(monkeypatch, change):
    value = fixture(monkeypatch)
    parts = list(value[2])
    if change.startswith("cell_"):
        raw = bytearray(parts[2])
        values = list(m.reported._CELL.unpack_from(raw, 0))
        if change == "cell_future":
            values[0] = 1
        elif change == "cell_class":
            values[1] = 100
        else:
            values[2] = 4
        m.reported._CELL.pack_into(raw, 0, *values)
        parts[2] = bytes(raw)
    else:
        raw = bytearray(parts[1])
        values = list(m.reported._ANCHOR.unpack_from(raw, 0))
        index, number = {"ordinal": (0, 100), "day": (1, 2), "label": (2, 100),
                "refresh": (4, 0), "identity_origin": (6, 1000)}[change]
        values[index] = number
        m.reported._ANCHOR.pack_into(raw, 0, *values)
        parts[1] = bytes(raw)
    with pytest.raises(m.AnchorCacheRefusal):
        rebuild(repin(monkeypatch, value, parts))


def test_negative_listing_and_class_transition_fences_remain_negative_and_chronological(monkeypatch):
    dates = ("2023-01-13", "2023-01-31", "2023-02-15")
    reports = (f.identity(dates[0]), f.identity(dates[1], venue=None), f.identity(dates[2], class_id=f.NEXT_CLASS))
    old, new = None, None
    value = fixture(monkeypatch, dates=dates, reports=reports)
    old, new = value[0], rebuild(value)
    assert list(old.iter_cells()) == list(new.iter_cells())
    cells = list(new.iter_cells())
    assert cells[1]["refusal_reasons"] and cells[1]["anchor_index"] == -1
    assert cells[0]["share_class_figi"] != cells[2]["share_class_figi"]


def test_wrong_original_action_archive_cannot_rebind_fences_to_cached_plan(monkeypatch):
    value = fixture(monkeypatch)
    with pytest.raises(m.AnchorCacheRefusal):
        m.rebuild_anchor_plan(value[1], *value[2][:3], tuple(value[2][3:]),
                f.actions(("2023-02-01,split,SYN,Source split,2,,\n",)), value[4], closure=value[6])
