"""
Append-only journal of generated decision packets — the foundation for
the "trading journal / research memory" feature (Phase 3 of the
assistant roadmap; see memory: project design discussion, 2026-07).

Phase 1 scope: just persist every DecisionPacket generated, one per
line, so there's a real historical record from day one. Comparing
"what did we say then vs. what actually happened" and similarity search
over past packets are future features built ON TOP of this log, not
implemented yet.
"""
from __future__ import annotations

import json
from pathlib import Path

from assistant.schemas import DecisionPacket

DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "decision_log.jsonl"


def append_decision_packet(packet: DecisionPacket, log_path: Path = DEFAULT_LOG_PATH) -> None:
    """Appends one JSON line. Never overwrites — this is a journal."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(packet.to_dict()) + "\n")


def read_decision_log(log_path: Path = DEFAULT_LOG_PATH) -> list[dict]:
    """Reads every logged packet back as plain dicts, oldest first.
    Returns an empty list if the log doesn't exist yet."""
    if not log_path.exists():
        return []
    with open(log_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
