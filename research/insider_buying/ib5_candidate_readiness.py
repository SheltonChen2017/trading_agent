"""Synthetic-only IB-5 study-input candidate; never an outcome or QC grant.

The owner delegated pre-outcome policy choices.  This separate v3 candidate
chooses the 20-session stock primary horizon (matching the frozen signal's
20-session half-life), leaves 5/60-session views descriptive, and assigns
1/160 of the permanent 1/80 lane ceiling to the stock cell while reserving
1/160 for a possible later ETF cell.  Neither allocation is spent.  The stock
look ID below is a candidate identifier, NOT a registered permanent look.

Caller-declared artifact names and digests can make an inventory structurally
complete; they cannot attest source authenticity, data rights, point-in-time
semantics, QC entitlement, independent review, or research-look registration.
Every result therefore retains false real-study/QC authority and zero looks.
This module performs no I/O and has no outcome loader or QC client.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from data.hashing import hash_payload
from research.insider_buying.contracts import CANONICAL_SPEC, ContractError
from research.insider_buying.preregistration import (
    INSIDER_BUYING_RESEARCH_GATE,
    INSIDER_BUYING_RESEARCH_GATE_SHA256,
)


IB5_CANDIDATE_VERSION = "INSETF-IB5-CANDIDATE-v3"
IB5_PARENT_GATE_SHA256 = (
    "cb3d8009539ffdba2a383eb949964dc9686fdd64a71c36eb102cc69160b47a8f"
)
IB5_STOCK_PRIMARY_CELL_ID = "ib5-stock-open-market-purchase-20-session-v1"
IB5_STOCK_LOOK_ID_CANDIDATE = "IB5-STOCK-PRIMARY-20S-V1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

_IDENTIFIER_FIELDS = (
    "outcome_dataset_id",
    "outcome_vintage_id",
    "outcome_rights_artifact_id",
    "pit_security_master_id",
    "pit_calendar_id",
    "delisting_return_semantics_id",
    "adjustment_semantics_id",
    "immutable_signal_manifest_id",
    "qc_processing_entitlement_id",
)
_SHA256_FIELDS = (
    "outcome_manifest_sha256",
    "outcome_rights_artifact_sha256",
    "pit_security_master_sha256",
    "pit_calendar_sha256",
    "delisting_return_semantics_sha256",
    "adjustment_semantics_sha256",
    "immutable_signal_manifest_sha256",
    "qc_processing_entitlement_sha256",
)
_DATE_FIELDS = ("outcome_first_session", "outcome_last_session")


class Ib5CandidateError(ContractError):
    """A claimed IB-5 candidate/input shape failed closed."""


@dataclass(frozen=True, slots=True)
class Ib5CandidatePolicy:
    """Exact pre-outcome choice, separate from the sealed zero-look IB-1I gate."""

    version: str = IB5_CANDIDATE_VERSION
    parent_gate_sha256: str = IB5_PARENT_GATE_SHA256
    primary_stock_cell_id: str = IB5_STOCK_PRIMARY_CELL_ID
    stock_look_id_candidate: str = IB5_STOCK_LOOK_ID_CANDIDATE
    stock_primary_horizon_sessions: int = 20
    descriptive_horizons_sessions: tuple[int, int] = (5, 60)
    stock_confirmatory_alpha: Fraction = Fraction(1, 160)
    etf_alpha_reserve: Fraction = Fraction(1, 160)
    alpha_spent: Fraction = Fraction(0, 1)
    etf_cell_executable: bool = False
    valid_stock_null_closes_family: bool = True
    etf_can_rescue_stock_null: bool = False
    qc_can_rescue_stock_null: bool = False
    shared_cutoff: date = date(2027, 8, 31)
    holdout_start: date = date(2027, 9, 1)
    holdout_end: date = date(2029, 8, 31)

    def __post_init__(self) -> None:
        expected = {
            "version": IB5_CANDIDATE_VERSION,
            "parent_gate_sha256": IB5_PARENT_GATE_SHA256,
            "primary_stock_cell_id": IB5_STOCK_PRIMARY_CELL_ID,
            "stock_look_id_candidate": IB5_STOCK_LOOK_ID_CANDIDATE,
            "stock_primary_horizon_sessions": 20,
            "descriptive_horizons_sessions": (5, 60),
            "stock_confirmatory_alpha": Fraction(1, 160),
            "etf_alpha_reserve": Fraction(1, 160),
            "alpha_spent": Fraction(0, 1),
            "etf_cell_executable": False,
            "valid_stock_null_closes_family": True,
            "etf_can_rescue_stock_null": False,
            "qc_can_rescue_stock_null": False,
            "shared_cutoff": INSIDER_BUYING_RESEARCH_GATE.shared_research_cutoff,
            "holdout_start": INSIDER_BUYING_RESEARCH_GATE.shared_holdout_start,
            "holdout_end": INSIDER_BUYING_RESEARCH_GATE.shared_holdout_end,
        }
        for name, value in expected.items():
            observed = getattr(self, name)
            if type(observed) is not type(value) or observed != value:
                raise Ib5CandidateError(f"REFUSED: candidate {name} drifted")
        if (
            INSIDER_BUYING_RESEARCH_GATE_SHA256 != IB5_PARENT_GATE_SHA256
            or INSIDER_BUYING_RESEARCH_GATE.semantic_sha256
            != IB5_PARENT_GATE_SHA256
            or INSIDER_BUYING_RESEARCH_GATE.authorized_outcome_looks != 0
            or INSIDER_BUYING_RESEARCH_GATE.consumed_outcome_looks != 0
            or INSIDER_BUYING_RESEARCH_GATE.outcome_access_authorized
            or INSIDER_BUYING_RESEARCH_GATE.qc_backtest_authorized
            or CANONICAL_SPEC.primary_horizons_trading_days != (5, 20, 60)
            or CANONICAL_SPEC.decay_half_life_trading_days != 20
            or CANONICAL_SPEC.outcomes_authorized
        ):
            raise Ib5CandidateError("REFUSED: sealed IB-0/IB-1I gate drifted")
        if (
            self.stock_confirmatory_alpha + self.etf_alpha_reserve
            != INSIDER_BUYING_RESEARCH_GATE.permanent_lane_alpha_maximum
        ):
            raise Ib5CandidateError("REFUSED: candidate exceeds lane alpha ceiling")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "version": self.version,
            "parent_gate_sha256": self.parent_gate_sha256,
            "primary_stock_cell_id": self.primary_stock_cell_id,
            "stock_look_id_candidate": self.stock_look_id_candidate,
            "stock_look_registered": False,
            "stock_primary_horizon_sessions": self.stock_primary_horizon_sessions,
            "descriptive_horizons_sessions": list(self.descriptive_horizons_sessions),
            "stock_confirmatory_alpha": [
                self.stock_confirmatory_alpha.numerator,
                self.stock_confirmatory_alpha.denominator,
            ],
            "etf_alpha_reserve": [
                self.etf_alpha_reserve.numerator,
                self.etf_alpha_reserve.denominator,
            ],
            "alpha_spent": [self.alpha_spent.numerator, self.alpha_spent.denominator],
            "etf_cell_executable": self.etf_cell_executable,
            "valid_stock_null_closes_family": self.valid_stock_null_closes_family,
            "etf_can_rescue_stock_null": self.etf_can_rescue_stock_null,
            "qc_can_rescue_stock_null": self.qc_can_rescue_stock_null,
            "shared_cutoff": self.shared_cutoff.isoformat(),
            "holdout_start": self.holdout_start.isoformat(),
            "holdout_end": self.holdout_end.isoformat(),
        }

    @property
    def semantic_sha256(self) -> str:
        return hash_payload(self.to_payload())


IB5_CANDIDATE_POLICY = Ib5CandidatePolicy()


@dataclass(frozen=True, slots=True)
class Ib5CallerDeclaredInputs:
    """Unverified locator/rights declarations; never actual source attestations."""

    outcome_dataset_id: str | None = None
    outcome_vintage_id: str | None = None
    outcome_manifest_sha256: str | None = None
    outcome_rights_artifact_id: str | None = None
    outcome_rights_artifact_sha256: str | None = None
    outcome_first_session: date | None = None
    outcome_last_session: date | None = None
    pit_security_master_id: str | None = None
    pit_security_master_sha256: str | None = None
    pit_calendar_id: str | None = None
    pit_calendar_sha256: str | None = None
    delisting_return_semantics_id: str | None = None
    delisting_return_semantics_sha256: str | None = None
    adjustment_semantics_id: str | None = None
    adjustment_semantics_sha256: str | None = None
    immutable_signal_manifest_id: str | None = None
    immutable_signal_manifest_sha256: str | None = None
    qc_processing_entitlement_id: str | None = None
    qc_processing_entitlement_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in _IDENTIFIER_FIELDS:
            value = getattr(self, name)
            if value is not None and (
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
            ):
                raise Ib5CandidateError(f"REFUSED: {name} is not an exact identifier")
        for name in _SHA256_FIELDS:
            value = getattr(self, name)
            if value is not None and (
                type(value) is not str or _SHA256.fullmatch(value) is None
            ):
                raise Ib5CandidateError(f"REFUSED: {name} is not lowercase SHA-256")
        for name in _DATE_FIELDS:
            value = getattr(self, name)
            if value is not None and type(value) is not date:
                raise Ib5CandidateError(f"REFUSED: {name} is not an exact date")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            name: (
                getattr(self, name).isoformat()
                if name in _DATE_FIELDS and getattr(self, name) is not None
                else getattr(self, name)
            )
            for name in (*_IDENTIFIER_FIELDS, *_SHA256_FIELDS, *_DATE_FIELDS)
        }


def _declaration_blockers(inputs: Ib5CallerDeclaredInputs) -> tuple[str, ...]:
    missing = tuple(
        f"missing_{name}"
        for name in (*_IDENTIFIER_FIELDS, *_SHA256_FIELDS, *_DATE_FIELDS)
        if getattr(inputs, name) is None
    )
    temporal: list[str] = []
    if (
        inputs.outcome_first_session is not None
        and inputs.outcome_last_session is not None
        and inputs.outcome_first_session > inputs.outcome_last_session
    ):
        temporal.append("outcome_window_reversed")
    if (
        inputs.outcome_last_session is not None
        and inputs.outcome_last_session > IB5_CANDIDATE_POLICY.shared_cutoff
    ):
        temporal.append("outcome_window_crosses_shared_cutoff")
    return (*missing, *temporal)


@dataclass(frozen=True, slots=True)
class Ib5CandidateReadiness:
    """Structurally complete can be true; real/QC readiness is always false."""

    inputs: Ib5CallerDeclaredInputs
    blockers: tuple[str, ...]
    caller_declarations_complete: bool
    policy_sha256: str = IB5_CANDIDATE_POLICY.semantic_sha256
    source_evidence_independently_verified: bool = False
    stock_look_registered: bool = False
    authorized_outcome_looks: int = 0
    consumed_outcome_looks: int = 0
    outcome_access_authorized: bool = False
    qc_processing_authorized: bool = False
    qc_job_authorized: bool = False
    real_study_ready: bool = False
    qc_parity_ready: bool = False

    def __post_init__(self) -> None:
        if type(self.inputs) is not Ib5CallerDeclaredInputs:
            raise Ib5CandidateError("REFUSED: inputs are not exact declarations")
        self.inputs.__post_init__()
        expected_blockers = _declaration_blockers(self.inputs)
        if type(self.blockers) is not tuple or self.blockers != expected_blockers:
            raise Ib5CandidateError("REFUSED: declaration blockers drifted")
        if (
            type(self.caller_declarations_complete) is not bool
            or self.caller_declarations_complete != (not expected_blockers)
        ):
            raise Ib5CandidateError("REFUSED: declaration completeness drifted")
        if (
            type(self.policy_sha256) is not str
            or self.policy_sha256 != IB5_CANDIDATE_POLICY.semantic_sha256
        ):
            raise Ib5CandidateError("REFUSED: candidate policy identity drifted")
        for name in (
            "source_evidence_independently_verified",
            "stock_look_registered",
            "outcome_access_authorized",
            "qc_processing_authorized",
            "qc_job_authorized",
            "real_study_ready",
            "qc_parity_ready",
        ):
            value = getattr(self, name)
            if type(value) is not bool or value:
                raise Ib5CandidateError(f"REFUSED: {name} cannot be promoted")
        for name in ("authorized_outcome_looks", "consumed_outcome_looks"):
            value = getattr(self, name)
            if type(value) is not int or value != 0:
                raise Ib5CandidateError(f"REFUSED: {name} must remain zero")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "policy_sha256": self.policy_sha256,
            "inputs": self.inputs.to_payload(),
            "blockers": list(self.blockers),
            "caller_declarations_complete": self.caller_declarations_complete,
            "source_evidence_independently_verified": False,
            "stock_look_registered": False,
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
            "outcome_access_authorized": False,
            "qc_processing_authorized": False,
            "qc_job_authorized": False,
            "real_study_ready": False,
            "qc_parity_ready": False,
        }

    @property
    def semantic_sha256(self) -> str:
        return hash_payload(self.to_payload())


def assess_ib5_candidate_inputs(
    inputs: Ib5CallerDeclaredInputs,
) -> Ib5CandidateReadiness:
    """Assess declaration shape without touching data, QC, or look registries."""

    if type(inputs) is not Ib5CallerDeclaredInputs:
        raise Ib5CandidateError("REFUSED: inputs are not exact declarations")
    inputs.__post_init__()
    IB5_CANDIDATE_POLICY.__post_init__()
    blockers = _declaration_blockers(inputs)
    return Ib5CandidateReadiness(
        inputs=inputs,
        blockers=blockers,
        caller_declarations_complete=not blockers,
    )
