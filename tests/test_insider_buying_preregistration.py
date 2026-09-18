"""Dangerous-direction tests for the zero-authority IB-1I research gate."""
from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest

from research.insider_buying import (
    CANONICAL_SPEC,
    FIXED_STRATEGY_LANE_IDS,
    INSIDER_BUYING_BLUEPRINT_SHA256,
    INSIDER_BUYING_RESEARCH_GATE,
    INSIDER_BUYING_RESEARCH_GATE_SHA256,
    InsiderBuyingAllocationState,
    InsiderBuyingPreregistrationError,
    InsiderBuyingResearchGate,
    InsiderBuyingSlotDisposition,
)
from research.insider_buying import preregistration
from research.insider_buying.preregistration import (
    CANDIDATE_PRIMARY_HORIZONS_TRADING_DAYS,
    IB0_CONTRACT_VERSION,
    INSIDER_PAPER_PILOT_DURATION_TRADING_DAYS,
    INSIDER_PAPER_PROMOTION_SEQUENCE,
    INSIDER_SHARED_HOLDOUT_ROLE,
    INSIDER_BUYING_BLUEPRINT_PATH,
    MULTIPLICITY_DIRECTIVE_COMMIT,
    PAPER_PROMOTION_DIRECTIVE_COMMIT,
    SHARED_FAMILY_DIRECTIVE_COMMIT,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "research" / "insider_buying" / "preregistration.py"
BLUEPRINT_PATH = (
    REPO_ROOT
    / "docs"
    / "Strategy Description"
    / "INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf"
)


class _StringSubclass(str):
    pass


class _DateSubclass(date):
    pass


def test_four_lane_family_uses_exact_owner_directed_arithmetic() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE

    assert gate.fixed_lane_ids == (
        "analyst-revisions-v2",
        "insider-buying",
        "short-interest",
        "target-price-revisions",
    )
    assert gate.assigned_lane_id == "insider-buying"
    assert type(gate.shared_two_sided_fwer) is Fraction
    assert type(gate.permanent_lane_alpha_maximum) is Fraction
    assert gate.shared_two_sided_fwer == Fraction(1, 20)
    assert gate.permanent_lane_alpha_maximum == Fraction(1, 80)
    assert gate.within_lane_confirmatory_alpha_ceiling == Fraction(1, 80)
    assert len(gate.fixed_lane_ids) * gate.permanent_lane_alpha_maximum == (
        gate.shared_two_sided_fwer
    )


def test_unused_or_withdrawn_slot_expires_without_reallocation() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE

    assert gate.unused_slot_disposition is InsiderBuyingSlotDisposition.EXPIRES
    assert gate.withdrawn_slot_disposition is InsiderBuyingSlotDisposition.EXPIRES
    assert gate.slot_transfer_authorized is False
    assert gate.slot_redistribution_authorized is False
    assert gate.denominator_recomputation_authorized is False


def test_candidate_horizons_are_not_allocated_cells_or_looks() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE

    assert gate.candidate_primary_horizons_trading_days == (5, 20, 60)
    assert CANDIDATE_PRIMARY_HORIZONS_TRADING_DAYS == (5, 20, 60)
    assert gate.candidate_primary_horizons_trading_days == (
        CANONICAL_SPEC.primary_horizons_trading_days
    )
    assert gate.ib0_contract_version == IB0_CONTRACT_VERSION == "INSETF-IB0-v1"
    assert gate.confirmatory_alpha_allocations == ()
    assert gate.permanent_look_ids == ()
    assert gate.allocation_state is (
        InsiderBuyingAllocationState.OWNER_DECISION_REQUIRED
    )
    assert gate.authorized_outcome_looks == 0
    assert gate.consumed_outcome_looks == 0


def test_upstream_ib0_horizon_drift_refuses_instead_of_redefining_gate() -> None:
    original = CANONICAL_SPEC.primary_horizons_trading_days
    try:
        object.__setattr__(
            CANONICAL_SPEC,
            "primary_horizons_trading_days",
            (10, 20, 60),
        )
        with pytest.raises(
            InsiderBuyingPreregistrationError,
            match="IB-0 primary horizons drifted",
        ):
            InsiderBuyingResearchGate()
    finally:
        object.__setattr__(
            CANONICAL_SPEC,
            "primary_horizons_trading_days",
            original,
        )

    assert CANONICAL_SPEC.primary_horizons_trading_days == (5, 20, 60)


@pytest.mark.parametrize(
    ("field_name", "mutated_value"),
    [
        ("version", "INSETF-IB0-v2"),
        ("outcomes_authorized", True),
        ("authorized_outcome_looks", 1),
    ],
)
def test_upstream_ib0_version_or_outcome_authority_drift_refuses(
    field_name: str,
    mutated_value: object,
) -> None:
    original = getattr(CANONICAL_SPEC, field_name)
    try:
        object.__setattr__(CANONICAL_SPEC, field_name, mutated_value)
        with pytest.raises(InsiderBuyingPreregistrationError, match="IB-0"):
            InsiderBuyingResearchGate()
    finally:
        object.__setattr__(CANONICAL_SPEC, field_name, original)


def test_shared_holdout_is_reserved_inaccessible_and_prospective() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE

    assert gate.shared_research_cutoff == date(2027, 8, 31)
    assert gate.shared_holdout_start == date(2027, 9, 1)
    assert gate.shared_holdout_end == date(2029, 8, 31)
    assert gate.shared_research_cutoff < gate.shared_holdout_start
    assert gate.shared_holdout_access_authorized is False
    assert gate.shared_holdout_role == INSIDER_SHARED_HOLDOUT_ROLE
    assert gate.shared_holdout_role == "long_term_prospective_validation"


def test_paper_promotion_boundary_is_accelerated_but_zero_authority() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE

    assert gate.shared_holdout_completion_required_for_paper_promotion is False
    assert gate.paper_promotion_sequence == INSIDER_PAPER_PROMOTION_SEQUENCE
    assert gate.paper_promotion_sequence == (
        "independently_reviewed_historical_validation",
        "independently_reviewed_qc_parity",
        "separate_owner_paper_deployment_authority",
        "60_trading_day_paper_pilot",
    )
    assert gate.paper_pilot_duration_trading_days == (
        INSIDER_PAPER_PILOT_DURATION_TRADING_DAYS
    )
    assert type(gate.paper_pilot_duration_trading_days) is int
    assert gate.paper_pilot_duration_trading_days == 60
    assert (
        gate.paper_promotion_prerequisites_confer_deployment_authority
        is False
    )
    assert gate.paper_trading_authorized is False
    assert gate.deployment_authorized is False
    assert gate.live_trading_authorized is False
    assert gate.trading_authority is False


def test_stock_null_cannot_be_rescued_by_etf_or_qc_work() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE

    assert gate.valid_stock_level_null_closes_canonical_family is True
    assert gate.post_result_tuning_or_rerun_authorized is False
    assert gate.later_hypothesis_requires_separate_preregistered_family is True
    assert (
        gate.later_family_requires_owner_authorized_permanent_look_budget is True
    )
    assert gate.later_family_can_retroactively_rescue_canonical_result is False
    assert gate.etf_can_rescue_valid_stock_null is False
    assert gate.qc_can_rescue_valid_stock_null is False
    assert gate.future_qc_stage == "IB-7"
    assert gate.future_qc_input_contract == (
        "independently_reviewed_immutable_precomputed_or_custom_signals_only"
    )


def test_every_external_or_operational_authority_is_false() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE
    authority_fields = (
        "network_access_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "credential_access_authorized",
        "licensed_row_access_authorized",
        "outcome_access_authorized",
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

    assert all(getattr(gate, field_name) is False for field_name in authority_fields)


def test_gate_is_frozen_and_payload_calls_are_isolated() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE
    first = gate.to_payload()
    second = gate.to_payload()

    assert first == second
    assert first is not second
    family = first["family_multiplicity"]
    allocation = first["within_lane_allocation"]
    paper = first["insider_paper_promotion"]
    assert isinstance(family, dict)
    assert isinstance(allocation, dict)
    assert isinstance(paper, dict)
    fixed_lane_ids = family["fixed_lane_ids"]
    permanent_look_ids = allocation["permanent_look_ids"]
    paper_sequence = paper["ordered_sequence"]
    assert isinstance(fixed_lane_ids, list)
    assert isinstance(permanent_look_ids, list)
    assert isinstance(paper_sequence, list)
    fixed_lane_ids.append("forged")
    permanent_look_ids.append("forged-look")
    paper_sequence.append("forged-step")
    assert gate.to_payload() == second
    with pytest.raises(FrozenInstanceError):
        gate.assigned_lane_id = "forged"  # type: ignore[misc]


def test_payload_and_semantic_hash_are_canonical_and_pinned() -> None:
    gate = INSIDER_BUYING_RESEARCH_GATE
    payload = gate.to_payload()

    assert gate.version == "INSETF-IB1I-RESEARCH-GATE-v2"
    assert payload["schema"] == "insider-buying-four-family-research-gate-v2"
    family = payload["family_multiplicity"]
    assert family["shared_two_sided_fwer"] == {  # type: ignore[index]
        "numerator": 1,
        "denominator": 20,
    }
    assert family[  # type: ignore[index]
        "permanent_lane_alpha_maximum"
    ] == {"numerator": 1, "denominator": 80}
    paper = payload["insider_paper_promotion"]
    assert paper == {
        "shared_holdout_completion_required": False,
        "ordered_sequence": list(INSIDER_PAPER_PROMOTION_SEQUENCE),
        "paper_pilot_duration_trading_days": 60,
        "prerequisites_confer_deployment_authority": False,
    }
    assert gate.semantic_sha256 == INSIDER_BUYING_RESEARCH_GATE_SHA256
    assert INSIDER_BUYING_RESEARCH_GATE_SHA256 == (
        "cb3d8009539ffdba2a383eb949964dc9686fdd64a71c36eb102cc69160b47a8f"
    )


def test_gate_is_bound_to_the_exact_governing_blueprint() -> None:
    assert INSIDER_BUYING_RESEARCH_GATE.blueprint_path == (
        INSIDER_BUYING_BLUEPRINT_PATH
    )
    assert INSIDER_BUYING_BLUEPRINT_SHA256 == (
        "f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c"
    )
    assert hashlib.sha256(BLUEPRINT_PATH.read_bytes()).hexdigest() == (
        INSIDER_BUYING_BLUEPRINT_SHA256
    )


def test_gate_is_bound_to_immutable_shared_directive_commits() -> None:
    action_plan = REPO_ROOT / "docs" / "ACTION_PLAN_2026-08-20.md"
    direction = REPO_ROOT / "docs" / "THREE_STRATEGY_PROJECT_DIRECTION.md"
    workflow = (
        REPO_ROOT
        / "docs"
        / "Strategy Description"
        / "THREE_STRATEGY_PARALLEL_WORKFLOW.md"
    )
    action_text = " ".join(action_plan.read_text(encoding="utf-8").split())
    direction_text = " ".join(direction.read_text(encoding="utf-8").split())
    workflow_text = " ".join(workflow.read_text(encoding="utf-8").split())

    assert MULTIPLICITY_DIRECTIVE_COMMIT == (
        "6b12102b9710efb838e41cefd94cfcecd3ab592d"
    )
    assert SHARED_FAMILY_DIRECTIVE_COMMIT == (
        "ba01e98f9d3c8746c70182818a27a2d49a9c0fe7"
    )
    assert PAPER_PROMOTION_DIRECTIVE_COMMIT == (
        "6204643eb9b4f464eb66248ba271ef2fe5e4b74c"
    )
    assert "Owner multiplicity amendment, 2026-08-30" in action_text
    assert "Owner-coordinated shared-family amendment, 2026-08-29" in (
        direction_text
    )
    assert "Owner-coordinated Insider paper-stage amendment, 2026-09-18" in (
        direction_text
    )
    assert (
        "shared final holdout is no longer a prerequisite for paper promotion"
        in direction_text
    )
    assert "60-trading-day paper pilot" in direction_text
    assert "grants neither continued paper operation nor live promotion" in (
        direction_text
    )
    assert "does not govern Insider Buying paper promotion" in workflow_text
    assert "preserves step 5 for the common portfolio evaluation" in workflow_text
    assert "grants no paper deployment authority" in workflow_text
    assert "This sequencing entry grants no data" in action_text
    assert INSIDER_BUYING_RESEARCH_GATE.multiplicity_directive_effective_date == (
        date(2026, 8, 30)
    )
    assert INSIDER_BUYING_RESEARCH_GATE.shared_family_directive_effective_date == (
        date(2026, 8, 29)
    )
    assert (
        INSIDER_BUYING_RESEARCH_GATE.paper_promotion_directive_effective_date
        == date(2026, 9, 18)
    )


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        (
            "confirmatory_alpha_allocations",
            (("ib-stock-primary-20d", Fraction(1, 80)),),
        ),
        ("permanent_look_ids", ("ib-look-stock-primary-001",)),
    ],
)
def test_semantic_hash_binds_unallocated_cell_and_look_inventories(
    field_name: str,
    forged_value: object,
) -> None:
    forged = copy.copy(INSIDER_BUYING_RESEARCH_GATE)
    object.__setattr__(forged, field_name, forged_value)

    assert forged.semantic_sha256 != INSIDER_BUYING_RESEARCH_GATE_SHA256


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("paper_promotion_directive_id", "forged-directive"),
        ("paper_promotion_directive_path", "docs/forged.md"),
        ("paper_promotion_directive_commit", "0" * 40),
        ("paper_promotion_directive_effective_date", date(2026, 9, 19)),
        ("shared_holdout_access_authorized", True),
        ("shared_holdout_role", "forged_role"),
        ("shared_holdout_completion_required_for_paper_promotion", True),
        ("paper_promotion_sequence", INSIDER_PAPER_PROMOTION_SEQUENCE[:-1]),
        ("paper_pilot_duration_trading_days", 59),
        ("paper_promotion_prerequisites_confer_deployment_authority", True),
    ],
)
def test_semantic_hash_binds_each_paper_promotion_field(
    field_name: str,
    forged_value: object,
) -> None:
    forged = copy.copy(INSIDER_BUYING_RESEARCH_GATE)
    object.__setattr__(forged, field_name, forged_value)

    assert forged.semantic_sha256 != INSIDER_BUYING_RESEARCH_GATE_SHA256


