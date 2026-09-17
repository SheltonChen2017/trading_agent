"""Synthetic/offline tests for bounded Insider Buying IB-3B normalization.

IB-3B consumes only sealed synthetic observations.  Positive scores replay
from exact IB-3A diagnostics, structural zeros remain in the usable cohort,
and every excluded name remains in the output.  Nothing in this file grants a
canonical score, ranking, seed, outcome look, external-data access, QC work,
deployment, or trading authority.
"""
from __future__ import annotations

import ast
from dataclasses import fields
from datetime import date
from decimal import Context, Decimal, Inexact, ROUND_UP, localcontext
from pathlib import Path

import pytest

import research.insider_buying as insider_package
from data.hashing import hash_payload
from research.insider_buying import (
    form4_stock_signal_formula_diagnostics as signal_module,
)
from research.insider_buying import (
    form4_stock_signal_normalization_diagnostics as normalization_module,
)


BUILDER_COMMIT = "e" * 40
EVALUATION_SESSION = "2026-09-17-synthetic-session"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "insider_buying"
    / "form4_stock_signal_normalization_diagnostics.py"
)
EXPECTED_MODULE_IMPORTS = {
    "__future__",
    "data.financial_primitives",
    "data.hashing",
    "dataclasses",
    "decimal",
    "enum",
    "re",
    "research.insider_buying.form4_stock_signal_formula_diagnostics",
    "threading",
    "weakref",
}
EXPECTED_PUBLIC_EXPORTS = (
    "FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_ROUNDING",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_FINAL_QUANTIZATION",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_QUANTILE_METHOD",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_VARIANCE_DENOMINATOR",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_ZERO_DISPERSION_POLICY",
    "MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS",
    "MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS",
    "Form4StockSignalNormalizationDiagnostics",
    "Form4StockSignalNormalizationDiagnosticsError",
    "Form4StockSignalNormalizationDisposition",
    "Form4StockSignalNormalizationIdentity",
    "Form4StockSignalNormalizationObservation",
    "Form4StockSignalNormalizationOutcome",
    "Form4StockSignalNormalizedDiagnosticRow",
    "build_form4_stock_signal_normalization_diagnostics",
    "build_form4_stock_signal_normalization_observation",
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


def _zero(
    index: int,
    *,
    source_sequence: int | None = None,
):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        disposition=(
            normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
        ),
        synthetic_source_id=_source_id(
            1_000_000 + index if source_sequence is None else source_sequence
        ),
    )


def _excluded(
    index: int,
    disposition,
    *,
    source_sequence: int | None = None,
):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        disposition=disposition,
        synthetic_source_id=_source_id(
            2_000_000 + index if source_sequence is None else source_sequence
        ),
    )


def _signal_source(index: int, purchase_value_usd: Decimal):
    issuer_cik, security_id, share_class_id = _stock_key(index)
    event = signal_module.build_form4_stock_signal_fixture_event(
        source_event_id=_source_id(3_000_000 + index),
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        buyer_id=f"buyer-{index:05d}",
        transaction_date=date(2026, 9, 17),
        purchase_value_usd=purchase_value_usd,
        age_trading_days=0,
        normalized_role_ids=("director",),
    )
    return signal_module.build_form4_stock_signal_formula_diagnostics(
        (event,),
        builder_git_commit=BUILDER_COMMIT,
    )


def _signal(index: int, purchase_value_usd: Decimal):
    source = _signal_source(index, purchase_value_usd)
    return normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=source.issuer_cik,
        security_id=source.security_id,
        share_class_id=source.share_class_id,
        disposition=(
            normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        ),
        source_diagnostics=source,
    )


def _build(*observations):
    return normalization_module.build_form4_stock_signal_normalization_diagnostics(
        observations,
        evaluation_session=EVALUATION_SESSION,
        builder_git_commit=BUILDER_COMMIT,
    )


def _zero_cohort(count: int = 20):
    return tuple(_zero(index) for index in range(count))


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


class _TextSubclass(str):
    pass


def _rehash_observation(observation, **updates):
    changed = _forge(observation, **updates)
    return _forge(
        changed,
        observation_id=hash_payload(changed.lineage_payload()),
    )


def _rehash_row(row, **updates):
    changed = _forge(row, **updates)
    return _forge(
        changed,
        row_id=hash_payload(changed.lineage_payload()),
    )


def _rehash_identity(identity, **updates):
    changed = _forge(identity, **updates)
    digest = hash_payload(changed.lineage_payload())
    return _forge(
        changed,
        normalization_id=(
            "form4-stock-signal-normalization-diagnostics-" + digest[:16]
        ),
    )


