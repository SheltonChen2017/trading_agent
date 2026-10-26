"""Identified notebook-capacity successor of the fixed EXT26 OFF capture.

Only the module identity and all-file inventory cap change from the preserved
predecessor: 17 files may now include the separately registered research-only
diagnostic notebook. Unexpected files remain privately archived and hash-only
in public receipts; neither notebook contents nor strategy economics execute.

Two fixed EXT26 OFF source archives, never a Mia message or launch.

Fresh baseline/post-Mia scopes each read files/read exactly twice. Complete
source inventories and diffs remain private. Stable current project files are
not compiled-job provenance, unchanged economics or execution acceptance.
Imports perform no I/O; production exposes no injected path or transport.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

from . import extended_frontier_diagnostic as files
from . import extended_evidence as e, extended_operations as ops

LANE, BRANCH, PRIVATE_ROOT = ops.LANE, ops.BRANCH, ops.PRIVATE_ROOT
PREFIX = "research/target_price_revisions_qc/"
MODULE = PREFIX + "extended_mia_capture_notebook_successor.py"
BUNDLE = PREFIX + "extended_source_bundle_completion.json"
BUNDLE_SHA256 = "daaf0c33fd837b9896c99d1759e67454a9f3027d478879c5e60015af1f099934"
SOURCE_PATHS = (MODULE, PREFIX + "extended_frontier_diagnostic.py", PREFIX + "extended_evidence.py",
    PREFIX + "extended_operations.py", "research/__init__.py", PREFIX + "__init__.py",
    PREFIX + "extended_study_freeze.json", PREFIX + "extended_calendar.json", BUNDLE)
PROJECT, CANDIDATE = 37650980, "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
ENDPOINT = "files/read"
MAX_FILES, MAX_FILE = 17, 1024 * 1024
MAX_RESPONSE, MAX_TOTAL = 4 * 1024 * 1024, 8 * 1024 * 1024
MAX_ARCHIVE, MAX_SECONDS, REQUEST_SECONDS = 16 * 1024 * 1024, 120, 40
MAX_RECEIPT = 64 * 1024
EXPECTED_FILES = frozenset(("cap_observer.py", "cap_tilt.py", "extended_completion_successor.py",
    "extended_compressed_store.py", "extended_config.py", "extended_construction.py", "extended_core.py",
    "extended_loader.py", "extended_runtime_successor.py", "main.py"))
_ARGUMENTS = ("action", "operation_id", "git_head", "source_hashes", "owner_instruction_sha256",
    "created_utc", "expires_utc", "baseline_reference", "mode")
_BASELINE_KEYS = frozenset(("operation_id", "receipt_bytes", "receipt_sha256", "sources_bytes", "sources_sha256"))
Refusal = e.EvidenceError


def _fail():
    raise Refusal("fixed EXT26 OFF source capture refused; no automatic retry")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _integer(value, maximum):
    if type(value) is e.JsonNumber and value.fraction().denominator == 1:
        value = int(value.fraction())
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _clock(value):
    if type(value) is not str or len(value) > 64:
        _fail()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail()
    if result.utcoffset() != timedelta(0):
        _fail()
    return result


def _operation(value, action):
    prefix = "TPR-EXT26-MIA-SOURCE-BASELINE-" if action == "baseline-source" else "TPR-EXT26-MIA-SOURCE-POST-"
    if type(value) is not str or re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9-]{1,50}", value) is None:
        _fail()
    return value


def _guard(head):
    e._hash(head, 40)
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE:
        _fail()
    def git(*arguments):
        return subprocess.run(["git", *arguments], cwd=LANE, capture_output=True,
            text=True, timeout=5, check=True).stdout.strip()
    top, branch, actual = git("rev-parse", "--show-toplevel"), git("branch", "--show-current"), git("rev-parse", "HEAD")
    git("status", "--short")
    if top != str(LANE) or branch != BRANCH or actual != head:
        _fail()
    _imports()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode:
        _fail()
    if subprocess.run(["git", "check-ignore", "-q", str(PRIVATE_ROOT)], cwd=LANE,
            capture_output=True, timeout=5).returncode:
        _fail()


def _imports():
    import research
    from . import __file__ as package_file
    paths = ((Path(__file__), MODULE), (Path(files.__file__), PREFIX + "extended_frontier_diagnostic.py"),
        (Path(e.__file__), PREFIX + "extended_evidence.py"), (Path(ops.__file__), PREFIX + "extended_operations.py"),
        (Path(research.__file__), "research/__init__.py"), (Path(package_file), PREFIX + "__init__.py"))
    if any(actual != LANE / relative or actual.resolve() != actual for actual, relative in paths):
        _fail()


def _sources(head):
    _guard(head); _imports()
    result = {}
    for relative in SOURCE_PATHS:
        _guard(head)
        committed = subprocess.run(["git", "show", head + ":" + relative], cwd=LANE,
            capture_output=True, timeout=5, check=True).stdout
        if not 0 <= len(committed) <= MAX_RESPONSE:
            _fail()
        directory = files._directory((LANE / relative).parent, private=False)
        try:
            _guard(head)
            result[relative] = files._read(directory, Path(relative).name,
                expected_size=len(committed), expected_sha256=_sha(committed), remaining=MAX_RESPONSE, private=False)
        finally:
            os.close(directory)
    if (_sha(result[BUNDLE]) != BUNDLE_SHA256
            or _sha(result[PREFIX + "extended_study_freeze.json"]) != e.FREEZE_SHA256
            or _sha(result[PREFIX + "extended_calendar.json"]) != ops.CALENDAR_SHA256):
        _fail()
    _guard(head)
    return result


def _plan(*, action, operation_id, git_head, source_hashes, owner_instruction_sha256,
          created_utc, expires_utc, baseline_reference=None, mode="production"):
    if action not in {"baseline-source", "post-mia-source"} or mode not in {"production", "offline-fixture"}:
        _fail()
    _operation(operation_id, action); e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS):
        _fail()
    for value in source_hashes.values():
        e._hash(value)
    if (source_hashes[BUNDLE] != BUNDLE_SHA256
            or source_hashes[PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[PREFIX + "extended_calendar.json"] != ops.CALENDAR_SHA256):
        _fail()
    duration = _clock(expires_utc) - _clock(created_utc)
    if not timedelta(0) < duration <= timedelta(hours=4):
        _fail()
    reference = None
    if action == "post-mia-source":
        if type(baseline_reference) is not dict or set(baseline_reference) != _BASELINE_KEYS:
            _fail()
        reference = dict(baseline_reference)
        _operation(reference["operation_id"], "baseline-source")
        for name, maximum in (("receipt_bytes", MAX_RECEIPT), ("sources_bytes", MAX_ARCHIVE)):
            reference[name] = _integer(reference[name], maximum)
            if not reference[name]:
                _fail()
        e._hash(reference["receipt_sha256"]); e._hash(reference["sources_sha256"])
    elif baseline_reference is not None:
        _fail()
    return {"schema": "tpr-ext26-mia-source-plan-v1", "action": action, "operation_id": operation_id,
        "project_id": PROJECT, "candidate_id": CANDIDATE, "git_head": git_head,
        "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "baseline_reference": reference, "mode": mode,
        "endpoint": ENDPOINT, "payload": {"projectId": PROJECT}, "max_requests": 2,
        "max_files": MAX_FILES, "max_file_bytes": MAX_FILE, "max_response_bytes": MAX_RESPONSE,
        "max_received_bytes": MAX_TOTAL, "max_seconds": MAX_SECONDS, "request_seconds": REQUEST_SECONDS,
        "baseline_body_bytes_bound": MAX_ARCHIVE + MAX_RECEIPT, "max_private_artifact_bytes": MAX_ARCHIVE,
        "compiled_job_binding_verified": False, "new_codex_attempts": 0, "new_looks": 0,
        "mia_message_or_job": False, "candidate_mutation": False, "automatic_retry": False}


def prepare_plan(**arguments):
    """Pin public committed source bytes only; no private read or network."""
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE:
        _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True,
        text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    return _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)


def _publish(directory, name, raw):
    if (type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,220}", name) is None
            or type(raw) is not bytes or not 0 < len(raw) <= MAX_ARCHIVE):
        _fail()
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            _fail()
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if not written:
                _fail()
            offset += written
        os.fsync(fd)
        # The pathname/claim must survive a crash before credentials or a
        # request can be used; flushing file bytes alone does not commit it.
        os.fsync(directory)
    finally:
        os.close(fd)
    return {"name": name, "bytes": len(raw), "sha256": _sha(raw)}


def _inventory(source):
    if type(source) is not dict or not 1 <= len(source) <= MAX_FILES:
        _fail()
    result = {}
    for name, text in sorted(source.items()):
        if (type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", name) is None
                or type(text) is not str or len(text.encode("utf-8")) > MAX_FILE):
            _fail()
        raw = text.encode("utf-8")
        result[name] = {"bytes": len(raw), "sha256": _sha(raw)}
    return result


def _public_inventory(inventory):
    """Only known module/notebook names are public; unknown names are hashes."""
    return {name if name in EXPECTED_FILES | {"research.ipynb"} else
        "unrecognized-name-sha256-" + _sha(name.encode()): value for name, value in inventory.items()}


def _public_file(name, metadata):
    return ({"name": name, **metadata} if name in EXPECTED_FILES | {"research.ipynb"} else
        {"name_sha256": _sha(name.encode()), "classification": "unrecognized_source", **metadata})


def _capture(response):
    if type(response) is not dict or response.get("success") is not True:
        _fail()
    returned = "projectId" in response
    if returned and _integer(response["projectId"], 2**31 - 1) != PROJECT:
        _fail()
    rows = response.get("files")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FILES:
        _fail()
    source = {}
    for row in rows:
        if (type(row) is not dict or type(row.get("name")) is not str
                or row["name"] in source or type(row.get("content")) is not str):
            _fail()
        if "projectId" in row and _integer(row["projectId"], 2**31 - 1) != PROJECT:
            _fail()
        source[row["name"]] = row["content"]
    inventory = _inventory(source)
    return source, inventory, returned


def _expected(sources):
    if _sha(sources[BUNDLE]) != BUNDLE_SHA256:
        _fail()
    bundle = e.parse_json(sources[BUNDLE])
    rows = [row for row in bundle["candidates"] if row["candidate_id"] == CANDIDATE]
    if len(rows) != 1 or set(rows[0]["files"]) != EXPECTED_FILES or _integer(rows[0]["planned_attempt"], 3) != 3:
        _fail()
    result = _inventory(rows[0]["files"])
    if result["main.py"]["bytes"] != 59931:
        _fail()
    return result


def _archive(operation, number, source):
    # Keep exact source strings without multiplying UTF-8 into ASCII escape
    # sequences. Duplicate-name refusal and parse/depth bounds precede this.
    value = {"schema": "tpr-ext26-mia-all-source-v1", "operation_id": operation,
        "project_id": PROJECT, "request_index": number, "files": source}
    e.canonical(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _baseline(directory, reference, sources, check, report):
    check()
    operation = reference["operation_id"]
    raw = files._read(directory, operation + ".result.json", expected_size=reference["receipt_bytes"],
        expected_sha256=reference["receipt_sha256"], remaining=MAX_RECEIPT, private=True)
    report["baseline_read_bytes"] += len(raw)
    receipt = e.parse_json(raw)
    if (receipt.get("schema") != "tpr-ext26-mia-source-receipt-v1" or receipt.get("operation_id") != operation
            or receipt.get("action") != "baseline-source" or receipt.get("status") != "COMPLETED"
            or receipt.get("stable_source_inventory") is not True or receipt.get("baseline_expected_files_equal") is not True
            or _integer(receipt.get("project_id"), 2**31 - 1) != PROJECT
            or receipt.get("candidate_id") != CANDIDATE
            or receipt.get("source_hashes") != {name: _sha(raw) for name, raw in sources.items()}):
        _fail()
    archive = receipt.get("source_archives")
    if (type(archive) is not list or len(archive) != 2 or archive[-1] != {"name": operation + ".read2.sources.json",
            "bytes": e.JsonNumber(str(reference["sources_bytes"])), "sha256": reference["sources_sha256"]}):
        _fail()
    check()
    raw = files._read(directory, operation + ".read2.sources.json", expected_size=reference["sources_bytes"],
        expected_sha256=reference["sources_sha256"], remaining=MAX_ARCHIVE, private=True)
    report["baseline_read_bytes"] += len(raw)
    value = e.parse_json(raw)
    if (set(value) != {"schema", "operation_id", "project_id", "request_index", "files"}
            or value["schema"] != "tpr-ext26-mia-all-source-v1" or value["operation_id"] != operation
            or _integer(value["project_id"], 2**31 - 1) != PROJECT or _integer(value["request_index"], 2) != 2
            or e.canonical(_public_inventory(_inventory(value["files"]))) != e.canonical(receipt.get("inventory"))):
        _fail()
    actual, expected = _inventory(value["files"]), _expected(sources)
    if (not EXPECTED_FILES <= set(actual) or any(actual[name] != expected[name] for name in EXPECTED_FILES)
            or e.canonical(expected) != e.canonical(receipt.get("expected_files"))):
        _fail()
    return value["files"]


def _diff(before, after):
    inventory_before, inventory_after = _inventory(before), _inventory(after)
    changes, private = [], []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name) and name in before and name in after:
            continue
        kind = "added" if name not in before else "removed" if name not in after else "changed"
        changes.append(_public_file(name, {"kind": kind, "before": inventory_before.get(name), "after": inventory_after.get(name)}))
        # An exact whole-file before/after delta is complete and linear in the
        # bounded bytes. Avoid unbounded quadratic textual diff algorithms.
        private.append({"name": name, "kind": kind, "before": before.get(name), "after": after.get(name),
            "before_identity": inventory_before.get(name), "after_identity": inventory_after.get(name)})
    return changes, e.canonical({"schema": "tpr-ext26-mia-complete-source-diff-v1", "changes": private,
        "all_changed_file_bytes_retained": True, "diff_format": "complete-whole-file-before-after-v1",
        "source_executed": False, "economics_accepted": False})


def _native_request(payload, seconds):
    if payload != {"projectId": PROJECT} or type(seconds) not in (int, float) or not 0 < seconds <= REQUEST_SECONDS:
        _fail()
    connection = None
    with ops.wall_deadline(seconds):
        user, token = ops.credential()
        stamp = str(int(time.time()))
        signed = hashlib.sha256((token + ":" + stamp).encode()).hexdigest()
        authorization = base64.b64encode((user + ":" + signed).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED
        context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection("www.quantconnect.com", timeout=seconds, context=context)
            connection.request("POST", "/api/v2/files/read", body=e.canonical(payload), headers={
                "Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.read(MAX_RESPONSE + 1), response.status, token
        finally:
            if connection is not None:
                connection.close()


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    if type(plan) is not dict or e.canonical(plan) != e.canonical(_plan(**{key: plan[key] for key in _ARGUMENTS})):
        _fail()
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or transport is not _native_request
            or guard is not _guard or clock is not _production_clock or monotonic is not time.monotonic)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)):
        _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"])
        current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not _clock(plan["created_utc"]) <= current < _clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]):
            _fail()
    check(); expected = _expected(sources)
    directory = files._directory(root, private=True)
    operation, lock, report = plan["operation_id"], None, None
    try:
        check(); _publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        report = {"schema": "tpr-ext26-mia-source-receipt-v1", "operation_id": operation, "action": plan["action"],
            "project_id": PROJECT, "candidate_id": CANDIDATE, "git_head": plan["git_head"],
            "source_hashes": plan["source_hashes"], "owner_instruction_sha256": plan["owner_instruction_sha256"],
            "plan_sha256": _sha(e.canonical(plan)), "baseline_reference": plan["baseline_reference"],
            "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "read_attempts": 0, "received_bytes": 0,
            "baseline_read_bytes": 0, "failed_read_body_bytes_unknown": False, "requests": [], "source_archives": [],
            "inventory": None, "stable_source_inventory": False, "baseline_expected_files_equal": False,
            "expected_files": expected, "missing_expected_files": [], "different_expected_files": [], "unexpected_files": [],
            "changes": None, "complete_private_diff": None, "request_bound_to_fixed_project": True,
            "provider_authenticity_attested": False, "compiled_job_binding_verified": False,
            "new_codex_attempts": 0, "codex_attempts_consumed": 3, "new_looks": 0, "mia_message_or_job": False,
            "candidate_mutation": False, "licensed_input_reads": 0, "provider_reads": 0, "object_export": False,
            "automatic_retry": False, "old_claims_renewed": False, "raw_text_returned": False,
            "economics_accepted": False, "performance_accepted": False, "canonical_admission": False, "trading": False}
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                _fail()
            check(); _publish(directory, operation + ".access.json", e.canonical({"plan_sha256": report["plan_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"], "read_only": True}))
            before = _baseline(directory, plan["baseline_reference"], sources, check, report) if plan["action"] == "post-mia-source" else None
            snapshots = []
            for number in (1, 2):
                check(); stage = operation + ".read" + str(number)
                claim = {"endpoint": ENDPOINT, "payload": {"projectId": PROJECT}, "plan_sha256": report["plan_sha256"]}
                _publish(directory, stage + ".request.spent.json", e.canonical(claim))
                request = {"request_index": number, "status": "failed_or_unknown", "response_bytes": None,
                    "http_status": None, "projection": None, "returned_project_present_and_matching": False}
                report["requests"].append(request); report["read_attempts"] += 1
                report["failed_read_body_bytes_unknown"] = True
                check(); seconds = min(REQUEST_SECONDS, MAX_SECONDS - (monotonic() - started))
                raw, status, token = transport({"projectId": PROJECT}, seconds)
                if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE or report["received_bytes"] + len(raw) > MAX_TOTAL:
                    _fail()
                report["received_bytes"] += len(raw); report["failed_read_body_bytes_unknown"] = False
                if type(status) is not int or not 100 <= status <= 599:
                    _fail()
                request.update(response_bytes=len(raw), http_status=status)
                # An unusable echo credential must refuse before any projection is retained.
                if type(token) is not str or re.fullmatch(r"[!-~]{1,256}", token) is None:
                    _fail()
                check(); projection = e.project_wire(raw, credential=token)
                request["projection"] = _publish(directory, stage + ".projection.json", e.canonical(projection))
                if status != 200:
                    _fail()
                source, inventory, returned = _capture(projection["projection"])
                check(); archived = _publish(directory, stage + ".sources.json", _archive(operation, number, source))
                report["source_archives"].append(archived); snapshots.append((source, inventory))
                request.update(status="succeeded", returned_project_present_and_matching=returned)
                check(); _publish(directory, stage + ".terminal.json", e.canonical(request))
            check()
            report["inventory"] = _public_inventory(snapshots[-1][1])
            if snapshots[0][0] != snapshots[1][0]:
                _fail()
            report["stable_source_inventory"] = True
            inventory = snapshots[-1][1]
            report["missing_expected_files"] = sorted(EXPECTED_FILES - set(inventory))
            report["different_expected_files"] = sorted(name for name in EXPECTED_FILES & set(inventory) if inventory[name] != expected[name])
            report["unexpected_files"] = [_public_file(name, inventory[name]) for name in
                sorted(set(inventory) - EXPECTED_FILES - {"research.ipynb"})]
            report["baseline_expected_files_equal"] = not report["missing_expected_files"] and not report["different_expected_files"]
            if before is not None:
                changes, private_diff = _diff(before, snapshots[-1][0])
                check(); report["complete_private_diff"] = _publish(directory, operation + ".diff.json", private_diff)
                report["changes"] = changes
            report["status"] = "COMPLETED" if plan["action"] == "post-mia-source" or report["baseline_expected_files_equal"] else "BASELINE_MISMATCH"
        except (Exception, KeyboardInterrupt):
            if report["requests"] and report["requests"][-1]["status"] != "succeeded":
                stage = operation + ".read" + str(report["requests"][-1]["request_index"])
                _publish(directory, stage + ".terminal.json", e.canonical(report["requests"][-1]))
        report["ended_utc"] = clock().isoformat()
        raw_report = e.canonical(report)
        if len(raw_report) > MAX_RECEIPT:
            # The disclosure is refused, but the spent scope still gets a receipt.
            for key in ("inventory", "changes", "complete_private_diff"):
                report[key] = None
            for key in ("missing_expected_files", "different_expected_files", "unexpected_files"):
                report[key] = []
            report["status"] = "FAILED_OR_UNCERTAIN"; report["public_size_refused"] = True
            raw_report = e.canonical(report)
            if len(raw_report) > MAX_RECEIPT:
                _fail()
        _publish(directory, operation + ".result.json", raw_report)
        return raw_report
    finally:
        if lock is not None:
            try:
                current = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False)
                owned = os.fstat(lock)
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError:
                pass
            finally:
                os.close(lock)
        os.close(directory)


def execute_plan(plan):
    """No production root, credentials, transport or clock injection."""
    if type(plan) is not dict or plan.get("mode") != "production":
        _fail()
    sources = _sources(plan["git_head"])
    return _execute(plan, sources, PRIVATE_ROOT, guard=_guard,
        clock=_production_clock, monotonic=time.monotonic, transport=_native_request)


def _production_clock():
    return datetime.now(timezone.utc)


def _execute_fixture(plan, sources, root, *, clock, transport, guard=lambda _: None, monotonic=lambda: 0.0):
    if (type(plan) is not dict or plan.get("mode") != "offline-fixture" or root.is_relative_to(LANE)
            or transport is _native_request):
        _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic, transport=transport)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("baseline-source", "post-mia-source"))
    for name in ("operation-id", "owner-instruction-sha256", "created-utc", "expires-utc"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--baseline-operation")
    for name in ("receipt-bytes", "receipt-sha256", "sources-bytes", "sources-sha256"):
        parser.add_argument("--baseline-" + name)
    arguments = vars(parser.parse_args(argv))
    baseline_operation = arguments.pop("baseline_operation")
    reference_values = {name: arguments.pop("baseline_" + name) for name in ("receipt_bytes", "receipt_sha256", "sources_bytes", "sources_sha256")}
    try:
        reference = None
        if baseline_operation is not None or any(value is not None for value in reference_values.values()):
            reference = {"operation_id": baseline_operation, **reference_values}
            for name in ("receipt_bytes", "sources_bytes"):
                reference[name] = int(reference[name])
        plan = prepare_plan(**arguments, baseline_reference=reference)
        raw = execute_plan(plan); print(raw.decode("ascii"), end="")
        return 0 if e.parse_json(raw)["status"] == "COMPLETED" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","raw_text_returned":false,"automatic_retry":false}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
