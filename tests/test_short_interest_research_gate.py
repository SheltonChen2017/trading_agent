"""Dangerous-direction tests for the zero-authority SI-0M research gate."""
from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path

import pytest

from data.hashing import hash_payload
from research.short_interest_etf import (
    FIXED_STRATEGY_LANE_IDS,
    PREREGISTRATION,
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
    ShortInterestAllocationState,
    ShortInterestPreregistrationError,
    ShortInterestResearchGate,
    ShortInterestSlotDisposition,
    require_short_interest_research_gate,
)
import research.short_interest_etf.preregistration as preregistration
from research.short_interest_etf.preregistration import (
    FUTURE_QC_INPUT_CONTRACT,
    LEGACY_PREREGISTRATION_SHA256,
    MULTIPLICITY_DIRECTIVE_COMMIT,
    SHARED_FAMILY_DIRECTIVE_COMMIT,
    SHORT_INTEREST_BLUEPRINT_PATH,
    SHORT_INTEREST_BLUEPRINT_SHA256,
    SHORT_INTEREST_RESEARCH_GATE_VERSION,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "research" / "short_interest_etf" / "preregistration.py"
BLUEPRINT_PATH = REPO_ROOT / SHORT_INTEREST_BLUEPRINT_PATH
AUTHORITY_FIELDS = (
    "network_access_authorized",
    "finra_access_authorized",
    "provider_access_authorized",
    "source_data_request_authorized",
    "credential_access_authorized",
    "licensed_row_access_authorized",
    "outcome_access_authorized",
    "shared_holdout_access_authorized",
    "qc_upload_authorized",
    "qc_processing_authorized",
    "qc_job_authorized",
    "qc_backtest_authorized",
    "qc_research_inputs_execution_authority",
    "common_four_family_outcome_evaluation_authorized",
    "integration_authorized",
    "capital_authorized",
    "broker_access_authorized",
    "operator_database_access_authorized",
    "scheduler_access_authorized",
    "paper_trading_authorized",
    "live_trading_authorized",
    "deployment_authorized",
    "trading_authority",
)


class _StringSubclass(str):
    pass


class _IntSubclass(int):
    pass


class _TupleSubclass(tuple):
    pass


class _FractionSubclass(Fraction):
    pass


class _DateSubclass(date):
    pass


def test_gate_preserves_and_binds_the_legacy_preregistration_identity() -> None:
    assert PREREGISTRATION.schema_version == "1.0"
    assert PREREGISTRATION.canonical_score == "S1_delta"
    assert PREREGISTRATION.primary_horizon_sessions == 20
    assert PREREGISTRATION.milestone_outcome_look_budget == 0
    assert PREREGISTRATION.outcome_looks_used == 0
    assert PREREGISTRATION.production_authoritative is False
    assert PREREGISTRATION.sha256 == LEGACY_PREREGISTRATION_SHA256
    assert LEGACY_PREREGISTRATION_SHA256 == (
        "83165e805a8ad91787d10f066b28e14a1d6655d2dd19c4b5efd8a02a1ceeef9f"
    )
    assert SHORT_INTEREST_RESEARCH_GATE.legacy_preregistration_sha256 == (
        PREREGISTRATION.sha256
    )


def test_four_lane_family_uses_exact_owner_directed_arithmetic() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE

    assert gate.fixed_lane_ids == (
        "analyst-revisions-v2",
        "insider-buying",
        "short-interest",
        "target-price-revisions",
    )
    assert gate.fixed_lane_ids == FIXED_STRATEGY_LANE_IDS
    assert gate.assigned_lane_id == "short-interest"
    assert type(gate.shared_two_sided_fwer) is Fraction
    assert type(gate.permanent_lane_alpha_maximum) is Fraction
    assert gate.shared_two_sided_fwer == Fraction(1, 20)
    assert gate.permanent_lane_alpha_maximum == Fraction(1, 80)
    assert gate.within_lane_confirmatory_alpha_ceiling == Fraction(1, 80)
    assert len(gate.fixed_lane_ids) * gate.permanent_lane_alpha_maximum == (
        gate.shared_two_sided_fwer
    )


def test_unused_or_withdrawn_slot_expires_without_reallocation() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE

    assert gate.unused_slot_disposition is ShortInterestSlotDisposition.EXPIRES
    assert gate.withdrawn_slot_disposition is ShortInterestSlotDisposition.EXPIRES
    assert gate.slot_transfer_authorized is False
    assert gate.slot_redistribution_authorized is False
    assert gate.denominator_recomputation_authorized is False


def test_candidate_design_is_not_a_permanent_cell_or_look_allocation() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE

    assert PREREGISTRATION.score_family == (
        "S0_level",
        "S1_delta",
        "S2_surprise",
        "S3_delta_dtc",
        "S4_residual",
    )
    assert PREREGISTRATION.primary_horizon_sessions == 20
    assert gate.confirmatory_alpha_allocations == ()
    assert gate.permanent_look_ids == ()
    assert gate.allocation_state is (
        ShortInterestAllocationState.OWNER_DECISION_REQUIRED
    )
    assert gate.authorized_outcome_looks == 0
    assert gate.consumed_outcome_looks == 0


def test_shared_holdout_is_reserved_and_inaccessible() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE

    assert gate.shared_research_cutoff == date(2027, 8, 31)
    assert gate.shared_holdout_start == date(2027, 9, 1)
    assert gate.shared_holdout_end == date(2029, 8, 31)
    assert gate.shared_research_cutoff < gate.shared_holdout_start
    assert gate.shared_holdout_access_authorized is False


def test_stock_null_cannot_be_rescued_by_industry_etf_or_qc_work() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE

    assert gate.valid_stock_level_null_closes_canonical_family is True
    assert gate.post_result_tuning_or_rerun_authorized is False
    assert gate.later_hypothesis_requires_separate_preregistered_family is True
    assert gate.later_family_requires_owner_authorized_permanent_look_budget is True
    assert gate.later_family_can_retroactively_rescue_canonical_result is False
    assert gate.industry_can_rescue_valid_stock_null is False
    assert gate.etf_can_rescue_valid_stock_null is False
    assert gate.qc_can_rescue_valid_stock_null is False
    assert gate.future_qc_stage == "SI-7"
    assert gate.future_qc_input_contract == FUTURE_QC_INPUT_CONTRACT


def test_every_external_empirical_and_operational_authority_is_false() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE

    assert tuple(preregistration._FALSE_AUTHORITY_FIELDS) == AUTHORITY_FIELDS
    assert all(getattr(gate, field_name) is False for field_name in AUTHORITY_FIELDS)


def test_gate_is_frozen_and_payload_calls_are_isolated() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE
    first = gate.to_payload()
    second = gate.to_payload()

    assert first == second
    assert first is not second
    first["family_multiplicity"]["fixed_lane_ids"].append("forged")
    first["within_lane_allocation"]["permanent_look_ids"].append("forged-look")
    assert gate.to_payload() == second
    with pytest.raises(FrozenInstanceError):
        gate.assigned_lane_id = "forged"  # type: ignore[misc]


def test_payload_and_semantic_hash_are_canonical_and_pinned() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE
    payload = gate.to_payload()
    family = payload["family_multiplicity"]

    assert family["shared_two_sided_fwer"] == {
        "numerator": 1,
        "denominator": 20,
    }
    assert family["permanent_lane_alpha_maximum"] == {
        "numerator": 1,
        "denominator": 80,
    }
    assert gate.semantic_sha256 == hash_payload(payload)
    assert gate.semantic_sha256 == SHORT_INTEREST_RESEARCH_GATE_SHA256
    assert SHORT_INTEREST_RESEARCH_GATE_SHA256 == (
        "1d612d47369dbe642e10323a0154a5b5e1cd671e7e0d1a4f2631cb3f733f0f6e"
    )
    assert require_short_interest_research_gate(gate) == (
        SHORT_INTEREST_RESEARCH_GATE_SHA256
    )


def test_admission_refuses_a_subclass_that_forges_payload_and_hash() -> None:
    class ForgedResearchGate(ShortInterestResearchGate):
        def __post_init__(self):
            pass

        def to_payload(self):
            payload = SHORT_INTEREST_RESEARCH_GATE.to_payload()
            payload["authority"]["outcome_access_authorized"] = True
            return payload

        @property
        def semantic_sha256(self):
            return SHORT_INTEREST_RESEARCH_GATE_SHA256

    forged = ForgedResearchGate()
    assert forged.outcome_access_authorized is False
    assert forged.to_payload()["authority"]["outcome_access_authorized"] is True
    assert forged.semantic_sha256 == SHORT_INTEREST_RESEARCH_GATE_SHA256
    with pytest.raises(
        ShortInterestPreregistrationError,
        match="exact frozen contract type",
    ):
        require_short_interest_research_gate(forged)


def test_admission_returns_an_immutable_receipt_not_the_caller_object() -> None:
    candidate = copy.copy(SHORT_INTEREST_RESEARCH_GATE)
    receipt = require_short_interest_research_gate(candidate)

    assert type(receipt) is str
    assert receipt == SHORT_INTEREST_RESEARCH_GATE_SHA256
    assert receipt is not candidate
    object.__setattr__(candidate, "outcome_access_authorized", True)
    assert receipt == SHORT_INTEREST_RESEARCH_GATE_SHA256
    with pytest.raises(
        ShortInterestPreregistrationError,
        match="outcome_access_authorized",
    ):
        require_short_interest_research_gate(candidate)


def test_gate_is_bound_to_blueprint_and_immutable_directive_sources() -> None:
    gate = SHORT_INTEREST_RESEARCH_GATE
    action_plan = REPO_ROOT / "docs" / "ACTION_PLAN_2026-08-20.md"
    direction = REPO_ROOT / "docs" / "THREE_STRATEGY_PROJECT_DIRECTION.md"

    assert SHORT_INTEREST_RESEARCH_GATE_VERSION == "SIETF-SI0M-RESEARCH-GATE-v1"
    assert hashlib.sha256(BLUEPRINT_PATH.read_bytes()).hexdigest() == (
        SHORT_INTEREST_BLUEPRINT_SHA256
    )
    assert MULTIPLICITY_DIRECTIVE_COMMIT == (
        "6b12102b9710efb838e41cefd94cfcecd3ab592d"
    )
    assert SHARED_FAMILY_DIRECTIVE_COMMIT == (
        "ba01e98f9d3c8746c70182818a27a2d49a9c0fe7"
    )
    assert gate.multiplicity_directive_effective_date == date(2026, 8, 30)
    assert gate.shared_family_directive_effective_date == date(2026, 8, 29)
    assert "Owner multiplicity amendment, 2026-08-30" in action_plan.read_text(
        encoding="utf-8"
    )
    action_plan_text = action_plan.read_text(encoding="utf-8")
    direction_text = direction.read_text(encoding="utf-8")
    assert "the four named strategy-selection lanes are one fixed family" in (
        action_plan_text
    )
    assert "permanent maximum allocation of\n`1/80 = 0.0125`" in action_plan_text
    assert "allocation expires and is never transferred, redistributed" in (
        action_plan_text
    )
    assert "Owner-coordinated shared-family amendment, 2026-08-29" in (
        direction_text
    )
    assert "common cutoff session is **2027-08-31**" in direction_text
    assert "untouched shared final holdout\nis **2027-09-01 through 2029-08-31**" in (
        direction_text
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "SIETF-SI0M-RESEARCH-GATE-v2"},
        {"version": _StringSubclass(SHORT_INTEREST_RESEARCH_GATE_VERSION)},
        {"blueprint_path": "docs/Strategy Description/other.pdf"},
        {"blueprint_path": _StringSubclass(SHORT_INTEREST_BLUEPRINT_PATH)},
        {"blueprint_sha256": "0" * 64},
        {"blueprint_sha256": _StringSubclass(SHORT_INTEREST_BLUEPRINT_SHA256)},
        {"legacy_preregistration_sha256": "0" * 64},
        {
            "legacy_preregistration_sha256": _StringSubclass(
                LEGACY_PREREGISTRATION_SHA256
            )
        },
        {"multiplicity_directive_id": "other-directive"},
        {
            "multiplicity_directive_id": _StringSubclass(
                "owner-multiplicity-amendment-2026-08-30"
            )
        },
        {"multiplicity_directive_commit": "0" * 40},
        {
            "multiplicity_directive_path": _StringSubclass(
                "docs/ACTION_PLAN_2026-08-20.md"
            )
        },
        {
            "multiplicity_directive_effective_date": _DateSubclass(2026, 8, 30)
        },
        {"shared_family_directive_id": "other-directive"},
        {
            "shared_family_directive_path": _StringSubclass(
                "docs/THREE_STRATEGY_PROJECT_DIRECTION.md"
            )
        },
        {"shared_family_directive_commit": "0" * 40},
        {
            "shared_family_directive_effective_date": _DateSubclass(2026, 8, 29)
        },
        {"fixed_lane_ids": FIXED_STRATEGY_LANE_IDS[:-1]},
        {"fixed_lane_ids": _TupleSubclass(FIXED_STRATEGY_LANE_IDS)},
        {
            "fixed_lane_ids": (
                "analyst-revisions-v2",
                "insider-buying",
                _StringSubclass("short-interest"),
                "target-price-revisions",
            )
        },
        {"assigned_lane_id": "insider-buying"},
        {"assigned_lane_id": _StringSubclass("short-interest")},
        {"shared_two_sided_fwer": Fraction(1, 15)},
        {"shared_two_sided_fwer": _FractionSubclass(1, 20)},
        {"permanent_lane_alpha_maximum": Fraction(1, 60)},
        {"permanent_lane_alpha_maximum": _FractionSubclass(1, 80)},
        {"within_lane_confirmatory_alpha_ceiling": Fraction(1, 60)},
        {"within_lane_confirmatory_alpha_ceiling": _FractionSubclass(1, 80)},
        {"permanent_lane_alpha_maximum": 0.0125},
        {"unused_slot_disposition": "expires"},
        {"withdrawn_slot_disposition": "expires"},
        {"slot_transfer_authorized": True},
        {"slot_transfer_authorized": 0},
        {"slot_redistribution_authorized": True},
        {"slot_redistribution_authorized": 0},
        {"denominator_recomputation_authorized": True},
        {"denominator_recomputation_authorized": 0},
        {
            "confirmatory_alpha_allocations": (
                ("si-stock-primary-20d", Fraction(1, 80)),
            )
        },
        {"confirmatory_alpha_allocations": []},
        {"confirmatory_alpha_allocations": _TupleSubclass(())},
        {"permanent_look_ids": ("si-look-stock-primary-001",)},
        {"permanent_look_ids": []},
        {"permanent_look_ids": _TupleSubclass(())},
        {"allocation_state": "owner_decision_required"},
        {"authorized_outcome_looks": 1},
        {"authorized_outcome_looks": False},
        {"consumed_outcome_looks": 1},
        {"consumed_outcome_looks": False},
        {"shared_research_cutoff": date(2027, 8, 30)},
        {"shared_research_cutoff": _DateSubclass(2027, 8, 31)},
        {"shared_holdout_start": datetime(2027, 9, 1)},
        {"shared_holdout_start": _DateSubclass(2027, 9, 1)},
        {"shared_holdout_end": date(2029, 9, 1)},
        {"shared_holdout_end": _DateSubclass(2029, 8, 31)},
        {"valid_stock_level_null_closes_canonical_family": False},
        {"valid_stock_level_null_closes_canonical_family": 1},
        {"post_result_tuning_or_rerun_authorized": True},
        {"post_result_tuning_or_rerun_authorized": 0},
        {"later_hypothesis_requires_separate_preregistered_family": False},
        {"later_hypothesis_requires_separate_preregistered_family": 1},
        {"later_family_requires_owner_authorized_permanent_look_budget": False},
        {"later_family_requires_owner_authorized_permanent_look_budget": 1},
        {"later_family_can_retroactively_rescue_canonical_result": True},
        {"later_family_can_retroactively_rescue_canonical_result": 0},
        {"industry_can_rescue_valid_stock_null": True},
        {"industry_can_rescue_valid_stock_null": 0},
        {"etf_can_rescue_valid_stock_null": True},
        {"etf_can_rescue_valid_stock_null": 0},
        {"qc_can_rescue_valid_stock_null": True},
        {"qc_can_rescue_valid_stock_null": 0},
        {"future_qc_stage": "SI-6"},
        {"future_qc_stage": _StringSubclass("SI-7")},
        {"future_qc_input_contract": "call-provider-from-backtest"},
    ],
)
def test_multiplicity_holdout_allocation_and_null_mutations_refuse(changes) -> None:
    with pytest.raises(ShortInterestPreregistrationError, match="REFUSED"):
        replace(SHORT_INTEREST_RESEARCH_GATE, **changes)


