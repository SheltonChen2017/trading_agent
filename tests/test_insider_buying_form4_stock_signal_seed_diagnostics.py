"""Synthetic/offline tests for bounded Insider Buying IB-3C diagnostics.

The tests consume only fixture-created IB-3A and IB-3B artifacts.  They grant
no canonical score/rank/seed, external-data, outcome, ETF, QC, broker,
deployment, or trading authority.
"""
from __future__ import annotations

import ast
from dataclasses import fields
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import research.insider_buying as insider_package
from data.hashing import hash_payload
from research.insider_buying import (
    form4_stock_signal_formula_diagnostics as formula_module,
)
from research.insider_buying import (
    form4_stock_signal_normalization_diagnostics as normalization_module,
)
from research.insider_buying import (
    form4_stock_signal_seed_diagnostics as seed_module,
)


PARENT_BUILDER_COMMIT = "e" * 40
SEED_BUILDER_COMMIT = "f" * 40
EVALUATION_SESSION = "2026-09-18-synthetic-seed-session"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "insider_buying"
    / "form4_stock_signal_seed_diagnostics.py"
)
EXPECTED_MODULE_IMPORTS = {
    "__future__",
    "data.financial_primitives",
    "data.hashing",
    "dataclasses",
    "decimal",
    "enum",
    "re",
    "research.insider_buying.form4_stock_signal_normalization_diagnostics",
}
EXPECTED_PUBLIC_EXPORTS = (
    "FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS",
    "FORM4_STOCK_SIGNAL_SEED_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD",
    "FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE",
    "FORM4_STOCK_SIGNAL_SEED_TIE_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR",
    "FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR",
    "MAX_FORM4_STOCK_SIGNAL_SEED_ROWS",
    "MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS",
    "Form4StockSignalSeedDiagnosticRow",
    "Form4StockSignalSeedDiagnostics",
    "Form4StockSignalSeedDiagnosticsError",
    "Form4StockSignalSeedIdentity",
    "Form4StockSignalSeedOutcome",
    "build_form4_stock_signal_seed_diagnostics",
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


def _stock_key(index: int) -> tuple[str, str, str]:
    return (
        f"{index + 1:010d}",
        f"security-{index:05d}",
        "share-class-common",
    )


def _source_id(sequence: int) -> str:
    return f"{sequence:064x}"


def _signal(index: int, purchase_value_usd: Decimal):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    event = formula_module.build_form4_stock_signal_fixture_event(
        source_event_id=_source_id(3_000_000 + index),
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        buyer_id=f"buyer-{index:05d}",
        transaction_date=date(2026, 9, 18),
        purchase_value_usd=purchase_value_usd,
        age_trading_days=0,
        normalized_role_ids=("director",),
    )
    source = formula_module.build_form4_stock_signal_formula_diagnostics(
        (event,),
        builder_git_commit=PARENT_BUILDER_COMMIT,
    )
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        disposition=(
            normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        ),
        source_diagnostics=source,
    )


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
        synthetic_source_id=_source_id(4_000_000 + index),
    )


def _excluded(index: int, disposition):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        disposition=disposition,
        synthetic_source_id=_source_id(5_000_000 + index),
    )


def _parent(*observations):
    return normalization_module.build_form4_stock_signal_normalization_diagnostics(
        observations,
        evaluation_session=EVALUATION_SESSION,
        builder_git_commit=PARENT_BUILDER_COMMIT,
    )


def _build(parent):
    return seed_module.build_form4_stock_signal_seed_diagnostics(
        parent,
        builder_git_commit=SEED_BUILDER_COMMIT,
    )


def _distinct_signal_parent(count: int):
    return _parent(
        *(
            _signal(index, Decimal(50_000 * (index + 1)))
            for index in range(count)
        )
    )


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


def _rehash_row(row, **updates):
    changed = _forge(row, **updates)
    return _forge(changed, row_id=hash_payload(changed.lineage_payload()))


def _rehash_identity(identity, **updates):
    changed = _forge(identity, **updates)
    digest = hash_payload(changed.lineage_payload())
    return _forge(
        changed,
        seed_diagnostics_id=(
            "form4-stock-signal-seed-diagnostics-" + digest[:16]
        ),
    )


