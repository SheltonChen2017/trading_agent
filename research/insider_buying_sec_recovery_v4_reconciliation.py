"""Read-only reconciliation of the original partition and completed fresh v4 runs.

The immutable external inventory is exhaustive, not a directory-derived list of
successful runs. Unknown, incomplete and ambiguous claims refuse. This version
supports the independently captured first64 and combined-continuation journal
profiles; it does not mint a dispatch selection or modify either old contract.
Original producer/saved-consumer lineage and this fresh consumer are distinct.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
import weakref


VERSION = "INSETF-IB1B-COMPLETED-V4-RECONCILIATION-v1"
INVENTORY_VERSION = VERSION + "/external-capture-inventory"
SELF_PATH = "research/insider_buying_sec_recovery_v4_reconciliation.py"
BASE_PATH = "research/insider_buying_sec_recovery_v4_historical_replay.py"
COMBINED_PATH = "research/insider_buying_sec_recovery_v4_combined.py"
CONTINUATION_PATH = "research/insider_buying_sec_recovery_v4_continuation_capture.py"
MAX_OUTPUT_BYTES, MAX_TIMEOUT_SECONDS, MAX_PREVIEW_REQUESTS = 1024 * 1024, 900, 256
MAX_INVENTORY_BYTES, MAX_RUNS, MAX_PARENTS = 256 * 1024, 128, 79868
_SHA, _COMMIT = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[a-z][a-z0-9-]{0,79}\Z")
_TOKEN, _TEST_TOKEN = object(), object()
_IMAGES = weakref.WeakKeyDictionary()
_CAPTURED_BASE = None
_PINS = {
    BASE_PATH: "dedbddf5782da30359239049d46a48fbde7a3fd64ac0da458b40f32ca2f4f725",
    "research/insider_buying_sec_recovery_v4_source_view.py": "f5b09920b1a7b68079df664708f038e03c18279d4c7090e95a316ab330df2e9e",
    "research/insider_buying_sec_recovery_v4_capture.py": "11ba9f33325ea01c1b38f83ffc7ce5a237c2a251545a26e8fad82a66fd70e9f0",
    "research/insider_buying_sec_recovery_v4_projection.py": "8c78395b8a10fa5ffe3a8b556251dfddffd554ee08c625ead7f53e35775d3c08",
    "research/insider_buying_sec_recovery_v4_selection.py": "3df8e67531e5429bf0742bceafc6fdec817b26a07d83813fda0b4220bbb78e7b",
    COMBINED_PATH: "09bcd9a10136db28ce509c6020f88cbd8d1ad42cc88e1d1a68b1a7e37192c34f",
    CONTINUATION_PATH: "8a6699c272342716603c4a748b9ed6409528d2c01212bc77fc3d6393c423fcdc",
}


class ReconciliationV4Error(ValueError):
    pass


def _refuse(reason): raise ReconciliationV4Error("REFUSED: " + reason)
def _base(): return _CAPTURED_BASE or importlib.import_module("research.insider_buying_sec_recovery_v4_historical_replay")
def _canonical(body): return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _digest(body): return _sha(_canonical(body))


OBSERVED_CAPTURE_INVENTORY = {"kind": INVENTORY_VERSION, "scope": "observed_first64_then_continuation256", "runs": [
    {"profile": "first64-v4", "capture_id": "ib-sec-v4-first64-20261007-once",
     "report_sha256": "f93c844f2866fddedb96fb4277d74089be7bfa46abbbc2421945bfc648750ff6",
     "capture_producer_head": "e900c7a90d326cd81df952684b0c583ad8ffb639",
     "capture_source_inventory_sha256": "79253cb7cab395bb6c03e528096c1961ac159d87c48131afef06224ec0ab35fd",
     "selection_sha256": "c3c4a4dd6899e2ef681937adf4a61c76f5f69a5f866e05fe515d81bd50fa12c8",
     "selected_prefix_sha256": "48e5c2da08418e66d8b33c554a33048ac1b43bc66f3246304bbbc5beb1a22e70",
     "projection_id": "ib-sec-v4-projection-first64-20261007-once",
     "projection_receipt_sha256": "3a53e91be960eec7d7cfede08cd9d8888ecf8a715b0d48e45387a3fbc5d3cc19",
     "projection_receipt_size_bytes": 94936,
     "projection_consumer_head": "23c7a11d53a8d1c457bac34bdebe977d3d567d00",
     "projection_consumer_inventory_sha256": "f58694109a7af1e6be2eb6e3c2f72837658ea02b353fa625f30a5932270afc68",
     "projection_rows_sha256": "7bda748f0fba8b645418fc36dad110d68fe1f2dabc73b141db73d1fa67c6d532",
     "completed_parents": 64, "retained_body_bytes": 504050},
    {"profile": "combined-continuation-v1", "capture_id": "ib-sec-v4-continuation256-20261008-once",
     "report_sha256": "3112a6d841bf9307f72f69249185c85798e00ea94efd7b28f1cb2f59ebf18854",
     "capture_producer_head": "16d60b2b915c708e3c3d792c312cec6031f1d060",
     "capture_source_inventory_sha256": "a8d9100a2d67f28c08e12a12f9874bc69da6273e732c8686f7b16a7babbfa222",
     "selection_sha256": "66b36a9422129ebc99abeda965b5b5206cbeba6c095eaa9899660d4e0a159019",
     "selected_prefix_sha256": "4866773eda2eb2d73406b9e289738dd35b1e86deb9b8f5104c0f2d5c45ce52a3",
     "projection_id": "ib-sec-v4-projection-continuation256-20261008-once",
     "projection_receipt_sha256": "86398e3915dac12fadbd8e9e2fffd03ef018a22339948bf8fc9cb3324cb63acd",
     "projection_receipt_size_bytes": 157714,
     "projection_consumer_head": "16d60b2b915c708e3c3d792c312cec6031f1d060",
     "projection_consumer_inventory_sha256": "a8d9100a2d67f28c08e12a12f9874bc69da6273e732c8686f7b16a7babbfa222",
     "projection_rows_sha256": "c98ba1440ce7dac91b1a55bfa6a160c15a179887c4a621c2f80687b8d6aac037",
     "completed_parents": 256, "retained_body_bytes": 2011446},
]}
OBSERVED_CAPTURE_INVENTORY_BYTES = _canonical(OBSERVED_CAPTURE_INVENTORY)
OBSERVED_CAPTURE_INVENTORY_SHA256 = _sha(OBSERVED_CAPTURE_INVENTORY_BYTES)


def _inventory(raw, expected_sha, *, observed):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_INVENTORY_BYTES or type(expected_sha) is not str
            or _SHA.fullmatch(expected_sha) is None or _sha(raw) != expected_sha or type(observed) is not bool):
        _refuse("external immutable capture inventory/hash differs")
    try: body = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError): _refuse("capture inventory cannot be decoded")
    if (type(body) is not dict or set(body) != {"kind", "scope", "runs"} or body["kind"] != INVENTORY_VERSION
            or body["scope"] != ("observed_first64_then_continuation256" if observed else "invented_test_only")
            or _canonical(body) != raw or type(body["runs"]) is not list or not 1 <= len(body["runs"]) <= MAX_RUNS):
        _refuse("ordered capture inventory schema/serialization differs")
    keys = set(OBSERVED_CAPTURE_INVENTORY["runs"][0]); seen, total = set(), 0
    for ordinal, row in enumerate(body["runs"]):
        if (type(row) is not dict or set(row) != keys or type(row["profile"]) is not str or row["profile"] not in {"first64-v4", "combined-continuation-v1"}
                or (row["profile"] == "first64-v4") is not (ordinal == 0)
                or any(type(row[k]) is not str or _ID.fullmatch(row[k]) is None for k in ("capture_id", "projection_id"))
                or row["capture_id"] in seen or any(type(row[k]) is not str or _SHA.fullmatch(row[k]) is None
                    for k in keys if k.endswith("sha256"))
                or any(type(row[k]) is not str or _COMMIT.fullmatch(row[k]) is None
                    for k in ("capture_producer_head", "projection_consumer_head"))
                or type(row["completed_parents"]) is not int or not 1 <= row["completed_parents"] <= (64 if ordinal == 0 else 256)
                or type(row["retained_body_bytes"]) is not int or not 0 < row["retained_body_bytes"] <= row["completed_parents"] * 8 * 1024**2
                or type(row["projection_receipt_size_bytes"]) is not int or not 0 < row["projection_receipt_size_bytes"] <= MAX_OUTPUT_BYTES):
            _refuse("capture profile, identity, lineage or finite count differs")
        seen.add(row["capture_id"]); total += row["completed_parents"]
    if total > MAX_PARENTS: _refuse("fresh capture population exceeds frozen scope")
    # Existing continuation-v1 validates a first64-only predecessor inventory.
    # Do not silently reinterpret that contract for a third/new journal family.
    if len(body["runs"]) > 2: _refuse("later capture needs an explicitly supported successor journal profile")
    if observed and (body != OBSERVED_CAPTURE_INVENTORY or raw != OBSERVED_CAPTURE_INVENTORY_BYTES):
        _refuse("this observed profile requires the exact preregistered two-run inventory")
    return body


def _authority():
    return {"source_authenticated": False, "official_acceptance_verified": False,
        "publication_time_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_evidence": False, "economic_attribution_verified": False, "amendment_linkage_verified": False,
        "complete_corpus": False, "direct_ib1c_ingest_authorized": False, "dispatch_enabled": False,
        "qc_authorized": False, "backtest_authorized": False, "execution_authorized": False, "output_written": False,
        "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}


def _reconcile_partition(original_requests, original_partition, closed_runs, *, maximum_preview_requests):
    """Pure exact-prefix overlay; never a factory for acquisition authority."""
    from research import insider_buying_sec_recovery_v4_combined as combined
    from research import insider_buying_sec_recovery_v4_projection as projection
    if (type(original_requests) is not tuple or not 1 <= len(original_requests) <= 99394
            or type(original_partition) is not list or len(original_partition) != len(original_requests)
            or type(closed_runs) is not list or not 1 <= len(closed_runs) <= MAX_RUNS
            or type(maximum_preview_requests) is not int or not 1 <= maximum_preview_requests <= MAX_PREVIEW_REQUESTS):
        _refuse("original population, completed runs or preview bound differs")
    originals, accessions, eligible = [], set(), []
    counts = dict.fromkeys(combined._CLASSES, 0)
    for index, (request, part) in enumerate(zip(original_requests, original_partition, strict=True)):
        try: request = combined._request(request)
        except ValueError: _refuse("original request identity differs")
        if request["accession_number"] in accessions: _refuse("original accession repeats")
        accessions.add(request["accession_number"]); originals.append(request)
        if (type(part) is not dict or set(part) != {"global_index", "request_sha256", "source_class"}
                or type(part["global_index"]) is not int or part["global_index"] != index
                or part["request_sha256"] != _digest(request) or type(part["source_class"]) is not str or part["source_class"] not in counts):
            _refuse("full ordered original partition differs")
        counts[part["source_class"]] += 1
        if part["source_class"] == "originally_unattempted": eligible.append(part)
    offset, bodies, run_ids, all_rows = 0, set(), set(), []
    for run in closed_runs:
        if (type(run) is not dict or set(run) != {"capture_id", "rows"} or type(run["capture_id"]) is not str
                or _ID.fullmatch(run["capture_id"]) is None or run["capture_id"] in run_ids
                or type(run["rows"]) is not list or not 1 <= len(run["rows"]) <= 256):
            _refuse("ordered completed run identity/cardinality differs")
        run_ids.add(run["capture_id"])
        if offset + len(run["rows"]) > len(eligible): _refuse("completed runs exceed original eligible population")
        for ordinal, row in enumerate(run["rows"]):
            expected = eligible[offset + ordinal]
            if (type(row) is not dict or set(row) != {"ordinal", "global_index", "request_sha256", "target", "claim_sha256",
                    "start_sha256", "result_sha256", "raw_parent", "disposition", "projection"}
                    or type(row["ordinal"]) is not int or row["ordinal"] != ordinal
                    or type(row["global_index"]) is not int or row["global_index"] != expected["global_index"]
                    or row["request_sha256"] != expected["request_sha256"]
                    or row["disposition"] != "complete_parent_projected_noncanonical"
                    or any(type(row[k]) is not str or _SHA.fullmatch(row[k]) is None for k in ("claim_sha256", "start_sha256", "result_sha256"))):
                _refuse("completed runs are not the exact concatenated original eligible prefix")
            if row["target"] != projection._target(originals[row["global_index"]]).to_payload():
                _refuse("completed request locator/master/issuer target differs")
            raw, parsed = row["raw_parent"], row["projection"]
            if (type(raw) is not dict or set(raw) != {"sha256", "size_bytes"} or type(raw["sha256"]) is not str
                    or _SHA.fullmatch(raw["sha256"]) is None or raw["sha256"] in bodies
                    or type(raw["size_bytes"]) is not int or not 0 < raw["size_bytes"] <= 8 * 1024**2
                    or type(parsed) is not dict or set(parsed) != {"payload_sha256", "header_sha256", "primary_xml_sha256"}
                    or any(type(value) is not str or _SHA.fullmatch(value) is None for value in parsed.values())):
                _refuse("completed original parent/child hashes or uniqueness differ")
            bodies.add(raw["sha256"]); all_rows.append({"capture_id": run["capture_id"], **row})
        offset += len(run["rows"])
    updated = [dict(row) for row in original_partition]
    for row in all_rows: updated[row["global_index"]]["source_class"] = "fresh_v4_completed"
    remaining = eligible[offset:]
    preview = [{**row, "request": originals[row["global_index"]]} for row in remaining[:maximum_preview_requests]]
    return {"original_class_counts": counts,
        "combined_class_counts": {**counts, "fresh_v4_completed": offset, "originally_unattempted": len(remaining)},
        "total_parents": len(originals), "original_unattempted_count": len(eligible), "fresh_completed_parents": offset,
        "remaining_unattempted_count": len(remaining), "prior_source_bound_count": len(originals) - len(eligible),
        "combined_request_bound_custody_count": len(originals) - len(remaining), "combined_partition_sha256": _digest(updated),
        "remaining_inventory_sha256": _digest(remaining), "maximum_preview_requests": maximum_preview_requests,
        "next_request_preview": preview, "next_request_preview_sha256": _digest(preview),
        "completed_ordered_rows_sha256": _digest(all_rows), "completed_run_count": len(closed_runs)}


def _run_closures(root, inventory, *, observed):
    """Fresh exact saved-receipt/journal replay. No old-loader substitution."""
    from research import insider_buying_sec_recovery_v4_capture as capture
    from research import insider_buying_sec_recovery_v4_projection as projection
    from research import insider_buying_sec_recovery_v4_continuation_capture as continuation
    from research import insider_buying_sec_recovery_v4_combined as combined
    descriptors = inventory["runs"]
    expected_runs = tuple(sorted(row["capture_id"] for row in descriptors))
    count = sum(row["completed_parents"] for row in descriptors)
    before = combined._registry_snapshot(root, expected_count=count, expected_runs=expected_runs)
    closed, summaries, own_claims, folders, retained, retained_bodies = [], [], [], [], [], []
    try:
        for descriptor in descriptors:
            cid = descriptor["capture_id"]
            saved_dir = capture._Directory(Path(root).joinpath("artifacts", "insider_buying", "sec_recovery_v4_projection", descriptor["projection_id"]))
            run = capture._Directory(Path(root).joinpath(*capture.ARTIFACT_PARTS, "runs", cid))
            claims = capture._Directory(Path(root).joinpath(*capture.ARTIFACT_PARTS, "claims"))
            objects = capture._Directory(run.path / "objects")
            folders.extend((saved_dir, run, claims, objects))
            saved_raw = saved_dir.read("receipt.json", cap=MAX_OUTPUT_BYTES)
            if _sha(saved_raw) != descriptor["projection_receipt_sha256"] or len(saved_raw) != descriptor["projection_receipt_size_bytes"]:
                _refuse("saved original projection receipt external anchor differs")
            saved = capture._decode(saved_raw)
            report_raw, reservation_raw = run.read("complete.json"), run.read("reservation.json", cap=MAX_OUTPUT_BYTES)
            report, reservation = capture._decode(report_raw), capture._decode(reservation_raw)
            body = reservation["selection"]
            if (_sha(report_raw) != descriptor["report_sha256"] or _sha(reservation_raw) != report["reservation_sha256"]
                    or reservation["capture_git_commit"] != descriptor["capture_producer_head"]
                    or body["repository_head"] != descriptor["capture_producer_head"]
                    or body["current_source_inventory_sha256"] != descriptor["capture_source_inventory_sha256"]
                    or report["selection_sha256"] != descriptor["selection_sha256"]
                    or report["selected_prefix_sha256"] != descriptor["selected_prefix_sha256"]):
                _refuse("original acquisition producer/report/selection lineage differs")
            if descriptor["profile"] == "first64-v4":
                fresh = projection._project_root(cid, descriptor["report_sha256"], root=root, observed=observed,
                    consumer=lambda: {"scope": "fresh_reconciliation_consumer_not_original_consumer"}).to_payload()
                consumer = saved["consumer"]
                if (saved["capture_git_commit"] != descriptor["capture_producer_head"]
                        or saved["capture_report_sha256"] != descriptor["report_sha256"]
                        or saved["capture_source_inventory_sha256"] != descriptor["capture_source_inventory_sha256"]
                        or saved["capture_selection_sha256"] != descriptor["selection_sha256"]
                        or saved["capture_selected_prefix_sha256"] != descriptor["selected_prefix_sha256"]
                        or consumer["declared_projection_repository_head"] != descriptor["projection_consumer_head"]
                        or consumer["current_source_inventory_sha256"] != descriptor["projection_consumer_inventory_sha256"]
                        or saved["ordered_rows_sha256"] != descriptor["projection_rows_sha256"]
                        or {key: value for key, value in saved.items() if key != "consumer"}
                            != {key: value for key, value in fresh.items() if key != "consumer"}
                        or saved["authority"] != projection._authority()):
                    _refuse("first-prefix saved consumer lineage or fresh rows differ")
                rows = [{**row, "projection": {"payload_sha256": row["projection"]["payload_sha256"],
                    "header_sha256": row["projection"]["header"]["sha256"],
                    "primary_xml_sha256": row["projection"]["primary_xml"]["sha256"]}} for row in fresh["rows"]
                    if row["disposition"] == "complete_parent_projected_noncanonical"]
                counts = fresh["counts"]
            else:
                fresh = continuation._verify_capture(cid, descriptor["report_sha256"], root=root, observed=observed, project_retained=True)
                consumer = saved["consumer"]
                if (consumer["declared_repository_head"] != descriptor["projection_consumer_head"]
                        or consumer["current_source_inventory_sha256"] != descriptor["projection_consumer_inventory_sha256"]
                        or saved["projection_rows_sha256"] != descriptor["projection_rows_sha256"]
                        or {key: value for key, value in saved.items() if key != "consumer"} != fresh):
                    _refuse("continuation saved consumer lineage or fresh projection differs")
                # The previous full prior-claim inventory is an exact predecessor,
                # not a subset that can silently hide an unknown/ambiguous claim.
                if (body["claim_inventory"] != sorted(own_claims, key=lambda item: item["name"])
                        or body["known_run_inventory"] != sorted(row["capture_id"] for row in closed)):
                    _refuse("continuation predecessor inventory differs from completed earlier runs")
                rows = []
                for ordinal, (selected, parsed) in enumerate(zip(body["requests"], fresh["projection_rows"], strict=True)):
                    if parsed["disposition"] != "complete_parent_projected_noncanonical": _refuse("grammar-quarantined parent blocks this completed projection union")
                    result_descriptor = report["results"][ordinal]
                    result_raw = run.read(result_descriptor["result_name"]); result = capture._decode(result_raw)
                    start_raw = run.read(f"request-{ordinal:03d}-start.json"); start = capture._decode(start_raw)
                    claim_raw = claims.read(capture._claim_name(selected))
                    if (_sha(result_raw) != result_descriptor["result_sha256"] or _sha(start_raw) != result["start_sha256"]
                            or _sha(claim_raw) != start["claim_sha256"] or parsed["global_index"] != selected["global_index"]
                            or parsed["request_sha256"] != selected["request_sha256"] or parsed["raw_parent_sha256"] != result["body_sha256"]):
                        _refuse("fresh continuation projection/start/claim/result extraction differs")
                    rows.append({"ordinal": ordinal, "global_index": selected["global_index"], "request_sha256": selected["request_sha256"],
                        "target": projection._target(selected["request"]).to_payload(), "claim_sha256": _sha(claim_raw),
                        "start_sha256": _sha(start_raw), "result_sha256": _sha(result_raw),
                        "raw_parent": {"sha256": result["body_sha256"], "size_bytes": result["body_size_bytes"]},
                        "disposition": parsed["disposition"], "projection": {"payload_sha256": parsed["projection_sha256"],
                            "header_sha256": parsed["header_sha256"], "primary_xml_sha256": parsed["primary_xml_sha256"]}})
                    retained.extend(((run, result_descriptor["result_name"], _sha(result_raw)), (run, f"request-{ordinal:03d}-start.json", _sha(start_raw))))
                counts = fresh["projection_counts"] | {"raw_parent_bytes": fresh["retained_body_bytes"]}
            expected_counts = {"header_bound_retained": descriptor["completed_parents"], "complete_parent_projected": descriptor["completed_parents"],
                "complete_parent_grammar_quarantined": 0, "raw_parent_bytes": descriptor["retained_body_bytes"]}
            if counts != expected_counts or len(rows) != descriptor["completed_parents"] or report["batch_completed"] is not True:
                _refuse("whole completed run all-row/projection accounting differs")
            for selected, row in zip(body["requests"], rows, strict=True):
                own_claims.append({"name": capture._claim_name(selected), "sha256": row["claim_sha256"]})
                retained_bodies.append((objects, row["raw_parent"]["sha256"] + ".bin", row["raw_parent"]["sha256"], row["raw_parent"]["size_bytes"]))
            closed.append({"capture_id": cid, "rows": rows})
            summaries.append({**descriptor, "fresh_projection_rows_sha256": fresh.get("ordered_rows_sha256", fresh.get("projection_rows_sha256")),
                "fresh_normalized_rows_sha256": _digest(rows), "counts": counts})
            retained.extend(((saved_dir, "receipt.json", descriptor["projection_receipt_sha256"]), (run, "complete.json", descriptor["report_sha256"]),
                (run, "reservation.json", report["reservation_sha256"])))
        if sorted(own_claims, key=lambda row: row["name"]) != before["claim_inventory"]:
            _refuse("whole claim registry is not exactly the independently completed run inventory")
        for folder, name, digest in retained:
            if _sha(folder.read(name, cap=MAX_OUTPUT_BYTES)) != digest: _refuse("saved receipt/journal changed during reconciliation")
        for folder, name, digest, size in retained_bodies:
            raw = folder.read(name, cap=8 * 1024**2)
            if _sha(raw) != digest or len(raw) != size: _refuse("retained body changed during final reconciliation custody scan")
            del raw
        for folder in folders: folder.check()
        after = combined._registry_snapshot(root, expected_count=count, expected_runs=expected_runs)
        if before != after: _refuse("whole permanent claim registry changed during reconciliation")
        return closed, summaries, before
    finally:
        for folder in reversed(folders): folder.close()


def _validate_body(body, *, observed):
    from research import insider_buying_sec_recovery_v4_combined as combined
    keys = {"kind", "scope", "repository_head", "worker_source_sha256", "worker_bootstrap_sha256", "current_source_inventory_sha256",
        "executed_modules", "source_view", "replay_anchors", "capture_inventory", "capture_inventory_sha256", "verified_runs", "authority",
        "stopped_v3_disposition", "source_bound_union_scope", "claim_inventory", "claim_inventory_count", "claim_inventory_sha256",
        "known_run_inventory", "known_run_inventory_sha256", "original_class_counts", "combined_class_counts", "total_parents",
        "original_unattempted_count", "fresh_completed_parents", "remaining_unattempted_count", "prior_source_bound_count",
        "combined_request_bound_custody_count", "combined_partition_sha256", "remaining_inventory_sha256", "maximum_preview_requests",
        "next_request_preview", "next_request_preview_sha256", "completed_ordered_rows_sha256", "completed_run_count"}
    if (type(body) is not dict or set(body) != keys or type(observed) is not bool or body["kind"] != VERSION
            or body["scope"] != ("observed_original_plus_completed320" if observed else "invented_test_only")
            or type(body["repository_head"]) is not str or _COMMIT.fullmatch(body["repository_head"]) is None):
        _refuse("reconciliation receipt schema/scope differs")
    inventory = _inventory(_canonical(body["capture_inventory"]), body["capture_inventory_sha256"], observed=observed)
    registry = combined._inventory(body["claim_inventory"], body["known_run_inventory"])
    if any(type(body[key]) is not type(value) or body[key] != value for key, value in registry.items()): _refuse("receipt claim/run inventory differs")
    if (type(body["authority"]) is not dict or body["authority"] != _authority()
            or any(type(body["authority"][key]) is not type(value) for key, value in _authority().items())):
        _refuse("read-only reconciliation authority differs")
    for key in keys:
        if key.endswith("sha256") and (type(body[key]) is not str or _SHA.fullmatch(body[key]) is None): _refuse("receipt digest differs")
    integer_keys = ("total_parents", "original_unattempted_count", "fresh_completed_parents", "remaining_unattempted_count",
        "prior_source_bound_count", "combined_request_bound_custody_count", "completed_run_count", "maximum_preview_requests")
    if any(type(body[key]) is not int or body[key] < 0 for key in integer_keys): _refuse("receipt population integers differ")
    original_counts, combined_counts = body["original_class_counts"], body["combined_class_counts"]
    if (type(original_counts) is not dict or set(original_counts) != set(combined._CLASSES)
            or any(type(value) is not int or value < 0 for value in original_counts.values())
            or sum(original_counts.values()) != body["total_parents"]
            or original_counts["originally_unattempted"] != body["original_unattempted_count"]
            or type(combined_counts) is not dict or set(combined_counts) != set(combined._CLASSES) | {"fresh_v4_completed"}
            or any(type(value) is not int or value < 0 for value in combined_counts.values())
            or combined_counts != {**original_counts, "fresh_v4_completed": body["fresh_completed_parents"],
                "originally_unattempted": body["remaining_unattempted_count"]}):
        _refuse("original and fresh class ledger accounting differs")
    count = sum(row["completed_parents"] for row in inventory["runs"])
    if (body["fresh_completed_parents"] != count or body["claim_inventory_count"] != count
            or body["completed_run_count"] != len(inventory["runs"])
            or body["known_run_inventory"] != sorted(row["capture_id"] for row in inventory["runs"])
            or body["remaining_unattempted_count"] != body["original_unattempted_count"] - count
            or body["prior_source_bound_count"] != body["total_parents"] - body["original_unattempted_count"]
            or body["combined_request_bound_custody_count"] != body["prior_source_bound_count"] + count
            or not 1 <= body["maximum_preview_requests"] <= MAX_PREVIEW_REQUESTS
            or type(body["next_request_preview"]) is not list
            or len(body["next_request_preview"]) != min(body["maximum_preview_requests"], body["remaining_unattempted_count"])
            or body["next_request_preview_sha256"] != _digest(body["next_request_preview"])
            or type(body["verified_runs"]) is not list or len(body["verified_runs"]) != len(inventory["runs"])):
        _refuse("receipt full-population/run/remaining accounting differs")
    if body["next_request_preview"]: combined._rows(body["next_request_preview"], len(body["next_request_preview"]))
    if any(_sha(row["request"]["accession_number"].encode("ascii")) + ".json" in {item["name"] for item in body["claim_inventory"]}
            for row in body["next_request_preview"]): _refuse("preview request already has a permanent claim")
    for descriptor, verified in zip(inventory["runs"], body["verified_runs"], strict=True):
        if (type(verified) is not dict or set(verified) != set(descriptor) | {"fresh_projection_rows_sha256", "fresh_normalized_rows_sha256", "counts"}
                or any(verified[key] != value or type(verified[key]) is not type(value) for key, value in descriptor.items())
                or verified["fresh_projection_rows_sha256"] != descriptor["projection_rows_sha256"]
                or type(verified["fresh_normalized_rows_sha256"]) is not str or _SHA.fullmatch(verified["fresh_normalized_rows_sha256"]) is None
                or verified["counts"] != {"header_bound_retained": descriptor["completed_parents"], "complete_parent_projected": descriptor["completed_parents"],
                    "complete_parent_grammar_quarantined": 0, "raw_parent_bytes": descriptor["retained_body_bytes"]}
                or any(type(value) is not int for value in verified["counts"].values())):
            _refuse("receipt exact verified capture/projection descriptor differs")
    if not observed: return body
    base = _base(); view = importlib.import_module("research.insider_buying_sec_recovery_v4_source_view")
    if (body["original_class_counts"] != base._COUNTS or any(type(v) is not int for v in body["original_class_counts"].values())
            or body["combined_class_counts"] != {**base._COUNTS, "fresh_v4_completed": 320, "originally_unattempted": 79548}
            or any(type(v) is not int for v in body["combined_class_counts"].values())
            or body["total_parents"] != 99394 or body["original_unattempted_count"] != 79868
            or body["prior_source_bound_count"] != 19526 or body["combined_request_bound_custody_count"] != 19846
            or body["stopped_v3_disposition"] != "preserved_unresolved_not_resumable"
            or body["source_bound_union_scope"] != "request_bound_noncanonical_custody_only"
            or body["replay_anchors"] != view._REPLAY_HASHES or body["worker_bootstrap_sha256"] != _sha(_BOOTSTRAP.encode())):
        _refuse("observed original320 reconciliation scope/counts differ")
    proof, trace = body["source_view"], body["executed_modules"]
    if (type(proof) is not dict or set(proof) != {"kind", "historical_commit", "historical_validator_sha256", "files",
            "validator_function_name", "ordered_read_cycles", "source_read_count", "source_read_trace_sha256", "callsite_bound"}
            or proof["kind"] != view.SOURCE_VIEW_VERSION or proof["historical_commit"] != base.HISTORICAL_COMMIT
            or proof["historical_validator_sha256"] != base.HISTORICAL_VALIDATOR_SHA256
            or proof["files"] != [{"path": p, "sha256": s} for p, s in base.HISTORICAL_FILES]
            or proof["validator_function_name"] != "_validator_source_sha256" or type(proof["ordered_read_cycles"]) is not int
            or not 1 <= proof["ordered_read_cycles"] <= 512 or type(proof["source_read_count"]) is not int
            or proof["source_read_count"] != 4 * proof["ordered_read_cycles"]
            or proof["source_read_trace_sha256"] != view._source_read_trace_digest(proof["ordered_read_cycles"])
            or proof["callsite_bound"] is not True or type(trace) is not list or not 8 <= len(trace) <= 512):
        _refuse("source-only historical execution proof differs")
    seen, historical = {}, {}
    for row in trace:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_kind"} or type(row["path"]) is not str or row["path"] in seen
                or type(row["sha256"]) is not str or _SHA.fullmatch(row["sha256"]) is None
                or row["source_kind"] not in {"current_source_snapshot", "historical_git_blob"}): _refuse("executed source row differs")
        base._module_name(row["path"]); seen[row["path"]] = row["sha256"]
        if row["source_kind"] == "historical_git_blob": historical[row["path"]] = row["sha256"]
    if historical != dict(base.HISTORICAL_FILES) or seen.get(SELF_PATH) != body["worker_source_sha256"] or any(seen.get(p) != sha for p, sha in _PINS.items()):
        _refuse("required exact accepted source images were not executed")
    return body


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ReconciledV4Receipt:
    _raw: bytes
    _token: object
    def to_payload(self):
        if (type(self) is not ReconciledV4Receipt or self._token is not _TOKEN or type(self._raw) is not bytes or _IMAGES.get(self) != self._raw):
            _refuse("exact genuinely replayed reconciliation receipt required")
        return _validate_body(json.loads(self._raw), observed=True)
    @property
    def raw_bytes(self): self.to_payload(); return self._raw
    @property
    def sha256(self): return _sha(self.raw_bytes)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class InventedReconciledV4Receipt:
    _raw: bytes
    _token: object
    def to_payload(self):
        if (type(self) is not InventedReconciledV4Receipt or self._token is not _TEST_TOKEN or type(self._raw) is not bytes or _IMAGES.get(self) != self._raw):
            _refuse("exact factory-bound invented reconciliation receipt required")
        return _validate_body(json.loads(self._raw), observed=False)
    @property
    def raw_bytes(self): self.to_payload(); return self._raw
    @property
    def sha256(self): return _sha(self.raw_bytes)


def reconcile_invented_capture_inventory(original_requests, original_partition, *, root, capture_inventory_raw,
        expected_capture_inventory_sha256, maximum_preview_requests=256):
    """Invented journal test family; never accepted by the observed supervisor.

