"""Dangerous-direction tests for owner-frozen SI-3E-P1A percentiles."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
import inspect
from pathlib import Path
import subprocess

import pytest

from data.hashing import hash_payload
import research.short_interest_etf as canonical_short_interest_package
import research.short_interest_etf.stock_percentile as stock_percentile_module
from research.short_interest_etf.preregistration import (
    PREREGISTRATION,
    SHORT_INTEREST_BLUEPRINT_PATH,
    SHORT_INTEREST_BLUEPRINT_SHA256,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
)
from research.short_interest_etf.stock_covering import (
    build_pit_stock_covering_scores,
)
from research.short_interest_etf.stock_features import ExactRational
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
)
from research.short_interest_etf.stock_percentile import (
    STOCK_PERCENTILE_POLICY,
    STOCK_PERCENTILE_POLICY_ID,
    STOCK_PERCENTILE_POLICY_SHA256,
    STOCK_PERCENTILE_PROJECTION_ID,
    StockPercentileBatch,
    StockPercentileCandidateState,
    StockPercentileDisposition,
    StockPercentileError,
    StockPercentilePolicy,
    build_stock_percentile_projection,
    require_stock_percentile_policy,
)
from research.short_interest_etf.stock_score_order import (
    SCORE_ORDER_BATCH_SCHEMA_VERSION,
    SCORE_ORDER_INVENTORY_ID,
    SCORE_ORDER_SCHEMA_VERSION,
    StockScoreOrderBatch,
    StockScoreOrderRole,
    build_stock_score_order_inventory,
)
from tests.test_short_interest_stock_normalization import (
    _fresh_non_affine_scores,
    _scores,
    _single_sector_specs,
    _single_sector_scores,
)
from tests.test_short_interest_stock_score_order import (
    _four_cycle_inventory,
    _inventory,
)


@lru_cache(maxsize=1)
def _projection() -> StockPercentileBatch:
    return build_stock_percentile_projection(_inventory())


@lru_cache(maxsize=1)
def _projection_rows() -> tuple[StockPercentileDisposition, ...]:
    return _projection().dispositions


def _clone_disposition(
    disposition: StockPercentileDisposition,
    **changes,
) -> StockPercentileDisposition:
    clone = object.__new__(StockPercentileDisposition)
    for name in disposition.__dataclass_fields__:
        object.__setattr__(clone, name, getattr(disposition, name))
    for name, value in changes.items():
        object.__setattr__(clone, name, value)
    return clone


def _clone_batch(batch: StockPercentileBatch, **changes) -> StockPercentileBatch:
    clone = object.__new__(StockPercentileBatch)
    for name in batch.__dataclass_fields__:
        object.__setattr__(clone, name, getattr(batch, name))
    for name, value in changes.items():
        if name == "dispositions":
            name = "_dispositions"
        object.__setattr__(clone, name, value)
    return clone


def _clone_source_batch(
    batch: StockScoreOrderBatch,
    **changes,
) -> StockScoreOrderBatch:
    clone = object.__new__(StockScoreOrderBatch)
    for name in batch.__dataclass_fields__:
        object.__setattr__(clone, name, getattr(batch, name))
    for name, value in changes.items():
        if name == "dispositions":
            name = "_dispositions"
        object.__setattr__(clone, name, value)
    return clone


def _contains_float(value) -> bool:
    if type(value) is float:
        return True
    if type(value) is dict:
        return any(_contains_float(item) for item in value.values())
    if type(value) is list:
        return any(_contains_float(item) for item in value)
    return False


def _count_key(value, target: str) -> int:
    if type(value) is dict:
        return sum(key == target for key in value) + sum(
            _count_key(item, target) for item in value.values()
        )
    if type(value) is list:
        return sum(_count_key(item, target) for item in value)
    return 0


def _state_value(state: StockPercentileCandidateState) -> str:
    return state.value


def test_percentile_policy_is_exact_content_addressed_owner_freeze():
    payload = STOCK_PERCENTILE_POLICY.to_payload()
    assert set(payload) == {
        "arithmetic",
        "blueprint_path",
        "blueprint_sha256",
        "boundary_comparison",
        "candidate_semantic",
        "covering_candidate_maximum_pressure_percentile",
        "covering_role_minimum_percentile",
        "independent_return_evaluation_required",
        "investability_screen_applied",
        "mechanical_percentile_complement_required",
        "minimum_percentile_population",
        "minimum_threshold_classification_population",
        "normalization_policy_sha256",
        "outcome_access_authorized",
        "owner_directive_commit",
        "owner_directive_date",
        "owner_directive_id",
        "owner_directive_path",
        "owner_directive_sha256",
        "percentile_formula",
        "policy_id",
        "population_scope",
        "preregistration_sha256",
        "pressure_candidate_minimum_percentile",
        "production_authoritative",
        "research_gate_sha256",
        "return_effect_symmetry_assumed",
        "seed_selection_authorized",
        "source_score_order_batch_schema_version",
        "source_score_order_inventory_id",
        "source_score_order_row_schema_version",
        "tie_policy",
    }
    assert type(STOCK_PERCENTILE_POLICY) is StockPercentilePolicy
    assert STOCK_PERCENTILE_POLICY.sha256 == hash_payload(payload)
    assert STOCK_PERCENTILE_POLICY.sha256 == STOCK_PERCENTILE_POLICY_SHA256
    assert STOCK_PERCENTILE_POLICY_SHA256 == (
        "0e521b8275c5f813c11b578e1b9a6aefa3c8ba13ae57a53ad32393682efcd180"
    )
    assert require_stock_percentile_policy(STOCK_PERCENTILE_POLICY) == (
        STOCK_PERCENTILE_POLICY_SHA256
    )
    assert payload["policy_id"] == STOCK_PERCENTILE_POLICY_ID
    assert payload["owner_directive_id"] == (
        "si3ep1a-owner-approval-recorded-2026-09-26"
    )
    assert payload["owner_directive_date"] == "2026-09-26"
    assert payload["blueprint_path"] == SHORT_INTEREST_BLUEPRINT_PATH
    assert payload["blueprint_sha256"] == SHORT_INTEREST_BLUEPRINT_SHA256
    assert payload["preregistration_sha256"] == PREREGISTRATION.sha256
    assert payload["research_gate_sha256"] == SHORT_INTEREST_RESEARCH_GATE_SHA256
    assert payload["normalization_policy_sha256"] == (
        STOCK_NORMALIZATION_POLICY.sha256
    )
    assert payload["source_score_order_inventory_id"] == SCORE_ORDER_INVENTORY_ID
    assert payload["source_score_order_row_schema_version"] == (
        SCORE_ORDER_SCHEMA_VERSION
    )
    assert payload["source_score_order_batch_schema_version"] == (
        SCORE_ORDER_BATCH_SCHEMA_VERSION
    )
    assert payload["percentile_formula"] == "(2*L+E)/(2*N)"
    assert payload["minimum_percentile_population"] == 1
    assert payload["minimum_threshold_classification_population"] == 10
    assert payload["pressure_candidate_minimum_percentile"] == {
        "denominator": 10,
        "numerator": 9,
    }
    assert payload["covering_candidate_maximum_pressure_percentile"] == {
        "denominator": 10,
        "numerator": 1,
    }
    assert payload["covering_role_minimum_percentile"] == {
        "denominator": 10,
        "numerator": 9,
    }
    assert payload["boundary_comparison"] == "inclusive"
    assert payload["tie_policy"] == "exact_equivalence_group_indivisible"
    assert payload["arithmetic"] == "exact_reduced_rational_no_float_no_rounding"
    assert payload["population_scope"] == "structural_scoreable_population_only"
    assert payload["candidate_semantic"] == "threshold_candidate_not_seed"
    assert payload["mechanical_percentile_complement_required"] is True
    assert payload["independent_return_evaluation_required"] is True
    assert payload["return_effect_symmetry_assumed"] is False
    assert payload["investability_screen_applied"] is False
    assert payload["seed_selection_authorized"] is False
    assert payload["outcome_access_authorized"] is False
    assert payload["production_authoritative"] is False


def test_percentile_policy_binds_committed_verbatim_owner_approval():
    payload = STOCK_PERCENTILE_POLICY.to_payload()
    directive_path = (
        "docs/Strategy Description/SHORT_INTEREST_OWNER_DECISIONS_2026-09-26.md"
    )
    directive_commit = "c329d6f9aa616ea48776d6fbe75c36413b81d19b"
    assert payload["owner_directive_path"] == directive_path
    assert payload["owner_directive_commit"] == directive_commit
    assert payload["owner_directive_sha256"] == (
        "0172439871e3ace82cd0fe5fcd3526c7b20989185b10e334d169e16c50427bc3"
    )
    repository_root = Path(__file__).resolve().parents[1]
    committed_bytes = subprocess.run(
        ["git", "show", f"{directive_commit}:{directive_path}"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    ).stdout
    assert sha256(committed_bytes).hexdigest() == payload["owner_directive_sha256"]
    assert (repository_root / directive_path).read_bytes() == committed_bytes
    directive = committed_bytes.decode("utf-8")
    assert (
        "> yes this works. Approved. Freeze the proposed defaults and implement "
        "SI-2B offline, then complete the round with one push to the Short Interest "
        "lane only. With one change, tho. candidate lookbacks first"
    ) in directive
    assert "**20, 60, 120, and 252 trading sessions**" in directive
    assert "There is no selected lookback winner at this stage." in directive
    assert "equivalently `(2*L+E)/(2*N)`." in directive
    assert "Inclusive pressure `p >= 0.90` and covering `p <= 0.10`" in directive
    assert "Keep whole tie groups; never split or force exactly 10%" in directive
    assert "Fewer than 10 eligible stocks produces no seeds" in directive


@pytest.mark.parametrize(
    "field,value",
    (
        ("owner_directive_path", "docs/another-owner-record.md"),
        ("owner_directive_commit", "0" * 40),
        ("owner_directive_sha256", "0" * 64),
    ),
)
def test_percentile_policy_refuses_rebound_owner_provenance(field, value):
    forged = object.__new__(StockPercentilePolicy)
    for name in StockPercentilePolicy.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(STOCK_PERCENTILE_POLICY, name))
    object.__setattr__(forged, field, value)
    with pytest.raises(StockPercentileError, match="wrong owner directive"):
        require_stock_percentile_policy(forged)
    with pytest.raises(StockPercentileError, match="wrong owner directive"):
        forged.to_payload()


@pytest.mark.parametrize(
    (
        "role",
        "lower",
        "equal",
        "higher",
        "total",
        "expected_role_percentile",
        "expected_pressure_percentile",
        "expected_state",
        "expected_candidate",
    ),
    (
        (
            StockScoreOrderRole.PRESSURE,
            0,
            1,
            0,
            1,
            Fraction(1, 2),
            Fraction(1, 2),
            StockPercentileCandidateState.INSUFFICIENT_SCOREABLE_POPULATION,
            None,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            0,
            1,
            8,
            9,
            Fraction(1, 18),
            Fraction(1, 18),
            StockPercentileCandidateState.INSUFFICIENT_SCOREABLE_POPULATION,
            None,
        ),
        (
            StockScoreOrderRole.COVERING,
            8,
            1,
            0,
            9,
            Fraction(17, 18),
            Fraction(1, 18),
            StockPercentileCandidateState.INSUFFICIENT_SCOREABLE_POPULATION,
            None,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            0,
            1,
            9,
            10,
            Fraction(1, 20),
            Fraction(1, 20),
            StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE,
            False,
        ),
        (
            StockScoreOrderRole.COVERING,
            9,
            1,
            0,
            10,
            Fraction(19, 20),
            Fraction(1, 20),
            StockPercentileCandidateState.THRESHOLD_CANDIDATE,
            True,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            8,
            2,
            0,
            10,
            Fraction(9, 10),
            Fraction(9, 10),
            StockPercentileCandidateState.THRESHOLD_CANDIDATE,
            True,
        ),
        (
            StockScoreOrderRole.COVERING,
            8,
            2,
            0,
            10,
            Fraction(9, 10),
            Fraction(1, 10),
            StockPercentileCandidateState.THRESHOLD_CANDIDATE,
            True,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            7,
            3,
            0,
            10,
            Fraction(17, 20),
            Fraction(17, 20),
            StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE,
            False,
        ),
        (
            StockScoreOrderRole.COVERING,
            7,
            3,
            0,
            10,
            Fraction(17, 20),
            Fraction(3, 20),
            StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE,
            False,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            16,
            4,
            0,
            20,
            Fraction(9, 10),
            Fraction(9, 10),
            StockPercentileCandidateState.THRESHOLD_CANDIDATE,
            True,
        ),
        (
            StockScoreOrderRole.COVERING,
            16,
            4,
            0,
            20,
            Fraction(9, 10),
            Fraction(1, 10),
            StockPercentileCandidateState.THRESHOLD_CANDIDATE,
            True,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            15,
            5,
            0,
            20,
            Fraction(7, 8),
            Fraction(7, 8),
            StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE,
            False,
        ),
        (
            StockScoreOrderRole.PRESSURE,
            0,
            20,
            0,
            20,
            Fraction(1, 2),
            Fraction(1, 2),
            StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE,
            False,
        ),
    ),
)
def test_exact_count_kernel_freezes_formula_ties_small_n_and_direction(
    role,
    lower,
    equal,
    higher,
    total,
    expected_role_percentile,
    expected_pressure_percentile,
    expected_state,
    expected_candidate,
):
    role_percentile, pressure_percentile, state, candidate = (
        stock_percentile_module._evaluate_order_counts(
            role=role,
            strictly_lower_count=lower,
            equal_count=equal,
            strictly_higher_count=higher,
            scoreable_count=total,
        )
    )
    assert role_percentile.to_fraction() == expected_role_percentile
    assert pressure_percentile.to_fraction() == expected_pressure_percentile
    assert state is expected_state
    assert candidate is expected_candidate


@pytest.mark.parametrize(
    ("lower", "equal", "higher", "total"),
    (
        (0, 0, 0, 0),
        (-1, 1, 10, 10),
        (0, 1, 8, 10),
        (False, 1, 8, 9),
    ),
)
def test_exact_count_kernel_refuses_invalid_or_zero_populations(
    lower,
    equal,
    higher,
    total,
):
    with pytest.raises(StockPercentileError, match="REFUSED"):
        stock_percentile_module._evaluate_order_counts(
            role=StockScoreOrderRole.PRESSURE,
            strictly_lower_count=lower,
            equal_count=equal,
            strictly_higher_count=higher,
            scoreable_count=total,
        )


def test_projection_recomputes_every_percentile_with_independent_fraction_oracle():
    source = _inventory()
    source_rows = source.dispositions
    rows = _projection_rows()
    assert len(rows) == len(source_rows)
    for source_row, row in zip(source_rows, rows, strict=True):
        assert row.source_score_order_disposition_sha256 == hash_payload(
            source_row.to_payload()
        )
        assert row.role is source_row.role
        if source_row.score is None:
            assert row.role_percentile is None
            assert row.pressure_percentile is None
            continue
        expected = Fraction(
            2 * source_row.strictly_lower_count + source_row.equal_count,
            2 * source_row.scoreable_count,
        )
        assert row.role_percentile.to_fraction() == expected
        expected_pressure = (
            expected
            if row.role is StockScoreOrderRole.PRESSURE
            else 1 - expected
        )
        assert row.pressure_percentile.to_fraction() == expected_pressure


def test_pressure_and_covering_are_exact_complements_and_opposite_tails():
    rows = _projection_rows()
    by_record = {}
    for row in rows:
        by_record.setdefault(row.source_covering_disposition_sha256, {})[
            row.role
        ] = row
    assert by_record
    pressure_candidates = set()
    covering_candidates = set()
    for pair in by_record.values():
        assert set(pair) == set(StockScoreOrderRole)
        pressure = pair[StockScoreOrderRole.PRESSURE]
        covering = pair[StockScoreOrderRole.COVERING]
        if pressure.role_percentile is None:
            assert covering.role_percentile is None
            continue
        assert (
            pressure.role_percentile.to_fraction()
            + covering.role_percentile.to_fraction()
            == 1
        )
        assert pressure.pressure_percentile == covering.pressure_percentile
        if pressure.threshold_candidate:
            pressure_candidates.add(pressure.event_id)
            assert pressure.pressure_percentile.to_fraction() >= Fraction(9, 10)
            assert covering.threshold_candidate is False
        if covering.threshold_candidate:
            covering_candidates.add(covering.event_id)
            assert covering.pressure_percentile.to_fraction() <= Fraction(1, 10)
            assert covering.role_percentile.to_fraction() >= Fraction(9, 10)
            assert pressure.threshold_candidate is False
    assert pressure_candidates
    assert covering_candidates
    assert pressure_candidates.isdisjoint(covering_candidates)


def test_every_exact_tie_group_is_indivisible_without_quota_fill():
    groups = {}
    for row in _projection_rows():
        if row.source_equivalence_group_sha256 is None:
            continue
        groups.setdefault(
            (row.role, row.source_equivalence_group_sha256), []
        ).append(row)
    assert any(len(group) > 1 for group in groups.values())
    for group in groups.values():
        assert len({item.role_percentile for item in group}) == 1
        assert len({item.candidate_state for item in group}) == 1
        assert len({item.threshold_candidate for item in group}) == 1


@pytest.mark.parametrize("top_tie_size", (4, 5))
def test_authenticated_public_boundary_ties_include_whole_groups_and_allow_empty_pressure(
    top_tie_size,
):
    # Alter authentic source facts, then traverse the complete normalization,
    # covering, order and percentile chain; no projected row is fabricated.
    specs = tuple(
        replace(spec, current_shares=50, prior_shares=200)
        if spec.index < 4
        else replace(spec, current_shares=200, prior_shares=100)
        if spec.index >= 20 - top_tie_size
        else spec
        for spec in _single_sector_specs(20)
    )
    projection = build_stock_percentile_projection(
        build_stock_score_order_inventory(
            build_pit_stock_covering_scores(_scores(specs))
        )
    )
    payload = projection.to_payload()
    pressure = [
        row for row in payload["dispositions"]
        if row["role"] == StockScoreOrderRole.PRESSURE.value
        and row["role_percentile"] is not None
    ]
    covering = [
        row for row in payload["dispositions"]
        if row["role"] == StockScoreOrderRole.COVERING.value
        and row["role_percentile"] is not None
    ]
    assert len(pressure) == len(covering) == 20
    assert {row["scoreable_count"] for row in (*pressure, *covering)} == {20}
    bottom_ids = {f"sec-si3c-{index:03d}" for index in range(4)}
    top_ids = {
        f"sec-si3c-{index:03d}" for index in range(20 - top_tie_size, 20)
    }
    pressure_top = [row for row in pressure if row["security_id"] in top_ids]
    covering_bottom = [row for row in covering if row["security_id"] in bottom_ids]
    expected_top = Fraction(9, 10) if top_tie_size == 4 else Fraction(7, 8)
    for row in pressure_top:
        assert row["equal_count"] == top_tie_size
        assert Fraction(**row["role_percentile"]) == expected_top
        assert row["threshold_candidate"] is (top_tie_size == 4)
    assert len({row["source_equivalence_group_sha256"] for row in pressure_top}) == 1
    for row in covering_bottom:
        assert row["equal_count"] == 4
        assert Fraction(**row["role_percentile"]) == Fraction(9, 10)
        assert Fraction(**row["pressure_percentile"]) == Fraction(1, 10)
        assert row["threshold_candidate"] is True
    assert len({row["source_equivalence_group_sha256"] for row in covering_bottom}) == 1
    pressure_candidate_ids = {
        row["security_id"] for row in pressure if row["threshold_candidate"]
    }
    covering_candidate_ids = {
        row["security_id"] for row in covering if row["threshold_candidate"]
    }
    assert pressure_candidate_ids == (top_ids if top_tie_size == 4 else set())
    assert covering_candidate_ids == bottom_ids
    assert Fraction(len(covering_candidate_ids), len(covering)) == Fraction(1, 5)
    assert Fraction(len(pressure_candidate_ids), len(pressure)) == (
        Fraction(1, 5) if top_tie_size == 4 else 0
    )


def test_terminal_rows_are_retained_without_percentile_or_classification():
    source_rows = _inventory().dispositions
    rows = _projection_rows()
    terminals = [
        (source, row)
        for source, row in zip(source_rows, rows, strict=True)
        if source.score is None
    ]
    assert terminals
    for source, row in terminals:
        assert row.role_percentile is None
        assert row.pressure_percentile is None
        assert row.threshold_candidate is None
        assert row.candidate_state is StockPercentileCandidateState.SOURCE_TERMINAL
        assert row.refusal_reasons == source.refusal_reasons


def test_empty_and_all_terminal_batches_do_not_divide_or_invent_candidates():
    empty_source = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(())
    )
    empty = build_stock_percentile_projection(empty_source)
    assert empty.dispositions == ()
    assert empty.disposition_count == 0
    assert empty.threshold_candidate_count == 0
    assert empty.percentile_calculation_count == 0
    assert empty.threshold_classification_evaluated_count == 0
    assert empty.release_count == 0
    empty_payload = empty.to_payload()
    assert empty_payload["source_batch_verification_required"] is False
    assert empty_payload["structural_percentile_calculation_applied"] is False
    assert empty_payload["structural_threshold_classification_applied"] is False

    terminal_source = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(_single_sector_scores(19))
    )
    terminal = build_stock_percentile_projection(terminal_source)
    assert len(terminal.dispositions) == len(terminal_source.dispositions)
    assert terminal.threshold_candidate_count == 0
    assert terminal.percentile_calculation_count == 0
    assert terminal.threshold_classification_evaluated_count == 0
    terminal_payload = terminal.to_payload()
    assert terminal_payload["structural_percentile_calculation_applied"] is False
    assert terminal_payload["structural_threshold_classification_applied"] is False
    assert all(
        item.candidate_state is StockPercentileCandidateState.SOURCE_TERMINAL
        for item in terminal.dispositions
    )


def test_multiple_releases_remain_separate_and_canonically_ordered():
    source = _four_cycle_inventory()
    projection = build_stock_percentile_projection(source)
    assert len(projection.dispositions) == len(source.dispositions)
    assert projection.release_count == 4
    assert [
        item.source_score_order_record_id for item in projection.dispositions
    ] == [item.score_order_record_id for item in source.dispositions]
    for row in projection.dispositions:
        if row.role_percentile is not None:
            assert row.scoreable_count == 20


def test_identity_hashes_bind_policy_source_row_and_complete_source_batch():
    row = next(item for item in _projection_rows() if item.score is not None)
    expected_slot = hash_payload(
        {
            "percentile_policy_sha256": STOCK_PERCENTILE_POLICY.sha256,
            "projection_id": STOCK_PERCENTILE_PROJECTION_ID,
            "source_score_order_slot_id": row.source_score_order_slot_id,
        }
    )
    expected_record = hash_payload(
        {
            "percentile_slot_id": expected_slot,
            "source_score_order_batch_sha256": (
                row.source_score_order_batch_sha256
            ),
            "source_score_order_disposition_sha256": (
                row.source_score_order_disposition_sha256
            ),
        }
    )
    assert row.percentile_slot_id == expected_slot
    assert row.percentile_record_id == expected_record
    assert row.sha256 == hash_payload(row.to_payload())
    assert _projection().sha256 == hash_payload(_projection().to_payload())


def test_payload_applies_only_structural_percentile_candidate_authority():
    payload = _projection().to_payload()
    assert set(payload) == {
        "authority",
        "broker_access_authorized",
        "candidate_semantic",
        "capital_authorized",
        "common_four_family_outcome_evaluation_authorized",
        "credential_access_authorized",
        "deployment_authorized",
        "disposition_count",
        "dispositions",
        "finra_access_authorized",
        "independent_return_evaluation_required",
        "integration_authorized",
        "investability_screen_applied",
        "licensed_row_access_authorized",
        "live_trading_authorized",
        "network_access_authorized",
        "operator_database_access_authorized",
        "outcome_access_authorized",
        "paper_trading_authorized",
        "percentile_calculation_count",
        "percentile_policy",
        "percentile_policy_applied",
        "percentile_policy_sha256",
        "percentile_projection_id",
        "population_scope",
        "production_authoritative",
        "provider_access_authorized",
        "qc_backtest_authorized",
        "qc_job_authorized",
        "qc_processing_authorized",
        "qc_research_inputs_execution_authority",
        "qc_upload_authorized",
        "ranking_decision_authorized",
        "release_count",
        "research_gate_sha256",
        "return_effect_symmetry_assumed",
        "scheduler_access_authorized",
        "schema_version",
        "seed_selection_authorized",
        "shared_holdout_access_authorized",
        "source_batch_verification_required",
        "source_data_request_authorized",
        "source_score_order_batch",
        "source_score_order_batch_sha256",
        "standalone_source_authenticated",
        "structural_percentile_calculation_applied",
        "structural_threshold_classification_applied",
        "threshold_candidate_count",
        "threshold_classification_evaluated_count",
        "trading_authority",
    }
    expected_row_keys = {
        "authority",
        "broker_access_authorized",
        "candidate_semantic",
        "candidate_state",
        "capital_authorized",
        "common_four_family_outcome_evaluation_authorized",
        "credential_access_authorized",
        "decision_at",
        "decision_session",
        "deployment_authorized",
        "equal_count",
        "event_id",
        "finra_access_authorized",
        "independent_return_evaluation_required",
        "integration_authorized",
        "investability_screen_applied",
        "licensed_row_access_authorized",
        "live_trading_authorized",
        "network_access_authorized",
        "normalization_cohort_sha256",
        "normalization_policy_sha256",
        "operator_database_access_authorized",
        "outcome_access_authorized",
        "paper_trading_authorized",
        "percentile_policy_applied",
        "percentile_policy_sha256",
        "percentile_projection_id",
        "percentile_record_id",
        "percentile_slot_id",
        "population_scope",
        "pressure_percentile",
        "production_authoritative",
        "provider_access_authorized",
        "qc_backtest_authorized",
        "qc_job_authorized",
        "qc_processing_authorized",
        "qc_research_inputs_execution_authority",
        "qc_upload_authorized",
        "ranking_decision_authorized",
        "refusal_reasons",
        "research_gate_sha256",
        "return_effect_symmetry_assumed",
        "revision_selection_state",
        "role",
        "role_percentile",
        "scheduler_access_authorized",
        "schema_version",
        "score",
        "scoreable_count",
        "security_id",
        "seed_selection_authorized",
        "selected_event_id",
        "settlement_date",
        "shared_holdout_access_authorized",
        "source_batch_verification_required",
        "source_covering_batch_sha256",
        "source_covering_disposition_sha256",
        "source_covering_record_id",
        "source_data_request_authorized",
        "source_disposition_sha256",
        "source_equivalence_group_sha256",
        "source_normalization_slot_id",
        "source_s1_outcome_sha256",
        "source_score_batch_sha256",
        "source_score_order_batch_sha256",
        "source_score_order_disposition_sha256",
        "source_score_order_record_id",
        "source_score_order_slot_id",
        "standalone_source_authenticated",
        "strictly_higher_count",
        "strictly_lower_count",
        "structural_percentile_calculation_applied",
        "structural_threshold_classification_applied",
        "threshold_candidate",
        "trading_authority",
    }
    assert all(set(item) == expected_row_keys for item in payload["dispositions"])
    assert payload["percentile_policy_applied"] is True
    assert payload["structural_percentile_calculation_applied"] is True
    assert payload["structural_threshold_classification_applied"] is True
    assert payload["population_scope"] == "structural_scoreable_population_only"
    assert payload["candidate_semantic"] == "threshold_candidate_not_seed"
    assert payload["investability_screen_applied"] is False
    assert payload["seed_selection_authorized"] is False
    assert payload["ranking_decision_authorized"] is False
    assert payload["outcome_access_authorized"] is False
    assert payload["qc_job_authorized"] is False
    assert payload["broker_access_authorized"] is False
    assert payload["paper_trading_authorized"] is False
    assert payload["live_trading_authorized"] is False
    assert payload["deployment_authorized"] is False
    assert payload["trading_authority"] is False
    assert payload["production_authoritative"] is False
    assert payload["independent_return_evaluation_required"] is True
    assert payload["return_effect_symmetry_assumed"] is False
    assert payload["source_score_order_batch_sha256"] == hash_payload(
        payload["source_score_order_batch"]
    )
    assert _count_key(payload, "source_score_order_batch") == 1
    assert payload["percentile_policy_sha256"] == hash_payload(
        payload["percentile_policy"]
    )
    assert not _contains_float(payload)
    assert all(
        item["percentile_projection_id"] == STOCK_PERCENTILE_PROJECTION_ID
        for item in payload["dispositions"]
    )
    forbidden_action_fields = {
        "allocation",
        "buy",
        "is_seed",
        "order",
        "portfolio_weight",
        "position",
        "seed_side",
        "sell",
        "trade",
    }
    stack = [payload]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            assert forbidden_action_fields.isdisjoint(current)
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)


def test_output_types_are_closed_frozen_and_input_is_exact():
    with pytest.raises(TypeError, match="constructed only"):
        StockPercentileDisposition()
    with pytest.raises(TypeError, match="constructed only"):
        StockPercentileBatch()
    with pytest.raises(FrozenInstanceError):
        STOCK_PERCENTILE_POLICY.minimum_threshold_classification_population = 9

    class BatchSubclass(StockScoreOrderBatch):
        pass

    with pytest.raises(StockPercentileError, match="exact StockScoreOrderBatch"):
        build_stock_percentile_projection(object.__new__(BatchSubclass))


def test_builder_has_one_argument_and_contract_is_not_package_root_exported():
    parameters = tuple(
        inspect.signature(build_stock_percentile_projection).parameters.values()
    )
    assert len(parameters) == 1
    assert parameters[0].name == "score_order_batch"
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[0].default is inspect.Parameter.empty
    for name in (
        "StockPercentilePolicy",
        "StockPercentileDisposition",
        "StockPercentileBatch",
        "build_stock_percentile_projection",
    ):
        assert name not in canonical_short_interest_package.__all__
        assert not hasattr(canonical_short_interest_package, name)


def test_builder_never_dispatches_source_serializers_properties_or_iterator(
    monkeypatch,
):
    source = _inventory()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("caller-owned source callback was dispatched")

    monkeypatch.setattr(StockScoreOrderBatch, "to_payload", forbidden)
    monkeypatch.setattr(StockScoreOrderBatch, "__iter__", forbidden)
    monkeypatch.setattr(
        StockScoreOrderBatch,
        "dispositions",
        property(forbidden),
    )
    result = build_stock_percentile_projection(source)
    assert object.__getattribute__(result, "disposition_count") == len(
        object.__getattribute__(source, "_dispositions")
    )


def test_post_build_source_mutation_cannot_change_detached_output():
    source = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(_fresh_non_affine_scores())
    )
    result = build_stock_percentile_projection(source)
    before = result.to_payload()
    source_row = next(
        item
        for item in object.__getattribute__(source, "_dispositions")
        if item.score is not None
    )
    object.__setattr__(
        source_row,
        "strictly_lower_count",
        source_row.strictly_lower_count + 1,
    )
    assert result.to_payload() == before


def test_returned_payload_is_detached_from_the_frozen_result():
    first = _projection().to_payload()
    original = deepcopy(first)
    first["dispositions"][0]["pressure_percentile"] = {
        "denominator": 1,
        "numerator": 0,
    }
    first["percentile_policy"]["minimum_threshold_classification_population"] = 9
    first["source_score_order_batch"]["dispositions"].reverse()
    assert _projection().to_payload() == original


def test_coherent_output_forgery_is_rejected_against_authenticated_source():
    projection = _projection()
    rows = projection.dispositions
    index = next(
        index
        for index, item in enumerate(rows)
        if item.role_percentile is not None
        and item.role_percentile != ExactRational(1, 2)
    )
    forged_row = _clone_disposition(
        rows[index],
        role_percentile=ExactRational(1, 2),
        pressure_percentile=ExactRational(1, 2),
        candidate_state=StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE,
        threshold_candidate=False,
    )
    forged_rows = rows[:index] + (forged_row,) + rows[index + 1 :]
    forged = _clone_batch(projection, dispositions=forged_rows)
    with pytest.raises(StockPercentileError, match="authenticated source"):
        forged.to_payload()


def test_exact_scalar_types_precede_source_equality_and_serialization():
    projection = _projection()
    scored_index = next(
        index
        for index, item in enumerate(projection.dispositions)
        if item.score is not None
    )
    scored = projection.dispositions[scored_index]

    class TextSubclass(str):
        pass

    attacks = (
        {"threshold_candidate": int(bool(scored.threshold_candidate))},
        {"equal_count": True},
        {"schema_version": TextSubclass(scored.schema_version)},
        {"authority": TextSubclass(scored.authority)},
    )
    for changes in attacks:
        forged_row = _clone_disposition(scored, **changes)
        rows = (
            projection.dispositions[:scored_index]
            + (forged_row,)
            + projection.dispositions[scored_index + 1 :]
        )
        forged_batch = _clone_batch(projection, dispositions=rows)
        with pytest.raises(StockPercentileError, match="REFUSED"):
            forged_batch.to_payload()


def test_behavior_bearing_score_is_rejected_before_equality_callback():
    row = next(item for item in _projection_rows() if item.score is not None)
    forged = _clone_disposition(row)

    class MutatingScore:
        def __eq__(self, _other):
            object.__setattr__(forged, "live_trading_authorized", True)
            return True

    object.__setattr__(forged, "score", MutatingScore())
    with pytest.raises(StockPercentileError, match="ExactRational"):
        forged.to_payload()
    assert forged.live_trading_authorized is False


def test_candidate_state_singleton_sabotage_is_detected_and_restored():
    row = _projection_rows()[0]
    state = row.candidate_state
    state_values = object.__getattribute__(state, "__dict__")
    original = dict.__getitem__(state_values, "_value_")
    try:
        object.__setattr__(state, "_value_", "forged_candidate_state")
        with pytest.raises(StockPercentileError, match="candidate state"):
            row.to_payload()
    finally:
        object.__setattr__(state, "_value_", original)
    assert row.to_payload()["candidate_state"] == original


def test_missing_duplicate_or_reordered_source_rows_fail_closed():
    source = _inventory()
    rows = object.__getattribute__(source, "_dispositions")
    attacks = (
        rows[:-1],
        rows + (rows[-1],),
        (rows[1], rows[0]) + rows[2:],
    )
    for dispositions in attacks:
        forged = _clone_source_batch(source, dispositions=dispositions)
        with pytest.raises(StockPercentileError, match="source score-order"):
            build_stock_percentile_projection(forged)


def test_mutated_policy_is_refused_without_changing_the_canonical_policy():
    forged = object.__new__(StockPercentilePolicy)
    for name in STOCK_PERCENTILE_POLICY.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(STOCK_PERCENTILE_POLICY, name))
    object.__setattr__(
        forged,
        "minimum_threshold_classification_population",
        9,
    )
    with pytest.raises(StockPercentileError, match="minimum classification"):
        require_stock_percentile_policy(forged)
    assert STOCK_PERCENTILE_POLICY.minimum_threshold_classification_population == 10


def test_scope_and_candidate_semantics_are_emitted_from_hashed_policy(monkeypatch):
    projection = _projection()
    before = projection.to_payload()
    monkeypatch.setattr(
        stock_percentile_module,
        "_POPULATION_SCOPE",
        "forged_population_scope",
    )
    monkeypatch.setattr(
        stock_percentile_module,
        "_CANDIDATE_SEMANTIC",
        "seed_candidate",
    )
    assert projection.to_payload() == before


def test_gate_callback_mutation_is_validated_after_the_callback(monkeypatch):
    source = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(_fresh_non_affine_scores())
    )
    source_row = next(
        item
        for item in object.__getattribute__(source, "_dispositions")
        if item.score is not None
    )

    def mutate_then_admit(_gate):
        object.__setattr__(
            source_row,
            "strictly_lower_count",
            source_row.strictly_lower_count + 1,
        )
        return SHORT_INTEREST_RESEARCH_GATE_SHA256

    monkeypatch.setattr(
        stock_percentile_module,
        "require_short_interest_research_gate",
        mutate_then_admit,
    )
    with pytest.raises(StockPercentileError, match="source score-order"):
        build_stock_percentile_projection(source)


def test_output_gate_callback_mutation_is_validated_after_callback(monkeypatch):
    projection = _projection()
    original_rows = projection.dispositions
    index = next(
        index
        for index, item in enumerate(original_rows)
        if type(item.threshold_candidate) is bool
    )
    mutable_row = _clone_disposition(original_rows[index])
    rows = original_rows[:index] + (mutable_row,) + original_rows[index + 1 :]
    mutable_batch = _clone_batch(projection, dispositions=rows)

    def mutate_then_admit(_gate):
        object.__setattr__(
            mutable_row,
            "threshold_candidate",
            not mutable_row.threshold_candidate,
        )
        return SHORT_INTEREST_RESEARCH_GATE_SHA256

    monkeypatch.setattr(
        stock_percentile_module,
        "require_short_interest_research_gate",
        mutate_then_admit,
    )
    with pytest.raises(StockPercentileError, match="authenticated source"):
        mutable_batch.to_payload()


def test_iterator_refuses_before_next_yield_after_row_sabotage():
    projection = build_stock_percentile_projection(_inventory())
    iterator = iter(projection)
    first = next(iterator)
    assert type(first) is StockPercentileDisposition
    rows = object.__getattribute__(projection, "_dispositions")
    target = rows[-1]
    object.__setattr__(target, "threshold_candidate", not target.threshold_candidate)
    with pytest.raises(StockPercentileError, match="REFUSED"):
        next(iterator)


def test_batch_metadata_drift_is_rejected_against_complete_output():
    projection = _projection()
    attacks = (
        {"disposition_count": projection.disposition_count - 1},
        {
            "percentile_calculation_count": (
                projection.percentile_calculation_count - 1
            )
        },
        {
            "threshold_classification_evaluated_count": (
                projection.threshold_classification_evaluated_count - 1
            )
        },
        {"threshold_candidate_count": projection.threshold_candidate_count + 1},
        {"release_count": projection.release_count + 1},
    )
    for changes in attacks:
        with pytest.raises(StockPercentileError, match="count"):
            _clone_batch(projection, **changes).to_payload()


def test_row_and_batch_payloads_reject_direct_authority_sabotage():
    projection = _projection()
    row = projection.dispositions[0]
    forged_row = _clone_disposition(row, live_trading_authorized=True)
    with pytest.raises(StockPercentileError, match="live_trading_authorized"):
        forged_row.to_payload()
    forged_batch = _clone_batch(projection, production_authoritative=True)
    with pytest.raises(StockPercentileError, match="non-production"):
        forged_batch.to_payload()


def test_percentile_row_binds_its_policy_gate_and_production_flag():
    """Each row must name the frozen percentile policy, the SI-0M gate and stay non-production."""
    scored = next(
        item for item in _projection_rows() if item.role_percentile is not None
    )
    cases = (
        ({"percentile_policy_sha256": "0" * 64}, "another percentile policy"),
        ({"research_gate_sha256": "0" * 64}, "not bound to the SI-0M gate"),
        ({"production_authoritative": True}, "must remain non-production"),
    )
    for changes, message in cases:
        with pytest.raises(StockPercentileError, match=message):
            _clone_disposition(scored, **changes).to_payload()


def test_percentile_batch_binds_its_policy_gate_and_structural_authority():
    """The batch must name the frozen policy, the SI-0M gate and the structural authority."""
    projection = _projection()
    cases = (
        ({"percentile_policy_sha256": "0" * 64}, "another percentile policy"),
        ({"research_gate_sha256": "0" * 64}, "not bound to the SI-0M gate"),
        (
            {"authority": "production_stock_percentile_batch"},
            "wrong structural authority",
        ),
    )
    for changes, message in cases:
        with pytest.raises(StockPercentileError, match=message):
            _clone_batch(projection, **changes).to_payload()


def test_percentile_row_identities_are_content_bound():
    """Slot and record identities must be recomputed, not trusted from the row."""
    scored = next(
        item for item in _projection_rows() if item.role_percentile is not None
    )
    with pytest.raises(StockPercentileError, match="wrong slot identity"):
        _clone_disposition(scored, percentile_slot_id="0" * 64).to_payload()
    with pytest.raises(StockPercentileError, match="wrong record identity"):
        _clone_disposition(scored, percentile_record_id="0" * 64).to_payload()


def test_terminal_percentile_row_cannot_be_given_a_percentile():
    """A terminal source row must never acquire an invented percentile."""
    rows = _projection_rows()
    terminal = next(item for item in rows if item.role_percentile is None)
    scored = next(item for item in rows if item.role_percentile is not None)
    forged = _clone_disposition(
        terminal,
        role_percentile=scored.role_percentile,
        pressure_percentile=scored.pressure_percentile,
    )
    with pytest.raises(StockPercentileError, match="cannot carry a percentile"):
        forged.to_payload()
