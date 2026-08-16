"""Upload and run the LEAN universe smoke test on QuantConnect Cloud.

Method V2 step 4. This drives a run that is INCAPABLE of reporting an
alpha statistic (`research/lean/universe_smoke.py` places no orders and
computes no signal), so it is exempt from the research look count. The
exemption is a property of the algorithm, not of this script, and
`tests/test_lean_smoke_test.py` is what enforces it.

What the run is asked to demonstrate, none of which may be assumed from
the platform's reputation:

  1. universe membership changes over time (dynamic, not a symbol list)
  2. delisting events actually fire  <- the whole reason for using cloud
     data, since the local dataset could not price a delisted company at all
  3. point-in-time market cap and industry codes are populated

Nothing here retrieves raw market data. QuantConnect's licence forbids
exporting it, and the client's allowlist makes those endpoints
unreachable regardless of what this script asks for.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.quantconnect import (  # noqa: E402
    QuantConnectClient,
    QuantConnectError,
)

ALGORITHM = Path(__file__).resolve().parents[1] / "research" / "lean" / "universe_smoke.py"
#: QuantConnect projects are created with a main.py; the algorithm must
#: land there or the compiler runs the template instead of our code.
ENTRY_FILE = "main.py"
POLL_SECONDS = 10
MAX_WAIT_SECONDS = 1800


def _wait_for_compile(client: QuantConnectClient, project_id: int, compile_id: str) -> dict:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        state = client.read_compile(project_id, compile_id)
        status = str(state.get("state", "")).lower()
        if status in {"buildsuccess", "success"}:
            return state
        if status in {"builderror", "error"}:
            errors = state.get("logs") or state.get("errors") or []
            raise QuantConnectError(
                "compile failed: " + "; ".join(str(e) for e in errors)[:2000]
            )
        time.sleep(POLL_SECONDS)
    raise QuantConnectError("compile did not finish within 300s")


def _wait_for_backtest(client: QuantConnectClient, project_id: int, backtest_id: str) -> dict:
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        result = client.read_backtest(project_id, backtest_id)
        backtest = result.get("backtest") or result
        if backtest.get("completed") is True:
            return backtest
        if backtest.get("error"):
            raise QuantConnectError(f"backtest error: {backtest['error']}")
        progress = backtest.get("progress")
        print(f"  ... running, progress={progress}", flush=True)
        time.sleep(POLL_SECONDS)
    raise QuantConnectError(f"backtest did not finish within {MAX_WAIT_SECONDS}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default="trading-agent-universe-smoke")
    parser.add_argument("--backtest-name", default="universe-smoke-1")
    parser.add_argument("--project-id", type=int, default=None,
                        help="reuse an existing project instead of creating one")
    parser.add_argument("--output", default=None)
    parser.add_argument("--start", default=None,
                        help="YYYY-MM-DD; overrides the algorithm's declared START")
    parser.add_argument("--end", default=None,
                        help="YYYY-MM-DD; overrides the algorithm's declared END")
    args = parser.parse_args(argv)

    source = ALGORITHM.read_text(encoding="utf-8")
    if args.start or args.end:
        # Rewrite the DECLARED constants only. The earlier version patched
        # SetStartDate/SetEndDate calls directly, which left the committed
        # file disagreeing with the run it produced.
        source = _retarget_window(source, args.start, args.end)
    client = QuantConnectClient()

    print("authenticating...", flush=True)
    client.authenticate()

    if args.project_id is None:
        print(f"creating project {args.project_name!r}...", flush=True)
        created = client.create_project(args.project_name)
        projects = created.get("projects") or []
        if not projects:
            raise QuantConnectError(f"projects/create returned no project: {created}")
        project_id = int(projects[0]["projectId"])
    else:
        project_id = args.project_id
    print(f"  project id {project_id}", flush=True)

    print(f"uploading {ENTRY_FILE}...", flush=True)
    try:
        client.update_file(project_id, ENTRY_FILE, source)
    except QuantConnectError:
        # A fresh project may not have the file yet; create then.
        client.create_file(project_id, ENTRY_FILE, source)

    print("compiling...", flush=True)
    compile_record = client.compile_project(project_id)
    compile_id = str(compile_record.get("compileId") or "")
    if not compile_id:
        raise QuantConnectError(f"compile/create returned no compileId: {compile_record}")
    _wait_for_compile(client, project_id, compile_id)
    print("  compile ok", flush=True)

    print("launching backtest...", flush=True)
    launched = client.create_backtest(project_id, compile_id, args.backtest_name)
    backtest = (launched.get("backtest") or launched)
    backtest_id = str(backtest.get("backtestId") or "")
    if not backtest_id:
        raise QuantConnectError(f"backtests/create returned no backtestId: {launched}")
    print(f"  backtest id {backtest_id}", flush=True)

    finished = _wait_for_backtest(client, project_id, backtest_id)

    summary = {
        "project_id": project_id,
        "backtest_id": backtest_id,
        "completed": finished.get("completed"),
        # Deliberately NOT the performance statistics. This run has no
        # signal, so quoting its Sharpe would invite a reading the
        # algorithm cannot support.
        "orders": finished.get("totalOrders") or finished.get("orders"),
        "log_excerpt": _smoke_lines(finished),
    }
    text = json.dumps(summary, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print("\n=== SMOKE TEST SUMMARY (no alpha statistic) ===")
    print(text)
    return 0


def _retarget_window(source: str, start: str | None, end: str | None) -> str:
    """Replace the algorithm's declared START/END tuples.

    Refuses rather than silently running the wrong window: if the constant
    is not found, the algorithm is not the one this driver understands.
    """
    import re

    for name, value in (("START", start), ("END", end)):
        if not value:
            continue
        year, month, day = (int(part) for part in value.split("-"))
        pattern = rf"^{name} = \(\d+, \d+, \d+\)$"
        replacement = f"{name} = ({year}, {month}, {day})"
        source, count = re.subn(pattern, replacement, source, count=1, flags=re.M)
        if count != 1:
            raise SystemExit(
                f"could not find a `{name} = (y, m, d)` constant to retarget; "
                "refusing to run an algorithm whose window is unknown"
            )
    return source


def _smoke_lines(backtest: dict) -> list[str]:
    """Only the algorithm's own diagnostic lines."""
    raw = backtest.get("logs") or backtest.get("Logs") or []
    if isinstance(raw, str):
        raw = raw.splitlines()
    keep = ("[universe]", "[delisting]", "UNIVERSE SMOKE TEST",
            "universe screen", "coarse selections", "fine selections",
            "members min", "DELISTINGS OBSERVED", "rows missing",
            "orders placed")
    return [line for line in raw if any(k in str(line) for k in keep)]


if __name__ == "__main__":
    raise SystemExit(main())