Unlike a declaration sealer this consumes complete supplied invented journals,
freshly projects their bodies and proves exact source-prefix membership first.
"""
    inventory = _inventory(capture_inventory_raw, expected_capture_inventory_sha256, observed=False)
    closed, verified, registry = _run_closures(Path(root).resolve(), inventory, observed=False)
    reconciled = _reconcile_partition(original_requests, original_partition, closed,
        maximum_preview_requests=maximum_preview_requests)
    body = {"kind": VERSION, "scope": "invented_test_only", "repository_head": "a" * 40,
        "worker_source_sha256": "0" * 64, "worker_bootstrap_sha256": "0" * 64, "current_source_inventory_sha256": "0" * 64,
        "executed_modules": [], "source_view": None, "replay_anchors": {}, "capture_inventory": inventory,
        "capture_inventory_sha256": expected_capture_inventory_sha256, "verified_runs": verified,
        "stopped_v3_disposition": "not-observed-fixture", "source_bound_union_scope": "invented_test_only",
        **registry, **reconciled, "authority": _authority()}
    _validate_body(body, observed=False)
    raw = _canonical(body); receipt = InventedReconciledV4Receipt(raw, _TEST_TOKEN); _IMAGES[receipt] = raw
    return receipt


def _install_source_context(base, blobs, sources):
    if any(name.split(".")[0] in {"data", "research", "ml"} for name in sys.modules): _refuse("worker inherited lane modules")
    finder = base._HistoricalBlobFinder(blobs, sources); current = dict(sources)
    finder.executed.extend({"path": path, "sha256": _sha(current[path]), "source_kind": "current_source_snapshot"} for path in (BASE_PATH, SELF_PATH))
    sys.meta_path.insert(0, finder); sys.setprofile(finder.profile)
    view = importlib.import_module("research.insider_buying_sec_recovery_v4_source_view"); view._CAPTURED_BASE = base
    selection = importlib.import_module("research.insider_buying_sec_recovery_v4_selection"); selection._CAPTURED_BASE = base
    combined = importlib.import_module("research.insider_buying_sec_recovery_v4_combined"); combined._CAPTURED_BASE = base
    return finder, view


def _worker_main(bundle):
    base, finder, previous = _base(), None, sys.getprofile()
    try:
        blobs = base._validate_historical_blobs(base._decode_sources(bundle["historical_sources"]))
        sources = base._decode_sources(bundle["current_sources"]); current = dict(sources)
        if any(_sha(current[p]) != sha for p, sha in _PINS.items()) or _sha(current[SELF_PATH]) != bundle["worker_source_sha256"]:
            _refuse("captured accepted/new source images differ")
        inventory = _inventory(base64.b64decode(bundle["capture_inventory_b64"], validate=True), bundle["capture_inventory_sha256"], observed=True)
        base._assert_sources_unchanged(sources)
        finder, view_module = _install_source_context(base, blobs, sources)
        union = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_union")
        campaign = importlib.import_module("research.insider_buying_sec_all_form4_parent_campaign")
        prior = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_preflight")
        completed = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_verifier")
        partial = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_partial_verifier")
        diagnostic = importlib.import_module("research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier")
        v4 = importlib.import_module("research.insider_buying.sec_recovery_v4_plan")
        combined = importlib.import_module("research.insider_buying_sec_recovery_v4_combined")
        registry_before = combined._registry_snapshot(base.LANE_ROOT, expected_count=320,
            expected_runs=tuple(sorted(row["capture_id"] for row in inventory["runs"])))
        with view_module.HistoricalSourceView(blobs, union) as view:
            def source_replay():
                return union.preflight_observed_all_form4_parent_recovery_union(*base.SOURCE_ROOTS,
                    diagnostic_capture_git_commit=union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
                    expected_diagnostic_report_sha256=union.OBSERVED_DIAGNOSTIC_REPORT_SHA256)
            source = source_replay(); plan = campaign._build_real_plan(*base.SOURCE_ROOTS[:6])
            expectation = prior.PartialCampaignExpectation(capture_git_commit=prior.PRIOR_CAPTURE_GIT_COMMIT,
                shard_report_sha256s=prior.PRIOR_SHARD_REPORT_SHA256S, completed_counts=(8192, 1347), reused_counts=(972, 226), total_attempt_count=8342)
            def partial_replay():
                result = partial._verify_partial(plan, source, base.SOURCE_ROOTS[6], base.SOURCE_ROOTS[7], base.SOURCE_ROOTS[5], base.V3_ROOT,
                    prior_expectation=expectation, capture_git_commit=base.HISTORICAL_COMMIT, capture_code_sha256=base.EXECUTOR_SHA256)
                partial._require_observed_anchors(result)
                if result.completed_new_count != 1846 or result.attempt_count != 1847: _refuse("stopped v3 counts differ")
                return result
            stopped = partial_replay()
            accepted = diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT, expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256)
            classes, _ = completed._source_classes(plan, source)
            p = {key: getattr(stopped, key) for key in (*v4._PARTIAL_HASHES, *v4._PARTIAL_INTS)}
            d = {key: getattr(accepted, key) for key in (*v4._DIAGNOSTIC_HASHES, "diagnostic_capture_git_commit", "pending_global_index", "body_size_bytes")}
            proposal = v4.build_recovery_v4_offline_plan(tuple(req.to_payload() for req in plan.requests), tuple(classes), p, d,
                v4.bind_v3_historical_validator(base.HISTORICAL_COMMIT, blobs)); original = proposal.to_payload()
            closed, verified, registry = _run_closures(base.LANE_ROOT, inventory, observed=True)
            reconciled = _reconcile_partition(tuple(req.to_payload() for req in plan.requests), original["partition"], closed,
                maximum_preview_requests=bundle["maximum_preview_requests"])
            if registry != registry_before: _refuse("new claims appeared during original partition replay")
            if source_replay() != source or partial_replay() != stopped: _refuse("original retained roots changed during reconciliation")
            if diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                    capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT, expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256) != accepted:
                _refuse("separate ambiguous diagnostic changed")
            closed_after, verified_after, registry_after = _run_closures(base.LANE_ROOT, inventory, observed=True)
            if (closed_after, verified_after, registry_after) != (closed, verified, registry): _refuse("fresh runs/receipts/claims changed during reconciliation")
        base._assert_sources_unchanged(sources)
        if finder.called != {path for path, _ in base.HISTORICAL_FILES}: _refuse("exact historical functions were not executed")
        body = {"kind": VERSION, "scope": "observed_original_plus_completed320", "repository_head": bundle["repository_head"],
            "worker_source_sha256": bundle["worker_source_sha256"], "worker_bootstrap_sha256": _sha(_BOOTSTRAP.encode()),
            "current_source_inventory_sha256": _digest([{"path": path, "sha256": _sha(raw)} for path, raw in sources]),
            "executed_modules": finder.executed, "source_view": view.proof(), "replay_anchors": {
                "source_union_sha256": _digest(source), "partial_descriptor_sha256": _digest(p), "diagnostic_descriptor_sha256": _digest(d),
                "v4_plan_sha256": proposal.sha256, "partition_sha256": original["partition_sha256"],
                "proposed_unattempted_inventory_sha256": original["proposed_unattempted_inventory_sha256"]},
            "capture_inventory": inventory, "capture_inventory_sha256": bundle["capture_inventory_sha256"], "verified_runs": verified,
            "stopped_v3_disposition": "preserved_unresolved_not_resumable", "source_bound_union_scope": "request_bound_noncanonical_custody_only",
            **registry, **reconciled, "authority": _authority()}
        _validate_body(body, observed=True); raw = _canonical(body)
        if len(raw) + 1 > MAX_OUTPUT_BYTES: _refuse("reconciliation output cap exceeded")
        sys.stdout.buffer.write(raw + b"\n"); sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("REFUSED: isolated completed-v4 reconciliation failed\n")
        raise SystemExit(1) from None
    finally:
        sys.setprofile(previous)
        if finder is not None and finder in sys.meta_path: sys.meta_path.remove(finder)


_BOOTSTRAP = """import base64,hashlib,json,sys,types
raw=sys.stdin.buffer.read(33554433)
if len(raw)>33554432: raise SystemExit(2)
b=json.loads(raw)
rows=[r for r in b['current_sources'] if r['path']=='research/insider_buying_sec_recovery_v4_historical_replay.py']
if len(rows)!=1: raise SystemExit(2)
s=base64.b64decode(rows[0]['source_b64'],validate=True)
if hashlib.sha256(s).hexdigest()!=b['base_source_sha256']: raise SystemExit(2)
base=types.ModuleType('_reconciliation_v4_base');base.__file__=sys.argv[2];sys.modules[base.__name__]=base
exec(compile(s,base.__file__,'exec',dont_inherit=True),base.__dict__)
sys.addaudithook(base._audit_event)
s=base64.b64decode(b['worker_source_b64'],validate=True)
if hashlib.sha256(s).hexdigest()!=b['worker_source_sha256']: raise SystemExit(2)
m=types.ModuleType('_reconciliation_v4_worker');m.__file__=sys.argv[1];sys.modules[m.__name__]=m
exec(compile(s,m.__file__,'exec',dont_inherit=True),m.__dict__)
m._CAPTURED_BASE=base;m._worker_main(b)
"""


def _run_worker(raw, timeout_seconds):
    base = _base()
    if type(raw) is not bytes or not 0 < len(raw) <= base._MAX_INPUT_BYTES: _refuse("worker input cap differs")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS: _refuse("worker timeout differs")
    command = ("/usr/bin/sandbox-exec", "-p", base._worker_policy(), str(Path(sys.executable).resolve()), "-I", "-S", "-B", "-c", _BOOTSTRAP,
        str(base.LANE_ROOT / SELF_PATH), str(base.LANE_ROOT / BASE_PATH))
    proc = subprocess.Popen(command, cwd=base.LANE_ROOT, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline, output, offset = time.monotonic() + timeout_seconds, bytearray(), 0
    try:
        os.set_blocking(proc.stdin.fileno(), False); os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE); selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: _refuse("worker timed out")
                for key, _ in selector.select(min(remaining, 1)):
                    if key.fileobj is proc.stdin:
                        try: offset += os.write(proc.stdin.fileno(), raw[offset:offset + 65536])
                        except BrokenPipeError: selector.unregister(proc.stdin); proc.stdin.close(); continue
                        if offset == len(raw): selector.unregister(proc.stdin); proc.stdin.close()
                    else:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk: selector.unregister(proc.stdout); proc.stdout.close()
                        elif len(output) + len(chunk) > MAX_OUTPUT_BYTES: _refuse("worker output cap exceeded")
                        else: output.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0: _refuse("worker timed out")
        return subprocess.CompletedProcess(command, proc.wait(timeout=remaining), bytes(output))
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
        if proc.stdin is not None and not proc.stdin.closed: proc.stdin.close()
        if proc.stdout is not None and not proc.stdout.closed: proc.stdout.close()


def run_isolated_reconciliation_v4(*, expected_head, capture_inventory_raw=OBSERVED_CAPTURE_INVENTORY_BYTES,
        expected_capture_inventory_sha256=OBSERVED_CAPTURE_INVENTORY_SHA256, maximum_preview_requests=256, timeout_seconds=900):
    """Clean committed source supervisor -> isolated full replay -> sealed receipt.