class _TextSubclass(str):
    pass


def test_ib3c_policy_and_hash_are_frozen_to_the_owner_approval():
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION == (
        "INSETF-IB3C-FORM4-STOCK-SIGNAL-SEED-DIAGNOSTICS-v1"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE == (
        "exact-ib3b-winsorized-stock-score-diagnostic"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD == (
        "descending-exact-value-kth-cutoff-no-ordinal-rank"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY == (
        "all-usable-eligible-names-including-structural-zero"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR == 1
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR == 10
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY == "ceil(N/10)"
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_TIE_POLICY == (
        "include-all-exact-cutoff-ties-never-split-by-stock-identity"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY == (
        "positive-include-signal-rows-only"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY == (
        "deferred-separate-not-implemented"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS == 2
    assert seed_module.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH == (
        "809a0072a1976463545674733305b8f4"
        "0b6e606da9e8da3b29c6ca6950f371f4"
    )
    assert seed_module.FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH == (
        "6705744ca9df421f4f96f955a3a4e850"
        "570806ac5b1059ad79488f36d14ffd04"
    )
    assert (
        normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY
        == "deferred"
    )
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY == (
        "deferred"
    )
    assert hash_payload(seed_module._policy_payload()) == (
        seed_module.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH
    )
    assert "diagnostic_rank" not in {
        field.name for field in fields(seed_module.Form4StockSignalSeedDiagnosticRow)
    }
    seed_module._require_frozen_policy()


@pytest.mark.parametrize(
    ("name", "changed"),
    (
        (
            "FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION",
            "INSETF-IB3C-ALTERED",
        ),
        ("FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE", "rounded-z-score"),
        ("FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD", "identity-tiebreak-rank"),
        ("FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY", "signals-only"),
        ("FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR", 2),
        ("FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR", 9),
        ("FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY", "floor(N/10)"),
        ("FORM4_STOCK_SIGNAL_SEED_TIE_POLICY", "split-by-stock-identity"),
        ("FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY", "all-members"),
        (
            "FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY",
            "implemented",
        ),
        ("FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS", 1),
        ("MAX_FORM4_STOCK_SIGNAL_SEED_ROWS", 9_999),
        ("MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS", 127),
        ("_MAX_SEED_DECIMAL_DIGITS", 51),
        ("_MAX_SEED_DECIMAL_ABS_EXPONENT", 2_049),
        ("MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS", 9_999),
        (
            "FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION",
            "INSETF-IB3B-ALTERED",
        ),
        (
            "FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH",
            "0" * 64,
        ),
    ),
)
def test_coherent_policy_rebinding_fails_closed(monkeypatch, name, changed):
    monkeypatch.setattr(seed_module, name, changed)
    monkeypatch.setattr(
        seed_module,
        "FORM4_STOCK_SIGNAL_SEED_POLICY_HASH",
        hash_payload(seed_module._policy_payload()),
    )
    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="frozen IB-3C seed policy",
    ):
        seed_module._require_frozen_policy()


def test_direct_policy_hash_corruption_fails_closed(monkeypatch):
    monkeypatch.setattr(
        seed_module,
        "FORM4_STOCK_SIGNAL_SEED_POLICY_HASH",
        "0" * 64,
    )
    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="frozen IB-3C seed policy",
    ):
        seed_module._require_frozen_policy()


@pytest.mark.parametrize(
    ("count", "expected_target"),
    ((20, 2), (21, 3), (29, 3), (30, 3)),
)
def test_ceil_top_decile_count_boundaries(count, expected_target):
    result = _build(_distinct_signal_parent(count))

    assert result.outcome is seed_module.Form4StockSignalSeedOutcome.AVAILABLE
    assert result.target_count == expected_target
    assert result.positive_candidate_count == expected_target
    assert result.selected_seed_count == expected_target
    assert sum(row.diagnostic_seed_selected is True for row in result.rows) == (
        expected_target
    )


def test_exact_cutoff_ties_expand_without_identity_tiebreaking():
    observations = [
        _signal(index, Decimal(50_000 * (index + 1))) for index in range(17)
    ]
    observations.extend(
        (
            _signal(17, Decimal("1000000")),
            _signal(18, Decimal("900000")),
            _signal(19, Decimal("900000")),
        )
    )
    result = _build(_parent(*observations))
    members = [row for row in result.rows if row.meets_top_decile_cutoff]

    assert result.target_count == 2
    assert result.cutoff_tie_count == 2
    assert result.top_decile_member_count == 3
    assert result.positive_candidate_count == 3
    assert len(members) == 3
    assert members[1].exact_ranking_value == members[2].exact_ranking_value
    assert {row.security_id for row in members} == {
        "security-00017",
        "security-00018",
        "security-00019",
    }


def test_structural_zeros_are_in_the_denominator_but_never_seeds():
    parent = _parent(
        _signal(0, Decimal("50000")),
        _signal(1, Decimal("150000")),
        *(_zero(index) for index in range(2, 21)),
    )
    result = _build(parent)
    zeros = [
        row
        for row in result.rows
        if row.disposition
        is (
            normalization_module.Form4StockSignalNormalizationDisposition
            .INCLUDE_STRUCTURAL_ZERO
        )
    ]

    assert result.target_count == 3
    assert result.cutoff_value == 0
    assert result.cutoff_tie_count == 19
    assert result.top_decile_member_count == 21
    assert result.positive_candidate_count == 2
    assert result.selected_seed_count == 2
    assert all(row.included_in_percentile_denominator for row in zeros)
    assert all(row.meets_top_decile_cutoff for row in zeros)
    assert all(not row.positive_signal_candidate for row in zeros)
    assert all(row.diagnostic_seed_selected is False for row in zeros)


def test_one_positive_signal_returns_named_unavailable_without_partial_selection():
    parent = _parent(
        _signal(0, Decimal("50000")),
        *(_zero(index) for index in range(1, 20)),
    )
    assert parent.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    )

    result = _build(parent)

    assert result.outcome is (
        seed_module.Form4StockSignalSeedOutcome.UNAVAILABLE_INSUFFICIENT_POSITIVE_SEEDS
    )
    assert result.target_count == 2
    assert result.cutoff_value == 0
    assert result.top_decile_member_count == 20
    assert result.positive_candidate_count == 1
    assert result.selected_seed_count is None
    assert sum(row.positive_signal_candidate for row in result.rows) == 1
    assert all(row.diagnostic_seed_selected is None for row in result.rows)


def test_exclusions_are_retained_but_never_enter_ranking_denominator():
    observations = list(_distinct_signal_parent(20).observations)
    observations.extend(
        (
            _excluded(
                20,
                normalization_module.Form4StockSignalNormalizationDisposition
                .EXCLUDE_INELIGIBLE,
            ),
            _excluded(
                21,
                normalization_module.Form4StockSignalNormalizationDisposition
                .EXCLUDE_MISSING,
            ),
        )
    )
    result = _build(_parent(*observations))
    excluded = [
        row
        for row in result.rows
        if not row.included_in_percentile_denominator
    ]

    assert len(result.rows) == 22
    assert result.identity.observation_count == 22
    assert result.identity.usable_count == 20
    assert len(excluded) == 2
    assert all(row.exact_ranking_value is None for row in excluded)
    assert all(not row.meets_top_decile_cutoff for row in excluded)
    assert all(not row.positive_signal_candidate for row in excluded)
    assert all(row.diagnostic_seed_selected is False for row in excluded)


def test_exact_winsorized_values_break_a_rounded_z_tie_at_the_cutoff():
    observations = [
        _signal(index, Decimal(50_000 + index * 1_000))
        for index in range(17)
    ]
    observations.extend(
        (
            _signal(17, Decimal("1e130")),
            _signal(18, Decimal("1." + "0" * 46 + "1e130")),
            _signal(19, Decimal("1e250")),
        )
    )
    parent = _parent(*observations)
    row_a = parent.rows[17]
    row_b = parent.rows[18]

    assert row_b.winsorized_stock_score_diagnostic > (
        row_a.winsorized_stock_score_diagnostic
    )
    assert (
        row_b.winsorized_stock_score_diagnostic
        - row_a.winsorized_stock_score_diagnostic
        == Decimal("1E-47")
    )
    assert (
        row_a.normalized_stock_score_diagnostic
        == row_b.normalized_stock_score_diagnostic
    )

    result = _build(parent)

    assert result.target_count == 2
    assert result.rows[18].positive_signal_candidate is True
    assert result.rows[17].positive_signal_candidate is False
    assert result.rows[18].diagnostic_seed_selected is True
    assert result.rows[17].diagnostic_seed_selected is False


@pytest.mark.parametrize("parent_kind", ("insufficient", "zero_dispersion"))
def test_unavailable_ib3b_parents_are_refused(parent_kind):
    if parent_kind == "insufficient":
        parent = _distinct_signal_parent(19)
    else:
        parent = _parent(*(_zero(index) for index in range(20)))
    assert parent.outcome is not (
        normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    )

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="requires an AVAILABLE IB-3B parent",
    ):
        _build(parent)


def test_permutation_is_deterministic_and_parent_order_is_canonical():
    observations = tuple(
        _signal(index, Decimal(50_000 * (index + 1))) for index in range(20)
    )
    forward = _build(_parent(*observations))
    reverse = _build(_parent(*reversed(observations)))

    assert forward == reverse
    assert forward.to_payload() == reverse.to_payload()
    assert [row.stock_key for row in forward.rows] == sorted(
        row.stock_key for row in forward.rows
    )


def test_identity_binds_complete_parent_lineage_and_output_inventory():
    parent = _distinct_signal_parent(20)
    result = _build(parent)
    identity = result.identity

    assert identity.evaluation_session == parent.identity.evaluation_session
    assert identity.upstream_normalization_id == parent.identity.normalization_id
    assert identity.upstream_payload_hash == hash_payload(parent.to_payload())
    assert identity.upstream_diagnostics_version == parent.identity.diagnostics_version
    assert identity.upstream_policy_hash == parent.identity.policy_hash
    assert identity.upstream_builder_git_commit == parent.identity.builder_git_commit
    assert identity.upstream_observation_inventory_hash == (
        parent.identity.observation_inventory_hash
    )
    assert identity.upstream_normalized_row_inventory_hash == (
        parent.identity.normalized_row_inventory_hash
    )
    assert identity.row_inventory_hash == hash_payload(
        [row.to_payload() for row in result.rows]
    )
    assert identity.policy_hash == seed_module.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH


def test_identity_lineage_schema_and_id_bind_every_required_field():
    identity = _build(_distinct_signal_parent(20)).identity
    payload = identity.lineage_payload()

    assert set(payload) == {
        "diagnostics_version",
        "policy_hash",
        "builder_git_commit",
        "evaluation_session",
        "upstream_normalization_id",
        "upstream_payload_hash",
        "upstream_diagnostics_version",
        "upstream_policy_hash",
        "upstream_builder_git_commit",
        "upstream_observation_inventory_hash",
        "upstream_normalized_row_inventory_hash",
        "observation_count",
        "usable_count",
        "signal_count",
        "structural_zero_count",
        "excluded_ineligible_count",
        "excluded_missing_count",
        "target_count",
        "cutoff_tie_count",
        "top_decile_member_count",
        "positive_candidate_count",
        "selected_seed_count",
        "cutoff_value",
        "row_inventory_hash",
        "outcome",
        "population_is_caller_declared",
        "canonical_population_verified",
        "role_ids_are_caller_declared",
        *AUTHORITY_FIELDS,
        "authorized_outcome_looks",
        "consumed_outcome_looks",
    }
    assert identity.seed_diagnostics_id == (
        "form4-stock-signal-seed-diagnostics-" + hash_payload(payload)[:16]
    )


def test_local_builder_commit_changes_identity_but_not_diagnostic_rows():
    parent = _distinct_signal_parent(20)
    first = _build(parent)
    second = seed_module.build_form4_stock_signal_seed_diagnostics(
        parent,
        builder_git_commit="a" * 40,
    )

    assert first.rows == second.rows
    assert first.source_normalization == second.source_normalization
    assert first.identity.builder_git_commit != second.identity.builder_git_commit
    assert first.identity.seed_diagnostics_id != second.identity.seed_diagnostics_id


def test_parent_replay_precedes_serialization_and_ignores_shadowed_serializer():
    parent = _distinct_signal_parent(20)

    def fail_if_called():
        raise AssertionError("caller-shadowed serializer was invoked")

    object.__setattr__(parent, "to_payload", fail_if_called)
    result = _build(parent)

    assert result.outcome is seed_module.Form4StockSignalSeedOutcome.AVAILABLE
    assert result.source_normalization is not parent


def test_result_serialization_ignores_shadowed_nested_serializers():
    result = _build(_distinct_signal_parent(20))
    expected_parent_hash = result.identity.upstream_payload_hash
    expected_identity_id = result.identity.seed_diagnostics_id
    expected_row_id = result.rows[0].row_id

    object.__setattr__(result.identity, "to_payload", lambda: {"forged": True})
    object.__setattr__(
        result.identity,
        "lineage_payload",
        lambda: {"forged_identity": True},
    )
    object.__setattr__(result.rows[0], "to_payload", lambda: {"forged": True})
    object.__setattr__(
        result.rows[0],
        "authority_payload",
        lambda: {"trading_authorized": True, "stock_score": "forged"},
    )
    object.__setattr__(
        result,
        "authority_payload",
        lambda: {
            "trading_authorized": True,
            "outcome": "forged",
            "seed_selection": ["TRADE"],
        },
    )
    object.__setattr__(
        result.source_normalization,
        "to_payload",
        lambda: {"forged": True},
    )
    object.__setattr__(
        result.source_normalization.rows[0],
        "to_payload",
        lambda: {"forged": True},
    )

    payload = result.to_payload()

    assert payload["identity"]["seed_diagnostics_id"] == expected_identity_id
    assert payload["rows"][0]["row_id"] == expected_row_id
    assert hash_payload(payload["source_normalization"]) == expected_parent_hash
    assert "forged" not in payload["identity"]
    assert "forged_identity" not in payload["identity"]
    assert "forged" not in payload["rows"][0]
    assert "forged" not in payload["source_normalization"]
    assert payload["rows"][0]["trading_authorized"] is False
    assert payload["rows"][0]["stock_score"] is None
    assert payload["trading_authorized"] is False
    assert payload["outcome"] == result.outcome.value
    assert payload["seed_selection"] is None


def test_builder_detaches_parent_and_result_replays_after_caller_mutation():
    parent = _distinct_signal_parent(20)
    result = _build(parent)
    original_session = result.identity.evaluation_session

    object.__setattr__(parent.identity, "evaluation_session", "caller-mutated")

    assert result.source_normalization is not parent
    assert result.source_normalization.identity.evaluation_session == original_session
    seed_module.Form4StockSignalSeedDiagnostics.__post_init__(
        result,
        seed_module._RESULT_FACTORY_TOKEN,
    )


def test_final_parent_seal_detects_mutation_during_evaluation(monkeypatch):
    parent = _distinct_signal_parent(20)
    real_build_identity = seed_module._build_identity

    def mutate_caller_then_build(**kwargs):
        built = real_build_identity(**kwargs)
        object.__setattr__(
            parent.identity,
            "evaluation_session",
            "mutated-during-build",
        )
        return built

    monkeypatch.setattr(seed_module, "_build_identity", mutate_caller_then_build)
    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="source IB-3B diagnostics are inconsistent|do not replay",
    ):
        _build(parent)


def test_parent_row_tamper_is_refused_before_ib3c_computation():
    parent = _distinct_signal_parent(20)
    object.__setattr__(
        parent.rows[0],
        "winsorized_stock_score_diagnostic",
        Decimal("999"),
    )

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="source IB-3B diagnostics",
    ):
        _build(parent)


@pytest.mark.parametrize(
    ("location", "field_name"),
    (("identity", "structural_zero_count"), ("result", "outcome")),
)
def test_parent_replay_refuses_cross_type_values_that_compare_equal(
    location,
    field_name,
):
    parent = _distinct_signal_parent(20)
    if location == "identity":
        changed_identity = _forge(parent.identity, **{field_name: False})
        changed_parent = _forge(parent, identity=changed_identity)
    else:
        changed_parent = _forge(parent, outcome=parent.outcome.value)

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="source IB-3B diagnostics are inconsistent",
    ):
        _build(changed_parent)


