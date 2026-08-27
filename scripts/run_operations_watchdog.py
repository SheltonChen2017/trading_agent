"""Long-running operational watchdog intended for an external supervisor."""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.operations import append_alerts_jsonl, run_operational_check
from assistant.policy import load_policy, resolve_policy_path
from assistant.process_singleton import (
    ProcessSingletonError,
    acquire_process_singleton,
)
from assistant.storage import AssistantStore


def _positive_seconds(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("interval must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist health checks and durable operational alerts."
    )
    parser.add_argument(
        "--database",
        type=Path,
        help=(
            "SQLite database path. Defaults to TRADING_ASSISTANT_DB or "
            "data/trading_assistant.db."
        ),
    )
    parser.add_argument("--interval-seconds", type=_positive_seconds, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--alerts-jsonl", type=Path)
    parser.add_argument(
        "--policy",
        default=None,
        help=(
            "Policy file governing health checks. When omitted, resolves via "
            "TRADING_ASSISTANT_POLICY, then assistant/my_policy.json when "
            "present, otherwise assistant/default_policy.json."
        ),
    )
    return parser


def _resolve_runtime_policy(explicit: str | Path | None):
    """Resolve and load one canonical policy, failing before any DB access."""
    try:
        policy_path = resolve_policy_path(explicit).resolve(strict=True)
        policy = load_policy(policy_path)
    except (OSError, ValueError, TypeError) as exc:
        raise SystemExit(f"Policy resolution failed: {exc}") from exc
    return policy_path, policy


def main() -> None:
    args = build_parser().parse_args()
    policy_path, policy = _resolve_runtime_policy(args.policy)
    # Same orphan/self-heal race as monitor-orders: Task Scheduler
    # IgnoreNew is not enough when a previous process is still alive.
    try:
        acquire_process_singleton(args.database, "operations-watchdog")
    except ProcessSingletonError as exc:
        raise SystemExit(f"Operations watchdog already running: {exc}") from exc
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    store = AssistantStore(args.database)
    while not stop.is_set():
        report = run_operational_check(
            store,
            policy,
            check_broker=not args.offline,
            policy_path=policy_path,
            heartbeat_task="watchdog",
        )
        print(json.dumps(report["heartbeat"], sort_keys=True), flush=True)
        if args.alerts_jsonl and report["alerts"]:
            append_alerts_jsonl(report["alerts"], args.alerts_jsonl)
        if args.once:
            break
        stop.wait(args.interval_seconds)


if __name__ == "__main__":
    main()
