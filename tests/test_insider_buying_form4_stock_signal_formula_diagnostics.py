"""Synthetic/offline tests for bounded Insider Buying IB-3A formulas.

IB-3A is an equation-conformance diagnostic only.  It cannot consume the
provisional IB-2D result, assert canonical event eligibility, normalize a
cross-section, select seeds, inspect outcomes, or authorize any operation.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from pathlib import Path

import pytest

import research.insider_buying as insider_package
from data.financial_primitives import exact_decimal_sum
from data.hashing import hash_payload
from research.insider_buying import (
    form4_stock_signal_formula_diagnostics as signal_module,
)


BUILDER_COMMIT = "d" * 40
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "insider_buying"
    / "form4_stock_signal_formula_diagnostics.py"
)
EXPECTED_MODULE_IMPORTS = {
    "__future__",
    "collections",
    "data.financial_primitives",
    "data.hashing",
    "dataclasses",
    "datetime",
    "decimal",
    "re",
    "research.insider_buying.contracts",
    "research.insider_buying.form4_provisional_lot_diagnostics",
    "threading",
    "weakref",
}
EXPECTED_PUBLIC_EXPORTS = (
    "FORM4_STOCK_SIGNAL_DECIMAL_PRECISION",
    "FORM4_STOCK_SIGNAL_DECIMAL_ROUNDING",
    "FORM4_STOCK_SIGNAL_DOLLAR_BREADTH_FORMULA",
    "FORM4_STOCK_SIGNAL_EVENT_SCORE_FORMULA",
    "FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_FRESHNESS_EVALUATION",
    "FORM4_STOCK_SIGNAL_FRESHNESS_FORMULA",
    "FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS",
    "FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS",
    "FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD",
    "FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_RAW_SCORE_FORMULA",
    "FORM4_STOCK_SIGNAL_SIZE_FORMULA",
    "MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS",
    "MAX_FORM4_STOCK_SIGNAL_EVENTS",
    "MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH",
    "MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES",
    "MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT",
    "MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS",
    "Form4StockSignalBreadthDiagnostics",
    "Form4StockSignalEventContribution",
    "Form4StockSignalFixtureEvent",
    "Form4StockSignalFormulaDiagnostics",
    "Form4StockSignalFormulaDiagnosticsError",
    "Form4StockSignalFormulaIdentity",
    "build_form4_stock_signal_fixture_event",
    "build_form4_stock_signal_formula_diagnostics",
)


def _event(
    sequence: int,
    *,
    issuer_cik: str = "0000123456",
    security_id: str = "security-common",
    share_class_id: str = "share-class-common",
    buyer_id: str = "buyer-1",
    transaction_date: date = date(2026, 8, 18),
    purchase_value_usd: Decimal = Decimal("50000"),
    age_trading_days: int = 0,
    normalized_role_ids: tuple[str, ...] = ("director",),
):
    return signal_module.build_form4_stock_signal_fixture_event(
        source_event_id=f"{sequence:064x}",
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        buyer_id=buyer_id,
        transaction_date=transaction_date,
        purchase_value_usd=purchase_value_usd,
        age_trading_days=age_trading_days,
        normalized_role_ids=normalized_role_ids,
    )


def _build(*events):
    return signal_module.build_form4_stock_signal_formula_diagnostics(
        events,
        builder_git_commit=BUILDER_COMMIT,
    )


def _contribution(result, source_event_id: str):
    return next(
        item
        for item in result.contributions
        if item.source_event_id == source_event_id
    )


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


def _rehash_identity(identity, **updates):
    changed = _forge(identity, **updates)
    digest = hash_payload(
        signal_module._project_output(changed.lineage_payload())
    )
    return _forge(
        changed,
        diagnostics_id=identity.diagnostics_id[:-16] + digest[:16],
    )


def _rehash_breadth(breadth, **updates):
    changed = _forge(breadth, **updates)
    return _forge(
        changed,
        breadth_id=hash_payload(
            signal_module._project_output(changed.lineage_payload())
        ),
    )


def test_ib3a_contract_and_numeric_policy_are_frozen():
    assert signal_module.FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION == (
        "INSETF-IB3A-FORM4-STOCK-SIGNAL-FORMULA-DIAGNOSTICS-v1"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD == Decimal(
        "50000"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS == 20
    assert signal_module.FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS == 30
    assert signal_module.FORM4_STOCK_SIGNAL_DECIMAL_PRECISION == 50
    assert signal_module.FORM4_STOCK_SIGNAL_DECIMAL_ROUNDING == "ROUND_HALF_EVEN"
    assert signal_module.FORM4_STOCK_SIGNAL_SIZE_FORMULA == (
        "ln(1 + purchase_value_usd / 50000)"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_FRESHNESS_FORMULA == (
        "exp(-ln(2) * age_trading_days / 20)"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_FRESHNESS_EVALUATION == (
        "exact whole half-lives times a 50-digit fractional-half-life "
        "projection"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_EVENT_SCORE_FORMULA == (
        "event_size * freshness"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_RAW_SCORE_FORMULA == (
        "sum(event_score for value >= 50000 and "
        "0 <= age_trading_days <= 30)"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_DOLLAR_BREADTH_FORMULA == (
        "(total_purchase_value - largest_buyer_purchase_value) "
        "/ total_purchase_value"
    )
    assert signal_module.FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH == (
        "56eddf2fd800f022102c8c705211dc402"
        "fe52cef3a4ba7eb39ea8959d7b0ac2e"
    )
    assert signal_module.MAX_FORM4_STOCK_SIGNAL_EVENTS == 10_000
    assert signal_module.MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT == 16
    assert signal_module.MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS == 128
    assert signal_module.MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS == 10_000
    assert signal_module.MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES == 4_000_000
    assert signal_module.MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH == 32


def test_fixture_event_is_factory_created_and_hash_bound():
    event = _event(1)
    assert event.source_event_id == f"{1:064x}"
    assert event.purchase_value_usd == Decimal("50000")
    assert event.age_trading_days == 0
    assert event.normalized_role_ids == ("director",)
    assert len(event.fixture_event_id) == 64
    assert _event(1) == event

    unsealed_copy = _forge(event)
    assert unsealed_copy == event
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _build(unsealed_copy)

    payload_change = _forge(event, buyer_id="buyer-2")
    assert payload_change.fixture_event_id == event.fixture_event_id
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        signal_module.build_form4_stock_signal_formula_diagnostics(
            (payload_change,),
            builder_git_commit=BUILDER_COMMIT,
        )


def test_fixture_process_seal_detects_equal_decimal_representation_change():
    event = _event(1)
    decimal_tuple = event.purchase_value_usd.as_tuple()
    representation_variant = Decimal(
        (
            decimal_tuple.sign,
            decimal_tuple.digits + (0,),
            decimal_tuple.exponent - 1,
        )
    )
    assert representation_variant == event.purchase_value_usd
    assert representation_variant.as_tuple() != decimal_tuple

    forged = _forge(event, purchase_value_usd=representation_variant)
    assert forged.fixture_event_id == event.fixture_event_id
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _build(forged)


def test_public_builder_refuses_exact_real_ib2d_result_before_formula(
    monkeypatch,
):
    from tests import (
        test_insider_buying_form4_provisional_lot_diagnostics as ib2d_tests,
    )

    *_upstream, diagnostics = ib2d_tests._build(monkeypatch)

    def reached_formula(*_args, **_kwargs):
        raise AssertionError("IB-2D reached the IB-3A formula path")

    if hasattr(signal_module, "_event_formula"):
        monkeypatch.setattr(signal_module, "_event_formula", reached_formula)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="synthetic|fixture|IB-2D",
    ):
        signal_module.build_form4_stock_signal_formula_diagnostics(
            diagnostics,
            builder_git_commit=BUILDER_COMMIT,
        )


@pytest.mark.parametrize(
    ("purchase_value", "expected_size"),
    (
        (
            Decimal("50000"),
            Decimal(
                "0.69314718055994530941723212145817656807550013436026"
            ),
        ),
        (
            Decimal("100000"),
            Decimal(
                "1.0986122886681096913952452369225257046474905578227"
            ),
        ),
        (
            Decimal("150000"),
            Decimal(
                "1.3862943611198906188344642429163531361510002687205"
            ),
        ),
    ),
)
def test_event_size_has_fifty_digit_ln2_ln3_ln4_goldens(
    purchase_value,
    expected_size,
):
    result = _build(_event(1, purchase_value_usd=purchase_value))
    contribution = result.contributions[0]
    assert contribution.event_size == expected_size
    assert contribution.freshness == Decimal("1")
    assert contribution.event_score == expected_size


@pytest.mark.parametrize(
    ("age", "expected_freshness", "expected_score"),
    (
        (
            0,
            Decimal("1"),
            Decimal(
                "0.69314718055994530941723212145817656807550013436026"
            ),
        ),
        (
            1,
            Decimal(
                "0.96593632892484555106514431292046389939073731287925"
            ),
            Decimal(
                "0.66953604299468064223351872037314097861689229509599"
            ),
        ),
        (
            10,
            Decimal(
                "0.70710678118654752440084436210484903928483593768847"
            ),
            Decimal(
                "0.49012907173427359585695086181761669064573034954953"
            ),
        ),
        (
            20,
            Decimal("0.5"),
            Decimal(
                "0.34657359027997265470861606072908828403775006718013"
            ),
        ),
        (
            30,
            Decimal(
                "0.35355339059327376220042218105242451964241796884424"
            ),
            Decimal(
                "0.24506453586713679792847543090880834532286517477477"
            ),
        ),
    ),
)
def test_freshness_and_event_score_have_half_life_goldens(
    age,
    expected_freshness,
    expected_score,
):
    result = _build(_event(1, age_trading_days=age))
    contribution = result.contributions[0]
    assert contribution.freshness == expected_freshness
    assert contribution.event_score == expected_score


def test_threshold_and_lookback_route_exhaustively_without_dropping_rows():
    included = _event(1)
    below = _event(
        2,
        purchase_value_usd=Decimal("49999.99"),
        buyer_id="buyer-2",
    )
    outside = _event(3, age_trading_days=31, buyer_id="buyer-3")
    result = _build(outside, below, included)

    assert len(result.events) == len(result.contributions) == 3
    by_id = {
        item.source_event_id: item for item in result.contributions
    }
    assert by_id[included.source_event_id].meets_minimum_purchase_value is True
    assert by_id[included.source_event_id].inside_lookback is True
    assert by_id[included.source_event_id].included_in_raw_score is True
    assert by_id[below.source_event_id].meets_minimum_purchase_value is False
    assert by_id[below.source_event_id].inside_lookback is True
    assert by_id[below.source_event_id].included_in_raw_score is False
    assert by_id[outside.source_event_id].meets_minimum_purchase_value is True
    assert by_id[outside.source_event_id].inside_lookback is False
    assert by_id[outside.source_event_id].included_in_raw_score is False
    assert by_id[below.source_event_id].event_score > 0
    assert by_id[outside.source_event_id].event_score > 0
    assert result.raw_stock_score_diagnostic == by_id[
        included.source_event_id
    ].event_score
    assert result.breadth.included_event_count == 1
    assert result.breadth.unique_buyer_ids == (included.buyer_id,)
    assert result.breadth.normalized_role_ids == included.normalized_role_ids
    assert result.breadth.transaction_dates == (included.transaction_date,)
    assert result.breadth.total_purchase_value_usd == Decimal("50000")


def test_at_least_one_event_must_enter_the_raw_score():
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="included|qualifying|raw score",
    ):
        _build(_event(1, purchase_value_usd=Decimal("49999.99")))
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="included|qualifying|raw score",
    ):
        _build(_event(1, age_trading_days=31))


@pytest.mark.parametrize("age", (-1, True, Decimal("1"), 1.0, "1"))
def test_fixture_refuses_non_exact_or_negative_age(age):
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _event(1, age_trading_days=age)


def test_fixture_age_bound_is_inclusive_and_load_bearing():
    maximum = signal_module.MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS
    boundary = _event(
        2,
        buyer_id="buyer-2",
        age_trading_days=maximum,
    )
    result = _build(_event(1), boundary)
    assert result.events[-1] == boundary
    assert result.contributions[-1].age_trading_days == maximum
    assert result.contributions[-1].inside_lookback is False
    assert result.contributions[-1].event_score > 0
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _event(1, age_trading_days=maximum + 1)


def test_fixture_decimal_and_role_resource_boundaries_are_inclusive():
    bounded_value = Decimal("1" * 256)
    roles = tuple(f"role-{index:02d}" for index in range(16))
    event = _event(
        1,
        security_id="s" * 128,
        purchase_value_usd=bounded_value,
        normalized_role_ids=roles,
    )
    assert event.security_id == "s" * 128
    assert event.purchase_value_usd == bounded_value
    assert event.normalized_role_ids == roles
    assert _build(event).events == (event,)


def test_two_maximum_input_decimals_build_a_wider_exact_aggregate():
    bounded_value = Decimal("9" * 256)
    result = _build(
        _event(1, buyer_id="buyer-1", purchase_value_usd=bounded_value),
        _event(2, buyer_id="buyer-2", purchase_value_usd=bounded_value),
    )
    expected_total = exact_decimal_sum(
        (bounded_value, bounded_value),
        name="test IB-3A wide aggregate",
    )
    assert len(expected_total.as_tuple().digits) == 257
    assert result.breadth.total_purchase_value_usd == expected_total
    assert result.breadth.largest_buyer_purchase_value_usd == bounded_value
    assert result.breadth.dollar_breadth == Decimal("0.5")


@pytest.mark.parametrize(
    "smaller_value",
    (
        Decimal("50000"),
        Decimal("9" * 256 + "e-251"),
    ),
)
def test_mixed_exponent_inputs_build_their_wide_exact_aggregate(smaller_value):
    large_value = Decimal("8" * 256 + "e256")
    result = _build(
        _event(1, buyer_id="buyer-1", purchase_value_usd=large_value),
        _event(2, buyer_id="buyer-2", purchase_value_usd=smaller_value),
    )
    expected_total = exact_decimal_sum(
        (large_value, smaller_value),
        name="test IB-3A mixed-exponent aggregate",
    )
    assert result.breadth.total_purchase_value_usd == expected_total
    assert result.breadth.largest_buyer_purchase_value_usd == large_value
    assert result.raw_stock_score_diagnostic > 0


def test_input_exponent_bound_builds_extreme_included_and_excluded_rows():
    included = _event(1)
    tiny_outside = _event(
        2,
        buyer_id="buyer-2",
        purchase_value_usd=Decimal("1e-256"),
        age_trading_days=signal_module.MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS,
    )
    retained = _build(included, tiny_outside)
    tiny_contribution = _contribution(
        retained,
        tiny_outside.source_event_id,
    )
    assert tiny_outside in retained.events
    assert tiny_contribution.event_size > 0
    assert tiny_contribution.freshness > 0
    assert tiny_contribution.event_score > 0
    assert tiny_contribution.meets_minimum_purchase_value is False
    assert tiny_contribution.inside_lookback is False
    assert tiny_contribution.included_in_raw_score is False

    large = _build(_event(3, purchase_value_usd=Decimal("1e256")))
    assert large.events[0].purchase_value_usd == Decimal("1e256")
    assert large.contributions[0].event_size > 0


@pytest.mark.parametrize(
    "purchase_value",
    (
        50000,
        50000.0,
        "50000",
        True,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("0"),
        Decimal("-1"),
        Decimal("1" * 257),
        Decimal("1e257"),
        Decimal("1e-257"),
    ),
)
def test_fixture_refuses_invalid_or_unbounded_purchase_value(purchase_value):
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _event(1, purchase_value_usd=purchase_value)


@pytest.mark.parametrize(
    "roles",
    (
        [],
        (),
        ("director", "director"),
        ("officer", "director"),
        ("",),
        (" director",),
        ("director ",),
        (1,),
        tuple(f"role-{index:02d}" for index in range(17)),
        ("r" * 65,),
    ),
)
def test_fixture_refuses_noncanonical_opaque_role_inventory(roles):
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _event(1, normalized_role_ids=roles)


@pytest.mark.parametrize(
    "updates",
    (
        {"source_event_id": "A" * 64},
        {"source_event_id": "a" * 63},
        {"issuer_cik": "123456789"},
        {"security_id": ""},
        {"security_id": " security-common"},
        {"share_class_id": "share-class-common "},
        {"buyer_id": ""},
        {"buyer_id": "buyer\n1"},
        {"transaction_date": "2026-08-18"},
        {"transaction_date": datetime(2026, 8, 18)},
        {"normalized_role_ids": ("r" * 129,)},
        {"security_id": "s" * 129},
    ),
)
def test_fixture_refuses_noncanonical_identity_and_date_fields(updates):
    kwargs = {
        "source_event_id": f"{1:064x}",
        "issuer_cik": "0000123456",
        "security_id": "security-common",
        "share_class_id": "share-class-common",
        "buyer_id": "buyer-1",
        "transaction_date": date(2026, 8, 18),
        "purchase_value_usd": Decimal("50000"),
        "age_trading_days": 0,
        "normalized_role_ids": ("director",),
    }
    kwargs.update(updates)
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        signal_module.build_form4_stock_signal_fixture_event(**kwargs)


def test_main_builder_requires_exact_tuple_nonempty_and_canonical_commit():
    event = _event(1)
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        signal_module.build_form4_stock_signal_formula_diagnostics(
            [event],
            builder_git_commit=BUILDER_COMMIT,
        )
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        _build()
    for invalid_commit in ("d" * 39, "D" * 40, 1, None):
        with pytest.raises(
            signal_module.Form4StockSignalFormulaDiagnosticsError
        ):
            signal_module.build_form4_stock_signal_formula_diagnostics(
                (event,),
                builder_git_commit=invalid_commit,
            )


def test_formula_is_independent_of_ambient_decimal_context():
    events = (
        _event(1, purchase_value_usd=Decimal("50000"), age_trading_days=1),
        _event(
            2,
            buyer_id="buyer-2",
            purchase_value_usd=Decimal("100000"),
            age_trading_days=30,
        ),
    )
    expected = _build(*events)
    with localcontext() as context:
        context.prec = 3
        context.Emax = 9
        context.Emin = -9
        context.traps[InvalidOperation] = True
        context.traps[DivisionByZero] = True
        actual = _build(*events)
    assert actual.to_payload() == expected.to_payload()


def test_formula_is_independent_of_preimport_decimal_default_context():
    code = """