The preview is exact original-order metadata, not a dispatch-capable selection.
An unsupported later journal/claim blocks this version rather than being skipped.
"""
    base = _base()
    _inventory(capture_inventory_raw, expected_capture_inventory_sha256, observed=True)
    if type(maximum_preview_requests) is not int or not 1 <= maximum_preview_requests <= MAX_PREVIEW_REQUESTS: _refuse("preview bound differs")
    try:
        before = base._repository_snapshot()
        if type(expected_head) is not str or _COMMIT.fullmatch(expected_head) is None or before != (expected_head, ""):
            _refuse("exact clean committed designated lane required")
        sources = base._source_snapshot(); current = dict(sources)
        if Path(__file__).resolve() != base.LANE_ROOT / SELF_PATH or any(_sha(current[p]) != sha for p, sha in _PINS.items()):
            _refuse("designated root/accepted source images differ")
        if (_sha(base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{base.EXECUTOR_PATH}")) != base.EXECUTOR_SHA256
                or current[base.DIAGNOSTIC_CAPTURE_PATH] != base._git("cat-file", "blob", f"{base.DIAGNOSTIC_CAPTURE_COMMIT}:{base.DIAGNOSTIC_CAPTURE_PATH}")):
            _refuse("historical acquisition Git bytes differ")
        for path, raw in sources:
            if base._git("cat-file", "blob", f"{expected_head}:{path}") != raw: _refuse("executed source is not the exact committed image")
        blobs = base._validate_historical_blobs(tuple((p, base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{p}")) for p, _ in base.HISTORICAL_FILES))
        bundle = {"repository_head": expected_head, "historical_sources": base._encode_sources(blobs), "current_sources": base._encode_sources(sources),
            "worker_source_b64": base64.b64encode(current[SELF_PATH]).decode("ascii"), "worker_source_sha256": _sha(current[SELF_PATH]),
            "base_source_sha256": _PINS[BASE_PATH], "capture_inventory_b64": base64.b64encode(capture_inventory_raw).decode("ascii"),
            "capture_inventory_sha256": expected_capture_inventory_sha256, "maximum_preview_requests": maximum_preview_requests}
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before: _refuse("lane changed before worker")
        result = _run_worker(_canonical(bundle), timeout_seconds)
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before: _refuse("lane changed during worker")
        if result.returncode != 0 or not 0 < len(result.stdout) <= MAX_OUTPUT_BYTES: _refuse("isolated reconciliation refused or exceeded output cap")
        body = _validate_body(json.loads(result.stdout), observed=True)
        if (body["repository_head"] != expected_head or body["maximum_preview_requests"] != maximum_preview_requests
                or body["capture_inventory_sha256"] != expected_capture_inventory_sha256
                or body["worker_source_sha256"] != _sha(current[SELF_PATH])
                or body["current_source_inventory_sha256"] != _digest([{"path": p, "sha256": _sha(raw)} for p, raw in sources])):
            _refuse("fresh worker/current consumer parent context differs")
        historical = dict(blobs)
        for row in body["executed_modules"]:
            raw = historical.get(row["path"]) if row["source_kind"] == "historical_git_blob" else current.get(row["path"])
            if raw is None or _sha(raw) != row["sha256"]: _refuse("executed source differs from captured image")
        raw = _canonical(body); receipt = ReconciledV4Receipt(raw, _TOKEN); _IMAGES[receipt] = raw
        return receipt
    except ReconciliationV4Error: raise
    except Exception: raise ReconciliationV4Error("REFUSED: bounded completed-v4 reconciliation failed") from None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Source-only read-only original+completed320 reconciliation")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-capture-inventory-sha256", required=True)
    parser.add_argument("--maximum-preview-requests", type=int, default=256)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        receipt = run_isolated_reconciliation_v4(**vars(args))
        sys.stdout.buffer.write(receipt.raw_bytes + b"\n"); sys.stdout.buffer.flush()
    except Exception:
        sys.stderr.write("REFUSED: completed-v4 reconciliation supervisor failed\n")
        raise SystemExit(1) from None
