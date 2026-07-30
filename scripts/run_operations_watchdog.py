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
from assistant.policy import load_policy
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
    parser.add_argument("--interval-seconds", type=_positive_seconds, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--alerts-jsonl", type=Path)
    parser.add_argument(
        "--policy",
        default=str(
            Path(__file__).resolve().parent.parent
            / "assistant"
            / "default_policy.json"
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    store = AssistantStore()
    policy = load_policy(args.policy)
    while not stop.is_set():
        report = run_operational_check(
            store, policy, check_broker=not args.offline
        )
        print(json.dumps(report["heartbeat"], sort_keys=True), flush=True)
        if args.alerts_jsonl and report["alerts"]:
            append_alerts_jsonl(report["alerts"], args.alerts_jsonl)
        if args.once:
            break
        stop.wait(args.interval_seconds)


if __name__ == "__main__":
    main()