def test_coherently_rehashed_output_row_tamper_is_caught_by_parent_replay():
    result = _build(_distinct_signal_parent(20))
    original = result.rows[0]
    changed = _rehash_row(
        original,
        meets_top_decile_cutoff=True,
        positive_signal_candidate=True,
        diagnostic_seed_selected=True,
    )
    seed_module.Form4StockSignalSeedDiagnosticRow.__post_init__(
        changed,
        seed_module._ROW_FACTORY_TOKEN,
    )
    forged = _forge(result, rows=(changed, *result.rows[1:]))

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="seed rows do not replay",
    ):
        seed_module.Form4StockSignalSeedDiagnostics.__post_init__(
            forged,
            seed_module._RESULT_FACTORY_TOKEN,
        )


def test_standalone_row_rejects_a_stale_lineage_hash():
    result = _build(_distinct_signal_parent(20))
    changed = _forge(result.rows[0], row_id="0" * 64)

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="row ID is inconsistent",
    ):
        seed_module.Form4StockSignalSeedDiagnosticRow.__post_init__(
            changed,
            seed_module._ROW_FACTORY_TOKEN,
        )


def test_row_payload_and_id_bind_diagnostic_selection_state():
    result = _build(_distinct_signal_parent(20))
    selected = next(
        row for row in result.rows if row.diagnostic_seed_selected is True
    )
    payload = selected.to_payload()

    assert set(payload) == {
        "parent_row_id",
        "issuer_cik",
        "security_id",
        "share_class_id",
        "disposition",
        "included_in_percentile_denominator",
        "exact_ranking_value",
        "meets_top_decile_cutoff",
        "positive_signal_candidate",
        "diagnostic_seed_selected",
        "stock_score",
        "rank",
        "seed_selected",
        "population_is_caller_declared",
        "canonical_population_verified",
        "role_ids_are_caller_declared",
        *AUTHORITY_FIELDS,
        "authorized_outcome_looks",
        "consumed_outcome_looks",
        "row_id",
    }
    assert payload["diagnostic_seed_selected"] is True
    lineage = {name: value for name, value in payload.items() if name != "row_id"}
    assert selected.row_id == hash_payload(lineage)


