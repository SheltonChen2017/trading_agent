from __future__ import annotations

import copy
import dataclasses
import hashlib
import itertools
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

import research.analyst_revisions_v2.formulas as formula_module
import research.analyst_revisions_v2.costs as cost_module
import research.analyst_revisions_v2.holdings as holdings_module
import research.analyst_revisions_v2.portfolio as portfolio_module
from research.analyst_revisions_v2.availability import (
    AvailabilityError,
    AvailabilityQuality,
    derive_event_availability,
    prove_timing_order,
)
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.costs import (
    CostModelError,
    TerminalEventKind,
    TradeCostInput,
    portfolio_transaction_cost,
    verify_terminal_exit_evidence,
    verify_trade_cost_evidence,
)
from research.analyst_revisions_v2.formulas import (
    FormulaError,
    IndependentContribution,
    ObservationState,
    ResearchSourceKind,
    SignalObservation,
    analyst_reliability,
    derive_verified_analyst_policy,
    effective_contributors,
    independent_evidence_breadth,
    robust_group_normalize,
)
from research.analyst_revisions_v2.holdings import (
    Holding,
    HoldingsError,
    HoldingsSnapshot,
    InstrumentKind,
    MappingState,
    build_verified_holdings_snapshot,
    build_verified_stock_score_evidence,
    mapped_candidate_coverage,
    require_verified_stock_score_evidence,
    require_verified_holdings_snapshot,
    verify_holdings_evidence,
    weighted_stock_score,
)
from research.analyst_revisions_v2.portfolio import (
    PortfolioCandidate,
    PortfolioConstructionError,
    PortfolioRules,
    build_verified_classification_evidence,
    build_verified_cross_section_evidence,
    construct_portfolio,
)
from research.analyst_revisions_v2.provider_history import (
    MEASURED_ACCEPTED_COUNTS,
    ProviderEra,
    classify_provider_era,
)


DECISION = "2026-08-25T13:30:00+00:00"
EPOCH = "arv2-epoch-2026-08-25"
DATASET_ID = "arv2_ds_" + "a" * 64
_TEST_POLICY = None


@pytest.fixture(scope="module", autouse=True)
def _loader_authenticated_policy(tmp_path_factory: pytest.TempPathFactory):
    from research.analyst_revisions_v2.preregistration import (
        load_reviewed_preregistration,
    )
    from tests.test_analyst_revisions_v2_preregistration import _anchored_spec

    patcher = pytest.MonkeyPatch()
    path, _ = _anchored_spec(
        tmp_path_factory.mktemp("arv2-policy-authority"), patcher
    )
    policy = derive_verified_analyst_policy(load_reviewed_preregistration(path))
    global _TEST_POLICY
    _TEST_POLICY = policy
    try:
        yield policy
    finally:
        _TEST_POLICY = None
        patcher.undo()


def _decimal_text(value: object) -> str:
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if parsed == 0 else rendered


def _policy():
    assert _TEST_POLICY is not None
    return _TEST_POLICY


def _holding(
    position_id: str,
    weight: str,
    *,
    mapped: bool = True,
) -> Holding:
    return Holding(
        position_id=position_id,
        instrument_kind=InstrumentKind.LONG_EQUITY,
        weight=weight,
        security_id=f"sec-{position_id}" if mapped else None,
        share_class_id=f"class-{position_id}" if mapped else None,
        mapping_state=MappingState.MAPPED if mapped else MappingState.UNMAPPED,
        peer_category_id="industry-1" if mapped else None,
    )


def _holding_row(value: Holding) -> dict[str, object]:
    return {
        "position_id": value.position_id,
        "instrument_kind": value.instrument_kind.value,
        "weight": _decimal_text(value.weight),
        "security_id": value.security_id,
        "share_class_id": value.share_class_id,
        "mapping_state": value.mapping_state.value,
        "peer_category_id": value.peer_category_id,
    }


