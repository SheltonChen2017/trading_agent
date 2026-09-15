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
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
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
OWNER_WAIVER_RECEIPT_SCHEMA = "arv2-formal-run-owner-review-waiver-v1"
OWNER_WAIVER_EXTERNAL_PIN_SCHEMA = (
    "arv2-formal-run-owner-review-waiver-external-pin-v1"
)
OWNER_REVIEW_WAIVER_ID = "arv2-owner-review-waiver-section-72-v1"
OWNER_REVIEW_WAIVER_SCOPE = "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
OWNER_REVIEW_WAIVER_BASIS = "OWNER_EXPLICIT_REVIEW_WAIVER"
OWNER_REVIEW_WAIVER_DISPOSITION = "NOT_PERFORMED_OWNER_WAIVED"
INDEPENDENT_REVIEW_BASIS = "INDEPENDENT_CLAUDE_REVIEW_AND_CODEX_COUNTERREVIEW"
INDEPENDENT_REVIEW_DISPOSITION = "GO_INDEPENDENTLY_REVIEWED_AND_COUNTERREVIEWED"
CLAIM_RECEIPT_SCHEMA = "arv2-formal-run-one-use-claim-v1"
CLAIM_FILENAME = "arv2-formal-run-one-use-claim.json"
SUBMISSION_PERMIT_SCHEMA = "arv2-formal-run-submission-permit-v1"
SUBMISSION_PERMIT_FILENAME = "arv2-formal-run-submission-started.json"
RETRY_ATTEMPT_CLAIM_SCHEMA = "arv2-formal-run-retry-attempt-claim-v1"
RETRY_ATTEMPT_FAILURE_SCHEMA = (
    "arv2-formal-run-definite-pre-submission-failure-v1"
)
RETRY_ATTEMPT_PERMIT_SCHEMA = "arv2-formal-run-retry-attempt-permit-v1"
RETRY_ATTEMPT_TERMINAL_FAILURE_SCHEMA = (
    "arv2-formal-run-authenticated-terminal-failure-v1"
)
RETRY_ATTEMPT_SUCCESS_SCHEMA = "arv2-formal-run-successful-completion-v1"
RETRY_POLICY_ID = "arv2-formal-run-owner-standing-retry-policy-v1"
_RETRY_ATTEMPT_CLAIM_TEMPLATE = "arv2-formal-attempt-{ordinal:06d}-claim.json"
_RETRY_ATTEMPT_FAILURE_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-definite-pre-submission-failure.json"
)
_RETRY_ATTEMPT_PERMIT_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-outcome-consumed.json"
)
_RETRY_ATTEMPT_SUCCESS_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-successful-completion.json"
)
_RETRY_ATTEMPT_TERMINAL_FAILURE_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-authenticated-terminal-failure.json"
)
_RETRY_ATTEMPT_COMPILED_CONTROL_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-qc-compiled.json"
)
_RETRY_ATTEMPT_LAUNCH_CONTROL_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-qc-launch.json"
)
_RETRY_ATTEMPT_TERMINAL_CONTROL_TEMPLATE = (
    "arv2-formal-attempt-{ordinal:06d}-qc-terminal.json"
)
_RETRY_ATTEMPT_LOCK_TEMPLATE = "arv2-formal-attempt-{ordinal:06d}.lock"
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


def formal_owner_review_waiver_record() -> dict[str, object]:
    """Return the exact bounded review exception authorized by the owner.

    The exception ends when the statistics-free status path authenticates the
    first exact ``Completed.`` receipt.  ``Runtime Error`` and an unobserved or
    ambiguous remote state do not end it.  It never represents an independent
    review and cannot authorize the separately gated result read or trading.
    """

    return {
        "review_disposition": OWNER_REVIEW_WAIVER_DISPOSITION,
        "independent_review_complete": False,
        "authorization_basis": OWNER_REVIEW_WAIVER_BASIS,
        "owner_review_waiver_id": OWNER_REVIEW_WAIVER_ID,
        "owner_review_waiver_scope": OWNER_REVIEW_WAIVER_SCOPE,
        "waiver_ends_after_first_technically_completed_formal_backtest": True,
        "post_first_formal_backtest_independent_review_required": True,
    }


def formal_independent_review_record() -> dict[str, object]:
    """Return the ordinary completed Claude/Codex review state."""

    return {
        "review_disposition": INDEPENDENT_REVIEW_DISPOSITION,
        "independent_review_complete": True,
        "authorization_basis": INDEPENDENT_REVIEW_BASIS,
        "owner_review_waiver_id": None,
        "owner_review_waiver_scope": None,
        "waiver_ends_after_first_technically_completed_formal_backtest": False,
        "post_first_formal_backtest_independent_review_required": False,
    }


def formal_retry_policy_record() -> dict[str, object]:
    """Return the narrow, non-looping standing retry policy."""

    return {
        "retry_policy_id": RETRY_POLICY_ID,
        "automatic_retry_loop_authorized": False,
        "fresh_one_use_attempt_required": True,
        "definite_pre_backtests_create_failure_spends_outcome_look": False,
        "backtests_create_attempt_or_external_ambiguity_consumes_attempt": True,
        "consumed_attempt_reuse_or_deletion_authorized": False,
        "identical_frozen_lineage_required": True,
        "attempt_project_name_formula": (
            "{base_project_name}_A{attempt_ordinal:06d}_{claim_sha256}"
        ),
        "fresh_private_project_per_attempt_required": True,
        "preexisting_attempt_project_reuse_authorized": False,
        "attempt_project_deletion_authorized": False,
        "result_driven_changes_authorized": False,
        "fresh_retry_requires_authenticated_terminal_failure": True,
        "queued_running_or_unknown_authorizes_fresh_retry": False,
        "transport_ambiguity_authorizes_fresh_retry": False,
        "waiver_ending_qc_terminal_status": "Completed.",
        "waiver_ends_on_authenticated_terminal_receipt_only": True,
        "unobserved_or_ambiguous_remote_completion_cannot_end_waiver": True,
        "runtime_error_ends_owner_review_waiver": False,
    }


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
    claude_review_commit: str | None
    codex_counterreview_commit: str | None
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
    review_disposition: str = INDEPENDENT_REVIEW_DISPOSITION
    independent_review_complete: bool = True
    authorization_basis: str = INDEPENDENT_REVIEW_BASIS
    owner_review_waiver_id: str | None = None
    owner_review_waiver_scope: str | None = None
    waiver_ends_after_first_technically_completed_formal_backtest: bool = False
    post_first_formal_backtest_independent_review_required: bool = False


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
    review_disposition: str
    independent_review_complete: bool
    authorization_basis: str
    owner_review_waiver_id: str | None
    owner_review_waiver_scope: str | None
    waiver_ends_after_first_technically_completed_formal_backtest: bool
    post_first_formal_backtest_independent_review_required: bool
    claude_review_commit: str | None
    codex_counterreview_commit: str | None
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

_OWNER_WAIVER_REVIEW_FIELDS = frozenset(
    {
        "schema",
        "status",
        "authority_id",
        "authority_sha256",
        "candidate_id",
        "candidate_sha256",
        "candidate_artifact_sha256",
        "review_scope",
        "review_disposition",
        "independent_review_complete",
        "authorization_basis",
        "owner_review_waiver_id",
        "owner_review_waiver_scope",
        "waiver_ends_after_first_technically_completed_formal_backtest",
        "post_first_formal_backtest_independent_review_required",
        "reviewed_code_projection_artifact_sha256",
        "production_input_package_artifact_sha256",
        "current_view_partition_set_artifact_sha256",
        "censored_view_partition_set_artifact_sha256",
        "owner_decision_id",
        "owner_outcome_authority_receipt_id",
        "infrastructure_look_ledger_id",
        "infrastructure_look_ledger_hash",
        "infrastructure_look_ledger_artifact_sha256",
        "claim_directory",
        "maximum_backtest_submissions_per_attempt",
        "retry_policy",
        "result_read_requires_separate_terminal_gate",
        "deployment_orders_trading_authorized",
    }
)