def test_ib3b_policy_and_hash_are_frozen():
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION == (
        "INSETF-IB3B-FORM4-STOCK-SIGNAL-NORMALIZATION-DIAGNOSTICS-v1"
    )
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE == Decimal("0.01")
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE == Decimal("0.99")
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_QUANTILE_METHOD == (
        "type-7-linear-h=(N-1)*p-value-based-ties"
    )
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_VARIANCE_DENOMINATOR == "population-N"
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES == 20
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES == 2
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION == 50
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_ROUNDING == "ROUND_HALF_EVEN"
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_ZERO_DISPERSION_POLICY == (
        "unavailable-no-epsilon-no-substituted-zero"
    )
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_FINAL_QUANTIZATION is None
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY == "deferred"
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY == "deferred"
    assert normalization_module.MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS == 10_000
    assert normalization_module.MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS == 128
    assert normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH == (
        "6705744ca9df421f4f96f955a3a4e850"
        "570806ac5b1059ad79488f36d14ffd04"
    )
    assert hash_payload(normalization_module._policy_payload()) == (
        normalization_module.FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH
    )


def test_pure_kernel_has_type7_population_fifty_digit_goldens():
    values = tuple(Decimal(index) for index in range(20))
    result = normalization_module._compute_normalization(values)

    assert result.outcome is normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    assert result.lower_cutoff == Decimal("0.19")
    assert result.upper_cutoff == Decimal("18.81")
    assert result.winsorized_values == (
        Decimal("0.19"),
        *(Decimal(index) for index in range(1, 19)),
        Decimal("18.81"),
    )
    assert result.mean == Decimal("9.50")
    assert result.population_variance == Decimal("32.89261")
    assert result.population_variance != Decimal("34.6238")
    assert str(result.standard_deviation) == (
        "5.7352079299708044674152858151802959036108211469603"
    )
    expected = {
        0: "-1.6233064456736084364128085591057856114980460619635",
        1: "-1.4820735540521666712684073847904594734407509695693",
        9: "-0.087180797297186274780494552046497616084750057033485",
        10: "0.087180797297186274780494552046497616084750057033485",
        18: "1.4820735540521666712684073847904594734407509695693",
        19: "1.6233064456736084364128085591057856114980460619635",
    }
    for index, text in expected.items():
        assert str(result.normalized_values[index]) == text
    context = normalization_module._new_decimal_context()
    assert normalization_module._context_sum(
        context,
        result.normalized_values,
    ) == Decimal("0E-49")


def test_type7_fractional_upper_tail_integer_index_and_value_ties():
    context = normalization_module._new_decimal_context()
    asymmetric = tuple(Decimal(index) for index in range(19)) + (Decimal("100"),)
    assert normalization_module._type7_quantile(
        context,
        asymmetric,
        Decimal("0.01"),
    ) == Decimal("0.19")
    assert normalization_module._type7_quantile(
        context,
        asymmetric,
        Decimal("0.99"),
    ) == Decimal("84.42")
    integer_index = tuple(Decimal(index) for index in range(101))
    assert normalization_module._type7_quantile(context, integer_index, Decimal("0.01")) == Decimal("1")
    assert normalization_module._type7_quantile(context, integer_index, Decimal("0.99")) == Decimal("99")

    tied = normalization_module._compute_normalization(
        (Decimal("0"),) + (Decimal("100"),) * 19
    )
    assert tied.lower_cutoff == Decimal("19")
    assert tied.upper_cutoff == Decimal("100")
    assert tied.mean == Decimal("95.95")
    assert tied.population_variance == Decimal("311.6475")
    assert str(tied.standard_deviation) == (
        "17.653540721339727886559777034631443419504865897191"
    )
    assert str(tied.normalized_values[0]) == (
        "-4.3588989435406735522369819838596156591370039252325"
    )
    assert set(tied.normalized_values[1:]) == {
        Decimal("0.22941573387056176590720957809787450837563178553855")
    }


def test_pure_kernel_minimum_n_and_zero_dispersion_are_named_outcomes():
    insufficient = normalization_module._compute_normalization(
        tuple(Decimal(index) for index in range(19))
    )
    assert insufficient.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_INSUFFICIENT_USABLE_COHORT
    )
    assert insufficient.winsorized_values == (None,) * 19
    assert insufficient.normalized_values == (None,) * 19
    assert all(
        value is None
        for value in (
            insufficient.lower_cutoff,
            insufficient.upper_cutoff,
            insufficient.mean,
            insufficient.population_variance,
            insufficient.standard_deviation,
        )
    )

    zero_dispersion = normalization_module._compute_normalization(
        (Decimal("5"),) * 20
    )
    assert zero_dispersion.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
    )
    assert zero_dispersion.lower_cutoff == Decimal("5")
    assert zero_dispersion.upper_cutoff == Decimal("5")
    assert zero_dispersion.mean == Decimal("5")
    assert zero_dispersion.population_variance == Decimal("0")
    assert zero_dispersion.standard_deviation == Decimal("0")
    assert zero_dispersion.distinct_post_winsor_value_count == 1
    assert zero_dispersion.normalized_values == (None,) * 20


