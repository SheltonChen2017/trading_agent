"""Synthetic/offline tests for bounded Insider Buying IB-3D diagnostics.

The tests consume only fixture-created, exactly replayed IB-3A and IB-3C
artifacts.  They grant no canonical score/rank/seed, external-data, outcome,
ETF, QC, broker, deployment, or trading authority.
"""
from __future__ import annotations

import ast
from dataclasses import fields
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import research.insider_buying as insider_package
from data.hashing import hash_payload
from research.insider_buying import (
    form4_stock_signal_buyer_cluster_diagnostics as cluster_module,
)
from research.insider_buying import (
    form4_stock_signal_formula_diagnostics as formula_module,
)
from research.insider_buying import (
    form4_stock_signal_normalization_diagnostics as normalization_module,
)
from research.insider_buying import (
    form4_stock_signal_seed_diagnostics as seed_module,
)


FORMULA_BUILDER_COMMIT = "c" * 40
NORMALIZATION_BUILDER_COMMIT = "d" * 40
SEED_BUILDER_COMMIT = "e" * 40
CLUSTER_BUILDER_COMMIT = "f" * 40
EVALUATION_SESSION = "2026-09-18-synthetic-buyer-cluster-session"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "insider_buying"
    / "form4_stock_signal_buyer_cluster_diagnostics.py"
)
EXPECTED_PUBLIC_EXPORTS = (
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY",
    "MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS",
    "MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS",
    "MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS",
    "Form4StockSignalBuyerClusterDiagnosticRow",
    "Form4StockSignalBuyerClusterDiagnostics",
    "Form4StockSignalBuyerClusterDiagnosticsError",
    "Form4StockSignalBuyerClusterIdentity",
    "Form4StockSignalBuyerClusterOutcome",
    "build_form4_stock_signal_buyer_cluster_diagnostics",
)
AUTHORITY_FIELDS = (
    "role_normalization_verified",
    "role_normalization_authorized",
    "ib2_completion_authorized",
    "official_security_master_compatibility_verified",
    "qc_symbol_id_mapping_verified",
    "authenticated_amendment_supersession_verified",
    "calendar_session_mapping_verified",
    "point_in_time_issuer_identity_verified",
    "point_in_time_reporting_owner_identity_verified",
    "point_in_time_security_identity_verified",
    "point_in_time_transaction_identity_verified",
    "ordinary_equity_classification_verified",
    "canonical_filter_authorized",
    "deduplication_authorized",
    "lot_aggregation_authorized",
    "post_aggregation_minimum_gate_authorized",
    "canonical_stock_score_authorized",
    "cross_sectional_normalization_authorized",
    "seed_signal_authorized",
    "sec_access_authorized",
    "provider_access_authorized",
    "outcomes_authorized",
    "etf_construction_authorized",
    "qc_execution_authorized",
    "broker_access_authorized",
    "deployment_authorized",
    "trading_authorized",
)
AUTHORITY_PAYLOAD_KEYS = (
    "population_is_caller_declared",
    "canonical_population_verified",
    "role_ids_are_caller_declared",
    "buyer_ids_are_caller_declared",
    *AUTHORITY_FIELDS,
    "authorized_outcome_looks",
    "consumed_outcome_looks",
)


def _stock_key(index: int) -> tuple[str, str, str]:
    return (
        f"{index + 1:010d}",
        f"security-{index:05d}",
        "share-class-common",
    )


def _source_id(sequence: int) -> str:
    return f"{sequence:064x}"


def _signal(
    index: int,
    buyer_ids: tuple[str, ...],
    purchase_value_usd: Decimal,
    *,
    formula_builder_commit: str = FORMULA_BUILDER_COMMIT,
):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    events = tuple(
        formula_module.build_form4_stock_signal_fixture_event(
            source_event_id=_source_id(6_000_000 + index * 100 + position),
            issuer_cik=issuer_cik,
            security_id=security_id,
            share_class_id=share_class_id,
            buyer_id=buyer_id,
            transaction_date=date(2026, 9, 18) - timedelta(days=position),
            purchase_value_usd=purchase_value_usd,
            age_trading_days=position,
            normalized_role_ids=("director",),
        )
        for position, buyer_id in enumerate(buyer_ids)
    )
    source = formula_module.build_form4_stock_signal_formula_diagnostics(
        events,
        builder_git_commit=formula_builder_commit,
    )
    observation = (
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik=issuer_cik,
            security_id=security_id,
            share_class_id=share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition
                .INCLUDE_SIGNAL
            ),
            source_diagnostics=source,
        )
    )
    return observation, source