_OWNER_WAIVER_EXTERNAL_PIN_FIELDS = frozenset(
    {
        "schema",
        "status",
        "pin_id",
        "pin_sha256",
        "candidate_id",
        "candidate_sha256",
        "reviewed_code_projection_artifact_sha256",
        "production_input_package_artifact_sha256",
        "current_view_partition_set_artifact_sha256",
        "censored_view_partition_set_artifact_sha256",
        "review_receipt_artifact_sha256",
        "review_disposition",
        "independent_review_complete",
        "authorization_basis",
        "owner_review_waiver_id",
        "owner_review_waiver_scope",
        "waiver_ends_after_first_technically_completed_formal_backtest",
        "post_first_formal_backtest_independent_review_required",
        "owner_outcome_authority_receipt_id",
        "infrastructure_look_ledger_id",
        "infrastructure_look_ledger_hash",
        "infrastructure_look_ledger_artifact_sha256",
        "claim_directory",
        "maximum_backtest_submissions_per_attempt",
        "retry_policy",
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


def _owner_waiver_review_seed(
    candidate: FormalRunCandidate,
    *,
    infrastructure_look_ledger: InfrastructureLookLedgerBinding,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> dict[str, object]:
    """Build the exact, truthful section-72 formal-run waiver receipt."""

    require_formal_run_candidate(candidate)
    _require_id(
        owner_outcome_authority_receipt_id,
        "owner outcome/QC authority receipt",
    )
    _require_claim_directory_text(claim_directory)
    raw: dict[str, object] = {
        "schema": OWNER_WAIVER_RECEIPT_SCHEMA,
        "status": "owner_review_waiver_first_formal_backtest_only",
        "authority_id": None,
        "authority_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "candidate_artifact_sha256": hashlib.sha256(
            render_formal_run_candidate_bytes(candidate)
        ).hexdigest(),
        "review_scope": (
            "section_72_through_first_technically_completed_formal_backtest_"
            "owner_waived_post_run_independent_review_required"
        ),
        **formal_owner_review_waiver_record(),
        "reviewed_code_projection_artifact_sha256": (
            candidate.code_projection.artifact_sha256
        ),
        "production_input_package_artifact_sha256": (
            candidate.production_input_package.artifact_sha256
        ),
        "current_view_partition_set_artifact_sha256": (
            candidate.current_view_partition_set.artifact_sha256
        ),
        "censored_view_partition_set_artifact_sha256": (
            candidate.censored_view_partition_set.artifact_sha256
        ),
        "owner_decision_id": OWNER_DECISION_ID,
        "owner_outcome_authority_receipt_id": (
            owner_outcome_authority_receipt_id
        ),
        **_infrastructure_look_ledger_fields(infrastructure_look_ledger),
        "claim_directory": claim_directory,
        "maximum_backtest_submissions_per_attempt": 1,
        "retry_policy": formal_retry_policy_record(),
        "result_read_requires_separate_terminal_gate": True,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["authority_sha256"] = digest
    raw["authority_id"] = f"arv2-formal-owner-waiver-authority-{digest[:24]}"
    return raw


def render_formal_owner_review_waiver_receipt_candidate(
    candidate: FormalRunCandidate,
    *,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> bytes:
    """Render the bounded waiver receipt without inventing review commits."""

    return _canonical_bytes(
        _owner_waiver_review_seed(
            candidate,
            infrastructure_look_ledger=(
                _load_reconciled_infrastructure_look_ledger()
            ),
            owner_outcome_authority_receipt_id=(
                owner_outcome_authority_receipt_id
            ),
            claim_directory=claim_directory,
        )
    )


def _owner_waiver_external_pin_seed(
    *,
    candidate: FormalRunCandidate,
    infrastructure_look_ledger: InfrastructureLookLedgerBinding,
    review_receipt_artifact_sha256: str,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> dict[str, object]:
    require_formal_run_candidate(candidate)
    _require_sha256(review_receipt_artifact_sha256, "review receipt artifact")
    _require_id(
        owner_outcome_authority_receipt_id,
        "owner outcome/QC authority receipt",
    )
    _require_claim_directory_text(claim_directory)
    raw: dict[str, object] = {
        "schema": OWNER_WAIVER_EXTERNAL_PIN_SCHEMA,
        "status": "external_owner_controlled_review_waiver_and_outcome_authority_pin",
        "pin_id": None,
        "pin_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "reviewed_code_projection_artifact_sha256": (
            candidate.code_projection.artifact_sha256
        ),
        "production_input_package_artifact_sha256": (
            candidate.production_input_package.artifact_sha256
        ),
        "current_view_partition_set_artifact_sha256": (
            candidate.current_view_partition_set.artifact_sha256
        ),
        "censored_view_partition_set_artifact_sha256": (
            candidate.censored_view_partition_set.artifact_sha256
        ),
        "review_receipt_artifact_sha256": review_receipt_artifact_sha256,
        **formal_owner_review_waiver_record(),
        "owner_outcome_authority_receipt_id": (
            owner_outcome_authority_receipt_id
        ),
        **_infrastructure_look_ledger_fields(infrastructure_look_ledger),
        "claim_directory": claim_directory,
        "maximum_backtest_submissions_per_attempt": 1,
        "retry_policy": formal_retry_policy_record(),
        "result_read_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["pin_sha256"] = digest
    raw["pin_id"] = f"arv2-formal-owner-waiver-pin-{digest[:24]}"
    return raw


def render_owner_review_waiver_external_pin_candidate(
    *,
    candidate: FormalRunCandidate,
    review_receipt_bytes: bytes,
    owner_outcome_authority_receipt_id: str,
    claim_directory: str,
) -> bytes:
    """Render the private trust root for the exact owner-waiver receipt."""

    if type(review_receipt_bytes) is not bytes:
        raise FormalRunProtocolError("review waiver receipt must be exact bytes")
    ledger = _load_reconciled_infrastructure_look_ledger()
    expected = _canonical_bytes(
        _owner_waiver_review_seed(
            candidate,
            infrastructure_look_ledger=ledger,
            owner_outcome_authority_receipt_id=(
                owner_outcome_authority_receipt_id
            ),
            claim_directory=claim_directory,
        )
    )
    if review_receipt_bytes != expected:
        raise FormalRunProtocolError(
            "review waiver receipt does not match the owner-authorized identities"
        )
    return _canonical_bytes(
        _owner_waiver_external_pin_seed(
            candidate=candidate,
            infrastructure_look_ledger=ledger,
            review_receipt_artifact_sha256=hashlib.sha256(
                review_receipt_bytes
            ).hexdigest(),
            owner_outcome_authority_receipt_id=(
                owner_outcome_authority_receipt_id
            ),
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
    if type(raw) is not dict:
        raise FormalRunProtocolError("external review pin fields changed")
    if _canonical_bytes(raw) != payload:
        raise FormalRunProtocolError("external review pin is not canonical bytes")
    fields = frozenset(raw)
    if fields == _EXTERNAL_PIN_FIELDS:
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
        review_authorization = {
            "review_disposition": INDEPENDENT_REVIEW_DISPOSITION,
            "independent_review_complete": True,
            "authorization_basis": INDEPENDENT_REVIEW_BASIS,
            "owner_review_waiver_id": None,
            "owner_review_waiver_scope": None,
            "waiver_ends_after_first_technically_completed_formal_backtest": False,
            "post_first_formal_backtest_independent_review_required": False,
        }
        claude_review_commit: str | None = str(raw["claude_review_commit"])
        codex_counterreview_commit: str | None = str(
            raw["codex_counterreview_commit"]
        )
    elif fields == _OWNER_WAIVER_EXTERNAL_PIN_FIELDS:
        expected = _owner_waiver_external_pin_seed(
            candidate=candidate,
            infrastructure_look_ledger=infrastructure_look_ledger,
            review_receipt_artifact_sha256=_require_sha256(
                raw["review_receipt_artifact_sha256"], "review receipt artifact"
            ),
            owner_outcome_authority_receipt_id=_require_id(
                raw["owner_outcome_authority_receipt_id"],
                "owner outcome/QC authority receipt",
            ),
            claim_directory=_require_claim_directory_text(raw["claim_directory"]),
        )
        review_authorization = formal_owner_review_waiver_record()
        claude_review_commit = None
        codex_counterreview_commit = None
    else:
        raise FormalRunProtocolError("external review pin fields changed")
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
        review_disposition=str(review_authorization["review_disposition"]),
        independent_review_complete=bool(
            review_authorization["independent_review_complete"]
        ),
        authorization_basis=str(review_authorization["authorization_basis"]),
        owner_review_waiver_id=(
            str(review_authorization["owner_review_waiver_id"])
            if review_authorization["owner_review_waiver_id"] is not None
            else None
        ),
        owner_review_waiver_scope=(
            str(review_authorization["owner_review_waiver_scope"])
            if review_authorization["owner_review_waiver_scope"] is not None
            else None
        ),
        waiver_ends_after_first_technically_completed_formal_backtest=bool(
            review_authorization[
                "waiver_ends_after_first_technically_completed_formal_backtest"
            ]
        ),
        post_first_formal_backtest_independent_review_required=bool(
            review_authorization[
                "post_first_formal_backtest_independent_review_required"
            ]
        ),
        claude_review_commit=claude_review_commit,
        codex_counterreview_commit=codex_counterreview_commit,
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
    if type(raw) is not dict:
        raise FormalRunProtocolError("review receipt fields changed")
    if _canonical_bytes(raw) != receipt_bytes:
        raise FormalRunProtocolError("review receipt is not canonical bytes")
    fields = frozenset(raw)
    if fields == _REVIEW_FIELDS and external_pin.independent_review_complete is True:
        claude_commit: str | None = _require_commit(
            raw["claude_review_commit"], "Claude review commit"
        )
        counter_commit: str | None = _require_commit(
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
    elif (
        fields == _OWNER_WAIVER_REVIEW_FIELDS
        and external_pin.independent_review_complete is False
    ):
        claude_commit = None
        counter_commit = None
        expected = _owner_waiver_review_seed(
            candidate,
            infrastructure_look_ledger=infrastructure_look_ledger,
            owner_outcome_authority_receipt_id=(
                external_pin.owner_outcome_authority_receipt_id
            ),
            claim_directory=str(external_pin.claim_directory),
        )
    else:
        raise FormalRunProtocolError("review receipt fields changed")
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
        review_disposition=external_pin.review_disposition,
        independent_review_complete=external_pin.independent_review_complete,
        authorization_basis=external_pin.authorization_basis,
        owner_review_waiver_id=external_pin.owner_review_waiver_id,
        owner_review_waiver_scope=external_pin.owner_review_waiver_scope,
        waiver_ends_after_first_technically_completed_formal_backtest=(
            external_pin.waiver_ends_after_first_technically_completed_formal_backtest
        ),
        post_first_formal_backtest_independent_review_required=(
            external_pin.post_first_formal_backtest_independent_review_required
        ),
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


def formal_review_authorization_record(
    authority: ReviewedFormalRunAuthority,
) -> dict[str, object]:
    """Project only the review/waiver semantics bound by formal execution."""

    if type(authority) is not ReviewedFormalRunAuthority:
        raise FormalRunProtocolError("formal review authorization type changed")
    record = {
        "review_disposition": authority.review_disposition,
        "independent_review_complete": authority.independent_review_complete,
        "authorization_basis": authority.authorization_basis,
        "owner_review_waiver_id": authority.owner_review_waiver_id,
        "owner_review_waiver_scope": authority.owner_review_waiver_scope,
        "waiver_ends_after_first_technically_completed_formal_backtest": (
            authority.waiver_ends_after_first_technically_completed_formal_backtest
        ),
        "post_first_formal_backtest_independent_review_required": (
            authority.post_first_formal_backtest_independent_review_required
        ),
    }
    reviewed = formal_independent_review_record()
    if record != reviewed and record != formal_owner_review_waiver_record():
        raise FormalRunProtocolError("formal review authorization changed")
    return record


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
    formal_review_authorization_record(authority)
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
    attempt_ordinal: int | None = None
    retry_lineage_sha256: str | None = None
    outcome_look_consumed: bool = True
    submission_plan_id: str | None = None
    submission_plan_sha256: str | None = None
    resumed_after_interruption: bool = False
    _attempt_lock_descriptor: int | None = dataclasses.field(
        default=None,
        repr=False,
        compare=False,
    )
    _attempt_lock_pid: int | None = dataclasses.field(
        default=None,
        repr=False,
        compare=False,
    )


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
    attempt_ordinal: int | None = None
    retry_lineage_sha256: str | None = None
    consumption_reason: str = "legacy_pre_network_one_shot"


@dataclasses.dataclass(frozen=True, slots=True)
class FormalPreSubmissionFailure:
    """Durable proof that one attempt ended before an outcome look existed."""

    failure_id: str
    failure_sha256: str
    claim_id: str
    claim_sha256: str
    authority_id: str
    candidate_id: str
    candidate_sha256: str
    attempt_ordinal: int
    retry_lineage_sha256: str
    phase: str
    failure_class: str
    recorded_at_utc: str
    outcome_look_consumed: bool
    retry_with_fresh_attempt_authorized: bool
    failure_path: Path
    _failure_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalSuccessfulCompletion:
    """Durable evidence that the owner-review waiver has ended."""

    completion_id: str
    completion_sha256: str
    claim_id: str
    claim_sha256: str
    permit_id: str
    permit_sha256: str
    authority_id: str
    candidate_id: str
    candidate_sha256: str
    attempt_ordinal: int
    retry_lineage_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    backtest_id: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    recorded_at_utc: str
    completion_path: Path
    _completion_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalAuthenticatedTerminalFailure:
    """Durable proof that one consumed run ended in exact ``Runtime Error``."""

    disposition_id: str
    disposition_sha256: str
    claim_id: str
    claim_sha256: str
    permit_id: str
    permit_sha256: str
    authority_id: str
    candidate_id: str
    candidate_sha256: str
    attempt_ordinal: int
    retry_lineage_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    backtest_id: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    recorded_at_utc: str
    disposition_path: Path
    _disposition_bytes: bytes = dataclasses.field(repr=False)


def _uses_owner_review_waiver(authority: ReviewedFormalRunAuthority) -> bool:
    return formal_review_authorization_record(authority) == (
        formal_owner_review_waiver_record()
    )


def _retry_attempt_path(
    directory: Path,
    template: str,
    attempt_ordinal: int,
) -> Path:
    _require_count(attempt_ordinal, "attempt_ordinal", minimum=1)
    if attempt_ordinal > 999_999:
        raise FormalRunProtocolError("attempt_ordinal exceeds its fixed bound")
    return directory / template.format(ordinal=attempt_ordinal)


def _acquire_retry_attempt_lock(directory: Path, attempt_ordinal: int) -> int:
    """Acquire the process-held lease for one resumable unconsumed attempt."""

    lock_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_LOCK_TEMPLATE,
        attempt_ordinal,
    )
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise FormalRunProtocolError(
            "formal retry attempt lock is unavailable"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        named = lock_path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
        ):
            raise FormalRunProtocolError(
                "formal retry attempt lock changed identity or mode"
            )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FormalRunProtocolError(
                "formal retry attempt is active in another execution"
            ) from exc
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _require_retry_attempt_lock(
    claim: FormalLookClaim,
    directory: Path,
) -> None:
    """Reauthenticate the still-open attempt's live process lease."""

    descriptor = claim._attempt_lock_descriptor
    if (
        type(descriptor) is not int
        or descriptor < 0
        or type(claim._attempt_lock_pid) is not int
        or claim._attempt_lock_pid != os.getpid()
        or type(claim.attempt_ordinal) is not int
    ):
        raise FormalRunProtocolError(
            "formal retry open-attempt process lease changed"
        )
    lock_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_LOCK_TEMPLATE,
        claim.attempt_ordinal,
    )
    try:
        opened = os.fstat(descriptor)
        named = lock_path.stat(follow_symlinks=False)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as exc:
        raise FormalRunProtocolError(
            "formal retry open-attempt process lease changed"
        ) from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_dev != named.st_dev
        or opened.st_ino != named.st_ino
    ):
        raise FormalRunProtocolError(
            "formal retry open-attempt process lease changed"
        )


def _release_retry_attempt_lock(claim: FormalLookClaim) -> None:
    """Release a lease only in the process that acquired it."""

    descriptor = claim._attempt_lock_descriptor
    if type(descriptor) is not int or type(claim._attempt_lock_pid) is not int:
        raise FormalRunProtocolError("formal retry attempt lease is unavailable")
    if claim._attempt_lock_pid != os.getpid():
        raise FormalRunProtocolError(
            "formal retry attempt lease belongs to a different process"
        )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    except OSError as exc:
        raise FormalRunProtocolError(
            "formal retry attempt lease could not be released"
        ) from exc


def _open_retry_attempt_ordinals(directory: Path) -> tuple[int, ...]:
    """Return exact claim ordinals that have neither immutable disposition."""

    pattern = re.compile(r"arv2-formal-attempt-([0-9]{6})-claim\.json\Z")
    open_ordinals: list[int] = []
    try:
        children = tuple(directory.iterdir())
    except OSError as exc:
        raise FormalRunProtocolError(
            "formal retry attempt directory cannot be censused"
        ) from exc
    for child in children:
        match = pattern.fullmatch(child.name)
        if match is None:
            continue
        ordinal = int(match.group(1))
        failure = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_FAILURE_TEMPLATE,
            ordinal,
        )
        permit = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_PERMIT_TEMPLATE,
            ordinal,
        )
        if not failure.exists() and not permit.exists():
            open_ordinals.append(ordinal)
    return tuple(sorted(open_ordinals))


def _strict_json_object(payload: bytes, name: str) -> dict[str, object]:
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
        raise FormalRunProtocolError(f"{name} is not strict JSON") from exc
    if type(raw) is not dict or _canonical_bytes(raw) != payload:
        raise FormalRunProtocolError(f"{name} is not canonical JSON")
    return raw


def _retry_attempt_claim_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    *,
    attempt_ordinal: int,
    retry_lineage_sha256: str,
    submission_plan_id: str,
    submission_plan_sha256: str,
    claimed_at_utc: str,
    prior_attempt_count: int,
    prior_consumed_attempt_count: int,
    prior_no_outcome_failure_count: int,
) -> dict[str, object]:
    _require_count(attempt_ordinal, "attempt_ordinal", minimum=1)
    _require_sha256(retry_lineage_sha256, "retry lineage")
    _require_id(submission_plan_id, "formal submission plan")
    _require_sha256(submission_plan_sha256, "formal submission plan")
    _require_utc(claimed_at_utc, "claimed_at_utc")
    for value, name in (
        (prior_attempt_count, "prior_attempt_count"),
        (prior_consumed_attempt_count, "prior_consumed_attempt_count"),
        (prior_no_outcome_failure_count, "prior_no_outcome_failure_count"),
    ):
        _require_count(value, name)
    if (
        prior_attempt_count != attempt_ordinal - 1
        or prior_consumed_attempt_count + prior_no_outcome_failure_count
        != prior_attempt_count
    ):
        raise FormalRunProtocolError("formal retry attempt census does not reconcile")
    raw: dict[str, object] = {
        "schema": RETRY_ATTEMPT_CLAIM_SCHEMA,
        "status": "pre_submission_attempt_open_outcome_look_unspent",
        "claim_id": None,
        "claim_sha256": None,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "evaluation_id": EVALUATION_ID,
        "owner_decision_id": OWNER_DECISION_ID,
        "attempt_ordinal": attempt_ordinal,
        "retry_lineage_sha256": retry_lineage_sha256,
        "submission_plan_id": submission_plan_id,
        "submission_plan_sha256": submission_plan_sha256,
        "claimed_at_utc": claimed_at_utc,
        "prior_attempt_count": prior_attempt_count,
        "prior_consumed_attempt_count": prior_consumed_attempt_count,
        "prior_no_outcome_failure_count": prior_no_outcome_failure_count,
        "maximum_backtest_submissions_per_attempt": 1,
        "submission_count_reserved": 0,
        "outcome_look_consumed": False,
        "fresh_attempt_only": True,
        "attempt_reuse_or_deletion_authorized": False,
        "automatic_retry_loop_authorized": False,
        "result_driven_changes_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["claim_sha256"] = digest
    raw["claim_id"] = f"arv2-formal-attempt-claim-{digest[:24]}"
    return raw


def _retry_attempt_failure_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    *,
    phase: str,
    failure_class: str,
    recorded_at_utc: str,
) -> dict[str, object]:
    _require_id(phase, "pre-submission failure phase")
    _require_id(failure_class, "pre-submission failure class")
    _require_utc(recorded_at_utc, "recorded_at_utc")
    raw: dict[str, object] = {
        "schema": RETRY_ATTEMPT_FAILURE_SCHEMA,
        "status": "definite_pre_backtests_create_failure_no_outcome_look",
        "failure_id": None,
        "failure_sha256": None,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "evaluation_id": EVALUATION_ID,
        "attempt_ordinal": claim.attempt_ordinal,
        "retry_lineage_sha256": claim.retry_lineage_sha256,
        "phase": phase,
        "failure_class": failure_class,
        "recorded_at_utc": recorded_at_utc,
        "backtests_create_attempted": False,
        "external_state_ambiguous": False,
        "outcome_look_consumed": False,
        "retry_with_fresh_attempt_authorized": True,
        "current_attempt_reuse_authorized": False,
        "result_driven_changes_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["failure_sha256"] = digest
    raw["failure_id"] = f"arv2-formal-prelaunch-failure-{digest[:24]}"
    return raw


def _retry_attempt_success_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    *,
    permit_id: str,
    permit_sha256: str,
    launch_receipt_id: str,
    launch_receipt_sha256: str,
    backtest_id: str,
    terminal_receipt_id: str,
    terminal_receipt_sha256: str,
    recorded_at_utc: str,
) -> dict[str, object]:
    for value, name in (
        (permit_id, "formal submission permit"),
        (launch_receipt_id, "formal launch receipt"),
        (backtest_id, "formal backtest"),
        (terminal_receipt_id, "formal terminal receipt"),
    ):
        _require_id(value, name)
    for value, name in (
        (permit_sha256, "formal submission permit"),
        (launch_receipt_sha256, "formal launch receipt"),
        (terminal_receipt_sha256, "formal terminal receipt"),
    ):
        _require_sha256(value, name)
    _require_utc(recorded_at_utc, "recorded_at_utc")
    raw: dict[str, object] = {
        "schema": RETRY_ATTEMPT_SUCCESS_SCHEMA,
        "status": "successful_completed_formal_backtest_owner_waiver_ended",
        "completion_id": None,
        "completion_sha256": None,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "permit_id": permit_id,
        "permit_sha256": permit_sha256,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "evaluation_id": EVALUATION_ID,
        "attempt_ordinal": claim.attempt_ordinal,
        "retry_lineage_sha256": claim.retry_lineage_sha256,
        "launch_receipt_id": launch_receipt_id,
        "launch_receipt_sha256": launch_receipt_sha256,
        "backtest_id": backtest_id,
        "terminal_receipt_id": terminal_receipt_id,
        "terminal_receipt_sha256": terminal_receipt_sha256,
        "qc_terminal_status": "Completed.",
        "recorded_at_utc": recorded_at_utc,
        "owner_review_waiver_ended": True,
        "post_first_formal_backtest_independent_review_required": True,
        "runtime_error_ends_owner_review_waiver": False,
        "fresh_retry_authorized": False,
        "result_read_requires_separate_terminal_gate": True,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["completion_sha256"] = digest
    raw["completion_id"] = f"arv2-formal-successful-completion-{digest[:24]}"
    return raw


def _retry_attempt_terminal_failure_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    *,
    permit_id: str,
    permit_sha256: str,
    launch_receipt_id: str,
    launch_receipt_sha256: str,
    backtest_id: str,
    terminal_receipt_id: str,
    terminal_receipt_sha256: str,
    recorded_at_utc: str,
) -> dict[str, object]:
    """Build the sole terminal failure that can authorize a fresh ordinal."""

    for value, name in (
        (permit_id, "formal submission permit"),
        (launch_receipt_id, "formal launch receipt"),
        (backtest_id, "formal backtest"),
        (terminal_receipt_id, "formal terminal receipt"),
    ):
        _require_id(value, name)
    for value, name in (
        (permit_sha256, "formal submission permit"),
        (launch_receipt_sha256, "formal launch receipt"),
        (terminal_receipt_sha256, "formal terminal receipt"),
    ):
        _require_sha256(value, name)
    _require_utc(recorded_at_utc, "recorded_at_utc")
    raw: dict[str, object] = {
        "schema": RETRY_ATTEMPT_TERMINAL_FAILURE_SCHEMA,
        "status": "authenticated_runtime_error_fresh_attempt_authorized",
        "disposition_id": None,
        "disposition_sha256": None,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "permit_id": permit_id,
        "permit_sha256": permit_sha256,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "evaluation_id": EVALUATION_ID,
        "attempt_ordinal": claim.attempt_ordinal,
        "retry_lineage_sha256": claim.retry_lineage_sha256,
        "submission_plan_id": claim.submission_plan_id,
        "submission_plan_sha256": claim.submission_plan_sha256,
        "launch_receipt_id": launch_receipt_id,
        "launch_receipt_sha256": launch_receipt_sha256,
        "backtest_id": backtest_id,
        "terminal_receipt_id": terminal_receipt_id,
        "terminal_receipt_sha256": terminal_receipt_sha256,
        "qc_terminal_status": "Runtime Error",
        "recorded_at_utc": recorded_at_utc,
        "outcome_look_consumed": True,
        "fresh_retry_authorized": True,
        "queued_running_unknown_or_ambiguous_retry_authorized": False,
        "current_attempt_reuse_authorized": False,
        "attempt_project_deletion_authorized": False,
        "result_read_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["disposition_sha256"] = digest
    raw["disposition_id"] = f"arv2-formal-terminal-failure-{digest[:24]}"
    return raw


def _retry_attempt_terminal_census(
    *,
    directory: Path,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    retry_lineage_sha256: str,
    submission_plan_id: str,
    submission_plan_sha256: str,
    next_attempt_ordinal: int,
) -> tuple[int, int, int]:
    """Authenticate every immutable predecessor before opening a retry."""

    consumed = 0
    no_outcome = 0
    for ordinal in range(1, next_attempt_ordinal):
        claim_path = _retry_attempt_path(
            directory, _RETRY_ATTEMPT_CLAIM_TEMPLATE, ordinal
        )
        payload = _read_private_regular(
            claim_path,
            maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
            name="formal retry predecessor claim",
        )
        raw = _strict_json_object(payload, "formal retry predecessor claim")
        expected_claim = _retry_attempt_claim_document(
            candidate,
            authority,
            attempt_ordinal=ordinal,
            retry_lineage_sha256=retry_lineage_sha256,
            submission_plan_id=submission_plan_id,
            submission_plan_sha256=submission_plan_sha256,
            claimed_at_utc=raw.get("claimed_at_utc"),
            prior_attempt_count=ordinal - 1,
            prior_consumed_attempt_count=consumed,
            prior_no_outcome_failure_count=no_outcome,
        )
        if raw != expected_claim:
            raise FormalRunProtocolError(
                "formal retry predecessor changed or crossed lineage"
            )
        predecessor_claim = FormalLookClaim(
            claim_id=str(expected_claim["claim_id"]),
            claim_sha256=str(expected_claim["claim_sha256"]),
            authority_id=authority.authority_id,
            candidate_id=candidate.candidate_id,
            candidate_sha256=candidate.candidate_sha256,
            claimed_at_utc=str(expected_claim["claimed_at_utc"]),
            maximum_submissions=1,
            submission_count_reserved=0,
            ambiguous_submission_consumes_look=True,
            retry_authorized=True,
            claim_path=claim_path,
            _claim_bytes=payload,
            attempt_ordinal=ordinal,
            retry_lineage_sha256=retry_lineage_sha256,
            outcome_look_consumed=False,
            submission_plan_id=submission_plan_id,
            submission_plan_sha256=submission_plan_sha256,
        )
        failure_path = _retry_attempt_path(
            directory, _RETRY_ATTEMPT_FAILURE_TEMPLATE, ordinal
        )
        permit_path = _retry_attempt_path(
            directory, _RETRY_ATTEMPT_PERMIT_TEMPLATE, ordinal
        )
        failure_exists = failure_path.exists()
        permit_exists = permit_path.exists()
        if failure_exists == permit_exists:
            raise FormalRunProtocolError(
                "formal retry predecessor lacks one exact terminal disposition"
            )
        terminal_path = failure_path if failure_exists else permit_path
        terminal = _strict_json_object(
            _read_private_regular(
                terminal_path,
                maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
                name="formal retry predecessor disposition",
            ),
            "formal retry predecessor disposition",
        )
        if failure_exists:
            expected_terminal = _retry_attempt_failure_document(
                candidate,
                authority,
                predecessor_claim,
                phase=terminal.get("phase"),
                failure_class=terminal.get("failure_class"),
                recorded_at_utc=terminal.get("recorded_at_utc"),
            )
            if terminal != expected_terminal:
                raise FormalRunProtocolError(
                    "formal retry no-outcome disposition changed"
                )
            no_outcome += 1
        else:
            expected_terminal = _retry_attempt_permit_document(
                candidate,
                authority,
                predecessor_claim,
                submission_started_at_utc=terminal.get(
                    "submission_started_at_utc"
                ),
                consumption_reason=terminal.get("consumption_reason"),
            )
            if terminal != expected_terminal:
                raise FormalRunProtocolError(
                    "formal retry consumed disposition changed"
                )
            success_path = _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_SUCCESS_TEMPLATE,
                ordinal,
            )
            terminal_failure_path = _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_TERMINAL_FAILURE_TEMPLATE,
                ordinal,
            )
            if success_path.exists() and terminal_failure_path.exists():
                raise FormalRunProtocolError(
                    "formal consumed attempt has conflicting terminal dispositions"
                )
            if success_path.exists():
                success = _strict_json_object(
                    _read_private_regular(
                        success_path,
                        maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
                        name="formal successful-completion disposition",
                    ),
                    "formal successful-completion disposition",
                )
                expected_success = _retry_attempt_success_document(
                    candidate,
                    authority,
                    predecessor_claim,
                    permit_id=terminal.get("permit_id"),
                    permit_sha256=terminal.get("permit_sha256"),
                    launch_receipt_id=success.get("launch_receipt_id"),
                    launch_receipt_sha256=success.get("launch_receipt_sha256"),
                    backtest_id=success.get("backtest_id"),
                    terminal_receipt_id=success.get("terminal_receipt_id"),
                    terminal_receipt_sha256=success.get("terminal_receipt_sha256"),
                    recorded_at_utc=success.get("recorded_at_utc"),
                )
                if success != expected_success:
                    raise FormalRunProtocolError(
                        "formal successful-completion disposition changed"
                    )
                raise FormalRunProtocolError(
                    "owner review waiver ended after a successful Completed formal backtest"
                )
            if not terminal_failure_path.exists():
                raise FormalRunProtocolError(
                    "formal consumed predecessor lacks an authenticated terminal failure"
                )
            terminal_failure = _strict_json_object(
                _read_private_regular(
                    terminal_failure_path,
                    maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
                    name="formal authenticated terminal-failure disposition",
                ),
                "formal authenticated terminal-failure disposition",
            )
            expected_failure = _retry_attempt_terminal_failure_document(
                candidate,
                authority,
                predecessor_claim,
                permit_id=terminal.get("permit_id"),
                permit_sha256=terminal.get("permit_sha256"),
                launch_receipt_id=terminal_failure.get("launch_receipt_id"),
                launch_receipt_sha256=terminal_failure.get(
                    "launch_receipt_sha256"
                ),
                backtest_id=terminal_failure.get("backtest_id"),
                terminal_receipt_id=terminal_failure.get("terminal_receipt_id"),
                terminal_receipt_sha256=terminal_failure.get(
                    "terminal_receipt_sha256"
                ),
                recorded_at_utc=terminal_failure.get("recorded_at_utc"),
            )
            if terminal_failure != expected_failure:
                raise FormalRunProtocolError(
                    "formal authenticated terminal-failure disposition changed"
                )
            consumed += 1
    return next_attempt_ordinal - 1, consumed, no_outcome


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
    """Atomically publish one complete private immutable ledger entry.

    Bytes are written and fsynced under a private staging name before a hard
    link publishes the final name with create-exclusive semantics.  Therefore
    an interruption can leave either no final entry or the complete entry, but
    never a partial final claim/disposition that makes a retry uncloseable.
    """

    target = directory / filename
    staging: Path | None = None
    descriptor: int | None = None
    published = False
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{filename}.pending-",
            dir=directory,
        )
        staging = Path(staging_name)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
        ):
            raise FormalRunProtocolError(
                "formal ledger staging file is not private"
            )
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise FormalRunProtocolError("formal ledger write stalled")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise FormalRunProtocolError(
                "formal look is already spent; retry is not authorized"
            ) from exc
        except OSError as exc:
            raise FormalRunProtocolError(
                "formal ledger entry could not be created"
            ) from exc
        published = True
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
        if staging is None:
            raise FormalRunProtocolError(
                "formal ledger entry could not be created"
            ) from exc
        if not published:
            raise FormalRunProtocolError(
                "formal ledger staging write failed before publication"
            ) from exc
        raise FormalRunProtocolError(
            "formal ledger entry cannot be reauthenticated after creation"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if staging is not None:
            try:
                staging.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # A private, ignored staging name is safer than turning an
                # already-published immutable entry into an ambiguous result.
                pass
    if stored != payload:
        raise FormalRunProtocolError("formal ledger entry changed after creation")
    return target


def _formal_retry_adapter_control_path(
    directory: Path,
    attempt_ordinal: int,
    control_kind: str,
) -> Path:
    """Return one exact adapter-control name within a retry attempt."""

    if type(control_kind) is not str:
        raise FormalRunProtocolError("formal retry adapter control kind changed")
    if control_kind == "compiled":
        template = _RETRY_ATTEMPT_COMPILED_CONTROL_TEMPLATE
    elif control_kind == "launch":
        template = _RETRY_ATTEMPT_LAUNCH_CONTROL_TEMPLATE
    elif control_kind == "terminal":
        template = _RETRY_ATTEMPT_TERMINAL_CONTROL_TEMPLATE
    else:
        raise FormalRunProtocolError("formal retry adapter control kind changed")
    return _retry_attempt_path(directory, template, attempt_ordinal)


def _publish_formal_retry_adapter_control_once(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    control_kind: str,
    payload: bytes,
) -> Path:
    """Atomically publish one bounded adapter record for an owner-waived attempt.

    The protocol owns file placement and durability; the adapter owns and later
    reauthenticates the record schema.  A control record never changes the
    attempt's spent/unspent disposition and grants no network or result access.
    """

    require_formal_look_claim(candidate, authority, claim)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "formal retry adapter control requires the owner-review waiver"
        )
    if type(claim.attempt_ordinal) is not int:
        raise FormalRunProtocolError("formal retry adapter control attempt changed")
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_REVIEW_RECEIPT_BYTES
    ):
        raise FormalRunProtocolError(
            "formal retry adapter control payload is not bounded exact bytes"
        )
    directory = _require_private_directory(authority.claim_directory)
    target = _formal_retry_adapter_control_path(
        directory,
        claim.attempt_ordinal,
        control_kind,
    )
    return _exclusive_private_write(directory, target.name, payload)