def test_public_cohorts_preserve_exact_moments_at_numeric_boundaries():
    identical = _build(
        *tuple(_signal(index, Decimal("50000")) for index in range(20))
    )
    assert identical.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
    )
    assert identical.lower_cutoff == identical.upper_cutoff == identical.mean
    assert identical.population_variance == Decimal(0)
    assert identical.standard_deviation == Decimal(0)

    adjacent = _build(
        *tuple(
            _signal(
                index,
                Decimal("50000")
                if index < 10
                else Decimal("50000." + "0" * 44 + "1"),
            )
            for index in range(20)
        )
    )
    assert adjacent.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    )
    assert adjacent.lower_cutoff <= adjacent.mean <= adjacent.upper_cutoff

    rounded_variance_cap = _build(
        _signal(0, Decimal("50000")),
        *tuple(_zero(index) for index in range(1, 32)),
    )
    assert rounded_variance_cap.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    )

    rounded_variance_floor = _build(
        _zero(0),
        _signal(1, Decimal("150000")),
        *tuple(_signal(index, Decimal("50000")) for index in range(2, 53)),
    )
    assert rounded_variance_floor.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    )

    zero_clipped_signal = _build(
        _signal(0, Decimal("50000")),
        *tuple(_zero(index) for index in range(1, 101)),
    )
    assert zero_clipped_signal.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
    )
    assert zero_clipped_signal.upper_cutoff == zero_clipped_signal.mean == Decimal(0)
    assert next(
        row
        for row in zero_clipped_signal.rows
        if row.disposition
        is normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
    ).winsorized_stock_score_diagnostic == Decimal(0)
    impossible_nonzero_upper = _rehash_identity(
        zero_clipped_signal.identity,
        outcome=normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE,
        upper_cutoff=Decimal("1"),
        mean=Decimal("0.005"),
        population_variance=Decimal("0.01"),
        standard_deviation=Decimal("0.1"),
        distinct_post_winsor_value_count=2,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="upper cutoff is inconsistent with Type-7 zero mass",
    ):
        type(impossible_nonzero_upper).__post_init__(
            impossible_nonzero_upper,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    positive_clipped_zero = _build(
        _zero(0),
        *tuple(_signal(index, Decimal("50000")) for index in range(1, 101)),
    )
    assert positive_clipped_zero.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
    )
    assert positive_clipped_zero.lower_cutoff == positive_clipped_zero.mean
    assert positive_clipped_zero.mean > 0


def test_exact_ib3a_integration_includes_zero_and_retains_exclusions():
    usable = (_zero(0),) + tuple(
        _signal(index, Decimal(50_000 * (index + 1)))
        for index in range(1, 20)
    )
    ineligible = _excluded(
        20,
        normalization_module.Form4StockSignalNormalizationDisposition.EXCLUDE_INELIGIBLE,
    )
    missing = _excluded(
        21,
        normalization_module.Form4StockSignalNormalizationDisposition.EXCLUDE_MISSING,
    )
    supplied = tuple(reversed((*usable, ineligible, missing)))
    result = _build(*supplied)

    assert result.outcome is normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    assert result.identity.observation_count == 22
    assert result.identity.usable_count == 20
    assert result.identity.signal_count == 19
    assert result.identity.structural_zero_count == 1
    assert result.identity.excluded_ineligible_count == 1
    assert result.identity.excluded_missing_count == 1
    assert tuple(item.stock_key for item in result.observations) == tuple(
        sorted(item.stock_key for item in supplied)
    )

    usable_values = tuple(
        observation.raw_stock_score_diagnostic
        for observation in result.observations
        if observation.disposition
        in (
            normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
    )
    expected = normalization_module._compute_normalization(usable_values)
    assert result.lower_cutoff == expected.lower_cutoff
    assert result.upper_cutoff == expected.upper_cutoff
    assert result.mean == expected.mean
    assert result.population_variance == expected.population_variance
    assert result.standard_deviation == expected.standard_deviation
    structural_row = next(
        row
        for row in result.rows
        if row.disposition
        is normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
    )
    assert structural_row.included_in_normalization is True
    assert structural_row.raw_stock_score_diagnostic == Decimal("0")
    assert structural_row.winsorized_stock_score_diagnostic == result.lower_cutoff
    assert structural_row.normalized_stock_score_diagnostic is not None
    excluded_rows = [row for row in result.rows if not row.included_in_normalization]
    assert len(excluded_rows) == 2
    assert {
        row.disposition for row in excluded_rows
    } == {
        normalization_module.Form4StockSignalNormalizationDisposition.EXCLUDE_INELIGIBLE,
        normalization_module.Form4StockSignalNormalizationDisposition.EXCLUDE_MISSING,
    }
    assert all(
        row.raw_stock_score_diagnostic is None
        and row.winsorized_stock_score_diagnostic is None
        and row.normalized_stock_score_diagnostic is None
        for row in excluded_rows
    )
    assert result.identity.observation_inventory_hash == hash_payload(
        [item.to_payload() for item in result.observations]
    )
    assert result.identity.normalized_row_inventory_hash == hash_payload(
        [item.to_payload() for item in result.rows]
    )


def test_retained_exclusions_do_not_satisfy_minimum_usable_count():
    observations = _zero_cohort(19) + tuple(
        _excluded(
            30 + index,
            normalization_module.Form4StockSignalNormalizationDisposition.EXCLUDE_MISSING,
        )
        for index in range(10)
    )
    result = _build(*observations)
    assert result.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_INSUFFICIENT_USABLE_COHORT
    )
    assert result.identity.observation_count == 29
    assert result.identity.usable_count == 19
    assert result.identity.excluded_missing_count == 10
    assert all(row.winsorized_stock_score_diagnostic is None for row in result.rows)