def test_coherently_rehashed_identity_tamper_is_caught_by_result_replay():
    result = _build(_distinct_signal_parent(20))
    changed_identity = _rehash_identity(
        result.identity,
        upstream_payload_hash="0" * 64,
    )
    seed_module.Form4StockSignalSeedIdentity.__post_init__(
        changed_identity,
        seed_module._IDENTITY_FACTORY_TOKEN,
    )
    forged = _forge(result, identity=changed_identity)

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="identity does not replay",
    ):
        seed_module.Form4StockSignalSeedDiagnostics.__post_init__(
            forged,
            seed_module._RESULT_FACTORY_TOKEN,
        )


def test_seed_identity_id_binds_the_output_row_inventory_hash():
    result = _build(_distinct_signal_parent(20))
    changed = _rehash_identity(
        result.identity,
        row_inventory_hash="0" * 64,
    )

    assert changed.seed_diagnostics_id != result.identity.seed_diagnostics_id
    assert changed.lineage_payload()["row_inventory_hash"] == "0" * 64


def test_standalone_identity_rejects_a_stale_lineage_id():
    result = _build(_distinct_signal_parent(20))
    changed = _forge(
        result.identity,
        seed_diagnostics_id="form4-stock-signal-seed-diagnostics-" + "0" * 16,
    )

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="seed diagnostics ID is inconsistent",
    ):
        seed_module.Form4StockSignalSeedIdentity.__post_init__(
            changed,
            seed_module._IDENTITY_FACTORY_TOKEN,
        )


