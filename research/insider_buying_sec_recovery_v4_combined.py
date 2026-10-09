"""Genuinely replayed first64 closure and next bounded v4 continuation prefix.

The original 99,394 partition is reconstructed, not scraped from a receipt.
The independently captured/projected first64 is overlaid only after fresh
custody/projection replay and whole-registry exclusion. Unknown, incomplete or
ambiguous new claims refuse; they are never skipped into apparent eligibility.
No acquisition, old-v3 mutation, economic processing or readiness promotion.
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
import types
import weakref


VERSION = "INSETF-IB1B-COMBINED-V4-FIRST64-CONTINUATION-SELECTION-v1"
SELF_PATH = "research/insider_buying_sec_recovery_v4_combined.py"
BASE_PATH = "research/insider_buying_sec_recovery_v4_historical_replay.py"
VIEW_PATH = "research/insider_buying_sec_recovery_v4_source_view.py"
CAPTURE_PATH = "research/insider_buying_sec_recovery_v4_capture.py"
PROJECTION_PATH = "research/insider_buying_sec_recovery_v4_projection.py"
SELECTION_PATH = "research/insider_buying_sec_recovery_v4_selection.py"
_PINS = {BASE_PATH: "dedbddf5782da30359239049d46a48fbde7a3fd64ac0da458b40f32ca2f4f725",
    VIEW_PATH: "f5b09920b1a7b68079df664708f038e03c18279d4c7090e95a316ab330df2e9e",
    CAPTURE_PATH: "11ba9f33325ea01c1b38f83ffc7ce5a237c2a251545a26e8fad82a66fd70e9f0",
    PROJECTION_PATH: "8c78395b8a10fa5ffe3a8b556251dfddffd554ee08c625ead7f53e35775d3c08",
    SELECTION_PATH: "3df8e67531e5429bf0742bceafc6fdec817b26a07d83813fda0b4220bbb78e7b"}
PROJECTION_RECEIPT_SHA256 = "3a53e91be960eec7d7cfede08cd9d8888ecf8a715b0d48e45387a3fbc5d3cc19"
PROJECTION_ROWS_SHA256 = "7bda748f0fba8b645418fc36dad110d68fe1f2dabc73b141db73d1fa67c6d532"
PROJECTION_HEAD = "23c7a11d53a8d1c457bac34bdebe977d3d567d00"
PROJECTION_PARTS = ("artifacts", "insider_buying", "sec_recovery_v4_projection",
    "ib-sec-v4-projection-first64-20261007-once")
MAX_REQUESTS, MAX_OUTPUT_BYTES, MAX_TIMEOUT_SECONDS = 256, 1024 * 1024, 900
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")
_ID = re.compile(r"[a-z][a-z0-9-]{0,79}\Z")
_CLASSES = ("prior_completed", "offline_corrected_diagnostic", "remaining_selected_reuse",
            "v3_completed", "accepted_ambiguous_diagnostic", "originally_unattempted")
_TOKEN, _TEST_TOKEN = object(), object()
_IMAGES = weakref.WeakKeyDictionary()
_CAPTURED_BASE = None


class CombinedV4Error(ValueError):
    pass


def _refuse(reason):
    raise CombinedV4Error("REFUSED: " + reason)


def _base():
    return _CAPTURED_BASE or importlib.import_module("research.insider_buying_sec_recovery_v4_historical_replay")


def _canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _hash(body): return _sha(_canonical(body))


def _request(value):
    from research import insider_buying_sec_recovery_v4_selection as selection
    try: return selection._request(value)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise CombinedV4Error("REFUSED: combined request identity/schema differs") from None


def _authority():
    return {"source_authenticated": False, "official_acceptance_verified": False,
        "publication_time_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_evidence": False, "complete_corpus": False, "direct_ib1c_ingest_authorized": False,
        "dispatch_enabled": False, "qc_authorized": False, "backtest_authorized": False,
        "execution_authorized": False, "output_written": False,
        "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}


def _inventory(rows, runs):
    if (type(rows) is not list or len(rows) > 99394 or type(runs) is not list or len(runs) > 99394
            or any(type(row) is not dict or set(row) != {"name", "sha256"}
                or type(row["name"]) is not str or _NAME.fullmatch(row["name"]) is None
                or type(row["sha256"]) is not str or _SHA.fullmatch(row["sha256"]) is None for row in rows)
            or [row["name"] for row in rows] != sorted({row["name"] for row in rows})
            or any(type(name) is not str or _ID.fullmatch(name) is None for name in runs)
            or runs != sorted(set(runs))):
        _refuse("complete claims/run inventory schema or uniqueness differs")
    return {"claim_inventory": rows, "claim_inventory_count": len(rows),
            "claim_inventory_sha256": _hash(rows), "known_run_inventory": runs,
            "known_run_inventory_sha256": _hash(runs)}


def _registry_snapshot(root, *, expected_count, expected_runs):
    from research import insider_buying_sec_recovery_v4_capture as capture
    folders = []
    try:
        base = capture._Directory(Path(root).joinpath(*capture.ARTIFACT_PARTS)); folders.append(base)
        claims = capture._Directory(base.path / "claims"); folders.append(claims)
        runs = capture._Directory(base.path / "runs"); folders.append(runs)
        names, run_names = sorted(os.listdir(claims.fd)), sorted(os.listdir(runs.fd))
        if (type(expected_count) is not int or not 0 <= expected_count <= 99394 or len(names) != expected_count
                or run_names != list(expected_runs) or any(_NAME.fullmatch(name) is None for name in names)):
            _refuse("unknown, missing, incomplete or extra capture/claim blocks continuation")
        if base.read("capture.lock") != b"INSETF-v4-global-claim-lock\n":
            _refuse("shared registry lock byte identity differs")
        rows = [{"name": name, "sha256": _sha(claims.read(name))} for name in names]
        if sorted(os.listdir(claims.fd)) != names or sorted(os.listdir(runs.fd)) != run_names:
            _refuse("whole shared registry changed while snapshotting")
        for folder in folders: folder.check()
        return _inventory(rows, run_names)
    finally:
        for folder in reversed(folders): folder.close()


def _overlay_original_partition(original_requests, original_partition, closed_rows, *, maximum_requests):
    """Pure overlay only; caller descriptors do not mint an observed seal."""
    from research import insider_buying_sec_recovery_v4_selection as selection
    from research import insider_buying_sec_recovery_v4_projection as projection
    if (type(original_requests) is not tuple or not 1 <= len(original_requests) <= 99394
            or type(original_partition) is not list or len(original_partition) != len(original_requests)
            or type(closed_rows) is not list or not 1 <= len(closed_rows) <= MAX_REQUESTS
            or type(maximum_requests) is not int or not 1 <= maximum_requests <= MAX_REQUESTS):
        _refuse("combined original population, closure or bounded prefix differs")
    originals, accession_ids, eligible = [], set(), []
    counts = dict.fromkeys(_CLASSES, 0)
    for index, (request, partition) in enumerate(zip(original_requests, original_partition, strict=True)):
        request = _request(request)
        if request["accession_number"] in accession_ids: _refuse("original accession population repeats")
        accession_ids.add(request["accession_number"]); originals.append(request)
        if (type(partition) is not dict or set(partition) != {"global_index", "request_sha256", "source_class"}
                or type(partition["global_index"]) is not int or partition["global_index"] != index
                or partition["request_sha256"] != _hash(request) or partition["source_class"] not in _CLASSES):
            _refuse("ordered original partition/request identity differs")
        counts[partition["source_class"]] += 1
        if partition["source_class"] == "originally_unattempted": eligible.append(partition)
    if len(eligible) <= len(closed_rows): _refuse("no remaining original-unattempted continuation population")
    combined = [dict(row) for row in original_partition]
    bodies = set()
    for ordinal, (row, eligible_row) in enumerate(zip(closed_rows, eligible[:len(closed_rows)], strict=True)):
        if (type(row) is not dict or set(row) != {"ordinal", "global_index", "request_sha256", "target", "claim_sha256",
                "start_sha256", "result_sha256", "raw_parent", "disposition", "projection"}
                or type(row["ordinal"]) is not int or row["ordinal"] != ordinal
                or type(row["global_index"]) is not int or row["global_index"] != eligible_row["global_index"]
                or row["request_sha256"] != eligible_row["request_sha256"]
                or row["disposition"] != "complete_parent_projected_noncanonical"
                or any(type(row[key]) is not str or _SHA.fullmatch(row[key]) is None
                    for key in ("claim_sha256", "start_sha256", "result_sha256"))):
            _refuse("first completed/projected closure is not exact original eligible prefix")
        request = originals[row["global_index"]]
        if row["target"] != projection._target(request).to_payload():
            _refuse("closure exact locator/master/issuer/filing target differs")
        raw = row["raw_parent"]
        if (type(raw) is not dict or set(raw) != {"sha256", "size_bytes"}
                or type(raw["sha256"]) is not str or _SHA.fullmatch(raw["sha256"]) is None
                or raw["sha256"] in bodies or type(raw["size_bytes"]) is not int
                or not 0 < raw["size_bytes"] <= 8 * 1024 * 1024):
            _refuse("closure parent uniqueness or byte bounds differ")
        bodies.add(raw["sha256"])
        combined[row["global_index"]]["source_class"] = "fresh_v4_completed"
    remaining = eligible[len(closed_rows):]
    selected = [{**row, "request": originals[row["global_index"]]} for row in remaining[:maximum_requests]]
    combined_counts = {**counts, "fresh_v4_completed": len(closed_rows)}
    combined_counts["originally_unattempted"] -= len(closed_rows)
    return {"original_class_counts": counts, "combined_class_counts": combined_counts,
        "total_parents": len(originals), "original_unattempted_count": len(eligible),
        "remaining_unattempted_count": len(remaining), "prior_source_bound_count": len(originals) - len(eligible),
        "combined_request_bound_custody_count": len(originals) - len(remaining),
        "combined_partition_sha256": _hash(combined), "remaining_inventory_sha256": _hash(remaining),
        "maximum_requests": len(selected), "requests": selected, "selected_prefix_sha256": _hash(selected)}


def _rows(rows, maximum_requests):
    from research import insider_buying_sec_recovery_v4_selection as selection
    if type(rows) is not list or type(maximum_requests) is not int or not 1 <= maximum_requests <= MAX_REQUESTS or len(rows) != maximum_requests:
        _refuse("combined selected prefix cardinality differs")
    previous, accessions = -1, set()
    for row in rows:
        if (type(row) is not dict or set(row) != {"global_index", "request_sha256", "source_class", "request"}
                or type(row["global_index"]) is not int or not previous < row["global_index"] < 99394
                or row["source_class"] != "originally_unattempted"):
            _refuse("combined prefix ordinal/order/class differs")
        request = _request(row["request"])
        if row["request_sha256"] != _hash(request) or request["accession_number"] in accessions:
            _refuse("combined prefix request hash or accession uniqueness differs")
        previous = row["global_index"]; accessions.add(request["accession_number"])


def _validate_body(body, *, observed):
    from research import insider_buying_sec_recovery_v4_projection as projection
    base = _base()
    keys = {"kind", "scope", "repository_head", "worker_source_sha256", "worker_bootstrap_sha256", "current_source_inventory_sha256",
        "executed_modules", "source_view", "replay_anchors", "first64_capture_report_sha256", "first64_projection_receipt_sha256",
        "first64_projection_ordered_rows_sha256", "stopped_v3_disposition", "authority", "source_bound_union_scope",
        "claim_inventory", "claim_inventory_count", "claim_inventory_sha256", "known_run_inventory", "known_run_inventory_sha256",
        "original_class_counts", "combined_class_counts", "total_parents", "original_unattempted_count", "remaining_unattempted_count",
        "prior_source_bound_count", "combined_request_bound_custody_count", "combined_partition_sha256", "remaining_inventory_sha256",
        "maximum_requests", "requests", "selected_prefix_sha256"}
    if (type(observed) is not bool or type(body) is not dict or set(body) != keys or body["kind"] != VERSION
            or body["scope"] != ("observed_source_only_combined_first64" if observed else "invented_test_only")
            or type(body["repository_head"]) is not str or _COMMIT.fullmatch(body["repository_head"]) is None):
        _refuse("combined selection schema/scope/HEAD differs")
    _rows(body["requests"], body["maximum_requests"])
    if body["selected_prefix_sha256"] != _hash(body["requests"]): _refuse("combined next prefix digest differs")
    inventory = _inventory(body["claim_inventory"], body["known_run_inventory"])
    if any(body[k] != value or type(body[k]) is not type(value) for k, value in inventory.items()):
        _refuse("combined whole-registry digest/count differs")
    names = {row["name"] for row in body["claim_inventory"]}
    if any(_sha(row["request"]["accession_number"].encode("ascii")) + ".json" in names for row in body["requests"]):
        _refuse("selected request already has a permanent claim")
    if body["authority"] != _authority() or any(type(body["authority"][k]) is not type(v) for k, v in _authority().items()):
        _refuse("combined authority differs")
    digest_keys = ("worker_source_sha256", "worker_bootstrap_sha256", "current_source_inventory_sha256", "first64_capture_report_sha256",
        "first64_projection_receipt_sha256", "first64_projection_ordered_rows_sha256", "combined_partition_sha256", "remaining_inventory_sha256")
    if any(type(body[k]) is not str or _SHA.fullmatch(body[k]) is None for k in digest_keys): _refuse("combined digest differs")
    if not observed: return body
    view = importlib.import_module("research.insider_buying_sec_recovery_v4_source_view")
    if (body["first64_capture_report_sha256"] != projection.REPORT_SHA256
            or body["first64_projection_receipt_sha256"] != PROJECTION_RECEIPT_SHA256
            or body["first64_projection_ordered_rows_sha256"] != PROJECTION_ROWS_SHA256
            or body["worker_bootstrap_sha256"] != _sha(_BOOTSTRAP.encode()) or body["replay_anchors"] != view._REPLAY_HASHES
            or body["original_class_counts"] != base._COUNTS or any(type(v) is not int for v in body["original_class_counts"].values())
            or body["combined_class_counts"] != {**base._COUNTS, "fresh_v4_completed": 64, "originally_unattempted": 79804}
            or any(type(v) is not int for v in body["combined_class_counts"].values())
            or any(type(body[k]) is not int or body[k] != v for k, v in (("total_parents", 99394), ("original_unattempted_count", 79868),
                ("remaining_unattempted_count", 79804), ("prior_source_bound_count", 19526), ("combined_request_bound_custody_count", 19590),
                ("claim_inventory_count", 64)))
            or body["known_run_inventory"] != [projection.CAPTURE_ID]
            or body["stopped_v3_disposition"] != "preserved_unresolved_not_resumable"
            or body["source_bound_union_scope"] != "request_bound_noncanonical_custody_only"
            or any(row["global_index"] <= 11574 for row in body["requests"])):
        _refuse("observed combined closure/counts/source scope differ")
    proof = body["source_view"]
    if (type(proof) is not dict or set(proof) != {"kind", "historical_commit", "historical_validator_sha256", "files",
            "validator_function_name", "ordered_read_cycles", "source_read_count", "source_read_trace_sha256", "callsite_bound"}
            or proof.get("kind") != view.SOURCE_VIEW_VERSION or proof.get("validator_function_name") != "_validator_source_sha256"
            or proof.get("historical_commit") != base.HISTORICAL_COMMIT
            or proof.get("historical_validator_sha256") != base.HISTORICAL_VALIDATOR_SHA256
            or proof.get("files") != [{"path": p, "sha256": s} for p, s in base.HISTORICAL_FILES]
            or type(proof.get("ordered_read_cycles")) is not int or not 1 <= proof["ordered_read_cycles"] <= 512
            or type(proof.get("source_read_count")) is not int or proof["source_read_count"] != 4 * proof["ordered_read_cycles"]
            or proof.get("source_read_trace_sha256") != view._source_read_trace_digest(proof["ordered_read_cycles"])
            or proof.get("callsite_bound") is not True):
        _refuse("combined historical source-view execution proof differs")
    trace = body["executed_modules"]
    if type(trace) is not list or not 7 <= len(trace) <= 512: _refuse("combined executed source inventory differs")
    seen, historical = {}, {}
    for row in trace:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_kind"}
                or type(row["path"]) is not str or row["path"] in seen or type(row["sha256"]) is not str
                or _SHA.fullmatch(row["sha256"]) is None or row["source_kind"] not in {"historical_git_blob", "current_source_snapshot"}):
            _refuse("combined executing source row differs")
        base._module_name(row["path"]); seen[row["path"]] = row["sha256"]
        if row["source_kind"] == "historical_git_blob": historical[row["path"]] = row["sha256"]
    if (historical != dict(base.HISTORICAL_FILES) or seen.get(SELF_PATH) != body["worker_source_sha256"]
            or any(seen.get(path) != sha for path, sha in _PINS.items())):
        _refuse("required accepted source images were not executed")
    return body


def validate_combined_v4_selection_payload(body, *, observed):
    """Independent journal verification; does not mint a dispatch object."""
    return _validate_body(body, observed=observed)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class CombinedV4Selection:
    _raw: bytes
    _token: object
    def to_payload(self):
        if type(self) is not CombinedV4Selection or self._token is not _TOKEN or type(self._raw) is not bytes or _IMAGES.get(self) != self._raw:
            _refuse("genuine factory-bound combined selection required")
        return _validate_body(json.loads(self._raw), observed=True)
    @property
    def raw_bytes(self): self.to_payload(); return self._raw
    @property
    def sha256(self): return _sha(self.raw_bytes)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class InventedCombinedV4Selection:
    _raw: bytes
    _token: object
    def to_payload(self):
        if type(self) is not InventedCombinedV4Selection or self._token is not _TEST_TOKEN or type(self._raw) is not bytes or _IMAGES.get(self) != self._raw:
            _refuse("genuine factory-bound invented combined selection required")
        return _validate_body(json.loads(self._raw), observed=False)
    @property
    def raw_bytes(self): self.to_payload(); return self._raw
    @property
    def sha256(self): return _sha(self.raw_bytes)


def make_invented_combined_v4_selection(requests, *, repository_head="a" * 40, claim_inventory=(), known_run_inventory=()):
    from research import insider_buying_sec_recovery_v4_selection as selection
    if type(requests) is not tuple or not 1 <= len(requests) <= MAX_REQUESTS: _refuse("invented combined request bound differs")
    rows = [{"global_index": index + 100, "request_sha256": _hash(_request(req)),
             "source_class": "originally_unattempted", "request": _request(req)} for index, req in enumerate(requests)]
    body = {"kind": VERSION, "scope": "invented_test_only", "repository_head": repository_head,
        **{k: "0" * 64 for k in ("worker_source_sha256", "worker_bootstrap_sha256", "current_source_inventory_sha256",
            "first64_capture_report_sha256", "first64_projection_receipt_sha256", "first64_projection_ordered_rows_sha256",
            "combined_partition_sha256", "remaining_inventory_sha256")}, "executed_modules": [], "source_view": None,
        "replay_anchors": {}, "original_class_counts": {}, "combined_class_counts": {}, "total_parents": len(rows),
        "original_unattempted_count": len(rows), "remaining_unattempted_count": len(rows), "prior_source_bound_count": 0,
        "combined_request_bound_custody_count": 0, "stopped_v3_disposition": "not-observed-fixture",
        "source_bound_union_scope": "invented_test_only", "maximum_requests": len(rows), "requests": rows,
        "selected_prefix_sha256": _hash(rows), **_inventory(list(claim_inventory), list(known_run_inventory)), "authority": _authority()}
    _validate_body(body, observed=False)
    raw = _canonical(body); result = InventedCombinedV4Selection(raw, _TEST_TOKEN); _IMAGES[result] = raw
    return result


def _first64_closure(base):
    from research import insider_buying_sec_recovery_v4_capture as capture
    from research import insider_buying_sec_recovery_v4_projection as projection
    before = _registry_snapshot(base.LANE_ROOT, expected_count=64, expected_runs=(projection.CAPTURE_ID,))
    folder = capture._Directory(base.LANE_ROOT.joinpath(*PROJECTION_PARTS))
    try:
        raw = folder.read("receipt.json", cap=MAX_OUTPUT_BYTES)
        if len(raw) != 94936 or _sha(raw) != PROJECTION_RECEIPT_SHA256: _refuse("actual saved projection receipt anchor differs")
        saved = capture._decode(raw)
        if (saved["kind"] != projection.VERSION or saved["scope"] != "observed_first64_capture"
                or saved["capture_git_commit"] != projection.CAPTURE_HEAD or saved["capture_report_sha256"] != projection.REPORT_SHA256
                or saved["consumer"]["declared_projection_repository_head"] != PROJECTION_HEAD
                or saved["consumer"]["projection_source_sha256"] != _PINS[PROJECTION_PATH]
                or saved["ordered_rows_sha256"] != PROJECTION_ROWS_SHA256 or saved["authority"] != projection._authority()):
            _refuse("saved producer/consumer projection lineage differs")
        fresh = projection._project_root(projection.CAPTURE_ID, projection.REPORT_SHA256, root=base.LANE_ROOT,
            observed=True, consumer=lambda: {"scope": "combined_current_source_reprojection_not_original_consumer"}).to_payload()
        if (fresh["rows"] != saved["rows"] or fresh["ordered_rows_sha256"] != PROJECTION_ROWS_SHA256
                or fresh["counts"] != {"header_bound_retained": 64, "complete_parent_projected": 64,
                    "complete_parent_grammar_quarantined": 0, "raw_parent_bytes": 504050}
                or saved["counts"] != fresh["counts"] or _sha(folder.read("receipt.json", cap=MAX_OUTPUT_BYTES)) != PROJECTION_RECEIPT_SHA256):
            _refuse("fresh projection/actual saved rows or accounting differ")
        after = _registry_snapshot(base.LANE_ROOT, expected_count=64, expected_runs=(projection.CAPTURE_ID,))
        if after != before: _refuse("whole permanent claim registry changed during closure replay")
        folder.check()
        return fresh["rows"], before
    finally: folder.close()


def _install_source_context(base, blobs, sources):
    """Source-only wiring; no roots, transport or observed receipts involved."""
    if any(name.split(".")[0] in {"data", "research", "ml"} for name in sys.modules):
        _refuse("combined worker inherited lane modules")
    current = dict(sources)
    finder = base._HistoricalBlobFinder(blobs, sources)
    finder.executed.extend({"path": path, "sha256": _sha(current[path]), "source_kind": "current_source_snapshot"}
                          for path in (BASE_PATH, SELF_PATH))
    sys.meta_path.insert(0, finder)
    sys.setprofile(finder.profile)
    view = importlib.import_module("research.insider_buying_sec_recovery_v4_source_view")
    view._CAPTURED_BASE = base
    # Do not silently deduplicate a second execution of the accepted base.
    selection = importlib.import_module("research.insider_buying_sec_recovery_v4_selection")
    selection._CAPTURED_BASE = base
    return finder, view


def _worker_main(bundle):
    base, finder, previous = _base(), None, sys.getprofile()
    try:
        blobs = base._validate_historical_blobs(base._decode_sources(bundle["historical_sources"]))
        sources = base._decode_sources(bundle["current_sources"]); current = dict(sources)
        if any(_sha(current[p]) != sha for p, sha in _PINS.items()) or _sha(current[SELF_PATH]) != bundle["worker_source_sha256"]:
            _refuse("combined captured/accepted source bytes differ")
        base._assert_sources_unchanged(sources)
        finder, view_module = _install_source_context(base, blobs, sources)
        union = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_union")
        campaign = importlib.import_module("research.insider_buying_sec_all_form4_parent_campaign")
        prior = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_preflight")
        completed = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_verifier")
        partial = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_partial_verifier")
        diagnostic = importlib.import_module("research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier")
        v4 = importlib.import_module("research.insider_buying.sec_recovery_v4_plan")
        projection = importlib.import_module("research.insider_buying_sec_recovery_v4_projection")
        registry_before = _registry_snapshot(base.LANE_ROOT, expected_count=64, expected_runs=(projection.CAPTURE_ID,))
        with view_module.HistoricalSourceView(blobs, union) as view:
            def source_replay():
                return union.preflight_observed_all_form4_parent_recovery_union(*base.SOURCE_ROOTS,
                    diagnostic_capture_git_commit=union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
                    expected_diagnostic_report_sha256=union.OBSERVED_DIAGNOSTIC_REPORT_SHA256)
            source = source_replay(); plan = campaign._build_real_plan(*base.SOURCE_ROOTS[:6])
            expectation = prior.PartialCampaignExpectation(capture_git_commit=prior.PRIOR_CAPTURE_GIT_COMMIT,
                shard_report_sha256s=prior.PRIOR_SHARD_REPORT_SHA256S, completed_counts=(8192, 1347), reused_counts=(972, 226), total_attempt_count=8342)
            def partial_replay():
                stopped = partial._verify_partial(plan, source, base.SOURCE_ROOTS[6], base.SOURCE_ROOTS[7], base.SOURCE_ROOTS[5], base.V3_ROOT,
                    prior_expectation=expectation, capture_git_commit=base.HISTORICAL_COMMIT, capture_code_sha256=base.EXECUTOR_SHA256)
                partial._require_observed_anchors(stopped)
                if stopped.completed_new_count != 1846 or stopped.attempt_count != 1847: _refuse("stopped v3 counts differ")
                return stopped
            stopped = partial_replay()
            accepted = diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT, expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256)
            classes, _ = completed._source_classes(plan, source)
            p = {key: getattr(stopped, key) for key in (*v4._PARTIAL_HASHES, *v4._PARTIAL_INTS)}
            d = {key: getattr(accepted, key) for key in (*v4._DIAGNOSTIC_HASHES, "diagnostic_capture_git_commit", "pending_global_index", "body_size_bytes")}
            proposal = v4.build_recovery_v4_offline_plan(tuple(req.to_payload() for req in plan.requests), tuple(classes), p, d,
                v4.bind_v3_historical_validator(base.HISTORICAL_COMMIT, blobs)); original = proposal.to_payload()
            closed, registry = _first64_closure(base)
            overlay = _overlay_original_partition(tuple(req.to_payload() for req in plan.requests), original["partition"], closed,
                maximum_requests=bundle["maximum_requests"])
            if registry != registry_before: _refuse("new claims appeared during original retained-root reconstruction")
            if source_replay() != source or partial_replay() != stopped: _refuse("original retained roots changed during combined verification")
            if diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                    capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT, expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256) != accepted:
                _refuse("separate ambiguous diagnostic changed")
            closed_after, registry_after = _first64_closure(base)
            if closed_after != closed or registry_after != registry: _refuse("fresh capture/projection/claims changed during combined verification")
        base._assert_sources_unchanged(sources)
        if finder.called != {path for path, _ in base.HISTORICAL_FILES}: _refuse("exact historical function execution was not observed")
        payload = {"kind": VERSION, "scope": "observed_source_only_combined_first64", "repository_head": bundle["repository_head"],
            "worker_source_sha256": bundle["worker_source_sha256"], "worker_bootstrap_sha256": _sha(_BOOTSTRAP.encode()),
            "current_source_inventory_sha256": _hash([{"path": path, "sha256": _sha(raw)} for path, raw in sources]),
            "executed_modules": finder.executed, "source_view": view.proof(), "replay_anchors": {
                "source_union_sha256": _hash(source), "partial_descriptor_sha256": _hash(p), "diagnostic_descriptor_sha256": _hash(d),
                "v4_plan_sha256": proposal.sha256, "partition_sha256": original["partition_sha256"],
                "proposed_unattempted_inventory_sha256": original["proposed_unattempted_inventory_sha256"]},
            "first64_capture_report_sha256": projection.REPORT_SHA256, "first64_projection_receipt_sha256": PROJECTION_RECEIPT_SHA256,
            "first64_projection_ordered_rows_sha256": PROJECTION_ROWS_SHA256, "stopped_v3_disposition": "preserved_unresolved_not_resumable",
            "source_bound_union_scope": "request_bound_noncanonical_custody_only", **overlay, **registry, "authority": _authority()}
        _validate_body(payload, observed=True)
        raw = _canonical(payload)
        if len(raw) + 1 > MAX_OUTPUT_BYTES: _refuse("combined bounded prefix output exceeds cap")
        sys.stdout.buffer.write(raw + b"\n"); sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("REFUSED: isolated combined v4 replay failed\n")
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
base=types.ModuleType('_combined_v4_base');base.__file__=sys.argv[2];sys.modules[base.__name__]=base
exec(compile(s,base.__file__,'exec',dont_inherit=True),base.__dict__)
sys.addaudithook(base._audit_event)
s=base64.b64decode(b['worker_source_b64'],validate=True)
if hashlib.sha256(s).hexdigest()!=b['worker_source_sha256']: raise SystemExit(2)
m=types.ModuleType('_combined_v4_worker');m.__file__=sys.argv[1];sys.modules[m.__name__]=m
exec(compile(s,m.__file__,'exec',dont_inherit=True),m.__dict__)
m._CAPTURED_BASE=base;m._worker_main(b)
"""


