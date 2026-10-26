"""Fixed post005 two-FD policy diagnosis; source/literals are never disclosed."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from . import extended_owner_mia_source_inspect as predecessor

capture, e, files = predecessor.capture, predecessor.e, predecessor.files
LANE, PRIVATE_ROOT = predecessor.LANE, predecessor.PRIVATE_ROOT
MODULE = capture.PREFIX + "extended_owner_mia_source_diagnostic.py"
SOURCE_PATHS = (*predecessor.SOURCE_PATHS, MODULE)
PREDECESSOR_SHA256 = "204bb9ed5554f32eaa5e2e47a088bc79a2baf1402497c8f207663e1ee1a34dc0"
OPERATION = "TPR-EXT26-OWNER-MIA-SOURCE-DIAG-20261013-001"
MAX_PRIVATE, MAX_SECONDS, MAX_PUBLIC = 401314, 30, 64 * 1024
ARGS = ("git_head", "source_hashes", "owner_instruction_sha256", "created_utc", "expires_utc", "archive", "diff", "mode")


def _fail(): raise e.EvidenceError("fixed source-policy diagnosis refused; no retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    predecessor._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if Path(predecessor.__file__) != LANE / predecessor.MODULE or Path(predecessor.__file__).resolve() != LANE / predecessor.MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE, capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = predecessor._sources(head); _guard(head)
    committed = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        _guard(head)
        result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(committed), expected_sha256=_sha(committed),
            remaining=capture.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    _guard(head)
    return result


def _plan(*, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc, archive=None, diff=None, mode="production"):
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if mode not in {"production", "offline-fixture"} or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (source_hashes[predecessor.MODULE] != PREDECESSOR_SHA256 or source_hashes[capture.BUNDLE] != capture.BUNDLE_SHA256
            or source_hashes[capture.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[capture.PREFIX + "extended_calendar.json"] != capture.ops.CALENDAR_SHA256): _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(minutes=15): _fail()
    archive = predecessor._descriptor(predecessor.ARCHIVE if archive is None else archive)
    diff = predecessor._descriptor(predecessor.DIFF if diff is None else diff)
    if archive["bytes"] + diff["bytes"] > MAX_PRIVATE or mode == "production" and (archive != predecessor.ARCHIVE or diff != predecessor.DIFF): _fail()
    return {"schema": "tpr-ext26-owner-mia-source-diagnostic-plan-v1", "operation_id": OPERATION,
        "capture_operation_id": predecessor.CAPTURE_OPERATION, "project_id": predecessor.PROJECT, "candidate_id": predecessor.CANDIDATE,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "archive": archive, "diff": diff, "mode": mode,
        "max_private_bytes": MAX_PRIVATE, "max_seconds": MAX_SECONDS, "max_reads": 2,
        "api_requests": 0, "source_disclosed": False, "source_executed": False, "new_jobs": 0, "automatic_retry": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _proof(archive_raw, diff_raw, sources, report):
    report["stage"] = "archive_schema"
    archive = e.parse_json(archive_raw); delta = e.parse_json(diff_raw)
    e._closed(archive, {"schema", "operation_id", "project_id", "request_index", "files"})
    if (archive["schema"] != "tpr-ext26-mia-all-source-v1" or archive["operation_id"] != predecessor.CAPTURE_OPERATION
            or capture._integer(archive["project_id"], 2**31 - 1) != predecessor.PROJECT
            or capture._integer(archive["request_index"], 2) != 2): _fail()
    current = archive["files"]; inventory = capture._inventory(current)
    report["stage"] = "delta_schema_and_identities"
    e._closed(delta, {"schema", "changes", "all_changed_file_bytes_retained", "diff_format", "source_executed", "economics_accepted"})
    if (delta["schema"] != "tpr-ext26-mia-complete-source-diff-v1" or delta["all_changed_file_bytes_retained"] is not True
            or delta["diff_format"] != "complete-whole-file-before-after-v1" or delta["source_executed"] is not False
            or delta["economics_accepted"] is not False or type(delta["changes"]) is not list or len(delta["changes"]) > 16): _fail()
    before, seen = dict(current), set()
    for row in delta["changes"]:
        e._closed(row, {"name", "kind", "before", "after", "before_identity", "after_identity"})
        name, kind = row["name"], row["kind"]
        if type(name) is not str or name in seen or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", name) is None: _fail()
        seen.add(name)
        if kind == "removed":
            if name in current or row["after"] is not None or row["after_identity"] is not None or type(row["before"]) is not str: _fail()
            before[name] = row["before"]
        elif kind in {"added", "changed"}:
            if name not in current or row["after"] != current[name] or e.canonical(row["after_identity"]) != e.canonical(inventory[name]): _fail()
            if kind == "added":
                if row["before"] is not None or row["before_identity"] is not None: _fail()
                before.pop(name)
            else:
                if type(row["before"]) is not str: _fail()
                before[name] = row["before"]
        else: _fail()
        if row["before"] is not None and e.canonical(row["before_identity"]) != e.canonical(capture._inventory({name: row["before"]})[name]): _fail()
    report["stage"] = "delta_recomputation"
    changes, expected = capture._diff(before, current)
    if e.canonical(delta) != expected: _fail()
    report["stage"] = "immutable_before_tree"
    candidates = e.parse_json(sources[capture.BUNDLE])["candidates"]
    frozen = [row["files"] for row in candidates if row["candidate_id"] == predecessor.CANDIDATE]
    if (len(frozen) != 1 or set(before) != capture.EXPECTED_FILES | {"research.ipynb"}
            or any(before[name] != frozen[0][name] for name in capture.EXPECTED_FILES)
            or _sha(before["research.ipynb"].encode()) != predecessor.NOTEBOOK_SHA256): _fail()
    # Match the predecessor's public exemptions exactly; this diagnostic's
    # new source identity does not widen the earlier literal policy.
    hashes = {_sha(sources[name]) for name in predecessor.SOURCE_PATHS} | {predecessor.AUDIT_SHA256, predecessor.NOTEBOOK_SHA256}
    hashes.update(row["sha256"] for row in capture._inventory(frozen[0]).values())
    hashes.update(_sha(row["config_raw"].encode()) for row in candidates)
    report.update(all_current_file_identities=inventory, all_changed_file_metadata=changes,
        all_changes_recomputed=True, before_matches_public_immutable_bundle=True)
    return delta["changes"], hashes


def _event(reason, node=None, text="", segment=None):
    fragment = segment if segment is not None else ast.get_source_segment(text, node) if node is not None else None
    string_literal = isinstance(node, ast.Constant) and type(node.value) is str
    raw = node.value.encode() if string_literal else fragment.encode() if type(fragment) is str else None
    # Do not publish even a separate digest of a potentially secret/licensed
    # literal. Only the complete file content identity is exposed elsewhere.
    return {"reason": reason, "line": getattr(node, "lineno", None), "node_type": type(node).__name__ if node is not None else None,
        "literal_sha256": None, "literal_bytes": len(raw) if raw is not None else None,
        "literal_type": type(node.value).__name__ if isinstance(node, ast.Constant) else None,
        "length_representation": "string_literal_utf8" if string_literal else "source_segment_utf8" if raw is not None else None,
        "literal_digest_withheld": True}


def _classification(before, after, public_hashes):
    # Preserve the predecessor's predicate order; these labels describe that
    # conservative screen, not proof that a matched value actually is secret.
    trees = []
    for role, text in (("BEFORE", before), ("AFTER", after)):
        if type(text) is not str or len(text.encode()) > 128 * 1024: return _event(role + "_SOURCE_BOUND")
        try: tree = ast.parse(text)
        except (SyntaxError, RecursionError): return _event(role + "_SYNTAX_OR_RECURSION")
        if sum(1 for _ in ast.walk(tree)) > 12000: return _event(role + "_AST_NODE_BOUND")
        trees.append(tree)
    previous_tree, tree = trees
    previous = {node.value for node in ast.walk(previous_tree) if isinstance(node, ast.Constant) and type(node.value) is str}
    previous_nodes = {ast.dump(node) for node in ast.walk(previous_tree)}
    secret_name = re.compile(r"(?i)_?(?:api_?key|api_?token|qc_api_token|qc_user_id|user_id|account_id|password|passphrase|access_token|secret|credential|authorization)")
    market_keys = {"ticker", "symbol", "price", "target", "target_price", "market_cap", "volume", "ratings"}
    field_keys = {id(key) for node in ast.walk(tree) if isinstance(node, ast.Dict) for key in node.keys
        if isinstance(key, ast.Constant) and type(key.value) is str and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", key.value)
        and not secret_name.fullmatch(key.value) and key.value not in market_keys}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [child.id if isinstance(child, ast.Name) else child.attr if isinstance(child, ast.Attribute) else ""
                for target in targets for child in ast.walk(target)]
            if any(secret_name.fullmatch(name) for name in names) and isinstance(node.value, ast.Constant) and node.value.value not in (None, "", False):
                return _event("SECRET_NAMED_LITERAL_ASSIGNMENT", node.value, after)
        if isinstance(node, ast.Dict):
            keys = {key.value.lower() for key in node.keys if isinstance(key, ast.Constant) and type(key.value) is str}
            if ast.dump(node) not in previous_nodes and (keys & market_keys or any(secret_name.fullmatch(key) for key in keys)):
                try: value = ast.literal_eval(node)
                except (ValueError, TypeError, SyntaxError): pass
                else:
                    if value: return _event("NEW_LITERAL_MARKET_OR_CREDENTIAL_DICT", node, after)
        if isinstance(node, (ast.List, ast.Tuple)) and ast.dump(node) not in previous_nodes:
            try: value = ast.literal_eval(node)
            except (ValueError, TypeError, SyntaxError): pass
            else:
                if any(type(item) in {dict, list, tuple} and len(item) >= 2 for item in value): return _event("NEW_LITERAL_NESTED_ROW_CONTAINER", node, after)
        if isinstance(node, ast.Constant) and type(node.value) is str and node.value not in previous:
            value = node.value
            if len(value.encode()) > 1024: return _event("NEW_STRING_BYTE_BOUND", node, after)
            if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", value): return _event("NEW_PRIVATE_KEY_MARKER", node, after)
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value): return _event("NEW_EMAIL_PATTERN", node, after)
            if re.fullmatch(r"[A-Za-z0-9+/=_-]{32,}", value) and value not in public_hashes and id(node) not in field_keys:
                return _event("NEW_OPAQUE_STRING_LITERAL", node, after)
    changed = "\n".join(line[1:] for line in difflib.unified_diff(before.splitlines(), after.splitlines(), n=0)
        if line.startswith("+") and not line.startswith("+++"))
    matched = re.search(r"(?i)(?:api[_ -]?(?:key|token)|password|passphrase|private[_ -]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{12,}", changed)
    if matched is not None: return _event("CHANGED_LINE_CREDENTIAL_PATTERN", segment=matched.group())
    return None


def _diagnose(archive, delta, sources, report, check):
    changes, public_hashes = _proof(archive, delta, sources, report)
    report["stage"] = "static_policy"
    rows = []
    for row in changes:
        check(); name = row["name"]
        if name == "research.ipynb":
            rows.append({"name": name, "classification": "NOTEBOOK_METADATA_ONLY", "policy_refused": None, "event": None}); continue
        if re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.py", name) is None:
            rows.append({"name": name, "classification": "PYTHON_FILENAME_REFUSED", "policy_refused": True, "event": None}); continue
        before, after = row["before"] or "", row["after"] or ""
        event = _classification(before, after, public_hashes)
        refused = False
        try: predecessor._safe_source(before, after, public_hashes)
        except e.EvidenceError: refused = True
        classification = "POLICY_REFUSED" if refused and event is not None else "UNCLASSIFIED_POLICY_REFUSAL" if refused else "CLASSIFIER_POLICY_DISAGREEMENT" if event is not None else "POLICY_PASSED_NO_DISCLOSURE"
        rows.append({"name": name, "kind": row["kind"], "before_identity": row["before_identity"], "after_identity": row["after_identity"],
            "classification": classification, "policy_refused": refused, "event": event})
    report.update(policy_diagnostics=rows, source_disclosed=False, source_executed=False,
        general_secret_or_covert_data_absence_proven=False, economics_accepted=False, compiled_source_proven=False)
    report["stage"] = "diagnosis_complete"


def _execute(plan, sources, root, *, guard, clock, monotonic):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now or monotonic is not time.monotonic)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE))): _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"]); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= now < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    report = {"schema": "tpr-ext26-owner-mia-source-diagnostic-receipt-v1", "operation_id": OPERATION,
        "git_head": plan["git_head"], "source_hashes": plan["source_hashes"], "plan_sha256": _sha(e.canonical(plan)),
        "owner_instruction_sha256": plan["owner_instruction_sha256"], "status": "FAILED_OR_UNCERTAIN", "stage": "preflight",
        "scope_spent": True, "private_read_attempts": 0, "private_read_bytes": 0, "policy_diagnostics": None,
        "all_changes_recomputed": False, "before_matches_public_immutable_bundle": False,
        "api_requests": 0, "source_disclosed": False, "source_executed": False,
        "new_jobs": 0, "new_codex_attempts": 0, "attempt_reset": False, "automatic_retry": False,
        "accepted_metrics": None, "compiled_source_proven": False, "canonical_admission": False, "trading": False}
    try:
        check(); capture._publish(directory, OPERATION + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, OPERATION + ".access.json", e.canonical({"plan_sha256": report["plan_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"], "archive": plan["archive"], "diff": plan["diff"],
                "max_private_bytes": MAX_PRIVATE, "max_reads": 2, "read_only": True}))
            bodies = {}
            for role, suffix in (("archive", ".read2.sources.json"), ("diff", ".diff.json")):
                report["stage"] = role + "_fd_read"; descriptor = plan[role]
                check(); capture._publish(directory, OPERATION + "." + role + ".read.spent.json", e.canonical({
                    "plan_sha256": report["plan_sha256"], "name": predecessor.CAPTURE_OPERATION + suffix, **descriptor}))
                report["private_read_attempts"] += 1
                check(); raw = files._read(directory, predecessor.CAPTURE_OPERATION + suffix, expected_size=descriptor["bytes"],
                    expected_sha256=descriptor["sha256"], remaining=MAX_PRIVATE - report["private_read_bytes"], private=True)
                report["private_read_bytes"] += len(raw); bodies[role] = raw
            _diagnose(bodies["archive"], bodies["diff"], sources, report, check)
            check(); report["status"] = "COMPLETED_POLICY_DIAGNOSTIC"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat(); raw = e.canonical(report)
        if len(raw) > MAX_PUBLIC: _fail()
        capture._publish(directory, OPERATION + ".result.json", raw)
        return raw
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def _now(): return datetime.now(timezone.utc)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_now, monotonic=time.monotonic)


def execute_fixture(plan, sources, root, *, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    if type(plan) is not dict or plan.get("mode") != "offline-fixture": _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True); parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.plan_json.encode()
        if _sha(raw) != e._hash(args.plan_sha256): _fail()
        result = execute_plan(e.parse_json(raw)); print(result.decode(), end="")
        return 0 if e.parse_json(result)["status"] == "COMPLETED_POLICY_DIAGNOSTIC" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"source_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