def _read_formal_retry_adapter_control(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    control_kind: str,
) -> bytes:
    """Read one immutable adapter record without granting process authority."""

    require_formal_look_claim(candidate, authority, claim)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "formal retry adapter control requires the owner-review waiver"
        )
    if type(claim.attempt_ordinal) is not int:
        raise FormalRunProtocolError("formal retry adapter control attempt changed")
    directory = _require_private_directory(authority.claim_directory)
    return _read_private_regular(
        _formal_retry_adapter_control_path(
            directory,
            claim.attempt_ordinal,
            control_kind,
        ),
        maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
        name=f"formal retry {control_kind} adapter control",
    )


def _formal_retry_adapter_control_exists(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    control_kind: str,
) -> bool:
    """Report exact-name presence only; content is authenticated separately."""

    require_formal_look_claim(candidate, authority, claim)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "formal retry adapter control requires the owner-review waiver"
        )
    if type(claim.attempt_ordinal) is not int:
        raise FormalRunProtocolError("formal retry adapter control attempt changed")
    directory = _require_private_directory(authority.claim_directory)
    return _formal_retry_adapter_control_path(
        directory,
        claim.attempt_ordinal,
        control_kind,
    ).exists()


def claim_formal_run_once(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claimed_at_utc: str,
    attempt_ordinal: int | None = None,
    retry_lineage_sha256: str | None = None,
    submission_plan_id: str | None = None,
    submission_plan_sha256: str | None = None,
) -> FormalLookClaim:
    """Open one immutable attempt before any submitter can be invoked.

    The ordinary reviewed path preserves the original one-look behavior.  The
    exact owner-waiver path opens an outcome-unspent attempt.  Only a separately
    recorded definite pre-``backtests/create`` failure or a consumed-attempt
    marker can authorize the next sequential attempt; no loop is internal.
    """

    require_reviewed_formal_run_authority(candidate, authority)
    directory = _require_private_directory(authority.claim_directory)
    if _uses_owner_review_waiver(authority):
        if (
            type(attempt_ordinal) is not int
            or type(retry_lineage_sha256) is not str
            or type(submission_plan_id) is not str
            or type(submission_plan_sha256) is not str
        ):
            raise FormalRunProtocolError(
                "owner-waived formal run requires an exact retry lineage and plan"
            )
        retry_lineage_sha256 = _require_sha256(
            retry_lineage_sha256, "retry lineage"
        )
        submission_plan_id = _require_id(
            submission_plan_id, "formal submission plan"
        )
        submission_plan_sha256 = _require_sha256(
            submission_plan_sha256, "formal submission plan"
        )
        _require_utc(claimed_at_utc, "claimed_at_utc")
        prior, consumed, no_outcome = _retry_attempt_terminal_census(
            directory=directory,
            candidate=candidate,
            authority=authority,
            retry_lineage_sha256=retry_lineage_sha256,
            submission_plan_id=submission_plan_id,
            submission_plan_sha256=submission_plan_sha256,
            next_attempt_ordinal=attempt_ordinal,
        )
        descriptor = _acquire_retry_attempt_lock(directory, attempt_ordinal)
        try:
            target = _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_CLAIM_TEMPLATE,
                attempt_ordinal,
            )
            failure_path = _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_FAILURE_TEMPLATE,
                attempt_ordinal,
            )
            permit_path = _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_PERMIT_TEMPLATE,
                attempt_ordinal,
            )
            success_path = _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_SUCCESS_TEMPLATE,
                attempt_ordinal,
            )
            open_ordinals = _open_retry_attempt_ordinals(directory)
            if failure_path.exists() or permit_path.exists() or success_path.exists():
                raise FormalRunProtocolError(
                    "formal retry attempt is already durably closed"
                )
            if target.exists():
                if open_ordinals != (attempt_ordinal,):
                    raise FormalRunProtocolError(
                        "formal retry claim is not the sole open attempt"
                    )
                payload = _read_private_regular(
                    target,
                    maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
                    name="resumable formal retry claim",
                )
                raw = _strict_json_object(
                    payload,
                    "resumable formal retry claim",
                )
                expected = _retry_attempt_claim_document(
                    candidate,
                    authority,
                    attempt_ordinal=attempt_ordinal,
                    retry_lineage_sha256=retry_lineage_sha256,
                    submission_plan_id=submission_plan_id,
                    submission_plan_sha256=submission_plan_sha256,
                    claimed_at_utc=raw.get("claimed_at_utc"),
                    prior_attempt_count=prior,
                    prior_consumed_attempt_count=consumed,
                    prior_no_outcome_failure_count=no_outcome,
                )
                if raw != expected:
                    raise FormalRunProtocolError(
                        "resumable formal retry claim changed lineage or plan"
                    )
                resumed = True
            else:
                if open_ordinals:
                    raise FormalRunProtocolError(
                        "another formal retry claim remains open"
                    )
                raw = _retry_attempt_claim_document(
                    candidate,
                    authority,
                    attempt_ordinal=attempt_ordinal,
                    retry_lineage_sha256=retry_lineage_sha256,
                    submission_plan_id=submission_plan_id,
                    submission_plan_sha256=submission_plan_sha256,
                    claimed_at_utc=claimed_at_utc,
                    prior_attempt_count=prior,
                    prior_consumed_attempt_count=consumed,
                    prior_no_outcome_failure_count=no_outcome,
                )
                payload = _canonical_bytes(raw)
                target = _exclusive_private_write(
                    directory,
                    target.name,
                    payload,
                )
                resumed = False
            return FormalLookClaim(
                claim_id=str(raw["claim_id"]),
                claim_sha256=str(raw["claim_sha256"]),
                authority_id=authority.authority_id,
                candidate_id=candidate.candidate_id,
                candidate_sha256=candidate.candidate_sha256,
                claimed_at_utc=str(raw["claimed_at_utc"]),
                maximum_submissions=1,
                submission_count_reserved=0,
                ambiguous_submission_consumes_look=True,
                retry_authorized=True,
                attempt_ordinal=attempt_ordinal,
                retry_lineage_sha256=retry_lineage_sha256,
                outcome_look_consumed=False,
                submission_plan_id=submission_plan_id,
                submission_plan_sha256=submission_plan_sha256,
                resumed_after_interruption=resumed,
                claim_path=target,
                _claim_bytes=payload,
                _attempt_lock_descriptor=descriptor,
                _attempt_lock_pid=os.getpid(),
            )
        except BaseException:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
            raise
    if (
        attempt_ordinal is not None
        or retry_lineage_sha256 is not None
        or submission_plan_id is not None
        or submission_plan_sha256 is not None
    ):
        raise FormalRunProtocolError(
            "independently reviewed one-shot authority cannot claim a retry attempt"
        )
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
        attempt_ordinal=None,
        retry_lineage_sha256=None,
        outcome_look_consumed=True,
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
        waived = _uses_owner_review_waiver(authority)
        if waived:
            if type(claim.attempt_ordinal) is not int:
                raise FormalRunProtocolError("formal look claim attempt changed")
            expected_path = _retry_attempt_path(
                authority.claim_directory,
                _RETRY_ATTEMPT_CLAIM_TEMPLATE,
                claim.attempt_ordinal,
            )
        else:
            expected_path = authority.claim_directory / CLAIM_FILENAME
        if claim.claim_path != expected_path:
            raise FormalRunProtocolError("formal look claim path changed")
        payload = _read_private_regular(
            claim.claim_path,
            maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
            name="formal look claim",
        )
    except (AttributeError, OSError) as exc:
        raise FormalRunProtocolError("formal look claim is unavailable") from exc
    if waived:
        if (
            type(claim.retry_lineage_sha256) is not str
            or type(claim.submission_plan_id) is not str
            or type(claim.submission_plan_sha256) is not str
        ):
            raise FormalRunProtocolError(
                "formal look claim retry lineage or plan changed"
            )
        prior, consumed, no_outcome = _retry_attempt_terminal_census(
            directory=authority.claim_directory,
            candidate=candidate,
            authority=authority,
            retry_lineage_sha256=claim.retry_lineage_sha256,
            submission_plan_id=claim.submission_plan_id,
            submission_plan_sha256=claim.submission_plan_sha256,
            next_attempt_ordinal=claim.attempt_ordinal,
        )
        expected = _canonical_bytes(
            _retry_attempt_claim_document(
                candidate,
                authority,
                attempt_ordinal=claim.attempt_ordinal,
                retry_lineage_sha256=claim.retry_lineage_sha256,
                submission_plan_id=claim.submission_plan_id,
                submission_plan_sha256=claim.submission_plan_sha256,
                claimed_at_utc=claim.claimed_at_utc,
                prior_attempt_count=prior,
                prior_consumed_attempt_count=consumed,
                prior_no_outcome_failure_count=no_outcome,
            )
        )
        expected_submission_reserved = 0
        expected_retry_authorized = True
        expected_outcome_consumed = False
        failure_path = _retry_attempt_path(
            authority.claim_directory,
            _RETRY_ATTEMPT_FAILURE_TEMPLATE,
            claim.attempt_ordinal,
        )
        permit_path = _retry_attempt_path(
            authority.claim_directory,
            _RETRY_ATTEMPT_PERMIT_TEMPLATE,
            claim.attempt_ordinal,
        )
        if failure_path.exists() and permit_path.exists():
            raise FormalRunProtocolError(
                "formal retry attempt has conflicting dispositions"
            )
        if not failure_path.exists() and not permit_path.exists():
            _require_retry_attempt_lock(claim, authority.claim_directory)
    else:
        expected = _canonical_bytes(
            _claim_document(candidate, authority, claimed_at_utc=claim.claimed_at_utc)
        )
        expected_submission_reserved = 1
        expected_retry_authorized = False
        expected_outcome_consumed = True
        if (
            claim.attempt_ordinal is not None
            or claim.retry_lineage_sha256 is not None
            or claim.submission_plan_id is not None
            or claim.submission_plan_sha256 is not None
            or claim.resumed_after_interruption is not False
            or claim._attempt_lock_descriptor is not None
            or claim._attempt_lock_pid is not None
        ):
            raise FormalRunProtocolError("formal look claim attempt changed")
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
        or claim.submission_count_reserved != expected_submission_reserved
        or claim.ambiguous_submission_consumes_look is not True
        or claim.retry_authorized is not expected_retry_authorized
        or claim.outcome_look_consumed is not expected_outcome_consumed
        or type(claim.resumed_after_interruption) is not bool
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


