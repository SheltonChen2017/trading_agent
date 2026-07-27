"""Versioned, file-backed registry of the project's research claims."""
from __future__ import annotations

import json
from pathlib import Path

from assistant.schemas import EvidenceStatus, SignalEvidence

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "research_findings.json"


def load_research_findings(path: str | Path = DEFAULT_REGISTRY_PATH) -> list[SignalEvidence]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    findings = []
    for item in raw["findings"]:
        findings.append(
            SignalEvidence(
                label=item["label"],
                claim=item["claim"],
                status=EvidenceStatus(item["status"]),
                detail=item["detail"],
                source=item["source"],
                relevant_tickers=item.get("relevant_tickers", []),
            )
        )
    return findings


def registry_version(path: str | Path = DEFAULT_REGISTRY_PATH) -> str:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return str(raw["version"])