def _run_worker(raw, timeout_seconds):
    base = _base()
    if type(raw) is not bytes or not 0 < len(raw) <= base._MAX_INPUT_BYTES: _refuse("combined worker input cap differs")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS: _refuse("combined worker timeout differs")
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
                if remaining <= 0: _refuse("combined worker timed out")
                for key, _ in selector.select(min(remaining, 1)):
                    if key.fileobj is proc.stdin:
                        try: offset += os.write(proc.stdin.fileno(), raw[offset:offset + 65536])
                        except BrokenPipeError: selector.unregister(proc.stdin); proc.stdin.close(); continue
                        if offset == len(raw): selector.unregister(proc.stdin); proc.stdin.close()
                    else:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk: selector.unregister(proc.stdout); proc.stdout.close()
                        elif len(output) + len(chunk) > MAX_OUTPUT_BYTES: _refuse("combined worker output cap exceeded")
                        else: output.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0: _refuse("combined worker timed out")
        return subprocess.CompletedProcess(command, proc.wait(timeout=remaining), bytes(output))
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
        if proc.stdin is not None and not proc.stdin.closed: proc.stdin.close()
        if proc.stdout is not None and not proc.stdout.closed: proc.stdout.close()


def run_isolated_combined_v4(*, expected_head, maximum_requests=64, timeout_seconds=900):
    """Clean committed supervisor -> denied replay -> genuinely sealed selection."""
    base = _base()
    if type(maximum_requests) is not int or not 1 <= maximum_requests <= MAX_REQUESTS: _refuse("next bounded prefix differs")
    try:
        before = base._repository_snapshot()
        if type(expected_head) is not str or _COMMIT.fullmatch(expected_head) is None or before != (expected_head, ""):
            _refuse("exact clean committed combined lane required")
        sources = base._source_snapshot(); current = dict(sources)
        if Path(__file__).resolve() != base.LANE_ROOT / SELF_PATH or any(_sha(current[p]) != sha for p, sha in _PINS.items()):
            _refuse("combined designated root or accepted byte pins differ")
        if (_sha(base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{base.EXECUTOR_PATH}")) != base.EXECUTOR_SHA256
                or current[base.DIAGNOSTIC_CAPTURE_PATH] != base._git("cat-file", "blob",
                    f"{base.DIAGNOSTIC_CAPTURE_COMMIT}:{base.DIAGNOSTIC_CAPTURE_PATH}")):
            _refuse("historical acquisition executor or diagnostic capture Git bytes differ")
        for path, raw in sources:
            if base._git("cat-file", "blob", f"{expected_head}:{path}") != raw: _refuse("combined replay source is not exact committed image")
        blobs = base._validate_historical_blobs(tuple((p, base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{p}")) for p, _ in base.HISTORICAL_FILES))
        bundle = {"repository_head": expected_head, "historical_sources": base._encode_sources(blobs), "current_sources": base._encode_sources(sources),
            "worker_source_b64": base64.b64encode(current[SELF_PATH]).decode("ascii"), "worker_source_sha256": _sha(current[SELF_PATH]),
            "base_source_sha256": _PINS[BASE_PATH], "maximum_requests": maximum_requests}
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before: _refuse("combined lane changed before worker")
        result = _run_worker(_canonical(bundle), timeout_seconds)
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before: _refuse("combined lane changed during worker")
        if result.returncode != 0 or not 0 < len(result.stdout) <= MAX_OUTPUT_BYTES: _refuse("combined worker refused or output exceeded cap")
        body = _validate_body(json.loads(result.stdout), observed=True)
        if (body["repository_head"] != expected_head or body["maximum_requests"] != maximum_requests
                or body["worker_source_sha256"] != _sha(current[SELF_PATH])
                or body["current_source_inventory_sha256"] != _hash([{"path": p, "sha256": _sha(raw)} for p, raw in sources])):
            _refuse("combined worker exact parent context differs")
        historical = dict(blobs)
        for row in body["executed_modules"]:
            raw = historical.get(row["path"]) if row["source_kind"] == "historical_git_blob" else current.get(row["path"])
            if raw is None or _sha(raw) != row["sha256"]: _refuse("combined executed source differs from captured images")
        raw = _canonical(body); selected = CombinedV4Selection(raw, _TOKEN); _IMAGES[selected] = raw
        return selected
    except CombinedV4Error: raise
    except Exception:
        raise CombinedV4Error("REFUSED: bounded combined v4 replay failed") from None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Genuine offline combined-v4 replay and next prefix")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--maximum-requests", type=int, default=64)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        result = run_isolated_combined_v4(**vars(args))
        sys.stdout.buffer.write(result.raw_bytes + b"\n"); sys.stdout.buffer.flush()
    except Exception:
        sys.stderr.write("REFUSED: combined v4 supervisor failed\n")
        raise SystemExit(1) from None