@pytest.mark.parametrize(
    "changes",
    [
        {"fixed_lane_ids": FIXED_STRATEGY_LANE_IDS[:-1]},
        {
            "fixed_lane_ids": (
                "analyst-revisions-v2",
                _StringSubclass("insider-buying"),
                "short-interest",
                "target-price-revisions",
            )
        },
        {"version": "INSETF-IB1I-RESEARCH-GATE-v1"},
        {"blueprint_path": "docs/Strategy Description/other.pdf"},
        {"blueprint_sha256": "0" * 64},
        {"ib0_contract_version": "INSETF-IB0-v2"},
        {"multiplicity_directive_commit": "0" * 40},
        {"shared_family_directive_commit": "0" * 40},
        {
            "multiplicity_directive_id": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.multiplicity_directive_id
            )
        },
        {
            "multiplicity_directive_path": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.multiplicity_directive_path
            )
        },
        {
            "multiplicity_directive_commit": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.multiplicity_directive_commit
            )
        },
        {
            "multiplicity_directive_effective_date": _DateSubclass(
                2026, 8, 30
            )
        },
        {
            "shared_family_directive_id": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.shared_family_directive_id
            )
        },
        {
            "shared_family_directive_path": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.shared_family_directive_path
            )
        },
        {
            "shared_family_directive_commit": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.shared_family_directive_commit
            )
        },
        {
            "shared_family_directive_effective_date": _DateSubclass(
                2026, 8, 29
            )
        },
        {"paper_promotion_directive_id": "forged"},
        {"paper_promotion_directive_path": "docs/forged.md"},
        {"paper_promotion_directive_commit": "0" * 40},
        {"paper_promotion_directive_effective_date": date(2026, 9, 19)},
        {
            "paper_promotion_directive_id": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.paper_promotion_directive_id
            )
        },
        {
            "paper_promotion_directive_path": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.paper_promotion_directive_path
            )
        },
        {
            "paper_promotion_directive_commit": _StringSubclass(
                INSIDER_BUYING_RESEARCH_GATE.paper_promotion_directive_commit
            )
        },
        {
            "paper_promotion_directive_effective_date": _DateSubclass(
                2026, 9, 18
            )
        },
        {"assigned_lane_id": "short-interest"},
        {"shared_two_sided_fwer": Fraction(1, 15)},
        {"permanent_lane_alpha_maximum": Fraction(1, 60)},
        {"within_lane_confirmatory_alpha_ceiling": Fraction(1, 60)},
        {"permanent_lane_alpha_maximum": 0.0125},
        {"slot_transfer_authorized": True},
        {"slot_redistribution_authorized": True},
        {"denominator_recomputation_authorized": True},
        {"unused_slot_disposition": "expires"},
        {"withdrawn_slot_disposition": "expires"},
        {"candidate_primary_horizons_trading_days": (5, 20)},
        {"candidate_primary_horizons_trading_days": (5.0, 20.0, 60.0)},
        {
            "confirmatory_alpha_allocations": (
                ("ib-stock-primary-5d", Fraction(1, 80)),
                ("ib-stock-primary-20d", Fraction(1, 80)),
                ("ib-stock-primary-60d", Fraction(1, 80)),
            )
        },
        {"permanent_look_ids": ("ib-look-stock-primary-001",)},
        {"confirmatory_alpha_allocations": []},
        {"permanent_look_ids": []},
        {"allocation_state": "owner_decision_required"},
        {"authorized_outcome_looks": 1},
        {"consumed_outcome_looks": 1},
        {"shared_research_cutoff": date(2027, 9, 1)},
        {"shared_holdout_start": date(2027, 8, 31)},
        {"shared_holdout_end": date(2029, 9, 1)},
        {"shared_holdout_access_authorized": True},
        {"shared_holdout_access_authorized": 0},
        {"shared_holdout_role": "final_holdout_only"},
        {"shared_holdout_role": _StringSubclass(INSIDER_SHARED_HOLDOUT_ROLE)},
        {"shared_holdout_completion_required_for_paper_promotion": True},
        {"shared_holdout_completion_required_for_paper_promotion": 0},
        {"paper_promotion_sequence": INSIDER_PAPER_PROMOTION_SEQUENCE[:-1]},
        {
            "paper_promotion_sequence": tuple(
                reversed(INSIDER_PAPER_PROMOTION_SEQUENCE)
            )
        },
        {"paper_promotion_sequence": list(INSIDER_PAPER_PROMOTION_SEQUENCE)},
        {
            "paper_promotion_sequence": (
                _StringSubclass(INSIDER_PAPER_PROMOTION_SEQUENCE[0]),
                *INSIDER_PAPER_PROMOTION_SEQUENCE[1:],
            )
        },
        {"paper_pilot_duration_trading_days": 59},
        {"paper_pilot_duration_trading_days": 61},
        {"paper_pilot_duration_trading_days": 60.0},
        {"paper_pilot_duration_trading_days": True},
        {"paper_promotion_prerequisites_confer_deployment_authority": True},
        {"paper_promotion_prerequisites_confer_deployment_authority": 0},
        {"valid_stock_level_null_closes_canonical_family": False},
        {"post_result_tuning_or_rerun_authorized": True},
        {"later_hypothesis_requires_separate_preregistered_family": False},
        {
            "later_family_requires_owner_authorized_permanent_look_budget": (
                False
            )
        },
        {"later_family_can_retroactively_rescue_canonical_result": True},
        {"etf_can_rescue_valid_stock_null": True},
        {"qc_can_rescue_valid_stock_null": True},
        {"future_qc_stage": "IB-6"},
        {"future_qc_input_contract": "call_vendor_from_backtest"},
    ],
)
def test_multiplicity_allocation_holdout_and_null_mutations_refuse(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InsiderBuyingPreregistrationError, match="REFUSED"):
        replace(INSIDER_BUYING_RESEARCH_GATE, **changes)


