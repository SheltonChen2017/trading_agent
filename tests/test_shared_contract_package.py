"""Product-neutral behavior owned by the future tiny contracts package."""
from __future__ import annotations

from decimal import Decimal

import pytest

from data.evidence_status import EvidenceStatus
from data.financial_primitives import decimal_text, to_decimal
from data.research_results import (
    ResearchResultContractError,
    SignalTriggerResult,
    TickerSignalResearchResult,
    research_parameters_sha256,
)


def test_shared_evidence_status_values_are_stable_and_non_authoritative():
    assert [status.value for status in EvidenceStatus] == [
        "confirmed",
        "promising_unconfirmed",
        "exploratory",
        "rejected",
        "unavailable",
    ]


def test_shared_decimal_primitives_preserve_exact_finite_text():
    assert to_decimal("10.2500") == Decimal("10.2500")
    assert decimal_text(Decimal("10.2500")) == "10.25"
    with pytest.raises(ValueError, match="finite decimal"):
        to_decimal("NaN")


def test_shared_research_results_are_immutable_and_deterministically_bound():
    trigger = SignalTriggerResult(
        rule="zscore",
        direction="dip",
        date="2026-08-22",
        return_zscore=-2.25,
        volume_zscore=1.75,
    )
    result = TickerSignalResearchResult(
        ticker="SPY",
        as_of="2026-08-22",
        triggers=(trigger,),
    )
    assert result.triggers[0].to_dict() == {
        "rule": "zscore",
        "direction": "dip",
        "date": "2026-08-22",
        "return_zscore": -2.25,
        "volume_zscore": 1.75,
    }
    assert research_parameters_sha256({"window": 20, "threshold": 2.0}) == (
        research_parameters_sha256({"threshold": 2.0, "window": 20})
    )
    with pytest.raises(ResearchResultContractError, match="finite JSON"):
        research_parameters_sha256({"threshold": float("nan")})
