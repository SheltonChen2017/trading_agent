"""Fixed source-only AST views with docstrings/comments/notebook outputs withheld.

These views are not byte-equivalent source, an executable port, compiled-job
provenance, economics approval or general covert-data/secret-absence proof.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import difflib
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from . import extended_owner_mia_source_diagnostic as diagnostic

predecessor, capture, e, files = diagnostic.predecessor, diagnostic.capture, diagnostic.e, diagnostic.files
LANE, PRIVATE_ROOT = diagnostic.LANE, diagnostic.PRIVATE_ROOT
MODULE = capture.PREFIX + "extended_owner_mia_source_view.py"
SOURCE_PATHS = (*diagnostic.SOURCE_PATHS, MODULE)
DIAGNOSTIC_SHA256 = "0f661bc47c1bf6d044c4cf421dfd084e355530cc21f409a4bb8946c5752010bd"
OPERATION = "TPR-EXT26-OWNER-MIA-SOURCE-VIEW-20261013-001"
ARGS = diagnostic.ARGS
MAX_PRIVATE, MAX_SECONDS, MAX_PUBLIC = diagnostic.MAX_PRIVATE, 30, 64 * 1024


def _fail(): raise e.EvidenceError("fixed AST source view refused; no retry")


def _guard(head):
    diagnostic._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if Path(diagnostic.__file__) != LANE / diagnostic.MODULE or Path(diagnostic.__file__).resolve() != LANE / diagnostic.MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE, capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = diagnostic._sources(head); _guard(head)
    committed = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        _guard(head)
        result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(committed), expected_sha256=diagnostic._sha(committed),
            remaining=capture.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    _guard(head)
    return result


def _plan(**arguments):
    hashes = arguments.get("source_hashes")
    if type(hashes) is not dict or set(hashes) != set(SOURCE_PATHS) or hashes[diagnostic.MODULE] != DIAGNOSTIC_SHA256: _fail()
    e._hash(hashes[MODULE])
    old = diagnostic._plan(**{**arguments, "source_hashes": {name: hashes[name] for name in diagnostic.SOURCE_PATHS}})
    return {**old, "schema": "tpr-ext26-owner-mia-source-view-plan-v1", "operation_id": OPERATION, "source_hashes": dict(hashes),
        "all_syntactic_docstrings_withheld": True, "all_comments_withheld": True, "notebook_outputs_markdown_metadata_withheld": True,
        "source_is_normalized_ast_view_only": True, "source_not_an_executable_port": True}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: diagnostic._sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": diagnostic._sha(raw)}


def _masked(text):
    tree = predecessor._tree(text); omitted = []
    references = any(isinstance(node, ast.Attribute) and node.attr == "__doc__" or isinstance(node, ast.Name) and node.id == "__doc__"
        for node in ast.walk(tree))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or not node.body: continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and type(first.value.value) is str:
            omitted.append({"scope": type(node).__name__, "line": first.lineno, "end_line": first.end_lineno,
                "bytes": len(first.value.value.encode()), "literal_digest_withheld": True})
            node.body[0] = ast.copy_location(ast.Expr(value=ast.Constant(value=Ellipsis)), first)
    normalized = ast.unparse(ast.fix_missing_locations(tree)) + "\n"
    return normalized, omitted, references


def _python(before, after, public_hashes, *, added):
    old, old_docs, _old_refs = _masked(before)
    new, new_docs, refs = _masked(after)
    result = {"view_status": "POLICY_REFUSED", "before_docstrings_withheld": old_docs, "after_docstrings_withheld": new_docs,
        "docstring_reference_detected": refs, "comments_withheld": True, "source_not_executed": True,
        "source_is_normalized_ast_view_only": True, "byte_equivalence_or_docstring_inertness_proven": False}
    try: predecessor._safe_source(old, new, public_hashes)
    except e.EvidenceError:
        result["refusal_event"] = diagnostic._classification(old, new, public_hashes)
        return result
    body = new if added else "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile="before.normalized",
        tofile="after.normalized", lineterm="", n=3))
    return {**result, "view_status": "STATIC_POLICY_PASSED", "view_format": "normalized_ast_python" if added else "normalized_ast_unified_diff",
        "static_python_view": body, "refusal_event": None}


def _notebook(text, public_hashes):
    notebook = e.parse_json(text.encode())
    e._closed(notebook, {"cells", "metadata", "nbformat", "nbformat_minor"})
    if capture._integer(notebook["nbformat"], 4) != 4 or capture._integer(notebook["nbformat_minor"], 20) > 20: _fail()
    cells = notebook["cells"]
    if type(cells) is not list or len(cells) > 128 or type(notebook["metadata"]) is not dict: _fail()
    result, refused = [], False
    allowed = {"cell_type", "metadata", "source", "execution_count", "outputs", "id", "attachments"}
    for index, cell in enumerate(cells):
        if type(cell) is not dict or not set(cell) <= allowed: _fail()
        kind = cell.get("cell_type")
        row = {"cell_index": index, "cell_type": kind if kind in {"code", "markdown", "raw"} else "unsupported_cell_type",
            "outputs_withheld": True, "metadata_withheld": True, "source_withheld": True}
        if kind != "code": result.append(row); continue
        text = cell.get("source")
        if type(text) is list and len(text) <= 4096 and all(type(line) is str for line in text): text = "".join(text)
        if type(text) is not str: _fail()
        try: viewed = _python("", text, public_hashes, added=True)
        except e.EvidenceError: viewed = {"view_status": "STATIC_PARSE_REFUSED", "static_python_view": None}
        refused = refused or viewed["view_status"] != "STATIC_POLICY_PASSED"
        result.append({**row, "code_view": viewed})
    if refused:
        for row in result:
            if "code_view" in row: row["code_view"].pop("static_python_view", None)
    else:
        for row in result:
            if "code_view" in row: row["source_withheld"] = False
    return {"view_status": "NOTEBOOK_CODE_POLICY_REFUSED" if refused else "NOTEBOOK_CODE_POLICY_PASSED", "cells": result,
        "outputs_markdown_raw_metadata_withheld": True, "source_not_executed": True, "notebook_byte_equivalence_proven": False}


def _view(archive, delta, sources, report, check):
    changes, hashes = diagnostic._proof(archive, delta, sources, report)
    report["stage"] = "static_masked_views"; views = []
    for row in changes:
        check(); name, kind = row["name"], row["kind"]
        before, after = row["before"] or "", row["after"] or ""
        if re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.py", name):
            try: viewed = _python(before, after, hashes, added=kind == "added")
            except e.EvidenceError: viewed = {"view_status": "STATIC_PARSE_REFUSED", "static_python_view": None}
        elif re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.ipynb", name) and kind != "removed":
            try: viewed = _notebook(after, hashes)
            except e.EvidenceError: viewed = {"view_status": "NOTEBOOK_SCHEMA_REFUSED", "source_withheld": True}
        else: viewed = {"view_status": "UNSUPPORTED_OR_REMOVED_FILE_METADATA_ONLY", "source_withheld": True}
        views.append({"name": name, "kind": kind, "before_identity": row["before_identity"], "after_identity": row["after_identity"], "view": viewed})
    report.update(views=views, all_changed_files_accounted=True, all_cloud_file_identities_accounted=True,
        all_docstrings_comments_notebook_outputs_markdown_metadata_withheld=True,
        remaining_literal_policy="pinned-source-inspector-81b6-unmodified", source_is_normalized_ast_view_only=True,
        source_not_executed=True, source_not_an_executable_port=True, general_secret_or_covert_data_absence_proven=False,
        compiled_source_proven=False, economics_accepted=False)
    report["stage"] = "static_view_complete"


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
                or {name: diagnostic._sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    report = {"schema": "tpr-ext26-owner-mia-source-view-receipt-v1", "operation_id": OPERATION, "git_head": plan["git_head"],
        "source_hashes": plan["source_hashes"], "plan_sha256": diagnostic._sha(e.canonical(plan)), "owner_instruction_sha256": plan["owner_instruction_sha256"],
        "status": "FAILED_OR_UNCERTAIN", "stage": "preflight", "scope_spent": True, "private_read_attempts": 0, "private_read_bytes": 0,
        "views": None, "api_requests": 0, "source_executed": False, "new_jobs": 0, "new_codex_attempts": 0, "attempt_reset": False,
        "automatic_retry": False, "accepted_metrics": None, "compiled_source_proven": False, "canonical_admission": False, "trading": False}
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
            _view(bodies["archive"], bodies["diff"], sources, report, check)
            check(); report["status"] = "COMPLETED_STATIC_SOURCE_VIEW"
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
        if diagnostic._sha(raw) != e._hash(args.plan_sha256): _fail()
        result = execute_plan(e.parse_json(raw)); print(result.decode(), end="")
        return 0 if e.parse_json(result)["status"] == "COMPLETED_STATIC_SOURCE_VIEW" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"source_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