def _zero(index: int):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        disposition=(
            normalization_module.Form4StockSignalNormalizationDisposition
            .INCLUDE_STRUCTURAL_ZERO
        ),
        synthetic_source_id=_source_id(7_000_000 + index),
    )


def _excluded(index: int, disposition):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        disposition=disposition,
        synthetic_source_id=_source_id(8_000_000 + index),
    )


def _seed_case(
    signal_specs: tuple[tuple[tuple[str, ...], Decimal], ...],
    *,
    extra_observations: tuple = (),
):
    pairs = tuple(
        _signal(index, buyer_ids, purchase_value_usd)
        for index, (buyer_ids, purchase_value_usd) in enumerate(signal_specs)
    )
    observations = tuple(pair[0] for pair in pairs)
    sources = tuple(pair[1] for pair in pairs)
    usable_padding = tuple(
        _zero(index)
        for index in range(
            len(signal_specs),
            normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES,
        )
    )
    normalized = (
        normalization_module.build_form4_stock_signal_normalization_diagnostics(
            observations + usable_padding + extra_observations,
            evaluation_session=EVALUATION_SESSION,
            builder_git_commit=NORMALIZATION_BUILDER_COMMIT,
        )
    )
    seed = seed_module.build_form4_stock_signal_seed_diagnostics(
        normalized,
        builder_git_commit=SEED_BUILDER_COMMIT,
    )
    return seed, sources


def _available_case():
    return _seed_case(
        (
            (("buyer-00000-a", "buyer-00000-b"), Decimal("1000000")),
            (("buyer-00001-a", "buyer-00001-b"), Decimal("1000000")),
        )
    )


def _one_candidate_case():
    return _seed_case(
        (
            (("buyer-00000-same", "buyer-00000-same"), Decimal("1000000")),
            (("buyer-00001-a", "buyer-00001-b"), Decimal("1000000")),
        )
    )


def _three_signal_case():
    return _seed_case(
        (
            (("buyer-00000-a", "buyer-00000-b"), Decimal("1000000")),
            (("buyer-00001-a", "buyer-00001-b"), Decimal("1000000")),
            (("buyer-00002-a", "buyer-00002-b"), Decimal("50000")),
        )
    )


def _build(seed, sources):
    return cluster_module.build_form4_stock_signal_buyer_cluster_diagnostics(
        seed,
        sources,
        builder_git_commit=CLUSTER_BUILDER_COMMIT,
    )


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


class _TextSubclass(str):
    pass


def test_ib3d_policy_and_hash_are_frozen_to_the_owner_approval():
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION == (
        "INSETF-IB3D-FORM4-STOCK-SIGNAL-BUYER-CLUSTER-DIAGNOSTICS-v1"
    )
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY == (
        "exact-available-ib3c-parent-and-one-exact-ib3a-source-per-signal-row"
    )
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY == (
        "preserve-ib3c-selection-and-require-buyer-breadth-at-least-two"
    )
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY == (
        "caller-declared-unverified"
    )
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH == 2
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS == 2
    assert cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH == (
        "452a875f354530d5db1a55c1ea0d8cd9"
        "3fecca4f39904c26e616c09cb9050273"
    )
    assert cluster_module.Form4StockSignalBuyerClusterOutcome.AVAILABLE.value == (
        "available"
    )
    assert (
        cluster_module.Form4StockSignalBuyerClusterOutcome
        .UNAVAILABLE_INSUFFICIENT_BUYER_CLUSTER_SEEDS.value
        == "unavailable_insufficient_buyer_cluster_seeds"
    )
    assert hash_payload(cluster_module._policy_payload()) == (
        cluster_module.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH
    )
    assert "diagnostic_rank" not in {
        field.name
        for field in fields(
            cluster_module.Form4StockSignalBuyerClusterDiagnosticRow
        )
    }
    cluster_module._require_frozen_policy()


@pytest.mark.parametrize(
    ("name", "changed"),
    (
        (
            "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION",
            "INSETF-IB3D-ALTERED",
        ),
        ("FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY", "trust-caller"),
        (
            "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY",
            "replace-base-selection",
        ),
        (
            "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY",
            "verified-identities",
        ),
        ("FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH", 1),
        ("FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS", 1),
        ("MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS", 9_999),
        ("MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS", 9_999),
        ("MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS", 127),
    ),
)
def test_coherent_policy_rebinding_fails_closed(monkeypatch, name, changed):
    monkeypatch.setattr(cluster_module, name, changed)
    monkeypatch.setattr(
        cluster_module,
        "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH",
        hash_payload(cluster_module._policy_payload()),
    )
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
        match="frozen IB-3D buyer-cluster policy",
    ):
        cluster_module._require_frozen_policy()