from datetime import date
from decimal import DefaultContext, Decimal, ROUND_UP

DefaultContext.prec = 3
DefaultContext.rounding = ROUND_UP
DefaultContext.Emin = -9
DefaultContext.Emax = 9
DefaultContext.capitals = 0
DefaultContext.clamp = 1
for signal in DefaultContext.flags:
    DefaultContext.flags[signal] = True
    DefaultContext.traps[signal] = False

from research.insider_buying.form4_stock_signal_formula_diagnostics import (
    build_form4_stock_signal_fixture_event,
    build_form4_stock_signal_formula_diagnostics,
)

event = build_form4_stock_signal_fixture_event(
    source_event_id="a" * 64,
    issuer_cik="0000123456",
    security_id="security-common",
    share_class_id="share-class-common",
    buyer_id="buyer-1",
    transaction_date=date(2026, 8, 18),
    purchase_value_usd=Decimal("50000"),
    age_trading_days=1,
    normalized_role_ids=("director",),
)
result = build_form4_stock_signal_formula_diagnostics(
    (event,),
    builder_git_commit="d" * 40,
)
item = result.contributions[0]
print(item.freshness)
print(item.event_score)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=MODULE_PATH.parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stderr == ""
    assert completed.stdout.splitlines() == [
        "0.96593632892484555106514431292046389939073731287925",
        "0.66953604299468064223351872037314097861689229509599",
    ]