def _holdings_source(
    *holdings: Holding,
    declared: str = "1",
    etf_security_id: str = "etf-1",
    effective_at: str = "2026-08-24T20:00:00+00:00",
    effective_session: str = "2026-08-24",
    available_at: str = "2026-08-25T12:00:00+00:00",
    evidence_epoch_id: str = EPOCH,
    sort_rows: bool = True,
) -> bytes:
    rows = [_holding_row(row) for row in holdings]
    if sort_rows:
        rows.sort(key=lambda row: row["position_id"])
    return canonical_json_bytes(
        {
            "schema": "arv2-holdings-source-v1",
            "source_id": f"provider-holdings-{etf_security_id}",
            "evidence_epoch_id": evidence_epoch_id,
            "etf_security_id": etf_security_id,
            "source_snapshot_id": f"snapshot-{etf_security_id}",
            "effective_at": effective_at,
            "effective_session": effective_session,
            "available_at": available_at,
            "declared_total_weight": _decimal_text(declared),
            "holdings": rows,
        }
    )


def _classification_source(
    holdings_evidence,
    *,
    etf_security_id: str | None = None,
    decision_at: str | None = None,
    epoch: str | None = None,
    sector: str = "sector-a",
    sector_fraction: str = "1",
    cluster: str = "cluster-a",
    cluster_fraction: str = "1",
) -> bytes:
    etf_id = etf_security_id or holdings_evidence.etf_security_id
    return canonical_json_bytes(
        {
            "schema": "arv2-classification-source-v1",
            "source_id": f"provider-classification-{etf_id}",
            "evidence_epoch_id": epoch or holdings_evidence.evidence_epoch_id,
            "effective_at": holdings_evidence.snapshot.effective_at,
            "available_at": holdings_evidence.snapshot.available_at,
            "etf_security_id": etf_id,
            "holdings_snapshot_content_sha256": (
                holdings_evidence.snapshot_content_sha256
            ),
            "decision_at": decision_at or holdings_evidence.decision_at,
            "sector_exposures": [
                {"group_id": sector, "fraction": sector_fraction}
            ],
            "overlap_clusters": [
                {"group_id": cluster, "fraction": cluster_fraction}
            ],
        }
    )


def _cross_section_source(
    rows: list[dict[str, str]],
    *,
    policy,
    epoch: str = EPOCH,
    decision_at: str = DECISION,
) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "arv2-cross-section-source-v1",
            "source_id": "provider-cross-section-primary",
            "evidence_epoch_id": epoch,
            "effective_at": "2026-08-25T11:30:00+00:00",
            "available_at": "2026-08-25T12:30:00+00:00",
            "decision_at": decision_at,
            "policy_sha256": policy.evidence_sha256,
            "candidates": sorted(rows, key=lambda row: row["etf_security_id"]),
        }
    )


def _trade_cost_source(
    security_id: str,
    *,
    policy,
    adv: str | None = "10000",
    commission: str = "0.001",
    spread: str = "0.001",
    impact: str = "0.01",
    epoch: str = EPOCH,
    decision_at: str = DECISION,
) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "arv2-trade-cost-source-v1",
            "source_id": f"provider-trade-cost-{security_id}",
            "evidence_epoch_id": epoch,
            "policy_sha256": policy.evidence_sha256,
            "security_id": security_id,
            "effective_at": "2026-08-24T20:00:00+00:00",
            "available_at": "2026-08-25T12:00:00+00:00",
            "decision_at": decision_at,
            "commission_rate": commission,
            "half_spread_rate": spread,
            "impact_coefficient": impact,
            "adv_dollars": adv,
        }
    )


def _terminal_source(
    security_id: str,
    *,
    epoch: str = EPOCH,
    decision_at: str = DECISION,
) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "arv2-terminal-exit-source-v1",
            "source_id": f"provider-terminal-{security_id}",
            "evidence_epoch_id": epoch,
            "security_id": security_id,
            "terminal_event_id": f"terminal-{security_id}",
            "event_kind": TerminalEventKind.DELISTING.value,
            "position_snapshot_id": f"positions-{EPOCH}",
            "current_long_position_dollars": "100",
            "effective_at": "2026-08-24T20:00:00+00:00",
            "available_at": "2026-08-25T12:00:00+00:00",
            "decision_at": decision_at,
        }
    )