def test_eligible_missing_score_refuses_before_numerical_work(monkeypatch):
    missing = _excluded(
        19,
        normalization_module.Form4StockSignalNormalizationDisposition.REFUSE_ELIGIBLE_MISSING_SCORE,
    )

    def reached_kernel(_values):
        raise AssertionError("numeric kernel ran before eligible-missing refusal")

    monkeypatch.setattr(normalization_module, "_compute_normalization", reached_kernel)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="eligible row is missing",
    ):
        _build(*_zero_cohort(19), missing)

    issuer_cik, security_id, share_class_id = _stock_key(99)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="requires exact IB-3A diagnostics",
    ):
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik=issuer_cik,
            security_id=security_id,
            share_class_id=share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            ),
        )


def test_input_permutation_is_canonical_and_duplicate_identities_refuse():
    observations = _zero_cohort()
    forward = _build(*observations)
    reverse = _build(*reversed(observations))
    assert forward == reverse
    assert forward.to_payload() == reverse.to_payload()

    duplicate_stock = _zero(0, source_sequence=9_000_000)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="unique",
    ):
        _build(observations[0], duplicate_stock)

    duplicate_source = _zero(1, source_sequence=8_000_000)
    other_same_source = _zero(2, source_sequence=8_000_000)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="unique",
    ):
        _build(duplicate_source, other_same_source)


def test_signal_observation_replays_and_binds_exact_ib3a_source():
    source = _signal_source(4, Decimal("250000"))
    observation = normalization_module.build_form4_stock_signal_normalization_observation(
        issuer_cik=source.issuer_cik,
        security_id=source.security_id,
        share_class_id=source.share_class_id,
        disposition=(
            normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        ),
        source_diagnostics=source,
    )
    assert observation.raw_stock_score_diagnostic == source.raw_stock_score_diagnostic
    assert observation.upstream_diagnostics_id == source.identity.diagnostics_id
    assert observation.upstream_payload_hash == hash_payload(source.to_payload())
    assert observation.synthetic_source_id == observation.upstream_payload_hash
    assert observation.upstream_builder_git_commit == BUILDER_COMMIT

    mismatched_source_id = _rehash_observation(
        observation,
        synthetic_source_id="f" * 64,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="policy lineage",
    ):
        type(mismatched_source_id).__post_init__(
            mismatched_source_id,
            normalization_module._OBSERVATION_FACTORY_TOKEN,
        )

    malformed_upstream_id = _rehash_observation(
        observation,
        upstream_diagnostics_id="not-an-ib3a-diagnostics-id",
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="invalid shape",
    ):
        type(malformed_upstream_id).__post_init__(
            malformed_upstream_id,
            normalization_module._OBSERVATION_FACTORY_TOKEN,
        )

    subclass_version = _rehash_observation(
        observation,
        upstream_diagnostics_version=_TextSubclass(
            observation.upstream_diagnostics_version
        ),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="policy lineage",
    ):
        type(subclass_version).__post_init__(
            subclass_version,
            normalization_module._OBSERVATION_FACTORY_TOKEN,
        )

    forged = _forge(
        source,
        raw_stock_score_diagnostic=(
            source.raw_stock_score_diagnostic + Decimal("1")
        ),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="inconsistent or changed",
    ):
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik=source.issuer_cik,
            security_id=source.security_id,
            share_class_id=source.share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            ),
            source_diagnostics=forged,
        )

    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="stock key",
    ):
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik="0000009999",
            security_id=source.security_id,
            share_class_id=source.share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            ),
            source_diagnostics=source,
        )


def test_signal_observation_preflights_before_source_serialization(monkeypatch):
    source = _signal_source(5, Decimal("300000"))
    reached_replay = False

    def replay_reached(*_args, **_kwargs):
        nonlocal reached_replay
        reached_replay = True
        return source

    monkeypatch.setattr(
        normalization_module,
        "build_form4_stock_signal_formula_diagnostics",
        replay_reached,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="lowercase SHA-256",
    ):
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik=source.issuer_cik,
            security_id=source.security_id,
            share_class_id=source.share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            ),
            synthetic_source_id="not-a-sha",
            source_diagnostics=source,
        )
    assert reached_replay is False

    def refuse_replay(*_args, **_kwargs):
        raise signal_module.Form4StockSignalFormulaDiagnosticsError("upstream refused")

    def serialization_reached():
        raise AssertionError("untrusted source was serialized before replay refusal")

    monkeypatch.setattr(
        normalization_module,
        "build_form4_stock_signal_formula_diagnostics",
        refuse_replay,
    )
    object.__setattr__(source, "to_payload", serialization_reached)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="do not replay",
    ):
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik=source.issuer_cik,
            security_id=source.security_id,
            share_class_id=source.share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            ),
            source_diagnostics=source,
        )