def test_events_and_contributions_are_canonical_under_input_permutation():
    events = (
        _event(3, buyer_id="buyer-3"),
        _event(1, buyer_id="buyer-1"),
        _event(2, buyer_id="buyer-2"),
    )
    forward = _build(*events)
    reverse = _build(*reversed(events))
    assert forward.to_payload() == reverse.to_payload()
    assert [item.source_event_id for item in forward.events] == sorted(
        item.source_event_id for item in events
    )
    assert [item.source_event_id for item in forward.contributions] == sorted(
        item.source_event_id for item in events
    )


def test_raw_score_is_the_exact_sum_per_single_stock_and_class():
    result = _build(
        _event(
            1,
            buyer_id="buyer-1",
            purchase_value_usd=Decimal("50000"),
            age_trading_days=0,
        ),
        _event(
            2,
            buyer_id="buyer-2",
            purchase_value_usd=Decimal("100000"),
            age_trading_days=10,
        ),
        _event(
            3,
            buyer_id="buyer-3",
            purchase_value_usd=Decimal("150000"),
            age_trading_days=20,
        ),
    )
    expected = exact_decimal_sum(
        (
            item.event_score
            for item in result.contributions
            if item.included_in_raw_score
        ),
        name="test IB-3A raw score",
    )
    assert result.raw_stock_score_diagnostic == expected
    assert result.issuer_cik == "0000123456"
    assert result.security_id == "security-common"
    assert result.share_class_id == "share-class-common"
    assert result.stock_score is None


