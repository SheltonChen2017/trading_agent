"""The ADR's frozen committee replay/adversarial corpus and its harness.

docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md makes ">= 50 frozen replay cases
plus injection and memory-poisoning adversarial cases" a release gate for
daily model-backed committee use. This file is that gate's enforcement:

  - `tests/committee_corpus/cases.json` holds the frozen cases -- each one
    a deterministic (input, scripted provider output) -> expected outcome
    record. No case ever contacts a real provider.
  - The inventory tests pin the ADR's minimum counts and case uniqueness;
    deleting or renaming a case is loud.
  - Every case is executed through the REAL pipeline
    (project_committee_input -> run_committee_review with a scripted
    provider), so the corpus characterizes the actual deterministic
    validator, schema, and error-mapping behavior -- not a parallel
    reimplementation.

The corpus records measured deterministic behavior. A tiny number of cases
deliberately freeze DOCUMENTED LIMITATIONS (e.g. the lexical action filter
missing a homoglyph-obfuscated directive); their descriptions say so
explicitly, and passing them is a measurement, not an endorsement -- the
architectural boundary (read-only committee, mandatory human approval and
revalidation) remains the actual containment per the ADR.

Completing this corpus does NOT remove the ENABLE_EXPERIMENTAL_COMMITTEE
gate; that removal is a separately owner-authorized decision.

Run with: python -m pytest tests/test_committee_replay_corpus.py
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assistant.llm.committee import run_committee_review
from assistant.llm.projection import ProjectionError, project_committee_input
from assistant.schemas import EvidenceStatus, SignalEvidence, UpcomingEvent
from test_committee_foundation import (  # noqa: E402
    _FakeProvider,
    _packet,
    _proposal,
    _valid_raw_review,
)

_CORPUS_PATH = Path(__file__).resolve().parent / "committee_corpus" / "cases.json"

# The ADR's minimum inventory. Raising these numbers is always safe;
# lowering one is a reviewed weakening of the release gate.
MINIMUM_REPLAY_CASES = 50
MINIMUM_INJECTION_CASES = 5
MINIMUM_MEMORY_POISONING_CASES = 5
FROZEN_CORPUS_SHA256 = (
    "e9b569a90f267a3e0ae20d31125da9a4680f9352c3b07f733d33171d6e1577f4"
)


def _load_cases() -> list[dict]:
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


_CASES = _load_cases()


# --- inventory gates --------------------------------------------------------


def test_corpus_meets_the_adr_minimum_counts():
    by_category: dict[str, int] = {}
    for case in _CASES:
        by_category[case["category"]] = by_category.get(case["category"], 0) + 1
    assert by_category.get("replay", 0) >= MINIMUM_REPLAY_CASES, by_category
    assert by_category.get("injection", 0) >= MINIMUM_INJECTION_CASES, by_category
    assert (
        by_category.get("memory_poisoning", 0) >= MINIMUM_MEMORY_POISONING_CASES
    ), by_category


def test_case_ids_are_unique_and_shaped():
    ids = [case["case_id"] for case in _CASES]
    assert len(ids) == len(set(ids))
    for case in _CASES:
        assert case["category"] in ("replay", "injection", "memory_poisoning")
        assert case["description"].strip()
        assert "expected" in case


def test_frozen_corpus_content_identity():
    """Counts alone permit a release-gate case to be gutted while retaining
    its category and ID. Freeze the canonical content so any semantic corpus
    change requires an explicit reviewed fingerprint update."""
    canonical = json.dumps(
        _CASES,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == FROZEN_CORPUS_SHA256


# --- the harness ------------------------------------------------------------


def _build_packet(case: dict):
    options = case.get("packet", {})
    signals = []
    if "signal" in options:
        spec = options["signal"]
        signals.append(
            SignalEvidence(
                label=spec["label"],
                claim=spec["claim"],
                status=EvidenceStatus(spec["status"]),
                detail=spec["detail"],
                source="research_findings.json",
                relevant_tickers=list(spec.get("relevant_tickers", ["NVDA"])),
            )
        )
    packet = _packet(warnings=options.get("warnings", ()), signals=signals)
    if options.get("event_unavailable"):
        packet = dataclasses.replace(
            packet,
            upcoming_events=[
                UpcomingEvent(
                    ticker="NVDA",
                    event_type="earnings",
                    days_away=None,
                    status=EvidenceStatus.UNAVAILABLE,
                )
            ],
        )
    return packet


def _build_proposal(case: dict) -> dict:
    options = case.get("proposal", {})
    return _proposal(
        side=options.get("side", "sell"),
        before=options.get("before", 50.0),
        after=options.get("after", 25.0),
    )


def _resolve_placeholders(value, committee_input):
    """$WARNING_ID / $RESEARCH_ID / $EVENT_ID -> the projected fact ids.

    Fact ids for warnings/research/events are derived by projection, so the
    frozen corpus names them symbolically and the harness resolves them
    against the exact input the case built."""
    if isinstance(value, str):
        replacements = {}
        for token, category in (
            ("$WARNING_ID", "warning"),
            ("$RESEARCH_ID", "research"),
            ("$EVENT_ID", "event"),
        ):
            if token in value:
                replacements[token] = next(
                    fact.source_id
                    for fact in committee_input.facts
                    if fact.category == category
                )
        for token, resolved in replacements.items():
            value = value.replace(token, resolved)
        return value
    if isinstance(value, list):
        return [_resolve_placeholders(item, committee_input) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_placeholders(item, committee_input)
            for key, item in value.items()
        }
    return value


def _apply_path(target, path: str, value):
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        cursor = cursor[int(part)] if part.isdigit() else cursor[part]
    last = parts[-1]
    if last.isdigit():
        cursor[int(last)] = value
    else:
        cursor[last] = value


def _delete_path(target, path: str):
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        cursor = cursor[int(part)] if part.isdigit() else cursor[part]
    last = parts[-1]
    if last.isdigit():
        del cursor[int(last)]
    else:
        del cursor[last]


def _build_raw_review(case: dict, committee_input):
    review_spec = case.get("review", {})
    if "raw" in review_spec:
        return _resolve_placeholders(review_spec["raw"], committee_input)
    raw = copy.deepcopy(_valid_raw_review())
    for path, value in review_spec.get("set", {}).items():
        _apply_path(raw, path, _resolve_placeholders(value, committee_input))
    for path in review_spec.get("delete", []):
        _delete_path(raw, path)
    return raw


def _build_provider(case: dict, raw):
    error_kind = case.get("provider_error")
    if error_kind == "timeout":
        return _FakeProvider(error=TimeoutError("provider timed out"))
    if error_kind == "runtime":
        return _FakeProvider(error=RuntimeError("provider crashed"))
    return _FakeProvider(raw)


@pytest.mark.parametrize(
    "case", _CASES, ids=[case["case_id"] for case in _CASES]
)
def test_corpus_case(case):
    expected = case["expected"]
    packet = _build_packet(case)
    proposal = _build_proposal(case)

    if "projection_error_match" in expected:
        with pytest.raises(ProjectionError, match=expected["projection_error_match"]):
            project_committee_input(packet, proposal)
        return

    committee_input = project_committee_input(packet, proposal)
    raw = _build_raw_review(case, committee_input)
    provider = _build_provider(case, raw)
    kwargs = {}
    if "timeout_seconds" in case:
        timeout = case["timeout_seconds"]
        kwargs["timeout_seconds"] = float("nan") if timeout == "nan" else timeout

    result = run_committee_review(committee_input, provider, **kwargs)

    assert result.status.value == expected["status"], (
        result.error_code,
        result.issues,
    )
    if expected["status"] == "accepted":
        assert result.accepted and result.review is not None
        assert result.error_code is None
    else:
        assert not result.accepted and result.review is None
        if expected.get("error_code") is not None:
            assert result.error_code == expected["error_code"], result.error_code
    issue_codes = {issue.code for issue in result.issues}
    for code in expected.get("issue_codes", []):
        assert code in issue_codes, (case["case_id"], issue_codes)
    for code in expected.get("not_issue_codes", []):
        assert code not in issue_codes, (case["case_id"], issue_codes)