def test_rows_identity_and_result_refuse_direct_construction():
    result = _build(_distinct_signal_parent(20))

    for value in (result.rows[0], result.identity, result):
        kwargs = {field.name: getattr(value, field.name) for field in fields(value)}
        with pytest.raises(
            seed_module.Form4StockSignalSeedDiagnosticsError,
            match="factory-created",
        ):
            type(value)(**kwargs)


@pytest.mark.parametrize(
    "field_name",
    (
        "target_count",
        "cutoff_tie_count",
        "top_decile_member_count",
        "positive_candidate_count",
        "selected_seed_count",
    ),
)
def test_result_summary_refuses_equal_cross_type_counts(field_name):
    result = _build(_distinct_signal_parent(20))
    changed = _forge(
        result,
        **{field_name: Decimal(getattr(result, field_name))},
    )

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="exact integer",
    ):
        seed_module.Form4StockSignalSeedDiagnostics.__post_init__(
            changed,
            seed_module._RESULT_FACTORY_TOKEN,
        )


def test_result_summary_refuses_equal_raw_enum_and_integer_cutoff():
    available = _build(_distinct_signal_parent(20))
    raw_outcome = _forge(available, outcome=available.outcome.value)
    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="outcome must be an exact enum",
    ):
        seed_module.Form4StockSignalSeedDiagnostics.__post_init__(
            raw_outcome,
            seed_module._RESULT_FACTORY_TOKEN,
        )

    zero_cutoff = _build(
        _parent(
            _signal(0, Decimal("50000")),
            _signal(1, Decimal("150000")),
            *(_zero(index) for index in range(2, 21)),
        )
    )
    assert zero_cutoff.cutoff_value == Decimal("0")
    integer_cutoff = _forge(zero_cutoff, cutoff_value=0)
    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="exact finite Decimal",
    ):
        seed_module.Form4StockSignalSeedDiagnostics.__post_init__(
            integer_cutoff,
            seed_module._RESULT_FACTORY_TOKEN,
        )