def _stock_score_source(
    records: list[dict[str, object]],
    *,
    policy,
    dataset_id: str = DATASET_ID,
    policy_sha256: str | None = None,
    epoch: str = EPOCH,
    dataset_epoch: str | None = None,
    decision_at: str = DECISION,
    source_id: str = "reviewed-score-artifact-source",
) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "arv2-stock-score-source-v1",
            "source_id": source_id,
            "score_artifact_id": "arv2-stock-scores-primary",
            "evidence_epoch_id": epoch,
            "policy_sha256": policy_sha256 or policy.evidence_sha256,
            "derived_at": "2026-08-25T12:15:00+00:00",
            "available_at": "2026-08-25T12:30:00+00:00",
            "decision_at": decision_at,
            "normalized_dataset": {
                "dataset_id": dataset_id,
                "normalization_result_sha256": "1" * 64,
                "snapshot_id": "normalized-source-snapshot",
                "snapshot_manifest_sha256": "2" * 64,
                "normalizer_config_sha256": "3" * 64,
                "normalizer_code_sha256": "4" * 64,
                "evidence_epoch_id": dataset_epoch or epoch,
                "build_recipe_id": "normalization-recipe-primary",
                "build_recipe_sha256": "5" * 64,
                "producing_commit": "6" * 40,
                "producing_tree": "7" * 40,
                "events_sha256": "8" * 64,
                "refusals_sha256": "9" * 64,
            },
            "derivation": {
                "derivation_id": "stock-score-derivation-primary",
                "derivation_config_sha256": "a" * 64,
                "derivation_code_sha256": "b" * 64,
                "producing_commit": "c" * 40,
                "producing_tree": "d" * 40,
            },
            "scores": records,
        }
    )


def test_numerical_zero_boundary_is_exact_and_inclusive() -> None:
    """Pin the single NUMERICAL_ZERO use site at its exact boundary.

    The 1e-18 constant guards only the inverse-Herfindahl 0/0 in
    effective_contributors: total absolute mass at or below the constant is
    zero evidence, anything strictly above counts. Nothing previously probed
    the boundary itself, so the threshold could be widened anywhere below the
    tested 1e-12 - a genuine hidden epsilon - with the suite green.
    """
    from research.analyst_revisions_v2.formulas import NUMERICAL_ZERO

    assert NUMERICAL_ZERO == Decimal("1e-18")
    assert effective_contributors([NUMERICAL_ZERO]) == 0
    assert effective_contributors([Decimal("1.000000000000000001e-18")]) == 1
    assert effective_contributors([Decimal("2e-18")]) == 1
    # The gate applies to the summed mass, not per-value.
    assert effective_contributors([Decimal("6e-19"), Decimal("6e-19")]) == 2
    assert effective_contributors([Decimal("5e-19"), Decimal("5e-19")]) == 0


def test_effective_contributors_has_no_epsilon_or_ambient_context_pathology() -> None:
    assert effective_contributors([]) == 0
    assert effective_contributors(["1e-12"]) == 1
    assert effective_contributors([1, 1, 1, 1]) == 4
    dominant = effective_contributors([1, "1e-12"])
    with localcontext() as context:
        context.prec = 6
        assert effective_contributors([1, "1e-12"]) == dominant
    assert Decimal("1") <= dominant < Decimal("1.00000000001")
    with pytest.raises(FormulaError):
        effective_contributors([Decimal("NaN")])
    dynamic_range = ("1e49", "3", "1", "1e-49")
    expected = effective_contributors(dynamic_range)
    with localcontext() as context:
        context.prec = 6
        assert {
            effective_contributors(permutation)
            for permutation in itertools.permutations(dynamic_range)
        } == {expected}


@pytest.mark.parametrize(
    "bad_value",
    [
        "not-a-number",
        "NaN",
        "Infinity",
        Decimal("NaN"),
        Decimal("Infinity"),
        float("nan"),
        float("inf"),
        None,
        True,
    ],
)
def test_all_analyst_decimal_boundaries_reject_unsafe_values(bad_value) -> None:
    boundaries = (
        (formula_module._decimal, FormulaError),
        (cost_module._d, CostModelError),
        (holdings_module._decimal, HoldingsError),
        (portfolio_module._d, PortfolioConstructionError),
    )
    for parser, error_type in boundaries:
        with pytest.raises(error_type):
            parser(bad_value, "test_value")