@pytest.mark.parametrize(
    ("field_name", "different_value"),
    (
        ("issuer_cik", "0000654321"),
        ("security_id", "security-other"),
        ("share_class_id", "share-class-other"),
    ),
)
def test_builder_refuses_mixed_stock_or_share_class_keys(
    field_name,
    different_value,
):
    first = _event(1)
    second = _event(2, **{field_name: different_value})
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="one|mixed|issuer|security|class",
    ):
        _build(first, second)


def test_builder_refuses_duplicate_source_or_fixture_events():
    event = _event(1)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="duplicate|unique|order",
    ):
        _build(event, event)

    same_source = signal_module.build_form4_stock_signal_fixture_event(
        source_event_id=event.source_event_id,
        issuer_cik=event.issuer_cik,
        security_id=event.security_id,
        share_class_id=event.share_class_id,
        buyer_id="buyer-2",
        transaction_date=event.transaction_date,
        purchase_value_usd=event.purchase_value_usd,
        age_trading_days=event.age_trading_days,
        normalized_role_ids=event.normalized_role_ids,
    )
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="duplicate|unique|source",
    ):
        _build(event, same_source)


@pytest.mark.parametrize("purchase_value", ("50000", "30000"))
def test_builder_refuses_unaggregated_duplicate_buyer_date_keys(
    purchase_value,
):
    duplicates = (
        _event(1, purchase_value_usd=Decimal(purchase_value)),
        _event(2, purchase_value_usd=Decimal(purchase_value)),
    )
    included = _event(
        3,
        buyer_id="buyer-2",
        transaction_date=date(2026, 8, 19),
    )
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="post-lot|aggregation|duplicate|combined",
    ):
        _build(*duplicates, included)


def test_buyer_role_and_date_breadth_are_distinct_inventories():
    first_date = date(2026, 8, 18)
    second_date = date(2026, 8, 19)
    result = _build(
        _event(
            1,
            buyer_id="buyer-1",
            transaction_date=first_date,
            normalized_role_ids=("ceo", "director"),
        ),
        _event(
            2,
            buyer_id="buyer-1",
            transaction_date=second_date,
            normalized_role_ids=("director",),
        ),
        _event(
            3,
            buyer_id="buyer-2",
            transaction_date=second_date,
            normalized_role_ids=("cfo",),
        ),
    )
    breadth = result.breadth
    assert breadth.included_event_count == 3
    assert breadth.unique_buyer_ids == ("buyer-1", "buyer-2")
    assert breadth.buyer_breadth == 2
    assert breadth.normalized_role_ids == ("ceo", "cfo", "director")
    assert breadth.role_breadth == 3
    assert breadth.transaction_dates == (first_date, second_date)
    assert breadth.date_breadth == 2