def test_observation_constructor_registry_and_representation_seals():
    observation = _zero(0)
    with pytest.raises(normalization_module.Form4StockSignalNormalizationDiagnosticsError):
        type(observation)(**vars(observation))

    equal_unregistered = _forge(observation)
    assert equal_unregistered == observation
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="unsealed|mutated",
    ):
        _build(equal_unregistered)

    rehashed_but_contradictory = _rehash_observation(
        observation,
        disposition=(
            normalization_module.Form4StockSignalNormalizationDisposition.EXCLUDE_INELIGIBLE
        ),
    )
    with pytest.raises(normalization_module.Form4StockSignalNormalizationDiagnosticsError):
        type(rehashed_but_contradictory).__post_init__(
            rehashed_but_contradictory,
            normalization_module._OBSERVATION_FACTORY_TOKEN,
        )

    representation_variant = _forge(
        observation,
        raw_stock_score_diagnostic=Decimal("0.0"),
    )
    assert representation_variant.observation_id == observation.observation_id
    type(representation_variant).__post_init__(
        representation_variant,
        normalization_module._OBSERVATION_FACTORY_TOKEN,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="unsealed|mutated",
    ):
        _build(representation_variant)

    integer_zero = _rehash_observation(
        observation,
        raw_stock_score_diagnostic=0,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="exact finite Decimal",
    ):
        type(integer_zero).__post_init__(
            integer_zero,
            normalization_module._OBSERVATION_FACTORY_TOKEN,
        )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="exact finite Decimal",
    ):
        _build(integer_zero)


def test_result_rows_and_identity_are_factory_gated_and_replayable():
    result = _build(*_zero_cohort())
    targets_and_tokens = (
        (result.observations[0], normalization_module._OBSERVATION_FACTORY_TOKEN),
        (result.rows[0], normalization_module._ROW_FACTORY_TOKEN),
        (result.identity, normalization_module._IDENTITY_FACTORY_TOKEN),
        (result, normalization_module._RESULT_FACTORY_TOKEN),
    )
    for target, token in targets_and_tokens:
        with pytest.raises(normalization_module.Form4StockSignalNormalizationDiagnosticsError):
            type(target)(**vars(target))
        type(target).__post_init__(target, token)

    for field_name, value in (
        ("stock_score", Decimal("0")),
        ("rank", 1),
        ("seed_selected", False),
    ):
        promoted_row = _forge(result.rows[0], **{field_name: value})
        with pytest.raises(
            normalization_module.Form4StockSignalNormalizationDiagnosticsError,
            match="canonical score, rank, and seed",
        ):
            type(promoted_row).__post_init__(
                promoted_row,
                normalization_module._ROW_FACTORY_TOKEN,
            )

    for field_name, value in (
        ("stock_score", Decimal("0")),
        ("ranking", (1,)),
        ("seed_selection", (True,)),
    ):
        promoted_result = _forge(result, **{field_name: value})
        with pytest.raises(
            normalization_module.Form4StockSignalNormalizationDiagnosticsError,
            match="canonical score, ranking, and seed selection",
        ):
            type(promoted_result).__post_init__(
                promoted_result,
                normalization_module._RESULT_FACTORY_TOKEN,
            )

    reordered = _forge(result, observations=tuple(reversed(result.observations)))
    with pytest.raises(normalization_module.Form4StockSignalNormalizationDiagnosticsError):
        type(reordered).__post_init__(reordered, normalization_module._RESULT_FACTORY_TOKEN)