@pytest.mark.parametrize(
    ("target", "name", "changed"),
    (
        (cluster_module, "_MAX_CLUSTER_DECIMAL_DIGITS", 49),
        (cluster_module, "_MAX_CLUSTER_DECIMAL_ABS_EXPONENT", 2_047),
        (seed_module, "MAX_FORM4_STOCK_SIGNAL_SEED_ROWS", 9_999),
        (
            seed_module,
            "FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION",
            "INSETF-IB3C-ALTERED",
        ),
        (seed_module, "FORM4_STOCK_SIGNAL_SEED_POLICY_HASH", "0" * 64),
        (formula_module, "MAX_FORM4_STOCK_SIGNAL_EVENTS", 9_999),
        (
            formula_module,
            "FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION",
            "INSETF-IB3A-ALTERED",
        ),
        (formula_module, "FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH", "1" * 64),
    ),
)
def test_private_and_upstream_policy_rebinding_fails_closed(
    monkeypatch,
    target,
    name,
    changed,
):
    monkeypatch.setattr(target, name, changed)
    monkeypatch.setattr(
        cluster_module,
        "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH",
        hash_payload(cluster_module._policy_payload()),
    )
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
        match="frozen IB-3D buyer-cluster policy",
    ):
        cluster_module._require_frozen_policy()


def test_available_preserves_base_selection_and_adds_only_the_buyer_gate():
    seed, sources = _available_case()
    assert seed.outcome is seed_module.Form4StockSignalSeedOutcome.AVAILABLE

    result = _build(seed, sources)

    assert result.outcome is (
        cluster_module.Form4StockSignalBuyerClusterOutcome.AVAILABLE
    )
    assert result.base_selected_seed_count == 2
    assert result.buyer_breadth_gate_member_count == 2
    assert result.cluster_qualified_seed_count == 2
    assert result.selected_cluster_seed_count == 2
    assert sum(row.cluster_qualified_candidate for row in result.rows) == 2
    assert sum(
        row.diagnostic_cluster_seed_selected is True for row in result.rows
    ) == 2

    seed_rows = {row.row_id: row for row in seed.rows}
    source_by_key = {
        (source.issuer_cik, source.security_id, source.share_class_id): source
        for source in sources
    }
    assert len(result.rows) == len(seed.rows)
    assert tuple(row.parent_seed_row_id for row in result.rows) == tuple(
        row.row_id for row in seed.rows
    )
    for row in result.rows:
        parent = seed_rows[row.parent_seed_row_id]
        assert (
            row.issuer_cik,
            row.security_id,
            row.share_class_id,
            row.disposition,
            row.included_in_percentile_denominator,
            row.exact_ranking_value,
            row.meets_top_decile_cutoff,
            row.positive_signal_candidate,
            row.base_diagnostic_seed_selected,
        ) == (
            parent.issuer_cik,
            parent.security_id,
            parent.share_class_id,
            parent.disposition,
            parent.included_in_percentile_denominator,
            parent.exact_ranking_value,
            parent.meets_top_decile_cutoff,
            parent.positive_signal_candidate,
            parent.diagnostic_seed_selected,
        )
        source = source_by_key.get(
            (row.issuer_cik, row.security_id, row.share_class_id)
        )
        if source is None:
            assert row.source_formula_diagnostics_id is None
            assert row.source_formula_payload_hash is None
            assert row.source_breadth_id is None
            assert row.source_breadth_hash is None
            assert row.buyer_breadth is None
            assert row.meets_minimum_buyer_breadth is None
            assert row.cluster_qualified_candidate is False
            assert row.diagnostic_cluster_seed_selected is False
        else:
            assert row.source_formula_diagnostics_id == source.identity.diagnostics_id
            assert row.source_formula_payload_hash == hash_payload(
                formula_module.Form4StockSignalFormulaDiagnostics.to_payload(source)
            )
            assert row.source_breadth_id == source.breadth.breadth_id
            assert row.source_breadth_hash == hash_payload(
                formula_module.Form4StockSignalBreadthDiagnostics.to_payload(
                    source.breadth
                )
            )
            assert row.buyer_breadth == 2
            assert row.meets_minimum_buyer_breadth is True
            assert row.cluster_qualified_candidate is True
            assert row.diagnostic_cluster_seed_selected is True