@pytest.mark.parametrize("field_name", AUTHORITY_FIELDS)
def test_each_authority_mutation_refuses(field_name: str) -> None:
    with pytest.raises(ShortInterestPreregistrationError, match=field_name):
        replace(SHORT_INTEREST_RESEARCH_GATE, **{field_name: True})


@pytest.mark.parametrize("field_name", AUTHORITY_FIELDS)
def test_falsey_non_boolean_authority_mutations_refuse(field_name: str) -> None:
    with pytest.raises(ShortInterestPreregistrationError, match=field_name):
        replace(SHORT_INTEREST_RESEARCH_GATE, **{field_name: 0})


def test_semantic_hash_refuses_every_mutated_authority_field() -> None:
    for field_name in AUTHORITY_FIELDS:
        forged = copy.copy(SHORT_INTEREST_RESEARCH_GATE)
        object.__setattr__(forged, field_name, True)
        with pytest.raises(ShortInterestPreregistrationError, match=field_name):
            _ = forged.semantic_sha256


def test_serialization_and_hash_revalidate_exact_runtime_types() -> None:
    forged = copy.copy(SHORT_INTEREST_RESEARCH_GATE)
    object.__setattr__(
        forged,
        "version",
        _StringSubclass(SHORT_INTEREST_RESEARCH_GATE_VERSION),
    )

    with pytest.raises(ShortInterestPreregistrationError, match="version"):
        forged.to_payload()
    with pytest.raises(ShortInterestPreregistrationError, match="version"):
        _ = forged.semantic_sha256

    for field_name, value in (
        ("permanent_look_ids", ("forged-look",)),
        (
            "confirmatory_alpha_allocations",
            (("forged-look", Fraction(1, 80)),),
        ),
    ):
        forged = copy.copy(SHORT_INTEREST_RESEARCH_GATE)
        object.__setattr__(forged, field_name, value)
        with pytest.raises(
            ShortInterestPreregistrationError,
            match="permanent cells and looks require an owner decision",
        ):
            _ = forged.semantic_sha256


