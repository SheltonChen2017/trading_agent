"""
Tests for assistant/research_registry.py's provenance enforcement (GPT
review finding #8, 2026-07-29). Run with: python -m pytest tests/ -v
(or `python tests/test_research_registry.py` for a quick manual check).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.research_registry import (
    DEFAULT_REGISTRY_PATH,
    REQUIRED_PROVENANCE_FIELDS,
    is_production_authoritative,
    load_research_findings,
    underfilled_dataset_warning,
)
from assistant.schemas import EvidenceStatus, FindingProvenance, SignalEvidence


def _write_registry(tmp_dir: Path, findings: list[dict]) -> Path:
    path = tmp_dir / "findings.json"
    path.write_text(json.dumps({"version": "test", "updated_at": "2026-07-29", "findings": findings}), encoding="utf-8")
    return path


_VALID_PROVENANCE = {
    "actual_start_date": "2019-07-22",
    "actual_end_date": "2026-07-28",
    "actual_row_count": 1764,
    "requested_lookback_sessions": 1764,
    "actual_lookback_sessions": 1764,
    "entry_timing": "next_open",
    "data_fetched_at": "2026-07-28T14:53:45+00:00",
    "reproduced_after_data_loader_fix": False,
}


def test_confirmed_finding_without_provenance_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_registry(Path(tmp), [
            {
                "label": "Test finding",
                "claim": "Beats a baseline",
                "status": "confirmed",
                "detail": "...",
                "source": "test",
                "relevant_tickers": [],
            }
        ])
        try:
            load_research_findings(path)
            assert False, "expected a confirmed finding with no provenance to be rejected"
        except ValueError as exc:
            assert "no provenance" in str(exc)


def test_promising_unconfirmed_finding_without_provenance_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_registry(Path(tmp), [
            {
                "label": "Test finding",
                "claim": "Beats a baseline",
                "status": "promising_unconfirmed",
                "detail": "...",
                "source": "test",
                "relevant_tickers": [],
            }
        ])
        try:
            load_research_findings(path)
            assert False, "expected a promising_unconfirmed finding with no provenance to be rejected"
        except ValueError as exc:
            assert "no provenance" in str(exc)


def test_confirmed_finding_missing_one_required_provenance_field_is_rejected():
    incomplete = dict(_VALID_PROVENANCE)
    del incomplete["entry_timing"]
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_registry(Path(tmp), [
            {
                "label": "Test finding",
                "claim": "Beats a baseline",
                "status": "confirmed",
                "detail": "...",
                "source": "test",
                "relevant_tickers": [],
                "provenance": incomplete,
            }
        ])
        try:
            load_research_findings(path)
            assert False, "expected missing entry_timing to be rejected"
        except ValueError as exc:
            assert "entry_timing" in str(exc)


def test_rejected_finding_never_requires_provenance():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_registry(Path(tmp), [
            {
                "label": "Test finding",
                "claim": "Beats a baseline",
                "status": "rejected",
                "detail": "...",
                "source": "test",
                "relevant_tickers": [],
            }
        ])
        findings = load_research_findings(path)  # must not raise
        assert findings[0].provenance is None


def test_exploratory_and_unavailable_findings_never_require_provenance():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_registry(Path(tmp), [
            {
                "label": "Exploratory finding",
                "claim": "...",
                "status": "exploratory",
                "detail": "...",
                "source": "test",
                "relevant_tickers": [],
            },
            {
                "label": "Unavailable finding",
                "claim": "...",
                "status": "unavailable",
                "detail": "...",
                "source": "test",
                "relevant_tickers": [],
            },
        ])
        findings = load_research_findings(path)  # must not raise
        assert len(findings) == 2


def test_confirmed_finding_with_complete_provenance_loads_and_serializes_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_registry(Path(tmp), [
            {
                "label": "Test finding",
                "claim": "Beats a baseline",
                "status": "confirmed",
                "detail": "...",
                "source": "test",
                "relevant_tickers": ["SOXX", "SOXL"],
                "provenance": _VALID_PROVENANCE,
            }
        ])
        findings = load_research_findings(path)
        assert len(findings) == 1
        prov = findings[0].provenance
        assert prov is not None
        # Row counts and date ranges must retain their real types, not
        # get silently stringified/rounded during parsing.
        assert prov.actual_row_count == 1764
        assert isinstance(prov.actual_row_count, int)
        assert prov.actual_start_date == "2019-07-22"
        assert prov.actual_end_date == "2026-07-28"
        assert prov.requested_lookback_sessions == 1764
        assert prov.actual_lookback_sessions == 1764


def test_underfilled_dataset_warning_flags_short_history():
    prov = FindingProvenance(**{**_VALID_PROVENANCE, "requested_lookback_sessions": 1764, "actual_lookback_sessions": 907})
    warning = underfilled_dataset_warning(prov)
    assert warning is not None
    assert "907" in warning
    assert "1764" in warning


def test_underfilled_dataset_warning_silent_when_coverage_is_adequate():
    prov = FindingProvenance(**_VALID_PROVENANCE)  # requested == actual
    assert underfilled_dataset_warning(prov) is None


def test_underfilled_dataset_warning_silent_when_not_checkable():
    prov = FindingProvenance(actual_start_date="2020-01-01")  # no lookback fields at all
    assert underfilled_dataset_warning(prov) is None


def test_finding_not_reproduced_after_data_loader_fix_is_not_production_authoritative():
    prov = FindingProvenance(**{**_VALID_PROVENANCE, "reproduced_after_data_loader_fix": False})
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
        relevant_tickers=[], provenance=prov,
    )
    assert is_production_authoritative(finding) is False


def test_finding_reproduced_after_data_loader_fix_is_production_authoritative():
    prov = FindingProvenance(**{**_VALID_PROVENANCE, "reproduced_after_data_loader_fix": True})
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
        relevant_tickers=[], provenance=prov,
    )
    assert is_production_authoritative(finding) is True


def test_rejected_finding_is_always_production_authoritative_regardless_of_provenance():
    # A REJECTED verdict makes no positive production claim to distrust --
    # it's authoritative (in the sense of "don't act on this") with or
    # without provenance.
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.REJECTED, detail="...", source="test",
        relevant_tickers=[], provenance=None,
    )
    assert is_production_authoritative(finding) is True


def test_default_registry_loads_without_error_and_confirmed_findings_all_have_provenance():
    # Regression pin: the real, shipped research_findings.json must
    # satisfy its own new provenance requirement (finding #8) -- every
    # confirmed/promising_unconfirmed entry in the live registry needs
    # provenance, not just the temp fixtures above.
    findings = load_research_findings(DEFAULT_REGISTRY_PATH)
    assert len(findings) > 0
    for finding in findings:
        if finding.status in (EvidenceStatus.CONFIRMED, EvidenceStatus.PROMISING_UNCONFIRMED):
            assert finding.provenance is not None, f"{finding.label!r} is missing provenance"
            for field in REQUIRED_PROVENANCE_FIELDS:
                assert getattr(finding.provenance, field) is not None, f"{finding.label!r} missing {field}"


def test_default_registry_none_of_the_confirmed_findings_are_currently_production_authoritative():
    # Honest state as of this pass: none of the real registry's
    # confirmed/promising findings have been RE-RUN under the corrected
    # data loader (only their data coverage was freshly checked) -- so
    # none should currently report as production-authoritative.
    findings = load_research_findings(DEFAULT_REGISTRY_PATH)
    strong_findings = [f for f in findings if f.status in (EvidenceStatus.CONFIRMED, EvidenceStatus.PROMISING_UNCONFIRMED)]
    assert len(strong_findings) > 0
    assert all(not is_production_authoritative(f) for f in strong_findings)


def test_display_status_unqualified_when_production_authoritative():
    prov = FindingProvenance(**{**_VALID_PROVENANCE, "reproduced_after_data_loader_fix": True})
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
        relevant_tickers=[], provenance=prov,
    )
    assert finding.production_authoritative is True
    assert finding.display_status == "confirmed"


def test_display_status_qualified_when_not_production_authoritative():
    # GPT review, 2026-07-29: a confirmed/promising finding that is not
    # production_authoritative must never display as a bare "confirmed" --
    # the historical status label is preserved, but an explicit qualifier
    # is appended so a runtime consumer (CLI briefing, Streamlit UI)
    # cannot show it unqualified.
    prov = FindingProvenance(**{**_VALID_PROVENANCE, "reproduced_after_data_loader_fix": False})
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
        relevant_tickers=[], provenance=prov,
    )
    assert finding.production_authoritative is False
    assert finding.display_status.startswith("confirmed")
    assert "NOT CURRENTLY PRODUCTION-AUTHORITATIVE" in finding.display_status


def test_display_status_unqualified_for_rejected_regardless_of_provenance():
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.REJECTED, detail="...", source="test",
        relevant_tickers=[], provenance=None,
    )
    assert finding.production_authoritative is True
    assert finding.display_status == "rejected"


def test_to_dict_serializes_computed_authority_fields():
    # GPT review, 2026-07-29: production authority must reach every JSON
    # consumer (audit log, UI, briefing), not just be computable in memory.
    prov = FindingProvenance(**{**_VALID_PROVENANCE, "reproduced_after_data_loader_fix": False})
    finding = SignalEvidence(
        label="Test", claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
        relevant_tickers=[], provenance=prov,
    )
    from assistant.schemas import _to_dict

    serialized = _to_dict(finding)
    assert serialized["production_authoritative"] is False
    assert "NOT CURRENTLY PRODUCTION-AUTHORITATIVE" in serialized["display_status"]
    assert serialized["status"] == "confirmed"  # historical label preserved, not destroyed


def test_default_registry_flags_the_known_underfilled_nvdl_dataset():
    # Regression pin for the real underfilled-dataset case found while
    # implementing finding #8: NVDA/NVDL has substantially less history
    # than the other pairs in the 3-pair validation finding.
    findings = load_research_findings(DEFAULT_REGISTRY_PATH)
    three_pair = next(f for f in findings if "3-pair validation" in f.label)
    assert three_pair.provenance is not None
    warning = underfilled_dataset_warning(three_pair.provenance)
    assert warning is not None


if __name__ == "__main__":
    test_confirmed_finding_without_provenance_is_rejected()
    test_promising_unconfirmed_finding_without_provenance_is_rejected()
    test_confirmed_finding_missing_one_required_provenance_field_is_rejected()
    test_rejected_finding_never_requires_provenance()
    test_exploratory_and_unavailable_findings_never_require_provenance()
    test_confirmed_finding_with_complete_provenance_loads_and_serializes_correctly()
    test_underfilled_dataset_warning_flags_short_history()
    test_underfilled_dataset_warning_silent_when_coverage_is_adequate()
    test_underfilled_dataset_warning_silent_when_not_checkable()
    test_finding_not_reproduced_after_data_loader_fix_is_not_production_authoritative()
    test_finding_reproduced_after_data_loader_fix_is_production_authoritative()
    test_rejected_finding_is_always_production_authoritative_regardless_of_provenance()
    test_default_registry_loads_without_error_and_confirmed_findings_all_have_provenance()
    test_default_registry_none_of_the_confirmed_findings_are_currently_production_authoritative()
    test_display_status_unqualified_when_production_authoritative()
    test_display_status_qualified_when_not_production_authoritative()
    test_display_status_unqualified_for_rejected_regardless_of_provenance()
    test_to_dict_serializes_computed_authority_fields()
    test_default_registry_flags_the_known_underfilled_nvdl_dataset()
    print("All research registry tests passed.")