@pytest.mark.parametrize(
    "bad_value",
    [
        False,
        True,
        "not-a-number",
        Decimal("sNaN"),
        Decimal("NaN"),
        Decimal("Infinity"),
        float("nan"),
        float("inf"),
    ],
)
def test_structural_zero_observations_use_the_strict_decimal_boundary(
    bad_value,
) -> None:
    with pytest.raises(FormulaError):
        SignalObservation(
            "sec-structural-zero",
            ObservationState.STRUCTURAL_ZERO,
            bad_value,
        )


def test_structural_zero_observation_canonicalizes_explicit_zero() -> None:
    observation = SignalObservation(
        "sec-structural-zero",
        ObservationState.STRUCTURAL_ZERO,
        "-0.000",
    )

    assert observation.value == Decimal("0")
    assert isinstance(observation.value, Decimal)


def test_robust_normalization_preserves_exact_decimal_median_and_mad() -> None:
    result = robust_group_normalize(
        [
            SignalObservation(
                f"sec-{index:02}",
                ObservationState.SIGNAL,
                Decimal(index) / Decimal("10"),
            )
            for index in range(1, 21)
        ],
        policy=_policy(),
    )

    assert result.available
    assert result.median == Decimal("1.05")
    assert result.mad == Decimal("0.5")


def test_independent_breadth_does_not_multiply_repeats_or_common_catalyst() -> None:
    one_firm = independent_evidence_breadth(
        IndependentContribution("firm-1", f"event-{index}", 1)
        for index in range(5)
    )
    assert one_firm.institution_effective_n == 1
    one_catalyst = independent_evidence_breadth(
        IndependentContribution(f"firm-{index}", "earnings-1", 1)
        for index in range(15)
    )
    assert one_catalyst.institution_effective_n == 15
    assert one_catalyst.independent_effective_n == 1
    dynamic_rows = (
        IndependentContribution("firm-a", "event-a", "1e49"),
        IndependentContribution("firm-a", "event-b", "-1e49"),
        IndependentContribution("firm-a", "event-c", "1"),
        IndependentContribution("firm-b", "event-d", "2"),
    )
    expected = independent_evidence_breadth(dynamic_rows)
    with localcontext() as context:
        context.prec = 5
        assert {
            independent_evidence_breadth(permutation)
            for permutation in itertools.permutations(dynamic_rows)
        } == {expected}


def test_invalid_and_underidentified_normalization_fail_closed() -> None:
    policy = _policy()
    sparse = robust_group_normalize(
        [SignalObservation("sec-1", ObservationState.SIGNAL, 1)], policy=policy
    )
    assert not sparse.available and sparse.reason == "insufficient_total_names"
    zero_mad = robust_group_normalize(
        [
            SignalObservation(f"sec-{index:02}", ObservationState.SIGNAL, 1)
            for index in range(20)
        ],
        policy=policy,
    )
    assert not zero_mad.available and zero_mad.reason == "zero_mad"
    with pytest.raises(FormulaError, match="invalid observations refuse"):
        robust_group_normalize(
            [SignalObservation("invalid", ObservationState.INVALID, None)],
            policy=policy,
        )
    assert analyst_reliability(
        coverage="0.25", independent_effective_n=5, quality=1
    ) == Decimal("0.5")


def test_policy_authority_refuses_caller_authored_rules_or_unreviewed_input() -> None:
    policy = _policy()
    assert policy.half_life_sessions == 20
    assert policy.authorized_normalized_dataset_ids == (DATASET_ID,)
    assert policy.cost_scenario_bps == tuple(map(Decimal, ("0", "5", "10", "20")))
    with pytest.raises(PortfolioConstructionError, match="no longer caller-constructible"):
        PortfolioRules()
    with pytest.raises(FormulaError, match="reviewed preregistration"):
        derive_verified_analyst_policy(object())
    cloned = copy.copy(policy)
    object.__setattr__(cloned, "etf_cap", Decimal("0.99"))
    object.__setattr__(
        cloned,
        "evidence_sha256",
        hashlib.sha256(
            formula_module._policy_payload(
                {
                    field.name: getattr(cloned, field.name)
                    for field in dataclasses.fields(cloned)
                    if field.name not in {"evidence_sha256", "_token"}
                }
            )
        ).hexdigest(),
    )
    with pytest.raises(FormulaError, match="not derived"):
        formula_module.require_verified_analyst_policy(cloned)