@pytest.mark.parametrize(
    ("values", "expected_total", "expected_largest", "expected_breadth"),
    (
        (("50000",), "50000", "50000", "0"),
        (("50000", "50000"), "100000", "50000", "0.5"),
        (("150000", "100000"), "250000", "150000", "0.4"),
        (
            ("50000", "50000", "50000"),
            "150000",
            "50000",
            "0.66666666666666666666666666666666666666666666666667",
        ),
    ),
)
def test_dollar_breadth_has_golden_single_equal_and_concentrated_cases(
    values,
    expected_total,
    expected_largest,
    expected_breadth,
):
    events = tuple(
        _event(
            index,
            buyer_id=f"buyer-{index}",
            purchase_value_usd=Decimal(value),
        )
        for index, value in enumerate(values, start=1)
    )
    breadth = _build(*events).breadth
    assert breadth.total_purchase_value_usd == Decimal(expected_total)
    assert breadth.largest_buyer_purchase_value_usd == Decimal(expected_largest)
    assert breadth.dollar_breadth == Decimal(expected_breadth)


def test_dollar_breadth_aggregates_each_buyer_before_finding_the_largest():
    result = _build(
        _event(1, buyer_id="buyer-a", purchase_value_usd=Decimal("75000")),
        _event(
            2,
            buyer_id="buyer-a",
            purchase_value_usd=Decimal("75000"),
            transaction_date=date(2026, 8, 19),
        ),
        _event(3, buyer_id="buyer-b", purchase_value_usd=Decimal("100000")),
    )
    breadth = result.breadth
    assert breadth.total_purchase_value_usd == Decimal("250000")
    assert breadth.largest_buyer_purchase_value_usd == Decimal("150000")
    assert breadth.dollar_breadth == Decimal("0.4")


def test_breadth_dimensions_never_change_formula_or_raw_score():
    narrow = _build(
        _event(
            1,
            buyer_id="buyer-1",
            normalized_role_ids=("role-a",),
            transaction_date=date(2026, 8, 18),
        ),
        _event(
            2,
            buyer_id="buyer-1",
            normalized_role_ids=("role-a",),
            transaction_date=date(2026, 8, 19),
        ),
    )
    broad = _build(
        _event(
            1,
            buyer_id="buyer-1",
            normalized_role_ids=("role-a", "role-b"),
            transaction_date=date(2026, 8, 18),
        ),
        _event(
            2,
            buyer_id="buyer-2",
            normalized_role_ids=("role-c",),
            transaction_date=date(2026, 8, 18),
        ),
    )
    assert [item.event_size for item in narrow.contributions] == [
        item.event_size for item in broad.contributions
    ]
    assert [item.freshness for item in narrow.contributions] == [
        item.freshness for item in broad.contributions
    ]
    assert [item.event_score for item in narrow.contributions] == [
        item.event_score for item in broad.contributions
    ]
    assert narrow.raw_stock_score_diagnostic == broad.raw_stock_score_diagnostic
    assert narrow.breadth.buyer_breadth == 1
    assert broad.breadth.buyer_breadth == 2
    assert narrow.breadth.role_breadth == 1
    assert broad.breadth.role_breadth == 3
    assert narrow.breadth.date_breadth == 2
    assert broad.breadth.date_breadth == 1


def test_every_output_is_hash_bound_and_stock_score_remains_unavailable():
    result = _build(_event(1), _event(2, buyer_id="buyer-2"))
    assert result.stock_score is None
    assert len(result.identity.diagnostics_id) > 16
    assert len(result.identity.fixture_event_inventory_hash) == 64
    assert len(result.identity.contribution_inventory_hash) == 64
    assert len(result.identity.breadth_hash) == 64
    assert len(result.breadth.breadth_id) == 64
    assert all(len(item.fixture_event_id) == 64 for item in result.events)
    assert all(len(item.contribution_id) == 64 for item in result.contributions)
    assert all(
        item.fixture_event_id
        == hash_payload(signal_module._project_output(item.lineage_payload()))
        for item in result.events
    )
    assert all(
        item.contribution_id
        == hash_payload(signal_module._project_output(item.lineage_payload()))
        for item in result.contributions
    )
    assert result.breadth.breadth_id == hash_payload(
        signal_module._project_output(result.breadth.lineage_payload())
    )
    assert result.identity.fixture_event_inventory_hash == hash_payload(
        signal_module._project_output(
            [item.to_payload() for item in result.events]
        )
    )
    assert result.identity.contribution_inventory_hash == hash_payload(
        signal_module._project_output(
            [item.to_payload() for item in result.contributions]
        )
    )
    assert result.identity.breadth_hash == hash_payload(
        signal_module._project_output(result.breadth.to_payload())
    )
    assert result.identity.diagnostics_id == (
        "form4-stock-signal-formula-diagnostics-"
        + hash_payload(
            signal_module._project_output(result.identity.lineage_payload())
        )[:16]
    )


def test_every_public_result_type_is_factory_gated_and_replayable():
    result = _build(_event(1), _event(2, buyer_id="buyer-2"))
    values_and_tokens = (
        (result.events[0], signal_module._FIXTURE_EVENT_FACTORY_TOKEN),
        (result.contributions[0], signal_module._CONTRIBUTION_FACTORY_TOKEN),
        (result.breadth, signal_module._BREADTH_FACTORY_TOKEN),
        (result.identity, signal_module._IDENTITY_FACTORY_TOKEN),
        (result, signal_module._RESULT_FACTORY_TOKEN),
    )
    for value, token in values_and_tokens:
        with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
            type(value)(**vars(value))
        type(value).__post_init__(value, token)


