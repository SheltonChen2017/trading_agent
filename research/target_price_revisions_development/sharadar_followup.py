"""One approved status-only follow-up using a separately hash-bound projector.

Imports are inert. One immutable claim precedes credentials; the old spent
collectors are never rearmed. Structural observations confer no data authority.
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import sharadar_projection
from .source_audit import (
    AUTHORITY, LANE_BRANCH, LANE_ROOT, PRIVATE_ROOT, REQUESTS, SourceAuditError,
    _canonical, _clock, _digest, _https_get, _private_directory,
    _production_credential, _publish, _reduce_response, _source_object,
    _valid_credential, _verify_execution_identity,
)

FOLLOWUP_ID = "TPR-SHARADAR-FOLLOWUP-20261007-001"
AUDITOR_CODE_SHA256 = "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
LIMITS = {"requests": 1, "response_bytes": 65536, "request_timeout_seconds": 10,
    "redirects": 0, "retries": 0, "pages_followed": 0, "rows": 0,
    "max_report_bytes": 32768, "max_file_descriptors": 8}
_FIXED_CREDENTIAL, _FIXED_TRANSPORT = _production_credential, _https_get


@dataclass(frozen=True)
class FollowupPlan:
    payload: bytes
    sha256: str

    def body(self) -> dict:
        if type(self.payload) is not bytes or len(self.payload) > 16384 or _digest(self.payload) != self.sha256:
            raise SourceAuditError("invalid follow-up plan identity")
        try:
            body = _source_object(self.payload)
            expected = freeze_followup_plan(code_sha256=body["code_sha256"],
                projector_sha256=body["projector_sha256"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"],
                created_utc=body["created_utc"], expires_utc=body["expires_utc"], mode=body["mode"])
            if self.payload != expected.payload:
                raise SourceAuditError("invalid follow-up plan policy")
            return body
        except (ValueError, TypeError, KeyError):
            raise SourceAuditError("invalid follow-up plan policy") from None


def freeze_followup_plan(*, code_sha256: str, projector_sha256: str, git_sha: str,
                         owner_instruction_sha256: str, created_utc: str,
                         expires_utc: str, mode: str = "production") -> FollowupPlan:
    for value, length in ((code_sha256, 64), (projector_sha256, 64),
                          (git_sha, 40), (owner_instruction_sha256, 64)):
        if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None:
            raise SourceAuditError("invalid follow-up identity")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        raise SourceAuditError("invalid follow-up mode")
    if not created < expires <= created + timedelta(hours=48):
        raise SourceAuditError("invalid follow-up expiry")
    payload = _canonical({"schema": "tpr-sharadar-followup-plan-v1", "followup_id": FOLLOWUP_ID,
        "mode": mode, "code_sha256": code_sha256, "projector_sha256": projector_sha256,
        "auditor_code_sha256": AUDITOR_CODE_SHA256, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "private_destination": "artifacts/target_price_source_audit",
        "requests": [REQUESTS[1].body()], "limits": dict(LIMITS), "authority": dict(AUTHORITY),
        "projection_fields": list(sharadar_projection.FIELDS),
        "row_markers": list(sharadar_projection.ROW_MARKERS), "raw_retention": False,
        "raw_response_identity_retained": False, "d0_renewed": False,
        "original_audit_renewed": False, "previous_diagnostic_renewed": False,
        "previous_shape_renewed": False, "license_entitlement": "unestablished",
        "point_in_time_facts": "unestablished"})
    return FollowupPlan(payload, _digest(payload))


def _verify_file(source: Path, filename: str, expected_sha256: str) -> None:
    descriptor = None
    try:
        expected = LANE_ROOT / "research" / "target_price_revisions_development" / filename
        if source != expected or source.resolve() != expected:
            raise SourceAuditError("follow-up code identity mismatch")
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 262144:
            raise SourceAuditError("follow-up code identity mismatch")
        payload = os.read(descriptor, 262144)
        if len(payload) != metadata.st_size or _digest(payload) != expected_sha256:
            raise SourceAuditError("follow-up code identity mismatch")
    except OSError:
        raise SourceAuditError("follow-up code identity unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_identity(body: dict) -> None:
    _verify_execution_identity({"git_sha": body["git_sha"], "code_sha256": AUDITOR_CODE_SHA256})
    _verify_file(Path(__file__), "sharadar_followup.py", body["code_sha256"])
    _verify_file(Path(sharadar_projection.__file__), "sharadar_projection.py", body["projector_sha256"])


def _claim(directory_fd: int, plan: FollowupPlan, current: datetime) -> None:
    payload = _canonical({"schema": "tpr-sharadar-followup-spent-v1", "followup_id": FOLLOWUP_ID,
        "plan_sha256": plan.sha256, "started_utc": current.isoformat(), "mode": plan.body()["mode"]})
    try:
        descriptor = os.open(FOLLOWUP_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise SourceAuditError("follow-up already spent") from None
    except OSError:
        raise SourceAuditError("follow-up claim unavailable") from None
    try:
        if os.write(descriptor, payload) != len(payload):
            raise SourceAuditError("follow-up claim incomplete; one-shot scope remains spent")
        os.fsync(descriptor)
        os.fsync(directory_fd)
    except OSError:
        raise SourceAuditError("follow-up claim failed; one-shot scope remains spent") from None
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class FollowupResult:
    payload: bytes
    sha256: str
    aggregate_path: Path
    terminal_path: Path


def execute_followup(plan: FollowupPlan, private_root: Path, *, now: datetime | None = None,
                     credential_resolver: Callable | None = None,
                     transport: Callable | None = None) -> FollowupResult:
    """One operation; only explicitly offline fixtures accept injected adapters."""
    if type(plan) is not FollowupPlan:
        raise SourceAuditError("invalid follow-up plan frame")
    body = plan.body()
    mode = body["mode"]
    if mode == "production":
        if now is not None or credential_resolver is not None or transport is not None:
            raise SourceAuditError("follow-up injections require offline fixture mode")
        if private_root != PRIVATE_ROOT:
            raise SourceAuditError("production requires the fixed lane audit root")
        _verify_identity(body)
    else:
        if private_root == PRIVATE_ROOT:
            raise SourceAuditError("offline fixture cannot consume the production follow-up")
        if (credential_resolver is None or transport is None
                or credential_resolver in (_FIXED_CREDENTIAL, _production_credential)
                or transport in (_FIXED_TRANSPORT, _https_get)):
            raise SourceAuditError("offline follow-up requires synthetic fixtures")
    current = datetime.now(timezone.utc) if now is None else now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise SourceAuditError("invalid follow-up UTC clock")
    if not _clock(body["created_utc"]) <= current < _clock(body["expires_utc"]):
        raise SourceAuditError("follow-up plan is not currently valid")
    directory_fd = _private_directory(private_root, mode)
    try:
        _claim(directory_fd, plan, current)
        status, attempts, interrupted = "COMPLETED", 0, False
        provider = {"provider": "sharadar", "http_status": None, "disposition": "not_attempted",
            "authenticated_access_observed": False, "response_bytes": 0, "response_bytes_complete": True,
            "response_sha256": None, "metadata": {"metadata_shape_observed": False,
                "size_bytes": None, "snapshot_utc": None}}
        projection, table_literal, classification = None, "not_observed", "not_observed"
        try:
            resolver = _production_credential if mode == "production" else credential_resolver
            fetch = _https_get if mode == "production" else transport
            credential = resolver("sharadar")
            valid = _valid_credential(credential) and (mode == "production" or credential.startswith("SYNTHETIC_"))
            if not valid:
                provider["disposition"] = "credential_unavailable"
            else:
                attempts = 1
                response = fetch(REQUESTS[1], credential)
                provider = _reduce_response(REQUESTS[1], response, (credential,), actual=False)
                safe_to_project = provider["response_sha256"] is not None
                # In-memory privacy validation precedes projection; no raw-body
                # digest or source value is published by this operation.
                provider["response_sha256"] = None
                provider["authenticated_access_observed"] = False
                provider["metadata"] = {"metadata_shape_observed": False,
                    "size_bytes": None, "snapshot_utc": None}
                if (response.refusal is not None or provider["disposition"] in
                        ("redirect_refused", "encoding_refused", "content_type_refused", "response_byte_limit_refused")):
                    provider["response_bytes_complete"] = False
                if safe_to_project:
                    decoded = _source_object(response.body)
                    projection = sharadar_projection.project_metadata_shape(decoded)
                    table = decoded.get("table")
                    table_literal = ("tickers" if type(table) is str and table == "tickers"
                        else "other_string" if type(table) is str else "not_string")
                    classification = "status_structure_observed" if response.status == 200 else "http_access_refused"
        except KeyboardInterrupt:
            status, interrupted = "INTERRUPTED", True
            provider["disposition"] = "transport_interrupted" if attempts else "credential_interrupted"
            provider["response_bytes_complete"] = False
        except Exception:
            # Provider exceptions may contain authenticated URLs or values.
            status = "FAILED"
            provider["disposition"] = "transport_failed" if attempts else "credential_failed"
            provider["response_bytes_complete"] = False
        report = {"schema": "tpr-sharadar-followup-report-v1", "followup_id": FOLLOWUP_ID,
            "mode": mode, "status": status, "started_utc": current.isoformat(), "plan_sha256": plan.sha256,
            "code_sha256": body["code_sha256"], "projector_sha256": body["projector_sha256"],
            "auditor_code_sha256": AUDITOR_CODE_SHA256, "git_sha": body["git_sha"],
            "owner_instruction_sha256": body["owner_instruction_sha256"], "provider": provider,
            "classification": classification, "table_literal": table_literal, "projection": projection,
            "credential_state": "not_proven", "provider_requests": attempts if mode == "production" else 0,
            "fixture_transport_calls": attempts if mode == "offline-fixture" else 0,
            "authority": dict(AUTHORITY), "license_entitlement": "unestablished",
            "point_in_time_facts": "unestablished", "real_development_backtest_ready": False,
            "canonical_admission": False, "raw_response_identity_retained": False,
            "d0_renewed": False, "original_audit_renewed": False, "previous_diagnostic_renewed": False,
            "previous_shape_renewed": False, "outcome_reads": 0, "qc_attempts": 0, "development_looks": 0}
        payload = _canonical(report)
        if len(payload) > LIMITS["max_report_bytes"]:
            raise SourceAuditError("follow-up report exceeds budget; one-shot scope remains spent")
        identity = _digest(payload)
        aggregate_name = FOLLOWUP_ID + "." + identity + ".aggregate.json"
        terminal_name = FOLLOWUP_ID + ".terminal.json"
        _publish(directory_fd, aggregate_name, payload)
        _publish(directory_fd, terminal_name, _canonical({"schema": "tpr-sharadar-followup-terminal-v1",
            "followup_id": FOLLOWUP_ID, "plan_sha256": plan.sha256, "aggregate_sha256": identity,
            "status": status, "mode": mode}))
        if interrupted:
            raise KeyboardInterrupt("follow-up interrupted; one-shot scope remains spent") from None
        return FollowupResult(payload, identity, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