def test_checked_in_source_authority_is_canonical_zero_access_and_not_rebindable(
    tmp_path, monkeypatch
) -> None:
    assert not hasattr(formula_module, "_EXTERNALLY_REGISTERED_SOURCE_SHA256")
    for kind in ResearchSourceKind:
        with pytest.raises(FormulaError, match="zero-access"):
            formula_module.require_registered_source_bytes(kind, b"synthetic")

    fake_module = tmp_path / "fake-package" / "formulas.py"
    authority = fake_module.parent / "specs" / "research_source_authority.json"
    authority.parent.mkdir(parents=True)
    fake_module.write_text("# path fixture\n", encoding="utf-8")
    authority.write_bytes(
        canonical_json_bytes(
            {
                "schema": "arv2-research-source-authority-v2",
                "authority_mode": "append_only",
                "authority_id": "caller-controlled",
                "entries": [hashlib.sha256(b"synthetic").hexdigest()],
            }
        )
    )
    monkeypatch.setattr(formula_module, "__file__", str(fake_module))
    with pytest.raises(FormulaError, match="must remain zero-access"):
        formula_module.require_registered_source_bytes(
            ResearchSourceKind.HOLDINGS, b"synthetic"
        )


def test_holdings_public_authority_is_zero_access_but_parser_is_strict() -> None:
    source = _holdings_source(_holding("a", "1"))
    parsed = holdings_module._parse_holdings_source(source)
    holdings_module._validate_holdings_book(parsed[7], parsed[8])
    with pytest.raises(HoldingsError, match="zero-access"):
        build_verified_holdings_snapshot(source_bytes=source)

    unsorted = _holdings_source(
        _holding("b", "0.5"), _holding("a", "0.5"), sort_rows=False
    )
    with pytest.raises(HoldingsError, match="position-sorted"):
        holdings_module._parse_holdings_source(unsorted)
    bad_book = holdings_module._parse_holdings_source(
        _holdings_source(_holding("a", "0.8"), declared="0.8")
    )
    with pytest.raises(HoldingsError, match="reconcile"):
        holdings_module._validate_holdings_book(bad_book[7], bad_book[8])


def test_holdings_parser_uses_nyse_sessions_not_utc_calendar_dates() -> None:
    boundary = holdings_module._parse_holdings_source(
        _holdings_source(
            _holding("a", "1"),
            effective_at="2026-08-25T00:30:00+00:00",
            effective_session="2026-08-24",
        )
    )
    assert boundary[5] == "2026-08-24"
    assert holdings_module._derived_lag_sessions(
        SimpleNamespace(effective_session="2026-08-24"), "2026-08-25"
    ) == 1
    wrong = _holdings_source(
        _holding("a", "1"),
        effective_at="2026-08-25T00:30:00+00:00",
        effective_session="2026-08-25",
    )
    with pytest.raises(HoldingsError, match="latest NYSE session"):
        holdings_module._parse_holdings_source(wrong)
    with pytest.raises(HoldingsError, match="session open"):
        holdings_module._decision_session(
            holdings_module._instant(
                "2026-08-25T13:00:00+00:00", "decision_at"
            )
        )


def test_holdings_parser_preserves_complete_unmapped_book() -> None:
    parsed = holdings_module._parse_holdings_source(
        _holdings_source(
            _holding("a", "0.989"), _holding("b", "0.011", mapped=False)
        )
    )
    holdings_module._validate_holdings_book(parsed[7], parsed[8])
    assert sum((row.weight for row in parsed[8]), Decimal("0")) == 1
    assert parsed[8][1].mapping_state is MappingState.UNMAPPED
    assert parsed[8][1].security_id is None