@pytest.mark.parametrize(
    ("selector", "field_name", "replacement", "token_name"),
    (
        ("event", "fixture_event_id", "0" * 64, "_FIXTURE_EVENT_FACTORY_TOKEN"),
        (
            "event",
            "normalized_role_ids",
            ["director"],
            "_FIXTURE_EVENT_FACTORY_TOKEN",
        ),
        (
            "contribution",
            "contribution_id",
            "0" * 64,
            "_CONTRIBUTION_FACTORY_TOKEN",
        ),
        (
            "contribution",
            "event_score",
            Decimal("0"),
            "_CONTRIBUTION_FACTORY_TOKEN",
        ),
        ("breadth", "breadth_id", "0" * 64, "_BREADTH_FACTORY_TOKEN"),
        ("breadth", "unique_buyer_ids", ["buyer-1"], "_BREADTH_FACTORY_TOKEN"),
        (
            "identity",
            "diagnostics_id",
            "form4-stock-signal-formula-diagnostics-" + "0" * 16,
            "_IDENTITY_FACTORY_TOKEN",
        ),
        (
            "identity",
            "builder_git_commit",
            "D" * 40,
            "_IDENTITY_FACTORY_TOKEN",
        ),
        ("result", "stock_score", Decimal("0"), "_RESULT_FACTORY_TOKEN"),
        ("result", "events", [], "_RESULT_FACTORY_TOKEN"),
    ),
)
def test_constructor_replay_refuses_hash_value_and_runtime_type_tampering(
    selector,
    field_name,
    replacement,
    token_name,
):
    result = _build(_event(1))
    selected = {
        "event": result.events[0],
        "contribution": result.contributions[0],
        "breadth": result.breadth,
        "identity": result.identity,
        "result": result,
    }[selector]
    forged = _forge(selected, **{field_name: replacement})
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(forged).__post_init__(forged, getattr(signal_module, token_name))


@pytest.mark.parametrize("field_name", ("security_id", "share_class_id"))
def test_result_replay_refuses_value_equal_text_subclass(field_name):
    class EqualText(str):
        pass

    result = _build(_event(1))
    forged = _forge(
        result,
        **{field_name: EqualText(getattr(result, field_name))},
    )
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(forged).__post_init__(
            forged,
            signal_module._RESULT_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    "field_name",
    ("diagnostics_version", "numeric_policy_hash", "diagnostics_id"),
)
def test_identity_replay_refuses_value_equal_text_subclass(field_name):
    class EqualText(str):
        pass

    identity = _build(_event(1)).identity
    forged = _forge(
        identity,
        **{field_name: EqualText(getattr(identity, field_name))},
    )
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(forged).__post_init__(
            forged,
            signal_module._IDENTITY_FACTORY_TOKEN,
        )


AUTHORITY_FIELDS = (
    "role_normalization_verified",
    "role_normalization_authorized",
    "ib2_completion_authorized",
    "official_security_master_compatibility_verified",
    "qc_symbol_id_mapping_verified",
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
    "authenticated_amendment_supersession_verified",
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
    "canonical_stock_score_authorized",
)


def test_every_authority_gate_is_false_and_both_look_counts_are_exact_zero():
    assert set(AUTHORITY_FIELDS) == set(signal_module._BOOLEAN_AUTHORITY_FIELDS)
    result = _build(_event(1))
    targets = (
        *result.events,
        *result.contributions,
        result.breadth,
        result.identity,
        result,
    )
    for target in targets:
        assert target.role_ids_are_caller_declared is True
        assert all(getattr(target, field) is False for field in AUTHORITY_FIELDS)
        assert type(target.authorized_outcome_looks) is int
        assert target.authorized_outcome_looks == 0
        assert type(target.consumed_outcome_looks) is int
        assert target.consumed_outcome_looks == 0


@pytest.mark.parametrize("field_name", AUTHORITY_FIELDS)
def test_identity_replay_refuses_every_individual_authority_escalation(field_name):
    identity = _build(_event(1)).identity
    forged = _rehash_identity(identity, **{field_name: True})
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="authority|authorized|verified",
    ):
        type(forged).__post_init__(
            forged,
            signal_module._IDENTITY_FACTORY_TOKEN,
        )


@pytest.mark.parametrize("replacement", (False, 1, "true", None))
def test_identity_replay_refuses_caller_role_provenance_erasure(replacement):
    identity = _build(_event(1)).identity
    forged = _rehash_identity(
        identity,
        role_ids_are_caller_declared=replacement,
    )
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(forged).__post_init__(
            forged,
            signal_module._IDENTITY_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    "field_name",
    ("authorized_outcome_looks", "consumed_outcome_looks"),
)
@pytest.mark.parametrize("replacement", (1, True))
def test_identity_replay_refuses_nonzero_or_boolean_look_counts(
    field_name,
    replacement,
):
    identity = _build(_event(1)).identity
    forged = _rehash_identity(identity, **{field_name: replacement})
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(forged).__post_init__(
            forged,
            signal_module._IDENTITY_FACTORY_TOKEN,
        )


def test_replay_count_claims_cannot_exceed_the_event_resource_bound():
    result = _build(_event(1))
    excessive = signal_module.MAX_FORM4_STOCK_SIGNAL_EVENTS + 1
    identity = _rehash_identity(
        result.identity,
        fixture_event_count=excessive,
        contribution_count=excessive,
        included_event_count=excessive,
    )
    breadth = _rehash_breadth(
        result.breadth,
        included_event_count=excessive,
    )
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(identity).__post_init__(
            identity,
            signal_module._IDENTITY_FACTORY_TOKEN,
        )
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(breadth).__post_init__(
            breadth,
            signal_module._BREADTH_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    "updates",
    (
        {
            "normalized_role_ids": tuple(
                f"role-{index:02d}" for index in range(17)
            ),
            "role_breadth": 17,
        },
        {
            "transaction_dates": (
                date(2026, 8, 18),
                date(2026, 8, 19),
            ),
            "date_breadth": 2,
        },
    ),
)
def test_breadth_replay_enforces_per_event_role_and_date_bounds(updates):
    breadth = _rehash_breadth(_build(_event(1)).breadth, **updates)
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(breadth).__post_init__(
            breadth,
            signal_module._BREADTH_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    "updates",
    (
        {
            "largest_buyer_purchase_value_usd": Decimal("25000"),
            "dollar_breadth": Decimal("0.5"),
        },
        {
            "total_purchase_value_usd": Decimal("49999"),
            "largest_buyer_purchase_value_usd": Decimal("49999"),
            "dollar_breadth": Decimal("0"),
        },
    ),
)
def test_breadth_replay_refuses_impossible_included_value_claims(updates):
    breadth = _rehash_breadth(_build(_event(1)).breadth, **updates)
    with pytest.raises(signal_module.Form4StockSignalFormulaDiagnosticsError):
        type(breadth).__post_init__(
            breadth,
            signal_module._BREADTH_FACTORY_TOKEN,
        )


