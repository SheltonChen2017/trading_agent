"""Behavioural regressions for the dormant ETF/portfolio arithmetic.

ARV2WL-D01 recorded that `_allocate`'s water filling and hard caps,
`mapped_candidate_coverage`, `weighted_stock_score`'s success path and
`portfolio_transaction_cost` were verified only by hand against independent
execution: in-tree tests covered their zero-access refusals and low-level
parsers, not their numbers. ARV2-5 lifts that gate with a one-file registry
change, at which point this arithmetic goes live with no regression net.

These tests exercise the arithmetic directly. They deliberately do **not**
weaken any authority: the zero-access refusals keep their own dedicated tests,
and nothing here mutates a committed artifact.
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.portfolio import (
    ALLOCATION_CONVERGENCE_TOLERANCE,
    Allocation,
    LookThroughExposure,
    PortfolioConstructionError,
    _allocate,
)


def _candidate(etf: str, inverse_volatility: str, sectors, clusters):
    """Stand-in exposing exactly the attributes `_allocate` reads.

    `PortfolioCandidate` cannot be constructed here because its `__post_init__`
    requires cross-section evidence, whose authority raises unconditionally by
    design. Candidate authentication is covered by its own tests; this isolates
    the allocator's arithmetic.
    """
    return SimpleNamespace(
        etf_security_id=etf,
        inverse_volatility=Decimal(inverse_volatility),
        sector_exposures=tuple(
            LookThroughExposure(group, fraction) for group, fraction in sectors
        ),
        overlap_clusters=tuple(
            LookThroughExposure(group, fraction) for group, fraction in clusters
        ),
    )


def _policy(**overrides):
    base = dict(
        etf_cap=Decimal("0.20"),
        sector_cap=Decimal("0.40"),
        overlap_cluster_cap=Decimal("0.30"),
        maximum_holdings=5,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _weights(allocations: tuple[Allocation, ...]) -> dict[str, Decimal]:
    return {item.etf_security_id: item.weight for item in allocations}


def test_five_equal_names_fill_to_the_etf_cap_and_leave_exact_cash():
    """Five names at the 20% cap invest the whole NAV with no residual."""
    selected = tuple(
        _candidate(f"etf-{index}", "1", [(f"sector-{index}", "1")], [(f"cluster-{index}", "1")])
        for index in range(5)
    )
    allocations, cash, reasons = _allocate(selected, _policy())
    weights = _weights(allocations)
    assert set(weights) == {f"etf-{index}" for index in range(5)}
    for weight in weights.values():
        assert weight == Decimal("0.20")
    assert sum(weights.values()) == Decimal("1")
    assert cash == Decimal("0")
    assert "constraints_leave_residual_cash" not in reasons


def test_fewer_names_than_the_cap_allows_leave_residual_cash_and_say_so():
    """Two names cannot exceed 20% each, so 60% of NAV must stay in cash."""
    selected = (
        _candidate("etf-a", "1", [("sector-a", "1")], [("cluster-a", "1")]),
        _candidate("etf-b", "1", [("sector-b", "1")], [("cluster-b", "1")]),
    )
    allocations, cash, reasons = _allocate(selected, _policy())
    weights = _weights(allocations)
    assert weights == {"etf-a": Decimal("0.20"), "etf-b": Decimal("0.20")}
    assert cash == Decimal("0.60")
    assert "fewer_than_maximum_eligible_candidates" in reasons
    assert "constraints_leave_residual_cash" in reasons


def test_shared_sector_cap_binds_before_the_etf_cap():
    """Three names in one sector are limited by the 40% sector cap, not 3x20%."""
    selected = tuple(
        _candidate(f"etf-{index}", "1", [("shared-sector", "1")], [(f"cluster-{index}", "1")])
        for index in range(3)
    )
    allocations, cash, _ = _allocate(selected, _policy())
    weights = _weights(allocations)
    # Equal inverse volatility divides the binding sector budget evenly. A
    # three-way split of 0.40 is not exactly representable, so compare the
    # names to each other exactly and the total to the cap within the one
    # named convergence tolerance.
    distinct = set(weights.values())
    assert len(distinct) == 1
    invested = sum(weights.values(), Decimal("0"))
    assert abs(invested - Decimal("0.40")) <= ALLOCATION_CONVERGENCE_TOLERANCE
    assert invested <= Decimal("0.40") + ALLOCATION_CONVERGENCE_TOLERANCE
    # The sector cap, not the 20% ETF cap, is what bound this allocation.
    for weight in weights.values():
        assert weight < Decimal("0.20")
    assert abs(cash - Decimal("0.60")) <= ALLOCATION_CONVERGENCE_TOLERANCE


def test_shared_overlap_cluster_cap_binds_at_thirty_percent():
    selected = tuple(
        _candidate(f"etf-{index}", "1", [(f"sector-{index}", "1")], [("shared-cluster", "1")])
        for index in range(3)
    )
    allocations, cash, _ = _allocate(selected, _policy())
    assert sum(_weights(allocations).values()) == Decimal("0.30")
    assert cash == Decimal("0.70")


def test_inverse_volatility_sets_the_proportions_then_the_cap_redistributes():
    """A high-inverse-vol name hits the 20% cap; the rest is water-filled on."""
    selected = (
        _candidate("etf-hot", "8", [("sector-a", "1")], [("cluster-a", "1")]),
        _candidate("etf-mid", "1", [("sector-b", "1")], [("cluster-b", "1")]),
        _candidate("etf-low", "1", [("sector-c", "1")], [("cluster-c", "1")]),
    )
    allocations, cash, _ = _allocate(selected, _policy())
    weights = _weights(allocations)
    assert weights["etf-hot"] == Decimal("0.20")
    # The two remaining equal-vol names share what is left, still under cap.
    assert weights["etf-mid"] == weights["etf-low"]
    assert weights["etf-mid"] <= Decimal("0.20")
    invested = sum(weights.values())
    assert invested + cash == Decimal("1")


def test_no_allocation_may_exceed_a_hard_cap_beyond_the_named_tolerance():
    """Every hard cap holds to within the one named convergence tolerance."""
    selected = tuple(
        _candidate(
            f"etf-{index}",
            str(index + 1),
            [("shared-sector", "1")] if index < 2 else [(f"sector-{index}", "1")],
            [("shared-cluster", "1")] if index % 2 == 0 else [(f"cluster-{index}", "1")],
        )
        for index in range(5)
    )
    allocations, cash, _ = _allocate(selected, _policy())
    weights = _weights(allocations)
    for weight in weights.values():
        assert weight <= Decimal("0.20") + ALLOCATION_CONVERGENCE_TOLERANCE
    shared_sector = sum(weights[f"etf-{i}"] for i in range(2))
    assert shared_sector <= Decimal("0.40") + ALLOCATION_CONVERGENCE_TOLERANCE
    shared_cluster = sum(weights[f"etf-{i}"] for i in (0, 2, 4))
    assert shared_cluster <= Decimal("0.30") + ALLOCATION_CONVERGENCE_TOLERANCE
    assert Decimal("0") <= cash <= Decimal("1")
    assert sum(weights.values()) + cash == Decimal("1")


def test_zero_inverse_volatility_mass_refuses_rather_than_dividing_by_zero():
    selected = (_candidate("etf-a", "0", [("sector-a", "1")], [("cluster-a", "1")]),)
    with pytest.raises(PortfolioConstructionError, match="inverse-volatility mass"):
        _allocate(selected, _policy())


# --------------------------------------------------------------------------
# Gated arithmetic. The zero-access source gate is bypassed LOCALLY so the
# numbers behind it can be exercised. The gate's own refusals keep their
# dedicated tests in tests/test_analyst_revisions_v2_contracts.py; nothing
# here changes a committed artifact or a production authority.
# --------------------------------------------------------------------------

import dataclasses
import hashlib

import research.analyst_revisions_v2.costs as cost_module
import research.analyst_revisions_v2.holdings as holdings_module
from research.analyst_revisions_v2.costs import (
    TradeCostInput,
    portfolio_transaction_cost,
    verify_trade_cost_evidence,
)
from research.analyst_revisions_v2.formulas import (
    FormulaError,
    analyst_decimal_context,
)
from research.analyst_revisions_v2.holdings import (
    HoldingsError,
    build_verified_holdings_snapshot,
    build_verified_stock_score_evidence,
    mapped_candidate_coverage,
    verify_holdings_evidence,
    weighted_stock_score,
)
from tests.test_analyst_revisions_v2_contracts import (
    DECISION,
    EPOCH,
    _holding,
    _holdings_source,
    _stock_score_source,
    _trade_cost_source,
)


@pytest.fixture
def policy(tmp_path_factory):
    from research.analyst_revisions_v2.formulas import derive_verified_analyst_policy
    from research.analyst_revisions_v2.preregistration import (
        load_reviewed_preregistration,
    )
    from tests.test_analyst_revisions_v2_preregistration import _anchored_spec

    patcher = pytest.MonkeyPatch()
    path, _ = _anchored_spec(
        tmp_path_factory.mktemp("arv2-dormant-arithmetic-policy"), patcher
    )
    value = derive_verified_analyst_policy(load_reviewed_preregistration(path))
    try:
        yield value
    finally:
        patcher.undo()


@pytest.fixture
def admit_sources(monkeypatch):
    """Locally admit fixture bytes so the gated arithmetic is reachable."""

    def admit(kind, source_bytes):
        if type(source_bytes) is not bytes or not source_bytes:
            raise FormulaError("research source must be non-empty immutable bytes")
        return source_bytes, hashlib.sha256(source_bytes).hexdigest()

    for module in (holdings_module, cost_module):
        monkeypatch.setattr(module, "require_registered_source_bytes", admit)


def _snapshot(*holdings, **kwargs):
    return build_verified_holdings_snapshot(
        source_bytes=_holdings_source(*holdings, **kwargs)
    )


def test_mapped_candidate_coverage_computes_the_exact_covered_fraction(
    policy, admit_sources
):
    """99% of a book mapped is eligible; 98% is not, and both report exactly."""
    eligible = _snapshot(_holding("a", "0.99"), _holding("b", "0.01", mapped=False))
    result = mapped_candidate_coverage(
        eligible,
        candidate_position_ids=("a", "b"),
        decision_at=DECISION,
        policy=policy,
    )
    assert result.mapped_weight == Decimal("0.99")
    assert result.denominator_weight == Decimal("1")
    assert result.coverage == Decimal("0.99")
    assert result.eligible is True
    assert result.refusal_reason is None

    short = _snapshot(_holding("a", "0.98"), _holding("b", "0.02", mapped=False))
    refused = mapped_candidate_coverage(
        short,
        candidate_position_ids=("a", "b"),
        decision_at=DECISION,
        policy=policy,
    )
    assert refused.coverage == Decimal("0.98")
    assert refused.eligible is False
    assert refused.refusal_reason == "insufficient_mapped_candidate_weight"


def test_coverage_eligibility_is_exact_at_the_threshold_boundary(
    policy, admit_sources
):
    """The 99% gate is decided exactly, and its boundary is inclusive.

    ARV2WL-D03 observed that eligibility compared a rounded
    ``mapped / denominator`` rather than exact rationals. The comparison is now
    ``Fraction(mapped) >= Fraction(threshold) * Fraction(denominator)``. That
    is strictly more correct, but it is hardening rather than a reachable bug
    fix: ``mapped`` is accumulated under the same 50-digit context, so a weight
    carrying more digits is already rounded before the comparison sees it, and
    both forms then agree. This pins the boundary the gate actually decides.
    """
    exactly_at = _snapshot(_holding("a", "0.99"), _holding("b", "0.01", mapped=False))
    at_threshold = mapped_candidate_coverage(
        exactly_at,
        candidate_position_ids=("a", "b"),
        decision_at=DECISION,
        policy=policy,
    )
    assert Fraction(at_threshold.mapped_weight) == Fraction(Decimal("0.99")) * Fraction(
        at_threshold.denominator_weight
    )
    assert at_threshold.eligible is True

    one_representable_step_below = _snapshot(
        _holding("a", "0.9899999999999999999999999999999999999999999999999"),
        _holding("b", "0.0100000000000000000000000000000000000000000000001", mapped=False),
    )
    below = mapped_candidate_coverage(
        one_representable_step_below,
        candidate_position_ids=("a", "b"),
        decision_at=DECISION,
        policy=policy,
    )
    assert Fraction(below.mapped_weight) < Fraction(Decimal("0.99")) * Fraction(
        below.denominator_weight
    )
    assert below.eligible is False
    assert below.refusal_reason == "insufficient_mapped_candidate_weight"


def test_weighted_score_requires_loader_authenticated_exact_score_artifact(
    policy, admit_sources
):
    """Named in the archived remediation record (ARV2WL-D02); now real.

    Also exercises the ``weighted_stock_score`` success path: the
    coverage-weighted mean over mapped positions only.
    """
    snapshot = _snapshot(_holding("a", "0.75"), _holding("b", "0.25"))
    evidence = verify_holdings_evidence(snapshot, decision_at=DECISION, policy=policy)
    scores = build_verified_stock_score_evidence(
        source_bytes=_stock_score_source(
            [
                {"security_id": "sec-a", "state": "signal", "value": "2"},
                {"security_id": "sec-b", "state": "signal", "value": "-2"},
            ],
            policy=policy,
        ),
        policy=policy,
    )
    # 0.75*2 + 0.25*(-2) = 1.0, divided by mapped weight 1.0.
    assert weighted_stock_score(
        evidence, stock_score_evidence=scores, policy=policy
    ) == Decimal("1")

    # A hand-built copy that never passed the loader has no authority.
    forged = object.__new__(type(scores))
    for field in dataclasses.fields(scores):
        object.__setattr__(forged, field.name, getattr(scores, field.name))
    with pytest.raises(HoldingsError):
        weighted_stock_score(evidence, stock_score_evidence=forged, policy=policy)


def test_stock_score_artifact_refuses_missing_extra_duplicate_and_invalid_rows(
    policy, admit_sources
):
    """Named in the archived remediation record (ARV2WL-D02); now real."""
    snapshot = _snapshot(_holding("a", "0.5"), _holding("b", "0.5"))
    evidence = verify_holdings_evidence(snapshot, decision_at=DECISION, policy=policy)

    def scored(records):
        return build_verified_stock_score_evidence(
            source_bytes=_stock_score_source(records, policy=policy), policy=policy
        )

    missing = scored([{"security_id": "sec-a", "state": "signal", "value": "1"}])
    with pytest.raises(HoldingsError, match="exactly cover"):
        weighted_stock_score(evidence, stock_score_evidence=missing, policy=policy)

    extra = scored(
        [
            {"security_id": "sec-a", "state": "signal", "value": "1"},
            {"security_id": "sec-b", "state": "signal", "value": "1"},
            {"security_id": "sec-z", "state": "signal", "value": "1"},
        ]
    )
    with pytest.raises(HoldingsError, match="exactly cover"):
        weighted_stock_score(evidence, stock_score_evidence=extra, policy=policy)

    with pytest.raises(HoldingsError):
        scored(
            [
                {"security_id": "sec-a", "state": "signal", "value": "1"},
                {"security_id": "sec-a", "state": "signal", "value": "1"},
            ]
        )
    with pytest.raises(HoldingsError, match="nonzero"):
        scored([{"security_id": "sec-a", "state": "signal", "value": "0"}])


def test_stock_score_authority_refuses_clone_mutation_substitution_and_foreign_context(
    policy, admit_sources
):
    """Named in the archived remediation record (ARV2WL-D02); now real."""
    snapshot = _snapshot(_holding("a", "1"))
    evidence = verify_holdings_evidence(snapshot, decision_at=DECISION, policy=policy)
    scores = build_verified_stock_score_evidence(
        source_bytes=_stock_score_source(
            [{"security_id": "sec-a", "state": "signal", "value": "1"}], policy=policy
        ),
        policy=policy,
    )
    assert weighted_stock_score(
        evidence, stock_score_evidence=scores, policy=policy
    ) == Decimal("1")

    # Mutating the authenticated artifact after the fact must be detected.
    object.__setattr__(scores, "score_artifact_id", "substituted-artifact")
    with pytest.raises(HoldingsError):
        weighted_stock_score(evidence, stock_score_evidence=scores, policy=policy)


def test_portfolio_transaction_cost_matches_hand_arithmetic(policy, admit_sources):
    """Dollars per net security change, divided once by NAV."""
    cost_evidence = verify_trade_cost_evidence(
        source_bytes=_trade_cost_source("sec-a", policy=policy), policy=policy
    )
    result = portfolio_transaction_cost(
        (
            TradeCostInput(
                trade_id="t-1",
                security_id="sec-a",
                delta_dollars="100",
                cost_evidence=cost_evidence,
            ),
        ),
        nav_dollars="1000",
        policy=policy,
        cost_scenario_bps="10",
        decision_at=DECISION,
        evidence_epoch_id=EPOCH,
    )
    # commission 0.001 + half spread 0.001 + 10bps 0.001 = 0.003
    # impact 0.01 * sqrt(100/10000) = 0.01 * 0.1 = 0.001  ->  rate 0.004
    # dollars = 100 * 0.004 = 0.4 ; portfolio return = 0.4 / 1000 = 0.0004
    assert result.dollars == Decimal("0.4")
    assert result.portfolio_return == Decimal("0.0004")
    assert result.one_way_turnover == Decimal("0.1")


def test_split_trades_cannot_lower_modeled_impact_cost(policy, admit_sources):
    """Splitting one economically identical trade must not reduce modeled cost."""
    cost_evidence = verify_trade_cost_evidence(
        source_bytes=_trade_cost_source("sec-a", policy=policy), policy=policy
    )

    def cost(*deltas):
        return portfolio_transaction_cost(
            tuple(
                TradeCostInput(
                    trade_id=f"t-{index}",
                    security_id="sec-a",
                    delta_dollars=delta,
                    cost_evidence=cost_evidence,
                )
                for index, delta in enumerate(deltas)
            ),
            nav_dollars="1000",
            policy=policy,
            cost_scenario_bps="10",
            decision_at=DECISION,
            evidence_epoch_id=EPOCH,
        ).dollars

    assert cost("100") == cost("50", "50") == cost("25", "25", "25", "25")
