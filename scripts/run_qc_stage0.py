"""Launch and supervise the frozen Stage 0 and Stage 1 QuantConnect runs.

Owner conventions (docs/process/QC_RUN_CONVENTIONS.md):

  * project names are ``[number]. [FAMILY]_[UNIVERSE] - [YYYYMMDD]``;
  * AT MOST TWO cloud sessions run concurrently — the caller launches a
    round of one or two runs and must ``wait`` for both to finish (logs
    retrieved) before launching the next round.

Every launch is a counted real-market research look the moment the cloud
executes reviewed result-producing source, whether or not it succeeds.
This driver records the evidence the ledger needs — exact source SHA-256
of the uploaded (universe-rewritten) file, project ID and name, compile
ID, backtest ID, UTC times, and the raw log with its SHA-256 — into one
JSON evidence file per run under the git-ignored ``artifacts/`` tree.

It uploads only files from ``research/lean/`` at the current HEAD; it
refuses a dirty source file so the recorded Git commit genuinely
identifies the uploaded bytes.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.quantconnect import (  # noqa: E402
    QuantConnectClient,
    QuantConnectError,
)
from assistant.runtime_identity import (  # noqa: E402
    RuntimeIdentityError,
    current_commit,
)

ROOT = Path(__file__).resolve().parents[1]
LEAN = ROOT / "research" / "lean"
ENTRY_FILE = "main.py"
POLL_SECONDS = 30
MAX_WAIT_SECONDS = 16_200      # 4.5 hours; the prior monthly run took ~80 min
STALL_WAIT_SECONDS = 2_400     # 40 min without any observable state change
LOG_PAGE_LINES = 200           # backtests/read/log paginates by line numbers
MAX_LOG_PAGES = 1_000

FAMILIES = {
    "monthly": ("MONTHLY_BATTERY", LEAN / "alpha_battery_monthly.py"),
    "short": ("SHORT_BATTERY", LEAN / "alpha_battery_short.py"),
    "benchmark": ("UNIVERSE_BENCHMARK", LEAN / "universe_benchmark.py"),
    # Stage 1 (owner go 2026-08-18): the two frozen replication specs and
    # their cadence-matched benchmark. Same counted-look, serial-run, and
    # evidence rules as Stage 0; the 24-cell family gates live in
    # scripts/analyse_qc_alpha_stage1.py, never here.
    "stage1": ("STAGE1_REPLICATIONS", LEAN / "alpha_stage1_replications.py"),
    "stage1-benchmark": ("STAGE1_BENCHMARK", LEAN / "alpha_stage1_benchmark.py"),
}
UNIVERSES = ("A_large", "B_core", "C_broad")


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _git_commit_of(path: Path) -> str:
    """Exact shared runtime identity, refusing any uncommitted source.

    The evidence contract binds the run to a Git commit; uploading locally
    modified bytes would make that binding a lie.
    """
    try:
        return current_commit(require_clean=True, repository=ROOT)
    except RuntimeIdentityError as exc:
        raise SystemExit(f"{path} is not attributable to a clean commit: {exc}") from exc


def _retarget_universe(source: str, universe: str) -> str:
    """Rewrite the declared ACTIVE_UNIVERSE constant, refusing ambiguity."""
    if universe not in UNIVERSES:
        raise SystemExit(f"unknown universe {universe!r}")
    pattern = r'^ACTIVE_UNIVERSE = "(?:A_large|B_core|C_broad)"$'
    replacement = f'ACTIVE_UNIVERSE = "{universe}"'
    rewritten, count = re.subn(pattern, replacement, source, count=2, flags=re.M)
    if count != 1:
        raise SystemExit(
            f"expected exactly one ACTIVE_UNIVERSE constant, found {count}; "
            "refusing to run an algorithm whose screen is unknown"
        )
    return rewritten


def _project_name(number: int, family_label: str, universe: str, date: str) -> str:
    """docs/process/QC_RUN_CONVENTIONS.md section 1."""
    if number < 1:
        raise SystemExit("project number must be a positive integer")
    try:
        _dt.datetime.strptime(date, "%Y%m%d")
    except (TypeError, ValueError):
        raise SystemExit("project date must use YYYYMMDD")
    return f"{number}. {family_label}_{universe.upper()} - {date}"


def _new_evidence_path(raw_path: str) -> Path:
    """Return a new immutable JSON path inside the ignored artifacts tree."""
    path = Path(raw_path).resolve()
    artifacts = (ROOT / "artifacts").resolve()
    if path.suffix.lower() != ".json" or not path.is_relative_to(artifacts):
        raise SystemExit("evidence must be a .json file under artifacts/")
    if path.exists() or path.with_suffix(".log").exists():
        raise SystemExit(f"evidence already exists; refusing to overwrite {path}")
    return path


def _project_record(response: dict, project_id: int | None = None) -> dict:
    """Extract one exact project identity, refusing absent or ambiguous data."""
    projects = response.get("projects") or []
    if project_id is not None:
        matching = []
        for item in projects:
            try:
                if int(item.get("projectId", 0)) == project_id:
                    matching.append(item)
            except (TypeError, ValueError):
                continue
        projects = matching
    if len(projects) != 1 or not str(projects[0].get("name") or "").strip():
        raise QuantConnectError("project response lacks one exact id/name record")
    return projects[0]


def _wait_for_compile(client: QuantConnectClient, project_id: int,
                      compile_id: str) -> None:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        state = client.read_compile(project_id, compile_id)
        status = str(state.get("state", "")).lower()
        if status in {"buildsuccess", "success"}:
            return
        if status in {"builderror", "error"}:
            errors = state.get("logs") or state.get("errors") or []
            raise QuantConnectError(
                "compile failed: " + "; ".join(str(e) for e in errors)[:2000]
            )
        time.sleep(10)
    raise QuantConnectError("compile did not finish within 300s")


def launch(args: argparse.Namespace) -> int:
    out = _new_evidence_path(args.evidence)
    family_label, source_path = FAMILIES[args.family]
    commit = _git_commit_of(source_path)
    source = _retarget_universe(
        source_path.read_text(encoding="utf-8"), args.universe
    )
    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    date = args.date or _dt.date.today().strftime("%Y%m%d")
    name = _project_name(args.number, family_label, args.universe, date)

    client = QuantConnectClient()
    print(f"authenticating for {name!r}...", flush=True)
    client.authenticate()
    if args.project_id is not None:
        # Reuse a project whose earlier launch was refused at the backtest
        # step (for example a node-capacity refusal). The source is
        # re-uploaded and re-compiled so the recorded identity stays exact.
        project_id = int(args.project_id)
        project = _project_record(
            client.request("projects/read", {"projectId": project_id}), project_id
        )
        print(f"  reusing project {project_id}: {project['name']}", flush=True)
    else:
        created = client.create_project(name)
        project = _project_record(created)
        project_id = int(project["projectId"])
        print(f"  project {project_id}: {project['name']}", flush=True)

    client.update_file(project_id, ENTRY_FILE, source)
    compile_record = client.compile_project(project_id)
    compile_id = str(compile_record.get("compileId") or "")
    if not compile_id:
        raise QuantConnectError(f"compile/create returned no compileId: {compile_record}")
    _wait_for_compile(client, project_id, compile_id)
    print(f"  compile ok: {compile_id}", flush=True)

    backtest_name = name
    launched = client.create_backtest(project_id, compile_id, backtest_name)
    backtest = launched.get("backtest") or launched
    backtest_id = str(backtest.get("backtestId") or "")
    if not backtest_id:
        raise QuantConnectError(f"backtests/create returned no backtestId: {launched}")
    print(f"  backtest launched: {backtest_id}", flush=True)

    evidence = {
        "number": args.number,
        "family": args.family,
        "family_label": family_label,
        "universe": args.universe,
        "requested_project_name": name,
        "project_name": str(project["name"]),
        "project_id": project_id,
        "compile_id": compile_id,
        "backtest_id": backtest_id,
        "backtest_name": backtest_name,
        "source_file": str(source_path.relative_to(ROOT)),
        "source_commit": commit,
        "source_sha256": source_sha,
        "launched_at_utc": _utc_now(),
        "status": "launched",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"evidence written: {out}", flush=True)
    return 0


def _fetch_full_log(client: QuantConnectClient, project_id: int,
                    backtest_id: str) -> list[str]:
    """Page through backtests/read/log; start/end are line numbers."""
    lines: list[str] = []
    start = 0
    for _page in range(MAX_LOG_PAGES):
        response = client.request(
            "backtests/read/log",
            {
                "projectId": project_id,
                "backtestId": backtest_id,
                # The endpoint literally requires a parameter named `query`
                # (an empty filter returns every line); omitting it fails
                # with "Required parameter query is missing".
                "query": "",
                "start": start,
                "end": start + LOG_PAGE_LINES,
            },
        )
        chunk = response.get("logs") or response.get("log") or []
        if isinstance(chunk, str):
            chunk = chunk.splitlines()
        if not chunk:
            break
        lines.extend(str(line) for line in chunk)
        if len(chunk) < LOG_PAGE_LINES:
            break
        start += len(chunk)
    else:
        raise QuantConnectError(
            f"log for backtest {backtest_id} exceeded {MAX_LOG_PAGES} pages; "
            "refusing to record a possibly truncated artifact as complete"
        )
    return lines


def _write_log_artifact(path: Path, lines: list[str]) -> tuple[int, str]:
    """Write and hash the exact UTF-8 bytes; never hash pre-translation text."""
    if path.exists():
        raise QuantConnectError(f"log artifact already exists: {path}")
    text = "\n".join(lines) + ("\n" if lines else "")
    payload = text.encode("utf-8")
    path.write_bytes(payload)
    return len(lines), hashlib.sha256(path.read_bytes()).hexdigest()


def _watch_one(client: QuantConnectClient, evidence: dict) -> dict:
    project_id = int(evidence["project_id"])
    backtest_id = str(evidence["backtest_id"])
    started = time.monotonic()
    deadline = started + MAX_WAIT_SECONDS
    marker: object = object()
    marker_at = started
    while time.monotonic() < deadline:
        result = client.read_backtest(project_id, backtest_id)
        backtest = result.get("backtest") or result
        if backtest.get("error"):
            evidence["status"] = "error"
            evidence["error"] = str(backtest["error"])[:2000]
            return evidence
        if backtest.get("completed") is True:
            evidence["status"] = "completed"
            evidence["completed_at_utc"] = _utc_now()
            statistics = backtest.get("runtimeStatistics") or {}
            evidence["runtime_statistics"] = {
                key: str(value) for key, value in list(statistics.items())[:20]
            }
            return evidence
        progress = backtest.get("progress")
        state = (str(progress),
                 str(backtest.get("status") or backtest.get("state") or ""))
        now = time.monotonic()
        if state != marker:
            marker = state
            marker_at = now
        elif now - marker_at >= STALL_WAIT_SECONDS:
            raise QuantConnectError(
                f"backtest {backtest_id} reported no progress for "
                f"{STALL_WAIT_SECONDS:g}s (progress={progress!r}). The cloud "
                "run may still exist; inspect it before launching another look."
            )
        print(f"  [{evidence['project_name']}] progress={progress}", flush=True)
        time.sleep(POLL_SECONDS)
    raise QuantConnectError(
        f"backtest {backtest_id} did not finish within {MAX_WAIT_SECONDS:g}s. "
        "The cloud run may still exist; inspect it before launching another look."
    )


def wait(args: argparse.Namespace) -> int:
    paths = [Path(item) for item in args.evidence]
    if not 1 <= len(paths) <= 2:
        raise SystemExit("wait supervises one or two runs (the concurrency cap)")
    client = QuantConnectClient()
    client.authenticate()
    exit_code = 0
    for path in paths:
        evidence = json.loads(path.read_text(encoding="utf-8"))
        try:
            evidence = _watch_one(client, evidence)
        except QuantConnectError as exc:
            evidence["status"] = "unresolved"
            evidence["unresolved_reason"] = str(exc)
            path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(f"UNRESOLVED: {path}: {exc}", flush=True)
            exit_code = 2
            continue
        # Persist the completion verdict BEFORE fetching logs: a log-endpoint
        # failure must not lose the fact that the run finished (learned the
        # hard way when the missing `query` parameter erased run 1's status).
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        try:
            lines = _fetch_full_log(client, int(evidence["project_id"]),
                                    str(evidence["backtest_id"]))
        except QuantConnectError as exc:
            evidence["log_fetch_error"] = str(exc)
            path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(f"LOG FETCH FAILED: {path}: {exc}", flush=True)
            exit_code = 2
            continue
        log_path = path.with_suffix(".log")
        log_line_count, log_sha256 = _write_log_artifact(log_path, lines)
        evidence["log_path"] = str(log_path)
        evidence["log_line_count"] = log_line_count
        evidence["log_sha256"] = log_sha256
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(
            f"DONE: {evidence['project_name']} status={evidence['status']} "
            f"lines={log_line_count} log={log_path}",
            flush=True,
        )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    launch_parser = sub.add_parser("launch", help="create+upload+compile+start one run")
    launch_parser.add_argument("--family", choices=sorted(FAMILIES), required=True)
    launch_parser.add_argument("--universe", choices=UNIVERSES, required=True)
    launch_parser.add_argument("--number", type=int, required=True,
                               help="sequential project number for the naming rule")
    launch_parser.add_argument("--date", default=None, help="YYYYMMDD; default today")
    launch_parser.add_argument("--project-id", type=int, default=None,
                               help="reuse an existing project after a refused launch")
    launch_parser.add_argument("--evidence", required=True,
                               help="path for the run's JSON evidence file")
    launch_parser.set_defaults(handler=launch)

    wait_parser = sub.add_parser("wait", help="supervise 1-2 launched runs to completion")
    wait_parser.add_argument("--evidence", action="append", required=True,
                             help="evidence JSON from launch; repeat once at most")
    wait_parser.set_defaults(handler=wait)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