def test_fewer_than_two_candidates_is_named_atomic_unavailability():
    seed, sources = _one_candidate_case()
    repeated = sources[0]
    assert repeated.breadth.buyer_breadth == 1
    assert len(repeated.events) == 2

    result = _build(seed, sources)

    assert result.outcome is (
        cluster_module.Form4StockSignalBuyerClusterOutcome
        .UNAVAILABLE_INSUFFICIENT_BUYER_CLUSTER_SEEDS
    )
    assert result.base_selected_seed_count == 2
    assert result.buyer_breadth_gate_member_count == 1
    assert result.cluster_qualified_seed_count == 1
    assert result.selected_cluster_seed_count is None
    assert sum(row.cluster_qualified_candidate for row in result.rows) == 1
    assert all(
        row.diagnostic_cluster_seed_selected is None for row in result.rows
    )


def test_zero_candidates_is_unavailable_without_partial_selection():
    seed, sources = _seed_case(
        (
            (("buyer-00000-same", "buyer-00000-same"), Decimal("1000000")),
            (("buyer-00001-same", "buyer-00001-same"), Decimal("1000000")),
        )
    )

    result = _build(seed, sources)

    assert result.cluster_qualified_seed_count == 0
    assert result.selected_cluster_seed_count is None
    assert all(not row.cluster_qualified_candidate for row in result.rows)
    assert all(
        row.diagnostic_cluster_seed_selected is None for row in result.rows
    )


def test_three_exact_cutoff_ties_remain_selected_after_the_buyer_gate():
    seed, sources = _seed_case(
        (
            (("buyer-00000-a", "buyer-00000-b"), Decimal("1000000")),
            (("buyer-00001-a", "buyer-00001-b"), Decimal("1000000")),
            (("buyer-00002-a", "buyer-00002-b"), Decimal("1000000")),
        )
    )
    assert seed.target_count == 2
    assert seed.top_decile_member_count == 3
    assert seed.selected_seed_count == 3

    result = _build(seed, sources)

    assert result.outcome is cluster_module.Form4StockSignalBuyerClusterOutcome.AVAILABLE
    assert result.cluster_qualified_seed_count == 3
    assert result.selected_cluster_seed_count == 3
    assert sum(
        row.diagnostic_cluster_seed_selected is True for row in result.rows
    ) == 3


def test_high_breadth_unselected_stock_never_becomes_a_cluster_candidate():
    seed, sources = _three_signal_case()
    base_selected = {
        row.security_id
        for row in seed.rows
        if row.diagnostic_seed_selected is True
    }
    assert base_selected == {"security-00000", "security-00001"}
    assert sources[2].breadth.buyer_breadth == 2

    result = _build(seed, sources)
    third = next(row for row in result.rows if row.security_id == "security-00002")

    assert result.buyer_breadth_gate_member_count == 3
    assert result.cluster_qualified_seed_count == 2
    assert third.base_diagnostic_seed_selected is False
    assert third.meets_minimum_buyer_breadth is True
    assert third.cluster_qualified_candidate is False
    assert third.diagnostic_cluster_seed_selected is False


def test_every_parent_row_and_rejection_state_is_retained():
    extras = (
        _excluded(
            100,
            normalization_module.Form4StockSignalNormalizationDisposition
            .EXCLUDE_INELIGIBLE,
        ),
        _excluded(
            101,
            normalization_module.Form4StockSignalNormalizationDisposition
            .EXCLUDE_MISSING,
        ),
    )
    seed, sources = _seed_case(
        (
            (("buyer-00000-a", "buyer-00000-b"), Decimal("1000000")),
            (("buyer-00001-a", "buyer-00001-b"), Decimal("1000000")),
        ),
        extra_observations=extras,
    )

    result = _build(seed, sources)

    assert len(result.rows) == len(seed.rows) == 22
    assert {row.parent_seed_row_id for row in result.rows} == {
        row.row_id for row in seed.rows
    }
    excluded = [
        row
        for row in result.rows
        if row.disposition
        in {
            normalization_module.Form4StockSignalNormalizationDisposition
            .EXCLUDE_INELIGIBLE,
            normalization_module.Form4StockSignalNormalizationDisposition
            .EXCLUDE_MISSING,
        }
    ]
    assert len(excluded) == 2
    assert all(row.exact_ranking_value is None for row in excluded)
    assert all(not row.cluster_qualified_candidate for row in excluded)


def test_source_permutation_is_canonical_and_result_invariant():
    seed, sources = _three_signal_case()

    forward = _build(seed, sources)
    reverse = _build(seed, tuple(reversed(sources)))

    assert forward == reverse
    assert tuple(
        (source.issuer_cik, source.security_id, source.share_class_id)
        for source in forward.source_formula_diagnostics
    ) == tuple(sorted(_stock_key(index) for index in range(3)))


