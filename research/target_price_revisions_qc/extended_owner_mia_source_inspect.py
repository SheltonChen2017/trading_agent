"""Fixed two-FD own-OFF source-diff inspection; never executes cloud code.

Only a fresh scope admits the named post005 archive/diff. Full files remain
private; bounded static Python changes may be disclosed after conservative
literal checks. These checks are not general covert-data/secret-absence proof.
Current project source is not authenticated compiled-job source or economics.
"""
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

from . import extended_mia_capture as capture

e, files = capture.e, capture.files
LANE, PRIVATE_ROOT, PROJECT, CANDIDATE = capture.LANE, capture.PRIVATE_ROOT, capture.PROJECT, capture.CANDIDATE
MODULE = capture.PREFIX + "extended_owner_mia_source_inspect.py"
SOURCE_PATHS = (*capture.SOURCE_PATHS, MODULE)
CAPTURE_OPERATION = "TPR-EXT26-MIA-SOURCE-POST-20261013-005"
ARCHIVE = {"bytes": 250129, "sha256": "56b1609572a053aaeb6651dfdca3d55488be0a0f49b4d8f85bc2f3733bd69e36"}
DIFF = {"bytes": 151185, "sha256": "3127ecffa93f941093affb33aa92025c75d9b878201e9415dd98f8c441bb649d"}
NOTEBOOK_SHA256 = "af27200522531d426185f4daa25d23610c164134e3ab7fdf38919616d0d5b344"
AUDIT_SHA256 = "bce4182d09dc9d31132cb54d404712471ddff5e2b706c2988fbe9fcc48c93aea"
MAX_PRIVATE, MAX_SECONDS, MAX_PUBLIC = 401314, 30, 64 * 1024
ARGS = ("operation_id", "git_head", "source_hashes", "owner_instruction_sha256", "created_utc", "expires_utc", "archive", "diff", "mode")
Refusal = e.EvidenceError