def test_standalone_identity_refuses_impossible_outcome_partitions():
    result = _build(*_zero_cohort())
    assert result.identity.usable_count == 20
    assert result.identity.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
    )

    impossible_insufficient = _rehash_identity(
        result.identity,
        outcome=(
            normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_INSUFFICIENT_USABLE_COHORT
        ),
        lower_cutoff=None,
        upper_cutoff=None,
        mean=None,
        population_variance=None,
        standard_deviation=None,
        distinct_post_winsor_value_count=0,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="insufficient cohort",
    ):
        type(impossible_insufficient).__post_init__(
            impossible_insufficient,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_positive_dispersion = _rehash_identity(
        result.identity,
        population_variance=Decimal("1"),
        standard_deviation=Decimal("1"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="zero-dispersion",
    ):
        type(impossible_positive_dispersion).__post_init__(
            impossible_positive_dispersion,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_all_zero_available = _rehash_identity(
        result.identity,
        outcome=normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE,
        lower_cutoff=Decimal("0"),
        upper_cutoff=Decimal("1"),
        mean=Decimal("0.5"),
        population_variance=Decimal("0.25"),
        standard_deviation=Decimal("0.5"),
        distinct_post_winsor_value_count=2,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="counts are inconsistent",
    ):
        type(impossible_all_zero_available).__post_init__(
            impossible_all_zero_available,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_zero_distinct = _rehash_identity(
        result.identity,
        distinct_post_winsor_value_count=0,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="zero-dispersion",
    ):
        type(impossible_zero_distinct).__post_init__(
            impossible_zero_distinct,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    overprecision_value = Decimal("1" * 51)
    overprecision_summary = _rehash_identity(
        result.identity,
        lower_cutoff=overprecision_value,
        upper_cutoff=overprecision_value,
        mean=overprecision_value,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="50-digit output context",
    ):
        type(overprecision_summary).__post_init__(
            overprecision_summary,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    for field_name in ("diagnostics_version", "policy_hash"):
        subclass_value = _TextSubclass(getattr(result.identity, field_name))
        forged_subclass = _rehash_identity(
            result.identity,
            **{field_name: subclass_value},
        )
        with pytest.raises(
            normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        ):
            type(forged_subclass).__post_init__(
                forged_subclass,
                normalization_module._IDENTITY_FACTORY_TOKEN,
            )

    insufficient = _build(*_zero_cohort(19)).identity
    overbound_count = _rehash_identity(
        insufficient,
        observation_count=(
            normalization_module.MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS + 1
        ),
        excluded_missing_count=(
            normalization_module.MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS
            + 1
            - insufficient.usable_count
        ),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="counts are inconsistent",
    ):
        type(overbound_count).__post_init__(
            overbound_count,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )


def test_standalone_available_identity_binds_summary_relationships():
    observations = (_zero(0),) + tuple(
        _signal(index, Decimal(50_000 * (index + 1)))
        for index in range(1, 20)
    )
    identity = _build(*observations).identity
    assert identity.outcome is (
        normalization_module.Form4StockSignalNormalizationOutcome.AVAILABLE
    )

    mean_outside_cutoffs = _rehash_identity(
        identity,
        mean=identity.upper_cutoff + Decimal("1"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="mean lies outside",
    ):
        type(mean_outside_cutoffs).__post_init__(
            mean_outside_cutoffs,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    wrong_standard_deviation = _rehash_identity(
        identity,
        standard_deviation=identity.standard_deviation + Decimal("1"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="standard deviation is inconsistent",
    ):
        type(wrong_standard_deviation).__post_init__(
            wrong_standard_deviation,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    collapsed_available_cutoffs = _rehash_identity(
        identity,
        lower_cutoff=identity.mean,
        upper_cutoff=identity.mean,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="availability gates",
    ):
        type(collapsed_available_cutoffs).__post_init__(
            collapsed_available_cutoffs,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_gross_variance = _rehash_identity(
        identity,
        lower_cutoff=Decimal("1"),
        upper_cutoff=Decimal("2"),
        mean=Decimal("1.5"),
        population_variance=Decimal("100"),
        standard_deviation=Decimal("10"),
        distinct_post_winsor_value_count=2,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="coarse range-squared cap",
    ):
        type(impossible_gross_variance).__post_init__(
            impossible_gross_variance,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_mixed_zero_dispersion = _rehash_identity(
        identity,
        outcome=(
            normalization_module.Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
        ),
        lower_cutoff=identity.mean,
        upper_cutoff=identity.mean,
        population_variance=Decimal("0"),
        standard_deviation=Decimal("0"),
        distinct_post_winsor_value_count=1,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="positive zero dispersion",
    ):
        type(impossible_mixed_zero_dispersion).__post_init__(
            impossible_mixed_zero_dispersion,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_nonpositive_mean = _rehash_identity(
        identity,
        signal_count=10,
        structural_zero_count=10,
        lower_cutoff=Decimal("0"),
        mean=Decimal("0"),
        distinct_post_winsor_value_count=2,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="positive upper cutoff must have a positive mean",
    ):
        type(impossible_nonpositive_mean).__post_init__(
            impossible_nonpositive_mean,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_signal_only_zero_floor = _rehash_identity(
        identity,
        signal_count=identity.usable_count,
        structural_zero_count=0,
        lower_cutoff=Decimal("0"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="lower cutoff is inconsistent with Type-7 zero mass",
    ):
        type(impossible_signal_only_zero_floor).__post_init__(
            impossible_signal_only_zero_floor,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_zero_mass_cutoff = _rehash_identity(
        identity,
        signal_count=1,
        structural_zero_count=19,
        distinct_post_winsor_value_count=2,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="lower cutoff is inconsistent with Type-7 zero mass",
    ):
        type(impossible_zero_mass_cutoff).__post_init__(
            impossible_zero_mass_cutoff,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_mean_for_counts = _rehash_identity(
        identity,
        signal_count=10,
        structural_zero_count=10,
        lower_cutoff=Decimal("0"),
        upper_cutoff=Decimal("1"),
        mean=Decimal("0.75"),
        population_variance=Decimal("0.1"),
        standard_deviation=(
            normalization_module._new_decimal_context().sqrt(Decimal("0.1"))
        ),
        distinct_post_winsor_value_count=2,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="mean exceeds the category-count bound",
    ):
        type(impossible_mean_for_counts).__post_init__(
            impossible_mean_for_counts,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )

    impossible_distinct_count = _rehash_identity(
        identity,
        signal_count=1,
        structural_zero_count=19,
        distinct_post_winsor_value_count=3,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="counts are inconsistent",
    ):
        type(impossible_distinct_count).__post_init__(
            impossible_distinct_count,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )


def test_standalone_row_refuses_impossible_numeric_shapes():
    result = _build(*_zero_cohort())
    row = result.rows[0]
    assert row.disposition is (
        normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
    )

    nonzero_structural = _rehash_row(
        row,
        raw_stock_score_diagnostic=Decimal("1"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="structural-zero output row",
    ):
        type(nonzero_structural).__post_init__(
            nonzero_structural,
            normalization_module._ROW_FACTORY_TOKEN,
        )

    normalized_without_winsorized = _rehash_row(
        row,
        winsorized_stock_score_diagnostic=None,
        normalized_stock_score_diagnostic=Decimal("1"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="requires a winsorized diagnostic",
    ):
        type(normalized_without_winsorized).__post_init__(
            normalized_without_winsorized,
            normalization_module._ROW_FACTORY_TOKEN,
        )

    overprecision_winsorized = _rehash_row(
        row,
        winsorized_stock_score_diagnostic=Decimal("1" * 51),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="50-digit output context",
    ):
        type(overprecision_winsorized).__post_init__(
            overprecision_winsorized,
            normalization_module._ROW_FACTORY_TOKEN,
        )

    integer_normalized = _rehash_row(
        row,
        normalized_stock_score_diagnostic=1,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="exact finite Decimal",
    ):
        type(integer_normalized).__post_init__(
            integer_normalized,
            normalization_module._ROW_FACTORY_TOKEN,
        )


def test_authority_and_look_properties_cannot_be_shadowed_per_instance():
    observation = _zero(0)
    for field_name in AUTHORITY_FIELDS:
        with pytest.raises(AttributeError):
            object.__setattr__(observation, field_name, True)
        assert getattr(observation, field_name) is False
    for field_name in ("authorized_outcome_looks", "consumed_outcome_looks"):
        for replacement in (1, True):
            with pytest.raises(AttributeError):
                object.__setattr__(observation, field_name, replacement)
        assert type(getattr(observation, field_name)) is int
        assert getattr(observation, field_name) == 0


def test_every_public_output_has_zero_authority_and_no_rank_or_seed():
    result = _build(*_zero_cohort())
    assert set(AUTHORITY_FIELDS) == set(normalization_module._BOOLEAN_AUTHORITY_FIELDS)
    targets = (*result.observations, *result.rows, result.identity, result)
    for target in targets:
        assert target.population_is_caller_declared is True
        assert target.canonical_population_verified is False
        assert target.role_ids_are_caller_declared is True
        assert all(getattr(target, name) is False for name in AUTHORITY_FIELDS)
        assert type(target.authorized_outcome_looks) is int
        assert target.authorized_outcome_looks == 0
        assert type(target.consumed_outcome_looks) is int
        assert target.consumed_outcome_looks == 0
    assert result.stock_score is None
    assert result.ranking is None
    assert result.seed_selection is None
    assert all(row.stock_score is None for row in result.rows)
    assert all(row.rank is None for row in result.rows)
    assert all(row.seed_selected is None for row in result.rows)


def test_builder_detaches_caller_alias_and_final_input_seal_is_load_bearing(
    monkeypatch,
):
    observation = _zero(0)
    result = _build(observation)
    payload_before = result.to_payload()
    object.__setattr__(observation, "raw_stock_score_diagnostic", Decimal("0.0"))
    assert result.to_payload() == payload_before
    assert result.observations[0].raw_stock_score_diagnostic.as_tuple() == Decimal("0").as_tuple()

    late_observation = _zero(1)
    real_constructor = normalization_module.Form4StockSignalNormalizationDiagnostics

    def mutate_after_result_construction(*args, **kwargs):
        built = real_constructor(*args, **kwargs)
        object.__setattr__(
            late_observation,
            "raw_stock_score_diagnostic",
            Decimal("0.0"),
        )
        return built

    monkeypatch.setattr(
        normalization_module,
        "Form4StockSignalNormalizationDiagnostics",
        mutate_after_result_construction,
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="unsealed|mutated|changed",
    ):
        _build(late_observation)


def test_kernel_is_independent_of_ambient_decimal_context():
    values = tuple(Decimal(index) for index in range(20))
    baseline = normalization_module._compute_normalization(values)
    hostile = Context(prec=3, rounding=ROUND_UP)
    hostile.traps[Inexact] = True
    with localcontext(hostile):
        observed = normalization_module._compute_normalization(values)
    assert observed == baseline


def test_resource_and_shape_preflights_run_before_observation_work(monkeypatch):
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="row-count bound",
    ):
        normalization_module._compute_normalization(
            (Decimal("0"),)
            * (normalization_module.MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS + 1)
        )

    reached_snapshot = False

    def snapshot_reached(_value):
        nonlocal reached_snapshot
        reached_snapshot = True
        raise AssertionError("snapshot ran before row-count preflight")

    monkeypatch.setattr(
        normalization_module,
        "MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS",
        1,
    )
    monkeypatch.setattr(normalization_module, "_snapshot_observation", snapshot_reached)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="row-count",
    ):
        _build(object(), object())
    assert reached_snapshot is False

    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="exact tuple",
    ):
        normalization_module.build_form4_stock_signal_normalization_diagnostics(
            [_zero(10)],
            evaluation_session=EVALUATION_SESSION,
            builder_git_commit=BUILDER_COMMIT,
        )


@pytest.mark.parametrize(
    "value",
    (
        True,
        1,
        1.0,
        "1",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("1" * 1025),
        Decimal("1e2049"),
    ),
)
def test_kernel_refuses_nonexact_invalid_or_unbounded_values(value):
    with pytest.raises(normalization_module.Form4StockSignalNormalizationDiagnosticsError):
        normalization_module._compute_normalization((value,))


def test_frozen_policy_guard_and_text_bounds_are_load_bearing(monkeypatch):
    observation = _zero(0)
    result = _build(*_zero_cohort())
    monkeypatch.setattr(
        normalization_module,
        "FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE",
        Decimal("0.02"),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="frozen",
    ):
        _build(observation)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="frozen",
    ):
        normalization_module._compute_normalization((Decimal("0"),) * 20)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="frozen",
    ):
        type(result.identity).__post_init__(
            result.identity,
            normalization_module._IDENTITY_FACTORY_TOKEN,
        )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="frozen",
    ):
        type(result).__post_init__(
            result,
            normalization_module._RESULT_FACTORY_TOKEN,
        )

    monkeypatch.undo()
    issuer_cik, _, share_class_id = _stock_key(50)
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="bounded canonical text",
    ):
        normalization_module.build_form4_stock_signal_normalization_observation(
            issuer_cik=issuer_cik,
            security_id="x" * 129,
            share_class_id=share_class_id,
            disposition=(
                normalization_module.Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
            ),
            synthetic_source_id=_source_id(50),
        )


@pytest.mark.parametrize(
    ("constant_name", "replacement"),
    (
        ("MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS", 10_001),
        ("MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS", 129),
        ("_MAX_NORMALIZATION_DECIMAL_DIGITS", 1_025),
        ("_MAX_NORMALIZATION_DECIMAL_ABS_EXPONENT", 2_049),
    ),
)
def test_frozen_policy_refuses_coherent_resource_rebinding(
    monkeypatch,
    constant_name,
    replacement,
):
    monkeypatch.setattr(normalization_module, constant_name, replacement)
    monkeypatch.setattr(
        normalization_module,
        "FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH",
        hash_payload(normalization_module._policy_payload()),
    )
    with pytest.raises(
        normalization_module.Form4StockSignalNormalizationDiagnosticsError,
        match="frozen",
    ):
        normalization_module._require_frozen_policy()


def test_module_is_offline_decimal_only_and_has_no_hidden_consumer():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imports == EXPECTED_MODULE_IMPORTS
    assert not any(
        isinstance(node, ast.Constant) and type(node.value) is float
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "eval", "exec", "float", "open"}
        for node in ast.walk(tree)
    )
    assert imports.isdisjoint(
        {
            "AlgorithmImports",
            "QuantConnect",
            "aiohttp",
            "alpaca",
            "backtest",
            "execution",
            "httpx",
            "math",
            "ml",
            "numpy",
            "outcomes",
            "pandas",
            "requests",
            "risk",
            "socket",
            "statistics",
            "urllib",
            "yfinance",
        }
    )
    assert {
        item.name
        for item in fields(
            normalization_module.Form4StockSignalNormalizationDiagnostics
        )
    } == {
        "identity",
        "observations",
        "rows",
        "outcome",
        "lower_cutoff",
        "upper_cutoff",
        "mean",
        "population_variance",
        "standard_deviation",
        "distinct_post_winsor_value_count",
        "stock_score",
        "ranking",
        "seed_selection",
    }


def test_public_exports_are_explicit_and_package_bound():
    assert tuple(normalization_module.__all__) == EXPECTED_PUBLIC_EXPORTS
    assert all(name in insider_package.__all__ for name in EXPECTED_PUBLIC_EXPORTS)
    assert all(
        getattr(insider_package, name) is getattr(normalization_module, name)
        for name in EXPECTED_PUBLIC_EXPORTS
    )