def test_identity_binds_parent_sources_counts_and_output_inventory():
    seed, sources = _three_signal_case()
    result = _build(seed, sources)
    identity = result.identity

    assert identity.upstream_seed_diagnostics_id == seed.identity.seed_diagnostics_id
    assert identity.upstream_seed_payload_hash == hash_payload(
        seed_module.Form4StockSignalSeedDiagnostics.to_payload(seed)
    )
    assert identity.upstream_seed_diagnostics_version == (
        seed.identity.diagnostics_version
    )
    assert identity.upstream_seed_policy_hash == seed.identity.policy_hash
    assert identity.upstream_seed_builder_git_commit == (
        seed.identity.builder_git_commit
    )
    assert identity.upstream_seed_row_inventory_hash == (
        seed.identity.row_inventory_hash
    )
    assert identity.row_count == len(seed.rows)
    assert identity.signal_source_count == len(sources)
    assert identity.source_event_count == sum(len(source.events) for source in sources)
    assert identity.source_formula_inventory_hash == hash_payload(
        [
            formula_module.Form4StockSignalFormulaDiagnostics.to_payload(source)
            for source in result.source_formula_diagnostics
        ]
    )
    assert identity.base_selected_seed_count == 2
    assert identity.buyer_breadth_gate_member_count == 3
    assert identity.cluster_qualified_seed_count == 2
    assert identity.selected_cluster_seed_count == 2
    assert identity.row_inventory_hash == hash_payload(
        [
            cluster_module.Form4StockSignalBuyerClusterDiagnosticRow.to_payload(row)
            for row in result.rows
        ]
    )
    assert identity.buyer_cluster_diagnostics_id == (
        "form4-stock-signal-buyer-cluster-diagnostics-"
        + hash_payload(identity.lineage_payload())[:16]
    )


def test_payload_schemas_and_field_order_are_exact():
    result = _build(*_available_case())
    row_payload = result.rows[0].to_payload()
    identity_payload = result.identity.to_payload()
    result_payload = result.to_payload()

    assert tuple(row_payload) == (
        "parent_seed_row_id",
        "issuer_cik",
        "security_id",
        "share_class_id",
        "disposition",
        "included_in_percentile_denominator",
        "exact_ranking_value",
        "meets_top_decile_cutoff",
        "positive_signal_candidate",
        "base_diagnostic_seed_selected",
        "source_formula_diagnostics_id",
        "source_formula_payload_hash",
        "source_breadth_id",
        "source_breadth_hash",
        "buyer_breadth",
        "meets_minimum_buyer_breadth",
        "cluster_qualified_candidate",
        "diagnostic_cluster_seed_selected",
        "stock_score",
        "rank",
        "seed_selected",
        *AUTHORITY_PAYLOAD_KEYS,
        "row_id",
    )
    assert tuple(identity_payload) == (
        "diagnostics_version",
        "policy_hash",
        "builder_git_commit",
        "evaluation_session",
        "upstream_seed_diagnostics_id",
        "upstream_seed_payload_hash",
        "upstream_seed_diagnostics_version",
        "upstream_seed_policy_hash",
        "upstream_seed_builder_git_commit",
        "upstream_seed_row_inventory_hash",
        "row_count",
        "signal_source_count",
        "source_event_count",
        "source_formula_inventory_hash",
        "base_selected_seed_count",
        "buyer_breadth_gate_member_count",
        "cluster_qualified_seed_count",
        "selected_cluster_seed_count",
        "row_inventory_hash",
        "outcome",
        *AUTHORITY_PAYLOAD_KEYS,
        "buyer_cluster_diagnostics_id",
    )
    assert tuple(result_payload) == (
        "identity",
        "source_seed_diagnostics",
        "source_formula_diagnostics",
        "rows",
        "outcome",
        "base_selected_seed_count",
        "buyer_breadth_gate_member_count",
        "cluster_qualified_seed_count",
        "selected_cluster_seed_count",
        "stock_score",
        "ranking",
        "seed_selection",
        *AUTHORITY_PAYLOAD_KEYS,
    )


def test_local_builder_commit_changes_only_local_identity():
    seed, sources = _available_case()
    first = _build(seed, sources)
    second = (
        cluster_module.build_form4_stock_signal_buyer_cluster_diagnostics(
            seed,
            sources,
            builder_git_commit="a" * 40,
        )
    )

    assert first.rows == second.rows
    assert first.source_seed_diagnostics == second.source_seed_diagnostics
    assert first.source_formula_diagnostics == second.source_formula_diagnostics
    assert first.identity.builder_git_commit != second.identity.builder_git_commit
    assert (
        first.identity.buyer_cluster_diagnostics_id
        != second.identity.buyer_cluster_diagnostics_id
    )


