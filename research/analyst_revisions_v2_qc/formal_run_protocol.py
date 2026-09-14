"""Pre-submission contract and one-use gate for the first ARV2 formal run.

This module is deliberately host-side and outcome-value-free.  It freezes the
complete set of identities and censuses that must exist before a QuantConnect
submission may be claimed, and it implements an exclusive-create spend
receipt.  It does not contain a QuantConnect client, inspect credentials, open
an input or outcome artifact, upload code or data, submit a job, or read a
result.

No checked-in mutable review pin exists.  After Claude reviews the complete
pre-backtest code snapshot and Codex counter-reviews that exact review, an
owner-controlled private external pin must bind the reviewed code projection,
dynamic input candidate, outcome/QC authority, and sole ledger directory.
Until that file exists the activation and spend boundary fails closed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from research.analyst_revisions_v2.preregistration import (
    InfrastructureLookLedgerBinding,
    PreregistrationError,
    load_infrastructure_look_ledger,
    require_infrastructure_look_ledger,
)


class FormalRunProtocolError(ValueError):
    """A formal-run input, review receipt, or one-use claim is invalid."""


SCHEMA = "arv2-formal-run-protocol-v1"
STATUS = "candidate_pending_independent_review_and_counterreview"
AUTHORITY = "pre_submission_structure_only_no_qc_or_outcome_action_authority"
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
OWNER_DECISION_ID = "arv2-owner-first-formal-primary-plus-2021-2025-20260911"
REVIEW_RECEIPT_SCHEMA = "arv2-formal-run-reviewed-authority-v2"
EXTERNAL_REVIEW_PIN_SCHEMA = "arv2-formal-run-external-review-pin-v2"
CLAIM_RECEIPT_SCHEMA = "arv2-formal-run-one-use-claim-v1"
CLAIM_FILENAME = "arv2-formal-run-one-use-claim.json"
SUBMISSION_PERMIT_SCHEMA = "arv2-formal-run-submission-permit-v1"
SUBMISSION_PERMIT_FILENAME = "arv2-formal-run-submission-started.json"
# The review receipt pin is deliberately *not* a mutable source-code constant.
# A receipt contains the Codex counter-review commit, so checking its digest
# into that same commit would be self-referential.  The pin is supplied later
# by an owner-controlled, mode-restricted external authority file and is
# retained on the loaded authority object.  Until that happens this module has
# no launch authority.
REVIEWED_AUTHORITY_ARTIFACT_SHA256: None = None

FORMAL_PRIMARY_FOLD_IDS = tuple(
    f"arv2-wf-test-{year}" for year in range(2020, 2026)
)
DESCRIPTIVE_SENSITIVITY_FOLD_IDS = tuple(
    f"arv2-wf-test-{year}" for year in range(2021, 2026)
)
SOURCE_VIEW_IDS = (
    "current_row_current_vintage_non_pristine_pit",
    "conservative_censored_current_vintage_non_pristine_pit",
)
HORIZONS = (1, 5, 20, 60)
PRIMARY_HORIZON = 20
H20_TEST_SESSION_CAPACITY = 1388
POWER_FEASIBLE_DISPOSITION = (
    "FEASIBLE_FIXED_DESIGN_pending_authenticated_receipt"
)
TERMINAL_POLICY_ID = "arv2-terminal-payoff-benchmark-splice-v1"
MAX_REVIEW_RECEIPT_BYTES = 256 * 1024

_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")
_CAPABILITY_NAMES = (
    "credential_access",
    "provider_access",
    "production_input_read",
    "real_outcome_access",
    "qc_account_access",
    "qc_project_create",
    "qc_object_store_write",
    "qc_upload",
    "qc_compile",
    "qc_launch",
    "result_access",
    "result_disposition",
    "deployment",
    "orders",
    "trading",
)
_EXTERNAL_BINDING_NAMES = (
    "claude_review_commit",
    "codex_counterreview_commit",
    "review_receipt_artifact_sha256",
    "owner_outcome_authority_receipt_id",
    "atomic_look_claim_receipt_id",
    "qc_project_id",
    "qc_compile_id",
    "qc_backtest_id",
    "result_receipt_id",
)


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise FormalRunProtocolError("formal-run value is not canonical JSON") from exc


def _require_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalRunProtocolError(f"{name} is not a safe identifier")
    return value


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalRunProtocolError(f"{name} is not a lowercase SHA-256")
    return value


def _require_commit(value: object, name: str) -> str:
    if type(value) is not str or _HEX_40.fullmatch(value) is None:
        raise FormalRunProtocolError(f"{name} is not a full lowercase commit")
    return value


def _require_count(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FormalRunProtocolError(f"{name} is not an exact integer census")
    return value


def _require_utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise FormalRunProtocolError(f"{name} is not a canonical UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FormalRunProtocolError(f"{name} is not a canonical UTC instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise FormalRunProtocolError(f"{name} is not UTC")
    if parsed.isoformat(timespec="microseconds").replace("+00:00", "Z") != value:
        raise FormalRunProtocolError(f"{name} is not microsecond-canonical UTC")
    return value


def _require_claim_directory_text(value: object) -> str:
    if type(value) is not str or not value or len(value) > 4096 or "\x00" in value:
        raise FormalRunProtocolError("claim directory is not exact absolute text")
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise FormalRunProtocolError("claim directory is not canonical absolute text")
    return value


def _load_reconciled_infrastructure_look_ledger() -> InfrastructureLookLedgerBinding:
    try:
        return load_infrastructure_look_ledger()
    except PreregistrationError as exc:
        raise FormalRunProtocolError(
            "infrastructure-look ledger reconciliation failed"
        ) from exc


def _require_reconciled_infrastructure_look_ledger(
    binding: InfrastructureLookLedgerBinding,
) -> InfrastructureLookLedgerBinding:
    try:
        return require_infrastructure_look_ledger(binding)
    except PreregistrationError as exc:
        raise FormalRunProtocolError(
            "infrastructure-look ledger reconciliation failed"
        ) from exc


def _infrastructure_look_ledger_fields(
    binding: InfrastructureLookLedgerBinding,
) -> dict[str, str]:
    binding = _require_reconciled_infrastructure_look_ledger(binding)
    return {
        "infrastructure_look_ledger_id": binding.ledger_id,
        "infrastructure_look_ledger_hash": binding.ledger_hash,
        "infrastructure_look_ledger_artifact_sha256": binding.artifact_sha256,
    }


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactBinding:
    artifact_id: str
    content_sha256: str
    artifact_sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        _require_id(self.artifact_id, "artifact_id")
        _require_sha256(self.content_sha256, "content_sha256")
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        _require_count(self.byte_count, "byte_count", minimum=1)

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def require_artifact_binding(value: ArtifactBinding) -> ArtifactBinding:
    if type(value) is not ArtifactBinding:
        raise FormalRunProtocolError("artifact binding type changed")
    try:
        value.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalRunProtocolError("artifact binding changed") from exc
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPairBinding:
    pair: ArtifactBinding
    capture_id: str
    capture_sha256: str
    current_source_included_count: int
    censored_source_included_count: int
    current_admitted_decision_count: int
    current_named_preoutcome_refusal_count: int
    censored_admitted_decision_count: int
    censored_named_preoutcome_refusal_count: int
    guidance_admitted_count: int
    pre_2013_admitted_count: int
    pristine_point_in_time: bool
    views_share_one_capture: bool

    def __post_init__(self) -> None:
        if type(self.pair) is not ArtifactBinding:
            raise FormalRunProtocolError("accepted-risk pair binding type changed")
        require_artifact_binding(self.pair)
        _require_id(self.capture_id, "capture_id")
        _require_sha256(self.capture_sha256, "capture_sha256")
        for name in (
            "current_source_included_count",
            "censored_source_included_count",
            "current_admitted_decision_count",
            "current_named_preoutcome_refusal_count",
            "censored_admitted_decision_count",
            "censored_named_preoutcome_refusal_count",
            "guidance_admitted_count",
            "pre_2013_admitted_count",
        ):
            _require_count(getattr(self, name), name)
        if self.current_source_included_count < 1:
            raise FormalRunProtocolError("current accepted-risk view is empty")
        if self.censored_source_included_count > self.current_source_included_count:
            raise FormalRunProtocolError("censored view exceeds its current-row parent")
        if (
            self.current_admitted_decision_count
            + self.current_named_preoutcome_refusal_count
            != self.current_source_included_count
            or self.censored_admitted_decision_count
            + self.censored_named_preoutcome_refusal_count
            != self.censored_source_included_count
        ):
            raise FormalRunProtocolError(
                "accepted-risk rows lack exhaustive preoutcome dispositions"
            )
        if self.guidance_admitted_count != 0 or self.pre_2013_admitted_count != 0:
            raise FormalRunProtocolError("guidance or pre-2013 rows were admitted")
        if self.pristine_point_in_time is not False:
            raise FormalRunProtocolError("accepted-risk input cannot claim pristine PIT")
        if self.views_share_one_capture is not True:
            raise FormalRunProtocolError("accepted-risk views do not share one capture")

    def to_record(self) -> dict[str, object]:
        return {
            "pair": self.pair.to_record(),
            "capture_id": self.capture_id,
            "capture_sha256": self.capture_sha256,
            "current_source_included_count": self.current_source_included_count,
            "censored_source_included_count": self.censored_source_included_count,
            "current_admitted_decision_count": self.current_admitted_decision_count,
            "current_named_preoutcome_refusal_count": (
                self.current_named_preoutcome_refusal_count
            ),
            "censored_admitted_decision_count": self.censored_admitted_decision_count,
            "censored_named_preoutcome_refusal_count": (
                self.censored_named_preoutcome_refusal_count
            ),
            "guidance_admitted_count": self.guidance_admitted_count,
            "pre_2013_admitted_count": self.pre_2013_admitted_count,
            "pristine_point_in_time": self.pristine_point_in_time,
            "views_share_one_capture": self.views_share_one_capture,
        }


def require_accepted_risk_pair_binding(
    value: AcceptedRiskPairBinding,
) -> AcceptedRiskPairBinding:
    if type(value) is not AcceptedRiskPairBinding:
        raise FormalRunProtocolError("accepted-risk pair binding type changed")
    try:
        require_artifact_binding(value.pair)
        value.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalRunProtocolError):
            raise
        raise FormalRunProtocolError("accepted-risk pair binding changed") from exc
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class PowerFloorBinding:
    numeric_receipt: ArtifactBinding
    stock_successor: ArtifactBinding
    disposition: str
    required_valid_dates: int
    observed_preoutcome_valid_dates: int
    required_connected_components: int
    observed_preoutcome_connected_components: int
    h20_test_session_capacity: int
    preoutcome_candidate_date_count: int
    valid_h20_test_session_count: int
    refused_h20_test_session_count: int
    missing_h20_test_session_count: int
    connected_component_instance_count: int

    def __post_init__(self) -> None:
        if type(self.numeric_receipt) is not ArtifactBinding or type(
            self.stock_successor
        ) is not ArtifactBinding:
            raise FormalRunProtocolError("power binding artifact type changed")
        require_artifact_binding(self.numeric_receipt)
        require_artifact_binding(self.stock_successor)
        if self.disposition != POWER_FEASIBLE_DISPOSITION:
            raise FormalRunProtocolError("numeric power receipt does not permit launch")
        for name in (
            "required_valid_dates",
            "observed_preoutcome_valid_dates",
            "required_connected_components",
            "observed_preoutcome_connected_components",
        ):
            _require_count(getattr(self, name), name, minimum=1)
        _require_count(
            self.h20_test_session_capacity,
            "h20_test_session_capacity",
            minimum=1,
        )
        for name in (
            "preoutcome_candidate_date_count",
            "valid_h20_test_session_count",
            "refused_h20_test_session_count",
            "missing_h20_test_session_count",
            "connected_component_instance_count",
        ):
            _require_count(getattr(self, name), name)
        if self.observed_preoutcome_valid_dates < self.required_valid_dates:
            raise FormalRunProtocolError("preoutcome valid-date floor is not met")
        if (
            self.observed_preoutcome_connected_components
            < self.required_connected_components
        ):
            raise FormalRunProtocolError(
                "preoutcome connected-component floor is not met"
            )
        if (
            self.h20_test_session_capacity != H20_TEST_SESSION_CAPACITY
            or self.preoutcome_candidate_date_count
            != (
                self.valid_h20_test_session_count
                + self.refused_h20_test_session_count
            )
            or self.h20_test_session_capacity
            != (
                self.preoutcome_candidate_date_count
                + self.missing_h20_test_session_count
            )
            or self.observed_preoutcome_valid_dates
            != self.valid_h20_test_session_count
            or self.observed_preoutcome_connected_components
            != self.connected_component_instance_count
        ):
            raise FormalRunProtocolError(
                "authenticated preoutcome H20 power census does not reconcile"
            )

    def to_record(self) -> dict[str, object]:
        return {
            "numeric_receipt": self.numeric_receipt.to_record(),
            "stock_successor": self.stock_successor.to_record(),
            "disposition": self.disposition,
            "required_valid_dates": self.required_valid_dates,
            "observed_preoutcome_valid_dates": self.observed_preoutcome_valid_dates,
            "required_connected_components": self.required_connected_components,
            "observed_preoutcome_connected_components": (
                self.observed_preoutcome_connected_components
            ),
            "h20_test_session_capacity": self.h20_test_session_capacity,
            "preoutcome_candidate_date_count": (
                self.preoutcome_candidate_date_count
            ),
            "valid_h20_test_session_count": self.valid_h20_test_session_count,
            "refused_h20_test_session_count": (
                self.refused_h20_test_session_count
            ),
            "missing_h20_test_session_count": (
                self.missing_h20_test_session_count
            ),
            "connected_component_instance_count": (
                self.connected_component_instance_count
            ),
        }


def require_power_floor_binding(value: PowerFloorBinding) -> PowerFloorBinding:
    if type(value) is not PowerFloorBinding:
        raise FormalRunProtocolError("power-floor binding type changed")
    try:
        require_artifact_binding(value.numeric_receipt)
        require_artifact_binding(value.stock_successor)
        value.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalRunProtocolError):
            raise
        raise FormalRunProtocolError("power-floor binding changed") from exc
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class TerminalCensusBinding:
    census: ArtifactBinding
    terminal_policy_id: str
    security_count: int
    lifecycle_coverage_count: int
    terminal_requirement_count: int
    terminal_payoff_count: int
    benchmark_splice_continuation_count: int
    named_terminal_refusal_count: int
    silently_omitted_count: int

    def __post_init__(self) -> None:
        if type(self.census) is not ArtifactBinding:
            raise FormalRunProtocolError("terminal census artifact type changed")
        require_artifact_binding(self.census)
        if self.terminal_policy_id != TERMINAL_POLICY_ID:
            raise FormalRunProtocolError("terminal-payoff policy changed")
        for name in (
            "security_count",
            "lifecycle_coverage_count",
            "terminal_requirement_count",
            "terminal_payoff_count",
            "benchmark_splice_continuation_count",
            "named_terminal_refusal_count",
            "silently_omitted_count",
        ):
            _require_count(getattr(self, name), name)
        if self.security_count < 1:
            raise FormalRunProtocolError("terminal census has no securities")
        if self.lifecycle_coverage_count != self.security_count:
            raise FormalRunProtocolError("security lifecycle coverage is not exhaustive")
        if (
            self.terminal_payoff_count
            + self.benchmark_splice_continuation_count
            + self.named_terminal_refusal_count
            != self.terminal_requirement_count
        ):
            raise FormalRunProtocolError(
                "terminal requirements lack payoff, benchmark-splice, or refusal dispositions"
            )
        if self.silently_omitted_count != 0:
            raise FormalRunProtocolError("terminal census silently omitted securities")

    @property
    def complete_payoffs(self) -> bool:
        return self.named_terminal_refusal_count == 0

    def to_record(self) -> dict[str, object]:
        return {
            "census": self.census.to_record(),
            "terminal_policy_id": self.terminal_policy_id,
            "security_count": self.security_count,
            "lifecycle_coverage_count": self.lifecycle_coverage_count,
            "terminal_requirement_count": self.terminal_requirement_count,
            "terminal_payoff_count": self.terminal_payoff_count,
            "benchmark_splice_continuation_count": (
                self.benchmark_splice_continuation_count
            ),
            "named_terminal_refusal_count": self.named_terminal_refusal_count,
            "silently_omitted_count": self.silently_omitted_count,
            "complete_payoffs": self.complete_payoffs,
        }


def require_terminal_census_binding(
    value: TerminalCensusBinding,
) -> TerminalCensusBinding:
    if type(value) is not TerminalCensusBinding:
        raise FormalRunProtocolError("terminal census binding type changed")
    try:
        require_artifact_binding(value.census)
        value.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalRunProtocolError):
            raise
        raise FormalRunProtocolError("terminal census binding changed") from exc
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalRunCandidate:
    candidate_id: str
    candidate_sha256: str
    code_projection: ArtifactBinding
    production_input_package: ArtifactBinding
    current_view_partition_set: ArtifactBinding
    censored_view_partition_set: ArtifactBinding
    accepted_risk: AcceptedRiskPairBinding
    power_floor: PowerFloorBinding
    terminal_census: TerminalCensusBinding
    formal_primary_fold_ids: tuple[str, ...]
    descriptive_sensitivity_fold_ids: tuple[str, ...]
    source_view_ids: tuple[str, ...]
    horizons: tuple[int, ...]
    primary_horizon: int
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def launch_available(self) -> bool:
        return False

    @property
    def result_access_available(self) -> bool:
        return False


def _candidate_seed(
    *,
    code_projection: ArtifactBinding,
    production_input_package: ArtifactBinding,
    current_view_partition_set: ArtifactBinding,
    censored_view_partition_set: ArtifactBinding,
    accepted_risk: AcceptedRiskPairBinding,
    power_floor: PowerFloorBinding,
    terminal_census: TerminalCensusBinding,
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "candidate_id": None,
        "candidate_sha256": None,
        "evaluation_id": EVALUATION_ID,
        "owner_decision_id": OWNER_DECISION_ID,
        "code_projection": code_projection.to_record(),
        "production_input_package": production_input_package.to_record(),
        "source_view_partition_sets": {
            SOURCE_VIEW_IDS[0]: current_view_partition_set.to_record(),
            SOURCE_VIEW_IDS[1]: censored_view_partition_set.to_record(),
        },
        "accepted_risk": accepted_risk.to_record(),
        "power_floor": power_floor.to_record(),
        "terminal_census": terminal_census.to_record(),
        "execution_geometry": {
            "single_execution": True,
            "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
            "descriptive_sensitivity_fold_ids": list(
                DESCRIPTIVE_SENSITIVITY_FOLD_IDS
            ),
            "descriptive_sensitivity_cannot_replace_or_rescue_primary": True,
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "horizons": list(HORIZONS),
            "primary_horizon": PRIMARY_HORIZON,
            "maximum_backtest_submissions": 1,
            "ambiguous_submission_consumes_the_look": True,
            "retry_after_ambiguity": False,
        },
        "non_pristine_pit_disclosure": {
            "current_row_overwrite_risk_owner_accepted": True,
            "both_source_views_non_pristine_pit": True,
            "same_capture_required": True,
            "censored_view_never_imputes_an_earlier_value": True,
        },
        "external_bindings": {name: None for name in _EXTERNAL_BINDING_NAMES},
        "capabilities": {name: False for name in _CAPABILITY_NAMES},
    }


def _identify(document: dict[str, object]) -> dict[str, object]:
    seed = dict(document)
    seed["candidate_id"] = None
    seed["candidate_sha256"] = None
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    seed["candidate_sha256"] = digest
    seed["candidate_id"] = f"arv2-formal-run-candidate-{digest[:24]}"
    return seed


def build_formal_run_candidate(
    *,
    code_projection: ArtifactBinding,
    production_input_package: ArtifactBinding,
    current_view_partition_set: ArtifactBinding,
    censored_view_partition_set: ArtifactBinding,
    accepted_risk: AcceptedRiskPairBinding,
    power_floor: PowerFloorBinding,
    terminal_census: TerminalCensusBinding,
) -> FormalRunCandidate:
    """Build a reviewable, non-authoritative pre-submission candidate."""

    for value, name, expected in (
        (code_projection, "code projection", ArtifactBinding),
        (production_input_package, "production input package", ArtifactBinding),
        (current_view_partition_set, "current partition set", ArtifactBinding),
        (censored_view_partition_set, "censored partition set", ArtifactBinding),
        (accepted_risk, "accepted-risk binding", AcceptedRiskPairBinding),
        (power_floor, "power-floor binding", PowerFloorBinding),
        (terminal_census, "terminal census", TerminalCensusBinding),
    ):
        if type(value) is not expected:
            raise FormalRunProtocolError(f"{name} type changed")
    require_artifact_binding(code_projection)
    require_artifact_binding(production_input_package)
    require_artifact_binding(current_view_partition_set)
    require_artifact_binding(censored_view_partition_set)
    require_accepted_risk_pair_binding(accepted_risk)
    require_power_floor_binding(power_floor)
    require_terminal_census_binding(terminal_census)
    if current_view_partition_set == censored_view_partition_set:
        raise FormalRunProtocolError("current and censored partition sets collapsed")
    document = _identify(
        _candidate_seed(
            code_projection=code_projection,
            production_input_package=production_input_package,
            current_view_partition_set=current_view_partition_set,
            censored_view_partition_set=censored_view_partition_set,
            accepted_risk=accepted_risk,
            power_floor=power_floor,
            terminal_census=terminal_census,
        )
    )
    payload = _canonical_bytes(document)
    return FormalRunCandidate(
        candidate_id=str(document["candidate_id"]),
        candidate_sha256=str(document["candidate_sha256"]),
        code_projection=code_projection,
        production_input_package=production_input_package,
        current_view_partition_set=current_view_partition_set,
        censored_view_partition_set=censored_view_partition_set,
        accepted_risk=accepted_risk,
        power_floor=power_floor,
        terminal_census=terminal_census,
        formal_primary_fold_ids=FORMAL_PRIMARY_FOLD_IDS,
        descriptive_sensitivity_fold_ids=DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
        source_view_ids=SOURCE_VIEW_IDS,
        horizons=HORIZONS,
        primary_horizon=PRIMARY_HORIZON,
        external_bindings=tuple((name, None) for name in _EXTERNAL_BINDING_NAMES),
        capabilities=tuple((name, False) for name in _CAPABILITY_NAMES),
        _canonical_document=payload,
    )


def require_formal_run_candidate(candidate: FormalRunCandidate) -> FormalRunCandidate:
    if type(candidate) is not FormalRunCandidate:
        raise FormalRunProtocolError("formal-run candidate type changed")
    if (
        type(candidate.formal_primary_fold_ids) is not tuple
        or candidate.formal_primary_fold_ids != FORMAL_PRIMARY_FOLD_IDS
        or type(candidate.descriptive_sensitivity_fold_ids) is not tuple
        or candidate.descriptive_sensitivity_fold_ids
        != DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        or type(candidate.source_view_ids) is not tuple
        or candidate.source_view_ids != SOURCE_VIEW_IDS
        or type(candidate.horizons) is not tuple
        or candidate.horizons != HORIZONS
        or type(candidate.primary_horizon) is not int
        or candidate.primary_horizon != PRIMARY_HORIZON
        or type(candidate.external_bindings) is not tuple
        or candidate.external_bindings
        != tuple((name, None) for name in _EXTERNAL_BINDING_NAMES)
        or type(candidate.capabilities) is not tuple
        or candidate.capabilities
        != tuple((name, False) for name in _CAPABILITY_NAMES)
        or type(candidate._canonical_document) is not bytes
    ):
        raise FormalRunProtocolError("formal-run candidate static surface changed")
    require_artifact_binding(candidate.code_projection)
    require_artifact_binding(candidate.production_input_package)
    require_artifact_binding(candidate.current_view_partition_set)
    require_artifact_binding(candidate.censored_view_partition_set)
    require_accepted_risk_pair_binding(candidate.accepted_risk)
    require_power_floor_binding(candidate.power_floor)
    require_terminal_census_binding(candidate.terminal_census)
    try:
        rebuilt = build_formal_run_candidate(
            code_projection=candidate.code_projection,
            production_input_package=candidate.production_input_package,
            current_view_partition_set=candidate.current_view_partition_set,
            censored_view_partition_set=candidate.censored_view_partition_set,
            accepted_risk=candidate.accepted_risk,
            power_floor=candidate.power_floor,
            terminal_census=candidate.terminal_census,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalRunProtocolError("formal-run candidate changed") from exc
    fields = tuple(field.name for field in dataclasses.fields(FormalRunCandidate))
    if any(getattr(candidate, name) != getattr(rebuilt, name) for name in fields):
        raise FormalRunProtocolError("formal-run candidate changed")
    if candidate.launch_available is not False or candidate.result_access_available is not False:
        raise FormalRunProtocolError("unreviewed candidate acquired action authority")
    return candidate


def render_formal_run_candidate_bytes(candidate: FormalRunCandidate) -> bytes:
    require_formal_run_candidate(candidate)
    return bytes(candidate._canonical_document)


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedFormalRunAuthority:
    authority_id: str
    authority_sha256: str
    candidate_id: str
    candidate_sha256: str
    claude_review_commit: str
    codex_counterreview_commit: str
    owner_decision_id: str
    owner_outcome_authority_receipt_id: str
    review_receipt_artifact_sha256: str
    claim_directory: Path
    maximum_submissions: int
    result_read_requires_separate_terminal_gate: bool
    _receipt_bytes: bytes = dataclasses.field(repr=False)
    _external_pin: "ExternalReviewPin" = dataclasses.field(repr=False)
    _infrastructure_look_ledger: InfrastructureLookLedgerBinding | None = (
        dataclasses.field(default=None, repr=False)
    )


@dataclasses.dataclass(frozen=True, slots=True)
class ExternalReviewPin:
    """Owner-controlled trust root created only after review/counter-review.

    The file carrying this record is external to the reviewed source snapshot,
    which avoids the impossible requirement for a commit to contain a digest
    that itself names that commit.  It binds the reviewed code projection,
    exact dynamic candidate receipt, one canonical machine ledger directory,
    and the separately granted outcome/QC authority.
    """

    pin_id: str
    pin_sha256: str
    candidate_id: str
    candidate_sha256: str
    reviewed_code_projection_artifact_sha256: str
    review_receipt_artifact_sha256: str
    claude_review_commit: str
    codex_counterreview_commit: str
    owner_outcome_authority_receipt_id: str
    claim_directory: Path
    _pin_bytes: bytes = dataclasses.field(repr=False)
    _pin_path: Path = dataclasses.field(repr=False)
    _infrastructure_look_ledger: InfrastructureLookLedgerBinding | None = (
        dataclasses.field(default=None, repr=False)
    )


_REVIEW_FIELDS = frozenset(
    {
        "schema",
        "status",
        "authority_id",
        "authority_sha256",
        "candidate_id",
        "candidate_sha256",
        "candidate_artifact_sha256",
        "review_scope",
        "reviewed_code_projection_artifact_sha256",
        "claude_review_commit",
        "claude_review_evidence_sha256",
        "codex_counterreview_commit",
        "codex_counterreview_evidence_sha256",
        "owner_decision_id",
        "owner_outcome_authority_receipt_id",
        "infrastructure_look_ledger_id",
        "infrastructure_look_ledger_hash",
        "infrastructure_look_ledger_artifact_sha256",
        "claim_directory",
        "maximum_submissions",
        "ambiguous_submission_consumes_look",
        "retry_after_ambiguity",
        "result_read_requires_separate_terminal_gate",
        "deployment_orders_trading_authorized",
    }
)

_EXTERNAL_PIN_FIELDS = frozenset(
    {
        "schema",
        "status",
        "pin_id",
        "pin_sha256",
        "candidate_id",
        "candidate_sha256",
        "reviewed_code_projection_artifact_sha256",
        "review_receipt_artifact_sha256",
        "claude_review_commit",
        "codex_counterreview_commit",
        "owner_outcome_authority_receipt_id",
        "infrastructure_look_ledger_id",
        "infrastructure_look_ledger_hash",
        "infrastructure_look_ledger_artifact_sha256",
        "claim_directory",
        "maximum_submissions",
        "ambiguous_submission_consumes_look",
        "retry_after_ambiguity",
        "result_read_authorized",
        "deployment_orders_trading_authorized",
    }
)


def _review_seed(
    candidate: FormalRunCandidate,
    *,
    infrastructure_look_ledger: InfrastructureLookLedgerBinding,
    claude_review_commit: str,
    claude_review_evidence_sha256: str,
    codex_counterreview_commit: str,
    codex_counterreview_evidence_sha256: str,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> dict[str, object]:
    require_formal_run_candidate(candidate)
    ledger_fields = _infrastructure_look_ledger_fields(
        infrastructure_look_ledger
    )
    _require_commit(claude_review_commit, "Claude review commit")
    _require_sha256(claude_review_evidence_sha256, "Claude review evidence")
    _require_commit(codex_counterreview_commit, "Codex counterreview commit")
    _require_sha256(codex_counterreview_evidence_sha256, "Codex counterreview evidence")
    if claude_review_commit == codex_counterreview_commit:
        raise FormalRunProtocolError("Claude review and Codex counterreview commits must differ")
    _require_id(
        owner_outcome_authority_receipt_id,
        "owner outcome/QC authority receipt",
    )
    _require_claim_directory_text(claim_directory)
    raw: dict[str, object] = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "status": "independently_reviewed_and_counterreviewed",
        "authority_id": None,
        "authority_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "candidate_artifact_sha256": hashlib.sha256(
            render_formal_run_candidate_bytes(candidate)
        ).hexdigest(),
        "review_scope": (
            "code_projection_independently_reviewed_dynamic_input_candidate_"
            "machine_authenticated_not_human_reviewed"
        ),
        "reviewed_code_projection_artifact_sha256": (
            candidate.code_projection.artifact_sha256
        ),
        "claude_review_commit": claude_review_commit,
        "claude_review_evidence_sha256": claude_review_evidence_sha256,
        "codex_counterreview_commit": codex_counterreview_commit,
        "codex_counterreview_evidence_sha256": codex_counterreview_evidence_sha256,
        "owner_decision_id": OWNER_DECISION_ID,
        "owner_outcome_authority_receipt_id": owner_outcome_authority_receipt_id,
        **ledger_fields,
        "claim_directory": claim_directory,
        "maximum_submissions": 1,
        "ambiguous_submission_consumes_look": True,
        "retry_after_ambiguity": False,
        "result_read_requires_separate_terminal_gate": True,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["authority_sha256"] = digest
    raw["authority_id"] = f"arv2-formal-reviewed-authority-{digest[:24]}"
    return raw


def render_formal_review_receipt_candidate(
    candidate: FormalRunCandidate,
    *,
    claude_review_commit: str,
    claude_review_evidence_sha256: str,
    codex_counterreview_commit: str,
    codex_counterreview_evidence_sha256: str,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> bytes:
    """Render bytes for later pinning; rendering does not grant authority."""

    infrastructure_look_ledger = _load_reconciled_infrastructure_look_ledger()
    return _canonical_bytes(
        _review_seed(
            candidate,
            infrastructure_look_ledger=infrastructure_look_ledger,
            claude_review_commit=claude_review_commit,
            claude_review_evidence_sha256=claude_review_evidence_sha256,
            codex_counterreview_commit=codex_counterreview_commit,
            codex_counterreview_evidence_sha256=(
                codex_counterreview_evidence_sha256
            ),
            owner_outcome_authority_receipt_id=(
                owner_outcome_authority_receipt_id
            ),
            claim_directory=claim_directory,
        )
    )


def _external_pin_seed(
    *,
    candidate: FormalRunCandidate,
    infrastructure_look_ledger: InfrastructureLookLedgerBinding,
    review_receipt_artifact_sha256: str,
    claude_review_commit: str,
    codex_counterreview_commit: str,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> dict[str, object]:
    require_formal_run_candidate(candidate)
    ledger_fields = _infrastructure_look_ledger_fields(
        infrastructure_look_ledger
    )
    _require_sha256(review_receipt_artifact_sha256, "review receipt artifact")
    _require_commit(claude_review_commit, "Claude review commit")
    _require_commit(codex_counterreview_commit, "Codex counterreview commit")
    if claude_review_commit == codex_counterreview_commit:
        raise FormalRunProtocolError("Claude review and Codex counterreview commits must differ")
    _require_id(owner_outcome_authority_receipt_id, "owner outcome/QC authority receipt")
    _require_claim_directory_text(claim_directory)
    raw: dict[str, object] = {
        "schema": EXTERNAL_REVIEW_PIN_SCHEMA,
        "status": "external_owner_controlled_review_and_outcome_authority_pin",
        "pin_id": None,
        "pin_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "reviewed_code_projection_artifact_sha256": (
            candidate.code_projection.artifact_sha256
        ),
        "review_receipt_artifact_sha256": review_receipt_artifact_sha256,
        "claude_review_commit": claude_review_commit,
        "codex_counterreview_commit": codex_counterreview_commit,
        "owner_outcome_authority_receipt_id": owner_outcome_authority_receipt_id,
        **ledger_fields,
        "claim_directory": claim_directory,
        "maximum_submissions": 1,
        "ambiguous_submission_consumes_look": True,
        "retry_after_ambiguity": False,
        "result_read_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["pin_sha256"] = digest
    raw["pin_id"] = f"arv2-formal-external-pin-{digest[:24]}"
    return raw


def render_external_review_pin_candidate(
    *,
    candidate: FormalRunCandidate,
    review_receipt_bytes: bytes,
    claude_review_commit: str,
    claude_review_evidence_sha256: str,
    codex_counterreview_commit: str,
    codex_counterreview_evidence_sha256: str,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> bytes:
    """Render the external trust-root candidate after both reviews.

    The caller must persist these bytes to a private owner-controlled path.
    Rendering alone grants no authority.
    """

    if type(review_receipt_bytes) is not bytes:
        raise FormalRunProtocolError("review receipt must be exact bytes")
    infrastructure_look_ledger = _load_reconciled_infrastructure_look_ledger()
    expected_review = _canonical_bytes(
        _review_seed(
            candidate,
            infrastructure_look_ledger=infrastructure_look_ledger,
            claude_review_commit=claude_review_commit,
            claude_review_evidence_sha256=claude_review_evidence_sha256,
            codex_counterreview_commit=codex_counterreview_commit,
            codex_counterreview_evidence_sha256=(
                codex_counterreview_evidence_sha256
            ),
            owner_outcome_authority_receipt_id=(
                owner_outcome_authority_receipt_id
            ),
            claim_directory=claim_directory,
        )
    )
    if review_receipt_bytes != expected_review:
        raise FormalRunProtocolError("review receipt does not match the reviewed identities")
    return _canonical_bytes(
        _external_pin_seed(
            candidate=candidate,
            infrastructure_look_ledger=infrastructure_look_ledger,
            review_receipt_artifact_sha256=hashlib.sha256(
                review_receipt_bytes
            ).hexdigest(),
            claude_review_commit=claude_review_commit,
            codex_counterreview_commit=codex_counterreview_commit,
            owner_outcome_authority_receipt_id=owner_outcome_authority_receipt_id,
            claim_directory=claim_directory,
        )
    )


def _read_private_regular(path: Path, *, maximum_bytes: int, name: str) -> bytes:
    if type(path) is not type(Path()) or path.is_symlink():
        raise FormalRunProtocolError(f"{name} must be a nonsymlink Path")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FormalRunProtocolError(f"{name} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) & 0o077
            or before.st_size <= 0
            or before.st_size > maximum_bytes
        ):
            raise FormalRunProtocolError(f"{name} is not a bounded private regular file")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > maximum_bytes
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise FormalRunProtocolError(f"{name} changed while read")
    finally:
        os.close(descriptor)
    return payload


def load_external_review_pin(
    candidate: FormalRunCandidate,
    pin_path: Path,
) -> ExternalReviewPin:
    """Load the post-review owner trust root from a private regular file."""

    require_formal_run_candidate(candidate)
    infrastructure_look_ledger = _load_reconciled_infrastructure_look_ledger()
    payload = _read_private_regular(
        pin_path,
        maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
        name="external review pin",
    )
    try:
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=lambda pairs: _reject_duplicate_pairs(pairs),
            parse_float=lambda _value: _reject_float(),
            parse_constant=lambda _value: _reject_float(),
        )
    except FormalRunProtocolError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FormalRunProtocolError("external review pin is not strict JSON") from exc
    if type(raw) is not dict or frozenset(raw) != _EXTERNAL_PIN_FIELDS:
        raise FormalRunProtocolError("external review pin fields changed")
    if _canonical_bytes(raw) != payload:
        raise FormalRunProtocolError("external review pin is not canonical bytes")
    expected = _external_pin_seed(
        candidate=candidate,
        infrastructure_look_ledger=infrastructure_look_ledger,
        review_receipt_artifact_sha256=_require_sha256(
            raw["review_receipt_artifact_sha256"], "review receipt artifact"
        ),
        claude_review_commit=_require_commit(
            raw["claude_review_commit"], "Claude review commit"
        ),
        codex_counterreview_commit=_require_commit(
            raw["codex_counterreview_commit"], "Codex counterreview commit"
        ),
        owner_outcome_authority_receipt_id=_require_id(
            raw["owner_outcome_authority_receipt_id"],
            "owner outcome/QC authority receipt",
        ),
        claim_directory=_require_claim_directory_text(raw["claim_directory"]),
    )
    if raw != expected:
        raise FormalRunProtocolError("external review pin content changed")
    return ExternalReviewPin(
        pin_id=str(raw["pin_id"]),
        pin_sha256=str(raw["pin_sha256"]),
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        reviewed_code_projection_artifact_sha256=(
            candidate.code_projection.artifact_sha256
        ),
        review_receipt_artifact_sha256=str(
            raw["review_receipt_artifact_sha256"]
        ),
        claude_review_commit=str(raw["claude_review_commit"]),
        codex_counterreview_commit=str(raw["codex_counterreview_commit"]),
        owner_outcome_authority_receipt_id=str(
            raw["owner_outcome_authority_receipt_id"]
        ),
        claim_directory=Path(str(raw["claim_directory"])),
        _pin_bytes=payload,
        _pin_path=pin_path,
        _infrastructure_look_ledger=infrastructure_look_ledger,
    )


def _load_reviewed_authority_with_pin(
    candidate: FormalRunCandidate,
    receipt_bytes: bytes,
    external_pin: ExternalReviewPin,
) -> ReviewedFormalRunAuthority:
    require_formal_run_candidate(candidate)
    external_pin = require_external_review_pin(candidate, external_pin)
    infrastructure_look_ledger = external_pin._infrastructure_look_ledger
    if type(infrastructure_look_ledger) is not InfrastructureLookLedgerBinding:
        raise FormalRunProtocolError(
            "infrastructure-look ledger reconciliation failed"
        )
    _require_reconciled_infrastructure_look_ledger(
        infrastructure_look_ledger
    )
    if type(receipt_bytes) is not bytes or not receipt_bytes:
        raise FormalRunProtocolError("review receipt must be exact nonempty bytes")
    if len(receipt_bytes) > MAX_REVIEW_RECEIPT_BYTES:
        raise FormalRunProtocolError("review receipt exceeds its byte bound")
    if (
        hashlib.sha256(receipt_bytes).hexdigest()
        != external_pin.review_receipt_artifact_sha256
    ):
        raise FormalRunProtocolError("review receipt does not match its external pin")
    try:
        text = receipt_bytes.decode("utf-8")
        raw = json.loads(
            text,
            object_pairs_hook=lambda pairs: _reject_duplicate_pairs(pairs),
            parse_float=lambda _value: _reject_float(),
            parse_constant=lambda _value: _reject_float(),
        )
    except FormalRunProtocolError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FormalRunProtocolError("review receipt is not strict JSON") from exc
    if type(raw) is not dict or frozenset(raw) != _REVIEW_FIELDS:
        raise FormalRunProtocolError("review receipt fields changed")
    if _canonical_bytes(raw) != receipt_bytes:
        raise FormalRunProtocolError("review receipt is not canonical bytes")
    claude_commit = _require_commit(raw["claude_review_commit"], "Claude review commit")
    counter_commit = _require_commit(
        raw["codex_counterreview_commit"], "Codex counterreview commit"
    )
    expected = _review_seed(
        candidate,
        infrastructure_look_ledger=infrastructure_look_ledger,
        claude_review_commit=claude_commit,
        claude_review_evidence_sha256=_require_sha256(
            raw["claude_review_evidence_sha256"], "Claude review evidence"
        ),
        codex_counterreview_commit=counter_commit,
        codex_counterreview_evidence_sha256=_require_sha256(
            raw["codex_counterreview_evidence_sha256"],
            "Codex counterreview evidence",
        ),
        owner_outcome_authority_receipt_id=(
            external_pin.owner_outcome_authority_receipt_id
        ),
        claim_directory=str(external_pin.claim_directory),
    )
    if (
        raw != expected
        or claude_commit != external_pin.claude_review_commit
        or counter_commit != external_pin.codex_counterreview_commit
        or raw["reviewed_code_projection_artifact_sha256"]
        != external_pin.reviewed_code_projection_artifact_sha256
    ):
        raise FormalRunProtocolError("review receipt content changed")
    return ReviewedFormalRunAuthority(
        authority_id=str(raw["authority_id"]),
        authority_sha256=str(raw["authority_sha256"]),
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        claude_review_commit=claude_commit,
        codex_counterreview_commit=counter_commit,
        owner_decision_id=OWNER_DECISION_ID,
        owner_outcome_authority_receipt_id=(
            external_pin.owner_outcome_authority_receipt_id
        ),
        review_receipt_artifact_sha256=(
            external_pin.review_receipt_artifact_sha256
        ),
        claim_directory=external_pin.claim_directory,
        maximum_submissions=1,
        result_read_requires_separate_terminal_gate=True,
        _receipt_bytes=bytes(receipt_bytes),
        _external_pin=external_pin,
        _infrastructure_look_ledger=infrastructure_look_ledger,
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FormalRunProtocolError("review receipt has duplicate keys")
        result[key] = value
    return result


def _reject_float() -> object:
    raise FormalRunProtocolError("review receipt cannot contain floats")


def load_reviewed_formal_run_authority(
    candidate: FormalRunCandidate,
    receipt_bytes: bytes,
    external_pin: ExternalReviewPin,
) -> ReviewedFormalRunAuthority:
    """Load an exact review receipt through its private external trust root."""

    return _load_reviewed_authority_with_pin(candidate, receipt_bytes, external_pin)


def require_external_review_pin(
    candidate: FormalRunCandidate,
    external_pin: ExternalReviewPin,
) -> ExternalReviewPin:
    """Re-read and compare the external trust root on every authority use."""

    require_formal_run_candidate(candidate)
    if type(external_pin) is not ExternalReviewPin:
        raise FormalRunProtocolError("external review pin type changed")
    infrastructure_look_ledger = external_pin._infrastructure_look_ledger
    if type(infrastructure_look_ledger) is not InfrastructureLookLedgerBinding:
        raise FormalRunProtocolError(
            "infrastructure-look ledger reconciliation failed"
        )
    _require_reconciled_infrastructure_look_ledger(
        infrastructure_look_ledger
    )
    try:
        loaded = load_external_review_pin(candidate, external_pin._pin_path)
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalRunProtocolError):
            raise
        raise FormalRunProtocolError("external review pin changed") from exc
    if external_pin != loaded:
        raise FormalRunProtocolError("external review pin changed")
    return external_pin


def require_reviewed_formal_run_authority(
    candidate: FormalRunCandidate, authority: ReviewedFormalRunAuthority
) -> ReviewedFormalRunAuthority:
    require_formal_run_candidate(candidate)
    if type(authority) is not ReviewedFormalRunAuthority:
        raise FormalRunProtocolError("reviewed formal-run authority type changed")
    infrastructure_look_ledger = authority._infrastructure_look_ledger
    if type(infrastructure_look_ledger) is not InfrastructureLookLedgerBinding:
        raise FormalRunProtocolError(
            "infrastructure-look ledger reconciliation failed"
        )
    _require_reconciled_infrastructure_look_ledger(
        infrastructure_look_ledger
    )
    if (
        type(authority.maximum_submissions) is not int
        or authority.maximum_submissions != 1
        or authority.result_read_requires_separate_terminal_gate is not True
        or type(authority.claim_directory) is not type(Path())
    ):
        raise FormalRunProtocolError("reviewed formal-run authority changed")
    loaded = load_reviewed_formal_run_authority(
        candidate,
        authority._receipt_bytes,
        authority._external_pin,
    )
    if authority != loaded:
        raise FormalRunProtocolError("reviewed formal-run authority changed")
    return authority


@dataclasses.dataclass(frozen=True, slots=True)
class FormalLookClaim:
    claim_id: str
    claim_sha256: str
    authority_id: str
    candidate_id: str
    candidate_sha256: str
    claimed_at_utc: str
    maximum_submissions: int
    submission_count_reserved: int
    ambiguous_submission_consumes_look: bool
    retry_authorized: bool
    claim_path: Path
    _claim_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalSubmissionPermit:
    """Durable evidence that the sole network submission attempt has begun.

    Creation is exclusive and happens before the QC adapter may make its first
    request.  A crash, timeout, or ambiguous response leaves the marker in
    place and therefore consumes the look permanently.
    """

    permit_id: str
    permit_sha256: str
    claim_id: str
    claim_sha256: str
    authority_id: str
    candidate_id: str
    candidate_sha256: str
    submission_started_at_utc: str
    maximum_submissions: int
    submission_attempt_count: int
    ambiguous_submission_consumes_look: bool
    retry_authorized: bool
    permit_path: Path
    _permit_bytes: bytes = dataclasses.field(repr=False)


def _claim_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    *,
    claimed_at_utc: str,
) -> dict[str, object]:
    _require_utc(claimed_at_utc, "claimed_at_utc")
    raw: dict[str, object] = {
        "schema": CLAIM_RECEIPT_SCHEMA,
        "status": "spent_before_submission",
        "claim_id": None,
        "claim_sha256": None,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "evaluation_id": EVALUATION_ID,
        "owner_decision_id": OWNER_DECISION_ID,
        "claimed_at_utc": claimed_at_utc,
        "maximum_submissions": 1,
        "submission_count_reserved": 1,
        "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
        "descriptive_sensitivity_fold_ids": list(
            DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        ),
        "source_view_ids": list(SOURCE_VIEW_IDS),
        "ambiguous_submission_consumes_look": True,
        "retry_authorized": False,
        "result_read_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["claim_sha256"] = digest
    raw["claim_id"] = f"arv2-formal-look-claim-{digest[:24]}"
    return raw


def _require_private_directory(path: Path) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute():
        raise FormalRunProtocolError("claim directory must be a Path")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat(follow_symlinks=False).st_mode
    except OSError as exc:
        raise FormalRunProtocolError("claim directory is unavailable") from exc
    if not stat.S_ISDIR(mode) or path.is_symlink() or resolved != path:
        raise FormalRunProtocolError("claim directory is not a real directory")
    if stat.S_IMODE(mode) != 0o700:
        raise FormalRunProtocolError("claim directory must be private mode 0700")
    return resolved


def _exclusive_private_write(directory: Path, filename: str, payload: bytes) -> Path:
    """Create and fsync one private immutable ledger entry."""

    target = directory / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise FormalRunProtocolError(
            "formal look is already spent; retry is not authorized"
        ) from exc
    except OSError as exc:
        raise FormalRunProtocolError("formal ledger entry could not be created") from exc
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise FormalRunProtocolError("formal ledger write stalled")
            offset += written
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    else:
        os.close(descriptor)
    try:
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        stored = _read_private_regular(
            target,
            maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
            name="formal ledger entry",
        )
    except OSError as exc:
        raise FormalRunProtocolError(
            "formal ledger entry cannot be reauthenticated after creation"
        ) from exc
    if stored != payload:
        raise FormalRunProtocolError("formal ledger entry changed after creation")
    return target


def claim_formal_run_once(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claimed_at_utc: str,
) -> FormalLookClaim:
    """Spend the single formal look before any submitter can be invoked.

    Exclusive creation means an existing claim, including one left by an
    ambiguous or crashed submission, permanently refuses a retry.
    """

    require_reviewed_formal_run_authority(candidate, authority)
    directory = _require_private_directory(authority.claim_directory)
    raw = _claim_document(candidate, authority, claimed_at_utc=claimed_at_utc)
    payload = _canonical_bytes(raw)
    target = _exclusive_private_write(directory, CLAIM_FILENAME, payload)
    return FormalLookClaim(
        claim_id=str(raw["claim_id"]),
        claim_sha256=str(raw["claim_sha256"]),
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        claimed_at_utc=claimed_at_utc,
        maximum_submissions=1,
        submission_count_reserved=1,
        ambiguous_submission_consumes_look=True,
        retry_authorized=False,
        claim_path=target,
        _claim_bytes=payload,
    )


def require_formal_look_claim(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
) -> FormalLookClaim:
    require_reviewed_formal_run_authority(candidate, authority)
    if type(claim) is not FormalLookClaim:
        raise FormalRunProtocolError("formal look claim type changed")
    try:
        if claim.claim_path != authority.claim_directory / CLAIM_FILENAME:
            raise FormalRunProtocolError("formal look claim path changed")
        payload = _read_private_regular(
            claim.claim_path,
            maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
            name="formal look claim",
        )
    except (AttributeError, OSError) as exc:
        raise FormalRunProtocolError("formal look claim is unavailable") from exc
    expected = _canonical_bytes(
        _claim_document(candidate, authority, claimed_at_utc=claim.claimed_at_utc)
    )
    if (
        payload != expected
        or payload != claim._claim_bytes
        or hashlib.sha256(payload).hexdigest()
        != hashlib.sha256(expected).hexdigest()
        or type(claim.claimed_at_utc) is not str
        or claim.claim_id != json.loads(expected)["claim_id"]
        or claim.claim_sha256 != json.loads(expected)["claim_sha256"]
        or claim.authority_id != authority.authority_id
        or claim.candidate_id != candidate.candidate_id
        or claim.candidate_sha256 != candidate.candidate_sha256
        or claim.maximum_submissions != 1
        or claim.submission_count_reserved != 1
        or claim.ambiguous_submission_consumes_look is not True
        or claim.retry_authorized is not False
    ):
        raise FormalRunProtocolError("formal look claim changed")
    return claim


def _submission_permit_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    *,
    submission_started_at_utc: str,
) -> dict[str, object]:
    _require_utc(submission_started_at_utc, "submission_started_at_utc")
    raw: dict[str, object] = {
        "schema": SUBMISSION_PERMIT_SCHEMA,
        "status": "submission_in_flight_look_consumed",
        "permit_id": None,
        "permit_sha256": None,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "evaluation_id": EVALUATION_ID,
        "owner_decision_id": OWNER_DECISION_ID,
        "submission_started_at_utc": submission_started_at_utc,
        "maximum_submissions": 1,
        "submission_attempt_count": 1,
        "ambiguous_submission_consumes_look": True,
        "retry_authorized": False,
        "result_read_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["permit_sha256"] = digest
    raw["permit_id"] = f"arv2-formal-submission-permit-{digest[:24]}"
    return raw


def begin_formal_submission_once(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    submission_started_at_utc: str,
) -> FormalSubmissionPermit:
    """Permanently consume the sole adapter invocation before network I/O."""

    require_formal_look_claim(candidate, authority, claim)
    directory = _require_private_directory(authority.claim_directory)
    raw = _submission_permit_document(
        candidate,
        authority,
        claim,
        submission_started_at_utc=submission_started_at_utc,
    )
    payload = _canonical_bytes(raw)
    target = _exclusive_private_write(
        directory,
        SUBMISSION_PERMIT_FILENAME,
        payload,
    )
    return FormalSubmissionPermit(
        permit_id=str(raw["permit_id"]),
        permit_sha256=str(raw["permit_sha256"]),
        claim_id=claim.claim_id,
        claim_sha256=claim.claim_sha256,
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        submission_started_at_utc=submission_started_at_utc,
        maximum_submissions=1,
        submission_attempt_count=1,
        ambiguous_submission_consumes_look=True,
        retry_authorized=False,
        permit_path=target,
        _permit_bytes=payload,
    )


def require_formal_submission_permit(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
) -> FormalSubmissionPermit:
    require_formal_look_claim(candidate, authority, claim)
    if type(permit) is not FormalSubmissionPermit:
        raise FormalRunProtocolError("formal submission permit type changed")
    try:
        if permit.permit_path != authority.claim_directory / SUBMISSION_PERMIT_FILENAME:
            raise FormalRunProtocolError("formal submission permit path changed")
        payload = _read_private_regular(
            permit.permit_path,
            maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
            name="formal submission permit",
        )
        expected = _canonical_bytes(
            _submission_permit_document(
                candidate,
                authority,
                claim,
                submission_started_at_utc=permit.submission_started_at_utc,
            )
        )
        raw = json.loads(expected)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalRunProtocolError):
            raise
        raise FormalRunProtocolError("formal submission permit is unavailable") from exc
    if (
        payload != expected
        or payload != permit._permit_bytes
        or permit.permit_id != raw["permit_id"]
        or permit.permit_sha256 != raw["permit_sha256"]
        or permit.claim_id != claim.claim_id
        or permit.claim_sha256 != claim.claim_sha256
        or permit.authority_id != authority.authority_id
        or permit.candidate_id != candidate.candidate_id
        or permit.candidate_sha256 != candidate.candidate_sha256
        or type(permit.maximum_submissions) is not int
        or permit.maximum_submissions != 1
        or type(permit.submission_attempt_count) is not int
        or permit.submission_attempt_count != 1
        or permit.ambiguous_submission_consumes_look is not True
        or permit.retry_authorized is not False
    ):
        raise FormalRunProtocolError("formal submission permit changed")
    return permit


def formal_run_protocol_record() -> Mapping[str, object]:
    """Return immutable static policy metadata for review tooling."""

    return MappingProxyType(
        {
            "schema": SCHEMA,
            "status": STATUS,
            "authority": AUTHORITY,
            "evaluation_id": EVALUATION_ID,
            "owner_decision_id": OWNER_DECISION_ID,
            "formal_primary_fold_ids": FORMAL_PRIMARY_FOLD_IDS,
            "descriptive_sensitivity_fold_ids": DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
            "source_view_ids": SOURCE_VIEW_IDS,
            "horizons": HORIZONS,
            "primary_horizon": PRIMARY_HORIZON,
            "reviewed_authority_artifact_sha256": (
                REVIEWED_AUTHORITY_ARTIFACT_SHA256
            ),
            "review_pin_is_external_owner_controlled": True,
            "infrastructure_look_ledger_bound_in_review_authority": True,
            "infrastructure_look_ledger_reauthenticated_before_claim": True,
            "submission_permit_filename": SUBMISSION_PERMIT_FILENAME,
            "maximum_submissions": 1,
            "ambiguous_submission_consumes_look": True,
            "retry_after_ambiguity": False,
            "result_read_requires_separate_terminal_gate": True,
            "deployment_orders_trading_authorized": False,
        }
    )


__all__ = [
    "AUTHORITY",
    "AcceptedRiskPairBinding",
    "ArtifactBinding",
    "CLAIM_FILENAME",
    "EXTERNAL_REVIEW_PIN_SCHEMA",
    "DESCRIPTIVE_SENSITIVITY_FOLD_IDS",
    "EVALUATION_ID",
    "FORMAL_PRIMARY_FOLD_IDS",
    "FormalLookClaim",
    "FormalRunCandidate",
    "FormalRunProtocolError",
    "FormalSubmissionPermit",
    "HORIZONS",
    "OWNER_DECISION_ID",
    "POWER_FEASIBLE_DISPOSITION",
    "PRIMARY_HORIZON",
    "PowerFloorBinding",
    "REVIEWED_AUTHORITY_ARTIFACT_SHA256",
    "SUBMISSION_PERMIT_FILENAME",
    "ReviewedFormalRunAuthority",
    "SCHEMA",
    "SOURCE_VIEW_IDS",
    "STATUS",
    "TERMINAL_POLICY_ID",
    "TerminalCensusBinding",
    "build_formal_run_candidate",
    "begin_formal_submission_once",
    "claim_formal_run_once",
    "formal_run_protocol_record",
    "load_reviewed_formal_run_authority",
    "load_external_review_pin",
    "render_external_review_pin_candidate",
    "render_formal_review_receipt_candidate",
    "render_formal_run_candidate_bytes",
    "require_formal_look_claim",
    "require_formal_run_candidate",
    "require_formal_submission_permit",
    "require_external_review_pin",
    "require_reviewed_formal_run_authority",
]
