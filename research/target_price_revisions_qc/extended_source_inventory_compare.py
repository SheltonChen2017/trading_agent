"""Compare two fixed metadata receipts, never reopen source archives or rows.

Import and pure comparison do not perform I/O. The production entry point
requires its own fresh committed-source-bound scope, exclusive spent claim,
access receipt and controller lock. Equality is saved-inventory metadata
only: no compiled-source, native completion, economic or ON acceptance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import time

from . import extended_mia_capture as m

e, files = m.e, m.files
LANE, PRIVATE_ROOT = m.LANE, m.PRIVATE_ROOT
MODULE = m.PREFIX + "extended_source_inventory_compare.py"
SOURCE_PATHS = (*m.SOURCE_PATHS, MODULE)
OPERATION = "TPR-EXT26-SOURCE-INVENTORY-COMPARE-20261022-001"
RECEIPTS = (
    {"operation_id": "TPR-EXT26-MIA-SOURCE-BASELINE-20261022-004", "bytes": 8053,
     "sha256": "267c70a21f5e26c246cd7c11edd3ab031da26b6f16f46028ad9193bafd96ca0e"},
    {"operation_id": "TPR-EXT26-MIA-SOURCE-BASELINE-20261022-005", "bytes": 8053,
     "sha256": "abf8bcf5af37cc13eaa6629c4278838ab4cf7e955bcb256caddc6af83753b4a3"},
)
MAX_EACH, MAX_TOTAL, MAX_RESULT, MAX_SECONDS = 8053, 16106, 4096, 120
MAIN = {"bytes": 60658, "sha256": "a098c087c14507c154a4740d0145f7af1c448ec24905f4c8b66e82869d917d86"}
KNOWN_NAMES = m.EXPECTED_FILES | {"research.ipynb"}
OTHER_NAMES = frozenset(("audit_key_recovery.py", "extended_refusal_witness_context_successor.py",
                         "mia.ipynb", "mia_diag.py", "mia_rescale.py"))
OTHER_HASHES = frozenset(hashlib.sha256(name.encode()).hexdigest() for name in OTHER_NAMES)
INVENTORY_KEYS = KNOWN_NAMES | {"unrecognized-name-sha256-" + value for value in OTHER_HASHES}
ARGS = ("git_head", "source_hashes", "owner_instruction_sha256", "created_utc", "expires_utc", "mode", "fixture_descriptors")
TOP = frozenset(("schema operation_id action project_id candidate_id git_head source_hashes owner_instruction_sha256 "
    "plan_sha256 baseline_reference status scope_spent read_attempts received_bytes baseline_read_bytes "
    "failed_read_body_bytes_unknown requests source_archives inventory stable_source_inventory "
    "baseline_expected_files_equal expected_files missing_expected_files different_expected_files unexpected_files "
    "changes complete_private_diff request_bound_to_fixed_project provider_authenticity_attested "
    "compiled_job_binding_verified new_codex_attempts codex_attempts_consumed new_looks mia_message_or_job "
    "candidate_mutation licensed_input_reads provider_reads object_export automatic_retry old_claims_renewed "
    "raw_text_returned economics_accepted performance_accepted canonical_admission trading ended_utc").split())
FALSE_FIELDS = frozenset(("failed_read_body_bytes_unknown provider_authenticity_attested compiled_job_binding_verified "
    "mia_message_or_job candidate_mutation object_export automatic_retry old_claims_renewed raw_text_returned "
    "economics_accepted performance_accepted canonical_admission trading").split())


def _fail():
    raise e.EvidenceError("fixed metadata-only source inventory comparison refused; no retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys): _fail()


def _integer(value, maximum):
    return m._integer(value, maximum)


def _identity(value, maximum):
    _closed(value, {"bytes", "sha256"})
    return {"bytes": _integer(value["bytes"], maximum), "sha256": e._hash(value["sha256"])}


def _inventory(value, keys):
    _closed(value, keys)
    return {name: _identity(metadata, m.MAX_FILE) for name, metadata in value.items()}


def _descriptor(value, name):
    _closed(value, {"name", "bytes", "sha256"})
    if value["name"] != name or not _integer(value["bytes"], m.MAX_ARCHIVE): _fail()
    e._hash(value["sha256"])


def _metadata(raw, operation):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_EACH: _fail()
    body = e.parse_json(raw)
    _closed(body, TOP)
    if (body["schema"] != "tpr-ext26-mia-source-receipt-v1" or body["operation_id"] != operation
            or body["action"] != "baseline-source" or _integer(body["project_id"], 2**31-1) != m.PROJECT
            or body["candidate_id"] != m.CANDIDATE or type(body["status"]) is not str
            or body["status"] not in {"COMPLETED", "BASELINE_MISMATCH"}
            or any(body[name] is not False for name in FALSE_FIELDS)
            or any(body[name] is not True for name in ("scope_spent", "stable_source_inventory", "request_bound_to_fixed_project"))
            or any(body[name] is not None for name in ("baseline_reference", "changes", "complete_private_diff"))
            or any(_integer(body[name], 3) != 0 for name in ("baseline_read_bytes", "new_codex_attempts", "new_looks", "licensed_input_reads", "provider_reads"))
            or _integer(body["codex_attempts_consumed"], 3) != 3 or _integer(body["read_attempts"], 2) != 2):
        _fail()
    e._hash(body["git_head"], 40)
    for field in ("owner_instruction_sha256", "plan_sha256"): e._hash(body[field])
    m._clock(body["ended_utc"])
    _closed(body["source_hashes"], m.SOURCE_PATHS)
    for digest in body["source_hashes"].values(): e._hash(digest)
    if (body["source_hashes"][m.BUNDLE] != m.BUNDLE_SHA256
            or body["source_hashes"][m.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or body["source_hashes"][m.PREFIX + "extended_calendar.json"] != m.ops.CALENDAR_SHA256): _fail()
    inventory = _inventory(body["inventory"], INVENTORY_KEYS)
    expected = _inventory(body["expected_files"], m.EXPECTED_FILES)
    if body["missing_expected_files"] != []: _fail()
    different = sorted(name for name in m.EXPECTED_FILES if inventory[name] != expected[name])
    equal = not different
    if (body["different_expected_files"] != different or body["baseline_expected_files_equal"] is not equal
            or body["status"] != ("COMPLETED" if equal else "BASELINE_MISMATCH")): _fail()
    unexpected = body["unexpected_files"]
    if type(unexpected) is not list or len(unexpected) != len(OTHER_HASHES): _fail()
    observed = set()
    for row in unexpected:
        _closed(row, {"name_sha256", "classification", "bytes", "sha256"})
        name_hash = e._hash(row["name_sha256"])
        if name_hash not in OTHER_HASHES or name_hash in observed or row["classification"] != "unrecognized_source": _fail()
        observed.add(name_hash)
        if _identity({key: row[key] for key in ("bytes", "sha256")}, m.MAX_FILE) != inventory["unrecognized-name-sha256-" + name_hash]: _fail()
    requests, archives = body["requests"], body["source_archives"]
    if type(requests) is not list or len(requests) != 2 or type(archives) is not list or len(archives) != 2: _fail()
    received = 0
    for index, (request, archive) in enumerate(zip(requests, archives), 1):
        _closed(request, {"request_index", "status", "response_bytes", "http_status", "projection", "returned_project_present_and_matching"})
        if (_integer(request["request_index"], 2) != index or request["status"] != "succeeded"
                or _integer(request["http_status"], 599) != 200
                or type(request["returned_project_present_and_matching"]) is not bool): _fail()
        size = _integer(request["response_bytes"], m.MAX_RESPONSE)
        if not size: _fail()
        received += size
        _descriptor(request["projection"], operation + ".read" + str(index) + ".projection.json")
        _descriptor(archive, operation + ".read" + str(index) + ".sources.json")
    if _integer(body["received_bytes"], m.MAX_TOTAL) != received: _fail()
    return inventory


def compare_receipts(before_raw, after_raw):
    """Pure metadata schema/comparison; hashes of referenced archives are not reopened."""
    before, after = (_metadata(raw, ref["operation_id"]) for raw, ref in zip((before_raw, after_raw), RECEIPTS))
    return {"schema": "tpr-ext26-source-inventory-metadata-comparison-v1", "files_each": 16,
        "all_16_equal": before == after, "changed_inventory_entries": sum(before[name] != after[name] for name in INVENTORY_KEYS),
        "before_inventory_sha256": _sha(e.canonical(before)), "after_inventory_sha256": _sha(e.canonical(after)),
        "registered_main_identity_verified": before["main.py"] == after["main.py"] == MAIN,
        "registered_main": dict(MAIN), "saved_inventory_metadata_only": True,
        "source_archives_reopened": False, "historical_compiled_source_proven": False,
        "native_accounting_verified": False, "economics_accepted": False, "off_baseline_valid": False,
        "on_launch_authorized": False, "accepted_metrics": None, "canonical_admission": False}


def _guard(head):
    m._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE, capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = m._sources(head); _guard(head)
    committed = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        _guard(head)
        result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(committed),
            expected_sha256=_sha(committed), remaining=m.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    _guard(head)
    return result


def _plan(*, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc,
          mode="production", fixture_descriptors=None):
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if mode not in {"production", "offline-fixture"}: _fail()
    _closed(source_hashes, SOURCE_PATHS)
    for digest in source_hashes.values(): e._hash(digest)
    if (source_hashes[m.BUNDLE] != m.BUNDLE_SHA256
            or source_hashes[m.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[m.PREFIX + "extended_calendar.json"] != m.ops.CALENDAR_SHA256): _fail()
    if not timedelta(0) < m._clock(expires_utc) - m._clock(created_utc) <= timedelta(seconds=600): _fail()
    references = [dict(ref, name=ref["operation_id"] + ".result.json") for ref in RECEIPTS]
    if mode == "production":
        if fixture_descriptors is not None: _fail()
    else:
        if type(fixture_descriptors) is not list or len(fixture_descriptors) != 2: _fail()
        fixture_descriptors = [_identity(value, MAX_EACH) for value in fixture_descriptors]
        if any(not value["bytes"] for value in fixture_descriptors): _fail()
        for ref, descriptor in zip(references, fixture_descriptors): ref.update(descriptor)
    return {"schema": "tpr-ext26-source-inventory-compare-plan-v1", "operation_id": OPERATION,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "mode": mode, "fixture_descriptors": fixture_descriptors,
        "receipts": references, "max_reads": 2, "max_read_bytes_each": MAX_EACH, "max_total_read_bytes": MAX_TOTAL,
        "max_seconds": MAX_SECONDS, "max_result_bytes": MAX_RESULT, "metadata_only": True,
        "source_archive_reads": 0, "api_requests": 0, "credential_reads": 0, "new_jobs": 0,
        "new_codex_attempts": 0, "new_looks": 0, "automatic_retry": False, "economics_accepted": False,
        "off_baseline_valid": False, "on_launch_authorized": False, "canonical_admission": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _now(): return datetime.now(timezone.utc)


def _execute(plan, sources, root, *, guard, clock, monotonic):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now or monotonic is not time.monotonic)
            or plan["mode"] == "offline-fixture" and (not isinstance(root, Path) or root == PRIVATE_ROOT or root.is_relative_to(LANE))): _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"]); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not m._clock(plan["created_utc"]) <= now < m._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    report = {"schema": "tpr-ext26-source-inventory-compare-receipt-v1", "operation_id": OPERATION,
        "git_head": plan["git_head"], "plan_sha256": _sha(e.canonical(plan)), "status": "FAILED_OR_UNCERTAIN",
        "scope_spent": True, "private_read_attempts": 0, "private_read_bytes": 0, "comparison": None,
        "api_requests": 0, "credential_reads": 0, "source_archive_reads": 0, "new_jobs": 0,
        "new_codex_attempts": 0, "new_looks": 0, "automatic_retry": False,
        "accepted_metrics": None, "off_baseline_valid": False, "on_launch_authorized": False, "canonical_admission": False}
    try:
        check(); m._publish(directory, OPERATION + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); m._publish(directory, OPERATION + ".access.json", e.canonical({"plan_sha256": report["plan_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"], "receipts": plan["receipts"],
                "read_only": True, "metadata_only": True, "max_reads": 2, "max_total_read_bytes": MAX_TOTAL}))
            bodies = []
            for reference in plan["receipts"]:
                check(); report["private_read_attempts"] += 1
                raw = files._read(directory, reference["name"], expected_size=reference["bytes"],
                    expected_sha256=reference["sha256"], remaining=MAX_TOTAL - report["private_read_bytes"], private=True)
                report["private_read_bytes"] += len(raw)
                check(); _metadata(raw, reference["operation_id"])
                bodies.append(raw)
            check(); report["comparison"] = compare_receipts(*bodies)
            check(); report["status"] = "COMPLETED_METADATA_COMPARISON"
        except KeyboardInterrupt:
            report["status"] = "CANCELLED"
        except Exception:
            report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat()
        raw_report = e.canonical(report)
        if len(raw_report) > MAX_RESULT:
            report["status"], report["comparison"] = "RESULT_BOUND_REFUSED", None
            raw_report = e.canonical(report)
        if len(raw_report) > MAX_RESULT: _fail()
        m._publish(directory, OPERATION + ".result.json", raw_report)
        return raw_report
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_now, monotonic=time.monotonic)


def execute_fixture(plan, sources, root, *, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    if type(plan) is not dict or plan.get("mode") != "offline-fixture": _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic)