def _retry_attempt_permit_document(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    *,
    submission_started_at_utc: str,
    consumption_reason: str,
) -> dict[str, object]:
    _require_utc(submission_started_at_utc, "submission_started_at_utc")
    if type(consumption_reason) is not str or consumption_reason not in {
        "backtests_create_attempt",
        "external_state_ambiguous",
    }:
        raise FormalRunProtocolError("formal attempt consumption reason changed")
    raw: dict[str, object] = {
        "schema": RETRY_ATTEMPT_PERMIT_SCHEMA,
        "status": "formal_attempt_permanently_consumed_and_counted",
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
        "attempt_ordinal": claim.attempt_ordinal,
        "retry_lineage_sha256": claim.retry_lineage_sha256,
        "submission_started_at_utc": submission_started_at_utc,
        "consumption_reason": consumption_reason,
        "backtests_create_attempted": consumption_reason == "backtests_create_attempt",
        "external_state_ambiguous": consumption_reason == "external_state_ambiguous",
        "maximum_backtest_submissions_per_attempt": 1,
        "submission_attempt_count": (
            1 if consumption_reason == "backtests_create_attempt" else 0
        ),
        "outcome_look_consumed": True,
        "retry_with_fresh_attempt_authorized": False,
        "fresh_retry_requires_authenticated_terminal_failure": True,
        "current_attempt_reuse_authorized": False,
        "attempt_deletion_authorized": False,
        "result_driven_changes_authorized": False,
        "result_read_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
    raw["permit_sha256"] = digest
    raw["permit_id"] = f"arv2-formal-attempt-consumed-{digest[:24]}"
    return raw


def begin_formal_submission_once(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    submission_started_at_utc: str,
    consumption_reason: str = "backtests_create_attempt",
) -> FormalSubmissionPermit:
    """Permanently consume one attempt immediately before outcome creation."""

    require_formal_look_claim(candidate, authority, claim)
    directory = _require_private_directory(authority.claim_directory)
    if _uses_owner_review_waiver(authority):
        if type(claim.attempt_ordinal) is not int:
            raise FormalRunProtocolError("formal attempt ordinal changed")
        failure_path = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_FAILURE_TEMPLATE,
            claim.attempt_ordinal,
        )
        if failure_path.exists():
            raise FormalRunProtocolError(
                "definite pre-submission failure already closed this attempt"
            )
        raw = _retry_attempt_permit_document(
            candidate,
            authority,
            claim,
            submission_started_at_utc=submission_started_at_utc,
            consumption_reason=consumption_reason,
        )
        payload = _canonical_bytes(raw)
        target = _exclusive_private_write(
            directory,
            _retry_attempt_path(
                directory,
                _RETRY_ATTEMPT_PERMIT_TEMPLATE,
                claim.attempt_ordinal,
            ).name,
            payload,
        )
        _release_retry_attempt_lock(claim)
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
            submission_attempt_count=int(raw["submission_attempt_count"]),
            ambiguous_submission_consumes_look=True,
            retry_authorized=False,
            attempt_ordinal=claim.attempt_ordinal,
            retry_lineage_sha256=claim.retry_lineage_sha256,
            consumption_reason=consumption_reason,
            permit_path=target,
            _permit_bytes=payload,
        )
    if consumption_reason != "backtests_create_attempt":
        raise FormalRunProtocolError(
            "legacy one-shot authority cannot consume an ambiguity retry marker"
        )
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
        attempt_ordinal=None,
        retry_lineage_sha256=None,
        consumption_reason="legacy_pre_network_one_shot",
        permit_path=target,
        _permit_bytes=payload,
    )


