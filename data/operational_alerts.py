"""Assistant-owned serialization for immutable operational alert envelopes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_alerts_jsonl(
    alerts: list[dict[str, Any]], destination: str | Path
) -> Path:
    """Append alert envelopes for a local log shipper or paging sidecar."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for alert in alerts:
            handle.write(json.dumps(alert, sort_keys=True, default=str) + "\n")
        handle.flush()
    return target


__all__ = ["append_alerts_jsonl"]
