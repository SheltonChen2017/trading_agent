"""Frozen SI-0 choices and the additive, zero-authority SI-0M gate.

The original fixture preregistration keeps its historical payload identity.
The later family-multiplicity and holdout amendments are bound separately;
they grant no research look, data access, or operational authority. Licensed
data, empirical allocations, extensions, and changes require a new
owner-authorized milestone and a recorded preregistration change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from fractions import Fraction
from typing import Any

from data.hashing import hash_payload


@dataclass(frozen=True)
class ShortInterestPreregistration:
    source_semantic: str = field(
        default="official_open_short_position_snapshot", init=False
    )
    execution_calendar: str = field(default="XNYS", init=False)
    canonical_denominator: str = field(
        default="point_in_time_shares_outstanding", init=False
    )
    audited_preferred_denominator: str = field(
        default="point_in_time_float", init=False
    )
    score_family: tuple[str, ...] = field(
        default=(
            "S0_level",
            "S1_delta",
            "S2_surprise",
            "S3_delta_dtc",
            "S4_residual",
        ),
        init=False,
    )
    canonical_score: str = field(default="S1_delta", init=False)
    primary_horizon_sessions: int = field(default=20, init=False)
    primary_cost_bps: int = field(default=10, init=False)
    cost_sensitivity_bps: tuple[int, ...] = field(default=(0, 5, 20), init=False)
    canonical_leverage: int = field(default=1, init=False)
    milestone_outcome_look_budget: int = field(default=0, init=False)
    outcome_looks_used: int = field(default=0, init=False)
    production_authoritative: bool = field(default=False, init=False)
    schema_version: str = field(default="1.0", init=False)

    def to_payload(self) -> dict[str, Any]:
        return {
            "audited_preferred_denominator": self.audited_preferred_denominator,
            "canonical_denominator": self.canonical_denominator,
            "canonical_leverage": self.canonical_leverage,
            "canonical_score": self.canonical_score,
            "cost_sensitivity_bps": list(self.cost_sensitivity_bps),
            "execution_calendar": self.execution_calendar,
            "milestone_outcome_look_budget": self.milestone_outcome_look_budget,
            "outcome_looks_used": self.outcome_looks_used,
            "primary_cost_bps": self.primary_cost_bps,
            "primary_horizon_sessions": self.primary_horizon_sessions,
            "production_authoritative": self.production_authoritative,
            "schema_version": self.schema_version,
            "score_family": list(self.score_family),
            "source_semantic": self.source_semantic,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


PREREGISTRATION = ShortInterestPreregistration()


SHORT_INTEREST_RESEARCH_GATE_VERSION = "SIETF-SI0M-RESEARCH-GATE-v1"
SHORT_INTEREST_BLUEPRINT_PATH = (
    "docs/Strategy Description/SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf"
)
SHORT_INTEREST_BLUEPRINT_SHA256 = (
    "2f7ccff9bcd35810b11350314fd6e47c7c92e24ac35a866addb82ce66645b14c"
)
LEGACY_PREREGISTRATION_SHA256 = (
    "83165e805a8ad91787d10f066b28e14a1d6655d2dd19c4b5efd8a02a1ceeef9f"
)
MULTIPLICITY_DIRECTIVE_ID = "owner-multiplicity-amendment-2026-08-30"
MULTIPLICITY_DIRECTIVE_PATH = "docs/ACTION_PLAN_2026-08-20.md"
MULTIPLICITY_DIRECTIVE_COMMIT = "6b12102b9710efb838e41cefd94cfcecd3ab592d"
MULTIPLICITY_DIRECTIVE_EFFECTIVE_DATE = date(2026, 8, 30)
SHARED_FAMILY_DIRECTIVE_ID = "owner-coordinated-shared-family-amendment-2026-08-29"
SHARED_FAMILY_DIRECTIVE_PATH = "docs/THREE_STRATEGY_PROJECT_DIRECTION.md"
SHARED_FAMILY_DIRECTIVE_COMMIT = "ba01e98f9d3c8746c70182818a27a2d49a9c0fe7"
SHARED_FAMILY_DIRECTIVE_EFFECTIVE_DATE = date(2026, 8, 29)
FIXED_STRATEGY_LANE_IDS = (
    "analyst-revisions-v2",
    "insider-buying",
    "short-interest",
    "target-price-revisions",
)
SHORT_INTEREST_LANE_ID = "short-interest"
SHARED_TWO_SIDED_FWER = Fraction(1, 20)
PERMANENT_LANE_ALPHA_MAXIMUM = Fraction(1, 80)
SHARED_RESEARCH_CUTOFF = date(2027, 8, 31)
SHARED_HOLDOUT_START = date(2027, 9, 1)
SHARED_HOLDOUT_END = date(2029, 8, 31)
FUTURE_QC_STAGE = "SI-7"
FUTURE_QC_INPUT_CONTRACT = (
    "independently_reviewed_immutable_precomputed_or_custom_signals_only"
)


class ShortInterestPreregistrationError(ValueError):
    """The sealed SI-0M zero-access research gate failed closed."""


class ShortInterestAllocationState(str, Enum):
    """Whether permanent within-lane cells and looks have been approved."""

    OWNER_DECISION_REQUIRED = "owner_decision_required"


class ShortInterestSlotDisposition(str, Enum):
    """Permanent disposition of an unused or withdrawn family slot."""

    EXPIRES = "expires"


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


_FALSE_AUTHORITY_FIELDS = (
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


@dataclass(frozen=True)
class ShortInterestResearchGate:
    """Additive SI-0M multiplicity freeze with every empirical gate closed.

    This gate deliberately binds, rather than replaces, the original SI-0
    preregistration. Existing synthetic artifacts therefore retain their
    authenticated preregistration identity while the later owner amendments
    become a separate content-addressed prerequisite for any outcome work.
    """

    version: str = SHORT_INTEREST_RESEARCH_GATE_VERSION
    blueprint_path: str = SHORT_INTEREST_BLUEPRINT_PATH
    blueprint_sha256: str = SHORT_INTEREST_BLUEPRINT_SHA256
    legacy_preregistration_sha256: str = LEGACY_PREREGISTRATION_SHA256
    multiplicity_directive_id: str = MULTIPLICITY_DIRECTIVE_ID
    multiplicity_directive_path: str = MULTIPLICITY_DIRECTIVE_PATH
    multiplicity_directive_commit: str = MULTIPLICITY_DIRECTIVE_COMMIT
    multiplicity_directive_effective_date: date = (
        MULTIPLICITY_DIRECTIVE_EFFECTIVE_DATE
    )
    shared_family_directive_id: str = SHARED_FAMILY_DIRECTIVE_ID
    shared_family_directive_path: str = SHARED_FAMILY_DIRECTIVE_PATH
    shared_family_directive_commit: str = SHARED_FAMILY_DIRECTIVE_COMMIT
    shared_family_directive_effective_date: date = (
        SHARED_FAMILY_DIRECTIVE_EFFECTIVE_DATE
    )
    fixed_lane_ids: tuple[str, ...] = FIXED_STRATEGY_LANE_IDS
    assigned_lane_id: str = SHORT_INTEREST_LANE_ID
    shared_two_sided_fwer: Fraction = SHARED_TWO_SIDED_FWER
    permanent_lane_alpha_maximum: Fraction = PERMANENT_LANE_ALPHA_MAXIMUM
    within_lane_confirmatory_alpha_ceiling: Fraction = (
        PERMANENT_LANE_ALPHA_MAXIMUM
    )
    unused_slot_disposition: ShortInterestSlotDisposition = (
        ShortInterestSlotDisposition.EXPIRES
    )
    withdrawn_slot_disposition: ShortInterestSlotDisposition = (
        ShortInterestSlotDisposition.EXPIRES
    )
    slot_transfer_authorized: bool = False
    slot_redistribution_authorized: bool = False
    denominator_recomputation_authorized: bool = False
    confirmatory_alpha_allocations: tuple[tuple[str, Fraction], ...] = ()
    permanent_look_ids: tuple[str, ...] = ()
    allocation_state: ShortInterestAllocationState = (
        ShortInterestAllocationState.OWNER_DECISION_REQUIRED
    )
    shared_research_cutoff: date = SHARED_RESEARCH_CUTOFF
    shared_holdout_start: date = SHARED_HOLDOUT_START
    shared_holdout_end: date = SHARED_HOLDOUT_END
    valid_stock_level_null_closes_canonical_family: bool = True
    post_result_tuning_or_rerun_authorized: bool = False
    later_hypothesis_requires_separate_preregistered_family: bool = True
    later_family_requires_owner_authorized_permanent_look_budget: bool = True
    later_family_can_retroactively_rescue_canonical_result: bool = False
    industry_can_rescue_valid_stock_null: bool = False
    etf_can_rescue_valid_stock_null: bool = False
    qc_can_rescue_valid_stock_null: bool = False
    future_qc_stage: str = FUTURE_QC_STAGE
    future_qc_input_contract: str = FUTURE_QC_INPUT_CONTRACT
    authorized_outcome_looks: int = 0
    consumed_outcome_looks: int = 0
    network_access_authorized: bool = False
    finra_access_authorized: bool = False
    provider_access_authorized: bool = False
    source_data_request_authorized: bool = False
    credential_access_authorized: bool = False
    licensed_row_access_authorized: bool = False
    outcome_access_authorized: bool = False
    shared_holdout_access_authorized: bool = False
    qc_upload_authorized: bool = False
    qc_processing_authorized: bool = False
    qc_job_authorized: bool = False
    qc_backtest_authorized: bool = False
    qc_research_inputs_execution_authority: bool = False
    common_four_family_outcome_evaluation_authorized: bool = False
    integration_authorized: bool = False
    capital_authorized: bool = False
    broker_access_authorized: bool = False
    operator_database_access_authorized: bool = False
    scheduler_access_authorized: bool = False
    paper_trading_authorized: bool = False
    live_trading_authorized: bool = False
    deployment_authorized: bool = False
    trading_authority: bool = False

    def __post_init__(self) -> None:
        if type(self) is not ShortInterestResearchGate:
            raise ShortInterestPreregistrationError(
                "REFUSED: research gate must be the exact frozen contract type"
            )
        for field_name, value, expected in (
            ("version", self.version, SHORT_INTEREST_RESEARCH_GATE_VERSION),
            ("blueprint_path", self.blueprint_path, SHORT_INTEREST_BLUEPRINT_PATH),
            (
                "blueprint_sha256",
                self.blueprint_sha256,
                SHORT_INTEREST_BLUEPRINT_SHA256,
            ),
            (
                "legacy_preregistration_sha256",
                self.legacy_preregistration_sha256,
                LEGACY_PREREGISTRATION_SHA256,
            ),
            (
                "multiplicity_directive_id",
                self.multiplicity_directive_id,
                MULTIPLICITY_DIRECTIVE_ID,
            ),
            (
                "multiplicity_directive_path",
                self.multiplicity_directive_path,
                MULTIPLICITY_DIRECTIVE_PATH,
            ),
            (
                "multiplicity_directive_commit",
                self.multiplicity_directive_commit,
                MULTIPLICITY_DIRECTIVE_COMMIT,
            ),
            (
                "shared_family_directive_id",
                self.shared_family_directive_id,
                SHARED_FAMILY_DIRECTIVE_ID,
            ),
            (
                "shared_family_directive_path",
                self.shared_family_directive_path,
                SHARED_FAMILY_DIRECTIVE_PATH,
            ),
            (
                "shared_family_directive_commit",
                self.shared_family_directive_commit,
                SHARED_FAMILY_DIRECTIVE_COMMIT,
            ),
        ):
            if type(value) is not str or value != expected:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} changed from its frozen authority"
                )
        if type(PREREGISTRATION) is not ShortInterestPreregistration:
            raise ShortInterestPreregistrationError(
                "REFUSED: legacy SI-0 preregistration must retain its exact type"
            )
        for field_name, value, expected in (
            (
                "source_semantic",
                PREREGISTRATION.source_semantic,
                "official_open_short_position_snapshot",
            ),
            ("execution_calendar", PREREGISTRATION.execution_calendar, "XNYS"),
            (
                "canonical_denominator",
                PREREGISTRATION.canonical_denominator,
                "point_in_time_shares_outstanding",
            ),
            (
                "audited_preferred_denominator",
                PREREGISTRATION.audited_preferred_denominator,
                "point_in_time_float",
            ),
            ("canonical_score", PREREGISTRATION.canonical_score, "S1_delta"),
            ("schema_version", PREREGISTRATION.schema_version, "1.0"),
        ):
            if type(value) is not str or value != expected:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: legacy SI-0 {field_name} drifted"
                )
        expected_score_family = (
            "S0_level",
            "S1_delta",
            "S2_surprise",
            "S3_delta_dtc",
            "S4_residual",
        )
        if (
            type(PREREGISTRATION.score_family) is not tuple
            or any(type(item) is not str for item in PREREGISTRATION.score_family)
            or PREREGISTRATION.score_family != expected_score_family
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: legacy SI-0 score_family drifted"
            )
        for field_name, value, expected in (
            (
                "primary_horizon_sessions",
                PREREGISTRATION.primary_horizon_sessions,
                20,
            ),
            ("primary_cost_bps", PREREGISTRATION.primary_cost_bps, 10),
            ("canonical_leverage", PREREGISTRATION.canonical_leverage, 1),
            (
                "milestone_outcome_look_budget",
                PREREGISTRATION.milestone_outcome_look_budget,
                0,
            ),
            ("outcome_looks_used", PREREGISTRATION.outcome_looks_used, 0),
        ):
            if type(value) is not int or value != expected:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: legacy SI-0 {field_name} drifted"
                )
        if (
            type(PREREGISTRATION.cost_sensitivity_bps) is not tuple
            or any(
                type(item) is not int
                for item in PREREGISTRATION.cost_sensitivity_bps
            )
            or PREREGISTRATION.cost_sensitivity_bps != (0, 5, 20)
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: legacy SI-0 cost_sensitivity_bps drifted"
            )
        if (
            type(PREREGISTRATION.production_authoritative) is not bool
            or PREREGISTRATION.production_authoritative
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: legacy SI-0 production_authoritative drifted"
            )
        legacy_payload = ShortInterestPreregistration.to_payload(PREREGISTRATION)
        if hash_payload(legacy_payload) != LEGACY_PREREGISTRATION_SHA256:
            raise ShortInterestPreregistrationError(
                "REFUSED: the legacy SI-0 preregistration identity drifted"
            )
        for field_name, value, expected in (
            (
                "multiplicity_directive_effective_date",
                self.multiplicity_directive_effective_date,
                MULTIPLICITY_DIRECTIVE_EFFECTIVE_DATE,
            ),
            (
                "shared_family_directive_effective_date",
                self.shared_family_directive_effective_date,
                SHARED_FAMILY_DIRECTIVE_EFFECTIVE_DATE,
            ),
            (
                "shared_research_cutoff",
                self.shared_research_cutoff,
                SHARED_RESEARCH_CUTOFF,
            ),
            ("shared_holdout_start", self.shared_holdout_start, SHARED_HOLDOUT_START),
            ("shared_holdout_end", self.shared_holdout_end, SHARED_HOLDOUT_END),
        ):
            if type(value) is not date or value != expected:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} changed from its frozen date"
                )
        if (
            type(self.fixed_lane_ids) is not tuple
            or any(type(lane_id) is not str for lane_id in self.fixed_lane_ids)
            or self.fixed_lane_ids != FIXED_STRATEGY_LANE_IDS
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: strategy-selection family must retain four fixed lanes"
            )
        if type(self.assigned_lane_id) is not str or (
            self.assigned_lane_id != SHORT_INTEREST_LANE_ID
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: this gate is assigned only to the Short Interest lane"
            )
        for field_name, value, expected in (
            (
                "shared_two_sided_fwer",
                self.shared_two_sided_fwer,
                SHARED_TWO_SIDED_FWER,
            ),
            (
                "permanent_lane_alpha_maximum",
                self.permanent_lane_alpha_maximum,
                PERMANENT_LANE_ALPHA_MAXIMUM,
            ),
            (
                "within_lane_confirmatory_alpha_ceiling",
                self.within_lane_confirmatory_alpha_ceiling,
                PERMANENT_LANE_ALPHA_MAXIMUM,
            ),
        ):
            if type(value) is not Fraction or value != expected:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} is not the owner-directed exact fraction"
                )
        if (
            len(self.fixed_lane_ids) * self.permanent_lane_alpha_maximum
            != self.shared_two_sided_fwer
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: four permanent lane maxima do not equal shared FWER"
            )
        for field_name in (
            "unused_slot_disposition",
            "withdrawn_slot_disposition",
        ):
            value = getattr(self, field_name)
            if (
                type(value) is not ShortInterestSlotDisposition
                or value is not ShortInterestSlotDisposition.EXPIRES
            ):
                raise ShortInterestPreregistrationError(
                    "REFUSED: unused and withdrawn lane allocations must expire"
                )
        for field_name in (
            "slot_transfer_authorized",
            "slot_redistribution_authorized",
            "denominator_recomputation_authorized",
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} must remain false"
                )
        if (
            type(self.confirmatory_alpha_allocations) is not tuple
            or self.confirmatory_alpha_allocations
            or type(self.permanent_look_ids) is not tuple
            or self.permanent_look_ids
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: permanent cells and looks require an owner decision"
            )
        if (
            type(self.allocation_state) is not ShortInterestAllocationState
            or self.allocation_state
            is not ShortInterestAllocationState.OWNER_DECISION_REQUIRED
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: within-lane alpha allocation still requires owner decision"
            )
        if self.shared_research_cutoff >= self.shared_holdout_start or (
            self.shared_holdout_start > self.shared_holdout_end
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: shared research and final-holdout periods overlap"
            )
        for field_name in (
            "valid_stock_level_null_closes_canonical_family",
            "later_hypothesis_requires_separate_preregistered_family",
            "later_family_requires_owner_authorized_permanent_look_budget",
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or not value:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} must remain true"
                )
        for field_name in (
            "post_result_tuning_or_rerun_authorized",
            "later_family_can_retroactively_rescue_canonical_result",
            "industry_can_rescue_valid_stock_null",
            "etf_can_rescue_valid_stock_null",
            "qc_can_rescue_valid_stock_null",
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} must remain false"
                )
        if (
            type(self.future_qc_stage) is not str
            or self.future_qc_stage != FUTURE_QC_STAGE
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: future QC work must remain at SI-7"
            )
        if (
            type(self.future_qc_input_contract) is not str
            or self.future_qc_input_contract != FUTURE_QC_INPUT_CONTRACT
        ):
            raise ShortInterestPreregistrationError(
                "REFUSED: future QC inputs are not constrained to reviewed artifacts"
            )
        for field_name in ("authorized_outcome_looks", "consumed_outcome_looks"):
            value = getattr(self, field_name)
            if type(value) is not int or value != 0:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} must remain exact integer zero"
                )
        for field_name in _FALSE_AUTHORITY_FIELDS:
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise ShortInterestPreregistrationError(
                    f"REFUSED: {field_name} must remain false"
                )

    def to_payload(self) -> dict[str, Any]:
        """Return a fresh canonical-JSON-safe representation of the gate."""

        ShortInterestResearchGate.__post_init__(self)
        return {
            "schema": "short-interest-four-family-research-gate-v1",
            "version": self.version,
            "governing_blueprint": {
                "path": self.blueprint_path,
                "sha256": self.blueprint_sha256,
            },
            "legacy_preregistration_sha256": self.legacy_preregistration_sha256,
            "governance_sources": [
                {
                    "directive_id": self.shared_family_directive_id,
                    "path": self.shared_family_directive_path,
                    "source_commit": self.shared_family_directive_commit,
                    "effective_date": (
                        self.shared_family_directive_effective_date.isoformat()
                    ),
                },
                {
                    "directive_id": self.multiplicity_directive_id,
                    "path": self.multiplicity_directive_path,
                    "source_commit": self.multiplicity_directive_commit,
                    "effective_date": (
                        self.multiplicity_directive_effective_date.isoformat()
                    ),
                },
            ],
            "family_multiplicity": {
                "fixed_lane_ids": list(self.fixed_lane_ids),
                "assigned_lane_id": self.assigned_lane_id,
                "shared_two_sided_fwer": _fraction_payload(
                    self.shared_two_sided_fwer
                ),
                "permanent_lane_alpha_maximum": _fraction_payload(
                    self.permanent_lane_alpha_maximum
                ),
                "within_lane_confirmatory_alpha_ceiling": _fraction_payload(
                    self.within_lane_confirmatory_alpha_ceiling
                ),
                "unused_slot_disposition": self.unused_slot_disposition.value,
                "withdrawn_slot_disposition": self.withdrawn_slot_disposition.value,
                "slot_transfer_authorized": self.slot_transfer_authorized,
                "slot_redistribution_authorized": (
                    self.slot_redistribution_authorized
                ),
                "denominator_recomputation_authorized": (
                    self.denominator_recomputation_authorized
                ),
            },
            "within_lane_allocation": {
                "state": self.allocation_state.value,
                "confirmatory_alpha_allocations": [
                    {
                        "cell_or_look_id": cell_or_look_id,
                        "two_sided_alpha": _fraction_payload(alpha),
                    }
                    for cell_or_look_id, alpha in (
                        self.confirmatory_alpha_allocations
                    )
                ],
                "permanent_look_ids": list(self.permanent_look_ids),
                "authorized_outcome_looks": self.authorized_outcome_looks,
                "consumed_outcome_looks": self.consumed_outcome_looks,
            },
            "shared_evidence_boundary": {
                "research_cutoff": self.shared_research_cutoff.isoformat(),
                "holdout_start": self.shared_holdout_start.isoformat(),
                "holdout_end": self.shared_holdout_end.isoformat(),
                "holdout_access_authorized": (
                    self.shared_holdout_access_authorized
                ),
            },
            "null_and_extension_boundary": {
                "valid_stock_level_null_closes_canonical_family": (
                    self.valid_stock_level_null_closes_canonical_family
                ),
                "post_result_tuning_or_rerun_authorized": (
                    self.post_result_tuning_or_rerun_authorized
                ),
                "later_hypothesis_requires_separate_preregistered_family": (
                    self.later_hypothesis_requires_separate_preregistered_family
                ),
                "later_family_requires_owner_authorized_permanent_look_budget": (
                    self.later_family_requires_owner_authorized_permanent_look_budget
                ),
                "later_family_can_retroactively_rescue_canonical_result": (
                    self.later_family_can_retroactively_rescue_canonical_result
                ),
                "industry_can_rescue_valid_stock_null": (
                    self.industry_can_rescue_valid_stock_null
                ),
                "etf_can_rescue_valid_stock_null": self.etf_can_rescue_valid_stock_null,
                "qc_can_rescue_valid_stock_null": self.qc_can_rescue_valid_stock_null,
            },
            "future_qc_boundary": {
                "stage": self.future_qc_stage,
                "input_contract": self.future_qc_input_contract,
                "upload_authorized": self.qc_upload_authorized,
                "processing_authorized": self.qc_processing_authorized,
                "job_authorized": self.qc_job_authorized,
                "backtest_authorized": self.qc_backtest_authorized,
                "research_inputs_execution_authority": (
                    self.qc_research_inputs_execution_authority
                ),
            },
            "authority": {
                field_name: getattr(self, field_name)
                for field_name in _FALSE_AUTHORITY_FIELDS
            },
        }

    @property
    def semantic_sha256(self) -> str:
        return hash_payload(ShortInterestResearchGate.to_payload(self))


SHORT_INTEREST_RESEARCH_GATE_SHA256 = (
    "1d612d47369dbe642e10323a0154a5b5e1cd671e7e0d1a4f2631cb3f733f0f6e"
)


def require_short_interest_research_gate(
    gate: ShortInterestResearchGate,
) -> str:
    """Validate the gate and return its immutable semantic identity receipt."""

    if type(gate) is not ShortInterestResearchGate:
        raise ShortInterestPreregistrationError(
            "REFUSED: research gate must be the exact frozen contract type"
        )
    payload = ShortInterestResearchGate.to_payload(gate)
    if hash_payload(payload) != SHORT_INTEREST_RESEARCH_GATE_SHA256:
        raise ShortInterestPreregistrationError(
            "REFUSED: research gate does not match the frozen semantic identity"
        )
    return SHORT_INTEREST_RESEARCH_GATE_SHA256


SHORT_INTEREST_RESEARCH_GATE = ShortInterestResearchGate()
require_short_interest_research_gate(SHORT_INTEREST_RESEARCH_GATE)