def record_definite_pre_submission_failure(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    phase: str,
    failure_class: str,
    recorded_at_utc: str,
) -> FormalPreSubmissionFailure:
    """Close an owner-waived attempt known not to have created an outcome."""

    require_formal_look_claim(candidate, authority, claim)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "legacy one-shot authority cannot record a retryable failure"
        )
    if type(claim.attempt_ordinal) is not int:
        raise FormalRunProtocolError("formal attempt ordinal changed")
    directory = _require_private_directory(authority.claim_directory)
    permit_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_PERMIT_TEMPLATE,
        claim.attempt_ordinal,
    )
    if permit_path.exists():
        raise FormalRunProtocolError(
            "consumed formal attempt cannot become a no-outcome failure"
        )
    raw = _retry_attempt_failure_document(
        candidate,
        authority,
        claim,
        phase=phase,
        failure_class=failure_class,
        recorded_at_utc=recorded_at_utc,
    )
    payload = _canonical_bytes(raw)
    target = _exclusive_private_write(
        directory,
        _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_FAILURE_TEMPLATE,
            claim.attempt_ordinal,
        ).name,
        payload,
    )
    _release_retry_attempt_lock(claim)
    return FormalPreSubmissionFailure(
        failure_id=str(raw["failure_id"]),
        failure_sha256=str(raw["failure_sha256"]),
        claim_id=claim.claim_id,
        claim_sha256=claim.claim_sha256,
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        attempt_ordinal=claim.attempt_ordinal,
        retry_lineage_sha256=str(claim.retry_lineage_sha256),
        phase=phase,
        failure_class=failure_class,
        recorded_at_utc=recorded_at_utc,
        outcome_look_consumed=False,
        retry_with_fresh_attempt_authorized=True,
        failure_path=target,
        _failure_bytes=payload,
    )


