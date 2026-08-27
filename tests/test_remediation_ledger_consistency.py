"""Fail-closed structural checks for the 2026-08-26 remediation ledger.

The ledger is a review control, not merely prose.  A finding can disappear if
only its summary row or only its detailed disposition is retained, and split
severity columns can hide a stale grand total.  These checks therefore pin the
stable finding namespace and independently reconcile the map, detail, status,
and aggregate-summary views.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LEDGER = (
    ROOT
    / "docs"
    / "Archive"
    / "Review"
    / "REMEDIATION_2026-08-26_ANALYST_AND_FULL_PROJECT.md"
)

IMPLEMENTED_PENDING_REVIEW = (
    "**Implementation status:** Implemented — pending required independent "
    "review/counter-review."
)

_ID_TOKEN = r"(?:AR|SYS)-(?:FU-|FINAL-)?P[0-3]-\d{3}"
_COVERAGE_HEADING = re.compile(
    r"^##\s+(?:\d+\.\s+)?[^\r\n]*coverage map[^\r\n]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_COVERAGE_ROW = re.compile(
    rf"^\|\s*(?P<id>{_ID_TOKEN})\s*\|\s*(?P<priority>P[0-3])\s*\|",
    flags=re.MULTILINE,
)
_BROAD_DETAIL_HEADING = re.compile(
    rf"^###\s+(?P<id>{_ID_TOKEN})(?P<suffix>[^\r\n]*)$",
    flags=re.MULTILINE,
)
_EXACT_DETAIL_HEADING = re.compile(
    rf"^### (?P<id>{_ID_TOKEN}) — \S[^\r\n]*$",
    flags=re.MULTILINE,
)


def _numbered(prefix: str, count: int) -> set[str]:
    return {f"{prefix}-{number:03d}" for number in range(1, count + 1)}


# These are the immutable finding families in the original audit, its first
# remediation follow-up, and the final adversarial pass.  Ranges are expanded
# here rather than discovered from the document: deriving the expected set
# from the artifact under test would let deletion weaken the guard.
EXPECTED_IDS = frozenset(
    _numbered("AR-P2", 17)
    | _numbered("AR-P3", 7)
    | _numbered("AR-FU-P1", 14)
    | _numbered("AR-FU-P2", 11)
    | _numbered("AR-FU-P3", 2)
    | _numbered("SYS-P1", 6)
    | _numbered("SYS-P2", 13)
    | _numbered("SYS-P3", 3)
    | _numbered("SYS-FU-P1", 5)
    | _numbered("SYS-FU-P2", 4)
    | _numbered("SYS-FU-P3", 2)
    | _numbered("AR-FINAL-P1", 2)
    | _numbered("SYS-FINAL-P1", 19)
    | _numbered("SYS-FINAL-P2", 4)
)
EXPECTED_PRIORITY_TOTALS = {"P0": 0, "P1": 46, "P2": 49, "P3": 14}
EXPECTED_GRAND_TOTAL = 109


def _read_ledger() -> str:
    assert LEDGER.is_file(), f"required remediation ledger is missing: {LEDGER}"
    return LEDGER.read_text(encoding="utf-8")


def _section_end(text: str, content_start: int, *, maximum_level: int) -> int:
    """Return the next Markdown heading at or above ``maximum_level``."""
    following = re.search(
        rf"^#{{1,{maximum_level}}}\s+",
        text[content_start:],
        flags=re.MULTILINE,
    )
    return len(text) if following is None else content_start + following.start()


def _coverage_rows(text: str, errors: list[str]) -> list[tuple[str, str]]:
    headings = list(_COVERAGE_HEADING.finditer(text))
    if not headings:
        errors.append("no `## ... coverage map` section was found")
        return []

    rows: list[tuple[str, str]] = []
    for heading in headings:
        end = _section_end(text, heading.end(), maximum_level=2)
        rows.extend(
            (match.group("id"), match.group("priority"))
            for match in _COVERAGE_ROW.finditer(text, heading.end(), end)
        )
    return rows


def _detail_sections(
    text: str, errors: list[str]
) -> list[tuple[str, str]]:
    broad = list(_BROAD_DETAIL_HEADING.finditer(text))
    exact = list(_EXACT_DETAIL_HEADING.finditer(text))
    broad_locations = {(match.start(), match.group("id")) for match in broad}
    exact_locations = {(match.start(), match.group("id")) for match in exact}
    malformed = sorted(broad_locations - exact_locations)
    if malformed:
        errors.append(
            "finding headings must use exact `### ID — title` syntax; malformed "
            f"headings: {malformed}"
        )

    sections: list[tuple[str, str]] = []
    for match in exact:
        end = _section_end(text, match.end(), maximum_level=3)
        sections.append((match.group("id"), text[match.end():end]))
    return sections


def _format_id_delta(label: str, counts: Counter[str]) -> list[str]:
    errors: list[str] = []
    observed = set(counts)
    missing = sorted(EXPECTED_IDS - observed)
    unexpected = sorted(observed - EXPECTED_IDS)
    duplicates = sorted(
        finding_id for finding_id, count in counts.items() if count != 1
    )
    if missing:
        errors.append(f"{label} missing IDs: {missing}")
    if unexpected:
        errors.append(f"{label} has unexpected IDs: {unexpected}")
    if duplicates:
        errors.append(
            f"{label} IDs do not occur exactly once: "
            f"{[(finding_id, counts[finding_id]) for finding_id in duplicates]}"
        )
    return errors


def _coverage_summary(text: str, errors: list[str]) -> str:
    match = re.search(
        r"^##\s+(?:\d+\.\s+)?Coverage summary\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if match is None:
        errors.append("the ledger has no `Coverage summary` section")
        return ""
    end = _section_end(text, match.end(), maximum_level=2)
    return text[match.end():end]


def _ledger_errors(text: str) -> list[str]:
    errors: list[str] = []

    if len(EXPECTED_IDS) != EXPECTED_GRAND_TOTAL:
        errors.append(
            "test invariant is broken: expected ID namespace contains "
            f"{len(EXPECTED_IDS)} entries, not {EXPECTED_GRAND_TOTAL}"
        )

    rows = _coverage_rows(text, errors)
    row_counts = Counter(finding_id for finding_id, _ in rows)
    errors.extend(_format_id_delta("coverage maps", row_counts))

    row_priorities = Counter(priority for _, priority in rows)
    if dict(sorted(row_priorities.items())) != {
        priority: count
        for priority, count in EXPECTED_PRIORITY_TOTALS.items()
        if count
    }:
        errors.append(
            "coverage-map priority totals are incoherent: "
            f"observed {dict(sorted(row_priorities.items()))}, expected "
            f"{EXPECTED_PRIORITY_TOTALS}"
        )
    if len(rows) != EXPECTED_GRAND_TOTAL:
        errors.append(
            f"coverage maps contain {len(rows)} rows, expected "
            f"{EXPECTED_GRAND_TOTAL}"
        )

    for finding_id, stated_priority in rows:
        encoded_priority = re.search(r"-(P[0-3])-", finding_id)
        if encoded_priority is None or encoded_priority.group(1) != stated_priority:
            errors.append(
                f"coverage row {finding_id} states {stated_priority}, which "
                "disagrees with its stable ID"
            )

    detail_sections = _detail_sections(text, errors)
    detail_counts = Counter(finding_id for finding_id, _ in detail_sections)
    errors.extend(_format_id_delta("detailed headings", detail_counts))
    for finding_id, section in detail_sections:
        status_lines = [
            line.strip()
            for line in section.splitlines()
            if line.strip().startswith("**Implementation status:**")
        ]
        if status_lines != [IMPLEMENTED_PENDING_REVIEW]:
            errors.append(
                f"{finding_id} has noncanonical or non-unique implementation "
                f"status: {status_lines!r}"
            )

    summary = _coverage_summary(text, errors)
    # Formatting marks are irrelevant, but the aggregate declarations must be
    # explicit.  Split original/follow-up/final columns alone are insufficient
    # because a reader should not have to rediscover the severity totals.
    summary_plain = summary.replace("*", "").replace("`", "")
    priority_declarations = re.findall(
        r"\b(P[0-3])\s*=\s*(\d+)\b", summary_plain, flags=re.IGNORECASE
    )
    declaration_counts = Counter(priority.upper() for priority, _ in priority_declarations)
    declared_totals = {
        priority.upper(): int(value)
        for priority, value in priority_declarations
    }
    if declaration_counts != Counter({priority: 1 for priority in EXPECTED_PRIORITY_TOTALS}):
        errors.append(
            "coverage summary must declare each aggregate exactly once as "
            "P1=46, P2=49, P3=14, P0=0; observed "
            f"{priority_declarations}"
        )
    elif declared_totals != EXPECTED_PRIORITY_TOTALS:
        errors.append(
            f"coverage summary declares {declared_totals}, expected "
            f"{EXPECTED_PRIORITY_TOTALS}"
        )

    grand_declarations = re.findall(
        r"\btotal\s*=\s*(\d+)\b", summary_plain, flags=re.IGNORECASE
    )
    if grand_declarations != [str(EXPECTED_GRAND_TOTAL)]:
        errors.append(
            "coverage summary must declare `total=109` exactly once; observed "
            f"{grand_declarations}"
        )
    if sum(EXPECTED_PRIORITY_TOTALS.values()) != EXPECTED_GRAND_TOTAL:
        errors.append("test severity totals do not sum to the expected grand total")

    stale_claims = re.findall(
        r"\ball\s+84\s+IDs\b|\b84\s+findings\b",
        text,
        flags=re.IGNORECASE,
    )
    if stale_claims:
        errors.append(f"stale 84-finding completion claims remain: {stale_claims}")

    return errors


def _assert_ledger_consistent(text: str) -> None:
    errors = _ledger_errors(text)
    assert not errors, "remediation ledger consistency failures:\n- " + "\n- ".join(errors)


def test_remediation_ledger_is_complete_and_internally_coherent() -> None:
    _assert_ledger_consistent(_read_ledger())


def _duplicate_coverage_row(text: str) -> str:
    row = next(
        line for line in text.splitlines() if line.startswith("| AR-P2-001 |")
    )
    return text.replace(row, f"{row}\n{row}", 1)


def _remove_detail_status(text: str) -> str:
    heading = text.index("### AR-P2-001 —")
    status = text.index(IMPLEMENTED_PENDING_REVIEW, heading)
    return (
        text[:status]
        + "**Implementation status:** Implemented."
        + text[status + len(IMPLEMENTED_PENDING_REVIEW):]
    )


def _restore_stale_total_claim(text: str) -> str:
    return text + "\n\nAll 84 IDs receive an explicit disposition.\n"


@pytest.mark.parametrize(
    "mutator",
    (_duplicate_coverage_row, _remove_detail_status, _restore_stale_total_claim),
    ids=("duplicate-map-row", "weaken-detail-status", "restore-stale-total"),
)
def test_consistency_guard_rejects_structural_mutations(
    mutator: Callable[[str], str],
) -> None:
    text = _read_ledger()
    _assert_ledger_consistent(text)
    with pytest.raises(AssertionError):
        _assert_ledger_consistent(mutator(text))