def test_decimal_resource_bounds_apply_to_rows_and_identity():
    result = _build(_distinct_signal_parent(20))
    too_many_digits = Decimal("1" * 51)
    too_large_exponent = Decimal("1e2049")

    for value in (too_many_digits, too_large_exponent):
        changed_row = _rehash_row(
            result.rows[-1],
            exact_ranking_value=value,
        )
        with pytest.raises(
            seed_module.Form4StockSignalSeedDiagnosticsError,
            match="Decimal resource bound",
        ):
            seed_module.Form4StockSignalSeedDiagnosticRow.__post_init__(
                changed_row,
                seed_module._ROW_FACTORY_TOKEN,
            )

        changed_identity = _rehash_identity(
            result.identity,
            cutoff_value=value,
        )
        with pytest.raises(
            seed_module.Form4StockSignalSeedDiagnosticsError,
            match="Decimal resource bound",
        ):
            seed_module.Form4StockSignalSeedIdentity.__post_init__(
                changed_identity,
                seed_module._IDENTITY_FACTORY_TOKEN,
            )


@pytest.mark.parametrize(
    "invalid_value",
    ("1", Decimal("NaN"), Decimal("Infinity"), Decimal("-1")),
)
def test_decimal_type_finiteness_and_sign_guards_are_load_bearing(invalid_value):
    result = _build(_distinct_signal_parent(20))
    changed_row = _forge(
        result.rows[-1],
        exact_ranking_value=invalid_value,
    )
    changed_identity = _forge(
        result.identity,
        cutoff_value=invalid_value,
    )

    with pytest.raises(seed_module.Form4StockSignalSeedDiagnosticsError):
        seed_module.Form4StockSignalSeedDiagnosticRow.__post_init__(
            changed_row,
            seed_module._ROW_FACTORY_TOKEN,
        )
    with pytest.raises(seed_module.Form4StockSignalSeedDiagnosticsError):
        seed_module.Form4StockSignalSeedIdentity.__post_init__(
            changed_identity,
            seed_module._IDENTITY_FACTORY_TOKEN,
        )