def _record_authenticated_formal_backtest_completion(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
    launch_receipt: object,
    terminal_receipt: object,
    recorded_at_utc: str,
) -> FormalSuccessfulCompletion:
    """Persist an adapter-authenticated ``Completed.`` disposition.

    This is deliberately an internal ledger primitive.  Process-return
    authority belongs to the submission adapter; its sealed status action must
    authenticate the exact launch and terminal objects before entering this
    durable boundary.  Keeping the primitive out of the public protocol surface
    prevents scalar identities (or caller-constructed lookalike objects) from
    ending the owner-review waiver.
    """

    require_formal_submission_permit(candidate, authority, claim, permit)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "independently reviewed authority has no owner waiver to end"
        )
    if (
        permit.consumption_reason != "backtests_create_attempt"
        or permit.submission_attempt_count != 1
        or type(claim.attempt_ordinal) is not int
    ):
        raise FormalRunProtocolError(
            "successful completion requires one consumed backtests/create attempt"
        )
    try:
        launch_receipt_id = launch_receipt.receipt_id
        launch_receipt_sha256 = launch_receipt.receipt_sha256
        backtest_id = launch_receipt.backtest_id
        terminal_receipt_id = terminal_receipt.receipt_id
        terminal_receipt_sha256 = terminal_receipt.receipt_sha256
        terminal_status = terminal_receipt.terminal_status
        terminal_launch_receipt_id = terminal_receipt.launch_receipt_id
        terminal_launch_receipt_sha256 = terminal_receipt.launch_receipt_sha256
        terminal_permit_id = terminal_receipt.permit_id
        terminal_permit_sha256 = terminal_receipt.permit_sha256
        terminal_backtest_id = terminal_receipt.backtest_id
    except AttributeError as exc:
        raise FormalRunProtocolError(
            "successful completion requires exact launch and terminal receipts"
        ) from exc
    if (
        type(terminal_status) is not str
        or terminal_status != "Completed."
        or terminal_launch_receipt_id != launch_receipt_id
        or terminal_launch_receipt_sha256 != launch_receipt_sha256
        or terminal_permit_id != permit.permit_id
        or terminal_permit_sha256 != permit.permit_sha256
        or terminal_backtest_id != backtest_id
        or getattr(launch_receipt, "permit_id", None) != permit.permit_id
        or getattr(launch_receipt, "permit_sha256", None) != permit.permit_sha256
    ):
        raise FormalRunProtocolError(
            "successful completion terminal receipt is not the exact Completed run"
        )
    raw = _retry_attempt_success_document(
        candidate,
        authority,
        claim,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        launch_receipt_id=launch_receipt_id,
        launch_receipt_sha256=launch_receipt_sha256,
        backtest_id=backtest_id,
        terminal_receipt_id=terminal_receipt_id,
        terminal_receipt_sha256=terminal_receipt_sha256,
        recorded_at_utc=recorded_at_utc,
    )
    payload = _canonical_bytes(raw)
    directory = _require_private_directory(authority.claim_directory)
    descriptor = _acquire_retry_attempt_lock(directory, claim.attempt_ordinal)
    try:
        terminal_failure_path = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_TERMINAL_FAILURE_TEMPLATE,
            claim.attempt_ordinal,
        )
        if terminal_failure_path.exists():
            raise FormalRunProtocolError(
                "Runtime Error already closed this formal attempt"
            )
        completion_path = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_SUCCESS_TEMPLATE,
            claim.attempt_ordinal,
        )
        if completion_path.exists():
            payload = _read_private_regular(
                completion_path,
                maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
                name="existing formal successful-completion disposition",
            )
            existing = _strict_json_object(
                payload,
                "existing formal successful-completion disposition",
            )
            raw = _retry_attempt_success_document(
                candidate,
                authority,
                claim,
                permit_id=permit.permit_id,
                permit_sha256=permit.permit_sha256,
                launch_receipt_id=launch_receipt_id,
                launch_receipt_sha256=launch_receipt_sha256,
                backtest_id=backtest_id,
                terminal_receipt_id=terminal_receipt_id,
                terminal_receipt_sha256=terminal_receipt_sha256,
                recorded_at_utc=existing.get("recorded_at_utc"),
            )
            if existing != raw or payload != _canonical_bytes(raw):
                raise FormalRunProtocolError(
                    "existing Completed disposition changed exact run identity"
                )
            target = completion_path
        else:
            target = _exclusive_private_write(
                directory,
                completion_path.name,
                payload,
            )
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    return FormalSuccessfulCompletion(
        completion_id=str(raw["completion_id"]),
        completion_sha256=str(raw["completion_sha256"]),
        claim_id=claim.claim_id,
        claim_sha256=claim.claim_sha256,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        attempt_ordinal=claim.attempt_ordinal,
        retry_lineage_sha256=str(claim.retry_lineage_sha256),
        launch_receipt_id=launch_receipt_id,
        launch_receipt_sha256=launch_receipt_sha256,
        backtest_id=backtest_id,
        terminal_receipt_id=terminal_receipt_id,
        terminal_receipt_sha256=terminal_receipt_sha256,
        recorded_at_utc=str(raw["recorded_at_utc"]),
        completion_path=target,
        _completion_bytes=payload,
    )