def _fail(): raise Refusal("fixed own-OFF source inspection refused; no automatic retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    capture._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = capture._sources(head); _guard(head)
    raw = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        _guard(head)
        result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(raw), expected_sha256=_sha(raw),
            remaining=capture.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    _guard(head)
    return result


def _descriptor(value):
    e._closed(value, {"bytes", "sha256"})
    size = capture._integer(value["bytes"], MAX_PRIVATE)
    if not size: _fail()
    return {"bytes": size, "sha256": e._hash(value["sha256"])}


def _plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc,
          archive=None, diff=None, mode="production"):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-EXT26-OWNER-MIA-SOURCE-INSPECT-[A-Za-z0-9-]{1,50}", operation_id) is None
            or mode not in {"production", "offline-fixture"}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (source_hashes[capture.BUNDLE] != capture.BUNDLE_SHA256
            or source_hashes[capture.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[capture.PREFIX + "extended_calendar.json"] != capture.ops.CALENDAR_SHA256): _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(hours=1): _fail()
    archive, diff = _descriptor(ARCHIVE if archive is None else archive), _descriptor(DIFF if diff is None else diff)
    if archive["bytes"] + diff["bytes"] > MAX_PRIVATE or mode == "production" and (archive != ARCHIVE or diff != DIFF): _fail()
    return {"schema": "tpr-ext26-owner-mia-source-inspect-plan-v1", "operation_id": operation_id,
        "project_id": PROJECT, "candidate_id": CANDIDATE, "capture_operation_id": CAPTURE_OPERATION,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "archive": archive, "diff": diff, "mode": mode,
        "max_private_bytes": MAX_PRIVATE, "max_seconds": MAX_SECONDS, "max_public_bytes": MAX_PUBLIC,
        "network_requests": 0, "cloud_source_executed": False, "source_current_equals_job_compiled": False,
        "new_codex_attempts": 0, "new_jobs_launched": 0, "attempt_reset": False, "automatic_retry": False,
        "strategy_accepted": False, "canonical_admission": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _tree(text):
    if type(text) is not str or len(text.encode()) > 128 * 1024: _fail()
    try: tree = ast.parse(text)
    except (SyntaxError, RecursionError): _fail()
    if sum(1 for _ in ast.walk(tree)) > 12000: _fail()
    return tree


def _safe_source(before, after, public_hashes):
    """Conservative explicit-literal screen, not arbitrary encoding detection."""
    previous_tree = _tree(before)
    previous = {node.value for node in ast.walk(previous_tree) if isinstance(node, ast.Constant) and type(node.value) is str}
    previous_nodes = {ast.dump(node) for node in ast.walk(previous_tree)}
    tree = _tree(after)
    secret_name = re.compile(r"(?i)_?(?:api_?key|api_?token|qc_api_token|qc_user_id|user_id|account_id|password|passphrase|access_token|secret|credential|authorization)")
    market_keys = {"ticker", "symbol", "price", "target", "target_price", "market_cap", "volume", "ratings"}
    field_keys = {id(key) for node in ast.walk(tree) if isinstance(node, ast.Dict) for key in node.keys
        if isinstance(key, ast.Constant) and type(key.value) is str
        and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", key.value) and not secret_name.fullmatch(key.value) and key.value not in market_keys}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [child.id if isinstance(child, ast.Name) else child.attr if isinstance(child, ast.Attribute) else ""
                for target in targets for child in ast.walk(target)]
            if any(secret_name.fullmatch(name) for name in names) and isinstance(node.value, ast.Constant) and node.value.value not in (None, "", False): _fail()
        if isinstance(node, ast.Dict):
            keys = {key.value.lower() for key in node.keys if isinstance(key, ast.Constant) and type(key.value) is str}
            if ast.dump(node) not in previous_nodes and (keys & market_keys or any(secret_name.fullmatch(key) for key in keys)):
                try: value = ast.literal_eval(node)
                except (ValueError, TypeError, SyntaxError): pass
                else:
                    if value: _fail()
        if isinstance(node, (ast.List, ast.Tuple)) and ast.dump(node) not in previous_nodes:
            try: value = ast.literal_eval(node)
            except (ValueError, TypeError, SyntaxError): pass
            else:
                if any(type(item) in {dict, list, tuple} and len(item) >= 2 for item in value): _fail()
        if isinstance(node, ast.Constant) and type(node.value) is str and node.value not in previous:
            value = node.value
            if (len(value.encode()) > 1024 or re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", value)
                    or re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value)
                    or re.fullmatch(r"[A-Za-z0-9+/=_-]{32,}", value) and value not in public_hashes and id(node) not in field_keys): _fail()
    # Comments are disclosed too: refuse obvious credential-bearing comments.
    changed = "\n".join(line[1:] for line in difflib.unified_diff(before.splitlines(), after.splitlines(), n=0)
        if line.startswith("+") and not line.startswith("+++"))
    if re.search(r"(?i)(?:api[_ -]?(?:key|token)|password|passphrase|private[_ -]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{12,}", changed): _fail()


def _inspect(archive_raw, diff_raw, sources):
    archive, delta = e.parse_json(archive_raw), e.parse_json(diff_raw)
    e._closed(archive, {"schema", "operation_id", "project_id", "request_index", "files"})
    if (archive["schema"] != "tpr-ext26-mia-all-source-v1" or archive["operation_id"] != CAPTURE_OPERATION
            or capture._integer(archive["project_id"], 2**31 - 1) != PROJECT
            or capture._integer(archive["request_index"], 2) != 2): _fail()
    current = archive["files"]; inventory = capture._inventory(current)
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
    changes, expected = capture._diff(before, current)
    if e.canonical(delta) != expected: _fail()
    frozen = [row["files"] for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE]
    if (len(frozen) != 1 or set(before) != capture.EXPECTED_FILES | {"research.ipynb"}
            or any(before[name] != frozen[0][name] for name in capture.EXPECTED_FILES)
            or _sha(before["research.ipynb"].encode()) != NOTEBOOK_SHA256): _fail()
    public_hashes = set(sources and [_sha(raw) for raw in sources.values()]) | {AUDIT_SHA256, NOTEBOOK_SHA256}
    public_hashes.update(row["sha256"] for row in capture._inventory(frozen[0]).values())
    public_hashes.update(_sha(row["config_raw"].encode()) for row in e.parse_json(sources[capture.BUNDLE])["candidates"])
    disclosures = []
    for row in delta["changes"]:
        name = row["name"]
        if name == "research.ipynb":
            disclosures.append({"name": name, "kind": row["kind"], "body_disclosed": False, "classification": "notebook_metadata_only"})
            continue
        if re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.py", name) is None: _fail()
        old, new = row["before"] or "", row["after"] or ""
        _safe_source(old, new, public_hashes)
        text = new if row["kind"] == "added" else "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(),
            fromfile=name + ".before", tofile=name + ".after", lineterm="", n=3))
        disclosures.append({"name": name, "kind": row["kind"], "body_disclosed": True, "static_python_text": text})
    result = {"all_current_file_identities": inventory, "all_changed_file_metadata": changes,
        "all_changes_recomputed": True, "before_matches_public_immutable_bundle": True,
        "known_audit_helper_hash_matches": inventory.get("audit_key_recovery.py", {}).get("sha256") == AUDIT_SHA256,
        "disclosures": disclosures, "source_not_executed": True, "current_source_is_compiled_job_proof": False,
        "general_secret_or_covert_data_absence_proven": False, "economics_accepted": False}
    if len(e.canonical(result)) > MAX_PUBLIC: _fail()
    return result


