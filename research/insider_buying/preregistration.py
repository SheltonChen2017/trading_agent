"""Zero-authority research gate for the Insider Buying lane.

IB-1I records the owner-directed four-strategy multiplicity ceiling and the
shared final-holdout boundary before any outcome can be inspected.  It does
not choose a confirmatory horizon, cell, or permanent look: those allocations
remain an explicit owner decision.  This module has no data acquisition,
outcome, QuantConnect, broker, deployment, or execution surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from fractions import Fraction

from data.hashing import canonical_json, hash_bytes
from research.insider_buying.contracts import CANONICAL_SPEC, ContractError


INSIDER_BUYING_RESEARCH_GATE_VERSION = "INSETF-IB1I-RESEARCH-GATE-v1"
INSIDER_BUYING_BLUEPRINT_PATH = (
    "docs/Strategy Description/INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf"
)
INSIDER_BUYING_BLUEPRINT_SHA256 = (
    "f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c"
)
MULTIPLICITY_DIRECTIVE_ID = "owner-multiplicity-amendment-2026-08-30"
MULTIPLICITY_DIRECTIVE_PATH = "docs/ACTION_PLAN_2026-08-20.md"
MULTIPLICITY_DIRECTIVE_COMMIT = (
    "6b12102b9710efb838e41cefd94cfcecd3ab592d"
)
MULTIPLICITY_DIRECTIVE_EFFECTIVE_DATE = date(2026, 8, 30)
SHARED_FAMILY_DIRECTIVE_ID = (
    "owner-coordinated-shared-family-amendment-2026-08-29"
)
SHARED_FAMILY_DIRECTIVE_PATH = "docs/THREE_STRATEGY_PROJECT_DIRECTION.md"
SHARED_FAMILY_DIRECTIVE_COMMIT = (
    "ba01e98f9d3c8746c70182818a27a2d49a9c0fe7"
)
SHARED_FAMILY_DIRECTIVE_EFFECTIVE_DATE = date(2026, 8, 29)
FIXED_STRATEGY_LANE_IDS = (
    "analyst-revisions-v2",
    "insider-buying",
    "short-interest",
    "target-price-revisions",
)
INSIDER_BUYING_LANE_ID = "insider-buying"
IB0_CONTRACT_VERSION = "INSETF-IB0-v1"
CANDIDATE_PRIMARY_HORIZONS_TRADING_DAYS = (5, 20, 60)
SHARED_TWO_SIDED_FWER = Fraction(1, 20)
PERMANENT_LANE_ALPHA_MAXIMUM = Fraction(1, 80)
SHARED_RESEARCH_CUTOFF = date(2027, 8, 31)
SHARED_HOLDOUT_START = date(2027, 9, 1)
SHARED_HOLDOUT_END = date(2029, 8, 31)
FUTURE_QC_STAGE = "IB-7"
FUTURE_QC_INPUT_CONTRACT = (
    "independently_reviewed_immutable_precomputed_or_custom_signals_only"
)


class InsiderBuyingPreregistrationError(ContractError):
    """The sealed IB-1I research gate failed closed."""


class InsiderBuyingAllocationState(str, Enum):
    """Whether permanent within-lane alpha allocations have been approved."""

    OWNER_DECISION_REQUIRED = "owner_decision_required"


class InsiderBuyingSlotDisposition(str, Enum):
    """Permanent disposition of an unused or withdrawn lane slot."""

    EXPIRES = "expires"


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
    }


@dataclass(frozen=True)
class InsiderBuyingResearchGate:
    """Sealed, outcome-inert family and authority contract for IB-1I."""

    version: str = INSIDER_BUYING_RESEARCH_GATE_VERSION
    blueprint_path: str = INSIDER_BUYING_BLUEPRINT_PATH
    blueprint_sha256: str = INSIDER_BUYING_BLUEPRINT_SHA256
    ib0_contract_version: str = IB0_CONTRACT_VERSION
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
    assigned_lane_id: str = INSIDER_BUYING_LANE_ID
    shared_two_sided_fwer: Fraction = SHARED_TWO_SIDED_FWER
    permanent_lane_alpha_maximum: Fraction = PERMANENT_LANE_ALPHA_MAXIMUM
    within_lane_confirmatory_alpha_ceiling: Fraction = (
        PERMANENT_LANE_ALPHA_MAXIMUM
    )
    unused_slot_disposition: InsiderBuyingSlotDisposition = (
        InsiderBuyingSlotDisposition.EXPIRES
    )
    withdrawn_slot_disposition: InsiderBuyingSlotDisposition = (
        InsiderBuyingSlotDisposition.EXPIRES
    )
    slot_transfer_authorized: bool = False
    slot_redistribution_authorized: bool = False
    denominator_recomputation_authorized: bool = False
    candidate_primary_horizons_trading_days: tuple[int, ...] = (
        CANDIDATE_PRIMARY_HORIZONS_TRADING_DAYS
    )
    confirmatory_alpha_allocations: tuple[tuple[str, Fraction], ...] = ()
    permanent_look_ids: tuple[str, ...] = ()
    allocation_state: InsiderBuyingAllocationState = (
        InsiderBuyingAllocationState.OWNER_DECISION_REQUIRED
    )
    shared_research_cutoff: date = SHARED_RESEARCH_CUTOFF
    shared_holdout_start: date = SHARED_HOLDOUT_START
    shared_holdout_end: date = SHARED_HOLDOUT_END
    shared_holdout_access_authorized: bool = False
    valid_stock_level_null_closes_canonical_family: bool = True
    post_result_tuning_or_rerun_authorized: bool = False
    later_hypothesis_requires_separate_preregistered_family: bool = True
    later_family_requires_owner_authorized_permanent_look_budget: bool = True
    later_family_can_retroactively_rescue_canonical_result: bool = False
    etf_can_rescue_valid_stock_null: bool = False
    qc_can_rescue_valid_stock_null: bool = False
    future_qc_stage: str = FUTURE_QC_STAGE
    future_qc_input_contract: str = FUTURE_QC_INPUT_CONTRACT
    authorized_outcome_looks: int = 0
    consumed_outcome_looks: int = 0
    network_access_authorized: bool = False
    sec_access_authorized: bool = False
    provider_access_authorized: bool = False
    credential_access_authorized: bool = False
    licensed_row_access_authorized: bool = False
    outcome_access_authorized: bool = False
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
        if type(self.version) is not str or (
            self.version != INSIDER_BUYING_RESEARCH_GATE_VERSION
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: research-gate version is not the sealed IB-1I version"
            )
        if (
            type(self.blueprint_path) is not str
            or self.blueprint_path != INSIDER_BUYING_BLUEPRINT_PATH
            or type(self.blueprint_sha256) is not str
            or self.blueprint_sha256 != INSIDER_BUYING_BLUEPRINT_SHA256
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: research gate is not bound to the governing blueprint"
            )
        if (
            type(self.ib0_contract_version) is not str
            or self.ib0_contract_version != IB0_CONTRACT_VERSION
            or CANONICAL_SPEC.version != IB0_CONTRACT_VERSION
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: IB-0 contract version drifted from the IB-1I gate"
            )
        for field_name, value, expected in (
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
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} changed from the governing directive"
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
        ):
            if type(value) is not date or value != expected:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} changed from the governing directive"
                )
        if (
            type(self.fixed_lane_ids) is not tuple
            or any(type(lane_id) is not str for lane_id in self.fixed_lane_ids)
            or self.fixed_lane_ids != FIXED_STRATEGY_LANE_IDS
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: strategy-selection family must retain four fixed lanes"
            )
        if type(self.assigned_lane_id) is not str or (
            self.assigned_lane_id != INSIDER_BUYING_LANE_ID
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: this gate is assigned only to the Insider Buying lane"
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
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} is not the owner-directed exact fraction"
                )
        if (
            len(self.fixed_lane_ids) * self.permanent_lane_alpha_maximum
            != self.shared_two_sided_fwer
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: four permanent lane maxima do not equal shared FWER"
            )
        if (
            not isinstance(
                self.unused_slot_disposition, InsiderBuyingSlotDisposition
            )
            or self.unused_slot_disposition
            is not InsiderBuyingSlotDisposition.EXPIRES
            or not isinstance(
                self.withdrawn_slot_disposition, InsiderBuyingSlotDisposition
            )
            or self.withdrawn_slot_disposition
            is not InsiderBuyingSlotDisposition.EXPIRES
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: unused and withdrawn lane allocations must expire"
            )
        for field_name in (
            "slot_transfer_authorized",
            "slot_redistribution_authorized",
            "denominator_recomputation_authorized",
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} must remain false"
                )
        if (
            type(self.candidate_primary_horizons_trading_days) is not tuple
            or any(
                type(horizon) is not int
                for horizon in self.candidate_primary_horizons_trading_days
            )
            or self.candidate_primary_horizons_trading_days
            != CANDIDATE_PRIMARY_HORIZONS_TRADING_DAYS
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: blueprint candidate horizons changed"
            )
        if CANONICAL_SPEC.primary_horizons_trading_days != (
            CANDIDATE_PRIMARY_HORIZONS_TRADING_DAYS
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: IB-0 primary horizons drifted from the IB-1I gate"
            )
        if (
            type(CANONICAL_SPEC.outcomes_authorized) is not bool
            or CANONICAL_SPEC.outcomes_authorized
            or type(CANONICAL_SPEC.authorized_outcome_looks) is not int
            or CANONICAL_SPEC.authorized_outcome_looks != 0
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: IB-0 outcome authority drifted from exact zero"
            )
        if (
            type(self.confirmatory_alpha_allocations) is not tuple
            or self.confirmatory_alpha_allocations
            or type(self.permanent_look_ids) is not tuple
            or self.permanent_look_ids
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: permanent cells and looks require an owner decision"
            )
        if (
            not isinstance(self.allocation_state, InsiderBuyingAllocationState)
            or self.allocation_state
            is not InsiderBuyingAllocationState.OWNER_DECISION_REQUIRED
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: within-lane alpha allocation still requires owner decision"
            )
        for field_name, value, expected in (
            (
                "shared_research_cutoff",
                self.shared_research_cutoff,
                SHARED_RESEARCH_CUTOFF,
            ),
            ("shared_holdout_start", self.shared_holdout_start, SHARED_HOLDOUT_START),
            ("shared_holdout_end", self.shared_holdout_end, SHARED_HOLDOUT_END),
        ):
            if type(value) is not date or value != expected:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} changed from the shared boundary"
                )
        if self.shared_research_cutoff >= self.shared_holdout_start or (
            self.shared_holdout_start > self.shared_holdout_end
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: shared research and final-holdout periods overlap"
            )
        if (
            type(self.shared_holdout_access_authorized) is not bool
            or self.shared_holdout_access_authorized
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: the shared final holdout is unavailable to this lane"
            )
        for field_name in (
            "valid_stock_level_null_closes_canonical_family",
            "later_hypothesis_requires_separate_preregistered_family",
            "later_family_requires_owner_authorized_permanent_look_budget",
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or not value:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} must remain true"
                )
        for field_name in (
            "post_result_tuning_or_rerun_authorized",
            "later_family_can_retroactively_rescue_canonical_result",
            "etf_can_rescue_valid_stock_null",
            "qc_can_rescue_valid_stock_null",
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} must remain false"
                )
        if type(self.future_qc_stage) is not str or (
            self.future_qc_stage != FUTURE_QC_STAGE
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: future QC work must remain at IB-7"
            )
        if type(self.future_qc_input_contract) is not str or (
            self.future_qc_input_contract != FUTURE_QC_INPUT_CONTRACT
        ):
            raise InsiderBuyingPreregistrationError(
                "REFUSED: future QC inputs are not constrained to reviewed artifacts"
            )
        for field_name in ("authorized_outcome_looks", "consumed_outcome_looks"):
            value = getattr(self, field_name)
            if type(value) is not int or value != 0:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} must remain exact integer zero"
                )
        for field_name in (
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
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise InsiderBuyingPreregistrationError(
                    f"REFUSED: {field_name} must remain false"
                )

    def to_payload(self) -> dict[str, object]:
        """Return a fresh canonical-JSON-safe representation of the gate."""

        return {
            "schema": "insider-buying-four-family-research-gate-v1",
            "version": self.version,
            "governing_blueprint": {
                "path": self.blueprint_path,
                "sha256": self.blueprint_sha256,
            },
            "ib0_contract_version": self.ib0_contract_version,
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
                "shared_family_count": len(self.fixed_lane_ids),
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
                "withdrawn_slot_disposition": (
                    self.withdrawn_slot_disposition.value
                ),
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
                "candidate_primary_horizons_trading_days": list(
                    self.candidate_primary_horizons_trading_days
                ),
                "confirmatory_alpha_allocations": [
                    {
                        "cell_or_look_id": allocation_id,
                        "two_sided_alpha": _fraction_payload(alpha),
                    }
                    for allocation_id, alpha in self.confirmatory_alpha_allocations
                ],
                "permanent_look_ids": list(self.permanent_look_ids),
                "authorized_outcome_looks": self.authorized_outcome_looks,
                "consumed_outcome_looks": self.consumed_outcome_looks,
            },
            "shared_holdout": {
                "research_cutoff": self.shared_research_cutoff.isoformat(),
                "reserved_start": self.shared_holdout_start.isoformat(),
                "reserved_end": self.shared_holdout_end.isoformat(),
                "lane_access_authorized": (
                    self.shared_holdout_access_authorized
                ),
            },
            "stock_first_gate": {
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
                "etf_can_rescue_valid_stock_null": (
                    self.etf_can_rescue_valid_stock_null
                ),
                "qc_can_rescue_valid_stock_null": (
                    self.qc_can_rescue_valid_stock_null
                ),
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
                "network_access_authorized": self.network_access_authorized,
                "sec_access_authorized": self.sec_access_authorized,
                "provider_access_authorized": self.provider_access_authorized,
                "credential_access_authorized": self.credential_access_authorized,
                "licensed_row_access_authorized": (
                    self.licensed_row_access_authorized
                ),
                "outcome_access_authorized": self.outcome_access_authorized,
                "common_four_family_outcome_evaluation_authorized": (
                    self.common_four_family_outcome_evaluation_authorized
                ),
                "integration_authorized": self.integration_authorized,
                "capital_authorized": self.capital_authorized,
                "broker_access_authorized": self.broker_access_authorized,
                "operator_database_access_authorized": (
                    self.operator_database_access_authorized
                ),
                "scheduler_access_authorized": self.scheduler_access_authorized,
                "paper_trading_authorized": self.paper_trading_authorized,
                "live_trading_authorized": self.live_trading_authorized,
                "deployment_authorized": self.deployment_authorized,
                "trading_authority": self.trading_authority,
            },
        }

    @property
    def semantic_sha256(self) -> str:
        payload = (canonical_json(self.to_payload()) + "\n").encode("utf-8")
        return hash_bytes(payload)


INSIDER_BUYING_RESEARCH_GATE = InsiderBuyingResearchGate()
INSIDER_BUYING_RESEARCH_GATE_SHA256 = (
    INSIDER_BUYING_RESEARCH_GATE.semantic_sha256
)
