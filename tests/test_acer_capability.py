"""Tests for the ACER-2 data-capability checks.

The dangerous direction is **claiming a capability the repository does not
have**, because that is what would let a study run on data nobody verified.
The tests therefore drive the false-positive direction hardest: a finding
cannot claim `available` without evidence, cannot claim `available` while
blocking, and `unmeasured` must stay distinct from `unavailable`.
"""
from __future__ import annotations

import pytest

from research.acer.capability import (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    STATUS_UNMEASURED,
    CapabilityFinding,
    assess_capabilities,
    check_databento_path,
    check_delisting_returns,
    check_point_in_time_prices,
    check_sector_classification,
    check_trading_session_calendar,
    check_value_control_source,
    summarize_capabilities,
)


def _by_requirement(findings):
    return {f.requirement: f for f in findings}


# --------------------------------------------------------------------------
# The contract itself
# --------------------------------------------------------------------------


def test_a_finding_cannot_be_created_without_evidence():
    with pytest.raises(ValueError, match="evidence"):
        CapabilityFinding(
            requirement="x", status=STATUS_AVAILABLE, evidence="  ", blocks_acer2=False
        )


def test_an_available_capability_cannot_also_block():
    """Guards the incoherent state that would read as 'ready but blocked'."""
    with pytest.raises(ValueError, match="cannot block"):
        CapabilityFinding(
            requirement="x",
            status=STATUS_AVAILABLE,
            evidence="something",
            blocks_acer2=True,
        )


def test_an_unknown_status_is_refused():
    with pytest.raises(ValueError, match="unknown status"):
        CapabilityFinding(
            requirement="x", status="probably fine", evidence="e", blocks_acer2=True
        )


def test_findings_are_frozen():
    finding = check_trading_session_calendar()
    with pytest.raises(Exception):
        finding.status = STATUS_AVAILABLE  # type: ignore[misc]


# --------------------------------------------------------------------------
# What the repository actually has, checked rather than asserted
# --------------------------------------------------------------------------


def test_the_nyse_session_calendar_is_available():
    """It was available all along, while a measurement approximated sessions
    as `calendar_days * 252/365`. That approximation was never necessary."""
    finding = check_trading_session_calendar()
    assert finding.status == STATUS_AVAILABLE
    assert finding.blocks_acer2 is False
    assert "pandas_market_calendars" in finding.evidence


def test_the_production_price_path_is_reported_as_not_point_in_time():
    finding = check_point_in_time_prices()
    assert finding.status == STATUS_UNAVAILABLE
    assert finding.blocks_acer2 is True
    assert "provides_point_in_time_lineage = False" in finding.evidence


def test_databento_is_unmeasured_rather_than_available_or_absent():
    """The path exists and has never been exercised for ACER. Calling it
    either way would be a claim nobody has earned."""
    finding = check_databento_path()
    assert finding.status == STATUS_UNMEASURED
    assert finding.blocks_acer2 is True
    assert "databento_source.py" in finding.evidence


def test_databento_capability_is_not_inferred_from_a_credential(monkeypatch):
    """A key proves access, not history depth or delisted coverage."""
    monkeypatch.setenv("DATABENTO_API_KEY", "db-not-a-real-key")
    finding = check_databento_path()
    assert finding.status == STATUS_UNMEASURED
    assert "db-not-a-real-key" not in finding.evidence
    assert "API_KEY" not in finding.evidence.upper()


def test_delisting_returns_are_reported_missing():
    finding = check_delisting_returns()
    assert finding.status == STATUS_UNAVAILABLE
    assert finding.blocks_acer2 is True


def test_the_value_control_has_no_local_source():
    finding = check_value_control_source()
    assert finding.status == STATUS_UNAVAILABLE
    assert finding.blocks_acer2 is True


def test_sector_is_sic_not_the_proposed_gics():
    finding = check_sector_classification()
    assert finding.status == STATUS_UNAVAILABLE
    assert "SIC" in finding.evidence and "GICS" in finding.requirement


# --------------------------------------------------------------------------
# The overall answer
# --------------------------------------------------------------------------


def test_acer2_is_not_runnable_and_the_summary_says_which_requirements_block():
    findings = assess_capabilities()
    report = summarize_capabilities(findings)
    assert report["acer2_runnable"] is False
    assert report["blocking"] >= 1
    assert report["requirements"] == len(findings)
    assert (
        report["available"] + report["unavailable"] + report["unmeasured"]
        == report["requirements"]
    )
    # The one capability that is genuinely present must not be listed as blocking.
    assert "NYSE trading-session calendar" not in report["blocking_requirements"]


def test_every_requirement_carries_its_own_evidence():
    for finding in assess_capabilities():
        assert finding.evidence.strip(), finding.requirement


def test_unmeasured_is_distinct_from_unavailable_in_the_summary():
    """Collapsing the two would let 'nobody checked' read as 'we checked'."""
    findings = _by_requirement(assess_capabilities())
    assert (
        findings["Databento point-in-time bars and reference"].status
        == STATUS_UNMEASURED
    )
    assert (
        findings["terminal returns for delisted securities"].status
        == STATUS_UNAVAILABLE
    )
    report = summarize_capabilities(list(findings.values()))
    assert report["unmeasured"] >= 1 and report["unavailable"] >= 1