def _execute(plan, sources, root, *, guard, clock, monotonic):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now or monotonic is not time.monotonic)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE))): _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"]); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    operation = plan["operation_id"]
    report = {"schema": "tpr-ext26-owner-mia-source-inspect-receipt-v1", "operation_id": operation,
        "capture_operation_id": CAPTURE_OPERATION, "project_id": PROJECT, "candidate_id": CANDIDATE,
        "git_head": plan["git_head"], "source_hashes": plan["source_hashes"], "plan_sha256": _sha(e.canonical(plan)),
        "owner_instruction_sha256": plan["owner_instruction_sha256"], "status": "FAILED_OR_UNCERTAIN", "scope_spent": True,
        "private_read_attempts": 0, "private_read_bytes": 0, "inspection": None, "network_requests": 0,
        "cloud_source_executed": False, "compiled_source_proven": False, "new_codex_attempts": 0,
        "new_jobs_launched": 0, "attempt_reset": False, "automatic_retry": False, "accepted_metrics": None,
        "strategy_accepted": False, "canonical_admission": False, "trading": False}
    try:
        check(); capture._publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, operation + ".access.json", e.canonical({"plan_sha256": report["plan_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"], "fixed_archive": plan["archive"],
                "fixed_diff": plan["diff"], "max_private_bytes": MAX_PRIVATE, "read_only": True}))
            bodies = {}
            for role, suffix in (("archive", ".read2.sources.json"), ("diff", ".diff.json")):
                descriptor = plan[role]
                request = {"plan_sha256": report["plan_sha256"], "name": CAPTURE_OPERATION + suffix, **descriptor}
                check(); capture._publish(directory, operation + "." + role + ".read.spent.json", e.canonical(request))
                report["private_read_attempts"] += 1
                check(); raw = files._read(directory, CAPTURE_OPERATION + suffix, expected_size=descriptor["bytes"],
                    expected_sha256=descriptor["sha256"], remaining=MAX_PRIVATE - report["private_read_bytes"], private=True)
                report["private_read_bytes"] += len(raw); bodies[role] = raw
            inspected = _inspect(bodies["archive"], bodies["diff"], sources)
            check(); report["inspection"] = inspected; report["status"] = "COMPLETED_SOURCE_INSPECTION"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat(); raw = e.canonical(report)
        if len(raw) > MAX_PUBLIC:
            # The disclosure is refused, but the spent scope still gets a receipt.
            report["inspection"] = None; report["status"] = "FAILED_OR_UNCERTAIN"; report["public_size_refused"] = True
            raw = e.canonical(report)
            if len(raw) > MAX_PUBLIC: _fail()
        capture._publish(directory, operation + ".result.json", raw)
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
        return 0 if e.parse_json(result)["status"] == "COMPLETED_SOURCE_INSPECTION" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"source_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