def test_zero_authority_and_canonical_fields_remain_unavailable():
    available = _build(_distinct_signal_parent(20))
    unavailable = _build(
        _parent(
            _signal(0, Decimal("50000")),
            *(_zero(index) for index in range(1, 20)),
        )
    )

    for result in (available, unavailable):
        objects = (result, result.identity, *result.rows)
        for value in objects:
            assert value.population_is_caller_declared is True
            assert value.canonical_population_verified is False
            assert value.role_ids_are_caller_declared is True
            assert all(getattr(value, name) is False for name in AUTHORITY_FIELDS)
            assert value.authorized_outcome_looks == 0
            assert value.consumed_outcome_looks == 0
        assert result.stock_score is None
        assert result.ranking is None
        assert result.seed_selection is None
        assert all(row.stock_score is None for row in result.rows)
        assert all(row.rank is None for row in result.rows)
        assert all(row.seed_selected is None for row in result.rows)
        assert result.source_normalization.ranking is None
        assert result.source_normalization.seed_selection is None


@pytest.mark.parametrize(
    ("scope", "field_name"),
    (
        ("row", "stock_score"),
        ("row", "rank"),
        ("row", "seed_selected"),
        ("result", "stock_score"),
        ("result", "ranking"),
        ("result", "seed_selection"),
    ),
)
def test_canonical_unavailability_guards_are_load_bearing(scope, field_name):
    result = _build(_distinct_signal_parent(20))
    if scope == "row":
        changed = _forge(result.rows[0], **{field_name: "forged"})
        validator = seed_module.Form4StockSignalSeedDiagnosticRow.__post_init__
        token = seed_module._ROW_FACTORY_TOKEN
    else:
        changed = _forge(result, **{field_name: "forged"})
        validator = seed_module.Form4StockSignalSeedDiagnostics.__post_init__
        token = seed_module._RESULT_FACTORY_TOKEN

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="canonical score, rank, and seed selection remain unavailable",
    ):
        validator(changed, token)