@pytest.mark.parametrize("case", ("missing", "extra", "duplicate", "alternate"))
def test_exact_one_to_one_signal_source_inventory_is_required(case):
    seed, sources = _three_signal_case()
    _, extra = _signal(
        100,
        ("buyer-extra-a", "buyer-extra-b"),
        Decimal("1000000"),
    )
    alternate = formula_module.build_form4_stock_signal_formula_diagnostics(
        sources[0].events,
        builder_git_commit="a" * 40,
    )
    supplied = {
        "missing": sources[:-1],
        "extra": sources + (extra,),
        "duplicate": sources + (sources[0],),
        "alternate": (alternate, *sources[1:]),
    }[case]

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        _build(seed, supplied)


def test_even_an_unselected_signal_requires_its_exact_ib3a_source():
    seed, sources = _three_signal_case()
    assert next(
        row
        for row in seed.rows
        if row.security_id == "security-00002"
    ).diagnostic_seed_selected is False

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        _build(seed, sources[:2])


def test_same_stock_and_score_with_different_buyer_ids_is_not_the_bound_source():
    seed, sources = _available_case()
    _, alternate = _signal(
        0,
        ("buyer-alternate-a", "buyer-alternate-b"),
        Decimal("1000000"),
    )
    assert alternate.raw_stock_score_diagnostic == (
        sources[0].raw_stock_score_diagnostic
    )
    assert alternate.identity.diagnostics_id != sources[0].identity.diagnostics_id
    assert hash_payload(alternate.to_payload()) != hash_payload(
        sources[0].to_payload()
    )

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
        match="exactly match IB-3B signal lineage",
    ):
        _build(seed, (alternate, sources[1]))


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("issuer_cik", "9999999999"),
        (
            "upstream_diagnostics_id",
            "form4-stock-signal-formula-diagnostics-0000000000000000",
        ),
        ("upstream_payload_hash", "0" * 64),
        ("synthetic_source_id", "1" * 64),
        ("upstream_builder_git_commit", "0" * 40),
        ("upstream_diagnostics_version", "altered-version"),
        ("upstream_numeric_policy_hash", "2" * 64),
        ("raw_stock_score_diagnostic", Decimal("1")),
    ),
)
def test_each_explicit_ib3a_to_ib3b_join_field_fails_closed(
    field_name,
    replacement,
):
    seed, sources = _available_case()
    source = cluster_module._replay_formula_source(sources[0])
    observation = next(
        item
        for item in seed.source_normalization.observations
        if item.stock_key == source.stock_key
    )
    forged = _forge(observation, **{field_name: replacement})

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
        match="exactly match IB-3B signal lineage",
    ):
        cluster_module._validate_signal_join(forged, source)


def test_unavailable_ib3c_parent_is_refused():
    seed, sources = _seed_case(
        ((("buyer-only-a", "buyer-only-b"), Decimal("1000000")),)
    )
    assert seed.outcome is (
        seed_module.Form4StockSignalSeedOutcome
        .UNAVAILABLE_INSUFFICIENT_POSITIVE_SEEDS
    )

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
        match="AVAILABLE IB-3C",
    ):
        _build(seed, sources)


def test_parent_and_formula_sources_are_exactly_replayed_and_detached():
    seed, sources = _available_case()
    result = _build(seed, sources)

    assert result.source_seed_diagnostics is not seed
    assert all(
        replayed is not supplied
        for replayed, supplied in zip(result.source_formula_diagnostics, sources)
    )
    object.__setattr__(seed.identity, "evaluation_session", "caller-mutated")
    object.__setattr__(sources[0].breadth, "buyer_breadth", 1)

    assert result.identity.evaluation_session == EVALUATION_SESSION
    assert result.source_formula_diagnostics[0].breadth.buyer_breadth == 2
    cluster_module.Form4StockSignalBuyerClusterDiagnostics.__post_init__(
        result,
        cluster_module._RESULT_FACTORY_TOKEN,
    )


@pytest.mark.parametrize("source_kind", ("seed", "formula"))
def test_final_source_seal_detects_mutation_during_evaluation(
    monkeypatch,
    source_kind,
):
    seed, sources = _available_case()
    real_build_identity = cluster_module._build_identity

    def mutate_caller_then_build(*args, **kwargs):
        built = real_build_identity(*args, **kwargs)
        if source_kind == "seed":
            object.__setattr__(
                seed.identity,
                "evaluation_session",
                "mutated-during-build",
            )
        else:
            object.__setattr__(sources[0].breadth, "buyer_breadth", 1)
        return built

    monkeypatch.setattr(cluster_module, "_build_identity", mutate_caller_then_build)
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        _build(seed, sources)


