"""Fixed notebook AST view admitting only exact already-public job identities.

No generic hexadecimal/opaque-string exemption, source execution, port,
compiled-job provenance, performance acceptance or attempt reset is granted.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from . import extended_owner_mia_source_view as view
from . import extended_owner_mia_discovery as discovery

diagnostic, predecessor, capture, e, files = view.diagnostic, view.predecessor, view.capture, view.e, view.files
LANE, PRIVATE_ROOT = view.LANE, view.PRIVATE_ROOT
MODULE = capture.PREFIX + "extended_owner_mia_source_job_view.py"
LEDGER = capture.PREFIX + "extended_owner_recovery_observations30.json"
LEDGER_SHA256 = "0d42011a1a7e2c94fe9a5df948d5fa21b9a0546e7f69b8036f2532ac7073d8ef"
VIEW_SHA256 = "c214171da13cfc8c492bb8a399fbde51ae7fafbc94eae57734d7c972f541cccf"
DISCOVERY_SHA256 = "93b45e421a6fe15a52411a7bcd1ca74ce3877bec038de7f662d7e91bb664403c"
ADDITIONS = (discovery.MODULE, discovery.LOOK, LEDGER, MODULE)
SOURCE_PATHS = (*view.SOURCE_PATHS, *ADDITIONS)
OPERATION = "TPR-EXT26-OWNER-MIA-SOURCE-JOB-VIEW-20261013-001"
ARGS = view.ARGS
MAX_PRIVATE, MAX_SECONDS, MAX_PUBLIC = view.MAX_PRIVATE, 30, view.MAX_PUBLIC


def _fail(): raise e.EvidenceError("fixed public-job notebook view refused; no retry")


def _guard(head):
    view._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if Path(discovery.__file__) != LANE / discovery.MODULE or Path(discovery.__file__).resolve() != LANE / discovery.MODULE: _fail()
    if Path(view.__file__) != LANE / view.MODULE or Path(view.__file__).resolve() != LANE / view.MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE, capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = view._sources(head)
    for relative in ADDITIONS:
        _guard(head)
        committed = subprocess.run(["git", "show", head + ":" + relative], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        directory = files._directory((LANE / relative).parent, private=False)
        try:
            _guard(head)
            result[relative] = files._read(directory, Path(relative).name, expected_size=len(committed), expected_sha256=diagnostic._sha(committed),
                remaining=capture.MAX_RESPONSE, private=False)
        finally: os.close(directory)
    _guard(head)
    return result


def _public_ids(sources):
    if diagnostic._sha(sources[LEDGER]) != LEDGER_SHA256 or diagnostic._sha(sources[view.MODULE]) != VIEW_SHA256 or diagnostic._sha(sources[discovery.MODULE]) != DISCOVERY_SHA256: _fail()
    known = discovery._frozen({name: sources[name] for name in discovery.SOURCE_PATHS})
    ledger = e.parse_json(sources[LEDGER])
    if (ledger.get("schema") != "tpr-ext26-retrospective-owner-job-observations-v1" or ledger.get("study_id") != e.STUDY_ID
            or ledger.get("candidate_id") != predecessor.CANDIDATE or capture._integer(ledger.get("project_id"), 2**31 - 1) != predecessor.PROJECT
            or ledger.get("freeze_sha256") != e.FREEZE_SHA256 or ledger.get("calendar_sha256") != capture.ops.CALENDAR_SHA256
            or ledger.get("config_sha256") != discovery.CONFIG_SHA256 or capture._integer(ledger.get("retained_looks_before"), 30) != 20
            or capture._integer(ledger.get("retained_looks_after"), 30) != 30 or ledger.get("attempt_reset") is not False): _fail()
    rows = ledger.get("jobs"); historical = ledger.get("known_historical_jobs")
    if type(rows) is not list or len(rows) != 10 or type(historical) is not list or set(historical) != known: _fail()
    ids = set(known)
    for ordinal, row in enumerate(rows, 21):
        if type(row) is not dict or capture._integer(row.get("look_ordinal"), 30) != ordinal: _fail()
        identity = e._id(row.get("backtest_id"))
        if identity in ids or row.get("compiled_source_proven") is not False or row.get("economics_accepted") is not False or row.get("accepted_metrics") is not None: _fail()
        ids.add(identity)
    if len(ids) != 14: _fail()
    return frozenset(ids)


def _plan(**arguments):
    hashes = arguments.get("source_hashes")
    if type(hashes) is not dict or set(hashes) != set(SOURCE_PATHS): _fail()
    for name in ADDITIONS: e._hash(hashes[name])
    if hashes[view.MODULE] != VIEW_SHA256 or hashes[discovery.MODULE] != DISCOVERY_SHA256 or hashes[LEDGER] != LEDGER_SHA256 or hashes[discovery.LOOK] != discovery.LOOK_SHA256: _fail()
    old = view._plan(**{**arguments, "source_hashes": {name: hashes[name] for name in view.SOURCE_PATHS}})
    return {**old, "schema": "tpr-ext26-owner-mia-source-public-job-view-plan-v1", "operation_id": OPERATION,
        "source_hashes": dict(hashes), "public_identity_ledger_sha256": LEDGER_SHA256, "public_identity_count": 14,
        "public_identity_exception_notebook_code_only": True, "generic_opaque_or_hex_exception": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head); _public_ids(sources)
    plan = _plan(git_head=head, source_hashes={name: diagnostic._sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": diagnostic._sha(raw)}


def _notebook(text, hashes, public_ids):
    # The existing policy is unchanged; only exact already-public literals
    # are added. A secret-named assignment or market-row container still fails.
    result = view._notebook(text, hashes | set(public_ids))
    matched = set()
    if result["view_status"] == "NOTEBOOK_CODE_POLICY_PASSED":
        for row in result["cells"]:
            source = row.get("code_view", {}).get("static_python_view")
            if source is not None:
                tree = predecessor._tree(source)
                matched.update(node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and type(node.value) is str and node.value in public_ids)
    return {**result, "matched_already_public_job_literals": sorted(matched), "public_job_literal_ledger_sha256": LEDGER_SHA256,
        "matching_job_literal_proves_compiled_source": False, "generic_opaque_exception": False}


def _view(archive, delta, sources, report, check):
    public_ids = _public_ids(sources)
    changes, hashes = diagnostic._proof(archive, delta, sources, report)
    report["stage"] = "static_public_job_notebook_views"; views = []
    for row in changes:
        check(); name, kind = row["name"], row["kind"]
        before, after = row["before"] or "", row["after"] or ""
        if re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.py", name):
            try: viewed = view._python(before, after, hashes, added=kind == "added")
            except e.EvidenceError: viewed = {"view_status": "STATIC_PARSE_REFUSED", "static_python_view": None}
        elif re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.ipynb", name) and kind != "removed":
            try: viewed = _notebook(after, hashes, public_ids)
            except e.EvidenceError: viewed = {"view_status": "NOTEBOOK_SCHEMA_REFUSED", "source_withheld": True}
        else: viewed = {"view_status": "UNSUPPORTED_OR_REMOVED_FILE_METADATA_ONLY", "source_withheld": True}
        views.append({"name": name, "kind": kind, "before_identity": row["before_identity"], "after_identity": row["after_identity"], "view": viewed})
    report.update(views=views, all_changed_files_accounted=True, all_cloud_file_identities_accounted=True,
        public_job_literal_ledger_sha256=LEDGER_SHA256, public_identity_count=len(public_ids), public_identity_exception_notebook_code_only=True,
        generic_opaque_or_hex_exception=False, all_docstrings_comments_notebook_outputs_markdown_metadata_withheld=True,
        source_is_normalized_ast_view_only=True, source_not_executed=True, source_not_an_executable_port=True,
        general_secret_or_covert_data_absence_proven=False, compiled_source_proven=False, economics_accepted=False)
    report["stage"] = "static_public_job_view_complete"


def _execute(plan, sources, root, *, guard, clock, monotonic):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now or monotonic is not time.monotonic)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE))): _fail()
    _public_ids(sources)
    started = monotonic()
    def check():
        guard(plan["git_head"]); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= now < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: diagnostic._sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    report = {"schema": "tpr-ext26-owner-mia-source-public-job-view-receipt-v1", "operation_id": OPERATION, "git_head": plan["git_head"],
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
                "public_identity_ledger_sha256": LEDGER_SHA256, "max_private_bytes": MAX_PRIVATE, "max_reads": 2, "read_only": True}))
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
            check(); report["status"] = "COMPLETED_PUBLIC_JOB_STATIC_VIEW"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat(); raw = e.canonical(report)
        if len(raw) > MAX_PUBLIC:
            # The disclosure is refused, but the spent scope still gets a receipt.
            report["views"] = None; report["status"] = "FAILED_OR_UNCERTAIN"; report["public_size_refused"] = True
            raw = e.canonical(report)
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
        return 0 if e.parse_json(result)["status"] == "COMPLETED_PUBLIC_JOB_STATIC_VIEW" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"source_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
