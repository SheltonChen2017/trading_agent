"""Versioned, file-backed registry of the project's research claims."""
from __future__ import annotations

import json
from pathlib import Path

from assistant.schemas import EvidenceStatus, FindingProvenance, SignalEvidence

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "research_findings.json"

# Statuses whose findings are strong enough that a reader might treat them
# as production-actionable -- these require provenance so that trust can't
# rest on an unlabeled, unreproducible claim (GPT review finding #8).
_STATUSES_REQUIRING_PROVENANCE = {EvidenceStatus.CONFIRMED, EvidenceStatus.PROMISING_UNCONFIRMED}

# The minimum provenance fields a confirmed/promising finding must carry.
# Deliberately a small, checkable subset (not every FindingProvenance
# field) -- these are the ones needed to judge dataset adequacy and
# know whether the result predates the fetch_historical lookback-days
# fix, not a demand that every historical run be fully re-documented.
REQUIRED_PROVENANCE_FIELDS = (
    "actual_start_date",
    "actual_end_date",
    "actual_row_count",
    "entry_timing",
    "data_fetched_at",
)


def _parse_provenance(item: dict) -> FindingProvenance | None:
    raw = item.get("provenance")
    if raw is None:
        return None
    return FindingProvenance(**raw)


def load_research_findings(path: str | Path = DEFAULT_REGISTRY_PATH) -> list[SignalEvidence]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    findings = []
    for item in raw["findings"]:
        status = EvidenceStatus(item["status"])
        provenance = _parse_provenance(item)

        if status in _STATUSES_REQUIRING_PROVENANCE:
            if provenance is None:
                raise ValueError(
                    f"Finding {item['label']!r} has status {status.value!r} but no provenance -- "
                    f"a confirmed/promising claim must record {REQUIRED_PROVENANCE_FIELDS} "
                    f"(GPT review finding #8: unreproducible confirmed findings can't be trusted)."
                )
            missing = [f for f in REQUIRED_PROVENANCE_FIELDS if getattr(provenance, f) is None]
            if missing:
                raise ValueError(
                    f"Finding {item['label']!r} has status {status.value!r} but its provenance is "
                    f"missing required field(s) {missing} -- see REQUIRED_PROVENANCE_FIELDS."
                )

        findings.append(
            SignalEvidence(
                label=item["label"],
                claim=item["claim"],
                status=status,
                detail=item["detail"],
                source=item["source"],
                relevant_tickers=item.get("relevant_tickers", []),
                provenance=provenance,
            )
        )
    return findings


def registry_version(path: str | Path = DEFAULT_REGISTRY_PATH) -> str:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return str(raw["version"])


def is_production_authoritative(finding: SignalEvidence) -> bool:
    """Whether this finding's status can be trusted as CURRENT production
    evidence, as opposed to a label carried over from a prior (possibly
    superseded) data-loader methodology. A confirmed/promising finding
    that has never been re-verified since the fetch_historical
    lookback-days fix (commit 9f0ebc1) is NOT production-authoritative,
    regardless of its status string -- callers deciding whether to act
    on a finding must check this, not just `status`.

    Kept here for backward compatibility (existing callers/tests import
    this function directly) -- delegates to SignalEvidence.
    production_authoritative, which is now the single source of truth
    for this logic and the form every runtime display consumer (CLI
    briefing, Streamlit UI) actually reads (GPT review, 2026-07-29: this
    function existed but was previously referenced only by this module's
    own tests, never by a runtime consumer)."""
    return finding.production_authoritative


def underfilled_dataset_warning(provenance: FindingProvenance) -> str | None:
    """Returns a human-readable warning if the dataset actually used was
    materially shorter than what was requested (e.g. a recent-IPO ticker
    diluting a basket result with far less real history than intended),
    or None if coverage looks adequate or isn't checkable."""
    requested = provenance.requested_lookback_sessions
    actual = provenance.actual_lookback_sessions
    if requested is None or actual is None:
        return None
    if actual < requested:
        pct = actual / requested * 100 if requested else 0.0
        return (
            f"Requested {requested} lookback sessions but only {actual} were actually available "
            f"({pct:.0f}% of requested) -- treat this result as based on a shorter, less "
            f"statistically meaningful window than the nominal lookback suggests."
        )
    return None