@pytest.mark.parametrize("tamper", ("seed_enum", "formula_count", "breadth_count"))
def test_value_equal_cross_types_and_source_mutation_are_refused(tamper):
    seed, sources = _available_case()
    if tamper == "seed_enum":
        supplied_seed = _forge(seed, outcome=seed.outcome.value)
        supplied_sources = sources
    elif tamper == "formula_count":
        changed_identity = _forge(sources[0].identity, fixture_event_count=True)
        supplied_seed = seed
        supplied_sources = (_forge(sources[0], identity=changed_identity), sources[1])
    else:
        changed_breadth = _forge(sources[0].breadth, buyer_breadth=Decimal(2))
        supplied_seed = seed
        supplied_sources = (_forge(sources[0], breadth=changed_breadth), sources[1])

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        _build(supplied_seed, supplied_sources)


def test_builder_requires_exact_input_types_and_commit_shape():
    seed, sources = _available_case()
    invalid_calls = (
        (object(), sources, CLUSTER_BUILDER_COMMIT),
        (seed, list(sources), CLUSTER_BUILDER_COMMIT),
        (seed, (object(),), CLUSTER_BUILDER_COMMIT),
        (seed, sources, "F" * 40),
        (seed, sources, "f" * 39),
        (seed, sources, _TextSubclass("f" * 40)),
    )

    for supplied_seed, supplied_sources, commit in invalid_calls:
        with pytest.raises(
            cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
        ):
            cluster_module.build_form4_stock_signal_buyer_cluster_diagnostics(
                supplied_seed,
                supplied_sources,
                builder_git_commit=commit,
            )


def test_resource_bounds_fail_before_unbounded_source_replay():
    seed, sources = _available_case()
    too_many_rows = _forge(
        seed,
        rows=(seed.rows[0],)
        * (cluster_module.MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS + 1),
    )
    too_many_events = _forge(
        sources[0],
        events=(sources[0].events[0],)
        * (cluster_module.MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS + 1),
    )

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        _build(too_many_rows, sources)
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        _build(seed, (too_many_events, sources[1]))


def test_aggregate_event_bound_refuses_before_any_formula_replay(monkeypatch):
    _, sources = _available_case()
    oversized = tuple(
        _forge(
            source,
            events=(source.events[0],) * 6_000,
        )
        for source in sources
    )
    replay_calls = 0

    def counted_replay(value):
        nonlocal replay_calls
        replay_calls += 1
        return cluster_module._FormulaReplay(
            diagnostics=value,
            payload_hash=f"{replay_calls:064x}",
        )

    monkeypatch.setattr(cluster_module, "_replay_formula_source", counted_replay)
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
        match="aggregate IB-3A source events",
    ):
        cluster_module._replay_formula_sources(oversized)
    assert replay_calls == 0


def test_zero_authority_provenance_look_counts_and_canonical_nulls():
    available = _build(*_available_case())
    unavailable = _build(*_one_candidate_case())

    for result in (available, unavailable):
        for value in (result, result.identity, *result.rows):
            assert value.population_is_caller_declared is True
            assert value.canonical_population_verified is False
            assert value.role_ids_are_caller_declared is True
            assert value.buyer_ids_are_caller_declared is True
            assert all(getattr(value, name) is False for name in AUTHORITY_FIELDS)
            assert value.authorized_outcome_looks == 0
            assert value.consumed_outcome_looks == 0
        assert result.stock_score is None
        assert result.ranking is None
        assert result.seed_selection is None
        assert all(row.stock_score is None for row in result.rows)
        assert all(row.rank is None for row in result.rows)
        assert all(row.seed_selected is None for row in result.rows)