@pytest.mark.parametrize(
    "field_name",
    [
        "network_access_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "credential_access_authorized",
        "licensed_row_access_authorized",
        "outcome_access_authorized",
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
    ],
)
def test_each_authority_mutation_refuses(field_name: str) -> None:
    with pytest.raises(InsiderBuyingPreregistrationError, match=field_name):
        replace(INSIDER_BUYING_RESEARCH_GATE, **{field_name: True})


@pytest.mark.parametrize(
    "field_name",
    [
        "network_access_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "credential_access_authorized",
        "licensed_row_access_authorized",
        "outcome_access_authorized",
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
    ],
)
def test_semantic_hash_binds_every_authority_field(field_name: str) -> None:
    forged = copy.copy(INSIDER_BUYING_RESEARCH_GATE)
    object.__setattr__(forged, field_name, True)

    assert forged.semantic_sha256 != INSIDER_BUYING_RESEARCH_GATE_SHA256


@pytest.mark.parametrize(
    "field_name",
    [
        "network_access_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "credential_access_authorized",
        "licensed_row_access_authorized",
        "outcome_access_authorized",
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
    ],
)
def test_falsey_non_boolean_authority_mutations_refuse(field_name: str) -> None:
    with pytest.raises(InsiderBuyingPreregistrationError, match=field_name):
        replace(INSIDER_BUYING_RESEARCH_GATE, **{field_name: 0})