def test_event_count_preflight_runs_before_any_formula_work(monkeypatch):
    monkeypatch.setattr(signal_module, "MAX_FORM4_STOCK_SIGNAL_EVENTS", 1)

    def reached_formula(*_args, **_kwargs):
        raise AssertionError("formula ran before the event-count preflight")

    monkeypatch.setattr(signal_module, "_event_formula", reached_formula)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="event|count|bound",
    ):
        _build(_event(1), _event(2))


@pytest.mark.parametrize(
    ("constant_name", "value", "message"),
    (
        ("MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES", ["x"], "node"),
        ("MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH", [["x"]], "depth"),
        ("MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS", "xx", "text"),
    ),
)
def test_projection_resource_guards_are_load_bearing(
    monkeypatch,
    constant_name,
    value,
    message,
):
    monkeypatch.setattr(signal_module, constant_name, 1 if message != "depth" else 0)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match=message,
    ):
        signal_module._project_output(value)


def test_projection_refuses_cycles_and_non_text_keys():
    cyclic = []
    cyclic.append(cyclic)
    for value, message in ((cyclic, "cycle"), ({1: "value"}, "non-text key")):
        with pytest.raises(
            signal_module.Form4StockSignalFormulaDiagnosticsError,
            match=message,
        ):
            signal_module._project_output(value)


def test_module_is_exactly_offline_decimal_only_and_has_no_hidden_score_stage():
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
        and node.func.id in {
            "__import__",
            "eval",
            "exec",
            "float",
            "open",
        }
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
            "urllib",
            "yfinance",
        }
    )
    assert result_schema_names() == {
        "breadth",
        "contributions",
        "events",
        "identity",
        "issuer_cik",
        "raw_stock_score_diagnostic",
        "security_id",
        "share_class_id",
        "stock_score",
    }


def result_schema_names():
    return {
        item.name
        for item in fields(signal_module.Form4StockSignalFormulaDiagnostics)
    }


def test_public_exports_are_explicit_and_package_bound():
    assert tuple(signal_module.__all__) == EXPECTED_PUBLIC_EXPORTS
    expected = set(EXPECTED_PUBLIC_EXPORTS)
    assert all(name in insider_package.__all__ for name in expected)
    assert all(
        getattr(insider_package, name) is getattr(signal_module, name)
        for name in expected
    )


# --- Claude review additions (2026-09-10): guards that survived targeted mutation ---


def _rehash_contribution(contribution, **updates):
    changed = _forge(contribution, **updates)
    return _forge(
        changed,
        contribution_id=hash_payload(
            signal_module._project_output(changed.lineage_payload())
        ),
    )


def _replay_result(result) -> None:
    type(result).__post_init__(result, signal_module._RESULT_FACTORY_TOKEN)


def _replay_contribution(contribution) -> None:
    type(contribution).__post_init__(
        contribution,
        signal_module._CONTRIBUTION_FACTORY_TOKEN,
    )


def _replay_breadth(breadth) -> None:
    type(breadth).__post_init__(breadth, signal_module._BREADTH_FACTORY_TOKEN)


def _replay_identity(identity) -> None:
    type(identity).__post_init__(identity, signal_module._IDENTITY_FACTORY_TOKEN)


def _identity_for(result, *, events=None, contributions=None, breadth=None, raw=None):
    """Rebuild a replay-consistent identity for forged result parts."""
    return signal_module._build_identity(
        events=result.events if events is None else events,
        contributions=result.contributions if contributions is None else contributions,
        breadth=result.breadth if breadth is None else breadth,
        raw_stock_score_diagnostic=(
            result.raw_stock_score_diagnostic if raw is None else raw
        ),
        builder_git_commit=result.identity.builder_git_commit,
    )