def test_lane_maxima_must_still_multiply_to_the_shared_fwer(monkeypatch) -> None:
    drifted = Fraction(1, 40)
    monkeypatch.setattr(
        preregistration,
        "PERMANENT_LANE_ALPHA_MAXIMUM",
        drifted,
    )

    with pytest.raises(
        ShortInterestPreregistrationError,
        match="four permanent lane maxima do not equal shared FWER",
    ):
        ShortInterestResearchGate(
            permanent_lane_alpha_maximum=drifted,
            within_lane_confirmatory_alpha_ceiling=drifted,
        )


def test_research_cutoff_must_still_precede_the_final_holdout(monkeypatch) -> None:
    overlapping_start = date(2027, 8, 31)
    monkeypatch.setattr(preregistration, "SHARED_HOLDOUT_START", overlapping_start)

    with pytest.raises(
        ShortInterestPreregistrationError,
        match="shared research and final-holdout periods overlap",
    ):
        ShortInterestResearchGate(shared_holdout_start=overlapping_start)


def test_legacy_preregistration_drift_is_rejected_and_restored() -> None:
    original = PREREGISTRATION.milestone_outcome_look_budget
    try:
        object.__setattr__(PREREGISTRATION, "milestone_outcome_look_budget", 1)
        with pytest.raises(
            ShortInterestPreregistrationError,
            match="legacy SI-0 milestone_outcome_look_budget drifted",
        ):
            ShortInterestResearchGate()
        with pytest.raises(
            ShortInterestPreregistrationError,
            match="legacy SI-0 milestone_outcome_look_budget drifted",
        ):
            _ = SHORT_INTEREST_RESEARCH_GATE.semantic_sha256
    finally:
        object.__setattr__(
            PREREGISTRATION,
            "milestone_outcome_look_budget",
            original,
        )
    assert PREREGISTRATION.sha256 == LEGACY_PREREGISTRATION_SHA256