def test_lane_maxima_must_still_multiply_to_the_shared_fwer(monkeypatch) -> None:
    """The 4 x 1/80 = 1/20 equation must fail closed if a constant drifts.

    Every alpha field is pinned to its module constant, so the product
    equation can only fire when a constant is edited inconsistently - exactly
    the mistake it exists to catch. Patch the lane maximum and supply the
    matching value so the per-field checks pass and the cross-check is reached.
    """
    drifted = Fraction(1, 40)
    monkeypatch.setattr(
        preregistration, "PERMANENT_LANE_ALPHA_MAXIMUM", drifted
    )

    with pytest.raises(
        InsiderBuyingPreregistrationError,
        match="four permanent lane maxima do not equal shared FWER",
    ):
        InsiderBuyingResearchGate(
            permanent_lane_alpha_maximum=drifted,
            within_lane_confirmatory_alpha_ceiling=drifted,
        )


def test_research_cutoff_must_still_precede_the_final_holdout(monkeypatch) -> None:
    """A cutoff that reaches into the reserved holdout must fail closed.

    The three dates are pinned to constants, so the ordering check is only
    reachable through constant drift. A cutoff on or after the holdout start
    would let this lane consume reserved evidence.
    """
    overlapping_start = date(2027, 8, 31)
    monkeypatch.setattr(
        preregistration, "SHARED_HOLDOUT_START", overlapping_start
    )

    with pytest.raises(
        InsiderBuyingPreregistrationError,
        match="shared research and final-holdout periods overlap",
    ):
        InsiderBuyingResearchGate(shared_holdout_start=overlapping_start)


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
        "research",
    }
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
