"""Fresh first-prefix selection from genuinely executed, isolated SEC custody.

No transport, journal mutation or contact access. The unchanged accepted
HistoricalSourceView and exact four historical modules reconstruct/recheck all
99,394 requests and the stopped root. Only first <=64 originally-unattempted
public SEC request descriptors leave the denied worker. This is a new replay
profile, not an assertion that the old aggregate-only worker emitted requests.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
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


VERSION = "INSETF-IB1B-FRESH-FIRST-PREFIX-SELECTION-v4"
SELF_PATH = "research/insider_buying_sec_recovery_v4_selection.py"
BASE_PATH = "research/insider_buying_sec_recovery_v4_historical_replay.py"
VIEW_PATH = "research/insider_buying_sec_recovery_v4_source_view.py"
ACCEPTED_VIEW_SHA256 = "f5b09920b1a7b68079df664708f038e03c18279d4c7090e95a316ab330df2e9e"
ACCEPTED_BASE_SHA256 = "dedbddf5782da30359239049d46a48fbde7a3fd64ac0da458b40f32ca2f4f725"
MAX_REQUESTS = 64
MAX_OUTPUT_BYTES = 256 * 1024
_CAPTURED_BASE = None
_TOKEN = object()
_TEST_TOKEN = object()
_FACTORY_IMAGES = weakref.WeakKeyDictionary()
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_REQUEST_KEYS = {"period", "accession_number", "form_type", "filing_date", "issuer_cik",
                 "archive_path", "submission_row_id", "parsed_lineage_hash", "master_source_sha256", "url"}


class FreshV4SelectionError(ValueError):
    pass


def _refuse(reason):
    raise FreshV4SelectionError("REFUSED: " + reason)


def _base():
    return _CAPTURED_BASE or importlib.import_module("research.insider_buying_sec_recovery_v4_historical_replay")


def _canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(body):
    return _sha(_canonical(body))


def _request(value):
    from datetime import date
    if (type(value) is not dict or set(value) != _REQUEST_KEYS
            or any(type(v) is not str for v in value.values())):
        _refuse("request schema differs")
    accession = value["accession_number"]
    if (re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession) is None
            or re.fullmatch(r"[0-9]{1,10}", value["issuer_cik"]) is None
            or int(value["issuer_cik"]) == 0 or value["form_type"] not in {"4", "4/A"}
            or value["period"] not in {"2022Q4", "2023Q1"}
            or any(_SHA.fullmatch(value[k]) is None for k in
                   ("submission_row_id", "parsed_lineage_hash", "master_source_sha256"))
            or re.fullmatch(r"edgar/data/[0-9]{1,10}/" + re.escape(accession) + r"\.txt", value["archive_path"]) is None
            or int(value["archive_path"].split("/")[2]) == 0
            or value["url"] != "https://www.sec.gov/Archives/" + value["archive_path"]):
        _refuse("request identity or fixed SEC locator differs")
    try: filed = date.fromisoformat(value["filing_date"])
    except ValueError: _refuse("request filing date is malformed")
    if filed.isoformat() != value["filing_date"] or value["period"] != f"{filed.year}Q{(filed.month - 1) // 3 + 1}":
        _refuse("request date differs from its frozen quarter")
    return dict(value)


def _rows(rows, count):
    if type(count) is not int or not 1 <= count <= MAX_REQUESTS or type(rows) is not list or len(rows) != count:
        _refuse("selected first-prefix cardinality differs")
    previous, accessions = -1, set()
    for row in rows:
        if (type(row) is not dict or set(row) != {"global_index", "request_sha256", "source_class", "request"}
                or type(row["global_index"]) is not int or not previous < row["global_index"] < 99394
                or row["source_class"] != "originally_unattempted"):
            _refuse("selected order, class or ordinal differs")
        item = _request(row["request"])
        if row["request_sha256"] != _hash(item) or item["accession_number"] in accessions:
            _refuse("selected request hash or accession uniqueness differs")
        previous = row["global_index"]
        accessions.add(item["accession_number"])


def _validate_body(body, *, observed):
    base = _base()
    keys = {"kind", "scope", "repository_head", "worker_source_sha256", "worker_bootstrap_sha256",
            "accepted_source_view_sha256", "accepted_base_sha256", "current_source_inventory_sha256",
            "executed_modules", "historical_commit", "historical_validator_sha256", "historical_files",
            "historical_function_paths", "source_view", "replay_anchors", "class_counts", "total_parents",
            "source_bound_count", "v3_completed_count", "v3_attempt_count", "stopped_v3_disposition",
            "maximum_requests", "requests", "selected_prefix_sha256", "isolation", "authority"}
    if type(body) is not dict or set(body) != keys or body["kind"] != VERSION:
        _refuse("selection schema differs")
    if (body["scope"] != ("observed_isolated_retained_root_replay" if observed else "invented_test_only")
            or type(body["repository_head"]) is not str or _COMMIT.fullmatch(body["repository_head"]) is None):
        _refuse("selection scope or repository lineage differs")
    _rows(body["requests"], body["maximum_requests"])
    if body["selected_prefix_sha256"] != _hash(body["requests"]):
        _refuse("selected prefix digest differs")
    hashes = ("worker_source_sha256", "worker_bootstrap_sha256", "accepted_source_view_sha256",
              "accepted_base_sha256", "current_source_inventory_sha256", "historical_validator_sha256")
    if any(type(body[k]) is not str or _SHA.fullmatch(body[k]) is None for k in hashes):
        _refuse("selection source digest differs")
    expected_authority = {"source_authenticated": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_evidence": False, "complete_corpus": False, "dispatch_enabled": False,
        "qc_authorized": False, "backtest_authorized": False, "execution_authorized": False,
        "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}
    if (body["authority"] != expected_authority or type(body["authority"]) is not dict
            or any(type(body["authority"][k]) is not type(v) for k, v in expected_authority.items())):
        _refuse("selection authority differs")
    if not observed:
        if (body["isolation"] != {"observed_worker_execution": False}
                or body["isolation"]["observed_worker_execution"] is not False):
            _refuse("invented selection cannot claim worker isolation")
        return body
    view = importlib.import_module("research.insider_buying_sec_recovery_v4_source_view")
    if (body["accepted_source_view_sha256"] != ACCEPTED_VIEW_SHA256
            or body["accepted_base_sha256"] != ACCEPTED_BASE_SHA256
            or body["worker_bootstrap_sha256"] != _sha(_BOOTSTRAP.encode())
            or body["historical_commit"] != base.HISTORICAL_COMMIT
            or body["historical_validator_sha256"] != base.HISTORICAL_VALIDATOR_SHA256
            or body["historical_files"] != [{"path": p, "sha256": s} for p, s in base.HISTORICAL_FILES]
            or body["historical_function_paths"] != [p for p, _ in base.HISTORICAL_FILES]
            or body["replay_anchors"] != view._REPLAY_HASHES
            or body["class_counts"] != base._COUNTS
            or any(type(body["class_counts"][k]) is not int for k in base._COUNTS)
            or any(type(body[k]) is not int or body[k] != v for k, v in
                   (("total_parents", 99394), ("source_bound_count", 19526), ("v3_completed_count", 1846), ("v3_attempt_count", 1847)))
            or body["stopped_v3_disposition"] != "preserved_unresolved_not_resumable"
            or body["isolation"] != {"os_network_denied": True, "os_file_writes_denied": True,
                 "os_process_fork_denied": True, "audit_additional_processes_denied": True, "source_only_lane_imports": True}
            or any(v is not True for v in body["isolation"].values())):
        _refuse("observed replay anchors, counts or isolation differ")
    proof = body["source_view"]
    if (type(proof) is not dict or set(proof) != {"kind", "historical_commit", "historical_validator_sha256", "files",
            "validator_function_name", "ordered_read_cycles", "source_read_count", "source_read_trace_sha256", "callsite_bound"}
            or proof["kind"] != view.SOURCE_VIEW_VERSION or proof["historical_commit"] != base.HISTORICAL_COMMIT
            or proof["historical_validator_sha256"] != base.HISTORICAL_VALIDATOR_SHA256
            or proof["files"] != body["historical_files"] or proof["validator_function_name"] != "_validator_source_sha256"
            or type(proof["ordered_read_cycles"]) is not int or not 1 <= proof["ordered_read_cycles"] <= 512
            or type(proof["source_read_count"]) is not int or proof["source_read_count"] != proof["ordered_read_cycles"] * 4
            or proof["source_read_trace_sha256"] != view._source_read_trace_digest(proof["ordered_read_cycles"])
            or proof["callsite_bound"] is not True):
        _refuse("historical executing-source read proof differs")
    trace = body["executed_modules"]
    if type(trace) is not list or not 7 <= len(trace) <= 512:
        _refuse("executed source inventory differs")
    seen, historical = set(), {}
    for row in trace:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_kind"}
                or type(row["path"]) is not str or row["path"] in seen
                or type(row["sha256"]) is not str or _SHA.fullmatch(row["sha256"]) is None
                or row["source_kind"] not in {"historical_git_blob", "current_source_snapshot"}):
            _refuse("executed source row differs")
        base._module_name(row["path"])
        seen.add(row["path"])
        if row["source_kind"] == "historical_git_blob": historical[row["path"]] = row["sha256"]
    if historical != dict(base.HISTORICAL_FILES):
        _refuse("exact four historical modules were not executed")
    for path, digest in ((SELF_PATH, body["worker_source_sha256"]),
                         (VIEW_PATH, ACCEPTED_VIEW_SHA256), (BASE_PATH, ACCEPTED_BASE_SHA256)):
        if {"path": path, "sha256": digest, "source_kind": "current_source_snapshot"} not in trace:
            _refuse("selection worker or accepted primitive execution differs")
    return body


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class FreshV4Selection:
    _raw: bytes = field(repr=False)
    _token: object = field(repr=False)
    _factory_raw: bytes = field(repr=False)

    def to_payload(self):
        if (type(self) is not FreshV4Selection or self._token is not _TOKEN or type(self._raw) is not bytes
                or self._raw != self._factory_raw or _FACTORY_IMAGES.get(self) != self._raw):
            _refuse("selection was not genuinely built here or was altered")
        return _validate_body(json.loads(self._raw), observed=True)

    @property
    def sha256(self):
        self.to_payload()
        return _sha(self._raw)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class InventedV4Selection:
    _raw: bytes = field(repr=False)
    _token: object = field(repr=False)
    _factory_raw: bytes = field(repr=False)

    def to_payload(self):
        if (type(self) is not InventedV4Selection or self._token is not _TEST_TOKEN or type(self._raw) is not bytes
                or self._raw != self._factory_raw or _FACTORY_IMAGES.get(self) != self._raw):
            _refuse("invented selection was altered")
        return _validate_body(json.loads(self._raw), observed=False)

    @property
    def sha256(self):
        self.to_payload()
        return _sha(self._raw)


def make_invented_test_selection(requests, *, repository_head="a" * 40):
    """Small invented test input; cannot enter the real capture entrypoint."""
    if type(requests) is not tuple or not 1 <= len(requests) <= MAX_REQUESTS:
        _refuse("invented request count differs")
    rows = [{"global_index": index + 100, "request_sha256": _hash(_request(item)),
             "source_class": "originally_unattempted", "request": _request(item)} for index, item in enumerate(requests)]
    body = {"kind": VERSION, "scope": "invented_test_only", "repository_head": repository_head,
        **{k: "0" * 64 for k in ("worker_source_sha256", "worker_bootstrap_sha256", "accepted_source_view_sha256",
               "accepted_base_sha256", "current_source_inventory_sha256", "historical_validator_sha256")},
        "historical_commit": None, "historical_files": [], "historical_function_paths": [], "source_view": None,
        "executed_modules": [], "replay_anchors": {}, "class_counts": {}, "total_parents": len(rows),
        "source_bound_count": 0, "v3_completed_count": 0, "v3_attempt_count": 0,
        "stopped_v3_disposition": "not-observed-fixture", "maximum_requests": len(rows), "requests": rows,
        "selected_prefix_sha256": _hash(rows), "isolation": {"observed_worker_execution": False},
        "authority": {"source_authenticated": False, "point_in_time_data": False, "rights_verified": False,
            "canonical_evidence": False, "complete_corpus": False, "dispatch_enabled": False,
            "qc_authorized": False, "backtest_authorized": False, "execution_authorized": False,
            "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}}
    _validate_body(body, observed=False)
    raw = _canonical(body)
    result = InventedV4Selection(raw, _TEST_TOKEN, raw)
    _FACTORY_IMAGES[result] = raw
    return result


def _worker_main(bundle):
    """New source-only entrypoint; accepted primitives remain byte-for-byte."""
    base, finder, previous = _base(), None, sys.getprofile()
    try:
        sys.dont_write_bytecode = True
        blobs = base._validate_historical_blobs(base._decode_sources(bundle["historical_sources"]))
        sources = base._decode_sources(bundle["current_sources"])
        current = dict(sources)
        if (base._sha(current[SELF_PATH]) != bundle["worker_source_sha256"]
                or base._sha(current[BASE_PATH]) != ACCEPTED_BASE_SHA256
                or base._sha(current[VIEW_PATH]) != ACCEPTED_VIEW_SHA256):
            _refuse("captured selector or accepted source primitives differ")
        base._assert_sources_unchanged(sources)
        if any(n.split(".")[0] in {"research", "data", "ml"} for n in sys.modules):
            _refuse("selection worker inherited repository modules")
        finder = base._HistoricalBlobFinder(blobs, sources)
        finder.executed.extend({"path": p, "sha256": base._sha(current[p]), "source_kind": "current_source_snapshot"}
                               for p in (BASE_PATH, SELF_PATH))
        sys.meta_path.insert(0, finder)
        sys.setprofile(finder.profile)
        view_module = importlib.import_module("research.insider_buying_sec_recovery_v4_source_view")
        view_module._CAPTURED_BASE = base
        union = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_union")
        campaign = importlib.import_module("research.insider_buying_sec_all_form4_parent_campaign")
        prior = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_preflight")
        completed = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_verifier")
        partial = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_partial_verifier")
        diagnostic = importlib.import_module("research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier")
        v4 = importlib.import_module("research.insider_buying.sec_recovery_v4_plan")
        with view_module.HistoricalSourceView(blobs, union) as view:
            def source_replay():
                return union.preflight_observed_all_form4_parent_recovery_union(*base.SOURCE_ROOTS,
                    diagnostic_capture_git_commit=union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
                    expected_diagnostic_report_sha256=union.OBSERVED_DIAGNOSTIC_REPORT_SHA256)
            source = source_replay()
            plan = campaign._build_real_plan(*base.SOURCE_ROOTS[:6])
            expectation = prior.PartialCampaignExpectation(capture_git_commit=prior.PRIOR_CAPTURE_GIT_COMMIT,
                shard_report_sha256s=prior.PRIOR_SHARD_REPORT_SHA256S, completed_counts=(8192, 1347),
                reused_counts=(972, 226), total_attempt_count=8342)
            def partial_replay():
                result = partial._verify_partial(plan, source, base.SOURCE_ROOTS[6], base.SOURCE_ROOTS[7],
                    base.SOURCE_ROOTS[5], base.V3_ROOT, prior_expectation=expectation,
                    capture_git_commit=base.HISTORICAL_COMMIT, capture_code_sha256=base.EXECUTOR_SHA256)
                partial._require_observed_anchors(result)
                if result.completed_new_count != 1846 or result.attempt_count != 1847:
                    _refuse("stopped root counts differ")
                return result
            stopped = partial_replay()
            accepted = diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT, expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256)
            classes, _ = completed._source_classes(plan, source)
            p = {key: getattr(stopped, key) for key in (*v4._PARTIAL_HASHES, *v4._PARTIAL_INTS)}
            d = {key: getattr(accepted, key) for key in (*v4._DIAGNOSTIC_HASHES,
                "diagnostic_capture_git_commit", "pending_global_index", "body_size_bytes")}
            proposal = v4.build_recovery_v4_offline_plan(tuple(r.to_payload() for r in plan.requests), tuple(classes), p, d,
                v4.bind_v3_historical_validator(base.HISTORICAL_COMMIT, blobs))
            body = proposal.to_payload()
            eligible = body["proposed_unattempted_inventory"]
            count = bundle["maximum_requests"]
            if type(count) is not int or not 1 <= count <= MAX_REQUESTS or len(eligible) != 79868:
                _refuse("fresh prefix cardinality differs")
            rows = []
            for row in eligible[:count]:
                request = plan.requests[row["global_index"]].to_payload()
                if row["source_class"] != "originally_unattempted" or row["request_sha256"] != _hash(request):
                    _refuse("fresh prefix differs from reconstructed original request")
                rows.append({**row, "request": request})
            if source_replay() != source or partial_replay() != stopped:
                _refuse("retained source or stopped root changed")
            if diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                    capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT,
                    expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256) != accepted:
                _refuse("accepted separate diagnostic changed")
        proof = view.proof()
        base._assert_sources_unchanged(sources)
        if finder.called != {p for p, _ in base.HISTORICAL_FILES}:
            _refuse("historical function execution was not observed")
        anchors = {"source_union_sha256": _hash(source), "partial_descriptor_sha256": _hash(p),
            "diagnostic_descriptor_sha256": _hash(d), "v4_plan_sha256": proposal.sha256,
            "partition_sha256": body["partition_sha256"],
            "proposed_unattempted_inventory_sha256": body["proposed_unattempted_inventory_sha256"]}
        payload = {"kind": VERSION, "scope": "observed_isolated_retained_root_replay", "repository_head": bundle["repository_head"],
            "worker_source_sha256": bundle["worker_source_sha256"], "worker_bootstrap_sha256": _sha(_BOOTSTRAP.encode()),
            "accepted_source_view_sha256": ACCEPTED_VIEW_SHA256, "accepted_base_sha256": ACCEPTED_BASE_SHA256,
            "current_source_inventory_sha256": _hash([{"path": path, "sha256": _sha(raw)} for path, raw in sources]),
            "executed_modules": finder.executed, "historical_commit": base.HISTORICAL_COMMIT,
            "historical_validator_sha256": base.HISTORICAL_VALIDATOR_SHA256,
            "historical_files": [{"path": path, "sha256": sha} for path, sha in base.HISTORICAL_FILES],
            "historical_function_paths": [path for path, _ in base.HISTORICAL_FILES], "source_view": proof,
            "replay_anchors": anchors, "class_counts": body["class_counts"], "total_parents": 99394,
            "source_bound_count": 19526, "v3_completed_count": 1846, "v3_attempt_count": 1847,
            "stopped_v3_disposition": "preserved_unresolved_not_resumable", "maximum_requests": count,
            "requests": rows, "selected_prefix_sha256": _hash(rows), "isolation": {
                "os_network_denied": True, "os_file_writes_denied": True, "os_process_fork_denied": True,
                "audit_additional_processes_denied": True, "source_only_lane_imports": True},
            "authority": {"source_authenticated": False, "point_in_time_data": False, "rights_verified": False,
                "canonical_evidence": False, "complete_corpus": False, "dispatch_enabled": False, "qc_authorized": False,
                "backtest_authorized": False, "execution_authorized": False, "sec_dispatches": 0, "outcome_looks": 0,
                "qc_jobs": 0, "backtests": 0}}
        _validate_body(payload, observed=True)
        raw = _canonical(payload)
        if len(raw) > MAX_OUTPUT_BYTES: _refuse("selected prefix output exceeds cap")
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("REFUSED: isolated fresh v4 selection replay failed\n")
        raise SystemExit(1) from None
    finally:
        sys.setprofile(previous)
        if finder is not None and finder in sys.meta_path: sys.meta_path.remove(finder)


_BOOTSTRAP = """import base64, hashlib, json, sys, types
raw = sys.stdin.buffer.read(33554433)
if len(raw) > 33554432: raise SystemExit(2)
b = json.loads(raw)
rows = [r for r in b['current_sources'] if r['path'] == 'research/insider_buying_sec_recovery_v4_historical_replay.py']
if len(rows) != 1: raise SystemExit(2)
old = base64.b64decode(rows[0]['source_b64'], validate=True)
if hashlib.sha256(old).hexdigest() != rows[0]['sha256'] or rows[0]['sha256'] != b['base_source_sha256']: raise SystemExit(2)
base = types.ModuleType('_insider_fresh_v4_base')
base.__file__ = sys.argv[2]
sys.modules[base.__name__] = base
exec(compile(old, base.__file__, 'exec', dont_inherit=True), base.__dict__)
sys.addaudithook(base._audit_event)
s = base64.b64decode(b['worker_source_b64'], validate=True)
if hashlib.sha256(s).hexdigest() != b['worker_source_sha256']: raise SystemExit(2)
m = types.ModuleType('_insider_fresh_v4_worker')
m.__file__ = sys.argv[1]
sys.modules[m.__name__] = m
exec(compile(s, m.__file__, 'exec', dont_inherit=True), m.__dict__)
m._CAPTURED_BASE = base
m._worker_main(b)
"""


def _run_isolated_worker(raw, timeout_seconds):
    base = _base()
    if type(raw) is not bytes or not 0 < len(raw) <= base._MAX_INPUT_BYTES:
        _refuse("worker input exceeds cap")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        _refuse("worker timeout differs")
    command = ("/usr/bin/sandbox-exec", "-p", base._worker_policy(), str(Path(sys.executable).resolve()),
        "-I", "-S", "-B", "-c", _BOOTSTRAP, str(base.LANE_ROOT / SELF_PATH), str(base.LANE_ROOT / BASE_PATH))
    proc = subprocess.Popen(command, cwd=base.LANE_ROOT, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline, output, offset = time.monotonic() + timeout_seconds, bytearray(), 0
    try:
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE)
            selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: _refuse("worker timed out")
                for key, _ in selector.select(min(remaining, 1.0)):
                    if key.fileobj is proc.stdin:
                        try: offset += os.write(proc.stdin.fileno(), raw[offset:offset + 65536])
                        except BrokenPipeError:
                            selector.unregister(proc.stdin); proc.stdin.close(); continue
                        if offset == len(raw): selector.unregister(proc.stdin); proc.stdin.close()
                    else:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk: selector.unregister(proc.stdout); proc.stdout.close()
                        elif len(output) + len(chunk) > MAX_OUTPUT_BYTES: _refuse("worker output exceeded cap")
                        else: output.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0: _refuse("worker timed out")
        return subprocess.CompletedProcess(command, proc.wait(timeout=remaining), bytes(output))
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
        if proc.stdin is not None and not proc.stdin.closed: proc.stdin.close()
        if proc.stdout is not None and not proc.stdout.closed: proc.stdout.close()


def _context(snapshot, expected_head):
    if type(expected_head) is not str or _COMMIT.fullmatch(expected_head) is None or snapshot[0] != expected_head:
        _refuse("exact lane HEAD differs")
    allowed = {SELF_PATH, "tests/test_insider_buying_sec_recovery_v4_selection.py",
        "research/insider_buying_sec_recovery_v4_capture.py", "tests/test_insider_buying_sec_recovery_v4_capture.py",
        "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"}
    for line in snapshot[1].splitlines():
        if len(line) < 4 or "R" in line[:2] or "C" in line[:2]: _refuse("unexpected lane status")
        path = json.loads(line[3:]) if line[3:].startswith('"') else line[3:]
        if path not in allowed: _refuse("unrelated lane changes")


def replay_observed_first_v4_requests(*, expected_head, maximum_requests=64, timeout_seconds=600):
    """Fixed retained roots; exact first prefix, no source/authentication shortcut."""
    base = _base()
    if type(maximum_requests) is not int or not 1 <= maximum_requests <= MAX_REQUESTS:
        _refuse("first-prefix bound differs")
    if not Path("/usr/bin/sandbox-exec").is_file(): _refuse("required worker sandbox unavailable")
    try:
        before = base._repository_snapshot(); _context(before, expected_head)
        blobs = base._validate_historical_blobs(tuple((p, base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{p}"))
                                                    for p, _ in base.HISTORICAL_FILES))
        sources = base._source_snapshot(); current = dict(sources)
        if (Path(__file__).resolve() != base.LANE_ROOT / SELF_PATH
                or _sha(current[BASE_PATH]) != ACCEPTED_BASE_SHA256 or _sha(current[VIEW_PATH]) != ACCEPTED_VIEW_SHA256
                or _sha(base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{base.EXECUTOR_PATH}")) != base.EXECUTOR_SHA256
                or current[base.DIAGNOSTIC_CAPTURE_PATH] != base._git("cat-file", "blob",
                    f"{base.DIAGNOSTIC_CAPTURE_COMMIT}:{base.DIAGNOSTIC_CAPTURE_PATH}")):
            _refuse("fixed source or historical acquisition bytes differ")
        worker = current[SELF_PATH]
        bundle = {"repository_head": before[0], "historical_sources": base._encode_sources(blobs),
            "current_sources": base._encode_sources(sources), "worker_source_b64": base64.b64encode(worker).decode("ascii"),
            "worker_source_sha256": _sha(worker), "base_source_sha256": ACCEPTED_BASE_SHA256, "maximum_requests": maximum_requests}
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before: _refuse("lane changed before replay")
        result = _run_isolated_worker(_canonical(bundle), timeout_seconds)
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before: _refuse("lane changed during replay")
        if result.returncode != 0 or not 0 < len(result.stdout) <= MAX_OUTPUT_BYTES:
            _refuse("isolated replay refused or overflowed")
        body = _validate_body(json.loads(result.stdout), observed=True)
        if (body["repository_head"] != before[0] or body["maximum_requests"] != maximum_requests
                or body["worker_source_sha256"] != _sha(worker)
                or body["current_source_inventory_sha256"] != _hash([{"path": p, "sha256": _sha(r)} for p, r in sources])):
            _refuse("worker context or exact requested prefix differs")
        historical = dict(blobs)
        for row in body["executed_modules"]:
            raw = historical.get(row["path"]) if row["source_kind"] == "historical_git_blob" else current.get(row["path"])
            if raw is None or _sha(raw) != row["sha256"]: _refuse("executed source differs from captured bytes")
        raw = _canonical(body)
        selected = FreshV4Selection(raw, _TOKEN, raw)
        _FACTORY_IMAGES[selected] = raw
        return selected
    except FreshV4SelectionError:
        raise
    except (base.HistoricalReplayError, OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError, subprocess.SubprocessError):
        raise FreshV4SelectionError("REFUSED: bounded fresh selection failed") from None
