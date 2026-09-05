from __future__ import annotations

import copy
import dataclasses
import gc
import hashlib
import json
import pickle
import shutil
import weakref
from datetime import date
from decimal import (
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    getcontext,
    localcontext,
)
from pathlib import Path

import pytest

import research.analyst_revisions_v2.power_calibration_protocol as module
from research.analyst_revisions_v2.power_calibration_protocol import (
    CALIBRATION_AXIS_SHA256,
    CALIBRATION_SESSION_COUNT,
    NORMAL_SUM_SQUARED,
    PROTOCOL_ID_PREFIX,
    TEST_SESSION_CAPACITY,
    Z_0800,
    Z_0975,
    PowerCalibrationProtocol,
    PowerCalibrationProtocolError,
    ProvisionalPowerDisposition,
    derive_provisional_power_requirement,
    load_power_calibration_protocol,
    render_expected_power_calibration_protocol,
    require_loaded_power_calibration_protocol,
)


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
FILENAMES = {
    "protocol": "arv2_stock_power_calibration_protocol.structural.json",
    "map": "arv2_global_rating_map.structural.json",
    "matched": "arv2_global_matched_comparison.structural.json",
    "successor": "arv2_stock_historical_successor.structural.json",
    "stock": "arv2_stock_historical.structural.json",
    "folds": "arv2_stock_walk_forward_folds.structural.json",
    "plan": "arv2_qc_first.draft.json",
    "base": "arv2_round0.draft.json",
}
PINNED_4C_ARTIFACT_HASHES = {
    "map": "630cc822fa83d7aba15920cfb8f37863f6d6fffa262e26ac96074e8526391f4e",
    "matched": "40b164e3e2944053eaaaaf1a651e34dfb335a4cbc8aeca2ee3f67ecdc9e8dffa",
    "successor": "51718ee5ae278d1254e8efb01b2acdd9c6cbe51741dd72d5b5969c3b48576647",
    "stock": "34d1e71548bc6850a02590596594944dad3fadb38954067f2cc2d00dcaa86bc8",
    "folds": "fecd984ad937fed57b860b15fdcb9cc994ff59ab62c3b72d5160ab62b342953c",
    "plan": "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081",
    "base": "b40a76f5f2f7726f328f1e444a41ecb0670234055a7c9c7245a26ffab601af2f",
}
EXPECTED_PROTOCOL_ID = "arv2-stock-power-calibration-protocol-0ba6b7d745783796"
EXPECTED_PROTOCOL_HASH = (
    "0ba6b7d7457837967b5b8b7966cc22c2ddd00f4dbf4a7269b9aaa562baac757f"
)
EXPECTED_PROTOCOL_ARTIFACT_SHA256 = (
    "ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13"
)
EXPECTED_NORMAL_CONSTANTS = (
    "1.9599639845400542355245944305205515279555500778695",
    "0.84162123357291420517870612136324810062629753400888",
    "7.8488797343490889511625145685327253191071246220413",
)


def _paths(root: Path = SPEC_ROOT) -> dict[str, Path]:
    return {name: root / filename for name, filename in FILENAMES.items()}


def _component_pairs(
    protocol: PowerCalibrationProtocol, counts: tuple[int, ...]
) -> tuple[tuple[str, int], ...]:
    return tuple(zip(protocol.calibration_session_axis, counts, strict=True))


def _load(root: Path = SPEC_ROOT) -> PowerCalibrationProtocol:
    paths = _paths(root)
    return load_power_calibration_protocol(
        paths["protocol"],
        map_path=paths["map"],
        matched_contract_path=paths["matched"],
        successor_spec_path=paths["successor"],
        parent_stock_spec_path=paths["stock"],
        fold_manifest_path=paths["folds"],
        qc_first_plan_path=paths["plan"],
    )


def _clone(tmp_path: Path) -> Path:
    root = tmp_path / "specs"
    root.mkdir(parents=True)
    for filename in FILENAMES.values():
        shutil.copyfile(SPEC_ROOT / filename, root / filename)
    return root


