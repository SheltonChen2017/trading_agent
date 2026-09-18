"""One-use QuantConnect adapter for the outcome-free PIT coverage probe.

The adapter can create one private project, upload the exact reviewed plan and
source projection, compile once, and launch once.  Status inspection requests
``includeStatistics=False``.  A separately permitted ``backtests/read`` then
selects exactly one bounded count-and-availability attestation.  The full
receipt and terminal pointer remain in QuantConnect; returns, prices, orders,
raw rows, identifiers, weights, and market-cap values are never selected.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
import threading
import time
import weakref
from datetime import datetime
from pathlib import Path

from . import formal_submission_adapter as formal
from .formal_qc_transport import FormalQcTransport
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_preopen_execution_owner_signature,
)
from .pit_market_cap_membership_probe import (
    ATTESTATION_SCHEMA,
    BACKTEST_NAME,
    CONTRACT_SHA256,
    MAX_SUMMARY_CHARACTERS,
    PROJECT_NAME,
    RUNTIME_PATH,
    SUMMARY_NAME,
    PitMarketCapMembershipProbeQcProjection,
    PitMarketCapMembershipCoverageNamedRefusal,
    ReviewedPitMarketCapMembershipCoverageAttestation,
    build_pit_market_cap_membership_probe_qc_projection,
    load_reviewed_pit_market_cap_membership_coverage_attestation,
    require_pit_market_cap_membership_probe_qc_projection,
)


class PitMarketCapMembershipProbeSubmissionError(ValueError):
    """A local authority, projection, or bounded QC response is invalid."""


class PitMarketCapMembershipProbeSubmissionLocked(RuntimeError):
    """A durable one-use permission was spent and external state is final/ambiguous."""


REVIEW_FILENAME = "arv2-pit-market-cap-membership-probe-review-v1.json"
PERMIT_FILENAME = "arv2-pit-market-cap-membership-probe-permit-v1.json"
OUTPUT_READ_PERMIT_FILENAME = (
    "arv2-pit-market-cap-membership-probe-summary-read-permit-v2.json"
)
PLAN_SCHEMA = "arv2-pit-market-cap-membership-probe-submission-plan-v1"
REVIEW_SCHEMA = "arv2-pit-market-cap-membership-probe-review-v1"
EXECUTION_AUTHORITY_SCHEMA = (
    "arv2-pit-market-cap-membership-probe-execution-authority-v1"
)
PERMIT_SCHEMA = "arv2-pit-market-cap-membership-probe-permit-v1"
OUTPUT_READ_PERMIT_SCHEMA = (
    "arv2-pit-market-cap-membership-probe-summary-read-permit-v2"
)
LAUNCH_SCHEMA = "arv2-pit-market-cap-membership-probe-launch-v1"
TERMINAL_SCHEMA = "arv2-pit-market-cap-membership-probe-terminal-status-v1"
LAUNCH_RECEIPT_FILENAME = "arv2-pit-market-cap-membership-probe-launch-v1.json"
TERMINAL_RECEIPT_FILENAME = (
    "arv2-pit-market-cap-membership-probe-terminal-status-v1.json"
)
PERSISTED_ATTESTATION_FILENAME = (
    "arv2-pit-market-cap-membership-probe-coverage-attestation-v2.json"
)
MAX_CONTROL_BYTES = 1024 * 1024
COMPILE_POLLS = 120
STATUS_POLLS = 240
COMPILE_POLL_SECONDS = 2
STATUS_POLL_SECONDS = 30
QC_DEFAULT_RESEARCH_NOTEBOOK_PATH = "research.ipynb"
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+ /-]{0,255}")
_RUNTIME_CONTRACT_MARKER = (
    b"__ARV2_PIT_MARKET_CAP_MEMBERSHIP_CONTRACT_SHA256__"
)


@dataclasses.dataclass(frozen=True, slots=True)
class PitMarketCapMembershipProbeSubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    project_name: str
    backtest_name: str
    projection_id: str
    projection_sha256: str
    plan_object_store_key: str
    terminal_pointer_key: str
    project_source_set_sha256: str
    review_directory: Path
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    include_statistics: bool
    outcome_access_authorized: bool
    price_or_return_access_authorized: bool
    orders_or_portfolio_actions_authorized: bool
    projection: PitMarketCapMembershipProbeQcProjection = dataclasses.field(
        repr=False
    )


@dataclasses.dataclass(frozen=True, slots=True)
class PitMarketCapMembershipProbeReviewClaim:
    claim_id: str
    claim_sha256: str
    plan_id: str
    plan_sha256: str
    pin_path: Path
    pin_sha256: str
    pin_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class PitMarketCapMembershipProbeSubmissionPermit:
    permit_id: str
    permit_sha256: str
    plan_sha256: str
    claim_sha256: str
    owner_authority_sha256: str
    started_at_utc: str
    permit_path: Path
    permit_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PitMarketCapMembershipProbeLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    permit_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PitMarketCapMembershipProbeTerminalStatus:
    receipt_id: str
    receipt_sha256: str
    launch_sha256: str
    project_id: int
    backtest_id: str
    status: str
    poll_count: int
    include_statistics: bool
    result_values_selected_or_inspected: bool


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "control value is not canonical JSON"
        ) from exc


def _safe_text(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise PitMarketCapMembershipProbeSubmissionError(f"{name} changed")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise PitMarketCapMembershipProbeSubmissionError(f"{name} changed")
    return value


def _utc(value: object) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise PitMarketCapMembershipProbeSubmissionError(
            "timestamp must be exact UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "timestamp must be exact UTC text"
        ) from exc
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise PitMarketCapMembershipProbeSubmissionError(
            "timestamp must be canonical UTC text"
        )
    return value


def _private_directory(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise PitMarketCapMembershipProbeSubmissionError(
            "review directory must be an absolute Path"
        )
    try:
        info = path.lstat()
    except OSError as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "review directory is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "review directory must be owner-only and non-symlinked"
        )
    return path


def _read_private(path: Path, maximum: int) -> bytes:
    try:
        before = path.lstat()
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "private control file is unavailable"
        ) from exc
    if (
        any(
            getattr(before, field) != getattr(after, field)
            for field in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        )
        or not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or not 0 < len(payload) <= maximum
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "private control file changed"
        )
    return payload


def _write_private_once(path: Path, payload: bytes) -> None:
    parent = _private_directory(path.parent)
    descriptor = None
    parent_descriptor = None
    try:
        parent_descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        descriptor = os.open(
            path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short private write")
        os.fsync(descriptor)
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise PitMarketCapMembershipProbeSubmissionLocked(
            "one-use permission is already spent or publication is ambiguous"
        ) from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if parent_descriptor is not None:
            try:
                os.close(parent_descriptor)
            except OSError:
                pass


def _source_record(source: object) -> dict[str, object]:
    try:
        record = source.to_record()
    except (AttributeError, TypeError, ValueError) as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "project source descriptor changed"
        ) from exc
    if type(record) is not dict:
        raise PitMarketCapMembershipProbeSubmissionError(
            "project source descriptor changed"
        )
    return record


def _source_text(source: object) -> str:
    content = getattr(source, "content", None)
    if type(content) is not bytes:
        raise PitMarketCapMembershipProbeSubmissionError(
            "project source content must be exact bytes"
        )
    try:
        text = content.decode("ascii")
    except UnicodeError as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "project source content must be exact ASCII"
        ) from exc
    if (
        getattr(source, "project_path", None) is None
        or getattr(source, "character_count", None) != len(text)
        or getattr(source, "byte_count", None) != len(content)
        or getattr(source, "content_sha256", None)
        != hashlib.sha256(content).hexdigest()
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "project source content changed"
        )
    return text


def _plan_record(value: PitMarketCapMembershipProbeSubmissionPlan) -> dict[str, object]:
    return {
        "schema": PLAN_SCHEMA,
        "organization_id_sha256": hashlib.sha256(
            value.organization_id.encode("utf-8")
        ).hexdigest(),
        "project_name": value.project_name,
        "backtest_name": value.backtest_name,
        "projection_id": value.projection_id,
        "projection_sha256": value.projection_sha256,
        "plan_object_store_key": value.plan_object_store_key,
        "terminal_pointer_key": value.terminal_pointer_key,
        "project_source_set_sha256": value.project_source_set_sha256,
        "source_files": [_source_record(item) for item in value.projection.source_files],
        "review_directory": str(value.review_directory),
        "compile_poll_limit": value.compile_poll_limit,
        "status_poll_limit": value.status_poll_limit,
        "maximum_backtest_submissions": value.maximum_backtest_submissions,
        "include_statistics": value.include_statistics,
        "outcome_access_authorized": value.outcome_access_authorized,
        "price_or_return_access_authorized": value.price_or_return_access_authorized,
        "orders_or_portfolio_actions_authorized": (
            value.orders_or_portfolio_actions_authorized
        ),
    }


def _rebuild_projection(value):
    projection = require_pit_market_cap_membership_probe_qc_projection(value)
    matches = tuple(
        source
        for source in projection.source_files
        if source.project_path == RUNTIME_PATH
    )
    contract_bytes = CONTRACT_SHA256.encode("ascii")
    if (
        len(matches) != 1
        or matches[0].content.count(contract_bytes) != 1
        or _RUNTIME_CONTRACT_MARKER in matches[0].content
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe runtime projection changed"
        )
    runtime_template = matches[0].content.replace(
        contract_bytes, _RUNTIME_CONTRACT_MARKER
    )
    rebuilt = build_pit_market_cap_membership_probe_qc_projection(
        plan_bytes=projection.plan_bytes,
        runtime_source_bytes=runtime_template,
    )
    if rebuilt != projection:
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe source projection is not reproducible"
        )
    return projection


def build_pit_market_cap_membership_probe_submission_plan(
    *,
    projection: PitMarketCapMembershipProbeQcProjection,
    organization_id: str,
    review_directory: Path,
) -> PitMarketCapMembershipProbeSubmissionPlan:
    projection = _rebuild_projection(projection)
    _safe_text(organization_id, "organization id")
    _private_directory(review_directory)
    placeholder = object.__new__(PitMarketCapMembershipProbeSubmissionPlan)
    values = {
        "plan_id": "",
        "plan_sha256": "",
        "organization_id": organization_id,
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "plan_object_store_key": projection.plan_object_store_key,
        "terminal_pointer_key": projection.terminal_pointer_key,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "review_directory": review_directory,
        "compile_poll_limit": COMPILE_POLLS,
        "status_poll_limit": STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "include_statistics": False,
        "outcome_access_authorized": False,
        "price_or_return_access_authorized": False,
        "orders_or_portfolio_actions_authorized": False,
        "projection": projection,
    }
    for name, item in values.items():
        object.__setattr__(placeholder, name, item)
    digest = hashlib.sha256(_canonical(_plan_record(placeholder))).hexdigest()
    object.__setattr__(
        placeholder,
        "plan_id",
        f"arv2-pit-market-cap-membership-probe-plan-{digest[:24]}",
    )
    object.__setattr__(placeholder, "plan_sha256", digest)
    return require_pit_market_cap_membership_probe_submission_plan(placeholder)


def require_pit_market_cap_membership_probe_submission_plan(value):
    if type(value) is not PitMarketCapMembershipProbeSubmissionPlan:
        raise PitMarketCapMembershipProbeSubmissionError(
            "exact probe submission plan required"
        )
    projection = _rebuild_projection(value.projection)
    _private_directory(value.review_directory)
    digest = hashlib.sha256(_canonical(_plan_record(value))).hexdigest()
    if (
        value.plan_id
        != f"arv2-pit-market-cap-membership-probe-plan-{digest[:24]}"
        or value.plan_sha256 != digest
        or value.project_name != PROJECT_NAME
        or value.backtest_name != BACKTEST_NAME
        or value.project_name != projection.project_name
        or value.backtest_name != projection.backtest_name
        or value.projection_id != projection.projection_id
        or value.projection_sha256 != projection.projection_sha256
        or value.plan_object_store_key != projection.plan_object_store_key
        or value.terminal_pointer_key != projection.terminal_pointer_key
        or value.project_source_set_sha256
        != projection.project_source_set_sha256
        or value.maximum_backtest_submissions != 1
        or value.include_statistics is not False
        or value.outcome_access_authorized is not False
        or value.price_or_return_access_authorized is not False
        or value.orders_or_portfolio_actions_authorized is not False
        or type(value.compile_poll_limit) is not int
        or value.compile_poll_limit != COMPILE_POLLS
        or type(value.status_poll_limit) is not int
        or value.status_poll_limit != STATUS_POLLS
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe submission plan changed"
        )
    if type(projection.plan_bytes) is not bytes or not projection.plan_bytes:
        raise PitMarketCapMembershipProbeSubmissionError("probe plan bytes changed")
    for source in projection.source_files:
        _source_text(source)
    return value


def _claim_document(plan) -> dict[str, object]:
    require_pit_market_cap_membership_probe_submission_plan(plan)
    seed = {
        "schema": REVIEW_SCHEMA,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "project_source_set_sha256": plan.project_source_set_sha256,
        "review_disposition": "OWNER_DIRECTED_PREREVIEW_DIAGNOSTIC_WAIVER",
        "independent_review_complete": False,
        "owner_directed_prereview_diagnostic": True,
        "maximum_backtest_submissions": 1,
        "outcome_access": False,
        "price_or_return_access": False,
        "orders_or_portfolio_actions": False,
        "retry_after_ambiguity": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    return {
        **seed,
        "claim_id": f"arv2-pit-market-cap-membership-probe-review-{digest[:24]}",
        "claim_sha256": digest,
    }


def render_pit_market_cap_membership_probe_review_claim_candidate(plan) -> bytes:
    return _canonical(_claim_document(plan))


def load_pit_market_cap_membership_probe_review_claim(plan):
    expected = render_pit_market_cap_membership_probe_review_claim_candidate(plan)
    path = plan.review_directory / REVIEW_FILENAME
    payload = _read_private(path, MAX_CONTROL_BYTES)
    if payload != expected:
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe review claim changed"
        )
    raw = _claim_document(plan)
    return PitMarketCapMembershipProbeReviewClaim(
        claim_id=raw["claim_id"],
        claim_sha256=raw["claim_sha256"],
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        pin_path=path,
        pin_sha256=hashlib.sha256(payload).hexdigest(),
        pin_bytes=payload,
    )


def require_pit_market_cap_membership_probe_review_claim(value, plan):
    if (
        type(value) is not PitMarketCapMembershipProbeReviewClaim
        or value != load_pit_market_cap_membership_probe_review_claim(plan)
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "exact probe review claim required"
        )
    return value


def render_pit_market_cap_membership_probe_execution_authority_candidate(
    plan, review_claim
) -> bytes:
    require_pit_market_cap_membership_probe_submission_plan(plan)
    require_pit_market_cap_membership_probe_review_claim(review_claim, plan)
    return _canonical(
        {
            "schema": EXECUTION_AUTHORITY_SCHEMA,
            "gate": "PREOPEN_EXECUTION",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "claim_id": review_claim.claim_id,
            "claim_sha256": review_claim.claim_sha256,
            "review_pin_sha256": review_claim.pin_sha256,
            "project_name": plan.project_name,
            "backtest_name": plan.backtest_name,
            "projection_id": plan.projection_id,
            "projection_sha256": plan.projection_sha256,
            "project_source_set_sha256": plan.project_source_set_sha256,
            "terminal_pointer_key": plan.terminal_pointer_key,
            "actions": [
                "authenticate",
                "projects/read",
                "projects/create_once",
                "object/set_exact_plan",
                "object/properties_exact_plan",
                "files/delete_exact_new_project_default_research_notebook_once",
                "files/create_or_update_exact_projected_sources",
                "files/read_exact_source_readback",
                "compile/create_once",
                "compile/read_status_only",
                "backtests/create_once",
                "backtests/list_includeStatistics_false",
                "backtests/read_exact_aggregate_attestation_once",
                "persist_exact_validated_attestation_only",
            ],
            "maximum_backtest_submissions": 1,
            "maximum_backtests_read_calls": 1,
            "selected_summary_statistic": SUMMARY_NAME,
            "include_statistics": False,
            "backtests_read": True,
            "object_store_export": False,
            "outcome_access": False,
            "price_or_return_access": False,
            "orders_or_portfolio_actions": False,
            "retry_after_ambiguity": False,
        }
    )


def _require_owner_signature(plan, claim, owner_signature):
    payload = render_pit_market_cap_membership_probe_execution_authority_candidate(
        plan, claim
    )
    try:
        return require_preopen_execution_owner_signature(
            owner_signature, authority_payload=payload
        )
    except (OwnerSignatureAuthorityError, TypeError) as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "distinct owner PREOPEN execution signature is unavailable"
        ) from exc


def _submission_permit_candidate(plan, claim, owner_signature, started_at_utc):
    _utc(started_at_utc)
    seed = {
        "schema": PERMIT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "claim_sha256": claim.claim_sha256,
        "owner_authority_sha256": owner_signature.authority_sha256,
        "started_at_utc": started_at_utc,
        "attempt_count": 1,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    raw = {
        **seed,
        "permit_id": f"arv2-pit-market-cap-membership-probe-permit-{digest[:24]}",
        "permit_sha256": digest,
    }
    payload = _canonical(raw)
    path = plan.review_directory / PERMIT_FILENAME
    return PitMarketCapMembershipProbeSubmissionPermit(
        permit_id=raw["permit_id"],
        permit_sha256=digest,
        plan_sha256=plan.plan_sha256,
        claim_sha256=claim.claim_sha256,
        owner_authority_sha256=owner_signature.authority_sha256,
        started_at_utc=started_at_utc,
        permit_path=path,
        permit_bytes=payload,
    )


def _spend_submission_permit(value):
    _write_private_once(value.permit_path, value.permit_bytes)
    return value


def require_pit_market_cap_membership_probe_submission_permit(
    value, *, plan, review_claim, owner_signature
):
    require_pit_market_cap_membership_probe_submission_plan(plan)
    require_pit_market_cap_membership_probe_review_claim(review_claim, plan)
    _require_owner_signature(plan, review_claim, owner_signature)
    if type(value) is not PitMarketCapMembershipProbeSubmissionPermit:
        raise PitMarketCapMembershipProbeSubmissionError(
            "exact probe submission permit required"
        )
    _utc(value.started_at_utc)
    seed = {
        "schema": PERMIT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "claim_sha256": review_claim.claim_sha256,
        "owner_authority_sha256": owner_signature.authority_sha256,
        "started_at_utc": value.started_at_utc,
        "attempt_count": 1,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    expected = _canonical(
        {
            **seed,
            "permit_id": (
                f"arv2-pit-market-cap-membership-probe-permit-{digest[:24]}"
            ),
            "permit_sha256": digest,
        }
    )
    if (
        value.permit_id
        != f"arv2-pit-market-cap-membership-probe-permit-{digest[:24]}"
        or value.permit_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.claim_sha256 != review_claim.claim_sha256
        or value.owner_authority_sha256 != owner_signature.authority_sha256
        or value.permit_path != plan.review_directory / PERMIT_FILENAME
        or value.permit_bytes != expected
        or _read_private(value.permit_path, MAX_CONTROL_BYTES) != expected
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe submission permit changed"
        )
    return value


def load_pit_market_cap_membership_probe_submission_permit(
    *, plan, review_claim, owner_signature
):
    """Reload the durable submission permission for interruption recovery."""

    require_pit_market_cap_membership_probe_submission_plan(plan)
    require_pit_market_cap_membership_probe_review_claim(review_claim, plan)
    _require_owner_signature(plan, review_claim, owner_signature)
    path = plan.review_directory / PERMIT_FILENAME
    payload = _read_private(path, MAX_CONTROL_BYTES)
    raw = _control_json_object(payload, "persisted probe submission permit")
    expected_keys = {
        "schema",
        "plan_sha256",
        "claim_sha256",
        "owner_authority_sha256",
        "started_at_utc",
        "attempt_count",
        "retry_authorized",
        "permit_id",
        "permit_sha256",
    }
    if set(raw) != expected_keys or raw.get("schema") != PERMIT_SCHEMA:
        raise PitMarketCapMembershipProbeSubmissionError(
            "persisted probe submission permit changed"
        )
    value = PitMarketCapMembershipProbeSubmissionPermit(
        permit_id=raw["permit_id"],
        permit_sha256=raw["permit_sha256"],
        plan_sha256=raw["plan_sha256"],
        claim_sha256=raw["claim_sha256"],
        owner_authority_sha256=raw["owner_authority_sha256"],
        started_at_utc=raw["started_at_utc"],
        permit_path=path,
        permit_bytes=payload,
    )
    return require_pit_market_cap_membership_probe_submission_permit(
        value,
        plan=plan,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )


def _record_launch(value):
    return {
        "plan_sha256": value.plan_sha256,
        "permit_sha256": value.permit_sha256,
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
    }


def _record_terminal(value):
    return {
        "launch_sha256": value.launch_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "status": value.status,
        "poll_count": value.poll_count,
        "include_statistics": value.include_statistics,
        "result_values_selected_or_inspected": (
            value.result_values_selected_or_inspected
        ),
    }


def _control_json_object(payload: bytes, name: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            f"{name} is not JSON"
        ) from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise PitMarketCapMembershipProbeSubmissionError(
            f"{name} is not canonical JSON"
        )
    return value


def _persist_launch_receipt(plan, value) -> None:
    _write_private_once(
        plan.review_directory / LAUNCH_RECEIPT_FILENAME,
        _canonical(
            {
                "schema": LAUNCH_SCHEMA,
                "receipt_id": value.receipt_id,
                "receipt_sha256": value.receipt_sha256,
                **_record_launch(value),
            }
        ),
    )


def _persist_terminal_receipt(plan, value) -> None:
    _write_private_once(
        plan.review_directory / TERMINAL_RECEIPT_FILENAME,
        _canonical(
            {
                "schema": TERMINAL_SCHEMA,
                "receipt_id": value.receipt_id,
                "receipt_sha256": value.receipt_sha256,
                **_record_terminal(value),
            }
        ),
    )


def _make_return_authority():
    pid = os.getpid()
    lock = threading.RLock()
    launch_entries: dict[int, tuple[object, ...]] = {}
    terminal_entries: dict[int, tuple[object, ...]] = {}

    def store(registry, value, *lineage):
        identity = id(value)
        reference = weakref.ref(
            value, lambda _ref, key=identity: registry.pop(key, None)
        )
        with lock:
            registry[identity] = (reference, *lineage, pid)

    def current(registry, value):
        with lock:
            entry = registry.get(id(value))
            if (
                os.getpid() != pid
                or entry is None
                or entry[0]() is not value
            ):
                registry.pop(id(value), None)
                return None
            return entry

    return (
        lambda value, *lineage: store(launch_entries, value, *lineage),
        lambda value: current(launch_entries, value),
        lambda value, *lineage: store(terminal_entries, value, *lineage),
        lambda value: current(terminal_entries, value),
    )


(
    _register_launch,
    _current_launch,
    _register_terminal,
    _current_terminal,
) = _make_return_authority()


def require_pit_market_cap_membership_probe_launch_receipt(
    value, *, plan, permit, review_claim, owner_signature
):
    require_pit_market_cap_membership_probe_submission_permit(
        permit,
        plan=plan,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    entry = _current_launch(value)
    if (
        type(value) is not PitMarketCapMembershipProbeLaunchReceipt
        or entry is None
        or entry[0]() is not value
        or entry[1] is not plan
        or entry[2] is not permit
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe launch lacks process-return authority"
        )
    seed = _record_launch(value)
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.receipt_id
        != f"arv2-pit-market-cap-membership-probe-launch-{digest[:24]}"
        or value.receipt_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or type(value.project_id) is not int
        or value.project_id <= 0
        or value.backtest_name != plan.backtest_name
    ):
        raise PitMarketCapMembershipProbeSubmissionError("probe launch changed")
    _safe_text(value.compile_id, "compile id")
    _safe_text(value.backtest_id, "backtest id")
    _safe_text(value.initial_status, "initial status")
    return value


def require_pit_market_cap_membership_probe_terminal_status(
    value, *, plan, permit, launch, review_claim, owner_signature
):
    require_pit_market_cap_membership_probe_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    entry = _current_terminal(value)
    if (
        type(value) is not PitMarketCapMembershipProbeTerminalStatus
        or entry is None
        or entry[0]() is not value
        or entry[1] is not plan
        or entry[2] is not permit
        or entry[3] is not launch
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe terminal status lacks process-return authority"
        )
    seed = _record_terminal(value)
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.receipt_id
        != f"arv2-pit-market-cap-membership-probe-terminal-{digest[:24]}"
        or value.receipt_sha256 != digest
        or value.launch_sha256 != launch.receipt_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or type(value.poll_count) is not int
        or not 1 <= value.poll_count <= plan.status_poll_limit
        or value.include_statistics is not False
        or value.result_values_selected_or_inspected is not False
        or value.status not in formal.BACKTEST_TERMINAL_STATUSES
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe terminal status changed"
        )
    return value


def load_pit_market_cap_membership_probe_launch_receipt(
    *, plan, permit, review_claim, owner_signature
):
    """Reload the exact durable launch identity after a process interruption."""

    require_pit_market_cap_membership_probe_submission_permit(
        permit,
        plan=plan,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    raw = _control_json_object(
        _read_private(
            plan.review_directory / LAUNCH_RECEIPT_FILENAME,
            MAX_CONTROL_BYTES,
        ),
        "persisted probe launch receipt",
    )
    expected_keys = {
        "schema",
        "receipt_id",
        "receipt_sha256",
        "plan_sha256",
        "permit_sha256",
        "project_id",
        "compile_id",
        "backtest_id",
        "backtest_name",
        "initial_status",
    }
    if set(raw) != expected_keys or raw.get("schema") != LAUNCH_SCHEMA:
        raise PitMarketCapMembershipProbeSubmissionError(
            "persisted probe launch receipt changed"
        )
    launch = PitMarketCapMembershipProbeLaunchReceipt(
        **{key: value for key, value in raw.items() if key != "schema"}
    )
    _register_launch(launch, plan, permit)
    return require_pit_market_cap_membership_probe_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )


def load_pit_market_cap_membership_probe_terminal_status(
    *, plan, permit, launch, review_claim, owner_signature
):
    """Reload the exact durable statistics-free terminal status."""

    require_pit_market_cap_membership_probe_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    raw = _control_json_object(
        _read_private(
            plan.review_directory / TERMINAL_RECEIPT_FILENAME,
            MAX_CONTROL_BYTES,
        ),
        "persisted probe terminal status",
    )
    expected_keys = {
        "schema",
        "receipt_id",
        "receipt_sha256",
        "launch_sha256",
        "project_id",
        "backtest_id",
        "status",
        "poll_count",
        "include_statistics",
        "result_values_selected_or_inspected",
    }
    if set(raw) != expected_keys or raw.get("schema") != TERMINAL_SCHEMA:
        raise PitMarketCapMembershipProbeSubmissionError(
            "persisted probe terminal status changed"
        )
    terminal = PitMarketCapMembershipProbeTerminalStatus(
        **{key: value for key, value in raw.items() if key != "schema"}
    )
    _register_terminal(terminal, plan, permit, launch)
    return require_pit_market_cap_membership_probe_terminal_status(
        terminal,
        plan=plan,
        permit=permit,
        launch=launch,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )


def _transport_call(client, capability, method, *args):
    return formal._transport_call(client, capability, method, *args)


def _upload_entry(plan):
    payload = plan.projection.plan_bytes
    return formal.FormalQcUploadEntry(
        role="probe_plan",
        object_store_key=plan.plan_object_store_key,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        content_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        byte_count=len(payload),
        payload=payload,
    )


def _execute_pit_market_cap_membership_probe_submission_once_impl(
    *, plan, review_claim, owner_signature, client, started_at_utc,
    _transport_capability_minter,
):
    require_pit_market_cap_membership_probe_submission_plan(plan)
    require_pit_market_cap_membership_probe_review_claim(review_claim, plan)
    _require_owner_signature(plan, review_claim, owner_signature)
    formal._require_concrete_transport(client)
    permit_candidate = _submission_permit_candidate(
        plan, review_claim, owner_signature, started_at_utc
    )
    try:
        capability = _transport_capability_minter(
            transport=client,
            scope="submission",
            binding_record={
                "schema": "arv2-pit-market-cap-membership-probe-submission-capability-v1",
                "plan_sha256": plan.plan_sha256,
                "claim_sha256": review_claim.claim_sha256,
                "permit_sha256": permit_candidate.permit_sha256,
            },
            call_budget={
                "authenticate": 1,
                "projects/read": 2,
                "projects/create": 1,
                "object/set": 1,
                "object/properties": 1,
                "files/read": 2,
                "files/create": len(plan.projection.source_files),
                # A fresh project can contain only the default main.py, so no
                # other reviewed source can consume an update permission.
                "files/update": 1,
                # QuantConnect also seeds this exact notebook in a fresh
                # Python project.  No other unprojected path may be deleted.
                "files/delete": 1,
                "compile/create": 1,
                "compile/read": plan.compile_poll_limit,
                "backtests/create": 1,
            },
        )
    except Exception as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe submission capability mint failed before permit spend"
        ) from exc
    permit = _spend_submission_permit(permit_candidate)
    try:
        require_pit_market_cap_membership_probe_submission_permit(
            permit,
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
        )
        _transport_call(client, capability, "_request_json", "authenticate", {})
        inventory = formal._read_project_inventory(
            _transport_call(
                client, capability, "_request_json", "projects/read", {}
            )
        )
        if any(
            type(item) is dict and item.get("name") == plan.project_name
            for item in inventory
        ):
            raise PitMarketCapMembershipProbeSubmissionError(
                "exact probe project already exists"
            )
        created = formal._created_project(
            _transport_call(
                client,
                capability,
                "_request_json",
                "projects/create",
                {"name": plan.project_name, "language": "Py"},
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(created["projectId"])
        exact = formal._read_project_inventory(
            _transport_call(
                client,
                capability,
                "_request_json",
                "projects/read",
                {"projectId": project_id},
            )
        )
        if len(exact) != 1:
            raise PitMarketCapMembershipProbeSubmissionError(
                "created probe project is ambiguous"
            )
        formal._project_record(
            exact[0],
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        upload = _upload_entry(plan)
        _transport_call(
            client,
            capability,
            "_set_object_multipart",
            plan.organization_id,
            upload.object_store_key,
            upload.payload,
        )
        formal._object_metadata_matches(
            _transport_call(
                client,
                capability,
                "_read_object_properties",
                plan.organization_id,
                upload.object_store_key,
            ),
            upload,
        )
        existing = formal._read_files(
            _transport_call(
                client,
                capability,
                "_request_json",
                "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        projected = {
            item.project_path: item for item in plan.projection.source_files
        }
        allowed_fresh_paths = {
            "main.py",
            QC_DEFAULT_RESEARCH_NOTEBOOK_PATH,
        }
        if set(existing) - allowed_fresh_paths:
            raise PitMarketCapMembershipProbeSubmissionError(
                "new probe project contains an unexpected source"
            )
        unexpected = set(existing) - set(projected)
        if QC_DEFAULT_RESEARCH_NOTEBOOK_PATH in unexpected:
            formal._success(
                _transport_call(
                    client,
                    capability,
                    "_request_json",
                    "files/delete",
                    {
                        "projectId": project_id,
                        "name": QC_DEFAULT_RESEARCH_NOTEBOOK_PATH,
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                "files/delete",
            )
        for path, source in projected.items():
            content = _source_text(source)
            endpoint = "files/update" if path in existing else "files/create"
            formal._success(
                _transport_call(
                    client,
                    capability,
                    "_request_json",
                    endpoint,
                    {"projectId": project_id, "name": path, "content": content},
                ),
                frozenset({"success", "errors", "messages"}),
                endpoint,
            )
        readback = formal._read_files(
            _transport_call(
                client,
                capability,
                "_request_json",
                "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        expected = {
            item.project_path: _source_text(item)
            for item in plan.projection.source_files
        }
        if readback != expected:
            raise PitMarketCapMembershipProbeSubmissionError(
                "probe source readback changed"
            )
        compile_id = formal._compile_id(
            _transport_call(
                client,
                capability,
                "_request_json",
                "compile/create",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = formal._compile_state(
                _transport_call(
                    client,
                    capability,
                    "_request_json",
                    "compile/read",
                    {"projectId": project_id, "compileId": compile_id},
                ),
                compile_id,
            )
            if compile_state in formal.COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise PitMarketCapMembershipProbeSubmissionError(
                    "probe compile polling exhausted"
                )
            time.sleep(COMPILE_POLL_SECONDS)
        if compile_state != "BuildSuccess":
            raise PitMarketCapMembershipProbeSubmissionError(
                "probe project did not compile"
            )
        backtest_id, initial_status = formal._created_backtest(
            _transport_call(
                client,
                capability,
                "_request_json",
                "backtests/create",
                {
                    "projectId": project_id,
                    "compileId": compile_id,
                    "backtestName": plan.backtest_name,
                },
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        seed = {
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "project_id": project_id,
            "compile_id": compile_id,
            "backtest_id": backtest_id,
            "backtest_name": plan.backtest_name,
            "initial_status": initial_status,
        }
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        launch = PitMarketCapMembershipProbeLaunchReceipt(
            receipt_id=(
                f"arv2-pit-market-cap-membership-probe-launch-{digest[:24]}"
            ),
            receipt_sha256=digest,
            **seed,
        )
        _persist_launch_receipt(plan, launch)
        _register_launch(launch, plan, permit)
        require_pit_market_cap_membership_probe_launch_receipt(
            launch,
            plan=plan,
            permit=permit,
            review_claim=review_claim,
            owner_signature=owner_signature,
        )
        return permit, launch
    except PitMarketCapMembershipProbeSubmissionLocked:
        raise
    except Exception as exc:
        raise PitMarketCapMembershipProbeSubmissionLocked(
            "probe submission became ambiguous; permit remains consumed"
        ) from exc


def _inspect_pit_market_cap_membership_probe_terminal_status_impl(
    *, plan, review_claim, owner_signature, permit, launch, client,
    _transport_capability_minter,
):
    require_pit_market_cap_membership_probe_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    capability = _transport_capability_minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-pit-market-cap-membership-probe-status-capability-v1",
            "launch_sha256": launch.receipt_sha256,
            "permit_sha256": permit.permit_sha256,
        },
        call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = formal.parse_statistics_free_backtest_list(
                _transport_call(
                    client,
                    capability,
                    "_request_json",
                    "backtests/list",
                    {
                        "projectId": launch.project_id,
                        "includeStatistics": False,
                    },
                ),
                expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise PitMarketCapMembershipProbeSubmissionLocked(
                "probe terminal-status read became ambiguous"
            ) from exc
        if status.status in formal.BACKTEST_TERMINAL_STATUSES:
            seed = {
                "launch_sha256": launch.receipt_sha256,
                "project_id": launch.project_id,
                "backtest_id": launch.backtest_id,
                "status": status.status,
                "poll_count": index + 1,
                "include_statistics": False,
                "result_values_selected_or_inspected": False,
            }
            digest = hashlib.sha256(_canonical(seed)).hexdigest()
            terminal = PitMarketCapMembershipProbeTerminalStatus(
                receipt_id=(
                    "arv2-pit-market-cap-membership-probe-terminal-"
                    + digest[:24]
                ),
                receipt_sha256=digest,
                **seed,
            )
            _persist_terminal_receipt(plan, terminal)
            _register_terminal(terminal, plan, permit, launch)
            return require_pit_market_cap_membership_probe_terminal_status(
                terminal,
                plan=plan,
                permit=permit,
                launch=launch,
                review_claim=review_claim,
                owner_signature=owner_signature,
            )
        if index + 1 == plan.status_poll_limit:
            raise PitMarketCapMembershipProbeSubmissionLocked(
                "probe terminal-status polling exhausted"
            )
        time.sleep(STATUS_POLL_SECONDS)
    raise AssertionError("unreachable probe status loop")


_BACKTEST_READ_TOP_KEYS = frozenset(
    {"success", "errors", "messages", "backtest"}
)
_BACKTEST_READ_RECORD_KEYS = frozenset(
    set(formal._BACKTEST_STATUS_KEYS)
    | set(formal._DISCARDED_BACKTEST_SUMMARY_KEYS)
    | {"statistics"}
)


def _bounded_string_list(value: object, name: str) -> None:
    if value is None:
        return
    if (
        type(value) is not list
        or len(value) > 64
        or any(type(item) is not str or len(item) > 2048 for item in value)
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            f"{name} response field changed"
        )


def _extract_attestation_summary_bytes(
    response: object,
    *,
    launch: PitMarketCapMembershipProbeLaunchReceipt,
) -> bytes:
    if (
        type(response) is not dict
        or not set(response).issubset(_BACKTEST_READ_TOP_KEYS)
        or response.get("success") is not True
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe backtests/read response changed"
        )
    _bounded_string_list(response.get("errors"), "errors")
    _bounded_string_list(response.get("messages"), "messages")
    backtest = response.get("backtest")
    if (
        type(backtest) is not dict
        or not set(backtest).issubset(_BACKTEST_READ_RECORD_KEYS)
        or backtest.get("projectId") != launch.project_id
        or backtest.get("backtestId") != launch.backtest_id
        or backtest.get("name") != launch.backtest_name
        or backtest.get("status") != "Completed."
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe backtests/read returned another run"
        )
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or any(
        type(key) is not str for key in statistics
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe backtests/read omitted summary statistics"
        )
    selected_names = tuple(
        sorted(key for key in statistics if key.startswith("ARV2_"))
    )
    if selected_names != (SUMMARY_NAME,):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe aggregate-attestation statistic inventory changed"
        )
    summary = statistics[SUMMARY_NAME]
    if (
        type(summary) is not str
        or not summary
        or len(summary) > MAX_SUMMARY_CHARACTERS
    ):
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe aggregate attestation exceeded its character bound"
        )
    try:
        return summary.encode("ascii")
    except UnicodeError as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe aggregate attestation is not ASCII"
        ) from exc


def _review_attestation_summary_bytes(plan, summary_bytes):
    try:
        return load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan.projection.plan_bytes,
            projection=plan.projection,
            summary_bytes=summary_bytes,
        )
    except Exception as exc:
        if isinstance(exc, PitMarketCapMembershipProbeSubmissionError):
            raise
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe aggregate attestation changed"
        ) from exc


def load_persisted_pit_market_cap_membership_probe_output(
    *, plan, review_claim, owner_signature, permit, launch, terminal_status
):
    """Reload and reauthenticate the spent one-summary result read."""

    require_pit_market_cap_membership_probe_terminal_status(
        terminal_status,
        plan=plan,
        permit=permit,
        launch=launch,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    if terminal_status.status != "Completed.":
        raise PitMarketCapMembershipProbeSubmissionError(
            "persisted probe output requires Completed terminal status"
        )
    _require_persisted_output_read_permit(plan, permit, terminal_status)
    summary_bytes = _read_private(
        plan.review_directory / PERSISTED_ATTESTATION_FILENAME,
        MAX_SUMMARY_CHARACTERS,
    )
    return _review_attestation_summary_bytes(plan, summary_bytes)


def _output_read_permit_candidate(plan, permit, terminal, started_at_utc):
    _utc(started_at_utc)
    seed = {
        "schema": OUTPUT_READ_PERMIT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "submission_permit_sha256": permit.permit_sha256,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "started_at_utc": started_at_utc,
        "maximum_backtests_read_calls": 1,
        "selected_summary_statistic": SUMMARY_NAME,
        "backtests_read": True,
        "object_store_export": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    payload = _canonical({**seed, "permit_sha256": digest})
    return digest, payload


def _spend_output_read_permit(plan, payload):
    _write_private_once(
        plan.review_directory / OUTPUT_READ_PERMIT_FILENAME, payload
    )


def _require_persisted_output_read_permit(plan, permit, terminal):
    payload = _read_private(
        plan.review_directory / OUTPUT_READ_PERMIT_FILENAME,
        MAX_CONTROL_BYTES,
    )
    raw = _control_json_object(payload, "persisted probe summary-read permit")
    expected_keys = {
        "schema",
        "plan_sha256",
        "submission_permit_sha256",
        "terminal_receipt_sha256",
        "started_at_utc",
        "maximum_backtests_read_calls",
        "selected_summary_statistic",
        "backtests_read",
        "object_store_export",
        "permit_sha256",
    }
    if set(raw) != expected_keys or raw.get("schema") != OUTPUT_READ_PERMIT_SCHEMA:
        raise PitMarketCapMembershipProbeSubmissionError(
            "persisted probe summary-read permit changed"
        )
    expected_digest, expected_payload = _output_read_permit_candidate(
        plan, permit, terminal, raw.get("started_at_utc")
    )
    if raw.get("permit_sha256") != expected_digest or payload != expected_payload:
        raise PitMarketCapMembershipProbeSubmissionError(
            "persisted probe summary-read permit changed"
        )
    return expected_digest


def _read_pit_market_cap_membership_probe_receipt_once_impl(
    *, plan, review_claim, owner_signature, permit, launch, terminal_status,
    client, started_at_utc, _transport_capability_minter,
) -> (
    ReviewedPitMarketCapMembershipCoverageAttestation
    | PitMarketCapMembershipCoverageNamedRefusal
):
    require_pit_market_cap_membership_probe_terminal_status(
        terminal_status,
        plan=plan,
        permit=permit,
        launch=launch,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    if terminal_status.status != "Completed.":
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe output read requires Completed terminal status"
        )
    output_permit_sha256, output_permit_payload = _output_read_permit_candidate(
        plan, permit, terminal_status, started_at_utc
    )
    try:
        capability = _transport_capability_minter(
            transport=client,
            scope="result_read",
            binding_record={
                "schema": (
                    "arv2-pit-market-cap-membership-probe-"
                    "summary-read-capability-v2"
                ),
                "plan_sha256": plan.plan_sha256,
                "launch_sha256": launch.receipt_sha256,
                "terminal_sha256": terminal_status.receipt_sha256,
                "output_permit_sha256": output_permit_sha256,
                "selected_summary_statistic": SUMMARY_NAME,
                "attestation_schema": ATTESTATION_SCHEMA,
                "object_store_export": False,
            },
            call_budget={"backtests/read": 1},
        )
    except Exception as exc:
        raise PitMarketCapMembershipProbeSubmissionError(
            "probe output-read capability mint failed before permit spend"
        ) from exc
    _spend_output_read_permit(plan, output_permit_payload)
    try:
        response = _transport_call(
            client,
            capability,
            "_read_backtest_result",
            launch.project_id,
            launch.backtest_id,
        )
        summary_bytes = _extract_attestation_summary_bytes(
            response, launch=launch
        )
        reviewed = _review_attestation_summary_bytes(plan, summary_bytes)
        _write_private_once(
            plan.review_directory / PERSISTED_ATTESTATION_FILENAME,
            summary_bytes,
        )
        return reviewed
    except PitMarketCapMembershipProbeSubmissionLocked:
        raise
    except Exception as exc:
        raise PitMarketCapMembershipProbeSubmissionLocked(
            "probe output read became ambiguous; read permit remains consumed"
        ) from exc


def _bind_actions(minter, execute_impl, inspect_impl, read_impl):
    def execute_pit_market_cap_membership_probe_submission_once(**kwargs):
        return execute_impl(_transport_capability_minter=minter, **kwargs)

    def inspect_pit_market_cap_membership_probe_terminal_status(**kwargs):
        return inspect_impl(_transport_capability_minter=minter, **kwargs)

    def read_pit_market_cap_membership_probe_receipt_once(**kwargs):
        return read_impl(_transport_capability_minter=minter, **kwargs)

    return (
        execute_pit_market_cap_membership_probe_submission_once,
        inspect_pit_market_cap_membership_probe_terminal_status,
        read_pit_market_cap_membership_probe_receipt_once,
    )


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = formal._claim_pit_market_cap_membership_probe_transport_capability_minter()

(
    execute_pit_market_cap_membership_probe_submission_once,
    inspect_pit_market_cap_membership_probe_terminal_status,
    read_pit_market_cap_membership_probe_receipt_once,
) = _bind_actions(
    _transport_capability_minter,
    _execute_pit_market_cap_membership_probe_submission_once_impl,
    _inspect_pit_market_cap_membership_probe_terminal_status_impl,
    _read_pit_market_cap_membership_probe_receipt_once_impl,
)

_seal_transport_capability_callers(
    (
        (
            "submission",
            ((
                _execute_pit_market_cap_membership_probe_submission_once_impl,
                execute_pit_market_cap_membership_probe_submission_once,
            ),),
        ),
        (
            "status",
            ((
                _inspect_pit_market_cap_membership_probe_terminal_status_impl,
                inspect_pit_market_cap_membership_probe_terminal_status,
            ),),
        ),
        (
            "result_read",
            ((
                _read_pit_market_cap_membership_probe_receipt_once_impl,
                read_pit_market_cap_membership_probe_receipt_once,
            ),),
        ),
    )
)

del _transport_capability_minter
del _seal_transport_capability_callers
del _execute_pit_market_cap_membership_probe_submission_once_impl
del _inspect_pit_market_cap_membership_probe_terminal_status_impl
del _read_pit_market_cap_membership_probe_receipt_once_impl
del _bind_actions