def _record_authenticated_formal_backtest_terminal_failure(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
    launch_receipt: object,
    terminal_receipt: object,
    recorded_at_utc: str,
) -> FormalAuthenticatedTerminalFailure:
    """Persist the exact authenticated ``Runtime Error`` retry boundary."""

    require_formal_submission_permit(candidate, authority, claim, permit)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "independently reviewed authority has no waiver retry to authorize"
        )
    if (
        permit.consumption_reason != "backtests_create_attempt"
        or permit.submission_attempt_count != 1
        or type(claim.attempt_ordinal) is not int
    ):
        raise FormalRunProtocolError(
            "terminal failure requires one consumed backtests/create attempt"
        )
    try:
        launch_receipt_id = launch_receipt.receipt_id
        launch_receipt_sha256 = launch_receipt.receipt_sha256
        backtest_id = launch_receipt.backtest_id
        terminal_receipt_id = terminal_receipt.receipt_id
        terminal_receipt_sha256 = terminal_receipt.receipt_sha256
        terminal_status = terminal_receipt.terminal_status
        terminal_launch_receipt_id = terminal_receipt.launch_receipt_id
        terminal_launch_receipt_sha256 = terminal_receipt.launch_receipt_sha256
        terminal_permit_id = terminal_receipt.permit_id
        terminal_permit_sha256 = terminal_receipt.permit_sha256
        terminal_backtest_id = terminal_receipt.backtest_id
    except AttributeError as exc:
        raise FormalRunProtocolError(
            "terminal failure requires exact launch and terminal receipts"
        ) from exc
    if (
        type(terminal_status) is not str
        or terminal_status != "Runtime Error"
        or terminal_launch_receipt_id != launch_receipt_id
        or terminal_launch_receipt_sha256 != launch_receipt_sha256
        or terminal_permit_id != permit.permit_id
        or terminal_permit_sha256 != permit.permit_sha256
        or terminal_backtest_id != backtest_id
        or getattr(launch_receipt, "permit_id", None) != permit.permit_id
        or getattr(launch_receipt, "permit_sha256", None) != permit.permit_sha256
    ):
        raise FormalRunProtocolError(
            "terminal failure receipt is not the exact Runtime Error run"
        )
    raw = _retry_attempt_terminal_failure_document(
        candidate,
        authority,
        claim,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        launch_receipt_id=launch_receipt_id,
        launch_receipt_sha256=launch_receipt_sha256,
        backtest_id=backtest_id,
        terminal_receipt_id=terminal_receipt_id,
        terminal_receipt_sha256=terminal_receipt_sha256,
        recorded_at_utc=recorded_at_utc,
    )
    payload = _canonical_bytes(raw)
    directory = _require_private_directory(authority.claim_directory)
    descriptor = _acquire_retry_attempt_lock(directory, claim.attempt_ordinal)
    try:
        success_path = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_SUCCESS_TEMPLATE,
            claim.attempt_ordinal,
        )
        if success_path.exists():
            raise FormalRunProtocolError(
                "Completed already closed this formal attempt"
            )
        disposition_path = _retry_attempt_path(
            directory,
            _RETRY_ATTEMPT_TERMINAL_FAILURE_TEMPLATE,
            claim.attempt_ordinal,
        )
        if disposition_path.exists():
            payload = _read_private_regular(
                disposition_path,
                maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
                name="existing formal authenticated terminal-failure disposition",
            )
            existing = _strict_json_object(
                payload,
                "existing formal authenticated terminal-failure disposition",
            )
            raw = _retry_attempt_terminal_failure_document(
                candidate,
                authority,
                claim,
                permit_id=permit.permit_id,
                permit_sha256=permit.permit_sha256,
                launch_receipt_id=launch_receipt_id,
                launch_receipt_sha256=launch_receipt_sha256,
                backtest_id=backtest_id,
                terminal_receipt_id=terminal_receipt_id,
                terminal_receipt_sha256=terminal_receipt_sha256,
                recorded_at_utc=existing.get("recorded_at_utc"),
            )
            if existing != raw or payload != _canonical_bytes(raw):
                raise FormalRunProtocolError(
                    "existing Runtime Error disposition changed exact run identity"
                )
            target = disposition_path
        else:
            target = _exclusive_private_write(
                directory,
                disposition_path.name,
                payload,
            )
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    return FormalAuthenticatedTerminalFailure(
        disposition_id=str(raw["disposition_id"]),
        disposition_sha256=str(raw["disposition_sha256"]),
        claim_id=claim.claim_id,
        claim_sha256=claim.claim_sha256,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        attempt_ordinal=claim.attempt_ordinal,
        retry_lineage_sha256=str(claim.retry_lineage_sha256),
        launch_receipt_id=launch_receipt_id,
        launch_receipt_sha256=launch_receipt_sha256,
        backtest_id=backtest_id,
        terminal_receipt_id=terminal_receipt_id,
        terminal_receipt_sha256=terminal_receipt_sha256,
        recorded_at_utc=str(raw["recorded_at_utc"]),
        disposition_path=target,
        _disposition_bytes=payload,
    )