def test_stock_score_public_authority_is_zero_access_but_parser_is_strict() -> None:
    policy = _policy()
    records = [
        {"security_id": "sec-a", "state": "signal", "value": "2"},
        {"security_id": "sec-b", "state": "structural_zero", "value": None},
    ]
    source = _stock_score_source(records, policy=policy)
    parsed = holdings_module._parse_stock_score_source(source, policy=policy)
    assert [row.security_id for row in parsed[-1]] == ["sec-a", "sec-b"]
    with pytest.raises(HoldingsError, match="zero-access"):
        build_verified_stock_score_evidence(source_bytes=source, policy=policy)
    with pytest.raises(HoldingsError, match="verified holdings evidence"):
        weighted_stock_score(
            object(), stock_score_evidence=object(), policy=policy
        )


@pytest.mark.parametrize(
    ("records", "match"),
    [
        (
            [
                {"security_id": "sec-a", "state": "signal", "value": "1"},
                {"security_id": "sec-a", "state": "signal", "value": "2"},
            ],
            "uniquely",
        ),
        ([{"security_id": "sec-a", "state": "missing", "value": None}], "refuse"),
        ([{"security_id": "sec-a", "state": "invalid", "value": None}], "refuse"),
        ([{"security_id": "sec-a", "state": "signal", "value": "4.1"}], "clip"),
        ([{"security_id": "sec-a", "state": "signal", "value": "0"}], "nonzero"),
    ],
)
def test_non_authoritative_stock_score_parser_rejects_unsafe_rows(
    records, match
) -> None:
    policy = _policy()
    with pytest.raises(HoldingsError, match=match):
        holdings_module._parse_stock_score_source(
            _stock_score_source(records, policy=policy), policy=policy
        )


def test_cost_and_terminal_public_authority_is_zero_access_but_parsers_are_strict() -> None:
    policy = _policy()
    cost_source = _trade_cost_source("sec-1", policy=policy)
    terminal_source = _terminal_source("sec-1")
    parsed_cost = cost_module._parse_trade_cost_source(cost_source)
    parsed_terminal = cost_module._parse_terminal_source(terminal_source)
    assert parsed_cost[3] == "sec-1" and parsed_cost[-1] == Decimal("10000")
    assert parsed_terminal[2] == "sec-1" and parsed_terminal[6] == Decimal("100")
    with pytest.raises(CostModelError, match="zero-access"):
        verify_trade_cost_evidence(source_bytes=cost_source, policy=policy)
    with pytest.raises(CostModelError, match="zero-access"):
        verify_terminal_exit_evidence(source_bytes=terminal_source)


def test_cost_internal_sum_is_permutation_invariant_under_high_dynamic_range() -> None:
    values = (Decimal("1e49"), Decimal("1"), Decimal("3"))
    expected = cost_module._stable_decimal_sum(values)
    with localcontext() as context:
        context.prec = 6
        assert {
            cost_module._stable_decimal_sum(permutation)
            for permutation in itertools.permutations(values)
        } == {expected}


def test_cross_section_and_nonempty_portfolio_are_zero_access_until_rank_rule_is_frozen() -> None:
    policy = _policy()
    source = _cross_section_source(
        [
            {
                "etf_security_id": "etf-unranked",
                "peer_rank": "100",
                "inverse_volatility": "1",
            }
        ],
        policy=policy,
    )
    with pytest.raises(PortfolioConstructionError, match="zero-access"):
        build_verified_cross_section_evidence(source_bytes=source, policy=policy)
    forged = object.__new__(portfolio_module.VerifiedCrossSectionEvidence)
    object.__setattr__(forged, "source_bytes", source)
    object.__setattr__(
        forged, "_token", portfolio_module._VERIFIED_CROSS_SECTION_TOKEN
    )
    with pytest.raises(PortfolioConstructionError, match="source authority.*zero-access"):
        portfolio_module.require_verified_cross_section_evidence(
            forged, policy=policy
        )
    with pytest.raises(PortfolioConstructionError, match="zero-access"):
        PortfolioCandidate("etf-unranked", object(), object(), object(), policy)
    empty = construct_portfolio((), policy=policy)
    assert not empty.allocations and empty.cash_weight == 1