def test_legacy_preregistration_subclass_cannot_forge_its_bound_hash(
    monkeypatch,
) -> None:
    class ForgedLegacyPreregistration(type(PREREGISTRATION)):
        source_semantic = "daily_short_volume"

        @property
        def sha256(self):
            return LEGACY_PREREGISTRATION_SHA256

    forged = ForgedLegacyPreregistration()
    assert forged.sha256 == LEGACY_PREREGISTRATION_SHA256
    monkeypatch.setattr(preregistration, "PREREGISTRATION", forged)

    with pytest.raises(
        ShortInterestPreregistrationError,
        match="legacy SI-0 preregistration must retain its exact type",
    ):
        ShortInterestResearchGate()


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        (
            "source_semantic",
            _StringSubclass("official_open_short_position_snapshot"),
        ),
        ("execution_calendar", _StringSubclass("XNYS")),
        (
            "canonical_denominator",
            _StringSubclass("point_in_time_shares_outstanding"),
        ),
        ("audited_preferred_denominator", _StringSubclass("point_in_time_float")),
        (
            "score_family",
            _TupleSubclass(
                (
                    "S0_level",
                    "S1_delta",
                    "S2_surprise",
                    "S3_delta_dtc",
                    "S4_residual",
                )
            ),
        ),
        (
            "score_family",
            [
                "S0_level",
                "S1_delta",
                "S2_surprise",
                "S3_delta_dtc",
                "S4_residual",
            ],
        ),
        ("canonical_score", _StringSubclass("S1_delta")),
        ("primary_horizon_sessions", _IntSubclass(20)),
        ("primary_cost_bps", _IntSubclass(10)),
        ("cost_sensitivity_bps", _TupleSubclass((0, 5, 20))),
        ("cost_sensitivity_bps", [0, 5, 20]),
        ("canonical_leverage", _IntSubclass(1)),
        ("milestone_outcome_look_budget", False),
        ("outcome_looks_used", False),
        ("production_authoritative", 0),
        ("schema_version", _StringSubclass("1.0")),
    ],
)
def test_legacy_same_value_wrong_runtime_types_are_refused(
    monkeypatch,
    field_name: str,
    forged_value: object,
) -> None:
    forged = copy.copy(PREREGISTRATION)
    object.__setattr__(forged, field_name, forged_value)
    monkeypatch.setattr(preregistration, "PREREGISTRATION", forged)

    with pytest.raises(
        ShortInterestPreregistrationError,
        match=field_name,
    ):
        ShortInterestResearchGate()


def test_module_has_no_float_or_forbidden_runtime_import_surface() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots == {
        "__future__",
        "data",
        "dataclasses",
        "datetime",
        "enum",
        "fractions",
        "typing",
    }
    assert not any(
        isinstance(node, ast.Constant) and type(node.value) is float
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "__import__")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
        )
        for node in ast.walk(tree)
    )


def test_module_admits_the_singleton_at_import_time() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    singleton_assignments = [
        index
        for index, node in enumerate(tree.body)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "SHORT_INTEREST_RESEARCH_GATE"
            for target in node.targets
        )
    ]
    admission_calls = []
    for index, node in enumerate(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if (
            isinstance(call.func, ast.Name)
            and call.func.id == "require_short_interest_research_gate"
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "SHORT_INTEREST_RESEARCH_GATE"
        ):
            admission_calls.append(index)

    assert len(singleton_assignments) == 1
    assert len(admission_calls) == 1
    assert admission_calls[0] == singleton_assignments[0] + 1
