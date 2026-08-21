"""Tests for the ACER-2 data-capability checks.

The dangerous direction is **claiming a capability the repository does not
have**, because that is what would let a study run on data nobody verified.
The tests therefore drive the false-positive direction hardest: a finding
cannot claim `available` without evidence, cannot claim `available` while
blocking, and `unmeasured` must stay distinct from `unavailable`.
"""
from __future__ import annotations

import re

import pytest

import research.acer.capability as capability
from research.acer.capability import REPO_ROOT
from research.acer.capability import (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    STATUS_UNMEASURED,
    CapabilityFinding,
    assess_capabilities,
    check_databento_path,
    check_delisting_returns,
    check_earnings_surprise_control,
    check_point_in_time_corporate_actions,
    check_point_in_time_prices,
    check_point_in_time_security_eligibility,
    check_ratings_event_corpus,
    check_sector_classification,
    check_size_control_source,
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


@pytest.mark.parametrize("status", [STATUS_UNAVAILABLE, STATUS_UNMEASURED])
def test_a_non_available_requirement_cannot_be_non_blocking(status):
    """Every finding describes a required ACER-2 input, so an unavailable
    or unmeasured one must fail closed rather than permit the study."""
    with pytest.raises(ValueError, match="must block"):
        CapabilityFinding(
            requirement="x", status=status, evidence="missing", blocks_acer2=False
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


def test_the_calendar_is_not_called_importable_when_import_fails(monkeypatch):
    """Module discovery alone is not an import or a usable calendar."""
    def _fail_import(_name):
        raise ImportError("simulated broken installation")

    monkeypatch.setattr(capability.importlib, "import_module", _fail_import)
    finding = check_trading_session_calendar()
    assert finding.status == STATUS_UNAVAILABLE
    assert finding.blocks_acer2 is True
    assert "importable=False" in finding.evidence


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


def test_the_earnings_surprise_control_has_no_point_in_time_source():
    """ACER-0A.7 names earnings surprise as a required control, and the only
    local earnings module is yfinance-backed and exposes the vendor's own
    percentage — the exact value ACER-0A.5 declines to trust."""
    finding = check_earnings_surprise_control()
    assert finding.status == STATUS_UNAVAILABLE
    assert finding.blocks_acer2 is True
    assert "surprise_pct" in finding.evidence


def test_the_checklist_covers_every_control_that_needs_its_own_source():
    """The summary refuses anything but the *complete* set, so a control
    silently missing from the checklist would make the incompleteness harder
    to notice, not easier. Size, value, sector and earnings surprise each need
    a distinct source; the other four ACER-0A.7 controls are arithmetic over
    prices and the ratings corpus and are covered by the price requirement.
    """
    requirements = {finding.requirement for finding in assess_capabilities()}
    assert any("value" in name for name in requirements)
    assert any("shares outstanding" in name for name in requirements)
    assert any("sector" in name for name in requirements)
    assert any("earnings-surprise" in name for name in requirements)
    assert set(capability._CONTROLS_COVERED_BY_PRICES) == {
        "momentum",
        "liquidity",
        "volatility",
        "analyst coverage",
    }


def test_every_control_named_in_the_frozen_document_is_accounted_for():
    """Derive the control list from the frozen document instead of memory.

    Twice in successive rounds this checklist was asserted complete and was
    not: the first time it omitted earnings surprise, the second it omitted
    size, the ratings corpus, corporate actions, and security eligibility.
    Both omissions came from writing the list from memory rather than reading
    the specification that fixes it.

    So this test parses ACER-0A.7's frozen control list and requires every
    control to be accounted for exactly one way — either as arithmetic over
    prices and the corpus, or by a named requirement with its own check. A
    control that is neither fails here rather than being silently treated as
    satisfied.
    """
    text = (
        REPO_ROOT
        / "docs"
        / "research"
        / "ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md"
    ).read_text(encoding="utf-8")
    # Strip parentheticals from the WHOLE document before matching. Doing it
    # afterwards left "ACER-0A.2" inside the sentence, and the regex then
    # stopped at that period and produced a fragment.
    normalized = re.sub(r"\([^)]*\)", "", " ".join(text.split()))
    match = re.search(
        r"\*\*Controls\*\*, all point-in-time as of the eligibility session:(.+?)\.",
        normalized,
    )
    assert match, "the frozen control sentence was not found — fix the test, not the guard"

    controls = {
        part.strip().strip(",").removeprefix("and ").strip().casefold()
        for part in match.group(1).split(",")
    }
    controls = {name for name in controls if name}
    # Fail loudly if the parse degrades, rather than passing vacuously on an
    # empty or truncated set — the mirror case of this guard.
    assert len(controls) == 8, f"expected 8 frozen controls, parsed {sorted(controls)}"

    # Exact set equality, never a substring search: the previous version of
    # this assertion matched a broken parse fragment against an unrelated
    # requirement and passed while a control was missing.
    assert controls == set(capability._CONTROL_ACCOUNTING), (
        "the frozen control list and the accounting map disagree: "
        f"only in document={sorted(controls - set(capability._CONTROL_ACCOUNTING))}, "
        f"only in map={sorted(set(capability._CONTROL_ACCOUNTING) - controls)}"
    )

    # Every control accounted for by a named requirement must actually be in
    # the required set, and every price-derived claim must be declared.
    for control, accounting in sorted(capability._CONTROL_ACCOUNTING.items()):
        if accounting.startswith("derived from"):
            assert control in {
                name.casefold() for name in capability._CONTROLS_COVERED_BY_PRICES
            }, f"{control} claims derivation but is not in the declared list"
        else:
            assert accounting in capability._REQUIRED_REQUIREMENTS, (
                f"{control} maps to {accounting!r}, which is not a required "
                "requirement"
            )


def test_the_core_ratings_event_corpus_is_itself_required():
    """A checker cannot call ACER-2 runnable after checking only controls and
    outcomes; the normalized analyst-event signal is a required input too."""
    finding = check_ratings_event_corpus()
    assert finding.status == STATUS_UNMEASURED
    assert finding.blocks_acer2 is True
    assert "normalized" in finding.evidence.lower()


def test_size_is_not_claimed_to_be_covered_by_prices_alone():
    """The frozen size control is log market cap, which also needs a
    point-in-time share count. A price-only requirement cannot cover it."""
    finding = check_size_control_source()
    assert finding.status == STATUS_UNMEASURED
    assert finding.blocks_acer2 is True
    assert "shares" in finding.evidence.lower()


def test_total_return_corporate_actions_are_a_separate_requirement():
    """The frozen outcome includes dividends and split handling. Daily bars
    alone do not prove a point-in-time corporate-action source."""
    finding = check_point_in_time_corporate_actions()
    assert finding.status in {STATUS_UNAVAILABLE, STATUS_UNMEASURED}
    assert finding.blocks_acer2 is True
    assert "corporate" in finding.requirement.lower()


def test_security_type_and_listing_history_are_a_separate_requirement():
    """Issuer identity cannot establish that a historical instrument was a
    US primary-listed common stock rather than an excluded security type."""
    finding = check_point_in_time_security_eligibility()
    assert finding.status in {STATUS_UNAVAILABLE, STATUS_UNMEASURED}
    assert finding.blocks_acer2 is True
    assert "security" in finding.requirement.lower()


@pytest.mark.parametrize(
    ("check", "expected_text"),
    [
        (check_ratings_event_corpus, "pipeline modules"),
        (check_size_control_source, "shares tag"),
        (check_point_in_time_corporate_actions, "no corporate-action"),
        (check_point_in_time_security_eligibility, "no point-in-time security"),
    ],
)
def test_new_requirements_fail_closed_when_their_sources_disappear(
    tmp_path, monkeypatch, check, expected_text
):
    """Each added guard is load-bearing in the dangerous direction: removing
    all source evidence must never leave it unmeasured or available."""
    monkeypatch.setattr(capability, "REPO_ROOT", tmp_path)
    finding = check()
    assert finding.status == STATUS_UNAVAILABLE
    assert finding.blocks_acer2 is True
    assert expected_text in finding.evidence.lower()


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


def test_an_incomplete_requirement_set_cannot_report_acer2_runnable():
    """A caller must not obtain a green result by omitting blocking checks."""
    calendar_only = [check_trading_session_calendar()]
    with pytest.raises(ValueError, match="complete ACER-2 requirement set"):
        summarize_capabilities(calendar_only)


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