def require_definite_pre_submission_failure(
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
    failure: FormalPreSubmissionFailure,
) -> FormalPreSubmissionFailure:
    require_formal_look_claim(candidate, authority, claim)
    if type(failure) is not FormalPreSubmissionFailure:
        raise FormalRunProtocolError("pre-submission failure type changed")
    if type(claim.attempt_ordinal) is not int:
        raise FormalRunProtocolError("formal attempt ordinal changed")
    expected_path = _retry_attempt_path(
        authority.claim_directory,
        _RETRY_ATTEMPT_FAILURE_TEMPLATE,
        claim.attempt_ordinal,
    )
    if failure.failure_path != expected_path:
        raise FormalRunProtocolError("pre-submission failure path changed")
    expected = _canonical_bytes(
        _retry_attempt_failure_document(
            candidate,
            authority,
            claim,
            phase=failure.phase,
            failure_class=failure.failure_class,
            recorded_at_utc=failure.recorded_at_utc,
        )
    )
    payload = _read_private_regular(
        failure.failure_path,
        maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
        name="formal pre-submission failure",
    )
    raw = _strict_json_object(expected, "formal pre-submission failure")
    if (
        payload != expected
        or payload != failure._failure_bytes
        or failure.failure_id != raw["failure_id"]
        or failure.failure_sha256 != raw["failure_sha256"]
        or failure.claim_id != claim.claim_id
        or failure.claim_sha256 != claim.claim_sha256
        or failure.authority_id != authority.authority_id
        or failure.candidate_id != candidate.candidate_id
        or failure.candidate_sha256 != candidate.candidate_sha256
        or failure.attempt_ordinal != claim.attempt_ordinal
        or failure.retry_lineage_sha256 != claim.retry_lineage_sha256
        or failure.outcome_look_consumed is not False
        or failure.retry_with_fresh_attempt_authorized is not True
    ):
        raise FormalRunProtocolError("pre-submission failure changed")
    return failure


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
        waived = _uses_owner_review_waiver(authority)
        if waived:
            if type(claim.attempt_ordinal) is not int:
                raise FormalRunProtocolError("formal submission attempt changed")
            expected_path = _retry_attempt_path(
                authority.claim_directory,
                _RETRY_ATTEMPT_PERMIT_TEMPLATE,
                claim.attempt_ordinal,
            )
        else:
            expected_path = authority.claim_directory / SUBMISSION_PERMIT_FILENAME
        if permit.permit_path != expected_path:
            raise FormalRunProtocolError("formal submission permit path changed")
        payload = _read_private_regular(
            permit.permit_path,
            maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
            name="formal submission permit",
        )
        if waived:
            expected = _canonical_bytes(
                _retry_attempt_permit_document(
                    candidate,
                    authority,
                    claim,
                    submission_started_at_utc=permit.submission_started_at_utc,
                    consumption_reason=permit.consumption_reason,
                )
            )
        else:
            expected = _canonical_bytes(
                _submission_permit_document(
                    candidate,
                    authority,
                    claim,
                    submission_started_at_utc=permit.submission_started_at_utc,
                )
            )
        raw = _strict_json_object(expected, "formal submission permit")
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
        or permit.submission_attempt_count
        != (int(raw["submission_attempt_count"]))
        or permit.ambiguous_submission_consumes_look is not True
        or permit.retry_authorized is not False
        or permit.attempt_ordinal != claim.attempt_ordinal
        or permit.retry_lineage_sha256 != claim.retry_lineage_sha256
        or (
            waived
            and permit.consumption_reason
            not in {"backtests_create_attempt", "external_state_ambiguous"}
        )
        or (
            not waived
            and permit.consumption_reason != "legacy_pre_network_one_shot"
        )
    ):
        raise FormalRunProtocolError("formal submission permit changed")
    return permit


def load_consumed_formal_retry_attempt(
    *,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    attempt_ordinal: int,
    retry_lineage_sha256: str,
    submission_plan_id: str,
    submission_plan_sha256: str,
) -> tuple[FormalLookClaim, FormalSubmissionPermit]:
    """Reauthenticate one consumed owner-waived attempt after process loss.

    This loader mints no submission, status, or result capability.  It accepts
    only the exact immutable claim and ``backtests_create_attempt`` permit.  An
    external-state ambiguity, a no-outcome failure, or a missing permit remains
    locked rather than being interpreted as evidence that no run exists.
    """

    require_reviewed_formal_run_authority(candidate, authority)
    if not _uses_owner_review_waiver(authority):
        raise FormalRunProtocolError(
            "formal retry recovery requires the owner-review waiver"
        )
    _require_count(attempt_ordinal, "attempt_ordinal", minimum=1)
    if attempt_ordinal > 999_999:
        raise FormalRunProtocolError("attempt_ordinal exceeds its fixed bound")
    retry_lineage_sha256 = _require_sha256(
        retry_lineage_sha256,
        "retry lineage",
    )
    submission_plan_id = _require_id(
        submission_plan_id,
        "formal submission plan",
    )
    submission_plan_sha256 = _require_sha256(
        submission_plan_sha256,
        "formal submission plan",
    )
    directory = _require_private_directory(authority.claim_directory)
    prior, consumed, no_outcome = _retry_attempt_terminal_census(
        directory=directory,
        candidate=candidate,
        authority=authority,
        retry_lineage_sha256=retry_lineage_sha256,
        submission_plan_id=submission_plan_id,
        submission_plan_sha256=submission_plan_sha256,
        next_attempt_ordinal=attempt_ordinal,
    )
    claim_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_CLAIM_TEMPLATE,
        attempt_ordinal,
    )
    claim_payload = _read_private_regular(
        claim_path,
        maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
        name="recoverable formal retry claim",
    )
    claim_raw = _strict_json_object(
        claim_payload,
        "recoverable formal retry claim",
    )
    expected_claim = _retry_attempt_claim_document(
        candidate,
        authority,
        attempt_ordinal=attempt_ordinal,
        retry_lineage_sha256=retry_lineage_sha256,
        submission_plan_id=submission_plan_id,
        submission_plan_sha256=submission_plan_sha256,
        claimed_at_utc=claim_raw.get("claimed_at_utc"),
        prior_attempt_count=prior,
        prior_consumed_attempt_count=consumed,
        prior_no_outcome_failure_count=no_outcome,
    )
    if claim_raw != expected_claim:
        raise FormalRunProtocolError(
            "recoverable formal retry claim changed lineage or plan"
        )
    claim = FormalLookClaim(
        claim_id=str(expected_claim["claim_id"]),
        claim_sha256=str(expected_claim["claim_sha256"]),
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        claimed_at_utc=str(expected_claim["claimed_at_utc"]),
        maximum_submissions=1,
        submission_count_reserved=0,
        ambiguous_submission_consumes_look=True,
        retry_authorized=True,
        claim_path=claim_path,
        _claim_bytes=claim_payload,
        attempt_ordinal=attempt_ordinal,
        retry_lineage_sha256=retry_lineage_sha256,
        outcome_look_consumed=False,
        submission_plan_id=submission_plan_id,
        submission_plan_sha256=submission_plan_sha256,
        resumed_after_interruption=True,
    )
    failure_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_FAILURE_TEMPLATE,
        attempt_ordinal,
    )
    permit_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_PERMIT_TEMPLATE,
        attempt_ordinal,
    )
    if failure_path.exists():
        raise FormalRunProtocolError(
            "no-outcome formal attempt has no consumed run to recover"
        )
    permit_payload = _read_private_regular(
        permit_path,
        maximum_bytes=MAX_REVIEW_RECEIPT_BYTES,
        name="recoverable formal submission permit",
    )
    permit_raw = _strict_json_object(
        permit_payload,
        "recoverable formal submission permit",
    )
    expected_permit = _retry_attempt_permit_document(
        candidate,
        authority,
        claim,
        submission_started_at_utc=permit_raw.get("submission_started_at_utc"),
        consumption_reason=permit_raw.get("consumption_reason"),
    )
    if permit_raw != expected_permit:
        raise FormalRunProtocolError(
            "recoverable formal submission permit changed"
        )
    if permit_raw["consumption_reason"] != "backtests_create_attempt":
        raise FormalRunProtocolError(
            "external-state ambiguity has no recoverable exact QC run"
        )
    success_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_SUCCESS_TEMPLATE,
        attempt_ordinal,
    )
    terminal_failure_path = _retry_attempt_path(
        directory,
        _RETRY_ATTEMPT_TERMINAL_FAILURE_TEMPLATE,
        attempt_ordinal,
    )
    if success_path.exists() and terminal_failure_path.exists():
        raise FormalRunProtocolError(
            "recoverable formal attempt has conflicting terminal dispositions"
        )
    permit = FormalSubmissionPermit(
        permit_id=str(expected_permit["permit_id"]),
        permit_sha256=str(expected_permit["permit_sha256"]),
        claim_id=claim.claim_id,
        claim_sha256=claim.claim_sha256,
        authority_id=authority.authority_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        submission_started_at_utc=str(
            expected_permit["submission_started_at_utc"]
        ),
        maximum_submissions=1,
        submission_attempt_count=1,
        ambiguous_submission_consumes_look=True,
        retry_authorized=False,
        permit_path=permit_path,
        _permit_bytes=permit_payload,
        attempt_ordinal=attempt_ordinal,
        retry_lineage_sha256=retry_lineage_sha256,
        consumption_reason="backtests_create_attempt",
    )
    require_formal_submission_permit(candidate, authority, claim, permit)
    return claim, permit


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
            "owner_review_waiver_variant_available": True,
            "owner_review_waiver": formal_owner_review_waiver_record(),
            "owner_standing_retry_policy": formal_retry_policy_record(),
            "infrastructure_look_ledger_bound_in_review_authority": True,
            "infrastructure_look_ledger_reauthenticated_before_claim": True,
            "submission_permit_filename": SUBMISSION_PERMIT_FILENAME,
            "maximum_submissions": 1,
            "ambiguous_submission_consumes_look": True,
            "retry_after_ambiguity": False,
            "owner_waiver_fresh_attempt_after_counted_ambiguity": True,
            "same_attempt_reuse_or_deletion_authorized": False,
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
    "FormalPreSubmissionFailure",
    "FormalRunCandidate",
    "FormalRunProtocolError",
    "FormalSubmissionPermit",
    "FormalSuccessfulCompletion",
    "HORIZONS",
    "OWNER_DECISION_ID",
    "OWNER_REVIEW_WAIVER_BASIS",
    "OWNER_REVIEW_WAIVER_DISPOSITION",
    "OWNER_REVIEW_WAIVER_ID",
    "OWNER_REVIEW_WAIVER_SCOPE",
    "OWNER_WAIVER_EXTERNAL_PIN_SCHEMA",
    "OWNER_WAIVER_RECEIPT_SCHEMA",
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
    "formal_owner_review_waiver_record",
    "formal_independent_review_record",
    "formal_retry_policy_record",
    "formal_review_authorization_record",
    "formal_run_protocol_record",
    "load_consumed_formal_retry_attempt",
    "load_reviewed_formal_run_authority",
    "load_external_review_pin",
    "render_external_review_pin_candidate",
    "render_formal_review_receipt_candidate",
    "render_formal_owner_review_waiver_receipt_candidate",
    "render_formal_run_candidate_bytes",
    "render_owner_review_waiver_external_pin_candidate",
    "record_definite_pre_submission_failure",
    "require_definite_pre_submission_failure",
    "require_formal_look_claim",
    "require_formal_run_candidate",
    "require_formal_submission_permit",
    "require_external_review_pin",
    "require_reviewed_formal_run_authority",
]