def _rewrite_protocol(path: Path, mutate) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    raw["protocol_id"] = None
    raw["protocol_hash"] = None
    compact = json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(compact).hexdigest()
    raw["protocol_hash"] = digest
    raw["protocol_id"] = PROTOCOL_ID_PREFIX + digest[:16]
    path.write_text(
        json.dumps(
            raw,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return raw


@pytest.fixture
def protocol() -> PowerCalibrationProtocol:
    return _load()


def test_checked_in_protocol_is_exact_renderer_output():
    path = _paths()["protocol"]
    assert path.read_text(encoding="utf-8") == (
        render_expected_power_calibration_protocol()
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        EXPECTED_PROTOCOL_ARTIFACT_SHA256
    )


def test_protocol_identity_is_content_derived():
    raw = json.loads(_paths()["protocol"].read_text(encoding="utf-8"))
    declared_id = raw["protocol_id"]
    declared_hash = raw["protocol_hash"]
    raw["protocol_id"] = None
    raw["protocol_hash"] = None
    digest = hashlib.sha256(
        json.dumps(
            raw,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert declared_id == EXPECTED_PROTOCOL_ID
    assert declared_hash == EXPECTED_PROTOCOL_HASH
    assert declared_hash == digest
    assert declared_id == PROTOCOL_ID_PREFIX + digest[:16]


def test_exact_owner_policy_scope_and_no_authority(protocol):
    definition = protocol.definition
    effect = definition["owner_policy"]["minimum_meaningful_effect"]
    assert effect["basis_points"] == {"numerator": 10, "denominator": 1}
    assert effect["return_per_adjusted_score_unit"] == {
        "numerator": 1,
        "denominator": 1000,
    }
    assert definition["owner_policy"]["target_power"] == {
        "numerator": 4,
        "denominator": 5,
    }
    assert definition["owner_policy"]["two_sided_size"] == {
        "numerator": 1,
        "denominator": 20,
    }
    assert definition["claim_scope"]["primary_gate_id"] == (
        "bullish_20_session_fama_macbeth"
    )
    excluded = definition["claim_scope"]["does_not_establish_power_for"]
    assert "three_gate_conjunction" in excluded
    assert "the_strategy_lane_as_a_whole" in excluded
    assert all(value is False for value in protocol.capabilities.values())
    assert protocol.calibration_input_access_available is False
    assert protocol.source_access_available is False
    assert protocol.outcome_access_available is False
    assert protocol.authoritative_receipt_available is False
    assert protocol.power_plan_binding_available is False
    assert protocol.qc_action_available is False
    assert protocol.result_disposition_available is False
    assert protocol.deployment_available is False
    assert protocol.orders_available is False


def test_numeric_receipt_and_action_bindings_remain_null(protocol):
    assert all(
        value is None
        for value in protocol.definition["external_bindings"].values()
    )
    current = protocol.definition["deferred_ARV2_4D_B"]["current_numeric_values"]
    assert all(value is None for value in current.values())
    assert protocol.definition["deferred_ARV2_4D_B"][
        "separate_authority_required"
    ] is True


def test_calendar_axis_and_maturity_are_exactly_derived(protocol):
    assert len(protocol.calibration_session_axis) == CALIBRATION_SESSION_COUNT
    assert protocol.calibration_session_axis[0] == "2018-01-31"
    assert protocol.calibration_session_axis[-1] == "2019-12-31"
    payload = json.dumps(
        protocol.calibration_session_axis,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == CALIBRATION_AXIS_SHA256
    maturity = protocol.definition["calibration_source"]["maturity_separation"]
    assert maturity["last_included_h20_outcome_session"] == "2020-01-30"
    assert maturity[
        "validation_end_boundary_h20_outcome_would_equal_first_test_session_and_is_excluded"
    ] is True


def test_protocol_extends_the_unchanged_4c_dag_as_one_leaf(protocol):
    graph = protocol.lineage_graph
    assert len(graph) == 9
    assert graph["global_map"] == ("strategy_pdf",)
    assert graph["stock_v2"] == (
        "strategy_pdf",
        "qc_plan",
        "stock_v1",
        "fold_manifest",
        "global_map",
        "matched_contract",
    )
    assert graph["power_protocol"] == (
        "strategy_pdf",
        "qc_plan",
        "stock_v1",
        "fold_manifest",
        "global_map",
        "matched_contract",
        "stock_v2",
    )
    assert not any("power_protocol" in parents for node, parents in graph.items() if node != "power_protocol")


def test_reviewed_4c_and_ancestor_artifact_bytes_are_unchanged():
    for name, expected in PINNED_4C_ARTIFACT_HASHES.items():
        assert hashlib.sha256(_paths()[name].read_bytes()).hexdigest() == expected
    stock = json.loads(_paths()["stock"].read_text(encoding="utf-8"))
    successor = json.loads(_paths()["successor"].read_text(encoding="utf-8"))
    assert stock["power_definition"]["current_execution_authorized"] is False
    assert successor["external_bindings"]["power_plan_sha256"] is None


def test_hac_and_component_methods_are_fully_frozen(protocol):
    hac = protocol.definition["h20_HAC_protocol"]
    assert hac["maximum_lag_sessions"] == 20
    assert hac["autocovariance_denominator"] == "N_not_lag_pair_count"
    assert hac["lag_weights"] == (
        "Bartlett_weight_l=(21-l)/21_for_l_1_through_20"
    )
    context = hac["arithmetic_context"]
    assert context == {
        "precision": 50,
        "rounding": "ROUND_HALF_EVEN",
        "Emin": -999999,
        "Emax": 999999,
        "capitals": 1,
        "clamp": 0,
        "fresh_local_context": True,
        "flags_cleared_before_use": True,
        "enabled_traps": (
            "InvalidOperation",
            "DivisionByZero",
            "Overflow",
        ),
        "binary_float_bool_and_nonfinite_inputs": "forbidden",
        "ambient_context_or_flags_may_not_change_result_or_leak": True,
    }
    component = protocol.definition["component_floor_protocol"]
    assert component["component_definition"] == (
        "firm_specific_primary_h20_Fama_MacBeth_design_connected_component_instances_per_complete_axis_session_built_from_all_point_in_time_eligible_security_decision_rows_including_structural_zero_neutral_rows_with_no_score_or_sign_filter_after_all_required_nonoutcome_eligibility_common_event_and_cross_date_component_refusals_before_outcome_join_and_before_global_comparator_matching_with_neutral_rows_as_singletons"
    )
    assert component["fixed_rank_for_483_sessions"] == 25
    assert component["honest_zero_count"] == "included_as_zero"
    assert component["selection_role"].startswith("none_never_a_per_date_filter")
    assert component["required_connected_components"] == (
        "max(50,required_valid_dates*q05_components_per_date)"
    )
    receipt = protocol.definition["deferred_ARV2_4D_B"]
    allowed = protocol.definition["calibration_source"][
        "allowed_numeric_receipt_outputs"
    ]
    for field in (
        "component_count_census_sha256",
        "component_count_census_session_count",
    ):
        assert field in allowed
        assert field in receipt["required_receipt_fields"]
        assert receipt["current_numeric_values"][field] is None


def test_normal_constants_and_capacity_are_exact(protocol):
    normal = protocol.definition["normal_planning_formula"]
    assert (Z_0975, Z_0800, NORMAL_SUM_SQUARED) == EXPECTED_NORMAL_CONSTANTS
    assert normal["z_0_975"] == Z_0975
    assert normal["z_0_800"] == Z_0800
    assert normal["squared_sum"] == NORMAL_SUM_SQUARED
    assert normal["fixed_h20_test_session_capacity"] == TEST_SESSION_CAPACITY
    assert normal["capacity_comparison"] == (
        "required_valid_dates_less_than_or_equal_to_1388_is_within_capacity_greater_than_1388_is_underpowered"
    )
    assert normal["within_capacity"] == (
        "FEASIBLE_FIXED_DESIGN_pending_authenticated_receipt"
    )
    assert normal["over_capacity"] == "UNDERPOWERED_FIXED_DESIGN_no_launch"
    assert normal["evaluation_order"] == (
        "inside_the_fresh_context_construct_exact_Decimal_constants_compute_effect_times_effect_then_Omega_times_squared_sum_then_divide_and_apply_ROUND_CEILING"
    )
    with localcontext() as context:
        context.prec = 50
        expected = (Decimal(Z_0975) + Decimal(Z_0800)) ** 2
    assert expected == Decimal(NORMAL_SUM_SQUARED)


def test_executable_decimal_context_exactly_matches_the_frozen_contract():
    context = module._fresh_decimal_context()
    assert context.prec == 50
    assert context.rounding == ROUND_HALF_EVEN
    assert context.Emin == -999999
    assert context.Emax == 999999
    assert context.capitals == 1
    assert context.clamp == 0
    assert {signal for signal, enabled in context.traps.items() if enabled} == {
        InvalidOperation,
        DivisionByZero,
        Overflow,
    }
    assert not any(context.flags.values())


def test_private_frozen_authority_templates_are_immutable():
    with pytest.raises(TypeError):
        module._EXTERNAL_BINDINGS["dataset_id"] = "forged"
    with pytest.raises(TypeError):
        module._CAPABILITIES["outcome_access"] = True


def test_nested_protocol_state_is_immutable(protocol):
    with pytest.raises(TypeError):
        protocol.definition["owner_policy"]["target_power"]["numerator"] = 9
    with pytest.raises(TypeError):
        protocol.lineage_graph["power_protocol"] = ()
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        protocol.protocol_hash = "0" * 64


def test_provisional_planning_arithmetic_and_pooled_component_units(protocol):
    result = derive_provisional_power_requirement(
        protocol,
        long_run_variance=Decimal("0.00001"),
        per_session_component_counts=_component_pairs(protocol, (3,) * 483),
    )
    assert result.long_run_variance == Decimal("0.00001")
    assert result.raw_required_valid_dates == 79
    assert result.required_valid_dates == 79
    assert result.q05_components_per_date == 3
    assert result.required_connected_components == 237
    assert result.fixed_h20_test_session_capacity == TEST_SESSION_CAPACITY
    assert result.disposition is (
        ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
    )
    assert result.authoritative is False
    assert result.power_plan_sha256 is None
    assert result.receipt_id is None


def test_absolute_floor_and_honest_zero_component_count(protocol):
    counts = (0,) * 25 + (100,) * (483 - 25)
    result = derive_provisional_power_requirement(
        protocol,
        long_run_variance=Decimal("0.000000001"),
        per_session_component_counts=_component_pairs(protocol, counts),
    )
    assert result.raw_required_valid_dates == 1
    assert result.required_valid_dates == 50
    assert result.q05_components_per_date == 0
    assert result.required_connected_components == 50


def test_absolute_date_floor_drives_the_component_floor(protocol):
    result = derive_provisional_power_requirement(
        protocol,
        long_run_variance=Decimal("0.000000001"),
        per_session_component_counts=_component_pairs(protocol, (3,) * 483),
    )
    assert result.raw_required_valid_dates == 1
    assert result.required_valid_dates == 50
    assert result.q05_components_per_date == 3
    assert result.required_connected_components == 150


def test_nearest_rank_uses_the_25th_smallest_of_all_483_dates(protocol):
    counts = tuple(reversed((0,) * 24 + (7,) + (100,) * (483 - 25)))
    result = derive_provisional_power_requirement(
        protocol,
        long_run_variance=Decimal("0.00001"),
        per_session_component_counts=_component_pairs(protocol, counts),
    )
    assert result.q05_components_per_date == 7
    assert result.required_connected_components == 79 * 7


@pytest.mark.parametrize(
    "counts,expected",
    (
        ((7,), 7),
        (tuple(range(20)), 0),
        (tuple(range(21)), 1),
        (tuple(range(40)), 1),
        (tuple(range(41)), 2),
        ((4, 2, 2, 9, 2), 2),
    ),
)
def test_nearest_rank_lower_fifth_boundaries(counts, expected):
    assert module._nearest_rank_lower_fifth(counts) == expected


@pytest.mark.parametrize("counts", ((), (True,), (1.0,), (-1,), ("1",)))
def test_nearest_rank_refuses_invalid_counts(counts):
    with pytest.raises(PowerCalibrationProtocolError):
        module._nearest_rank_lower_fifth(counts)


@pytest.mark.parametrize(
    "variance",
    (
        1,
        0.1,
        Decimal("0"),
        Decimal("-0.1"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ),
)
def test_provisional_planning_refuses_invalid_variance(protocol, variance):
    with pytest.raises(PowerCalibrationProtocolError):
        derive_provisional_power_requirement(
            protocol,
            long_run_variance=variance,
            per_session_component_counts=_component_pairs(protocol, (1,) * 483),
        )


@pytest.mark.parametrize(
    "counts",
    (
        [1] * 483,
        (1,) * 482,
        (1,) * 484,
        (1,) * 482 + (True,),
        (1,) * 482 + (1.0,),
        (1,) * 482 + (-1,),
    ),
)
def test_provisional_planning_requires_an_exact_complete_component_census(
    protocol, counts
):
    with pytest.raises(PowerCalibrationProtocolError):
        derive_provisional_power_requirement(
            protocol,
            long_run_variance=Decimal("0.00001"),
            per_session_component_counts=counts,
        )


@pytest.mark.parametrize(
    "replace_index,replacement",
    (
        (0, ("2018-01-30", 1)),
        (1, ("2018-02-01", True)),
        (2, ("2018-02-02", 1.0)),
        (3, ("2018-02-05", -1)),
        (4, ["2018-02-06", 1]),
        (5, ("2018-02-07", 1, 2)),
    ),
)
def test_component_census_pairs_must_match_each_exact_axis_position(
    protocol, replace_index, replacement
):
    pairs = list(_component_pairs(protocol, (1,) * 483))
    pairs[replace_index] = replacement
    with pytest.raises(PowerCalibrationProtocolError, match="pair every exact"):
        derive_provisional_power_requirement(
            protocol,
            long_run_variance=Decimal("0.00001"),
            per_session_component_counts=tuple(pairs),
        )


@pytest.mark.parametrize(
    "variance,expected_dates,expected_disposition",
    (
        (
            Decimal(
                "0.00017684052335847230949274228529845986715910476260250"
            ),
            1388,
            ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT,
        ),
        (
            Decimal(
                "0.00017684052335847230949274228529845986715910476260251"
            ),
            1389,
            ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH,
        ),
    ),
)
def test_fixed_capacity_boundary_never_clamps_or_extends(
    protocol, variance, expected_dates, expected_disposition
):
    result = derive_provisional_power_requirement(
        protocol,
        long_run_variance=variance,
        per_session_component_counts=_component_pairs(protocol, (1,) * 483),
    )
    assert result.raw_required_valid_dates == expected_dates
    assert result.required_valid_dates == expected_dates
    assert result.disposition is expected_disposition


def test_planning_uses_a_fresh_decimal_context_without_ambient_leak(protocol):
    process_context_before = getcontext().copy()
    boundary_variance = Decimal(
        "0.000010065130652247343263635908169004560162513887785013"
    )
    ordinary = derive_provisional_power_requirement(
        protocol,
        long_run_variance=boundary_variance,
        per_session_component_counts=_component_pairs(protocol, (3,) * 483),
    )
    assert ordinary.raw_required_valid_dates == 80
    with localcontext() as ambient:
        ambient.prec = 6
        ambient.rounding = ROUND_FLOOR
        ambient.Emin = -9
        ambient.Emax = 9
        ambient.capitals = 0
        ambient.clamp = 1
        ambient.traps[Inexact] = False
        Decimal(1) / Decimal(7)
        before = ambient.copy()
        hostile = derive_provisional_power_requirement(
            protocol,
            long_run_variance=boundary_variance,
            per_session_component_counts=_component_pairs(protocol, (3,) * 483),
        )
        assert ambient.prec == before.prec
        assert ambient.rounding == before.rounding
        assert ambient.Emin == before.Emin
        assert ambient.Emax == before.Emax
        assert ambient.capitals == before.capitals
        assert ambient.clamp == before.clamp
        assert ambient.flags == before.flags
        assert ambient.traps == before.traps
    assert hostile == ordinary
    process_context_after = getcontext()
    assert (
        process_context_after.prec,
        process_context_after.rounding,
        process_context_after.Emin,
        process_context_after.Emax,
        process_context_after.capitals,
        process_context_after.clamp,
    ) == (
        process_context_before.prec,
        process_context_before.rounding,
        process_context_before.Emin,
        process_context_before.Emax,
        process_context_before.capitals,
        process_context_before.clamp,
    )
    assert process_context_after.flags == process_context_before.flags
    assert process_context_after.traps == process_context_before.traps


def test_provisional_result_cannot_be_constructed_or_replaced_as_authoritative(
    protocol,
):
    with pytest.raises(TypeError):
        module.ProvisionalPowerRequirement()
    with pytest.raises(TypeError):
        module.ProvisionalPowerRequirement(
            long_run_variance=Decimal("0.00001"),
            raw_required_valid_dates=79,
            required_valid_dates=79,
            q05_components_per_date=3,
            required_connected_components=237,
            fixed_h20_test_session_capacity=1388,
            disposition=ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT,
            authoritative=True,
            power_plan_sha256="forged",
            receipt_id="forged",
        )
    result = derive_provisional_power_requirement(
        protocol,
        long_run_variance=Decimal("0.00001"),
        per_session_component_counts=_component_pairs(protocol, (3,) * 483),
    )
    with pytest.raises(TypeError):
        dataclasses.replace(result, required_valid_dates=1)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        result.authoritative = True


def test_caller_cannot_override_frozen_policy_arguments(protocol):
    with pytest.raises(TypeError):
        derive_provisional_power_requirement(
            protocol,
            long_run_variance=Decimal("0.00001"),
            per_session_component_counts=_component_pairs(protocol, (1,) * 483),
            effect=Decimal("0.01"),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda raw: raw["owner_policy"]["minimum_meaningful_effect"][
            "basis_points"
        ].__setitem__("numerator", 5),
        lambda raw: raw["owner_policy"]["target_power"].__setitem__(
            "numerator", 3
        ),
        lambda raw: raw["owner_policy"]["two_sided_size"].__setitem__(
            "denominator", 10
        ),
        lambda raw: raw["claim_scope"].__setitem__(
            "claim", "lane_level_exact_power"
        ),
        lambda raw: raw["calibration_source"]["boundary_source"].__setitem__(
            "validation_end_exclusive", "2020-01-03"
        ),
        lambda raw: raw["component_floor_protocol"].__setitem__(
            "method", "interpolated_Type_7"
        ),
        lambda raw: raw["normal_planning_formula"].__setitem__(
            "over_capacity", "extend_test_period"
        ),
        lambda raw: raw["deferred_ARV2_4D_B"]["current_numeric_values"].__setitem__(
            "required_valid_dates", 50
        ),
        lambda raw: raw["external_bindings"].__setitem__("dataset_id", "forged"),
        lambda raw: raw["capabilities"].__setitem__("outcome_access", True),
        lambda raw: raw.__setitem__("status", "evaluation_ready"),
        lambda raw: raw.__setitem__("unknown_field", "not_allowed"),
        lambda raw: raw["acyclic_lineage"]["ordered_nodes"][-1].__setitem__(
            "parents", ["stock_v2"]
        ),
    ),
)
def test_correctly_rehashed_policy_weakening_is_refused(tmp_path, mutation):
    root = _clone(tmp_path)
    _rewrite_protocol(_paths(root)["protocol"], mutation)
    with pytest.raises(PowerCalibrationProtocolError):
        _load(root)


@pytest.mark.parametrize(
    "mutate_bytes",
    (
        lambda payload: b"\xef\xbb\xbf" + payload,
        lambda payload: payload.replace(b"\n", b"\r\n"),
        lambda payload: b" " + payload,
        lambda payload: payload + b" ",
        lambda payload: payload.replace(
            b'"horizon_sessions": 20', b'"horizon_sessions": 20.0', 1
        ),
        lambda payload: payload.replace(
            b'"horizon_sessions": 20', b'"horizon_sessions": NaN', 1
        ),
        lambda payload: b'{"schema":"duplicate",' + payload[1:],
        lambda payload: payload[:-2] + b"\xff\n",
        lambda payload: payload.replace(b"{\n", b"{  \n", 1),
    ),
)
def test_noncanonical_or_malformed_protocol_bytes_are_refused(
    tmp_path, mutate_bytes
):
    root = _clone(tmp_path)
    path = _paths(root)["protocol"]
    path.write_bytes(mutate_bytes(path.read_bytes()))
    with pytest.raises(PowerCalibrationProtocolError):
        _load(root)


@pytest.mark.parametrize("field", ("protocol_id", "protocol_hash"))
def test_wrong_declared_identity_is_refused(tmp_path, field):
    root = _clone(tmp_path)
    path = _paths(root)["protocol"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw[field] = "0" * (64 if field == "protocol_hash" else len(raw[field]))
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(PowerCalibrationProtocolError):
        _load(root)


def test_unstable_protocol_read_is_refused(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    target = _paths(root)["protocol"].resolve()
    original = Path.read_bytes
    reads = 0

    def unstable(path):
        nonlocal reads
        payload = original(path)
        if path.resolve() == target:
            reads += 1
            if reads == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(Path, "read_bytes", unstable)
    with pytest.raises(PowerCalibrationProtocolError, match="changed while being read"):
        _load(root)


def test_interior_complete_session_axis_drift_is_refused(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    original = module.trading_sessions

    def drifted_axis(start, end):
        sessions = list(original(start, end))
        if start.isoformat() == "2018-01-31" and end.isoformat() == "2020-01-02":
            sessions[100] = date.fromisoformat("2018-07-04")
        return tuple(sessions)

    monkeypatch.setattr(module, "trading_sessions", drifted_axis)
    with pytest.raises(PowerCalibrationProtocolError, match="session axis changed"):
        _load(root)


@pytest.mark.parametrize(
    "anchor,wrong_session,error",
    (
        (
            "2018-01-02",
            "2018-01-30",
            "calibration start no longer matches its purge",
        ),
        (
            "2019-12-31",
            "2020-01-31",
            "last calibration outcome maturity changed",
        ),
        (
            "2020-01-02",
            "2020-02-03",
            "first test session no longer matches its embargo",
        ),
    ),
)
def test_calibration_maturity_or_excluded_boundary_drift_is_refused(
    tmp_path, monkeypatch, anchor, wrong_session, error
):
    root = _clone(tmp_path)
    original = module.resolve_nth_session_after

    def drifted_maturity(candidate, count):
        if candidate == anchor and count == 20:
            return wrong_session
        return original(candidate, count)

    monkeypatch.setattr(module, "resolve_nth_session_after", drifted_maturity)
    with pytest.raises(PowerCalibrationProtocolError, match=error):
        _load(root)


def test_mutation_during_nested_parent_revalidation_is_refused(
    tmp_path, monkeypatch
):
    root = _clone(tmp_path)
    path = _paths(root)["protocol"]
    original = module.require_loaded_global_benchmark_contract

    def mutate_after_parent_check(parent):
        result = original(parent)
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module,
        "require_loaded_global_benchmark_contract",
        mutate_after_parent_check,
    )
    with pytest.raises(PowerCalibrationProtocolError, match="changed after"):
        _load(root)


def test_mutation_during_post_load_parent_revalidation_is_refused(
    tmp_path, monkeypatch
):
    root = _clone(tmp_path)
    path = _paths(root)["protocol"]
    protocol = _load(root)
    original = module.require_loaded_global_benchmark_contract

    def mutate_after_parent_check(parent):
        result = original(parent)
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module,
        "require_loaded_global_benchmark_contract",
        mutate_after_parent_check,
    )
    with pytest.raises(PowerCalibrationProtocolError, match="changed after"):
        require_loaded_power_calibration_protocol(protocol)


def test_4c_ancestor_mutation_after_nested_load_is_refused(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    map_path = _paths(root)["map"]
    original = module._validate_calendar_and_capacity

    def mutate_parent_after_calendar_check(payload, parent):
        sessions = original(payload, parent)
        map_path.write_bytes(map_path.read_bytes() + b" ")
        return sessions

    monkeypatch.setattr(
        module,
        "_validate_calendar_and_capacity",
        mutate_parent_after_calendar_check,
    )
    with pytest.raises(
        PowerCalibrationProtocolError,
        match="parent changed during authentication",
    ):
        _load(root)


def test_post_load_protocol_and_parent_mutations_are_reauthenticated(tmp_path):
    root = _clone(tmp_path)
    paths = _paths(root)
    protocol = _load(root)
    paths["protocol"].write_bytes(paths["protocol"].read_bytes() + b" ")
    with pytest.raises(PowerCalibrationProtocolError, match="changed after"):
        require_loaded_power_calibration_protocol(protocol)

    root = _clone(tmp_path / "second")
    paths = _paths(root)
    protocol = _load(root)
    paths["map"].write_bytes(paths["map"].read_bytes() + b" ")
    with pytest.raises(PowerCalibrationProtocolError, match="parent changed"):
        require_loaded_power_calibration_protocol(protocol)


def test_nested_parent_errors_are_normalized(tmp_path):
    root = _clone(tmp_path)
    path = _paths(root)["matched"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(PowerCalibrationProtocolError, match="parent authentication"):
        _load(root)


def test_protocol_path_must_not_be_a_symlink(tmp_path):
    root = _clone(tmp_path)
    original = _paths(root)["protocol"]
    linked = root / "linked-protocol.json"
    try:
        linked.symlink_to(original)
    except OSError as exc:
        pytest.skip(f"host cannot create test symlink: {exc}")
    paths = _paths(root)
    with pytest.raises(PowerCalibrationProtocolError, match="link"):
        load_power_calibration_protocol(
            linked,
            map_path=paths["map"],
            matched_contract_path=paths["matched"],
            successor_spec_path=paths["successor"],
            parent_stock_spec_path=paths["stock"],
            fold_manifest_path=paths["folds"],
            qc_first_plan_path=paths["plan"],
        )


def test_copy_reconstruction_and_pickle_never_create_authority(protocol):
    copied = copy.copy(protocol)
    assert copied is not protocol
    with pytest.raises(PowerCalibrationProtocolError):
        require_loaded_power_calibration_protocol(copied)

    forged = object.__new__(PowerCalibrationProtocol)
    for field in dataclasses.fields(PowerCalibrationProtocol):
        object.__setattr__(forged, field.name, getattr(protocol, field.name))
    with pytest.raises(PowerCalibrationProtocolError):
        require_loaded_power_calibration_protocol(forged)

    try:
        round_trip = pickle.loads(pickle.dumps(protocol))
    except (TypeError, pickle.PicklingError):
        return
    with pytest.raises(PowerCalibrationProtocolError):
        require_loaded_power_calibration_protocol(round_trip)


def test_dataclasses_replace_cannot_reconstruct_authenticated_protocol(protocol):
    with pytest.raises(TypeError):
        dataclasses.replace(protocol, protocol_hash="0" * 64)


def test_low_level_scalar_mutation_is_detected(protocol):
    object.__setattr__(protocol, "protocol_id", str(protocol.protocol_id))
    require_loaded_power_calibration_protocol(protocol)
    object.__setattr__(protocol, "protocol_id", protocol.protocol_id + "x")
    with pytest.raises(PowerCalibrationProtocolError, match="changed after"):
        require_loaded_power_calibration_protocol(protocol)


@pytest.mark.parametrize(
    "field,replacement",
    (
        ("calibration_session_axis", ["2018-01-31"]),
        ("definition", {}),
        ("lineage_graph", {}),
        ("capabilities", {}),
    ),
)
def test_low_level_collection_type_substitution_is_detected(
    protocol, field, replacement
):
    object.__setattr__(protocol, field, replacement)
    with pytest.raises(PowerCalibrationProtocolError):
        require_loaded_power_calibration_protocol(protocol)


def test_equality_spoofed_scalar_subclass_is_detected(protocol):
    class SpoofedStr(str):
        pass

    object.__setattr__(protocol, "protocol_id", SpoofedStr(protocol.protocol_id))
    with pytest.raises(PowerCalibrationProtocolError, match="changed type"):
        require_loaded_power_calibration_protocol(protocol)


def test_provisional_helper_rejects_a_forged_protocol(protocol):
    forged = copy.copy(protocol)
    with pytest.raises(PowerCalibrationProtocolError):
        derive_provisional_power_requirement(
            forged,
            long_run_variance=Decimal("0.00001"),
            per_session_component_counts=_component_pairs(protocol, (1,) * 483),
        )


def test_weakref_callback_removes_loader_authority():
    protocol = _load()
    identity = id(protocol)
    reference = weakref.ref(protocol)
    assert identity in module._POWER_CALIBRATION_PROTOCOL_AUTHORITIES
    del protocol
    gc.collect()
    assert reference() is None
    assert identity not in module._POWER_CALIBRATION_PROTOCOL_AUTHORITIES