def test_classification_public_authority_is_zero_access_and_membership_cannot_dilute() -> None:
    holdings = SimpleNamespace(
        etf_security_id="etf-cluster",
        evidence_epoch_id=EPOCH,
        snapshot=SimpleNamespace(
            effective_at="2026-08-24T20:00:00+00:00",
            available_at="2026-08-25T12:00:00+00:00",
        ),
        snapshot_content_sha256="a" * 64,
        decision_at=DECISION,
    )
    valid = _classification_source(holdings)
    parsed = portfolio_module._parse_classification_source(valid)
    assert parsed[2] == "etf-cluster"
    with pytest.raises(PortfolioConstructionError, match="zero-access"):
        build_verified_classification_evidence(source_bytes=valid)
    with pytest.raises(PortfolioConstructionError, match="non-dilutable"):
        portfolio_module._parse_classification_source(
            _classification_source(holdings, cluster_fraction="0.5")
        )
    with pytest.raises(PortfolioConstructionError, match="reconcile to one"):
        portfolio_module._parse_classification_source(
            _classification_source(holdings, sector_fraction="0.999999")
        )


@pytest.mark.parametrize(
    ("public_date", "expected_session"),
    [
        ("2026-08-25", "2026-08-27"),
        ("2026-08-28", "2026-09-01"),
        ("2026-09-04", "2026-09-09"),
    ],
)
def test_date_only_event_waits_two_exchange_sessions(
    public_date: str, expected_session: str
) -> None:
    result = derive_event_availability(evidence_id="clock-1", public_date=public_date)
    assert result.eligible_session == expected_session
    assert result.quality is AvailabilityQuality.DATE_ONLY_TWO_SESSION_DELAY


def test_exact_event_uses_first_open_strictly_after_publication() -> None:
    assert derive_event_availability(
        evidence_id="clock-1", public_at="2026-08-25T12:00:00+00:00"
    ).eligible_session == "2026-08-25"
    assert derive_event_availability(
        evidence_id="clock-2", public_at="2026-08-25T13:30:00+00:00"
    ).eligible_session == "2026-08-26"
    assert derive_event_availability(
        evidence_id="clock-3", public_at="2026-11-27T18:01:00+00:00"
    ).eligible_session == "2026-11-30"


def test_inconsistent_clocks_are_hard_refusals() -> None:
    with pytest.raises(AvailabilityError, match="effective_at"):
        prove_timing_order(
            effective_at="2026-08-25T14:00:00+00:00",
            provider_published_at="2026-08-25T13:00:00+00:00",
            available_at="2026-08-25T13:30:00+00:00",
            ingested_at="2026-08-25T14:30:00+00:00",
        )


def test_availability_requires_exactly_one_evidence_clock() -> None:
    """The two evidence forms are mutually exclusive, and that guard was
    untested. Supplying both an instant and a date would let a caller silently
    pick the less conservative rule; supplying neither reaches the calendar
    with no clock. Both must refuse."""
    with pytest.raises(AvailabilityError, match="exactly one"):
        derive_event_availability(
            evidence_id="clock-1",
            public_at="2026-08-25T12:00:00+00:00",
            public_date="2026-08-25",
        )
    with pytest.raises(AvailabilityError, match="exactly one"):
        derive_event_availability(evidence_id="clock-1")


def test_prove_timing_order_refuses_each_out_of_order_clock() -> None:
    """The published>available and available>ingested branches were untested;
    only the effective>published branch had coverage."""
    with pytest.raises(AvailabilityError, match="provider_published_at cannot follow"):
        prove_timing_order(
            effective_at="2026-08-25T13:00:00+00:00",
            provider_published_at="2026-08-25T14:00:00+00:00",
            available_at="2026-08-25T13:30:00+00:00",
            ingested_at="2026-08-25T14:30:00+00:00",
        )
    with pytest.raises(AvailabilityError, match="available_at cannot follow"):
        prove_timing_order(
            effective_at="2026-08-25T13:00:00+00:00",
            provider_published_at="2026-08-25T13:15:00+00:00",
            available_at="2026-08-25T14:30:00+00:00",
            ingested_at="2026-08-25T14:00:00+00:00",
        )


def test_measured_pre_2013_rows_are_factual_but_quarantined() -> None:
    assert MEASURED_ACCEPTED_COUNTS == {2011: 5, 2012: 24_296, 2013: 28_609}
    early = classify_provider_era("2012-12-31")
    assert early.era is ProviderEra.PRE_2013_BACKFILL_UNVERIFIED
    assert not early.admissible
    assert classify_provider_era("2013-01-01").admissible