def test_frozen_decimal_context_isolates_trapping_default_context():
    """IB3A-R06's dangerous direction: a trapping DefaultContext must not refuse
    a valid event.  The existing pre-import test disables every trap, so it
    cannot detect the loss of the explicit ``flags``/``traps`` arguments."""
    code = """
from datetime import date
from decimal import DefaultContext, Decimal, Inexact, Rounded

DefaultContext.traps[Inexact] = True
DefaultContext.traps[Rounded] = True

from research.insider_buying.form4_stock_signal_formula_diagnostics import (
    build_form4_stock_signal_fixture_event,
    build_form4_stock_signal_formula_diagnostics,
)

event = build_form4_stock_signal_fixture_event(
    source_event_id="a" * 64,
    issuer_cik="0000123456",
    security_id="security-common",
    share_class_id="share-class-common",
    buyer_id="buyer-1",
    transaction_date=date(2026, 8, 18),
    purchase_value_usd=Decimal("50000"),
    age_trading_days=1,
    normalized_role_ids=("director",),
)
result = build_form4_stock_signal_formula_diagnostics(
    (event,),
    builder_git_commit="d" * 40,
)
print(result.contributions[0].freshness)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=MODULE_PATH.parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = _build(_event(1, age_trading_days=1)).contributions[0].freshness
    assert completed.stdout.strip() == str(expected)


def test_process_seal_detects_in_place_equal_decimal_representation_change():
    """The sealed-event fingerprint is the only guard here: ``decimal_text``
    canonicalizes the representation, so the fixture-event ID still binds."""
    event = _event(1)
    decimal_tuple = event.purchase_value_usd.as_tuple()
    variant = Decimal(
        (decimal_tuple.sign, decimal_tuple.digits + (0,), decimal_tuple.exponent - 1)
    )
    assert variant == event.purchase_value_usd
    assert variant.as_tuple() != decimal_tuple

    object.__setattr__(event, "purchase_value_usd", variant)
    assert event.fixture_event_id == hash_payload(
        signal_module._project_output(event.lineage_payload())
    )
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="unsealed or mutated",
    ):
        _build(event)


@pytest.mark.parametrize(
    "updates",
    (
        {"meets_minimum_purchase_value": False},
        {"inside_lookback": False},
        {"included_in_raw_score": False},
    ),
    ids=("minimum", "lookback", "included"),
)
def test_contribution_constructor_refuses_forged_routing_flags(updates):
    result = _build(_event(1))
    forged = _rehash_contribution(result.contributions[0], **updates)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="threshold or lookback routing is inconsistent",
    ):
        _replay_contribution(forged)


def test_result_replay_refuses_a_self_consistent_substituted_contribution():
    """A contribution can be internally coherent yet describe another event."""
    result = _build(_event(1, purchase_value_usd=Decimal("50000")))
    other = _build(_event(2, purchase_value_usd=Decimal("100000")))
    substituted = _rehash_contribution(
        other.contributions[0],
        source_event_id=result.contributions[0].source_event_id,
        fixture_event_id=result.contributions[0].fixture_event_id,
    )
    _replay_contribution(substituted)

    contributions = (substituted,)
    forged = _forge(
        result,
        contributions=contributions,
        identity=_identity_for(result, contributions=contributions),
    )
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="do not replay from their fixture events",
    ):
        _replay_result(forged)


def test_result_replay_requires_canonical_event_order():
    result = _build(_event(1), _event(2, buyer_id="buyer-2"))
    events = tuple(reversed(result.events))
    contributions = tuple(reversed(result.contributions))
    forged = _forge(
        result,
        events=events,
        contributions=contributions,
        identity=_identity_for(result, events=events, contributions=contributions),
    )
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="canonical order",
    ):
        _replay_result(forged)


def test_result_replay_refuses_a_self_consistent_substituted_breadth():
    result = _build(_event(1), _event(2, buyer_id="buyer-2"))
    other = _build(
        _event(1),
        _event(2, buyer_id="buyer-2", purchase_value_usd=Decimal("150000")),
    )
    assert other.breadth.total_purchase_value_usd != result.breadth.total_purchase_value_usd
    _replay_breadth(other.breadth)

    forged = _forge(
        result,
        breadth=other.breadth,
        identity=_identity_for(result, breadth=other.breadth),
    )
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="breadth diagnostics do not replay",
    ):
        _replay_result(forged)


def test_result_replay_refuses_a_self_consistent_substituted_identity():
    result = _build(_event(1))
    forged_identity = _rehash_identity(result.identity, issuer_cik="0000654321")
    _replay_identity(forged_identity)

    forged = _forge(result, identity=forged_identity)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="identity does not replay",
    ):
        _replay_result(forged)


def test_result_replay_binds_the_raw_score_to_its_included_contributions():
    result = _build(_event(1))
    inflated = result.raw_stock_score_diagnostic + Decimal("1")
    forged = _forge(result, raw_stock_score_diagnostic=inflated)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="raw stock-score diagnostic is inconsistent",
    ):
        _replay_result(forged)


@pytest.mark.parametrize("field_name", ("security_id", "share_class_id"))
def test_result_replay_binds_the_stock_key_to_its_events(field_name):
    result = _build(_event(1))
    forged = _forge(result, **{field_name: "substituted-identifier"})
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="result stock key is inconsistent",
    ):
        _replay_result(forged)


def test_seal_detects_representation_drift_during_formula_evaluation(
    monkeypatch,
):
    """An equal-valued representation change replays identically through every
    formula, so only a fingerprint comparison can see it.  The refusal comes
    from the result constructor's own seal check, which makes the later
    post-build recheck defence in depth rather than the load-bearing guard."""
    event = _event(1)
    decimal_tuple = event.purchase_value_usd.as_tuple()
    variant = Decimal(
        (decimal_tuple.sign, decimal_tuple.digits + (0,), decimal_tuple.exponent - 1)
    )
    real_build_identity = signal_module._build_identity

    def mutate_then_build(**kwargs):
        object.__setattr__(event, "purchase_value_usd", variant)
        return real_build_identity(**kwargs)

    monkeypatch.setattr(signal_module, "_build_identity", mutate_then_build)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="changed during formula evaluation|unsealed or mutated",
    ):
        _build(event)


@pytest.mark.parametrize(
    ("updates", "expected"),
    (
        ({"buyer_breadth": 2}, "buyer breadth count is inconsistent"),
        ({"role_breadth": 2}, "role breadth count is inconsistent"),
        ({"date_breadth": 2}, "date breadth count is inconsistent"),
    ),
)
def test_breadth_counts_are_bound_to_their_inventories(updates, expected):
    result = _build(_event(1))
    forged = _rehash_breadth(result.breadth, **updates)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match=expected,
    ):
        _replay_breadth(forged)


def test_breadth_buyer_count_cannot_exceed_the_included_event_count():
    result = _build(_event(1), _event(2, buyer_id="buyer-2"))
    breadth = result.breadth
    assert breadth.buyer_breadth == breadth.included_event_count == 2
    forged = _rehash_breadth(breadth, included_event_count=1)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="buyer breadth exceeds included event count",
    ):
        _replay_breadth(forged)


@pytest.mark.parametrize(
    "updates",
    (
        {"contribution_count": 2},
        {"included_event_count": 2},
        {"included_event_count": 0},
    ),
    ids=("contribution-count", "included-above-fixture", "included-zero"),
)
def test_identity_counts_are_mutually_consistent(updates):
    result = _build(_event(1))
    assert result.identity.fixture_event_count == 1
    forged = _rehash_identity(result.identity, **updates)
    with pytest.raises(
        signal_module.Form4StockSignalFormulaDiagnosticsError,
        match="identity counts are inconsistent",
    ):
        _replay_identity(forged)