def test_builder_requires_exact_types_and_commit_shape():
    parent = _distinct_signal_parent(20)

    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="exact IB-3B",
    ):
        seed_module.build_form4_stock_signal_seed_diagnostics(
            object(),
            builder_git_commit=SEED_BUILDER_COMMIT,
        )
    for invalid in ("A" * 40, "f" * 39, _TextSubclass("f" * 40)):
        with pytest.raises(
            seed_module.Form4StockSignalSeedDiagnosticsError,
            match="builder Git commit",
        ):
            seed_module.build_form4_stock_signal_seed_diagnostics(
                parent,
                builder_git_commit=invalid,
            )


@pytest.mark.parametrize("inventory_kind", ("empty", "over_limit"))
def test_source_inventory_bounds_are_checked_before_upstream_replay(
    monkeypatch,
    inventory_kind,
):
    valid_parent = _distinct_signal_parent(20)
    observations = (
        ()
        if inventory_kind == "empty"
        else (valid_parent.observations[0],)
        * (seed_module.MAX_FORM4_STOCK_SIGNAL_SEED_ROWS + 1)
    )
    parent = _forge(valid_parent, observations=observations)
    called = False

    def unexpected_replay(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("upstream replay should not start")

    monkeypatch.setattr(
        seed_module,
        "build_form4_stock_signal_normalization_diagnostics",
        unexpected_replay,
    )
    with pytest.raises(
        seed_module.Form4StockSignalSeedDiagnosticsError,
        match="observation inventory is out of bounds",
    ):
        _build(parent)
    assert called is False


def test_standalone_identity_rejects_impossible_tie_and_selection_counts():
    result = _build(_distinct_signal_parent(20))
    cases = (
        {"cutoff_tie_count": 0},
        {"top_decile_member_count": 1},
        {"positive_candidate_count": result.identity.signal_count + 1},
        {"selected_seed_count": None},
        {
            "observation_count": 19,
            "usable_count": 19,
            "signal_count": 19,
        },
        {"target_count": True},
        {"evaluation_session": "x" * 129},
    )

    for updates in cases:
        changed = _rehash_identity(result.identity, **updates)
        with pytest.raises(seed_module.Form4StockSignalSeedDiagnosticsError):
            seed_module.Form4StockSignalSeedIdentity.__post_init__(
                changed,
                seed_module._IDENTITY_FACTORY_TOKEN,
            )


def test_public_exports_and_package_boundary_are_explicit():
    assert tuple(seed_module.__all__) == EXPECTED_PUBLIC_EXPORTS
    for name in EXPECTED_PUBLIC_EXPORTS:
        assert getattr(insider_package, name) is getattr(seed_module, name)
        assert name in insider_package.__all__


def test_module_import_boundary_is_offline_and_dependency_bounded():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)

    assert imports == EXPECTED_MODULE_IMPORTS
    assert not imports.intersection(
        {
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "quantconnect",
            "pandas",
            "numpy",
        }
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "eval", "exec", "float", "open"}
        for node in ast.walk(tree)
    )