@pytest.mark.parametrize(
    ("scope", "field_name", "replacement"),
    (
        ("row", "stock_score", "forged"),
        ("row", "rank", 1),
        ("row", "seed_selected", True),
        ("result", "stock_score", "forged"),
        ("result", "ranking", ("forged",)),
        ("result", "seed_selection", ("TRADE",)),
    ),
)
def test_authority_provenance_and_canonical_guards_are_load_bearing(
    scope,
    field_name,
    replacement,
):
    result = _build(*_available_case())
    if scope == "row":
        changed = _forge(result.rows[0], **{field_name: replacement})
        validator = (
            cluster_module.Form4StockSignalBuyerClusterDiagnosticRow.__post_init__
        )
        token = cluster_module._ROW_FACTORY_TOKEN
    elif scope == "identity":
        changed = _forge(result.identity, **{field_name: replacement})
        validator = cluster_module.Form4StockSignalBuyerClusterIdentity.__post_init__
        token = cluster_module._IDENTITY_FACTORY_TOKEN
    else:
        changed = _forge(result, **{field_name: replacement})
        validator = cluster_module.Form4StockSignalBuyerClusterDiagnostics.__post_init__
        token = cluster_module._RESULT_FACTORY_TOKEN

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        validator(changed, token)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("buyer_ids_are_caller_declared", False),
        ("trading_authorized", True),
        ("consumed_outcome_looks", True),
    ),
)
@pytest.mark.parametrize("scope", ("row", "identity", "result"))
def test_zero_authority_properties_are_load_bearing(
    monkeypatch,
    scope,
    field_name,
    replacement,
):
    result = _build(*_available_case())
    monkeypatch.setattr(
        cluster_module._ZeroAuthority,
        field_name,
        property(lambda _self: replacement),
    )
    if scope == "row":
        value = result.rows[0]
        validator = (
            cluster_module.Form4StockSignalBuyerClusterDiagnosticRow.__post_init__
        )
        token = cluster_module._ROW_FACTORY_TOKEN
    elif scope == "identity":
        value = result.identity
        validator = cluster_module.Form4StockSignalBuyerClusterIdentity.__post_init__
        token = cluster_module._IDENTITY_FACTORY_TOKEN
    else:
        value = result
        validator = cluster_module.Form4StockSignalBuyerClusterDiagnostics.__post_init__
        token = cluster_module._RESULT_FACTORY_TOKEN

    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        validator(value, token)


def test_rows_identity_and_result_refuse_direct_construction():
    result = _build(*_available_case())

    for value in (result.rows[0], result.identity, result):
        kwargs = {field.name: getattr(value, field.name) for field in fields(value)}
        with pytest.raises(
            cluster_module.Form4StockSignalBuyerClusterDiagnosticsError,
            match="factory-created",
        ):
            type(value)(**kwargs)


def test_stale_row_and_identity_hashes_and_result_replay_are_refused():
    result = _build(*_available_case())
    changed_row = _forge(
        result.rows[0],
        cluster_qualified_candidate=False,
    )
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        cluster_module.Form4StockSignalBuyerClusterDiagnosticRow.__post_init__(
            changed_row,
            cluster_module._ROW_FACTORY_TOKEN,
        )

    changed_identity = _forge(
        result.identity,
        buyer_breadth_gate_member_count=True,
    )
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        cluster_module.Form4StockSignalBuyerClusterIdentity.__post_init__(
            changed_identity,
            cluster_module._IDENTITY_FACTORY_TOKEN,
        )

    changed_result = _forge(
        result,
        rows=(changed_row, *result.rows[1:]),
    )
    with pytest.raises(
        cluster_module.Form4StockSignalBuyerClusterDiagnosticsError
    ):
        cluster_module.Form4StockSignalBuyerClusterDiagnostics.__post_init__(
            changed_result,
            cluster_module._RESULT_FACTORY_TOKEN,
        )


def test_result_serialization_ignores_shadowed_nested_serializers():
    result = _build(*_available_case())
    expected = result.to_payload()

    object.__setattr__(result.identity, "to_payload", lambda: {"forged": True})
    object.__setattr__(
        result.identity,
        "lineage_payload",
        lambda: {"trading_authorized": True},
    )
    object.__setattr__(result.rows[0], "to_payload", lambda: {"forged": True})
    object.__setattr__(
        result.rows[0],
        "lineage_payload",
        lambda: {"seed_selected": True},
    )
    object.__setattr__(
        result.rows[0],
        "authority_payload",
        lambda: {"trading_authorized": True},
    )
    object.__setattr__(
        result.source_seed_diagnostics,
        "to_payload",
        lambda: {"forged": True},
    )
    object.__setattr__(
        result.source_formula_diagnostics[0],
        "to_payload",
        lambda: {"forged": True},
    )
    object.__setattr__(
        result,
        "authority_payload",
        lambda: {"trading_authorized": True, "seed_selection": ["TRADE"]},
    )

    assert result.to_payload() == expected


def test_public_exports_and_package_boundary_are_explicit():
    assert tuple(cluster_module.__all__) == EXPECTED_PUBLIC_EXPORTS
    for name in EXPECTED_PUBLIC_EXPORTS:
        assert getattr(insider_package, name) is getattr(cluster_module, name)
        assert name in insider_package.__all__


def test_module_import_boundary_is_offline_and_dependency_bounded():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)

    assert not imports.intersection(
        {
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "quantconnect",
            "pandas",
            "numpy",
            "assistant",
            "backtest",
            "execution",
            "risk",
        }
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "eval", "exec", "float", "open"}
        for node in ast.walk(tree)
    )
